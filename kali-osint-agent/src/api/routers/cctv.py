"""CCTV camera discovery endpoints."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.api.auth import get_current_user
from src.tools.cctv_tool import cctv_tool

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/cctv", tags=["cctv"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CCTVRequest(BaseModel):
    lat: float = Field(..., description="Latitude of the center point")
    lng: float = Field(..., description="Longitude of the center point")
    radius_km: float = Field(default=10.0, ge=1, le=500, description="Initial search radius in km")
    max_radius_km: float = Field(default=50.0, ge=1, le=500, description="Maximum expansion radius in km")
    expand_step_km: float = Field(default=10.0, ge=1, le=100, description="Expansion step size in km")


class CameraInfo(BaseModel):
    ip: str
    port: int | None = None
    product: str = ""
    org: str = ""
    city: str = ""
    country: str = ""
    latitude: float | None = None
    longitude: float | None = None
    distance_km: float | None = None
    http_title: str = ""


class CCTVResponse(BaseModel):
    cameras: list[CameraInfo]
    total_found: int
    search_radius_km: float
    center: dict


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/discover", response_model=CCTVResponse)
async def discover_cameras(
    request: CCTVRequest,
    user: dict = Depends(get_current_user),
):
    """Discover publicly accessible cameras near a geographic point.

    Uses Shodan to search for known camera products and services
    within the specified radius, expanding outward if needed.
    """
    logger.info(
        "cctv.discover_request",
        lat=request.lat,
        lng=request.lng,
        radius_km=request.radius_km,
    )

    result = await cctv_tool(
        lat=request.lat,
        lng=request.lng,
        radius_km=request.radius_km,
        max_radius_km=request.max_radius_km,
        expand_step_km=request.expand_step_km,
    )

    cameras = [
        CameraInfo(
            ip=cam.get("ip", ""),
            port=cam.get("port"),
            product=cam.get("product", ""),
            org=cam.get("org", ""),
            city=cam.get("city", ""),
            country=cam.get("country", ""),
            latitude=cam.get("latitude"),
            longitude=cam.get("longitude"),
            distance_km=cam.get("distance_km"),
            http_title=cam.get("http_title", ""),
        )
        for cam in result.get("cameras", [])
    ]

    return CCTVResponse(
        cameras=cameras,
        total_found=result.get("total_found", 0),
        search_radius_km=result.get("search_radius_km", request.radius_km),
        center=result.get("center", {"lat": request.lat, "lng": request.lng}),
    )
