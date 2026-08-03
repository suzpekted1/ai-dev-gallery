"""LLM model registry, task classification, and routing configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TaskType(str, Enum):
    """Categories of work that can be dispatched to an LLM."""

    REASONING = "reasoning"
    CODING = "coding"
    ANALYSIS = "analysis"
    SUMMARIZATION = "summarization"
    VISION = "vision"
    EMBEDDING = "embedding"
    GENERAL = "general"


class ModelTier(str, Enum):
    """Where the model runs."""

    LOCAL = "local"
    REMOTE = "remote"


@dataclass(frozen=True)
class ModelConfig:
    """Describes a single LLM endpoint available to the agent."""

    model_id: str
    tier: ModelTier
    task_types: list[TaskType] = field(default_factory=list)
    max_tokens: int = 4096
    cost_per_1k_tokens: float = 0.0
    supports_vision: bool = False
    supports_tools: bool = False


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

MODEL_REGISTRY: dict[str, ModelConfig] = {
    "nemotron-mini-local": ModelConfig(
        model_id="nvidia/Nemotron-Mini-4B-Instruct",
        tier=ModelTier.LOCAL,
        task_types=[TaskType.SUMMARIZATION, TaskType.ANALYSIS, TaskType.GENERAL],
        max_tokens=4096,
        cost_per_1k_tokens=0.0,
    ),
    "nemotron-osint-local": ModelConfig(
        model_id="nvidia/Nemotron-Mini-4B-OSINT",
        tier=ModelTier.LOCAL,
        task_types=[
            TaskType.SUMMARIZATION,
            TaskType.ANALYSIS,
            TaskType.GENERAL,
            TaskType.CODING,
        ],
        max_tokens=4096,
        cost_per_1k_tokens=0.0,
    ),
    "nemotron-super": ModelConfig(
        model_id="nvidia/nemotron-super",
        tier=ModelTier.REMOTE,
        task_types=[
            TaskType.REASONING,
            TaskType.CODING,
            TaskType.ANALYSIS,
            TaskType.GENERAL,
        ],
        max_tokens=8192,
        cost_per_1k_tokens=0.20,
    ),
    "deepseek-r1": ModelConfig(
        model_id="deepseek/deepseek-r1",
        tier=ModelTier.REMOTE,
        task_types=[TaskType.REASONING],
        max_tokens=8192,
        cost_per_1k_tokens=0.55,
    ),
    "deepseek-coder": ModelConfig(
        model_id="deepseek/deepseek-coder",
        tier=ModelTier.REMOTE,
        task_types=[TaskType.CODING],
        max_tokens=8192,
        cost_per_1k_tokens=0.14,
    ),
    "claude-sonnet": ModelConfig(
        model_id="anthropic/claude-sonnet-4-20250514",
        tier=ModelTier.REMOTE,
        task_types=[
            TaskType.REASONING,
            TaskType.CODING,
            TaskType.ANALYSIS,
            TaskType.SUMMARIZATION,
            TaskType.VISION,
            TaskType.GENERAL,
        ],
        max_tokens=8192,
        cost_per_1k_tokens=3.00,
        supports_vision=True,
        supports_tools=True,
    ),
}

# ---------------------------------------------------------------------------
# Keyword -> TaskType mapping used by the router
# ---------------------------------------------------------------------------

TASK_TYPE_KEYWORDS: dict[str, TaskType] = {
    # Reasoning
    "reason": TaskType.REASONING,
    "think": TaskType.REASONING,
    "deduce": TaskType.REASONING,
    "infer": TaskType.REASONING,
    "logic": TaskType.REASONING,
    "plan": TaskType.REASONING,
    "strategy": TaskType.REASONING,
    # Coding
    "code": TaskType.CODING,
    "script": TaskType.CODING,
    "program": TaskType.CODING,
    "function": TaskType.CODING,
    "debug": TaskType.CODING,
    "implement": TaskType.CODING,
    "regex": TaskType.CODING,
    "parse": TaskType.CODING,
    # Analysis
    "analyze": TaskType.ANALYSIS,
    "analyse": TaskType.ANALYSIS,
    "investigate": TaskType.ANALYSIS,
    "examine": TaskType.ANALYSIS,
    "correlate": TaskType.ANALYSIS,
    "compare": TaskType.ANALYSIS,
    "assess": TaskType.ANALYSIS,
    # Summarization
    "summarize": TaskType.SUMMARIZATION,
    "summarise": TaskType.SUMMARIZATION,
    "summary": TaskType.SUMMARIZATION,
    "tldr": TaskType.SUMMARIZATION,
    "brief": TaskType.SUMMARIZATION,
    "digest": TaskType.SUMMARIZATION,
    # Vision
    "image": TaskType.VISION,
    "screenshot": TaskType.VISION,
    "photo": TaskType.VISION,
    "picture": TaskType.VISION,
    "ocr": TaskType.VISION,
    # General
    "help": TaskType.GENERAL,
    "explain": TaskType.GENERAL,
    "describe": TaskType.GENERAL,
    "list": TaskType.GENERAL,
    "what": TaskType.GENERAL,
}
