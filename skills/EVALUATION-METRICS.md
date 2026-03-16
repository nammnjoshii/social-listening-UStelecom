# Evaluation Metrics — U.S. Telecom Social Listening

This document defines the **evaluation framework** for Claude Code outputs, ensuring **reliable, accurate, and actionable social listening analytics**.

> **Client:** T-Mobile US | **Competitors:** AT&T Mobility, Verizon

---

## 1. LLM Evaluation Metrics

Measure the performance of Claude across all classification dimensions:

| Metric | Description |
|--------|-------------|
| **Sentiment Accuracy** | % of posts with correctly assigned Positive / Neutral / Negative sentiment |
| **Intent Accuracy** | % of posts with correctly identified primary intent (Complaint, Inquiry, Praise, Recommendation) |
| **Emotion Accuracy** | % of posts with correctly identified dominant emotion (Frustration, Satisfaction, Confusion, Excitement) |
| **Topic Consistency** | Degree to which posts are classified under canonical **taxonomy.md** hierarchy |
| **Brand Detection Precision/Recall** | Accuracy of multi-brand extraction against ground truth |

**Notes:** Use **confusion matrices** and **F1 scores** for precision, recall, and overall performance evaluation.

---

## 2. Manual Spot Checks

- Review a **random sample of 30 posts per day** across platforms.  
- Verify:  
  - Brand mentions  
  - Taxonomy assignment  
  - Sentiment, intent, emotion  
- Feed **discrepancies back into Claude prompt tuning** and pipeline improvements.  

---

## 3. Drift Detection

Monitor for changes over time to maintain **stable, reliable analytics**:

| Drift Type | Detection Rule | Action |
|------------|----------------|--------|
| **Topic Distribution Drift** | Unexpected shifts in Pillar / Category / Theme / Topic proportions | Flag for review; retrain or adjust taxonomy prompts |
| **Sentiment Polarity Drift** | Abrupt changes in sentiment percentages | Investigate posts; recalibrate LLM or rules |
| **Intent / Emotion Drift** | Significant shifts in distribution | Review prompts; update training examples if needed |

---

## 4. Best Practices

- **Daily Evaluation:** Combine automated metrics with **manual spot checks**.  
- **Alerts & Logging:** Integrate **real-time alerts** when drift thresholds are exceeded.  
- **Versioned Tracking:** Link evaluation results to **`taxonomy_version`** and **`schema_version`** for reproducibility.  
- **Cross-Platform Consistency:** Ensure metrics are tracked **independently and collectively** for Instagram, Reddit, and X.  
- **Continuous Improvement:** Feed insights from evaluation into **prompt refinement, noise filtering, and classification rules**.  

---

## 5. Experiment Tracking

Track every prompt version tested against the labeled evaluation set. This table is the source of truth for prompt promotion decisions.

| Run Date | Prompt Version | Taxonomy Version | Sentiment Acc | Intent Acc | Emotion Acc | Brand Recall | Flagged % | Promoted? |
|----------|---------------|-----------------|--------------|-----------|------------|-------------|----------|----------|
| 2026-03-14 | sentiment-v2.1.0 | 2.0.0 | 0.88 | 0.83 | 0.80 | 0.97 | 3.2% | Yes |
| 2026-03-07 | sentiment-v2.0.0 | 2.0.0 | 0.85 | 0.81 | 0.78 | 0.96 | 4.1% | Yes |
| 2026-02-28 | sentiment-v1.3.0 | 1.5.0 | 0.79 | 0.76 | 0.74 | 0.93 | 7.8% | No |

Add a new row after each evaluation run before promoting a prompt to the full 1,500-post pipeline.

---

## 6. Pipeline Run Log Format

Every pipeline run writes a structured log record for auditability and rollback decisions:

```json
{
  "run_id": "run-2026-03-14-001",
  "started_at": "2026-03-14T08:00:00Z",
  "completed_at": "2026-03-14T08:47:23Z",
  "prompt_version": "sentiment-v2.1.0",
  "taxonomy_version": "2.0.0",
  "schema_version": "1.0",
  "post_count": 1500,
  "classified_count": 1452,
  "flagged_count": 48,
  "flagged_pct": 3.2,
  "avg_confidence": 0.847,
  "sentiment_accuracy": 0.88,
  "intent_accuracy": 0.83,
  "emotion_accuracy": 0.80,
  "brand_recall": 0.97,
  "elapsed_seconds": 2843
}
```

Store run logs alongside classified post outputs. Reference by `run_id` when investigating anomalies.

---

## 7. Data Validation Checkpoints

Apply schema validation at the boundaries of each pipeline step — not just at the end:

| Step | Validation Check | Failure Action |
|------|-----------------|----------------|
| Post ingestion | Platform quota = 500/platform, no nulls in `post_id` / `timestamp` | Abort — do not proceed with partial dataset |
| After brand tagging | `brands` field is non-empty list, all values in canonical brand list | Flag record, continue |
| After Claude classification | JSON parseable, all required fields present, labels in allowed vocabulary | Flag record, log, skip aggregation |
| After aggregation | Conversation share % sums to ≤ 300% (multi-brand), sentiment % sums to 100% per brand | Alert — check explode logic |

---

## 8. Reproducibility Requirements

Every pipeline run must pin its context to enable exact replay:

```json
{
  "prompt_version": "sentiment-v2.1.0",
  "taxonomy_version": "2.0.0",
  "schema_version": "1.0",
  "claude_model": "claude-sonnet-4-6",
  "sample_seed": 42,
  "pipeline_run_id": "run-2026-03-14-001"
}
```

Include this metadata block in the run log and in the output JSONL header. Never run a pipeline without pinning prompt and taxonomy versions.

---

## 9. Rollback Criteria

Automatically trigger a rollback review when any of the following thresholds are breached vs. the previous run's baseline:

| Metric | Rollback Threshold |
|--------|-------------------|
| Sentiment Accuracy | Drop > 5 percentage points |
| Intent Accuracy | Drop > 5 percentage points |
| Flagged Post Rate | Increase > 3 percentage points |
| Brand Recall | Drop > 2 percentage points |
| Avg Confidence | Drop > 0.05 |

**Rollback procedure:** Revert to previous `prompt_version`, re-run on the same post batch, compare results. Do not promote the new version until accuracy recovers.

---

This evaluation framework ensures **Claude Code outputs are accurate, consistent, and actionable**, supporting executive dashboards and multi-brand trend analysis for U.S. telecom providers.
