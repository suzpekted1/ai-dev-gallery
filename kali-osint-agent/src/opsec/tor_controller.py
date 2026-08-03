"""Tor circuit management via the stem control protocol."""

from __future__ import annotations

import httpx
import structlog
from stem import Signal
from stem.control import Controller

from configs.settings import settings

logger = structlog.get_logger(__name__)


class TorController:
    """High-level wrapper around the Tor control port."""

    def __init__(self) -> None:
        self._host = "127.0.0.1"
        self._control_port = settings.tor_control_port
        self._password = settings.tor_control_password
        self._socks_port = settings.tor_socks_port

    # ------------------------------------------------------------------
    # Connection helper
    # ------------------------------------------------------------------

    def _connect(self) -> Controller:
        """Return an authenticated ``Controller`` instance."""

        controller = Controller.from_port(address=self._host, port=self._control_port)
        controller.authenticate(password=self._password)
        return controller

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def new_identity(self) -> None:
        """Request a new Tor identity (NEWNYM signal).

        This causes Tor to build new circuits so subsequent connections
        use different exit nodes.
        """

        with self._connect() as ctrl:
            ctrl.signal(Signal.NEWNYM)
            logger.info("tor_controller.new_identity_requested")

    async def get_exit_ip(self) -> str:
        """Resolve the current Tor exit IP by querying api.ipify.org
        through the local Tor SOCKS proxy."""

        proxy = f"socks5://{self._host}:{self._socks_port}"
        async with httpx.AsyncClient(proxy=proxy, timeout=15) as client:
            response = await client.get("https://api.ipify.org")
            response.raise_for_status()
            ip = response.text.strip()
            logger.info("tor_controller.exit_ip", ip=ip)
            return ip

    def get_circuit_info(self) -> list[dict]:
        """Return information about active Tor circuits.

        Each dict contains keys ``id``, ``status``, ``purpose``, and
        ``path`` (a list of relay fingerprints).
        """

        circuits: list[dict] = []
        with self._connect() as ctrl:
            for circ in ctrl.get_circuits():
                circuits.append(
                    {
                        "id": circ.id,
                        "status": str(circ.status),
                        "purpose": str(circ.purpose),
                        "path": [entry[0] for entry in circ.path],
                    }
                )
        logger.debug("tor_controller.circuits", count=len(circuits))
        return circuits

    def is_connected(self) -> bool:
        """Return ``True`` if the Tor control port is reachable and
        authenticated."""

        try:
            with self._connect() as ctrl:
                _ = ctrl.get_version()
            return True
        except Exception:
            logger.warning("tor_controller.not_connected")
            return False


tor_controller = TorController()
