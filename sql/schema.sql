-- U.S. Telecom Social Listening — SQLite Schema
-- Run once to initialize the local database.
-- SQLite file is stored at the path set in DB_PATH (.env).

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ─────────────────────────────────────────────
-- Raw staging table (pre-cleaning)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw_posts (
    post_id              TEXT    NOT NULL,
    platform             TEXT    NOT NULL,
    timestamp            TEXT    NOT NULL,
    raw_text             TEXT    NOT NULL,
    author_id            TEXT    NOT NULL DEFAULT '[ANONYMIZED]',
    engagement_metrics   TEXT    NOT NULL DEFAULT '{}',   -- stored as JSON string
    brand_keywords_matched TEXT  NOT NULL DEFAULT '[]',   -- stored as JSON string
    ingested_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    pipeline_run_id      TEXT    NOT NULL,
    PRIMARY KEY (post_id, pipeline_run_id)
);

-- ─────────────────────────────────────────────
-- Cleaned posts (post-filtering, pre-brand-tag)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cleaned_posts (
    post_id          TEXT    NOT NULL,
    pipeline_run_id  TEXT    NOT NULL,
    platform         TEXT    NOT NULL,
    timestamp        TEXT    NOT NULL,
    normalized_text  TEXT    NOT NULL,
    is_filtered      INTEGER NOT NULL DEFAULT 0,   -- 0=kept, 1=removed by filter
    filter_applied   TEXT,                          -- NULL if kept, reason if filtered
    cleaned_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (post_id, pipeline_run_id)
);

-- ─────────────────────────────────────────────
-- Brand-tagged posts (post-brand-recognition, pre-classify)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS branded_posts (
    post_id          TEXT    NOT NULL,
    pipeline_run_id  TEXT    NOT NULL,
    platform         TEXT    NOT NULL,
    timestamp        TEXT    NOT NULL,
    normalized_text  TEXT    NOT NULL,
    brands           TEXT    NOT NULL DEFAULT '[]',  -- JSON array string
    brand_confidence TEXT    NOT NULL,
    is_multi_brand   INTEGER NOT NULL DEFAULT 0,     -- 0=False, 1=True
    tagged_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (post_id, pipeline_run_id)
);

-- ─────────────────────────────────────────────
-- Classified posts (one row per brand per post)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS posts (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id              TEXT    NOT NULL,
    pipeline_run_id      TEXT    NOT NULL,
    platform             TEXT    NOT NULL,
    timestamp            TEXT    NOT NULL,
    normalized_text      TEXT    NOT NULL,
    brand                TEXT    NOT NULL,
    brand_confidence     TEXT    NOT NULL,
    is_multi_brand       INTEGER NOT NULL DEFAULT 0,      -- 0=False, 1=True
    pillar               TEXT,
    category             TEXT,
    theme                TEXT,
    topic                TEXT,
    sentiment            TEXT,
    intent               TEXT,
    emotion              TEXT,
    confidence           TEXT    NOT NULL,
    classification_status TEXT   NOT NULL,
    taxonomy_version     TEXT    NOT NULL,
    schema_version       TEXT    NOT NULL,
    supersedes           TEXT,
    classified_at        TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (post_id, brand, pipeline_run_id)
);

-- ─────────────────────────────────────────────
-- Aggregated brand metrics (one row per brand per run)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS brand_metrics (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_run_id          TEXT    NOT NULL,
    taxonomy_version         TEXT    NOT NULL,
    schema_version           TEXT    NOT NULL,
    period_start             TEXT    NOT NULL,
    period_end               TEXT    NOT NULL,
    brand                    TEXT    NOT NULL,
    total_posts              INTEGER NOT NULL,
    conversation_share_pct   REAL,
    positive_pct             REAL,
    neutral_pct              REAL,
    negative_pct             REAL,
    net_sentiment_score      REAL,
    complaint_pct            REAL,
    inquiry_pct              REAL,
    praise_pct               REAL,
    recommendation_pct       REAL,
    complaint_to_praise_ratio REAL,
    frustration_pct          REAL,
    satisfaction_pct         REAL,
    confusion_pct            REAL,
    excitement_pct           REAL,
    computed_at              TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (pipeline_run_id, brand)
);

-- ─────────────────────────────────────────────
-- Daily trend snapshots
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_trends (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_run_id        TEXT    NOT NULL,
    trend_date             TEXT    NOT NULL,
    brand                  TEXT    NOT NULL,
    post_count             INTEGER NOT NULL DEFAULT 0,
    conversation_share_pct REAL,
    net_sentiment_score    REAL,
    complaint_pct          REAL,
    praise_pct             REAL,
    frustration_pct        REAL,
    satisfaction_pct       REAL,
    UNIQUE (pipeline_run_id, trend_date, brand)
);

-- ─────────────────────────────────────────────
-- Top topics per brand per run
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS top_topics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_run_id TEXT    NOT NULL,
    brand           TEXT    NOT NULL,
    pillar          TEXT    NOT NULL,
    category        TEXT    NOT NULL,
    theme           TEXT    NOT NULL,
    topic           TEXT    NOT NULL,
    post_count      INTEGER NOT NULL,
    topic_share_pct REAL,
    is_emerging     INTEGER NOT NULL DEFAULT 0,
    rank            INTEGER NOT NULL,
    UNIQUE (pipeline_run_id, brand, topic)
);

-- ─────────────────────────────────────────────
-- Executive insight JSON per run
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS executive_insights (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_run_id TEXT    NOT NULL UNIQUE,
    generated_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    insight_json    TEXT    NOT NULL   -- stored as JSON string
);

-- ─────────────────────────────────────────────
-- Pipeline run audit log
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id               TEXT    PRIMARY KEY,
    started_at           TEXT    NOT NULL,
    completed_at         TEXT,
    prompt_version       TEXT    NOT NULL,
    taxonomy_version     TEXT    NOT NULL,
    schema_version       TEXT    NOT NULL,
    claude_model         TEXT    NOT NULL,
    post_count           INTEGER,
    classified_count     INTEGER,
    flagged_count        INTEGER,
    failed_count         INTEGER,
    low_confidence_pct   REAL,
    avg_confidence       TEXT,
    taxonomy_approver    TEXT,
    status               TEXT    NOT NULL DEFAULT 'running'
);

-- ─────────────────────────────────────────────
-- Indexes
-- ─────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_posts_brand       ON posts (brand);
CREATE INDEX IF NOT EXISTS idx_posts_platform    ON posts (platform);
CREATE INDEX IF NOT EXISTS idx_posts_sentiment   ON posts (sentiment);
CREATE INDEX IF NOT EXISTS idx_posts_timestamp   ON posts (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_posts_run_id      ON posts (pipeline_run_id);
CREATE INDEX IF NOT EXISTS idx_daily_trends_run  ON daily_trends (pipeline_run_id, trend_date);
CREATE INDEX IF NOT EXISTS idx_top_topics_run    ON top_topics (pipeline_run_id, brand, rank);
CREATE INDEX IF NOT EXISTS idx_cleaned_posts_run ON cleaned_posts (pipeline_run_id);
CREATE INDEX IF NOT EXISTS idx_branded_posts_run ON branded_posts (pipeline_run_id);
