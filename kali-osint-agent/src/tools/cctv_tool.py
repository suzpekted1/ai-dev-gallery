"""CCTV camera discovery tool using Shodan and Censys geolocation queries."""

from __future__ import annotations

import asyncio
import math

import shodan
import structlog

from configs.settings import settings

logger = structlog.get_logger(__name__)

# Shodan search queries commonly associated with network cameras and
# DVR/NVR devices.  Each is tried separately and results are merged.
_CAMERA_QUERIES = [
    'product:"webcam"',
    'product:"IP Camera"',
    'http.title:"DVR"',
    'http.title:"Network Camera"',
    'product:"Hikvision"',
    'product:"Dahua"',
    'port:554 has_screenshot:true',
    'http.title:"webcamXP"',
]


async def cctv_tool(
    lat: float,
    lng: float,
    radius_km: float = 10.0,
    max_radius_km: float = 50.0,
    expand_step_km: float = 10.0,
) -> dict:
    """Discover publicly accessible cameras near a geographic point.

    The search starts at *radius_km* and expands by *expand_step_km*
    until cameras are found or *max_radius_km* is reached.

    Parameters
    ----------
    lat, lng:
        Center coordinates (decimal degrees).
    radius_km:
        Initial search radius in kilometers.
    max_radius_km:
        Maximum radius to expand to.
    expand_step_km:
        Step size for each expansion round.

    Returns
    -------
    dict with ``cameras`` list, ``total_found``, ``search_radius_km``.
    """
    if not settings.shodan_api_key:
        logger.warning("cctv_tool.no_api_key")
        return {"cameras": [], "total_found": 0, "error": "Shodan API key not configured"}

    logger.info("cctv_tool.start", lat=lat, lng=lng, radius_km=radius_km)
    api = shodan.Shodan(settings.shodan_api_key)

    current_radius = radius_km
    all_cameras: list[dict] = []
    seen_ips: set[str] = set()

    while current_radius <= max_radius_km:
        geo_filter = f"geo:{lat},{lng},{current_radius}"

        for base_query in _CAMERA_QUERIES:
            query = f"{base_query} {geo_filter}"
            try:
                data = await asyncio.get_event_loop().run_in_executor(
                    None, api.search, query,
                )
                for match in data.get("matches", []):
                    ip = match.get("ip_str", "")
                    if ip in seen_ips:
                        continue
                    seen_ips.add(ip)

                    location = match.get("location", {})
                    cam_lat = location.get("latitude")
                    cam_lng = location.get("longitude")
                    distance = _haversine(lat, lng, cam_lat, cam_lng) if cam_lat and cam_lng else None

                    camera = {
                        "ip": ip,
                        "port": match.get("port"),
                        "product": match.get("product", ""),
                        "org": match.get("org", ""),
                        "hostnames": match.get("hostnames", []),
                        "city": location.get("city", ""),
                        "country": location.get("country_name", ""),
                        "latitude": cam_lat,
                        "longitude": cam_lng,
                        "distance_km": round(distance, 2) if distance is not None else None,
                        "banner": (match.get("data", "")[:300] if match.get("data") else ""),
                        "http_title": match.get("http", {}).get("title", "") if match.get("http") else "",
                    }
                    all_cameras.append(camera)

            except shodan.APIError as exc:
                logger.warning("cctv_tool.query_error", query=base_query, error=str(exc))
                continue

        if all_cameras:
            break

        current_radius += expand_step_km
        logger.info("cctv_tool.expanding", new_radius=current_radius)

    # Sort by distance
    all_cameras.sort(key=lambda c: c.get("distance_km") or float("inf"))

    result = {
        "cameras": all_cameras,
        "total_found": len(all_cameras),
        "search_radius_km": current_radius,
        "center": {"lat": lat, "lng": lng},
    }

    logger.info("cctv_tool.complete", total=result["total_found"], radius=current_radius)
    return result


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Compute distance in km between two lat/lng points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c
