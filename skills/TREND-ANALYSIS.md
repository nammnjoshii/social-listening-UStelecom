# Trend Analysis

> **Client:** T-Mobile US | **Competitors:** AT&T Mobility, Verizon

## Purpose

Monitor conversation patterns across the last 7 days for **T-Mobile US** (client) benchmarked against **AT&T Mobility** and **Verizon** (competitors).

Platforms analyzed:

- Instagram
- Reddit
- X (Twitter)

---

## Metrics

Conversation volume  
Sentiment trends  
Complaint trends  
Emotion signals

---

## Example Insight

A spike in negative sentiment may indicate:

- service outages
- billing issues
- customer support delays

---

## Output

Trend charts comparing telecom providers.

---

## Alert Threshold Definitions

Concrete rules that trigger alerts when trend metrics exceed normal variation. These thresholds apply to the 7-day rolling window.

| Alert | Condition | Severity | Action |
|-------|-----------|----------|--------|
| **Sentiment Spike** | Negative sentiment % moves > 2 standard deviations from the 7-day rolling mean for any brand | High | Investigate posts from that day; surface to analyst |
| **Complaint Surge** | Daily Complaint intent count increases > 20% day-over-day for any brand | High | Flag for executive insight generation; check for outages |
| **Brand Volume Drop** | Post volume for any brand drops > 15% vs. prior 7-day average | Medium | Check data pipeline; confirm API ingestion is healthy |
| **Emotion Shift** | Frustration % increases > 10 percentage points week-over-week | Medium | Cross-reference with complaint and sentiment trends |
| **Flagged Post Rate** | > 5% of posts in a daily batch classified as `flagged` | Medium | Review prompt performance; check for data distribution shift |
| **Confidence Drop** | Average classification confidence drops below 0.75 for a daily batch | Low | Investigate prompt or model change; compare with prior run |

### Standard Deviation Calculation

For the sentiment spike alert, compute rolling mean and std over the last 7 daily values per brand:

```python
import pandas as pd

def detect_sentiment_spike(df: pd.DataFrame, brand: str, metric: str = "Negative") -> pd.DataFrame:
    brand_daily = (
        df[(df["brand"] == brand) & (df["sentiment"] == metric)]
        .groupby(df["timestamp"].dt.date)
        .size()
        .rename("count")
    )
    rolling = brand_daily.rolling(7, min_periods=3)
    mean = rolling.mean()
    std = rolling.std()
    return brand_daily[(brand_daily - mean).abs() > 2 * std]
```

---

## Pipeline Step Logging

Each step of the 12-step workflow must emit a structured log entry. This enables operational monitoring and post-incident review.

Log format (JSON, one line per step):

```json
{
  "run_id": "run-2026-03-14-001",
  "step": "brand_tagging",
  "step_number": 4,
  "started_at": "2026-03-14T08:05:12Z",
  "completed_at": "2026-03-14T08:06:44Z",
  "elapsed_seconds": 92,
  "input_count": 1487,
  "output_count": 1487,
  "error_count": 0,
  "notes": "13 posts dropped at cleaning step (duplicates)"
}
```

Emit one log record per step. Aggregate `elapsed_seconds` and `error_count` across steps for the pipeline run summary.

---

## Operational Dashboard Metrics

Beyond trend charts, the monitoring dashboard should surface these pipeline health metrics:

| Metric | Definition | Alert Threshold |
|--------|-----------|----------------|
| **Pipeline health** | % of steps completed without errors in the last run | < 100% → investigate |
| **Classification confidence distribution** | Histogram of `confidence` scores across all posts | > 5% posts below 0.75 → review |
| **Flagged post rate** | % posts with `classification_status = 'flagged'` | > 5% → prompt review |
| **Per-platform post count** | Count per platform vs. 500 quota | Deviation > 0 → data ingestion issue |
| **Processing latency** | Total elapsed time for the 1,500-post classification batch | > 90 min → scaling review |
| **Prompt version in use** | Current prompt version tag | Any untracked version → governance issue |

---

## Correlation ID Pattern

Link every pipeline artifact back to its run for traceability:

- Every post output record includes `pipeline_run_id`
- Every step log includes `run_id` and `step`
- Every alert notification includes `run_id` and the metric that triggered it
- The experiment tracking table in `EVALUATION-METRICS.md` references `run_id`

This allows a single `run_id` to be used to pull all posts, all step logs, accuracy results, and alert history for any given pipeline execution.