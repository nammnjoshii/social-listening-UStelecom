"""Pipeline orchestrator — runs the full end-to-end cycle.

Execution order (per WORKFLOW.md):
  1. Ingest → 2. Clean → 3. Brand tag → 4. Classify
  → 5. Validate → 6. Aggregate → 7. Insights → 8. Persist

Run:
    python -m src.pipeline
    python -m src.pipeline --dry-run     # skips DB writes and Claude calls
"""
from __future__ import annotations

import argparse
import logging
import uuid
from datetime import datetime, timezone

from rich.console import Console
from rich.table import Table

from src import aggregate, brand, classify, clean, db, ingest, insights, validate
from src.config import cfg

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
logger = logging.getLogger("pipeline")
console = Console()


def _preflight_credit_check() -> None:
    """Make a minimal 1-token test call to verify Claude credits are available.
    Raises CreditExhaustedError immediately if the account is out of credits.
    Called before ingestion to avoid wasting 10+ minutes collecting data.
    """
    import anthropic as _anthropic
    client = _anthropic.Anthropic(api_key=cfg.claude_api_key)
    try:
        client.messages.create(
            model=cfg.claude_model,
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )
    except _anthropic.BadRequestError as e:
        if "credit balance" in str(e).lower():
            raise classify.CreditExhaustedError(str(e))
    except Exception:
        # Network errors, auth issues, etc. — preflight is best-effort; don't block the run
        logger.warning("Preflight check encountered unexpected error — proceeding anyway", exc_info=True)


def run(
    dry_run: bool = False,
    experiment: bool = False,
    resume_run_id: str | None = None,
    resume_from: str | None = None,  # "clean" | "brand" | "classify"
    discover_topics: bool = False,
) -> str:
    run_id = resume_run_id if resume_run_id else str(uuid.uuid4())
    period_end = datetime.now(timezone.utc)
    from datetime import timedelta
    period_start = period_end - timedelta(days=cfg.lookback_days)

    console.rule(f"[bold blue]T-Mobile Social Listening Pipeline — run_id={run_id}")

    # ── Step 1: Log run start ─────────────────────────────────────────
    if not dry_run:
        db.log_run_start(run_id, prompt_version=cfg.prompt_version)

    # ── Step 1b: Preflight credit check ──────────────────────────────
    if not dry_run:
        try:
            _preflight_credit_check()
            console.print("  [dim]✓ Claude credit preflight passed")
        except classify.CreditExhaustedError as e:
            console.print(f"[bold red]PREFLIGHT FAILED: Claude credit balance is exhausted.")
            console.print("[yellow]Top up credits at https://console.anthropic.com and re-run.")
            logger.critical("Aborting pipeline — credit balance exhausted before ingestion: %s", e)
            return run_id

    # ── Step 2: Ingest ───────────────────────────────────────────────
    if resume_from in ("clean", "brand", "classify"):
        console.print(f"[cyan]Step 1/7 — Resuming from '{resume_from}' — loading raw_posts from DB...")
        raw_posts = db.get_raw_posts_for_run(run_id)
        console.print(f"  Loaded {len(raw_posts)} raw posts from DB")
    else:
        console.print("[cyan]Step 1/7 — Ingesting posts from all platforms...")
        raw_posts = ingest.collect_all(run_id)
        console.print(f"  Collected {len(raw_posts)} raw candidates")
        if not dry_run:
            written = db.write_raw_posts(raw_posts, run_id)
            console.print(f"  [dim]✓ Wrote {written} raw posts to DB")

    # ── Step 3: Clean & normalize ─────────────────────────────────────
    if resume_from in ("brand", "classify"):
        console.print(f"[cyan]Step 2/7 — Resuming from '{resume_from}' — loading cleaned_posts from DB...")
        clean_posts = db.get_cleaned_posts_for_run(run_id)
        filter_stats: dict = {}
        console.print(f"  Loaded {len(clean_posts)} cleaned posts from DB")
    else:
        console.print("[cyan]Step 2/7 — Cleaning & noise filtering...")
        clean_posts, filter_stats = clean.filter_posts(raw_posts)
        console.print(f"  {len(clean_posts)} posts after filtering | stats={filter_stats}")
        if not dry_run:
            written = db.write_cleaned_posts(clean_posts, run_id)
            console.print(f"  [dim]✓ Wrote {written} cleaned posts to DB")

    if len(clean_posts) < 100:
        logger.error("Insufficient posts after cleaning (%d) — aborting", len(clean_posts))
        return run_id

    # ── Step 4: Brand recognition ─────────────────────────────────────
    if resume_from == "classify":
        console.print("[cyan]Step 3/7 — Resuming from 'classify' — loading branded_posts from DB...")
        tagged_posts = db.get_branded_posts_for_run(run_id)
        unresolved: list = []
        console.print(f"  Loaded {len(tagged_posts)} branded posts from DB")
    else:
        console.print("[cyan]Step 3/7 — Brand entity recognition...")
        tagged_posts, unresolved = brand.tag_posts(clean_posts)
        console.print(f"  {len(tagged_posts)} tagged | {len(unresolved)} unresolved (excluded)")
        if not dry_run:
            written = db.write_branded_posts(tagged_posts, run_id)
            console.print(f"  [dim]✓ Wrote {written} branded posts to DB")

    # ── Step 4b: Resume filter — skip already-classified posts ────────
    if not dry_run:
        already_done = db.get_classified_post_ids()
        if already_done:
            before = len(tagged_posts)
            tagged_posts = [p for p in tagged_posts if p.post_id not in already_done]
            skipped = before - len(tagged_posts)
            console.print(f"  [dim]Resume: {skipped} posts already classified — skipping, {len(tagged_posts)} remaining")
            logger.info("Resume filter: %d already classified, %d remaining", skipped, len(tagged_posts))
        else:
            console.print("  [dim]Resume: no prior classifications found — classifying all posts")

    # ── Step 4b: BERTopic corpus-level topic discovery (optional) ────
    if discover_topics and tagged_posts:
        console.print("[cyan]Step 3b — Running BERTopic topic discovery on corpus...")
        from src.topic_discovery import discover_topics as run_bertopic, print_topic_report
        texts = [p.normalized_text for p in tagged_posts]
        discovered = run_bertopic(texts, label_with_claude=not dry_run)
        print_topic_report(discovered)

    # ── Step 5: Classify ─────────────────────────────────────────────
    console.print("[cyan]Step 4/7 — Claude classification (async batches)...")
    if dry_run:
        console.print("  [yellow]DRY RUN — skipping Claude API calls")
        classified = []
    else:
        def _persist_batch(batch_results):
            persistable = [r for r in batch_results if r.classification_status in ("success", "flagged")]
            if persistable:
                db.write_posts(persistable, run_id)
                console.print(f"  [dim]✓ Batch saved — {len(persistable)} posts written to DB")

        try:
            classified = classify.classify_posts(tagged_posts, run_id, on_batch_complete=_persist_batch)
        except classify.CreditExhaustedError as e:
            console.print(
                f"[yellow]Credit exhausted mid-run — {e.classified_so_far} posts classified "
                "before credits ran out. All completed batches already saved to DB."
            )
            console.print("[yellow]Top up credits and re-run — resume filter will skip already-classified posts.")
            logger.warning("Partial run due to credit exhaustion: %d posts classified", e.classified_so_far)
            classified = []
    console.print(f"  {len(classified)} records classified")

    # ── Step 5b: Platform experiment (optional) ───────────────────────
    if experiment and classified:
        console.print("[cyan]Step 4b — Running platform signal quality experiment...")
        from src import experiment as exp_module
        scores = exp_module.run_experiment(classified, run_id)
        exp_module.print_experiment_report(scores)
        if not dry_run:
            db.write_experiment_scores(scores)

    # ── Step 6: Quality checks ────────────────────────────────────────
    console.print("[cyan]Step 5/7 — Running quality checks...")
    try:
        qc_stats = validate.run_quality_checks(classified) if classified else {}
        console.print(f"  QC passed — low_confidence={qc_stats.get('low_confidence_pct', 0):.1f}%")
    except validate.QualityGateError as e:
        console.print(f"  [bold red]QUALITY GATE HALT: {e}")
        logger.critical("Pipeline halted at quality gate: %s", e)
        return run_id

    # ── Step 7: Persist classified posts ─────────────────────────────
    # Already written incrementally per batch via on_batch_complete callback.
    # INSERT OR IGNORE ensures idempotency if pipeline is re-run.

    # ── Step 8: Aggregate metrics ─────────────────────────────────────
    console.print("[cyan]Step 6/7 — Aggregating metrics...")
    brand_metrics = aggregate.compute_brand_metrics(classified, run_id, period_start, period_end)
    top_topics_df = aggregate.compute_top_topics(classified, run_id)
    daily_trends_df = aggregate.compute_daily_trends(classified, run_id)
    comp_gap = aggregate.competitive_gap(brand_metrics)

    _print_metrics_table(brand_metrics, comp_gap)

    if not dry_run:
        db.write_brand_metrics(brand_metrics)
        if not top_topics_df.empty:
            _write_top_topics(top_topics_df, run_id)
        if not daily_trends_df.empty:
            _write_daily_trends(daily_trends_df, run_id)

    # ── Step 9: Executive insights ────────────────────────────────────
    console.print("[cyan]Step 7/7 — Generating executive insights...")
    if dry_run or not brand_metrics:
        console.print("  [yellow]Skipping insight generation (dry run or no metrics)")
    else:
        insight = insights.generate_insight(brand_metrics, top_topics_df, comp_gap, run_id)
        db.write_executive_insight(insight)
        console.print("  Executive brief generated and saved")
        for rec in insight.strategic_recommendations:
            console.print(f"    [green]→ {rec}")

    # ── Finalize run ──────────────────────────────────────────────────
    success_count = sum(1 for r in classified if r.classification_status in ("success", "flagged"))
    failed_count = sum(1 for r in classified if r.classification_status == "failed")
    flagged_count = sum(1 for r in classified if r.classification_status == "flagged")

    run_stats = {
        "post_count": len(classified),
        "classified_count": success_count,
        "flagged_count": flagged_count,
        "failed_count": failed_count,
        "low_confidence_pct": qc_stats.get("low_confidence_pct", 0),
    }
    if not dry_run:
        db.log_run_complete(run_id, run_stats)

    console.rule("[bold green]Pipeline complete")
    console.print(f"run_id={run_id}")
    return run_id


def _print_metrics_table(brand_metrics, comp_gap) -> None:
    table = Table(title="Brand Metrics Summary", show_lines=True)
    table.add_column("Brand", style="bold")
    table.add_column("Posts")
    table.add_column("Conv Share %")
    table.add_column("NSS")
    table.add_column("Complaint %")
    table.add_column("Frustration %")

    for m in brand_metrics:
        nss_style = "green" if m.net_sentiment_score > 0 else "red"
        table.add_row(
            m.brand,
            str(m.total_posts),
            f"{m.conversation_share_pct:.1f}%",
            f"[{nss_style}]{m.net_sentiment_score:+.1f}[/{nss_style}]",
            f"{m.complaint_pct:.1f}%",
            f"{m.frustration_pct:.1f}%",
        )
    console.print(table)

    if comp_gap:
        console.print("\n[bold]Competitive Gap (T-Mobile US vs. competitors):")
        for competitor, gap in comp_gap.items():
            nss_gap = gap["nss_gap"]
            style = "green" if nss_gap > 0 else "red"
            console.print(
                f"  vs {competitor}: NSS gap [{style}]{nss_gap:+.1f}[/{style}], "
                f"Complaint gap {gap['complaint_rate_gap']:+.1f}%"
            )


def _write_top_topics(df, run_id: str) -> None:
    from src.db import get_conn
    rows = [
        (
            run_id, str(row.brand), str(row.pillar), str(row.category),
            str(row.theme), str(row.topic), int(row.post_count),
            float(row.topic_share_pct), int(bool(row.is_emerging)), int(row.rank),
        )
        for row in df.itertuples(index=False)
    ]
    sql = """
        INSERT OR IGNORE INTO top_topics
            (pipeline_run_id, brand, pillar, category, theme, topic,
             post_count, topic_share_pct, is_emerging, rank)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """
    with get_conn() as conn:
        conn.executemany(sql, rows)


def _write_daily_trends(df, run_id: str) -> None:
    from src.db import get_conn

    def _safe_float(v):
        try:
            f = float(v)
            return f if f == f else None  # NaN check
        except (TypeError, ValueError):
            return None

    rows = [
        (
            run_id, str(row.date), str(row.brand), int(row.post_count),
            _safe_float(row.conversation_share_pct),
            _safe_float(row.net_sentiment_score),
            _safe_float(row.complaint_pct),
            _safe_float(row.praise_pct),
            _safe_float(row.frustration_pct),
            _safe_float(row.satisfaction_pct),
        )
        for row in df.itertuples(index=False)
    ]
    sql = """
        INSERT OR IGNORE INTO daily_trends
            (pipeline_run_id, trend_date, brand, post_count,
             conversation_share_pct, net_sentiment_score,
             complaint_pct, praise_pct, frustration_pct, satisfaction_pct)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """
    with get_conn() as conn:
        conn.executemany(sql, rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the telecom social listening pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Skip API calls and DB writes")
    parser.add_argument("--experiment", action="store_true", help="Run platform signal quality experiment after classification")
    parser.add_argument("--resume-run-id", type=str, default=None, help="Run ID to resume (must exist in pipeline_runs table)")
    parser.add_argument("--resume-from", choices=["clean", "brand", "classify"], default=None, help="Stage to resume from. Requires --resume-run-id.")
    parser.add_argument("--discover-topics", action="store_true", help="Run BERTopic unsupervised topic discovery before classification")
    args = parser.parse_args()
    run(
        dry_run=args.dry_run,
        experiment=args.experiment,
        resume_run_id=args.resume_run_id,
        resume_from=args.resume_from,
        discover_topics=args.discover_topics,
    )
