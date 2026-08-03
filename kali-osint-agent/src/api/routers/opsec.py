"""OPSEC status and control endpoints."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from configs.settings import ProxyMode
from src.api.auth import get_current_user
from src.opsec.proxy_manager import proxy_manager
from src.opsec.tor_controller import tor_controller
from src.opsec.traffic_analyzer import traffic_analyzer

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/opsec", tags=["opsec"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class OpsecStatus(BaseModel):
    proxy_mode: str
    tor_connected: bool
    exit_ip: str | None = None
    traffic_alerts: int
    should_rotate: bool


class ModeChangeRequest(BaseModel):
    mode: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/status", response_model=OpsecStatus)
async def get_opsec_status(user: dict = Depends(get_current_user)):
    """Return the current OPSEC posture including proxy mode, Tor
    connectivity, exit IP, and traffic alert status."""
    tor_connected = tor_controller.is_connected()

    exit_ip: str | None = None
    if tor_connected:
        try:
            exit_ip = await tor_controller.get_exit_ip()
        except Exception:
            pass

    should_rotate = traffic_analyzer.should_rotate_identity()

    return OpsecStatus(
        proxy_mode=proxy_manager._mode.value,
        tor_connected=tor_connected,
        exit_ip=exit_ip,
        traffic_alerts=len(traffic_analyzer._alerts),
        should_rotate=should_rotate,
    )


@router.post("/mode")
async def change_proxy_mode(
    request: ModeChangeRequest,
    user: dict = Depends(get_current_user),
):
    """Change the active proxy mode.

    Valid modes: stealth, fast, direct, rotating, whonix.
    When switching to whonix mode, Tor connectivity is verified first.
    """
    mode_map = {
        "stealth": ProxyMode.STEALTH,
        "fast": ProxyMode.FAST,
        "direct": ProxyMode.DIRECT,
        "rotating": ProxyMode.ROTATING,
        "whonix": ProxyMode.WHONIX,
    }

    mode_str = request.mode.lower()
    new_mode = mode_map.get(mode_str)
    if new_mode is None:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode: {request.mode}. "
            f"Valid modes: {', '.join(mode_map.keys())}",
        )

    # Validate Whonix connectivity before switching
    if new_mode == ProxyMode.WHONIX:
        if not tor_controller.is_connected():
            raise HTTPException(
                status_code=503,
                detail="Whonix gateway is not reachable. Ensure the Whonix VM is running.",
            )

    proxy_manager._mode = new_mode
    logger.info("opsec.mode_changed", new_mode=new_mode.value, by=user["username"])
    return {"status": "ok", "mode": new_mode.value}


@router.post("/new-identity")
async def request_new_identity(user: dict = Depends(get_current_user)):
    """Request a new Tor identity (NEWNYM signal).

    Causes Tor to build new circuits so subsequent connections
    use different exit nodes.
    """
    try:
        tor_controller.new_identity()
        new_ip = await tor_controller.get_exit_ip()
        logger.info("opsec.new_identity", exit_ip=new_ip, by=user["username"])
        return {"status": "ok", "new_exit_ip": new_ip}
    except Exception as exc:
        logger.error("opsec.new_identity_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=f"Failed to rotate identity: {exc}")


@router.get("/circuits")
async def get_circuits(user: dict = Depends(get_current_user)):
    """Return information about active Tor circuits.

    Each circuit includes its ID, status, purpose, and the list of
    relay fingerprints in the path.
    """
    try:
        circuits = tor_controller.get_circuit_info()
        return {"circuits": circuits, "count": len(circuits)}
    except Exception as exc:
        logger.error("opsec.circuits_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=f"Failed to get circuit info: {exc}")
