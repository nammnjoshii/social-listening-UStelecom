"""Executive insight generation via Claude.

Compiles aggregated metrics into a structured briefing and calls
Claude to produce the executive brief per EXECUTIVE-INSIGHT-GENERATION.md.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import anthropic

from src.config import cfg
from src.models import AggregatedMetrics, ExecutiveInsight

logger = logging.getLogger(__name__)

INSIGHT_SYSTEM = """\
You are a senior telecom industry analyst writing a weekly executive brief
for T-Mobile US leadership. Be direct, data-driven, and action-oriented.
Return ONLY valid JSON — no preamble or explanation text.
"""

INSIGHT_PROMPT = """\
Generate a structured executive social listening brief based on the data below.

DATA SUMMARY:
{data_json}

Return exactly this JSON structure:
{{
  "top_complaints": [
    {{"topic": "...", "brand": "T-Mobile US", "complaint_pct": 0.0, "context": "..."}}
  ],
  "emerging_topics": [
    {{"topic": "...", "brands_affected": ["..."], "growth_note": "..."}}
  ],
  "sentiment_gaps": {{
    "tmobile_nss": 0.0,
    "verizon_nss": 0.0,
    "att_nss": 0.0,
    "tmobile_vs_verizon": 0.0,
    "tmobile_vs_att": 0.0,
    "narrative": "..."
  }},
  "emotion_signals": {{
    "highest_frustration_brand": "...",
    "highest_satisfaction_brand": "...",
    "frustration_by_brand": {{"T-Mobile US": 0.0, "Verizon": 0.0, "AT&T Mobility": 0.0}},
    "satisfaction_by_brand": {{"T-Mobile US": 0.0, "Verizon": 0.0, "AT&T Mobility": 0.0}},
    "confusion_by_brand": {{"T-Mobile US": 0.0, "Verizon": 0.0, "AT&T Mobility": 0.0}},
    "excitement_by_brand": {{"T-Mobile US": 0.0, "Verizon": 0.0, "AT&T Mobility": 0.0}},
    "narrative": "..."
  }},
  "strategic_recommendations": [
    "Recommendation 1 for T-Mobile US leadership.",
    "Recommendation 2 for T-Mobile US leadership."
  ]
}}

Guidelines:
- top_complaints: top 3 T-Mobile US complaint topics by complaint_pct
- emerging_topics: top 3 topics that appeared or grew significantly this week
- sentiment_gaps: positive gap = T-Mobile outperforms; negative = underperforms
- emotion_signals: populate all four emotion breakdowns from the brand_metrics data
- strategic_recommendations: 2–3 concrete, executive-level action items
"""


def generate_insight(
    brand_metrics: list[AggregatedMetrics],
    top_topics_df,       # pd.DataFrame from aggregate.compute_top_topics
    competitive_gap: dict,
    run_id: str,
    platform_counts: dict | None = None,  # platform → post count for data quality notes
    topic_hierarchy_df=None,              # pd.DataFrame with pillar/category/theme/topic columns
) -> ExecutiveInsight:
    """Call Claude to generate the weekly executive brief."""

    # ── Build data summary for the prompt ────────────────────────────────────
    summary = {
        "brand_metrics": [
            {
                "brand": m.brand,
                "total_posts": m.total_posts,
                "conversation_share_pct": m.conversation_share_pct,
                "net_sentiment_score": m.net_sentiment_score,
                "positive_pct": m.positive_pct,
                "neutral_pct": m.neutral_pct,
                "negative_pct": m.negative_pct,
                "complaint_pct": m.complaint_pct,
                "inquiry_pct": m.inquiry_pct,
                "praise_pct": m.praise_pct,
                "recommendation_pct": m.recommendation_pct,
                "frustration_pct": m.frustration_pct,
                "satisfaction_pct": m.satisfaction_pct,
                "confusion_pct": m.confusion_pct,
                "excitement_pct": m.excitement_pct,
            }
            for m in brand_metrics
        ],
        "competitive_gap": competitive_gap,
        "top_topics_by_brand": {},
        "emerging_topics": [],
    }

    if top_topics_df is not None and not top_topics_df.empty:
        for brand in cfg.brands:
            bdf = top_topics_df[top_topics_df["brand"] == brand].head(5)
            summary["top_topics_by_brand"][brand] = bdf[["topic", "post_count", "topic_share_pct"]].to_dict("records")
            emerging = bdf[bdf["is_emerging"]]["topic"].tolist() if "is_emerging" in bdf.columns else []
            summary["emerging_topics"].extend(emerging)

    # ── Pre-compute structured fields (not LLM-dependent) ────────────────────
    conversation_share = {m.brand: m.conversation_share_pct for m in brand_metrics}

    intent_distribution = {
        m.brand: {
            "Complaint": m.complaint_pct,
            "Inquiry": m.inquiry_pct,
            "Praise": m.praise_pct,
            "Recommendation": m.recommendation_pct,
        }
        for m in brand_metrics
    }

    # Topic hierarchy: top 10 topics across all brands with full taxonomy path
    topic_hierarchy: list[dict] = []
    if topic_hierarchy_df is not None and not topic_hierarchy_df.empty:
        cols = [c for c in ["pillar", "category", "theme", "topic", "brand", "post_count"] if c in topic_hierarchy_df.columns]
        top = topic_hierarchy_df[cols].sort_values("post_count", ascending=False).head(10)
        topic_hierarchy = top.to_dict("records")

    # Data quality notes
    data_quality_notes: list[str] = []
    target = cfg.posts_per_platform
    if platform_counts:
        for platform, count in platform_counts.items():
            if count == 0:
                data_quality_notes.append(
                    f"{platform}: 0 posts collected — credentials missing or source unavailable."
                )
            elif count < target:
                data_quality_notes.append(
                    f"{platform}: {count} posts collected (target {target}) — partial coverage."
                )
    total_posts = sum(m.total_posts for m in brand_metrics)
    expected = target * len(cfg.platforms)
    if total_posts < expected:
        data_quality_notes.append(
            f"Total classified posts: {total_posts} of {expected} targeted — "
            "metrics may underrepresent full conversation volume."
        )

    # ── Call Claude ───────────────────────────────────────────────────────────
    client = anthropic.Anthropic(api_key=cfg.claude_api_key)
    try:
        response = client.messages.create(
            model=cfg.claude_model,
            max_tokens=2048,
            system=INSIGHT_SYSTEM,
            messages=[{
                "role": "user",
                "content": INSIGHT_PROMPT.format(data_json=json.dumps(summary, indent=2)),
            }],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        data = json.loads(raw)
        return ExecutiveInsight(
            pipeline_run_id=run_id,
            generated_at=datetime.now(timezone.utc),
            top_complaints=data.get("top_complaints", []),
            emerging_topics=data.get("emerging_topics", []),
            sentiment_gaps=data.get("sentiment_gaps", {}),
            emotion_signals=data.get("emotion_signals", {}),
            strategic_recommendations=data.get("strategic_recommendations", []),
            conversation_share=conversation_share,
            intent_distribution=intent_distribution,
            topic_hierarchy=topic_hierarchy,
            data_quality_notes=data_quality_notes,
        )

    except Exception as e:
        logger.error("Insight generation failed: %s", e)
        return ExecutiveInsight(
            pipeline_run_id=run_id,
            generated_at=datetime.now(timezone.utc),
            top_complaints=[],
            emerging_topics=[],
            sentiment_gaps={},
            emotion_signals={},
            strategic_recommendations=["Insight generation failed — review pipeline logs."],
            conversation_share=conversation_share,
            intent_distribution=intent_distribution,
            topic_hierarchy=topic_hierarchy,
            data_quality_notes=data_quality_notes,
        )
