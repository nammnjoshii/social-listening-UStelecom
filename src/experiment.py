"""Data source experimentation — measures and ranks platforms by signal quality.

Runs after classification to assess which platforms provide the most actionable
telecom customer intelligence. Results are stored in platform_experiment_results
and printed to the console as a Rich table.

Usage (via pipeline.py):
    python -m src.pipeline --experiment

Metrics (per platform):
    SNR                — % posts that are genuine telecom signals
    Complaint Rate     — % posts classified as Complaint
    Topic Diversity    — distinct taxonomy topics, normalised 0–100
    Sentiment Clarity  — % posts with High confidence classification

Composite score weights:
    SNR 35% | Complaint Rate 25% | Topic Diversity 20% | Sentiment Clarity 20%
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from rich.console import Console
from rich.table import Table

from src.config import cfg
from src.models import PlatformScore, PostClassification

logger = logging.getLogger(__name__)
console = Console()

# Composite score weights — must sum to 1.0
WEIGHTS: dict[str, float] = {
    "snr":               0.35,
    "complaint_rate":    0.25,
    "topic_diversity":   0.20,
    "sentiment_clarity": 0.20,
}

# Number of distinct topics considered "full diversity" (ceiling for normalisation)
_TOPIC_DIVERSITY_CEILING = 20

# Base allocation per platform (posts per run) — adjusted by rank
_BASE_ALLOCATION = cfg.posts_per_platform  # default 500


def _compute_platform_metrics(
    records: list[PostClassification],
    platform: str,
) -> dict[str, float]:
    """Compute the four raw quality metrics for one platform."""
    platform_records = [r for r in records if r.platform == platform]
    total = len(platform_records)

    if total == 0:
        return {
            "post_count": 0,
            "snr_pct": 0.0,
            "complaint_rate_pct": 0.0,
            "topic_diversity_score": 0.0,
            "sentiment_clarity_pct": 0.0,
        }

    # Signal-to-noise: successful classification + real taxonomy node + not Low confidence
    signal_count = sum(
        1 for r in platform_records
        if r.classification_status in ("success", "flagged")
        and r.pillar != "Uncategorized"
        and r.confidence != "Low"
    )
    snr_pct = signal_count / total * 100

    # Complaint rate
    complaint_count = sum(1 for r in platform_records if r.intent == "Complaint")
    complaint_rate_pct = complaint_count / total * 100

    # Topic diversity — distinct non-Uncategorized topics, normalised to 0–100
    distinct_topics = len({
        r.topic for r in platform_records
        if r.topic and r.topic != "Uncategorized"
    })
    topic_diversity_score = min(distinct_topics / _TOPIC_DIVERSITY_CEILING, 1.0) * 100

    # Sentiment clarity — High confidence classification rate
    high_conf_count = sum(1 for r in platform_records if r.confidence == "High")
    sentiment_clarity_pct = high_conf_count / total * 100

    return {
        "post_count": total,
        "snr_pct": round(snr_pct, 2),
        "complaint_rate_pct": round(complaint_rate_pct, 2),
        "topic_diversity_score": round(topic_diversity_score, 2),
        "sentiment_clarity_pct": round(sentiment_clarity_pct, 2),
    }


def _score_platform(metrics: dict[str, float]) -> float:
    """Compute composite score (0–100) using WEIGHTS."""
    return round(
        metrics["snr_pct"]              * WEIGHTS["snr"]
        + metrics["complaint_rate_pct"] * WEIGHTS["complaint_rate"]
        + metrics["topic_diversity_score"] * WEIGHTS["topic_diversity"]
        + metrics["sentiment_clarity_pct"] * WEIGHTS["sentiment_clarity"],
        2,
    )


def _generate_allocation(scores: list[PlatformScore]) -> list[PlatformScore]:
    """
    Rank platforms and assign recommended_allocation.
    Top-2 platforms get +20% allocation; bottom-1 gets -20%.
    All others keep the base allocation.
    Returns a new list with rank and recommended_allocation filled in.
    """
    sorted_scores = sorted(scores, key=lambda s: s.composite_score, reverse=True)
    result = []
    n = len(sorted_scores)
    for i, s in enumerate(sorted_scores):
        rank = i + 1
        if rank <= 2:
            allocation = int(_BASE_ALLOCATION * 1.20)
        elif rank == n:
            allocation = int(_BASE_ALLOCATION * 0.80)
        else:
            allocation = _BASE_ALLOCATION
        result.append(s.model_copy(update={"rank": rank, "recommended_allocation": allocation}))
    return result


def run_experiment(
    classified: list[PostClassification],
    run_id: str,
) -> list[PlatformScore]:
    """
    Measure platform quality and rank all platforms.

    Args:
        classified: Full list of PostClassification records from classify.py.
        run_id:     The pipeline_run_id for this execution.

    Returns:
        List of PlatformScore sorted by rank (best first).
    """
    experiment_run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    scores: list[PlatformScore] = []

    for platform in cfg.platforms:
        metrics = _compute_platform_metrics(classified, platform)
        composite = _score_platform(metrics)
        scores.append(PlatformScore(
            experiment_run_id=experiment_run_id,
            pipeline_run_id=run_id,
            platform=platform,
            post_count=int(metrics["post_count"]),
            snr_pct=metrics["snr_pct"],
            complaint_rate_pct=metrics["complaint_rate_pct"],
            topic_diversity_score=metrics["topic_diversity_score"],
            sentiment_clarity_pct=metrics["sentiment_clarity_pct"],
            composite_score=composite,
            rank=0,                    # filled in by _generate_allocation
            recommended_allocation=0,  # filled in by _generate_allocation
            computed_at=now,
        ))

    ranked = _generate_allocation(scores)
    logger.info("Platform experiment complete — %d platforms scored", len(ranked))
    return ranked


def print_experiment_report(scores: list[PlatformScore]) -> None:
    """Print a Rich table summarising platform quality scores."""
    table = Table(title="Platform Signal Quality Experiment", show_lines=True)
    table.add_column("Rank", style="bold", justify="right")
    table.add_column("Platform", style="bold")
    table.add_column("Posts", justify="right")
    table.add_column("SNR %", justify="right")
    table.add_column("Complaint %", justify="right")
    table.add_column("Diversity", justify="right")
    table.add_column("Clarity %", justify="right")
    table.add_column("Score", justify="right")
    table.add_column("Rec. Alloc", justify="right")

    for s in sorted(scores, key=lambda x: x.rank):
        score_style = "green" if s.composite_score >= 60 else ("yellow" if s.composite_score >= 40 else "red")
        table.add_row(
            str(s.rank),
            s.platform,
            str(s.post_count),
            f"{s.snr_pct:.1f}",
            f"{s.complaint_rate_pct:.1f}",
            f"{s.topic_diversity_score:.1f}",
            f"{s.sentiment_clarity_pct:.1f}",
            f"[{score_style}]{s.composite_score:.1f}[/{score_style}]",
            str(s.recommended_allocation),
        )
    console.print(table)

    # Recommend ingestion strategy
    console.print("\n[bold]Recommended ingestion strategy:")
    total_alloc = sum(s.recommended_allocation for s in scores)
    for s in sorted(scores, key=lambda x: x.rank):
        pct = s.recommended_allocation / total_alloc * 100 if total_alloc else 0
        console.print(f"  {s.platform:<14} {pct:.0f}%  ({s.recommended_allocation} posts/run)")
