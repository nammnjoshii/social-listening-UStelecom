"""Aggregation & trend computation — pandas layer.

Implements all metrics from PANDAS-DATA-PIPELINE.md and WORKFLOW.md §Step 7–8:
  - Conversation share
  - Net Sentiment Score (NSS)
  - Intent & emotion distributions
  - Complaint-to-Praise ratio
  - 10-week trend deltas
  - Top topics per brand
  - Competitive gap (T-Mobile vs. Verizon, AT&T)
  - Emerging topic detection
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from src.config import cfg
from src.models import AggregatedMetrics, PostClassification

logger = logging.getLogger(__name__)


def _build_df(records: list[PostClassification]) -> pd.DataFrame:
    """Explode multi-brand posts — one row per brand per post."""
    rows = []
    for r in records:
        if r.classification_status == "failed":
            continue
        for brand in r.brands:
            rows.append({
                "post_id": r.post_id,
                "platform": r.platform,
                "timestamp": r.timestamp,
                "brand": brand,
                "sentiment": r.sentiment,
                "intent": r.intent,
                "emotion": r.emotion,
                "pillar": r.pillar,
                "category": r.category,
                "theme": r.theme,
                "topic": r.topic,
                "confidence": r.confidence,
                "is_multi_brand": r.is_multi_brand,
            })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    for col in ["platform", "brand", "sentiment", "intent", "emotion", "pillar"]:
        if col in df.columns:
            df[col] = df[col].astype("category")

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["date"] = df["timestamp"].dt.date
    return df


def compute_brand_metrics(
    records: list[PostClassification],
    run_id: str,
    period_start: datetime,
    period_end: datetime,
) -> list[AggregatedMetrics]:
    """Compute per-brand aggregated metrics for the current cycle."""
    df = _build_df(records)
    if df.empty:
        logger.warning("No valid records for aggregation")
        return []

    total_posts = df["post_id"].nunique()
    metrics: list[AggregatedMetrics] = []

    for brand in cfg.brands:
        bdf = df[df["brand"] == brand].copy()
        if bdf.empty:
            continue

        n = len(bdf)
        conv_share = round(n / total_posts * 100, 2)

        def pct(col: str, val: str) -> float:
            return round((bdf[col] == val).sum() / n * 100, 2) if n else 0.0

        pos = pct("sentiment", "Positive")
        neu = pct("sentiment", "Neutral")
        neg = pct("sentiment", "Negative")
        nss = round(pos - neg, 2)

        complaint = pct("intent", "Complaint")
        inquiry = pct("intent", "Inquiry")
        praise = pct("intent", "Praise")
        recommendation = pct("intent", "Recommendation")
        c2p = round(complaint / praise, 3) if praise > 0 else float("inf")

        frustration = pct("emotion", "Frustration")
        satisfaction = pct("emotion", "Satisfaction")
        confusion = pct("emotion", "Confusion")
        excitement = pct("emotion", "Excitement")

        metrics.append(AggregatedMetrics(
            pipeline_run_id=run_id,
            taxonomy_version=cfg.taxonomy_version,
            schema_version=cfg.schema_version,
            period_start=period_start,
            period_end=period_end,
            brand=brand,
            total_posts=n,
            conversation_share_pct=conv_share,
            positive_pct=pos,
            neutral_pct=neu,
            negative_pct=neg,
            net_sentiment_score=nss,
            complaint_pct=complaint,
            inquiry_pct=inquiry,
            praise_pct=praise,
            recommendation_pct=recommendation,
            complaint_to_praise_ratio=c2p,
            frustration_pct=frustration,
            satisfaction_pct=satisfaction,
            confusion_pct=confusion,
            excitement_pct=excitement,
        ))

    logger.info("Computed metrics for %d brands", len(metrics))
    return metrics


def compute_top_topics(
    records: list[PostClassification],
    run_id: str,
    n: int = 10,
    prior_topics: set[str] | None = None,
) -> pd.DataFrame:
    """Top N topics per brand. Marks emerging topics."""
    df = _build_df(records)
    if df.empty:
        return pd.DataFrame()

    total = len(df)
    result = (
        df[df["pillar"] != "Uncategorized"]
        .groupby(["brand", "pillar", "category", "theme", "topic"], observed=True)
        .size()
        .rename("post_count")
        .reset_index()
    )
    result["topic_share_pct"] = (result["post_count"] / total * 100).round(2)

    # Rank per brand
    result["rank"] = result.groupby("brand", observed=True)["post_count"].rank(
        method="first", ascending=False
    ).astype(int)
    result = result[result["rank"] <= n].copy()

    # Emerging flag
    if prior_topics:
        prior_share = {t: s for t, s in prior_topics}  # type: ignore
        result["is_emerging"] = result.apply(
            lambda row: (
                row["topic"] not in prior_share or prior_share[row["topic"]] < 1.0
            ) and row["topic_share_pct"] >= 1.0,
            axis=1,
        )
    else:
        result["is_emerging"] = False

    result["pipeline_run_id"] = run_id
    return result.sort_values(["brand", "rank"])


def compute_daily_trends(
    records: list[PostClassification],
    run_id: str,
) -> pd.DataFrame:
    """Daily trend snapshot per brand for the full lookback window."""
    df = _build_df(records)
    if df.empty:
        return pd.DataFrame()

    all_dates = pd.date_range(
        df["timestamp"].dt.date.min(),
        df["timestamp"].dt.date.max(),
        freq="D",
    ).date
    all_brands = list(cfg.brands)
    spine = pd.MultiIndex.from_product([all_dates, all_brands], names=["date", "brand"])

    def daily_metric(metric_col: str, metric_val: str) -> pd.Series:
        return (
            df[df[metric_col] == metric_val]
            .groupby(["date", "brand"], observed=True)
            .size()
            .reindex(spine, fill_value=0)
        )

    daily_total = (
        df.groupby(["date", "brand"], observed=True)
        .size()
        .reindex(spine, fill_value=0)
        .rename("post_count")
        .reset_index()
    )

    daily_pos = daily_metric("sentiment", "Positive").rename("positive_count")
    daily_neg = daily_metric("sentiment", "Negative").rename("negative_count")
    daily_complaint = daily_metric("intent", "Complaint").rename("complaint_count")
    daily_praise = daily_metric("intent", "Praise").rename("praise_count")
    daily_frustration = daily_metric("emotion", "Frustration").rename("frustration_count")
    daily_satisfaction = daily_metric("emotion", "Satisfaction").rename("satisfaction_count")

    trends = daily_total.copy()
    for series in [daily_pos, daily_neg, daily_complaint, daily_praise, daily_frustration, daily_satisfaction]:
        trends = trends.merge(series.reset_index(), on=["date", "brand"], how="left")

    n = trends["post_count"].replace(0, np.nan)
    trends["net_sentiment_score"] = ((trends["positive_count"] - trends["negative_count"]) / n * 100).round(2)
    trends["complaint_pct"] = (trends["complaint_count"] / n * 100).round(2)
    trends["praise_pct"] = (trends["praise_count"] / n * 100).round(2)
    trends["frustration_pct"] = (trends["frustration_count"] / n * 100).round(2)
    trends["satisfaction_pct"] = (trends["satisfaction_count"] / n * 100).round(2)
    trends["conversation_share_pct"] = (trends["post_count"] / len(df) * 100).round(2)
    trends["pipeline_run_id"] = run_id

    return trends[["pipeline_run_id", "date", "brand", "post_count",
                    "conversation_share_pct", "net_sentiment_score",
                    "complaint_pct", "praise_pct", "frustration_pct", "satisfaction_pct"]]


def competitive_gap(metrics: list[AggregatedMetrics]) -> dict:
    """T-Mobile NSS vs. Verizon and AT&T."""
    by_brand = {m.brand: m for m in metrics}
    tmobile = by_brand.get("T-Mobile US")
    if not tmobile:
        return {}

    gap: dict = {}
    for competitor in ("Verizon", "AT&T Mobility"):
        comp = by_brand.get(competitor)
        if comp:
            gap[competitor] = {
                "nss_gap": round(tmobile.net_sentiment_score - comp.net_sentiment_score, 2),
                "complaint_rate_gap": round(tmobile.complaint_pct - comp.complaint_pct, 2),
            }
    return gap
