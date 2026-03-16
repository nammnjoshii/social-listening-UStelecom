# Output Schema — U.S. Telecom Social Listening

This document defines the **canonical output schema** for the social listening pipeline, ensuring consistent, auditable, and actionable analytics across **Instagram, Reddit, and X (Twitter)**.

> **Client:** T-Mobile US | **Competitors:** AT&T Mobility, Verizon

---

## 1. Per-Post JSON Structure

Each post is represented as a structured JSON object. All records are **immutable** once written with a `pipeline_run_id`. Corrections are appended as new records using the `supersedes` field — never in-place edits.

```json
{
  "post_id": "string",
  "platform": "Instagram | Reddit | X",
  "timestamp": "ISO-8601",
  "normalized_text": "string",
  "brands": ["T-Mobile US", "Verizon", "AT&T Mobility"],
  "brand_confidence": "High | Medium | Low",
  "is_multi_brand": true,
  "pillar": "string",
  "category": "string",
  "theme": "string",
  "topic": "string",
  "sentiment": "Positive | Neutral | Negative",
  "intent": "Complaint | Inquiry | Praise | Recommendation",
  "emotion": "Frustration | Satisfaction | Confusion | Excitement",
  "confidence": "High | Medium | Low",
  "classification_status": "success | failed | retry",
  "taxonomy_version": "string",
  "schema_version": "string",
  "pipeline_run_id": "string",
  "supersedes": "post_id | null"
}
```

### Field Details

| Field | Type | Description |
|---|---|---|
| `post_id` | string | Unique identifier for each post |
| `platform` | enum | Source platform: `Instagram`, `Reddit`, or `X` |
| `timestamp` | ISO-8601 | Date and time of the original post |
| `normalized_text` | string | Cleaned post text as sent to Claude — the audit record of what was classified |
| `brands` | string[] | Canonical brand(s) confirmed in the post |
| `brand_confidence` | enum | Confidence of brand detection: `High` (canonical match), `Medium` (alias match), `Low` (Claude-validated) |
| `is_multi_brand` | boolean | `true` if the post references more than one brand — used to filter competitive comparison posts |
| `pillar` | string | Top-level taxonomy domain (must match active taxonomy) |
| `category` | string | Sub-domain under the Pillar |
| `theme` | string | Group of related topics |
| `topic` | string | Most granular classification; use `"Uncategorized"` if no taxonomy fit |
| `sentiment` | enum | Post-level sentiment polarity |
| `intent` | enum | Primary purpose of the post |
| `emotion` | enum | Dominant emotion expressed |
| `confidence` | enum | Claude's self-assessed classification confidence for the assigned labels |
| `classification_status` | enum | Pipeline status: `success`, `failed` (could not be classified after retry), `retry` (pending second pass) |
| `taxonomy_version` | string | Semantic version of the taxonomy used (e.g., `v1.0.0`) |
| `schema_version` | string | Semantic version of this output schema (e.g., `v1.0.0`) |
| `pipeline_run_id` | string | Unique identifier for the pipeline execution that produced this record |
| `supersedes` | string \| null | `post_id` of the record this corrects, or `null` if this is an original record |

---

## 2. Aggregated Metrics Schema

Aggregations are computed per brand and per taxonomy level after all posts are classified and quality-checked. Each aggregation record carries the same `pipeline_run_id` and `taxonomy_version` as its source post records.

```json
{
  "pipeline_run_id": "string",
  "taxonomy_version": "string",
  "schema_version": "string",
  "period_start": "ISO-8601",
  "period_end": "ISO-8601",
  "brand": "T-Mobile US | Verizon | AT&T Mobility | All",
  "total_posts": 0,
  "conversation_share_pct": 0.0,
  "sentiment": {
    "positive_pct": 0.0,
    "neutral_pct": 0.0,
    "negative_pct": 0.0,
    "net_sentiment_score": 0.0
  },
  "intent": {
    "complaint_pct": 0.0,
    "inquiry_pct": 0.0,
    "praise_pct": 0.0,
    "recommendation_pct": 0.0,
    "complaint_to_praise_ratio": 0.0
  },
  "emotion": {
    "frustration_pct": 0.0,
    "satisfaction_pct": 0.0,
    "confusion_pct": 0.0,
    "excitement_pct": 0.0
  },
  "top_topics": [
    {
      "pillar": "string",
      "category": "string",
      "theme": "string",
      "topic": "string",
      "post_count": 0,
      "topic_share_pct": 0.0,
      "is_emerging": false
    }
  ],
  "competitive_gap": {
    "nss_vs_verizon": 0.0,
    "nss_vs_att": 0.0,
    "complaint_rate_vs_verizon": 0.0,
    "complaint_rate_vs_att": 0.0
  },
  "trend_alerts": [
    {
      "metric": "string",
      "current_value": 0.0,
      "rolling_avg": 0.0,
      "std_deviations_from_avg": 0.0,
      "direction": "up | down"
    }
  ]
}
```

### Aggregated Metric Definitions

| Metric | Formula / Description |
|---|---|
| `conversation_share_pct` | `(Posts mentioning Brand X / Total posts) × 100` |
| `net_sentiment_score` | `% Positive − % Negative` — headline T-Mobile KPI |
| `complaint_to_praise_ratio` | `Complaint posts / Praise posts` — competitive benchmarking signal |
| `topic_share_pct` | Share of posts for a topic relative to total brand posts |
| `is_emerging` | `true` if the topic was absent or below 1% in the prior cycle but ≥1% in the current cycle |
| `nss_vs_verizon` | T-Mobile NSS minus Verizon NSS — positive = T-Mobile outperforms |
| `nss_vs_att` | T-Mobile NSS minus AT&T NSS — positive = T-Mobile outperforms |
| `complaint_rate_vs_verizon` | T-Mobile Complaint rate minus Verizon Complaint rate |
| `trend_alerts` | Metrics that moved more than 2 standard deviations from the 7-day rolling average |

---

## 3. 7-Day Trend Record

A daily snapshot record for tracking time-series trends per brand:

```json
{
  "pipeline_run_id": "string",
  "taxonomy_version": "string",
  "date": "ISO-8601",
  "brand": "T-Mobile US | Verizon | AT&T Mobility",
  "post_count": 0,
  "conversation_share_pct": 0.0,
  "net_sentiment_score": 0.0,
  "complaint_pct": 0.0,
  "praise_pct": 0.0,
  "frustration_pct": 0.0,
  "satisfaction_pct": 0.0,
  "top_topic": "string",
  "emerging_topics": ["string"]
}
```

---

## 4. Best Practices

**Schema Validation:** Enforce JSON schema validation at pipeline ingestion and after Claude processing. Any record failing validation is flagged as `classification_status: "failed"` and retried once before being written as a failed record.

**Canonical References:** Always use `TAXONOMY.md` and `BRAND-ENTITY-RECOGNITION.md` (uppercase filenames) for valid values of `pillar`, `category`, `theme`, `topic`, and `brands` fields.

**Versioning:** Every record includes `schema_version` and `taxonomy_version`. When the taxonomy changes, all records from the current cycle must be re-classified under the new taxonomy before trend charts are published — do not mix records from different taxonomy versions in the same trend computation.

**Multi-Brand Posts:** Tag all brands confirmed in the post. Use `is_multi_brand: true` to flag these records. Taxonomy placement, intent, sentiment, and emotion remain single-label. For aggregation, multi-brand posts contribute to each referenced brand's metrics independently.

**Immutability:** Records are append-only. Never edit a published record in-place. If a correction is needed, write a new record with `supersedes` pointing to the original `post_id`.

**Time-Series Integration:** Use `timestamp` (post-level) and `date` (trend-level) to compute 7-day rolling trends and power dynamic dashboard views. Ensure all timestamps are stored in UTC.

**Confidence Gating:** Records with `confidence: "Low"` are flagged for secondary review before being included in aggregations. If the Low-confidence rate exceeds 15% of total posts in a cycle, halt aggregation and escalate before publishing.

**Cost Monitoring:** Track Claude API token usage per `pipeline_run_id`. A standard 1,500-post cycle consumes approximately 1.4M input tokens and 225K output tokens.
