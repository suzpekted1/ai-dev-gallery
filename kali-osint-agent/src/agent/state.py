"""LangGraph agent state definition."""

from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import MessagesState
from pydantic import Field


class AgentState(MessagesState):
    """Extended state for the OSINT agent graph.

    Inherits the ``messages`` list from :class:`MessagesState` and adds
    fields for tracking task metadata, approval workflows, tool outputs,
    and the final report.
    """

    # ── Task metadata ────────────────────────────────────────────────────
    task_id: int = Field(default=0, description="Database Task row ID.")
    task_type: Literal[
        "osint", "recon", "pentest", "cctv", "wayback", "report", "analysis"
    ] = Field(default="osint", description="Classification of the current task.")
    target: str = Field(default="", description="Primary target (domain, IP, URL, etc.).")
    description: str = Field(default="", description="Free-text task description.")

    # ── OPSEC ────────────────────────────────────────────────────────────
    proxy_mode: str = Field(default="stealth", description="Active proxy mode for this run.")

    # ── Human-in-the-loop approval ───────────────────────────────────────
    requires_approval: bool = Field(
        default=False,
        description="Whether the current task requires human approval before execution.",
    )
    approval_status: Literal[
        "pending", "approved", "denied", "not_needed"
    ] = Field(default="not_needed", description="Current approval decision.")
    approval_id: int | None = Field(
        default=None, description="Database Approval row ID when awaiting decision.",
    )
    pending_action: dict[str, Any] | None = Field(
        default=None,
        description="Tool invocation details awaiting approval (tool name, args, etc.).",
    )

    # ── Results ──────────────────────────────────────────────────────────
    tool_results: list[dict[str, Any]] = Field(
        default_factory=list, description="Accumulated outputs from executed tools.",
    )
    parsed_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured data extracted from tool results (emails, subdomains, etc.).",
    )
    report: str = Field(default="", description="Final generated dossier / report content.")

    # ── Control flow ─────────────────────────────────────────────────────
    error: str | None = Field(default=None, description="Error message if the run failed.")
    completed: bool = Field(default=False, description="True once the graph has finished.")
