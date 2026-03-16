# Deployment Guide — U.S. Telecom Social Listening

This guide provides **step-by-step instructions to deploy the Claude Code social listening pipeline**, from ingestion to executive dashboard delivery.

> **Client:** T-Mobile US | **Competitors:** AT&T Mobility, Verizon

---

## 1. Requirements

### Software

- **Python 3.11+** (required for full type annotation and async performance)
- **Scheduler:** Apache Airflow, Cron, or equivalent
- **Claude API access** — model: `claude-sonnet-4-6` (pin this version; do not use `latest`)
- **Database / Storage:** PostgreSQL (recommended) or equivalent relational store for raw, processed, and aggregated data

### Platform API Access

| Platform | API | Notes |
|---|---|---|
| Instagram | Instagram Graph API | Requires Business account approval; query hashtags and brand @mentions |
| Reddit | Reddit Data API v2 (or PRAW) | Rate limit: 100 requests/minute on free tier |
| X (Twitter) | X API v2 (Basic or Pro tier) | Recent search endpoint; `start_time` parameter for 7-day window |

### Environment Variables

| Variable | Description |
|---|---|
| `CLAUDE_API_KEY` | Anthropic API key for Claude classification calls |
| `DB_CONNECTION` | PostgreSQL connection string: `postgresql://user:password@host:port/dbname` |
| `INSTAGRAM_ACCESS_TOKEN` | Instagram Graph API long-lived access token |
| `REDDIT_CLIENT_ID` | Reddit API OAuth client ID |
| `REDDIT_CLIENT_SECRET` | Reddit API OAuth client secret |
| `REDDIT_USER_AGENT` | Reddit API user agent string |
| `TWITTER_BEARER_TOKEN` | X API v2 Bearer Token for recent search |

**Secrets management:** Store all secrets in a secrets manager (AWS Secrets Manager, HashiCorp Vault, or equivalent). Never hardcode API keys in source files or commit them to version control.

---

## 2. Pipeline Schedule

| Event | Schedule | Notes |
|---|---|---|
| Data ingestion | Sunday 02:00 UTC | Collects 7-day rolling window ending at run time |
| Classification + quality checks | Sunday 03:00 UTC | Runs after ingestion completes |
| Aggregation + insight generation | Sunday 05:00 UTC | Runs after classification completes |
| Dashboard publish | Monday 07:00 UTC | Published at start of business week |

**Human gates (mandatory before publish):**
1. Taxonomy approval — before classification begins (cycle Day 1)
2. Insight quality review — before dashboard publish (Monday morning)

---

## 3. Deployment Steps

### Step 1 — Ingestion

- Run scheduled jobs to **collect posts** from all three platforms.
- Collect up to **1,000 candidate posts per platform** (2× the 500 target) to allow for cleaning attrition.
- Apply brand keyword filters at ingestion using the canonical alias corpus from `BRAND-ENTITY-RECOGNITION.md`.
- Store raw posts in the staging database with: `platform`, `post_id`, `author_id` (anonymized), `timestamp`, `raw_text`, `engagement_metrics`, `brand_keywords_matched`.

### Step 2 — Cleaning & Normalization

- Deduplicate (SHA-256 + MinHash LSH with Jaccard ≥ 0.85).
- Remove spam, ads, and promotional content per `NOISE-FILTERING.md`.
- Text normalization: lowercase → strip URLs → **expand hashtags** (remove `#`, keep word) → replace @mentions with `[USER]` → normalize Unicode → collapse whitespace.
- Apply language filter (English only via `fastText`) and minimum-length filter (≥15 words).
- Target: 500 clean posts per platform.

### Step 3 — Brand Recognition

- Map mentions to canonical brands using alias dictionary from `BRAND-ENTITY-RECOGNITION.md`.
- Apply word-boundary regex; case-insensitive matching.
- Assign `brand_confidence` (High/Medium/Low) and set `is_multi_brand` flag.
- Run Claude validation pass for Low-confidence detections only.
- Validate at least one brand per post; exclude unresolved posts.

### Step 4 — Taxonomy Creation & Lock (Human Gate)

- Run Claude topic discovery on a stratified 300-post sample (100/platform).
- Validate taxonomy structure: 4 levels, no duplicates, max 6 Pillars.
- **Await project lead approval before proceeding.** Do not classify until approved.
- Lock taxonomy; assign `taxonomy_version` tag (e.g., `v1.0.0 — 2026-03-15`).

### Step 5 — Claude Classification

- Call Claude for each post using the unified classification prompt (all 5 labels in one call).
- Pin model version: `claude-sonnet-4-6`.
- Process in batches of 50; async concurrency limit of 5 simultaneous requests.
- Implement exponential backoff: 2s → 4s → 8s → 16s on rate limit errors.
- On repeated failure, mark `classification_status: "failed"` and continue. Retry failed posts in a second pass.
- Ensure all JSON outputs conform to `OUTPUT-SCHEMA.md`.

### Step 6 — Output Validation & Quality Checks

- Run all checks defined in `DATA-QUALITY-CHECKS.md`:
  - Schema validation
  - Taxonomy label verification
  - Sentiment/intent/emotion enum enforcement
  - Confidence gate (halt if Low-confidence rate >15%)
  - Distribution sanity checks
- Log all anomalies with `pipeline_run_id` for traceability.

### Step 7 — Aggregation & Trend Analysis

- Compute metrics:
  - Conversation share per brand (daily + 7-day aggregate)
  - Net Sentiment Score (NSS): `% Positive − % Negative` per brand per day
  - Intent distribution; Complaint-to-Praise ratio
  - Emotion heatmap (4×3 matrix)
  - Topic volume ranking (top 10 per brand)
  - 7-day trend deltas; flag metrics >2σ from rolling mean
  - Competitive gap: T-Mobile NSS vs. Verizon NSS and AT&T NSS
  - Emerging topic detection (absent or <1% in prior cycle, ≥1% in current)

### Step 8 — Executive Insight Generation

- Compile aggregated metrics into a structured briefing JSON.
- Run Claude executive insight prompt (see `EXECUTIVE-INSIGHT-GENERATION.md`).
- Verify all insight claims against underlying aggregated data.
- **Await insight quality review before publishing.** (Human gate)

### Step 9 — Dashboard Integration

- Push validated aggregated metrics and executive brief to the dashboard layer.
- Visualize: brand comparison charts, NSS trends, topic hierarchy tables, emotion heatmap, complaint volume, emerging topics.
- Dashboard platform options: Power BI, Tableau, Streamlit (connect to PostgreSQL aggregated metrics store).

---

## 4. Example Environment Setup (Linux / macOS)

```bash
# Set secrets (use secrets manager in production)
export CLAUDE_API_KEY="your_claude_api_key"
export DB_CONNECTION="postgresql://user:password@host:5432/telecom_listening"
export TWITTER_BEARER_TOKEN="your_twitter_bearer_token"
export REDDIT_CLIENT_ID="your_reddit_client_id"
export REDDIT_CLIENT_SECRET="your_reddit_client_secret"
export REDDIT_USER_AGENT="telecom-listening/1.0"
export INSTAGRAM_ACCESS_TOKEN="your_instagram_token"

# Run pipeline steps
python src/ingest_posts.py --since-days 7
python src/clean_posts.py
python src/brand_recognition.py
# [HUMAN GATE: approve taxonomy]
python src/claude_classify.py --model claude-sonnet-4-6 --batch-size 50 --concurrency 5
python src/validate_outputs.py
python src/aggregate_metrics.py
python src/generate_insights.py
# [HUMAN GATE: approve insights]
python src/push_dashboard.py
```

---

## 5. Best Practices

- **Pin Claude model version:** Always specify `claude-sonnet-4-6` explicitly. Never use `latest` — model updates can change classification behavior and break trend continuity.
- **Versioning:** Track `taxonomy_version`, `schema_version`, and `prompt_version` for every pipeline run. Store in the run audit log.
- **Automated scheduling:** Use Airflow DAG or cron with dependency chaining so each step only runs after the prior step succeeds.
- **Monitoring & alerts:** Track pipeline health, failed jobs, Low-confidence rate, and drift detection. See `TREND-ANALYSIS.md` for alert threshold definitions.
- **Prompt management:** Store Claude prompts in `CLAUDE-PROMPT-LIBRARY.md` and version them with semantic version tags. Never modify a prompt mid-cycle.
- **Sandbox testing:** Deploy initially on a sandbox environment with a 150-post sample (50/platform) to validate sampling, classification, and aggregation before full production run.
- **Cost monitoring:** Track Claude API token usage per `pipeline_run_id`. Standard cycle: ~1.4M input + ~225K output tokens.
