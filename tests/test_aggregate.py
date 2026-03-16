"""Unit tests for src/aggregate.py — metrics computation."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.aggregate import (
    competitive_gap,
    compute_brand_metrics,
    compute_daily_trends,
    compute_top_topics,
)
from src.models import AggregatedMetrics, PostClassification


def _make_record(
    post_id: str,
    brand: str = "T-Mobile US",
    sentiment: str = "Negative",
    intent: str = "Complaint",
    emotion: str = "Frustration",
    pillar: str = "Network Performance",
    category: str = "Coverage",
    theme: str = "Urban Coverage",
    topic: str = "Signal loss in subway",
    confidence: str = "High",
    platform: str = "Reddit",
    classification_status: str = "success",
) -> PostClassification:
    return PostClassification(
        post_id=post_id,
        platform=platform,
        timestamp=datetime.now(timezone.utc),
        normalized_text="test post text for aggregation purposes",
        brands=[brand],
        brand_confidence="High",
        is_multi_brand=False,
        pillar=pillar,
        category=category,
        theme=theme,
        topic=topic,
        sentiment=sentiment,
        intent=intent,
        emotion=emotion,
        confidence=confidence,
        classification_status=classification_status,
        taxonomy_version="v1.0.0",
        schema_version="v1.0.0",
        pipeline_run_id="run_test",
    )


def _make_sample_records() -> list[PostClassification]:
    records = []
    # 6 T-Mobile posts: 2 Positive, 4 Negative; 4 Complaint, 2 Praise
    for i in range(2):
        records.append(_make_record(f"tm_pos_{i}", "T-Mobile US", "Positive", "Praise", "Satisfaction"))
    for i in range(4):
        records.append(_make_record(f"tm_neg_{i}", "T-Mobile US", "Negative", "Complaint", "Frustration"))
    # 4 Verizon posts: all Positive
    for i in range(4):
        records.append(_make_record(f"vz_{i}", "Verizon", "Positive", "Praise", "Satisfaction"))
    return records


class TestComputeBrandMetrics:
    def test_returns_metrics_for_each_brand(self):
        records = _make_sample_records()
        now = datetime.now(timezone.utc)
        metrics = compute_brand_metrics(records, "run_001", now, now)
        brands = {m.brand for m in metrics}
        assert "T-Mobile US" in brands
        assert "Verizon" in brands

    def test_nss_calculation(self):
        records = _make_sample_records()
        now = datetime.now(timezone.utc)
        metrics = compute_brand_metrics(records, "run_001", now, now)
        tmobile = next(m for m in metrics if m.brand == "T-Mobile US")
        # 2 Positive / 6 = 33.3%, 4 Negative / 6 = 66.7% → NSS ≈ -33.3
        assert tmobile.net_sentiment_score < 0
        verizon = next(m for m in metrics if m.brand == "Verizon")
        # 4 Positive / 4 = 100%, 0 Negative → NSS = 100
        assert verizon.net_sentiment_score == 100.0

    def test_complaint_pct(self):
        records = _make_sample_records()
        now = datetime.now(timezone.utc)
        metrics = compute_brand_metrics(records, "run_001", now, now)
        tmobile = next(m for m in metrics if m.brand == "T-Mobile US")
        # 4 Complaint / 6 total T-Mobile = 66.67%
        assert abs(tmobile.complaint_pct - 66.67) < 0.5

    def test_excludes_failed_records(self):
        records = _make_sample_records()
        # Add a failed record — should not count
        failed = _make_record("failed_001", "T-Mobile US", classification_status="failed")
        now = datetime.now(timezone.utc)
        metrics_with = compute_brand_metrics(records + [failed], "run_001", now, now)
        metrics_without = compute_brand_metrics(records, "run_001", now, now)
        tm_with = next(m for m in metrics_with if m.brand == "T-Mobile US")
        tm_without = next(m for m in metrics_without if m.brand == "T-Mobile US")
        assert tm_with.total_posts == tm_without.total_posts


class TestCompetitiveGap:
    def test_positive_gap_when_tmobile_leads(self):
        metrics = [
            AggregatedMetrics(
                pipeline_run_id="r", taxonomy_version="v1", schema_version="v1",
                period_start=datetime.now(timezone.utc), period_end=datetime.now(timezone.utc),
                brand="T-Mobile US", total_posts=100,
                conversation_share_pct=40.0,
                positive_pct=60.0, neutral_pct=20.0, negative_pct=20.0,
                net_sentiment_score=40.0,
                complaint_pct=15.0, inquiry_pct=20.0, praise_pct=45.0, recommendation_pct=20.0,
                complaint_to_praise_ratio=0.33,
                frustration_pct=15.0, satisfaction_pct=55.0, confusion_pct=20.0, excitement_pct=10.0,
            ),
            AggregatedMetrics(
                pipeline_run_id="r", taxonomy_version="v1", schema_version="v1",
                period_start=datetime.now(timezone.utc), period_end=datetime.now(timezone.utc),
                brand="Verizon", total_posts=80,
                conversation_share_pct=35.0,
                positive_pct=40.0, neutral_pct=30.0, negative_pct=30.0,
                net_sentiment_score=10.0,
                complaint_pct=30.0, inquiry_pct=20.0, praise_pct=30.0, recommendation_pct=20.0,
                complaint_to_praise_ratio=1.0,
                frustration_pct=30.0, satisfaction_pct=30.0, confusion_pct=25.0, excitement_pct=15.0,
            ),
        ]
        gap = competitive_gap(metrics)
        assert gap["Verizon"]["nss_gap"] == 30.0   # 40 - 10
        assert gap["Verizon"]["complaint_rate_gap"] == -15.0  # 15 - 30

    def test_returns_empty_when_no_tmobile(self):
        metrics = [
            AggregatedMetrics(
                pipeline_run_id="r", taxonomy_version="v1", schema_version="v1",
                period_start=datetime.now(timezone.utc), period_end=datetime.now(timezone.utc),
                brand="Verizon", total_posts=80,
                conversation_share_pct=35.0,
                positive_pct=40.0, neutral_pct=30.0, negative_pct=30.0,
                net_sentiment_score=10.0,
                complaint_pct=30.0, inquiry_pct=20.0, praise_pct=30.0, recommendation_pct=20.0,
                complaint_to_praise_ratio=1.0,
                frustration_pct=30.0, satisfaction_pct=30.0, confusion_pct=25.0, excitement_pct=15.0,
            ),
        ]
        assert competitive_gap(metrics) == {}


class TestComputeTopTopics:
    def test_top_topics_ranked(self):
        records = []
        for i in range(5):
            records.append(_make_record(f"t{i}", topic="Signal loss in subway"))
        for i in range(3):
            records.append(_make_record(f"b{i}", topic="Slow LTE"))
        df = compute_top_topics(records, "run_001")
        if not df.empty:
            tm_df = df[df["brand"] == "T-Mobile US"].sort_values("rank")
            assert tm_df.iloc[0]["topic"] == "Signal loss in subway"

    def test_empty_records_returns_empty_df(self):
        df = compute_top_topics([], "run_001")
        assert df.empty
