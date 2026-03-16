# SQL Aggregation Patterns — U.S. Telecom Social Listening

Adapted from `sql-pro` skill. Covers PostgreSQL query patterns for computing dashboard metrics, trend data, and competitive analysis from the classified post dataset.

> **Client:** T-Mobile US | **Competitors:** AT&T Mobility, Verizon

---

## Schema Reference

All queries assume a `posts` table with the following key columns:

```sql
post_id          TEXT PRIMARY KEY,
pipeline_run_id  TEXT NOT NULL,
platform         TEXT NOT NULL,   -- 'Instagram' | 'Reddit' | 'X'
timestamp        TIMESTAMPTZ NOT NULL,
brand            TEXT NOT NULL,   -- one row per brand (exploded from multi-brand posts)
sentiment        TEXT,            -- 'Positive' | 'Neutral' | 'Negative'
intent           TEXT,            -- 'Complaint' | 'Inquiry' | 'Praise' | 'Recommendation'
emotion          TEXT,            -- 'Frustration' | 'Satisfaction' | 'Confusion' | 'Excitement'
pillar           TEXT,
category         TEXT,
theme            TEXT,
topic            TEXT,
confidence       NUMERIC(4,3),
classification_status TEXT,       -- 'classified' | 'flagged' | 'review_required'
taxonomy_version TEXT,
schema_version   TEXT
```

---

## 1. Recommended Indexes

Create these indexes before running any dashboard queries:

```sql
-- Primary filter axes
CREATE INDEX idx_posts_brand       ON posts (brand);
CREATE INDEX idx_posts_platform    ON posts (platform);
CREATE INDEX idx_posts_sentiment   ON posts (sentiment);
CREATE INDEX idx_posts_timestamp   ON posts (timestamp DESC);

-- Covering index for the most common trend query (brand + day + sentiment)
CREATE INDEX idx_posts_brand_ts_sentiment
    ON posts (brand, DATE_TRUNC('day', timestamp), sentiment)
    INCLUDE (post_id);

-- Pipeline run lookups
CREATE INDEX idx_posts_run_id      ON posts (pipeline_run_id);
```

---

## 2. Conversation Share

What percentage of all posts mention each brand (for the current 7-day window):

```sql
WITH total AS (
    SELECT COUNT(DISTINCT post_id) AS total_posts
    FROM posts
    WHERE timestamp >= NOW() - INTERVAL '7 days'
),
brand_counts AS (
    SELECT brand, COUNT(DISTINCT post_id) AS brand_posts
    FROM posts
    WHERE timestamp >= NOW() - INTERVAL '7 days'
    GROUP BY brand
)
SELECT
    b.brand,
    b.brand_posts,
    t.total_posts,
    ROUND(b.brand_posts::NUMERIC / t.total_posts * 100, 2) AS conversation_share_pct
FROM brand_counts b
CROSS JOIN total t
ORDER BY conversation_share_pct DESC;
```

---

## 3. Sentiment Distribution by Brand

```sql
SELECT
    brand,
    sentiment,
    COUNT(*)                                          AS post_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY brand), 2) AS pct
FROM posts
WHERE timestamp >= NOW() - INTERVAL '7 days'
  AND classification_status = 'classified'
GROUP BY brand, sentiment
ORDER BY brand, sentiment;
```

---

## 4. Intent & Emotion Breakdown by Brand

Reusable pattern — substitute `intent` or `emotion` for the label column:

```sql
-- Intent breakdown
SELECT
    brand,
    intent,
    COUNT(*)                                           AS post_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY brand), 2) AS pct
FROM posts
WHERE timestamp >= NOW() - INTERVAL '7 days'
  AND classification_status = 'classified'
GROUP BY brand, intent
ORDER BY brand, pct DESC;
```

---

## 5. 7-Day Rolling Sentiment Trend

Daily negative sentiment count per brand for the last 7 days. Used for trend chart generation:

```sql
WITH date_series AS (
    SELECT generate_series(
        DATE_TRUNC('day', NOW()) - INTERVAL '6 days',
        DATE_TRUNC('day', NOW()),
        INTERVAL '1 day'
    )::DATE AS day
),
brands AS (
    SELECT DISTINCT brand FROM posts
),
spine AS (
    SELECT d.day, b.brand
    FROM date_series d CROSS JOIN brands b
),
daily_neg AS (
    SELECT
        DATE_TRUNC('day', timestamp)::DATE AS day,
        brand,
        COUNT(*) AS negative_count
    FROM posts
    WHERE sentiment = 'Negative'
      AND timestamp >= NOW() - INTERVAL '7 days'
    GROUP BY 1, 2
)
SELECT
    s.day,
    s.brand,
    COALESCE(d.negative_count, 0) AS negative_count
FROM spine s
LEFT JOIN daily_neg d USING (day, brand)
ORDER BY s.brand, s.day;
```

---

## 6. Top Topics by Brand

```sql
SELECT
    brand,
    pillar,
    topic,
    post_count,
    rank
FROM (
    SELECT
        brand,
        pillar,
        topic,
        COUNT(*) AS post_count,
        RANK() OVER (PARTITION BY brand ORDER BY COUNT(*) DESC) AS rank
    FROM posts
    WHERE timestamp >= NOW() - INTERVAL '7 days'
      AND classification_status = 'classified'
    GROUP BY brand, pillar, topic
) ranked
WHERE rank <= 10
ORDER BY brand, rank;
```

---

## 7. Competitive Gap — T-Mobile vs Competitors

Compare T-Mobile US negative sentiment rate against each competitor:

```sql
WITH brand_sentiment AS (
    SELECT
        brand,
        COUNT(*) FILTER (WHERE sentiment = 'Negative') AS negative_count,
        COUNT(*)                                        AS total_count
    FROM posts
    WHERE timestamp >= NOW() - INTERVAL '7 days'
      AND classification_status = 'classified'
    GROUP BY brand
),
tmobile AS (
    SELECT ROUND(negative_count * 100.0 / total_count, 2) AS neg_pct
    FROM brand_sentiment
    WHERE brand = 'T-Mobile US'
)
SELECT
    bs.brand,
    ROUND(bs.negative_count * 100.0 / bs.total_count, 2)    AS competitor_neg_pct,
    t.neg_pct                                                 AS tmobile_neg_pct,
    ROUND(t.neg_pct - (bs.negative_count * 100.0 / bs.total_count), 2) AS gap_pct
FROM brand_sentiment bs
CROSS JOIN tmobile t
WHERE bs.brand <> 'T-Mobile US'
ORDER BY gap_pct DESC;
```

> A positive `gap_pct` means T-Mobile US has a higher negative rate than the competitor — a signal requiring executive attention.

---

## 8. Pipeline Run Summary

Used for `EVALUATION-METRICS.md` run logging. Returns per-run accuracy metadata:

```sql
SELECT
    pipeline_run_id,
    MIN(timestamp)                                               AS run_started_at,
    COUNT(*)                                                     AS total_posts,
    COUNT(*) FILTER (WHERE classification_status = 'classified') AS classified_count,
    COUNT(*) FILTER (WHERE classification_status = 'flagged')    AS flagged_count,
    ROUND(AVG(confidence), 3)                                    AS avg_confidence
FROM posts
GROUP BY pipeline_run_id
ORDER BY run_started_at DESC
LIMIT 10;
```

---

## Constraints

**MUST:**
- Always filter on `timestamp >= NOW() - INTERVAL '7 days'` to scope to current analysis window
- Exclude `classification_status = 'flagged'` from accuracy-sensitive metrics
- Use window functions (`OVER PARTITION BY`) for percentage calculations — avoid subquery joins
- Use CTEs for multi-step aggregations — avoid deeply nested subqueries
- Test all queries with `EXPLAIN ANALYZE` before production use

**MUST NOT:**
- Use `SELECT *` in production queries — always name columns explicitly
- Use `COUNT(DISTINCT post_id)` and `COUNT(*)` interchangeably — `post_id` is unique per brand row after exploding multi-brand posts
- Mix `classification_status` filters inconsistently across joined queries

---

## Related Skills

- [PANDAS-DATA-PIPELINE.md](PANDAS-DATA-PIPELINE.md) — Python-layer aggregation for in-memory analysis
- [OUTPUT-SCHEMA.md](../OUTPUT-SCHEMA.md) — canonical field names that map to column names here
- [TREND-ANALYISIS.md](TREND-ANALYISIS.md) — alert thresholds applied on top of these query results
- [EVALUATION-METRICS.md](EVALUATION-METRICS.md) — pipeline run summary queries feed into experiment tracking
