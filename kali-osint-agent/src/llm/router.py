"""Intelligent model router that picks the best LLM for each task."""

from __future__ import annotations

import structlog
from langchain_openai import ChatOpenAI

from configs.settings import settings
from src.llm.config import (
    MODEL_REGISTRY,
    TASK_TYPE_KEYWORDS,
    ModelConfig,
    ModelTier,
    TaskType,
)
from src.llm.providers import create_chat_model, get_local_model

logger = structlog.get_logger(__name__)

# Keywords that flag a prompt as containing sensitive/private data and
# must therefore be handled exclusively by a local model.
_SENSITIVE_KEYWORDS: list[str] = [
    "password",
    "credential",
    "secret",
    "token",
    "ssn",
    "social security",
    "classified",
    "private key",
    "api key",
    "confidential",
]


class ModelRouter:
    """Decide which LLM handles a given prompt based on sensitivity,
    task type, and estimated complexity."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(
        self,
        prompt: str,
        *,
        is_sensitive: bool = False,
        estimated_tokens: int = 0,
    ) -> ChatOpenAI:
        """Return the single best model for *prompt*.

        Parameters
        ----------
        prompt:
            The user / agent prompt text.
        is_sensitive:
            Explicitly flag the request as containing sensitive data.
        estimated_tokens:
            Rough token count of the expected *output*.  Used as a
            complexity signal.
        """

        # Sensitive content never leaves the local machine.
        if is_sensitive or self._contains_sensitive(prompt):
            logger.info("router.sensitive_route", reason="sensitive content detected")
            return get_local_model()

        task_type = self._classify_task(prompt)

        # Simple / short tasks -> local model.
        is_complex = task_type in {TaskType.REASONING, TaskType.CODING} or estimated_tokens > 2000
        if not is_complex:
            logger.info("router.local_route", task_type=task_type.value)
            return get_local_model()

        # Complex tasks -> cheapest remote model that supports the task.
        best = self._select_best_model(task_type)
        if best is not None:
            logger.info(
                "router.remote_route",
                task_type=task_type.value,
                model=best.model_id,
            )
            return create_chat_model(best)

        # No suitable remote model found -- fall back to local.
        logger.warning("router.fallback_local", task_type=task_type.value)
        return get_local_model()

    def route_with_fallback(
        self,
        prompt: str,
        *,
        is_sensitive: bool = False,
        estimated_tokens: int = 0,
    ) -> tuple[ChatOpenAI, ChatOpenAI]:
        """Return ``(primary, fallback)`` where *fallback* is always a
        local model.  Callers should try *primary* first and switch to
        *fallback* on failure."""

        primary = self.route(
            prompt,
            is_sensitive=is_sensitive,
            estimated_tokens=estimated_tokens,
        )
        fallback = get_local_model()
        return primary, fallback

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _contains_sensitive(prompt: str) -> bool:
        lower = prompt.lower()
        return any(kw in lower for kw in _SENSITIVE_KEYWORDS)

    @staticmethod
    def _classify_task(prompt: str) -> TaskType:
        """Map *prompt* to a :class:`TaskType` via keyword matching."""

        lower = prompt.lower()
        for keyword, task_type in TASK_TYPE_KEYWORDS.items():
            if keyword in lower:
                return task_type
        return TaskType.GENERAL

    @staticmethod
    def _select_best_model(task_type: TaskType) -> ModelConfig | None:
        """Pick the cheapest remote model that supports *task_type*."""

        candidates = [
            cfg
            for cfg in MODEL_REGISTRY.values()
            if cfg.tier == ModelTier.REMOTE and task_type in cfg.task_types
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda c: c.cost_per_1k_tokens)


model_router = ModelRouter()
