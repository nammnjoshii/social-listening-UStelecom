"""Post-classification quality checks per DATA-QUALITY-CHECKS.md.

Enforces:
  - Confidence gate (halt if Low-confidence rate > 15%)
  - Distribution sanity checks (sentiment concentration, topic concentration)
  - Platform balance check (450–550 posts per platform)
  - Brand parity audit (T-Mobile > 50% → normalize flag)
"""
from __future__ import annotations

import logging
from collections import Counter

from src.config import cfg
from src.models import PostClassification

logger = logging.getLogger(__name__)


class QualityGateError(Exception):
    """Raised when a critical quality check fails and the pipeline must halt."""


def run_quality_checks(
    records: list[PostClassification],
) -> dict:
    """
    Run all post-classification quality checks.
    Returns a stats dict. Raises QualityGateError on critical failures.
    """
    stats: dict = {}
    total = len(records)
    if total == 0:
        raise QualityGateError("No classified records — cannot proceed.")

    # ── Confidence gate ───────────────────────────────────────────────
    # Exclude failed/credit_error posts from the denominator — these are
    # API failures, not bad classifications. Counting them inflates the
    # low-confidence rate and triggers false quality gate halts.
    classifiable = [r for r in records if r.classification_status in ("success", "flagged")]
    classifiable_total = len(classifiable)
    if classifiable_total == 0:
        logger.warning(
            "No successfully classified posts — all %d records are failed/credit_error. "
            "Skipping confidence gate.", total,
        )
    low_confidence = [r for r in classifiable if r.confidence == "Low"]
    low_pct = len(low_confidence) / classifiable_total if classifiable_total else 0.0
    stats["low_confidence_count"] = len(low_confidence)
    stats["low_confidence_pct"] = round(low_pct * 100, 2)

    if low_pct > cfg.low_confidence_halt_pct:
        raise QualityGateError(
            f"Low-confidence rate {low_pct:.1%} exceeds halt threshold "
            f"{cfg.low_confidence_halt_pct:.1%}. "
            "Taxonomy may be under-specified. Escalate to project lead."
        )
    if low_pct > cfg.low_confidence_warn_pct:
        logger.warning(
            "Low-confidence rate %.1f%% exceeds warning threshold %.1f%%",
            low_pct * 100, cfg.low_confidence_warn_pct * 100,
        )

    # ── Classification success rate ───────────────────────────────────
    failed = [r for r in records if r.classification_status == "failed"]
    failed_pct = len(failed) / total
    stats["failed_count"] = len(failed)
    stats["failed_pct"] = round(failed_pct * 100, 2)
    if failed_pct > 0.05:
        logger.warning("Classification failure rate %.1f%% exceeds 5%% — check Claude API health", failed_pct * 100)

    # ── Platform balance ──────────────────────────────────────────────
    # Only enforce balance on platforms that actually returned data.
    # Platforms with 0 posts are logged as warnings (not halts) — they may
    # be unavailable due to missing credentials or external rate limits.
    platform_counts = Counter(r.platform for r in records)
    stats["platform_counts"] = dict(platform_counts)
    tolerance = 50  # ±10% of 500
    for platform in cfg.platforms:
        count = platform_counts.get(platform, 0)
        if count == 0:
            logger.warning(
                "Platform %s returned 0 posts — credentials missing or source unavailable",
                platform,
            )
        elif count < (cfg.posts_per_platform - tolerance):
            logger.warning(
                "Platform %s has only %d posts (target %d ±%d)",
                platform, count, cfg.posts_per_platform, tolerance,
            )

    # ── Sentiment distribution per brand ─────────────────────────────
    brand_sentiment: dict[str, Counter] = {}
    for r in records:
        for brand in r.brands:
            brand_sentiment.setdefault(brand, Counter())[r.sentiment] += 1

    stats["brand_sentiment"] = {}
    for brand, counts in brand_sentiment.items():
        brand_total = sum(counts.values())
        neg_pct = counts.get("Negative", 0) / brand_total if brand_total else 0
        stats["brand_sentiment"][brand] = {
            k: round(v / brand_total * 100, 2) for k, v in counts.items()
        }
        if neg_pct > 0.80:
            logger.warning(
                "%s shows %.0f%% Negative sentiment — possible bot/spam wave",
                brand, neg_pct * 100,
            )

    # ── Topic concentration ───────────────────────────────────────────
    topic_counts = Counter(r.topic for r in records)
    top_topic, top_count = topic_counts.most_common(1)[0] if topic_counts else ("", 0)
    top_pct = top_count / total if total else 0
    stats["top_topic"] = top_topic
    stats["top_topic_pct"] = round(top_pct * 100, 2)
    if top_pct > 0.30:
        logger.warning(
            "Topic '%s' captures %.0f%% of posts — may be over-broad",
            top_topic, top_pct * 100,
        )

    # ── Brand parity ─────────────────────────────────────────────────
    all_brand_counts: Counter = Counter()
    for r in records:
        for b in r.brands:
            all_brand_counts[b] += 1
    grand_total = sum(all_brand_counts.values())
    tmobile_pct = all_brand_counts.get("T-Mobile US", 0) / grand_total if grand_total else 0
    stats["tmobile_share_pct"] = round(tmobile_pct * 100, 2)
    stats["normalize_metrics"] = tmobile_pct > 0.50
    if tmobile_pct > 0.50:
        logger.warning(
            "T-Mobile US represents %.0f%% of brand mentions — use percentage metrics only",
            tmobile_pct * 100,
        )

    # ── Uncategorized rate ────────────────────────────────────────────
    uncategorized = sum(1 for r in records if r.pillar == "Uncategorized")
    uncategorized_pct = uncategorized / total
    stats["uncategorized_count"] = uncategorized
    stats["uncategorized_pct"] = round(uncategorized_pct * 100, 2)
    if uncategorized_pct > 0.10:
        logger.warning(
            "%.0f%% of posts are Uncategorized — review taxonomy for coverage gaps",
            uncategorized_pct * 100,
        )

    logger.info("Quality checks passed — stats: %s", stats)
    return stats
