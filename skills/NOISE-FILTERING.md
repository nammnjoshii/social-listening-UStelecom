# Noise Filtering — U.S. Telecom Social Listening

This document defines **noise filtering rules and thresholds** for social media posts referencing **T-Mobile US** (client) and its main competitors **AT&T Mobility** and **Verizon**.
Proper filtering ensures **Claude intelligence and downstream analytics** focus on **actionable customer experience signals**.

> **Client:** T-Mobile US | **Competitors:** AT&T Mobility, Verizon

---

## 1. Purpose

- Remove irrelevant content that does **not provide insight** into customer experience.
- Ensure **taxonomy classification, sentiment, intent, and emotion detection** are accurate.
- Maintain **high-quality data** feeding the executive dashboard.

---

## 2. Posts to Remove (Noise)

| Type | Examples | Filter Rule |
|---|---|---|
| Ads & Promotional | "Sign up for T-Mobile unlimited plan today!" | Promotional phrase blocklist; verified brand account filter |
| Excessive hashtags | "#tmobile #deal #sale #wireless #5G #unlimited #switch" | >5 hashtags → remove |
| Memes / image-only | GIFs, memes, or image posts with no caption text | <15 words post-normalization → remove |
| Bot spam | Repeated auto-posts, identical text across accounts | SHA-256 deduplication + MinHash LSH (Jaccard ≥ 0.85) |
| Non-service mentions | "I like Verizon's logo", "Watching the AT&T commercial" | Text-based context screening; Claude-assisted borderline pass |
| URL-only posts | "https://t.co/xyz123" | URL-only detection → remove |
| Non-English posts | Posts in languages other than English | fastText language ID filter → remove |
| Very short posts | Posts fewer than 15 words after normalization | Minimum-length filter → remove |

---

## 3. Posts to Keep (Signal)

| Type | Examples |
|---|---|
| Direct customer experience | "Verizon coverage dropped again today." |
| Indirect experience indicators | "Had to call AT&T support twice this week." |
| Multi-brand comparisons | "Switched from T-Mobile to Verizon because speeds were slow." |
| Praise or complaints about network, billing, devices | "AT&T trade-in program worked well." |
| Switching intent | "Thinking of leaving T-Mobile after this billing mess." |
| 5G or plan commentary | "T-Mobile's Go5G plan is expensive for what you get." |

---

## 4. Filtering Rules & Thresholds

Apply filters **in this order**:

### 4.1 Deduplication

- **Exact duplicates:** SHA-256 hash on normalized post text (lowercased, whitespace-collapsed). Remove any post whose hash already exists in the dataset.
- **Near-duplicates:** MinHash Locality-Sensitive Hashing (LSH) with a Jaccard similarity threshold of **0.85**. Handles retweets, cross-platform syndication, and minor character variations.
- Keep the instance with the highest engagement (likes + comments + shares) when deduplicating near-duplicates.

### 4.2 Spam & Promotional Content

- **Hashtag count filter:** Discard posts with **more than 5 hashtags** — a reliable spam signal on X and Instagram.
- **Verified brand account filter:** Discard posts from verified official brand accounts (T-Mobile, Verizon, AT&T corporate handles). These are promotional, not organic customer voice.
- **URL-only filter:** Discard posts whose normalized text is entirely composed of URLs.
- **Promotional phrase blocklist:** Remove posts matching any of the following patterns:
  - "Click the link in bio"
  - "Use code [A-Z0-9]+" (promo code pattern)
  - "Ad:" or "Sponsored" at start of post
  - "Limited time offer"
  - "Sign up now"
- **Claude-assisted borderline pass:** For posts that are not clearly organic or promotional, run: *"Is this post organic customer commentary or brand-generated promotional content? Answer: Organic / Promotional."* Only posts classified as Organic proceed.

### 4.3 Text Normalization (applied before length filter)

Apply in order:
1. Lowercase all text.
2. Remove URLs (regex `https?://\S+`).
3. **Expand hashtags** — strip the `#` prefix but **retain the word** (e.g., `#tmobile` → `tmobile`). Do **not** strip the word entirely, as it preserves brand and topic signals.
4. Replace @mentions with `[USER]` placeholder (preserves conversational structure, removes PII).
5. Normalize Unicode characters; strip emoji.
6. Collapse repeated whitespace and punctuation.

### 4.4 Language Filter

- Retain **English-language posts only**.
- Use `fastText` language identification model for speed and accuracy.
- Non-English posts are excluded and logged (not discarded silently).

### 4.5 Minimum-Length Filter

- Discard posts with **fewer than 15 words** after normalization.
- These carry insufficient signal for reliable multi-label classification.

---

## 5. Platform-Specific Rules

| Platform | Rule |
|---|---|
| **Instagram** | Image and meme posts are common in telecom communities. **Extract caption text** via the Instagram Graph API before applying the length filter. If caption is empty or <15 words, discard. |
| **Reddit** | Post titles and body text should both be included in the text field. Self-posts (text-only) are generally high-signal. Filter out deleted/removed posts (`[deleted]`, `[removed]`). |
| **X (Twitter)** | Threads: include both the original tweet and visible reply context where available. Retweets are near-duplicates and are caught by the MinHash LSH step. |

---

## 6. Output Schema

Filtered posts output a `signal` flag for audit purposes. Only `signal: true` posts proceed to Claude classification.

```json
{
  "post_id": "12345",
  "platform": "Instagram",
  "brands": ["Verizon", "AT&T Mobility"],
  "normalized_text": "verizon coverage dropped again today",
  "signal": true,
  "filter_applied": null
}
```

For removed posts:

```json
{
  "post_id": "12346",
  "platform": "X",
  "brands": ["T-Mobile US"],
  "normalized_text": "",
  "signal": false,
  "filter_applied": "hashtag_count"
}
```

**`filter_applied` values:** `duplicate`, `near_duplicate`, `hashtag_count`, `verified_account`, `url_only`, `promotional_phrase`, `non_english`, `min_length`, `claude_promotional`

Posts marked `signal: false` are logged for audit and quality monitoring but do not enter the classification pipeline.

---

## 7. Expected Outcome

- High signal-to-noise ratio for analytics.
- More accurate topic, sentiment, intent, and emotion classification.
- Cleaner data feeding the executive social listening dashboard.
- Cleaning log records removal counts per filter rule per platform for every pipeline run.

---

## 8. Best Practices

- **Periodically review filtering rules** for emerging noise patterns (new spam tactics, new promotional phrase formats).
- **Monitor cleaning attrition rate** per pipeline run. If >40% of collected posts are removed, investigate data collection filters — the API-level keyword query may be too broad.
- **Never strip hashtag words entirely** — expand them (`#tmobile` → `tmobile`). Stripped hashtags lose brand signals that downstream classification relies on.
- **Maintain version control** for the promotional phrase blocklist to track changes over time.
- **Ensure consistent filtering** across all platforms and brands using the same rule set.
