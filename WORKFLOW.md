# Data Processing Workflow — U.S. Telecom Social Listening

This document describes the **end-to-end workflow** for analyzing social media conversations about **T-Mobile US** (client) and its main competitors **AT&T Mobility** and **Verizon**. The workflow leverages **Claude as the intelligence layer** for taxonomy discovery and post classification, producing executive-ready insights.

> **Client:** T-Mobile US | **Competitors:** AT&T Mobility, Verizon

---

## Step 1 — Data Collection

- Collect posts from **Instagram, Reddit, and X (Twitter)**.
- Filter for posts referencing at least one target brand using the canonical alias corpus (see BRAND-ENTITY-RECOGNITION.md).
- Capture posts from the **last 7 days** (rolling window anchored to pipeline execution date).
- Collect up to **1,000 candidate posts per platform** (2× quota) to allow for attrition during cleaning.
- Store raw posts with: `platform`, `post_id`, `author_id` (anonymized), `timestamp`, `raw_text`, `engagement_metrics`, `brand_keywords_matched`.

**Platform API configuration:**
- **Instagram Graph API** — query brand hashtags (#tmobile, #verizon, #att, #attmobility) and @mentions; `since` = 7 days prior to execution date.
- **Reddit API** — search r/tmobile, r/verizon, r/ATT, r/wireless, r/NoContract and r/all with brand keywords; `time_filter=week`.
- **X/Twitter API v2** — recent search: `(T-Mobile OR TMobile OR Magenta OR Uncarrier OR Verizon OR VZW OR AT&T OR ATT) lang:en -is:retweet`; `start_time` = 7 days prior.

**Output:** Raw social media posts staged for processing.

---

## Step 2 — Stratified Sampling

- Sample **500 posts per platform** (1,500 total).
- If a platform returns fewer than 500 usable posts after cleaning, log it as a data gap.
- When downsampling from the 1,000-candidate pool, prioritize posts by engagement (likes + comments + shares) to maximize signal quality.
- Ensures balanced representation across platforms.

**Output:** Sampled candidate dataset for cleaning and analysis.

---

## Step 3 — Cleaning & Preprocessing

Apply the following filters **in order**:

1. **Deduplication** — SHA-256 hash on normalized text for exact duplicates; MinHash LSH (Jaccard similarity ≥ 0.85) for near-duplicates and cross-platform syndication.
2. **Spam & promotional removal** — Rule-based filters:
   - Discard posts with more than 5 hashtags.
   - Discard posts from verified brand accounts (promotional, not organic customer voice).
   - Discard URL-only posts.
   - Apply a blocklist of promotional phrases (e.g., "Click the link in bio", "Use code", "Ad:", "Sponsored").
   - For borderline cases, apply a Claude-assisted pass: *"Is this post organic customer commentary or promotional content? Answer: Organic / Promotional."*
3. **Text normalization** (applied in order):
   - Convert to lowercase.
   - Remove URLs (regex `https?://\S+`).
   - **Expand hashtags** — strip the `#` prefix but retain the word (e.g., `#tmobile` → `tmobile`) to preserve brand and topic signals.
   - Replace @mentions with `[USER]` placeholder to preserve conversational context without exposing usernames.
   - Normalize Unicode; strip emoji.
   - Collapse repeated whitespace and punctuation.
4. **Language filter** — retain English-language posts only (use `fastText` LID model for speed).
5. **Minimum-length filter** — discard posts with fewer than 15 words after normalization.

> **T-Mobile note:** Instagram image/meme posts are common in the T-Mobile community. Extract caption text via the Instagram Graph API before applying the length filter, as captions may carry the only meaningful text signal.

**Output:** Cleaned dataset (≤1,500 posts) + cleaning log recording removals per filter rule per platform.

---

## Step 4 — Brand Recognition

- Detect mentions of **T-Mobile US**, **AT&T Mobility**, and **Verizon** using the canonical alias dictionary in BRAND-ENTITY-RECOGNITION.md.
- Normalize brand variations (e.g., `TMobile` → `T-Mobile US`, `ATT` → `AT&T Mobility`, `Magenta` → `T-Mobile US`, `Big Red` → `Verizon`).
- Tag posts with multiple brands where applicable. Multi-brand posts are high-value for competitive analysis.
- **Confidence scoring** per brand detection:
  - **High** — exact canonical name match (e.g., "T-Mobile")
  - **Medium** — alias match (e.g., "Magenta", "Uncarrier", "Big Red")
  - **Low** — contextual inference only (e.g., "the pink carrier") — requires Claude validation
- For **Low-confidence** detections (~5–10% of posts), run a Claude validation pass: *"Does this post reference T-Mobile US, Verizon, AT&T Mobility, another carrier, or none of the above? Return a JSON array of brand names only."*
- Exclude posts with no confirmed brand match and log them.

> **T-Mobile note:** Include `Sprint` as a Medium-confidence T-Mobile alias — legacy Sprint customer references still surface post-merger.

**Output:** Brand-tagged posts with confidence scores.

---

## Step 5 — Topic Discovery & Taxonomy Creation (Claude)

- Claude analyzes a **stratified sample of 300 posts** (100 per platform) to identify recurring discussion topics.
- The taxonomy is constructed using the four-level hierarchy: `Pillar → Category → Theme → Topic`.
- **Seed the taxonomy** from documented examples (e.g., Network Performance → Coverage → Urban Coverage → Signal loss in subway) to anchor Claude and prevent structural drift.
- Discovery prompt constraints: **maximum 6 Pillars**, maximum 4 Categories per Pillar, maximum 4 Themes per Category.
- Validate taxonomy output: all four levels present, no duplicate labels, no orphaned nodes.
- **Human review checkpoint** — the project lead must approve the generated taxonomy before classification begins. This is a mandatory gate.
- **Lock the taxonomy** for the current analysis cycle. Topics discovered mid-cycle that do not fit the locked taxonomy are assigned to `"Uncategorized"` and logged as drift candidates for the next cycle. Do not update the taxonomy mid-cycle, as this causes classification inconsistency.
- **Version the taxonomy** with a semantic tag (e.g., `v1.0.0 — 2026-03-15`) — see TAXONOMY-VERSIONING.md for versioning rules.

**Expected Pillars for this cycle:**
Network Performance | Pricing & Plans | Customer Experience | Device & Equipment | Data & Privacy | Competitive Switching

**Output:** Approved, versioned, locked taxonomy and initial topic mapping.

---

## Step 6 — Post Classification (Claude)

For each post, Claude assigns all labels in a **single unified API call** to minimize latency and cost:

- **Taxonomy placement:** Pillar → Category → Theme → Topic (values must match the locked taxonomy)
- **Sentiment:** Positive, Neutral, Negative
- **Intent:** Complaint, Inquiry, Praise, Recommendation
- **Emotion:** Frustration, Satisfaction, Confusion, Excitement
- **Confidence:** High, Medium, or Low (Claude's self-assessed classification confidence)

**Batching:** Process posts in batches of 50 with async calls (concurrency limit of 5). Expected runtime: 8–12 minutes for 1,500 posts.

**Error handling:**
- Exponential backoff on rate limit errors: 2s → 4s → 8s → 16s.
- On repeated failure, mark the post as `classification_status: "failed"` and continue. Retry failed posts in a second pass after the primary run.
- If Claude returns malformed JSON, apply a JSON repair pass before raising a parse error.

**Output:** Structured post-level JSON (see OUTPUT-SCHEMA.md) ready for quality checks.

---

## Step 6a — Data Quality Checks

Before aggregation, validate all classified records:

1. **Schema enforcement** — all required fields present; enum values match allowed sets; taxonomy values match the locked active taxonomy.
2. **Confidence gate** — if Low-confidence rate exceeds 15% of total posts, halt aggregation and escalate to the project lead before proceeding.
3. **Distribution sanity checks:**
   - Any brand showing >80% Negative sentiment → flag as potential bot or spam wave.
   - Any single topic capturing >30% of posts → flag as over-broad topic definition.
   - Each platform must contribute 450–550 posts (±10% of target 500).
4. **Brand parity audit** — if T-Mobile US represents >50% of total posts, normalize all metrics to percentages; do not compare raw counts across brands.
5. **Ground truth spot-check** — manually review 30 posts (10 per platform) and compare to Claude output.

**Target accuracy benchmarks:**

| Dimension | Target Agreement |
|---|---|
| Sentiment | ≥ 85% |
| Intent | ≥ 80% |
| Emotion | ≥ 75% |
| Taxonomy (Pillar level) | ≥ 90% |

**Output:** Validated, quality-gated dataset ready for aggregation + QA report.

---

## Step 7 — Aggregation

Compute metrics at brand and taxonomy level:

- **Conversation share** — `(Posts mentioning Brand X / Total posts) × 100`, daily and 7-day aggregate
- **Net Sentiment Score (NSS)** — `% Positive − % Negative` per brand per day. NSS is the headline T-Mobile KPI.
- **Sentiment distribution** — Positive / Neutral / Negative percentages per brand
- **Intent distribution** — Complaint, Inquiry, Praise, Recommendation breakdown per brand
- **Complaint-to-Praise ratio** — key competitive benchmarking signal
- **Emotion heatmap** — 4×3 matrix (Frustration / Satisfaction / Confusion / Excitement × 3 brands)
- **Topic volume ranking** — top 10 topics per brand at each taxonomy level
- **Competitive gap analysis for T-Mobile:**
  - T-Mobile NSS minus Verizon NSS and AT&T NSS
  - T-Mobile Complaint rate vs. competitors
  - Positive gaps (T-Mobile outperforms) and negative gaps (T-Mobile underperforms) flagged separately

**Output:** Aggregated metrics dataset for dashboard visualization and trend analysis.

---

## Step 8 — Trend Analysis

Track **7-day trends** for each brand and topic:

- Day-over-day change and 7-day rolling average for each metric.
- **Trend alert** — flag any metric that moves more than 2 standard deviations from its rolling average.
- Volume fluctuations
- Sentiment shifts
- Complaint spikes
- **Emerging topic detection** — topics absent or below 1% of posts in the prior cycle but at or above 1% in the current cycle are tagged as `"Emerging"`.

**T-Mobile-specific trend modules:**
- **5G Perception Index** — aggregate sentiment for 5G-related topics, T-Mobile vs. competitors
- **Price Perception Score** — aggregate sentiment for the Pricing & Plans pillar per brand
- **Churn Signal Tracker** — volume in the Competitive Switching pillar for switch-away-from-T-Mobile intent

**Output:** Trend tables and flagged alerts for executive insights.

---

## Step 9 — Executive Dashboard

Visualize metrics and trends:

- Brand comparison charts (conversation share, NSS, complaint rate)
- Topic hierarchy tables ranked by volume
- Sentiment and intent breakdowns (7-day view)
- Complaint volume and emotion distribution
- Competitive gap summary: T-Mobile vs. AT&T Mobility vs. Verizon
- Emerging topic alerts

**Claude-generated executive brief** (published with each dashboard cycle):
1. Top 3 T-Mobile complaints this week (volume + sentiment context)
2. Top 3 emerging topics across all brands (with growth rate)
3. Competitive sentiment gap narrative
4. Emotion signal summary
5. 2–3 strategic recommendations for T-Mobile leadership

Supports leadership decisions with actionable, clear insights.

**Output:** **Executive social listening dashboard** for **T-Mobile US** benchmarked against **AT&T Mobility** and **Verizon**, published every Monday.

---

## Pipeline Schedule & Governance

- **Execution cadence:** Weekly, every Sunday at 02:00 UTC.
- **Dashboard publish deadline:** Every Monday morning.
- **Mandatory human gates:** (1) Taxonomy approval before Step 6; (2) Insight quality review before dashboard publish.
- **All other steps are fully automated.**
- Every pipeline run generates an **audit log** recording: run timestamp, taxonomy version used, total posts processed, classification success rate, QA flag counts, and the approver identity.
- Records are **immutable** once written with a `pipeline_run_id`. Corrections are appended as new records with a `supersedes` reference — never in-place edits.

---

## Notes

- All outputs maintain a **consistent schema** (see OUTPUT-SCHEMA.md) to support analytics pipelines.
- Noise filtering and governance ensure **taxonomy stability** over time (see TAXONOMY-VERSIONING.md).
- Claude operates within a **prompt-engineered framework** with a locked taxonomy and enumerated label sets for reliable, reproducible classification.
- The taxonomy is locked per cycle. Dynamic mid-cycle updates are prohibited as they cause classification inconsistency and break trend continuity.
