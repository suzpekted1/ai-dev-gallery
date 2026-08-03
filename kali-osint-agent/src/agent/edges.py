"""Conditional edge functions for the OSINT agent graph."""

from __future__ import annotations

from typing import Literal

from src.agent.state import AgentState


def route_by_task_type(
    state: AgentState,
) -> Literal[
    "osint_gather",
    "recon_scan",
    "pentest_execute",
    "cctv_discover",
    "wayback_search",
    "report",
]:
    """Return the next node name based on ``state["task_type"]``.

    Mapping:
    - ``osint``     -> ``osint_gather``
    - ``recon``     -> ``recon_scan``
    - ``pentest``   -> ``recon_scan``  (goes through approval first)
    - ``cctv``      -> ``cctv_discover``
    - ``wayback``   -> ``wayback_search``
    - ``report``    -> ``report``      (skip to report generation)
    - ``analysis``  -> ``osint_gather``
    """
    task_type = state["task_type"]
    routing: dict[str, str] = {
        "osint": "osint_gather",
        "recon": "recon_scan",
        "pentest": "recon_scan",
        "cctv": "cctv_discover",
        "wayback": "wayback_search",
        "report": "report",
        "analysis": "osint_gather",
    }
    return routing.get(task_type, "osint_gather")


def check_approval(
    state: AgentState,
) -> Literal["pentest_execute", "notify"]:
    """Route based on the approval decision.

    Returns ``"pentest_execute"`` if the action was approved, or
    ``"notify"`` if it was denied (skipping execution).
    """
    if state.get("approval_status") == "approved":
        return "pentest_execute"
    return "notify"
