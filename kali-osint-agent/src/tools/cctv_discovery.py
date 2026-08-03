"""CCTV / IP camera discovery via Shodan and Censys with radius expansion."""

from __future__ import annotations

import logging
import math
from typing import Any

from src.db.neo4j_client import neo4j_client
from src.tools.base import ScopedTool
from src.tools.censys_tool import CensysTool
from src.tools.shodan_tool import ShodanTool

logger = logging.getLogger(__name__)

# Shodan search fragments that tend to surface IP cameras
CAMERA_QUERIES = [
    "webcam",
    "camera",
    "rtsp",
    "hikvision",
    "dahua",
    "axis",
]


class CCTVDiscoveryTool(ScopedTool):
    """Discover internet-connected cameras near a geographic location."""

    name = "cctv_discovery"
    requires_approval = False
    is_active_scan = False

    def __init__(self) -> None:
        self._shodan = ShodanTool()
        self._censys = CensysTool()

    async def _execute(
        self,
        *,
        target: str,
        lat: float,
        lng: float,
        radius_km: int = 25,
        max_radius_km: int = 100,
        expand_step_km: int = 25,
        min_results: int = 5,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Search for cameras near (lat, lng), expanding until enough are found.

        Parameters
        ----------
        target:
            A label for the search (e.g. city name).
        lat, lng:
            Centre-point coordinates.
        radius_km:
            Initial search radius in km.
        max_radius_km:
            Stop expanding beyond this radius.
        expand_step_km:
            Increment for each expansion step.
        min_results:
            Keep expanding until at least this many cameras are found.
        """
        all_cameras: list[dict[str, Any]] = []
        seen_ips: set[str] = set()
        current_radius = radius_km

        while current_radius <= max_radius_km:
            cameras = await self._search_radius(lat, lng, current_radius, seen_ips)
            all_cameras.extend(cameras)

            if len(all_cameras) >= min_results:
                break
            current_radius += expand_step_km

        # Store results in Neo4j
        for cam in all_cameras:
            await self._store_camera(cam, target)

        return {
            "target": target,
            "lat": lat,
            "lng": lng,
            "final_radius_km": current_radius,
            "cameras_found": len(all_cameras),
            "cameras": all_cameras,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _search_radius(
        self,
        lat: float,
        lng: float,
        radius_km: int,
        seen_ips: set[str],
    ) -> list[dict[str, Any]]:
        """Run camera-related queries on Shodan and Censys for a given radius."""
        cameras: list[dict[str, Any]] = []

        # Shodan geo searches
        for query_fragment in CAMERA_QUERIES:
            try:
                result = await self._shodan._execute(
                    target="",
                    action="geo",
                    query=query_fragment,
                    lat=lat,
                    lng=lng,
                    radius_km=radius_km,
                )
                for match in result.get("matches", []):
                    ip = match.get("ip")
                    if ip and ip not in seen_ips:
                        seen_ips.add(ip)
                        loc = match.get("location", {})
                        cam_lat = loc.get("latitude")
                        cam_lng = loc.get("longitude")
                        distance = (
                            _haversine(lat, lng, cam_lat, cam_lng)
                            if cam_lat is not None and cam_lng is not None
                            else None
                        )
                        cameras.append(
                            {
                                "ip": ip,
                                "port": match.get("port"),
                                "brand": match.get("product", "unknown"),
                                "country": loc.get("country"),
                                "city": loc.get("city"),
                                "latitude": cam_lat,
                                "longitude": cam_lng,
                                "distance_km": round(distance, 2) if distance is not None else None,
                                "hostnames": match.get("hostnames", []),
                                "source": "shodan",
                            }
                        )
            except Exception:
                logger.warning("Shodan camera query failed: %s", query_fragment, exc_info=True)

        # Censys search
        try:
            censys_query = " OR ".join(f'services.service_name: "{q}"' for q in CAMERA_QUERIES[:3])
            result = await self._censys._execute(
                target="",
                action="search",
                query=censys_query,
                per_page=25,
                pages=1,
            )
            for match in result.get("matches", []):
                ip = match.get("ip")
                if ip and ip not in seen_ips:
                    seen_ips.add(ip)
                    loc = match.get("location", {})
                    services = match.get("services", [])
                    port = services[0].get("port") if services else None
                    cameras.append(
                        {
                            "ip": ip,
                            "port": port,
                            "brand": "unknown",
                            "country": loc.get("country"),
                            "city": loc.get("city"),
                            "latitude": loc.get("coordinates", {}).get("latitude") if isinstance(loc, dict) else None,
                            "longitude": loc.get("coordinates", {}).get("longitude") if isinstance(loc, dict) else None,
                            "distance_km": None,
                            "hostnames": [],
                            "source": "censys",
                        }
                    )
        except Exception:
            logger.warning("Censys camera search failed", exc_info=True)

        return cameras

    async def _store_camera(self, cam: dict[str, Any], target_label: str) -> None:
        """Merge camera into Neo4j and link to the target."""
        try:
            await neo4j_client.merge_node(
                label="Camera",
                match_keys={"ip": cam["ip"], "port": cam.get("port", 0)},
                set_keys={
                    "brand": cam.get("brand", "unknown"),
                    "country": cam.get("country"),
                    "city": cam.get("city"),
                    "location": (
                        f"{cam['latitude']},{cam['longitude']}"
                        if cam.get("latitude") is not None
                        else None
                    ),
                    "distance_km": cam.get("distance_km"),
                    "source": cam.get("source"),
                },
            )

            # Ensure a Target node exists and link to it
            await neo4j_client.merge_node(
                label="Target",
                match_keys={"domain": target_label},
                set_keys={},
            )
            await neo4j_client.create_relationship(
                from_label="Target",
                from_match={"domain": target_label},
                to_label="Camera",
                to_match={"ip": cam["ip"], "port": cam.get("port", 0)},
                rel_type="HAS_CAMERA",
            )
        except Exception:
            logger.warning("Failed to store camera %s in Neo4j", cam.get("ip"), exc_info=True)


# ---------------------------------------------------------------------------
# Geo helpers
# ---------------------------------------------------------------------------

_EARTH_RADIUS_KM = 6371.0


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate the great-circle distance between two points in km."""
    lat1_r, lng1_r = math.radians(lat1), math.radians(lng1)
    lat2_r, lng2_r = math.radians(lat2), math.radians(lng2)
    dlat = lat2_r - lat1_r
    dlng = lng2_r - lng1_r
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    return _EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))
