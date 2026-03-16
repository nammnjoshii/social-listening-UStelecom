# Pandas Data Pipeline — U.S. Telecom Social Listening

Adapted from `pandas-pro` skill. Covers vectorized DataFrame patterns for batch aggregation, trend analysis, and platform quota validation across 1,500 telecom social media posts.

> **Client:** T-Mobile US | **Competitors:** AT&T Mobility, Verizon

---

## Design Principles

- Use **vectorized operations** — never `.iterrows()` or `.apply()` where avoidable
- Set **explicit dtypes** at ingestion to minimize memory footprint
- Always **`.copy()`** slices before mutation to avoid `SettingWithCopyWarning`
- Handle **missing values explicitly** — do not silently drop or fill without logging
- Validate **row counts** at each stage against expected quotas

---

## 1. Ingestion & Dtype Setup

Load the 1,500-post dataset with explicit dtypes to minimize memory and prevent silent coercions:

```python
import pandas as pd

PLATFORM_QUOTA = 500  # posts per platform

dtype_map = {
    "post_id": "string",
    "platform": "category",       # Instagram | Reddit | X
    "brand": "category",          # T-Mobile US | Verizon | AT&T Mobility
    "sentiment": "category",      # Positive | Neutral | Negative
    "intent": "category",         # Complaint | Inquiry | Praise | Recommendation
    "emotion": "category",        # Frustration | Satisfaction | Confusion | Excitement
    "pillar": "category",
    "category": "category",
    "theme": "string",
    "topic": "string",
    "confidence": "float32",
}

df = pd.read_json("pipeline_output.jsonl", lines=True, dtype=dtype_map)
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
```

---

## 2. Platform Quota Validation

Assert stratified sampling quotas before any analysis. Fail fast if ingestion is incomplete.

```python
def validate_platform_quotas(df: pd.DataFrame, quota: int = PLATFORM_QUOTA) -> None:
    counts = df["platform"].value_counts()
    for platform in ["Instagram", "Reddit", "X"]:
        actual = counts.get(platform, 0)
        assert actual == quota, (
            f"Platform quota violation: {platform} has {actual} posts, expected {quota}"
        )

validate_platform_quotas(df)
```

---

## 3. Conversation Share

Calculate what percentage of total posts mention each brand. Posts mentioning multiple brands are counted once per brand (multi-label).

```python
def conversation_share(df: pd.DataFrame) -> pd.Series:
    total_posts = len(df)
    # brands column may be a list — explode for multi-label counting
    brand_counts = df.explode("brands")["brands"].value_counts()
    return (brand_counts / total_posts * 100).round(2).rename("conversation_share_pct")

share = conversation_share(df)
```

---

## 4. Sentiment Distribution by Brand

```python
def sentiment_distribution(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby(["brand", "sentiment"], observed=True)
        .size()
        .rename("count")
        .reset_index()
        .assign(pct=lambda x: x.groupby("brand")["count"].transform(lambda c: c / c.sum() * 100).round(2))
    )

sentiment_dist = sentiment_distribution(df)
```

---

## 5. Intent & Emotion Breakdown

```python
def label_breakdown(df: pd.DataFrame, label_col: str) -> pd.DataFrame:
    """Generic breakdown for intent or emotion by brand."""
    return (
        df.groupby(["brand", label_col], observed=True)
        .size()
        .rename("count")
        .reset_index()
        .assign(pct=lambda x: x.groupby("brand")["count"].transform(lambda c: c / c.sum() * 100).round(2))
    )

intent_breakdown = label_breakdown(df, "intent")
emotion_breakdown = label_breakdown(df, "emotion")
```

---

## 6. 7-Day Rolling Trend

Generate daily snapshots per brand for the last 7 days. Used for trend charts comparing T-Mobile US against competitors.

```python
def seven_day_trend(df: pd.DataFrame, metric_col: str, metric_value: str) -> pd.DataFrame:
    """
    Rolling daily count of posts where metric_col == metric_value, grouped by brand.
    Example: seven_day_trend(df, 'sentiment', 'Negative')
    """
    daily = (
        df[df[metric_col] == metric_value]
        .assign(date=df["timestamp"].dt.date)
        .groupby(["date", "brand"], observed=True)
        .size()
        .rename("count")
        .reset_index()
    )
    # Fill missing days with 0
    all_dates = pd.date_range(df["timestamp"].dt.date.min(), df["timestamp"].dt.date.max(), freq="D").date
    all_brands = df["brand"].cat.categories.tolist()
    idx = pd.MultiIndex.from_product([all_dates, all_brands], names=["date", "brand"])
    return daily.set_index(["date", "brand"]).reindex(idx, fill_value=0).reset_index()

negative_trend = seven_day_trend(df, "sentiment", "Negative")
complaint_trend = seven_day_trend(df, "intent", "Complaint")
```

---

## 7. Top Topics by Brand

```python
def top_topics(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    return (
        df.groupby(["brand", "pillar", "topic"], observed=True)
        .size()
        .rename("count")
        .reset_index()
        .sort_values(["brand", "count"], ascending=[True, False])
        .groupby("brand", observed=True)
        .head(n)
        .reset_index(drop=True)
    )

top_n = top_topics(df, n=10)
```

---

## 8. Memory Optimization for Large Batches

When ingesting more than one pipeline run at a time, chunk the JSONL file to avoid OOM errors:

```python
def load_chunked(filepath: str, chunksize: int = 500) -> pd.DataFrame:
    chunks = []
    for chunk in pd.read_json(filepath, lines=True, chunksize=chunksize):
        chunk["timestamp"] = pd.to_datetime(chunk["timestamp"], utc=True)
        for col in ["platform", "brand", "sentiment", "intent", "emotion", "pillar"]:
            if col in chunk.columns:
                chunk[col] = chunk[col].astype("category")
        chunks.append(chunk)
    return pd.concat(chunks, ignore_index=True)
```

---

## Constraints

**MUST:**
- Use vectorized operations for all aggregations
- Set `category` dtype for all low-cardinality label columns
- Validate platform quotas before running any aggregation
- Use `.copy()` when subsetting before mutation
- Handle missing brand/sentiment/topic values explicitly (log and exclude, do not silently drop)

**MUST NOT:**
- Use `.iterrows()` — use `.apply()` with `axis=1` only as a last resort, or restructure with `groupby`
- Use chained indexing (`df[...][...]`) — always use `.loc[]`
- Load the full dataset without chunking when processing multiple pipeline runs together
- Fill missing values with defaults without logging what was filled

---

## Related Skills

- [EVALUATION-METRICS.md](EVALUATION-METRICS.md) — validation gates and accuracy tracking
- [TREND-ANALYISIS.md](TREND-ANALYISIS.md) — alert thresholds for trend anomalies
- [OUTPUT-GOVERNANCE.md](OUTPUT-GOVERNANCE.md) — schema enforcement before loading into DataFrame
