"""Unit tests for src/classify.py — Claude classification (mocked)."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.classify import _build_prompt, _failed_record, classify_posts
from src.models import BrandTaggedPost, PostClassification

MOCK_RESPONSE = json.dumps({
    "brand": "T-Mobile US",
    "sentiment": "Negative",
    "intent": "Complaint",
    "emotion": "Frustration",
    "pillar": "Network Performance",
    "category": "Coverage",
    "theme": "Urban Coverage",
    "topic": "Signal loss in subway",
    "confidence": "High",
})


def _make_tagged(post_id: str = "test_001") -> BrandTaggedPost:
    return BrandTaggedPost(
        post_id=post_id,
        platform="Reddit",
        timestamp=datetime.now(timezone.utc),
        normalized_text="t-mobile signal dropped again on the subway",
        brands=["T-Mobile US"],
        brand_confidence="High",
        is_multi_brand=False,
    )


class TestBuildPrompt:
    def test_prompt_contains_post_text(self):
        post = _make_tagged()
        prompt = _build_prompt(post)
        assert post.normalized_text in prompt

    def test_prompt_contains_brand(self):
        post = _make_tagged()
        prompt = _build_prompt(post)
        assert "T-Mobile US" in prompt

    def test_prompt_contains_taxonomy(self):
        post = _make_tagged()
        prompt = _build_prompt(post)
        assert "Network Performance" in prompt
        assert "Competitive Switching" in prompt


class TestFailedRecord:
    def test_failed_record_has_correct_status(self):
        post = _make_tagged()
        record = _failed_record(post, "run_001")
        assert record.classification_status == "failed"
        assert record.pillar == "Uncategorized"

    def test_failed_record_preserves_post_id(self):
        post = _make_tagged("unique_001")
        record = _failed_record(post, "run_001")
        assert record.post_id == "unique_001"


class TestClassifyPosts:
    def _make_mock_response(self, text: str) -> MagicMock:
        block = MagicMock()
        block.text = text
        response = MagicMock()
        response.content = [block]
        return response

    @patch("src.classify.anthropic.AsyncAnthropic")
    def test_classify_returns_valid_record(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.messages.create = AsyncMock(
            return_value=self._make_mock_response(MOCK_RESPONSE)
        )

        posts = [_make_tagged()]
        results = classify_posts(posts, "run_001")

        assert len(results) == 1
        assert isinstance(results[0], PostClassification)
        assert results[0].sentiment == "Negative"
        assert results[0].intent == "Complaint"

    @patch("src.classify.anthropic.AsyncAnthropic")
    def test_classify_handles_malformed_json(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.messages.create = AsyncMock(
            return_value=self._make_mock_response("this is not json {broken}")
        )

        posts = [_make_tagged()]
        results = classify_posts(posts, "run_001")

        assert len(results) == 1
        assert results[0].classification_status == "failed"

    @patch("src.classify.anthropic.AsyncAnthropic")
    def test_low_confidence_sets_flagged_status(self, mock_client_cls):
        low_conf_response = json.dumps({
            **json.loads(MOCK_RESPONSE),
            "confidence": "Low",
        })
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.messages.create = AsyncMock(
            return_value=self._make_mock_response(low_conf_response)
        )

        posts = [_make_tagged()]
        results = classify_posts(posts, "run_001")

        assert results[0].confidence == "Low"
        assert results[0].classification_status == "flagged"

    @patch("src.classify.anthropic.AsyncAnthropic")
    def test_multiple_posts_classified(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.messages.create = AsyncMock(
            return_value=self._make_mock_response(MOCK_RESPONSE)
        )

        posts = [_make_tagged(f"p{i:03d}") for i in range(5)]
        results = classify_posts(posts, "run_001")

        assert len(results) == 5
