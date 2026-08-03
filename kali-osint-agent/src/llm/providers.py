"""LLM provider factories for local (vLLM) and remote (OpenRouter) models."""

from __future__ import annotations

import structlog
from langchain_openai import ChatOpenAI

from configs.settings import settings
from src.llm.config import MODEL_REGISTRY, ModelConfig

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Generic factory
# ---------------------------------------------------------------------------


def create_chat_model(config: ModelConfig, **kwargs) -> ChatOpenAI:
    """Instantiate the appropriate ``ChatOpenAI`` wrapper for *config*.

    Local models are served by a vLLM-compatible OpenAI endpoint; remote
    models go through OpenRouter.
    """

    from src.llm.config import ModelTier

    if config.tier == ModelTier.LOCAL:
        return _create_vllm_model(config, **kwargs)
    return _create_openrouter_model(config, **kwargs)


# ---------------------------------------------------------------------------
# vLLM (local)
# ---------------------------------------------------------------------------


def _create_vllm_model(config: ModelConfig, **kwargs) -> ChatOpenAI:
    """Return a ``ChatOpenAI`` pointed at the local vLLM server."""

    logger.info("providers.create_vllm", model=config.model_id)
    return ChatOpenAI(
        model=config.model_id,
        openai_api_base=settings.vllm_base_url,
        openai_api_key=settings.vllm_api_key,
        max_tokens=config.max_tokens,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# OpenRouter (remote)
# ---------------------------------------------------------------------------


def _create_openrouter_model(config: ModelConfig, **kwargs) -> ChatOpenAI:
    """Return a ``ChatOpenAI`` routed through OpenRouter."""

    logger.info("providers.create_openrouter", model=config.model_id)
    return ChatOpenAI(
        model=config.model_id,
        openai_api_base=settings.openrouter_base_url,
        openai_api_key=settings.openrouter_api_key,
        max_tokens=config.max_tokens,
        default_headers={
            "HTTP-Referer": "https://kali-osint-agent.local",
            "X-Title": "Kali OSINT Agent",
        },
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Convenience accessors
# ---------------------------------------------------------------------------


def get_local_model(**kwargs) -> ChatOpenAI:
    """Return the default local model (``nemotron-mini-local``)."""

    config = MODEL_REGISTRY["nemotron-mini-local"]
    return create_chat_model(config, **kwargs)


def get_osint_model(**kwargs) -> ChatOpenAI:
    """Return the fine-tuned OSINT model if available, otherwise fall
    back to ``nemotron-mini-local``."""

    config = MODEL_REGISTRY.get("nemotron-osint-local")
    if config is None:
        logger.warning("providers.osint_model_missing, falling back to nemotron-mini-local")
        config = MODEL_REGISTRY["nemotron-mini-local"]
    return create_chat_model(config, **kwargs)


def get_remote_model(model_key: str, **kwargs) -> ChatOpenAI:
    """Return a remote model by its registry key (e.g.
    ``"nemotron-super"``, ``"claude-sonnet"``)."""

    config = MODEL_REGISTRY[model_key]
    return create_chat_model(config, **kwargs)
