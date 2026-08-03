"""Resilient LLM invocation with automatic local-model fallback."""

from __future__ import annotations

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI

import structlog

from src.llm.providers import get_local_model

logger = structlog.get_logger(__name__)


async def invoke_with_fallback(
    primary: ChatOpenAI,
    fallback: ChatOpenAI,
    messages: list[BaseMessage],
) -> BaseMessage:
    """Try *primary*; on any exception fall back to *fallback*.

    Both models are called with the same *messages* list.  The fallback
    is typically a local model so that the agent can always make progress
    even when remote endpoints are unreachable or rate-limited.
    """

    try:
        response = await primary.ainvoke(messages)
        logger.debug("fallback.primary_ok", model=primary.model_name)
        return response
    except Exception:
        logger.warning(
            "fallback.primary_failed",
            model=primary.model_name,
            exc_info=True,
        )
        response = await fallback.ainvoke(messages)
        logger.info("fallback.fallback_ok", model=fallback.model_name)
        return response


async def invoke_sovereign(messages: list[BaseMessage]) -> BaseMessage:
    """Always use the local model -- no data leaves the machine.

    This is the "sovereign AI" path: the prompt and response stay
    entirely on-premise regardless of complexity.
    """

    model = get_local_model()
    response = await model.ainvoke(messages)
    logger.info("fallback.sovereign_ok", model=model.model_name)
    return response
