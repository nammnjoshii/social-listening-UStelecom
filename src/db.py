"""SQLite connection and write helpers.

Data is stored locally in a single .db file (no server required).
The file path is set via DB_PATH in .env (defaults to data/telecom.db).
"""
from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from src.config import cfg
from src.models import AggregatedMetrics, ExecutiveInsight, PlatformScore, PostClassification

logger = logging.getLogger(__name__)


def _db_path() -> Path:
    path = Path(cfg.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _ts(dt: datetime | None) -> str | None:
    """Convert datetime to ISO string for SQLite storage."""
    if dt is None:
        return None
    return dt.isoformat()


@contextmanager
def get_conn() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(_db_path(), detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create all tables from schema.sql (and experiment_schema.sql) if they don't exist."""
    schema_path = Path(__file__).parent.parent / "sql" / "schema.sql"
    with get_conn() as conn:
        conn.executescript(schema_path.read_text())

    exp_schema_path = Path(__file__).parent.parent / "sql" / "experiment_schema.sql"
    if exp_schema_path.exists():
        with get_conn() as conn:
            conn.executescript(exp_schema_path.read_text())

    logger.info("Database initialised at %s", _db_path())


def write_posts(records: list[PostClassification], run_id: str) -> int:
    """Insert classified post records (one row per brand). Returns count written."""
    if not records:
        return 0

    rows = []
    for r in records:
        for brand in r.brands:
            rows.append((
                r.post_id, run_id, r.platform,
                _ts(r.timestamp), r.normalized_text,
                brand, r.brand_confidence, int(r.is_multi_brand),
                r.pillar, r.category, r.theme, r.topic,
                r.sentiment, r.intent, r.emotion,
                r.confidence, r.classification_status,
                r.taxonomy_version, r.schema_version, r.supersedes,
            ))

    sql = """
        INSERT OR IGNORE INTO posts (
            post_id, pipeline_run_id, platform, timestamp, normalized_text,
            brand, brand_confidence, is_multi_brand,
            pillar, category, theme, topic,
            sentiment, intent, emotion,
            confidence, classification_status,
            taxonomy_version, schema_version, supersedes
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    with get_conn() as conn:
        conn.executemany(sql, rows)
        written = conn.total_changes

    logger.info("Wrote %d post-brand rows to posts table", written)
    return written


def write_brand_metrics(metrics: list[AggregatedMetrics]) -> None:
    rows = [(
        m.pipeline_run_id, m.taxonomy_version, m.schema_version,
        _ts(m.period_start), _ts(m.period_end), m.brand, m.total_posts,
        m.conversation_share_pct, m.positive_pct, m.neutral_pct, m.negative_pct,
        m.net_sentiment_score, m.complaint_pct, m.inquiry_pct,
        m.praise_pct, m.recommendation_pct, m.complaint_to_praise_ratio,
        m.frustration_pct, m.satisfaction_pct, m.confusion_pct, m.excitement_pct,
    ) for m in metrics]

    sql = """
        INSERT OR REPLACE INTO brand_metrics (
            pipeline_run_id, taxonomy_version, schema_version,
            period_start, period_end, brand, total_posts,
            conversation_share_pct, positive_pct, neutral_pct, negative_pct,
            net_sentiment_score, complaint_pct, inquiry_pct,
            praise_pct, recommendation_pct, complaint_to_praise_ratio,
            frustration_pct, satisfaction_pct, confusion_pct, excitement_pct
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    with get_conn() as conn:
        conn.executemany(sql, rows)
    logger.info("Wrote %d brand metric rows", len(rows))


def write_executive_insight(insight: ExecutiveInsight) -> None:
    sql = """
        INSERT OR REPLACE INTO executive_insights (pipeline_run_id, generated_at, insight_json)
        VALUES (?, ?, ?)
    """
    with get_conn() as conn:
        conn.execute(sql, (
            insight.pipeline_run_id,
            _ts(insight.generated_at),
            json.dumps(insight.model_dump(), default=str),
        ))
    logger.info("Wrote executive insight for run %s", insight.pipeline_run_id)


def write_experiment_scores(scores: list[PlatformScore]) -> None:
    """Write platform experiment results to platform_experiment_results table."""
    if not scores:
        return
    rows = [(
        s.experiment_run_id, s.pipeline_run_id, s.platform, s.post_count,
        s.snr_pct, s.complaint_rate_pct, s.topic_diversity_score,
        s.sentiment_clarity_pct, s.composite_score, s.rank,
        s.recommended_allocation, _ts(s.computed_at),
    ) for s in scores]

    sql = """
        INSERT OR REPLACE INTO platform_experiment_results (
            experiment_run_id, pipeline_run_id, platform, post_count,
            snr_pct, complaint_rate_pct, topic_diversity_score,
            sentiment_clarity_pct, composite_score, rank,
            recommended_allocation, computed_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """
    with get_conn() as conn:
        conn.executemany(sql, rows)
    logger.info("Wrote %d platform experiment score rows", len(rows))


def log_run_start(run_id: str, prompt_version: str) -> None:
    sql = """
        INSERT OR IGNORE INTO pipeline_runs
            (run_id, started_at, prompt_version, taxonomy_version,
             schema_version, claude_model, status)
        VALUES (?,?,?,?,?,?,'running')
    """
    with get_conn() as conn:
        conn.execute(sql, (
            run_id,
            _ts(datetime.now(timezone.utc)),
            prompt_version,
            cfg.taxonomy_version,
            cfg.schema_version,
            cfg.claude_model,
        ))


def log_run_complete(run_id: str, stats: dict) -> None:
    sql = """
        UPDATE pipeline_runs SET
            completed_at       = ?,
            post_count         = ?,
            classified_count   = ?,
            flagged_count      = ?,
            failed_count       = ?,
            low_confidence_pct = ?,
            status             = 'completed'
        WHERE run_id = ?
    """
    with get_conn() as conn:
        conn.execute(sql, (
            _ts(datetime.now(timezone.utc)),
            stats.get("post_count"),
            stats.get("classified_count"),
            stats.get("flagged_count"),
            stats.get("failed_count"),
            stats.get("low_confidence_pct"),
            run_id,
        ))
