from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from src.llm.config import TaskType, ModelTier
from src.llm.router import ModelRouter


@pytest.fixture
def router():
    return ModelRouter()


class TestTaskClassification:
    def test_reasoning_keywords(self, router):
        assert router._classify_task("plan a strategy for recon") == TaskType.REASONING

    def test_coding_keywords(self, router):
        assert router._classify_task("generate exploit code") == TaskType.CODING

    def test_summarization_keywords(self, router):
        assert router._classify_task("summarize the report") == TaskType.SUMMARIZATION

    def test_general_fallback(self, router):
        assert router._classify_task("do something") == TaskType.GENERAL


class TestSensitiveRouting:
    def test_sensitive_keywords(self, router):
        assert router._contains_sensitive_data("contains password and credentials")

    def test_not_sensitive(self, router):
        assert not router._contains_sensitive_data("scan the target")


class TestModelSelection:
    def test_cheapest_remote(self, router):
        model = router._select_best_model(TaskType.REASONING)
        assert model.tier == ModelTier.REMOTE

    def test_fallback_always_local(self, router):
        with patch("src.llm.router.get_local_model") as mock_local:
            mock_local.return_value = MagicMock()
            _, fallback = router.route_with_fallback("test task")
            mock_local.assert_called()
