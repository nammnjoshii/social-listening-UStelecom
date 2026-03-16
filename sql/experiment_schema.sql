-- Platform experiment results — created by src/experiment.py
-- Tracks per-platform quality scores so trends can be monitored across runs.

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS platform_experiment_results (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_run_id      TEXT    NOT NULL,
    pipeline_run_id        TEXT    NOT NULL,
    platform               TEXT    NOT NULL,
    post_count             INTEGER NOT NULL,
    snr_pct                REAL    NOT NULL,
    complaint_rate_pct     REAL    NOT NULL,
    topic_diversity_score  REAL    NOT NULL,
    sentiment_clarity_pct  REAL    NOT NULL,
    composite_score        REAL    NOT NULL,
    rank                   INTEGER NOT NULL,
    recommended_allocation INTEGER NOT NULL,
    computed_at            TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (experiment_run_id, platform)
);

CREATE INDEX IF NOT EXISTS idx_experiment_run
    ON platform_experiment_results (experiment_run_id, rank);
