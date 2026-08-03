"""LangGraph state graph construction and agent instantiation."""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from src.agent.edges import check_approval, route_by_task_type
from src.agent.hitl import hitl_approve_node
from src.agent.nodes import (
    cctv_discover_node,
    classify_node,
    intake_node,
    notify_node,
    opsec_setup_node,
    osint_gather_node,
    pentest_execute_node,
    recon_scan_node,
    report_node,
    store_node,
    wayback_search_node,
)
from src.agent.state import AgentState


def build_agent_graph() -> StateGraph:
    """Construct the full agent StateGraph with all nodes and edges.

    Flow::

        intake -> classify -> opsec_setup -> [conditional by task_type]
            osint_gather  -> store
            recon_scan    -> hitl_approve -> [conditional by approval]
                                approved  -> pentest_execute -> store
                                denied    -> notify -> END
            cctv_discover -> store
            wayback_search -> store
            report        -> notify -> END
        store -> report -> notify -> END
    """
    graph = StateGraph(AgentState)

    # Register all nodes
    graph.add_node("intake", intake_node)
    graph.add_node("classify", classify_node)
    graph.add_node("opsec_setup", opsec_setup_node)
    graph.add_node("osint_gather", osint_gather_node)
    graph.add_node("recon_scan", recon_scan_node)
    graph.add_node("hitl_approve", hitl_approve_node)
    graph.add_node("pentest_execute", pentest_execute_node)
    graph.add_node("cctv_discover", cctv_discover_node)
    graph.add_node("wayback_search", wayback_search_node)
    graph.add_node("store", store_node)
    graph.add_node("report", report_node)
    graph.add_node("notify", notify_node)

    # Linear edges: intake -> classify -> opsec_setup
    graph.set_entry_point("intake")
    graph.add_edge("intake", "classify")
    graph.add_edge("classify", "opsec_setup")

    # Conditional routing by task type
    graph.add_conditional_edges("opsec_setup", route_by_task_type)

    # Task-type-specific flows into store
    graph.add_edge("osint_gather", "store")
    graph.add_edge("cctv_discover", "store")
    graph.add_edge("wayback_search", "store")

    # Recon / pentest flow through approval
    graph.add_edge("recon_scan", "hitl_approve")
    graph.add_conditional_edges("hitl_approve", check_approval)
    graph.add_edge("pentest_execute", "store")

    # Store -> report -> notify -> END
    graph.add_edge("store", "report")
    graph.add_edge("report", "notify")
    graph.add_edge("notify", END)

    return graph


def create_agent():
    """Compile the agent graph with a MemorySaver checkpointer."""
    graph = build_agent_graph()
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


# Module-level singleton
agent = create_agent()
