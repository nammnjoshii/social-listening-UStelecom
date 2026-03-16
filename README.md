# U.S. Telecom Social Listening Intelligence Dashboard

> **Client:** T-Mobile US &nbsp;|&nbsp; **Competitors:** AT&T Mobility, Verizon

An AI-powered social listening pipeline that collects, classifies, and visualizes customer conversations about major U.S. telecom providers — surfaced through an executive-grade Streamlit dashboard.

---

## Overview

This system ingests social media posts from **Instagram, Reddit, and X (Twitter)**, runs them through a Claude-powered NLP pipeline, and produces a real-time executive dashboard comparing **T-Mobile US** against its competitors on sentiment, complaints, topics, and emotional signals.

| Dimension | Detail |
|---|---|
| **Data sources** | Instagram · Reddit · X (Twitter) |
| **Dataset size** | 1,500 posts (500 per platform, stratified) |
| **Time window** | Last 7 days |
| **Brands tracked** | T-Mobile US · Verizon · AT&T Mobility |
| **Intelligence model** | Claude (Anthropic) |
| **Dashboard** | Streamlit + Plotly |
| **Storage** | SQLite (local, zero-config) |

---

## Dashboard

The executive dashboard provides a side-by-side comparison of all three brands across:

- **Conversation share** — who owns the social conversation
- **Sentiment distribution** — Positive / Neutral / Negative breakdown
- **Net Sentiment Score (NSS)** — headline competitive KPI
- **Intent breakdown** — Complaint · Inquiry · Praise · Recommendation
- **Emotion signals** — Frustration · Satisfaction · Confusion · Excitement
- **Topic hierarchy** — Pillar → Category → Theme → Topic drill-down
- **7-day trend charts** — daily movement across all key metrics

---

## Analytics Framework

### Topic Taxonomy

Customer discussions are structured into a four-level hierarchy:

```
Pillar → Category → Theme → Topic
```

Example:

| Pillar | Category | Theme | Topic |
|---|---|---|---|
| Network Performance | Coverage | Urban Coverage | Signal loss in subway |
| Customer Experience | Support | Call Center | Long wait times |
| Pricing & Plans | Billing | Billing Transparency | Unexpected charges |

### Sentiment, Intent & Emotion Labels

| Dimension | Labels |
|---|---|
| **Sentiment** | Positive · Neutral · Negative |
| **Intent** | Complaint · Inquiry · Praise · Recommendation |
| **Emotion** | Frustration · Satisfaction · Confusion · Excitement |

---

## Project Structure

```
.
├── app/
│   └── dashboard.py          # Streamlit executive dashboard
├── src/
│   ├── pipeline.py           # End-to-end pipeline orchestrator
│   ├── ingest.py             # Social media data collection
│   ├── clean.py              # Text normalization & deduplication
│   ├── brand.py              # Brand entity recognition
│   ├── classify.py           # Claude classification (sentiment/intent/emotion/topic)
│   ├── aggregate.py          # Metrics aggregation & trend computation
│   ├── validate.py           # Schema & confidence validation
│   ├── db.py                 # SQLite read/write helpers
│   ├── models.py             # Pydantic data models
│   ├── config.py             # Environment config
│   └── insights.py           # Executive insight generation
├── sql/
│   ├── schema.sql            # Core database schema
│   └── experiment_schema.sql # Platform experiment tables
├── data/
│   └── telecom.db            # SQLite database (pipeline output)
├── tests/                    # Pytest test suite
├── skills/                   # Domain reference documentation
├── versions/                 # Dashboard version snapshots
├── ARCHITECTURE.md           # System design
├── WORKFLOW.md               # Step-by-step pipeline workflow
├── CLAUDE.md                 # Claude prompt engineering guide
├── OUTPUT-SCHEMA.md          # Canonical output schema
└── requirements.txt          # Python dependencies
```

---

## Quick Start

### 1. Clone & install dependencies

```bash
git clone https://github.com/nammnjoshii/social-listening-UStelecom.git
cd social-listening-UStelecom
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Add your CLAUDE_API_KEY to .env
```

### 3. Run the pipeline

```bash
python -m src.pipeline
```

### 4. Launch the dashboard

```bash
python -m streamlit run app/dashboard.py
```

The dashboard opens at `http://localhost:8501`.

---

## Pipeline Workflow

```
Social Media Collection (Instagram · Reddit · X)
         │
         ▼
  Preprocessing & Noise Filtering
         │
         ▼
   Stratified Sampling (500 posts/platform)
         │
         ▼
   Brand Entity Recognition
         │
         ▼
     Claude Intelligence Layer
  ┌──────────────┬──────────────┐
  │Topic Discovery│  Sentiment   │
  │  & Taxonomy   │   Analysis   │
  │ Construction  │              │
  ├──────────────┼──────────────┤
  │   Intent      │   Emotion    │
  │  Detection    │  Extraction  │
  └──────────────┴──────────────┘
         │
         ▼
  Aggregation & Trend Engine
         │
         ▼
   Executive Dashboard
```

---

## Output Schema

Each classified post is stored as a structured JSON record:

```json
{
  "post_id": "string",
  "platform": "Instagram | Reddit | X",
  "brand": "T-Mobile US | Verizon | AT&T Mobility",
  "sentiment": "Positive | Neutral | Negative",
  "intent": "Complaint | Inquiry | Praise | Recommendation",
  "emotion": "Frustration | Satisfaction | Confusion | Excitement",
  "pillar": "string",
  "category": "string",
  "theme": "string",
  "topic": "string",
  "confidence": "High | Medium | Low",
  "pipeline_run_id": "string",
  "taxonomy_version": "v1.0.0"
}
```

Full schema definition: [OUTPUT-SCHEMA.md](OUTPUT-SCHEMA.md)

---

## Documentation

| Document | Description |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design and component overview |
| [WORKFLOW.md](WORKFLOW.md) | Step-by-step pipeline workflow |
| [CLAUDE.md](CLAUDE.md) | Claude prompt engineering strategy |
| [OUTPUT-SCHEMA.md](OUTPUT-SCHEMA.md) | Canonical output schema with field definitions |
| [skills/TAXONOMY.md](skills/TAXONOMY.md) | Topic taxonomy reference |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Intelligence | Claude (Anthropic) |
| Data models | Pydantic v2 |
| Data processing | Pandas · NumPy |
| Dashboard | Streamlit · Plotly |
| Storage | SQLite |
| NLP utilities | langdetect · datasketch |
| Testing | Pytest |

---

## License

Private — Nammn AI Practice. All rights reserved.
