"""Tests for ModelRouter: task classification, sensitive data routing, model selection."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from src.llm.config import ModelTier, TaskType
from src.llm.router import ModelRouter


@pytest.fixture
def router():
    """Create a ModelRouter instance for testing."""
    return ModelRouter()


# ---------------------------------------------------------------------------
# Task classification
# ---------------------------------------------------------------------------


class TestTaskClassification:
    def test_reasoning_keywords(self, router):
        assert router._classify_task("plan a strategy for recon") == TaskType.REASONING

    def test_coding_keywords(self, router):
        assert router._classify_task("generate exploit code") == TaskType.CODING

    def test_analysis_keywords(self, router):
        assert router._classify_task("analyze the network data") == TaskType.ANALYSIS

    def test_summarization_keywords(self, router):
        assert router._classify_task("summarize the report") == TaskType.SUMMARIZATION

    def test_general_fallback(self, router):
        """Prompts with no recognised keywords should classify as GENERAL."""
        assert router._classify_task("do something random") == TaskType.GENERAL

    def test_vision_keywords(self, router):
        assert router._classify_task("analyze this screenshot") == TaskType.VISION


# ---------------------------------------------------------------------------
# Sensitive data routing
# ---------------------------------------------------------------------------


class TestSensitiveDataRouting:
    def test_sensitive_keywords_detected(self, router):
        assert router._contains_sensitive("contains password and credentials") is True

    def test_api_key_detected(self, router):
        assert router._contains_sensitive("store the api key securely") is True

    def test_not_sensitive(self, router):
        assert router._contains_sensitive("scan the target domain") is False

    @patch("src.llm.router.get_local_model")
    def test_sensitive_routes_to_local(self, mock_local, router):
        """Sensitive data must always route to a local model."""
        mock_model = MagicMock()
        mock_local.return_value = mock_model

        result = router.route("store these credentials safely", is_sensitive=True)
        mock_local.assert_called_once()
        assert result is mock_model


# ---------------------------------------------------------------------------
# Simple tasks route to local
# ---------------------------------------------------------------------------


class TestSimpleTaskRouting:
    @patch("src.llm.router.get_local_model")
    def test_simple_task_routes_to_local(self, mock_local, router):
        """Simple/short tasks should use the local model."""
        mock_model = MagicMock()
        mock_local.return_value = mock_model

        result = router.route("list the targets")
        mock_local.assert_called()
        assert result is mock_model


# ---------------------------------------------------------------------------
# Complex reasoning routes to remote
# ---------------------------------------------------------------------------


class TestComplexTaskRouting:
    def test_complex_reasoning_selects_remote(self, router):
        """Complex reasoning tasks should pick a remote model."""
        model = router._select_best_model(TaskType.REASONING)
        assert model is not None
        assert model.tier == ModelTier.REMOTE

    def test_cheapest_remote_selected(self, router):
        """The cheapest remote model supporting the task type should be chosen."""
        model = router._select_best_model(TaskType.CODING)
        assert model is not None
        assert model.tier == ModelTier.REMOTE
        # Verify it picked the cheapest option
        from src.llm.config import MODEL_REGISTRY
        remote_coding = [
            cfg for cfg in MODEL_REGISTRY.values()
            if cfg.tier == ModelTier.REMOTE and TaskType.CODING in cfg.task_types
        ]
        cheapest = min(remote_coding, key=lambda c: c.cost_per_1k_tokens)
        assert model.cost_per_1k_tokens == cheapest.cost_per_1k_tokens


# ---------------------------------------------------------------------------
# Fallback always includes local model
# ---------------------------------------------------------------------------


class TestFallback:
    @patch("src.llm.router.get_local_model")
    def test_fallback_always_includes_local(self, mock_local, router):
        """route_with_fallback must always return a local model as fallback."""
        mock_model = MagicMock()
        mock_local.return_value = mock_model

        _primary, fallback = router.route_with_fallback("complex reasoning task")
        assert fallback is mock_model
