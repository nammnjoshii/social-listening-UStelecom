# Data Quality Checks — U.S. Telecom Social Listening

This document defines **data quality checks and thresholds** at multiple stages of the social listening pipeline to ensure **reliable, accurate, and auditable insights** for **T-Mobile US** (client) and its main competitors **AT&T Mobility** and **Verizon**.

> **Client:** T-Mobile US | **Competitors:** AT&T Mobility, Verizon

---

## 1. Before Processing (Pre-Ingestion)

Ensure raw posts meet baseline quality standards before entering the pipeline:

| Check | Rule | Failure Action |
|---|---|---|
| **Timestamp validity** | Every post has a valid ISO-8601 timestamp within the last 7 days | Exclude post; log as `invalid_timestamp` |
| **Platform distribution** | Each platform contributes **450–550 posts** (target 500, ±10% tolerance) | If any platform <400 posts, flag as data gap; halt if <300 |
| **Required fields** | `post_id`, `platform`, `timestamp`, `raw_text` are all non-null | Exclude post; log as `missing_field` |
| **Duplicate detection** | SHA-256 hash deduplication on normalized text | Remove duplicate; keep highest-engagement instance |
| **Bot pattern detection** | Automated or spam account signals (see NOISE-FILTERING.md) | Exclude post; log as `bot_detected` |

---

## 2. After Noise Filtering & Normalization

Verify dataset integrity before brand recognition:

| Check | Rule | Failure Action |
|---|---|---|
| **Minimum text length** | Normalized text ≥ 15 words | Exclude; already enforced by NOISE-FILTERING.md |
| **Language** | English-language posts only | Exclude; already enforced by NOISE-FILTERING.md |
| **Cleaning attrition rate** | No more than 40% of collected posts removed by filters | If >40% removed, investigate API collection filters — keyword query may be too broad |
| **Signal flag** | `signal: true` on all posts entering classification | Hard gate — no `signal: false` post proceeds |

---

## 3. After Brand Recognition

Verify that brand detection is accurate and canonical:

| Check | Rule | Failure Action |
|---|---|---|
| **Canonical mapping** | All `brands` values are one of: `T-Mobile US`, `AT&T Mobility`, `Verizon` | Flag record; exclude from analytics |
| **Minimum brand presence** | Each post references at least one confirmed brand | Exclude post; log as `no_brand_detected` |
| **Brand confidence** | `brand_confidence` field populated with `High`, `Medium`, or `Low` | Flag record if missing |
| **Brand parity audit** | T-Mobile US must not represent >50% of total posts | If >50%, log warning; normalize all aggregated metrics to percentages — do not compare raw counts across brands |
| **Multi-brand flag** | `is_multi_brand: true` when `brands` contains >1 entry | Validate programmatically; multi-brand posts counted once per referenced brand in aggregation |

---

## 4. After Claude Classification

Validate post-classification outputs before aggregation:

| Check | Rule | Failure Action |
|---|---|---|
| **JSON parseability** | Claude response must be valid parseable JSON | Apply JSON repair pass; if still invalid, mark `classification_status: "failed"` and retry once |
| **Required fields** | All 9 classification fields present: `brand`, `sentiment`, `intent`, `emotion`, `pillar`, `category`, `theme`, `topic`, `confidence` | Flag record; log missing fields; skip from aggregation |
| **Sentiment enum** | Value must be exactly one of: `Positive`, `Neutral`, `Negative` | Flag; log; skip from aggregation |
| **Intent enum** | Value must be exactly one of: `Complaint`, `Inquiry`, `Praise`, `Recommendation` | Flag; log; skip from aggregation |
| **Emotion enum** | Value must be exactly one of: `Frustration`, `Satisfaction`, `Confusion`, `Excitement` | Flag; log; skip from aggregation |
| **Taxonomy label validity** | `pillar`, `category`, `theme`, `topic` must match values in the active locked taxonomy | Flag; log; posts with `pillar: "Uncategorized"` are valid but tracked separately |
| **Schema version match** | `taxonomy_version` in each record matches the active taxonomy version for this cycle | Alert — do not mix records from different taxonomy versions in trend charts |

### Confidence Gate (Critical)

After all 1,500 posts are classified:

- If **Low-confidence rate > 15%** of total classified posts → **halt aggregation immediately**. Escalate to project lead before proceeding. The taxonomy may be under-specified for the current data distribution.
- If **Low-confidence rate 10–15%** → log warning; continue aggregation but flag the cycle report.
- If **Low-confidence rate < 10%** → proceed normally.
- If **classification success rate < 95%** (`classification_status: "success"`) → halt; investigate Claude API health.

---

## 5. Distribution Sanity Checks (Post-Classification, Pre-Aggregation)

Run after classification is complete:

| Check | Threshold | Severity | Action |
|---|---|---|---|
| **Negative sentiment concentration** | Any brand >80% Negative in a single cycle | High | Flag as potential bot/spam wave; manual spot-check before publishing |
| **Topic over-concentration** | Any single topic >30% of all posts | High | Flag as over-broad topic definition; review taxonomy before next cycle |
| **Platform balance** | Each platform must contribute 450–550 posts | Medium | Log deviation; investigate ingestion if outside range |
| **Uncategorized rate** | Posts with `pillar: "Uncategorized"` >10% | Medium | Review Uncategorized bucket; assess for taxonomy promotion candidates |
| **Conversation share** | Sum of all brand conversation shares ≤ 300% (multi-brand posts counted per brand) | Medium | Alert if >300% — check multi-brand explosion logic |

---

## 6. Ground Truth Spot-Check

Run once per weekly cycle after classification:

- **Sample:** 30 posts, stratified — 10 per platform (Instagram, Reddit, X).
- **Process:** Human reviewer assigns labels independently; compare against Claude output.
- **Record:** Agreement rate per dimension; feed discrepancies into prompt tuning.

**Target accuracy benchmarks:**

| Dimension | Target Human Agreement |
|---|---|
| Sentiment | ≥ 85% |
| Intent | ≥ 80% |
| Emotion | ≥ 75% |
| Taxonomy placement (Pillar level) | ≥ 90% |

If any dimension falls below its target for two consecutive cycles, trigger a prompt review and update the experiment tracking table in `EVALUATION-METRICS.md`.

---

## 7. Post-Aggregation Validation

After metrics are computed:

| Check | Rule | Failure Action |
|---|---|---|
| **Sentiment % sum** | Positive + Neutral + Negative = 100% per brand | Alert — check rounding or missing records |
| **Intent % sum** | Complaint + Inquiry + Praise + Recommendation = 100% per brand | Alert — same |
| **Conversation share** | ≤ 300% total across all brands (multi-brand allowed) | Alert — check brand explosion logic |
| **NSS range** | Net Sentiment Score must be in range [−100, +100] | Alert — recheck sentiment distribution |

---

## 8. Best Practices

- **Automated pipeline checks:** Integrate checks into ETL and LLM processing pipelines for real-time validation. Do not defer checks to the end of the cycle.
- **Fail fast:** Apply checks at each pipeline boundary (ingestion, brand recognition, classification, aggregation). Earlier failures are cheaper to fix.
- **Error logging & alerts:** Maintain structured logs for all failures and schema violations. Alert data engineers for critical failures (confidence gate breach, classification success rate <95%).
- **Version control:** Track `schema_version` and `taxonomy_version` with each post for auditability and reproducibility. See `TAXONOMY-VERSIONING.md` for versioning rules.
- **Cross-platform consistency:** Apply all quality checks uniformly across Instagram, Reddit, and X. Track per-platform metrics separately.

---

This framework ensures **Claude outputs are accurate, consistent, and trustworthy**, forming a solid foundation for **executive dashboards, comparative metrics, and trend analysis**.
