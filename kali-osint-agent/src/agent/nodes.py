"""Async node functions for the OSINT agent graph."""

from __future__ import annotations

import json
from typing import Any

import structlog
from langchain_core.messages import AIMessage, HumanMessage

from src.agent.state import AgentState

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Intake
# ---------------------------------------------------------------------------


async def intake_node(state: AgentState) -> dict[str, Any]:
    """Log the start of a new task."""
    logger.info(
        "intake.start",
        task_id=state.get("task_id"),
        target=state["target"],
        task_type=state["task_type"],
    )
    return {
        "messages": [
            AIMessage(content=f"Starting {state['task_type']} task on {state['target']}")
        ],
    }


# ---------------------------------------------------------------------------
# Classify
# ---------------------------------------------------------------------------


async def classify_node(state: AgentState) -> dict[str, Any]:
    """Determine whether the task requires human approval."""
    task_type = state["task_type"]
    needs_approval = task_type in ("pentest", "recon")
    logger.info("classify", task_type=task_type, needs_approval=needs_approval)
    return {
        "requires_approval": needs_approval,
        "approval_status": "pending" if needs_approval else "not_needed",
    }


# ---------------------------------------------------------------------------
# OPSEC setup
# ---------------------------------------------------------------------------


async def opsec_setup_node(state: AgentState) -> dict[str, Any]:
    """Configure the proxy manager and verify Tor / Whonix connectivity."""
    from configs.settings import ProxyMode
    from src.opsec.proxy_manager import proxy_manager
    from src.opsec.tor_controller import tor_controller

    mode_str = state.get("proxy_mode", "stealth")
    mode_map = {
        "stealth": ProxyMode.STEALTH,
        "fast": ProxyMode.FAST,
        "direct": ProxyMode.DIRECT,
        "rotating": ProxyMode.ROTATING,
        "whonix": ProxyMode.WHONIX,
    }
    selected_mode = mode_map.get(mode_str, ProxyMode.STEALTH)
    proxy_manager._mode = selected_mode

    # Check Tor connectivity for modes that require it
    if selected_mode in (ProxyMode.STEALTH, ProxyMode.ROTATING):
        tor_ok = tor_controller.is_connected()
        if not tor_ok:
            logger.warning("opsec_setup.tor_not_connected", fallback="direct")
            proxy_manager._mode = ProxyMode.DIRECT
            selected_mode = ProxyMode.DIRECT

    # Check Whonix connectivity
    if selected_mode == ProxyMode.WHONIX:
        tor_ok = tor_controller.is_connected()
        if not tor_ok:
            logger.warning("opsec_setup.whonix_not_available", fallback="stealth")
            proxy_manager._mode = ProxyMode.STEALTH
            selected_mode = ProxyMode.STEALTH

    logger.info("opsec_setup.configured", mode=selected_mode.value)
    return {
        "messages": [
            AIMessage(content=f"OPSEC configured: proxy_mode={selected_mode.value}")
        ],
    }


# ---------------------------------------------------------------------------
# OSINT gather
# ---------------------------------------------------------------------------


async def osint_gather_node(state: AgentState) -> dict[str, Any]:
    """Run theHarvester, web scraper, and Shodan in sequence."""
    from src.tools.harvester_tool import HarvesterTool
    from src.tools.shodan_tool import ShodanTool
    from src.tools.web_scraper import WebScraperTool

    target = state["target"]
    results: list[dict[str, Any]] = list(state.get("tool_results", []))

    # theHarvester
    harvester = HarvesterTool()
    harvester_result = await harvester.run(target=target)
    results.append({"tool": "theharvester", "data": harvester_result})

    # Web scraper
    scraper = WebScraperTool()
    url = f"https://{target}" if not target.startswith("http") else target
    scraper_result = await scraper.run(target=url)
    results.append({"tool": "web_scraper", "data": scraper_result})

    # Shodan
    shodan = ShodanTool()
    shodan_result = await shodan.run(target=target, action="search", query=target)
    results.append({"tool": "shodan", "data": shodan_result})

    logger.info("osint_gather.complete", tools_ran=3, target=target)
    return {
        "tool_results": results,
        "messages": [
            AIMessage(content=f"OSINT gathering complete: {len(results)} tool results collected")
        ],
    }


# ---------------------------------------------------------------------------
# Recon scan
# ---------------------------------------------------------------------------


async def recon_scan_node(state: AgentState) -> dict[str, Any]:
    """Create a pending nmap action that requires approval."""
    target = state["target"]
    pending = {
        "tool": "nmap",
        "target": target,
        "args": {"scan_type": "quick"},
        "description": f"Network reconnaissance scan (nmap quick) on {target}",
    }
    logger.info("recon_scan.pending_approval", target=target)
    return {
        "pending_action": pending,
        "requires_approval": True,
        "approval_status": "pending",
    }


# ---------------------------------------------------------------------------
# Pentest execute
# ---------------------------------------------------------------------------


async def pentest_execute_node(state: AgentState) -> dict[str, Any]:
    """Execute the approved pending tool action."""
    from src.tools.nmap_tool import NmapTool
    from src.tools.shodan_tool import ShodanTool

    action = state.get("pending_action")
    if not action:
        return {"error": "No pending action to execute"}

    tool_name = action.get("tool", "")
    target = action.get("target", state["target"])
    args = action.get("args", {})

    tool_map: dict[str, Any] = {
        "nmap": NmapTool(),
        "shodan": ShodanTool(),
    }

    tool = tool_map.get(tool_name)
    if tool is None:
        return {"error": f"Unknown tool: {tool_name}"}

    result = await tool.run(target=target, **args)
    existing = list(state.get("tool_results", []))
    existing.append({"tool": tool_name, "data": result})

    logger.info("pentest_execute.done", tool=tool_name, target=target)
    return {
        "tool_results": existing,
        "pending_action": None,
        "messages": [AIMessage(content=f"Executed {tool_name} on {target}")],
    }


# ---------------------------------------------------------------------------
# CCTV discover
# ---------------------------------------------------------------------------


async def cctv_discover_node(state: AgentState) -> dict[str, Any]:
    """Parse lat/lng from description JSON and run the CCTV discovery tool."""
    from src.tools.cctv_discovery import CCTVDiscoveryTool

    desc = state.get("description", "")
    try:
        params = json.loads(desc) if desc.strip().startswith("{") else {}
    except json.JSONDecodeError:
        params = {}

    lat = params.get("lat")
    lng = params.get("lng")
    radius_km = params.get("radius_km", 25)

    if lat is None or lng is None:
        return {"error": "CCTV discovery requires lat and lng in description JSON"}

    cctv = CCTVDiscoveryTool()
    result = await cctv.run(
        target=state["target"] or "cctv_search",
        lat=lat,
        lng=lng,
        radius_km=radius_km,
    )

    logger.info("cctv_discover.complete", cameras=result.get("data", {}).get("cameras_found", 0))
    return {
        "tool_results": [{"tool": "cctv_discovery", "data": result}],
        "messages": [
            AIMessage(
                content=f"CCTV discovery complete: "
                f"{result.get('data', {}).get('cameras_found', 0)} cameras found"
            )
        ],
    }


# ---------------------------------------------------------------------------
# Wayback search
# ---------------------------------------------------------------------------


async def wayback_search_node(state: AgentState) -> dict[str, Any]:
    """Search the Wayback Machine for archived snapshots."""
    from src.tools.wayback_tool import wayback_tool

    target = state["target"]
    result = await wayback_tool(url=target)

    logger.info("wayback_search.complete", total=result.get("total", 0))
    return {
        "tool_results": [{"tool": "wayback", "data": result}],
        "messages": [
            AIMessage(content=f"Wayback search found {result.get('total', 0)} snapshots")
        ],
    }


# ---------------------------------------------------------------------------
# Store results in Neo4j
# ---------------------------------------------------------------------------


async def store_node(state: AgentState) -> dict[str, Any]:
    """Persist tool results into the Neo4j knowledge graph."""
    from src.db.neo4j_client import neo4j_client

    target = state["target"]
    tool_results = state.get("tool_results", [])

    # Ensure the target node exists
    await neo4j_client.merge_node("Target", {"domain": target})

    for result in tool_results:
        tool_name = result.get("tool", "")
        data = result.get("data", {})
        # ScopedTool wraps in {"success": ..., "data": ...}
        if "data" in data and "success" in data:
            data = data.get("data", {})

        try:
            if tool_name == "theharvester":
                for email in data.get("emails", []):
                    await neo4j_client.merge_node(
                        "Email", {"address": email}, {"source": "theharvester"},
                    )
                    await neo4j_client.create_relationship(
                        "Target", {"domain": target},
                        "Email", {"address": email},
                        "HAS_EMAIL",
                    )
                for host in data.get("hosts", []):
                    await neo4j_client.merge_node(
                        "Subdomain", {"name": host}, {"source": "theharvester"},
                    )
                    await neo4j_client.create_relationship(
                        "Target", {"domain": target},
                        "Subdomain", {"name": host},
                        "HAS_SUBDOMAIN",
                    )

            elif tool_name in ("nmap", "shodan"):
                for port_info in data.get("ports", []):
                    port_num = port_info if isinstance(port_info, int) else port_info.get("port", 0)
                    proto = port_info.get("protocol", "tcp") if isinstance(port_info, dict) else "tcp"
                    uid = f"{target}:{port_num}/{proto}"
                    svc = port_info.get("service", "") if isinstance(port_info, dict) else ""
                    ver = port_info.get("version", "") if isinstance(port_info, dict) else ""
                    await neo4j_client.merge_node(
                        "Port",
                        {"number": port_num, "protocol": proto},
                        {"service": svc, "version": ver, "uid": uid},
                    )
                    await neo4j_client.create_relationship(
                        "Target", {"domain": target},
                        "Port", {"number": port_num, "protocol": proto},
                        "HAS_PORT",
                    )

            elif tool_name == "cctv_discovery":
                # Cameras are stored by CCTVDiscoveryTool._store_camera
                pass

            elif tool_name == "wayback":
                for snap in data.get("snapshots", [])[:20]:
                    await neo4j_client.merge_node(
                        "WebPage",
                        {"url": snap.get("archive_url", "")},
                        {"snapshot_ts": snap.get("timestamp", ""), "status_code": snap.get("status_code", "")},
                    )
                    await neo4j_client.create_relationship(
                        "Target", {"domain": target},
                        "WebPage", {"url": snap.get("archive_url", "")},
                        "ARCHIVED_AS",
                    )

        except Exception as exc:
            logger.warning("store.failed", tool=tool_name, error=str(exc))

    logger.info("store.complete", target=target, results_count=len(tool_results))
    return {"messages": [AIMessage(content="Results stored in Neo4j knowledge graph")]}


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


async def report_node(state: AgentState) -> dict[str, Any]:
    """Use model_router to generate a dossier via LLM."""
    from src.llm.router import model_router

    model = model_router.route("summarize report dossier", is_sensitive=True)

    tool_summaries = []
    for r in state.get("tool_results", []):
        data = r.get("data", {})
        if "data" in data and "success" in data:
            data = data.get("data", {})
        tool_name = r.get("tool", "unknown")
        summary = f"Tool: {tool_name}"
        if tool_name == "theharvester":
            summary += (
                f", Emails found: {len(data.get('emails', []))}"
                f", Hosts found: {len(data.get('hosts', []))}"
                f", IPs found: {len(data.get('ips', []))}"
            )
        elif tool_name in ("nmap", "shodan"):
            summary += f", Ports found: {len(data.get('ports', []))}"
        elif tool_name == "cctv_discovery":
            summary += f", Cameras found: {data.get('cameras_found', 0)}"
        elif tool_name == "wayback":
            summary += f", Snapshots found: {data.get('total', 0)}"
        elif tool_name == "web_scraper":
            summary += f", Pages scraped: {data.get('pages_scraped', 0)}"
        tool_summaries.append(summary)

    prompt = f"""Generate a comprehensive intelligence dossier for target: {state['target']}

Task type: {state['task_type']}

Tool results:
{chr(10).join(tool_summaries)}

Structure the report with these sections:
1. Executive Summary
2. Target Overview
3. Network Infrastructure
4. Digital Footprint
5. Vulnerabilities
6. Associated Entities
7. Timeline
8. Risk Assessment
9. Recommendations
"""

    response = await model.ainvoke([HumanMessage(content=prompt)])
    report_content = response.content if hasattr(response, "content") else str(response)

    logger.info("report.generated", target=state["target"], length=len(report_content))
    return {
        "report": report_content,
        "messages": [AIMessage(content="Intelligence dossier generated")],
    }


# ---------------------------------------------------------------------------
# Notify
# ---------------------------------------------------------------------------


async def notify_node(state: AgentState) -> dict[str, Any]:
    """Log task completion and set the completed flag."""
    logger.info(
        "task.complete",
        task_id=state.get("task_id"),
        target=state["target"],
        task_type=state["task_type"],
        has_report=bool(state.get("report")),
        has_error=bool(state.get("error")),
    )
    return {"completed": True}
