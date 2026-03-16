# Troubleshooting — U.S. Telecom Social Listening

This document provides guidance for diagnosing and resolving common issues in the **Claude Code social listening pipeline** for **T-Mobile US** (client) and its main competitors **AT&T Mobility** and **Verizon**.

> **Client:** T-Mobile US | **Competitors:** AT&T Mobility, Verizon

---

## 1. Misclassified Posts

**Symptoms:** Posts assigned incorrect taxonomy, sentiment, intent, or emotion.

**Diagnosis:**
- Pull the post's `pipeline_run_id` and `prompt_version` from the run log.
- Check if the post was classified at Low confidence (`confidence: "Low"`).
- Verify the post's taxonomy path against `TAXONOMY.md`.

**Actions:**
- Re-run Claude classification on affected posts using the current locked taxonomy and prompt.
- Verify posts against the canonical taxonomy in `TAXONOMY.md`.
- Review prompt consistency in `CLAUDE-PROMPT-LIBRARY.md` — ensure the prompt includes the full taxonomy JSON and all enum constraints.
- Add the misclassified post as a corrective few-shot example in the next prompt version.
- Spot-check sample posts for model drift. Reference the experiment tracking table in `EVALUATION-METRICS.md`.

---

## 2. Missing Brands

**Symptoms:** Posts referencing a brand are not tagged; `brands` field is empty.

**Diagnosis:**
- Check the raw post text for the brand variant used (e.g., "Magenta" instead of "T-Mobile").
- Determine if the post uses an alias not in the current alias dictionary.

**Actions:**
- Check brand normalization patterns in `BRAND-ENTITY-RECOGNITION.md`. Update the alias dictionary if a new variant is found.
- Ensure multi-brand extraction rules are applied — a post mentioning two brands must produce two brand tags.
- Validate against sample posts containing alternative spellings or abbreviations (e.g., `T-Mo`, `VZW`, `Big Red`).
- If "Sprint" is mentioned in a legacy context, confirm it maps to T-Mobile US at Medium confidence.
- For contextual-only brand mentions ("the pink carrier"), the Claude Low-confidence resolution pass should have triggered. Check if it ran correctly for that post batch.

---

## 3. Schema Validation Errors

**Symptoms:** Claude output fails JSON parsing or schema validation.

**Diagnosis:**
- Log the raw Claude response for the failing post.
- Check whether the JSON is malformed (truncated, unescaped characters, trailing text after the JSON block).

**Actions:**
- Apply a **JSON repair pass** (e.g., `json-repair` Python library or custom regex cleanup) before raising a parse error. Many failures are minor formatting issues.
- If repair succeeds: re-validate against `OUTPUT-SCHEMA.md` and proceed.
- If repair fails: mark `classification_status: "failed"`; add to retry queue.
- Confirm Claude prompts were not modified in a way that changed the output format (trailing explanation text, different field names).
- Check for missing required fields: `post_id`, `platform`, `brands`, `pillar`, `category`, `theme`, `topic`, `sentiment`, `intent`, `emotion`, `timestamp`.
- Verify prompt explicitly instructs: *"Return only valid JSON. No explanation text."*

---

## 4. High Low-Confidence Rate (>15%)

**Symptoms:** More than 15% of classified posts return `confidence: "Low"`. Aggregation is halted.

**Diagnosis:**
- Pull the distribution of Low-confidence posts by Pillar — which taxonomy area has the most Low-confidence?
- Check if recent social media events introduced new conversation topics not covered by the locked taxonomy.

**Actions:**
- **Do not proceed with aggregation** until resolved.
- Escalate to project lead.
- Review the `"Uncategorized"` bucket — if emerging topics account for the confidence drop, assess whether they warrant immediate taxonomy promotion (follow `TAXONOMY-VERSIONING.md` rules).
- If the taxonomy is sound, review the classification prompt for ambiguity — tighten enum constraints and add few-shot examples for the categories driving Low confidence.
- Re-run classification on the Low-confidence subset after prompt update.

---

## 5. Empty Topic Buckets

**Symptoms:** Certain taxonomy topics have zero posts in a cycle.

**Diagnosis:**
- Check if the topic was recently added (patch version bump) — it may not yet have enough organic posts.
- Verify the topic label in `TAXONOMY.md` exactly matches what Claude is returning.

**Actions:**
- Review taxonomy drift via `TAXONOMY-VERSIONING.md`. Confirm topics are still relevant to current social conversations.
- Merge or retire obsolete topics following versioning rules. A retired topic triggers a minor version bump.
- Check topic label case sensitivity — taxonomy labels must match exactly (e.g., "Billing Transparency" not "billing transparency").
- If a topic is new, allow 2–3 cycles before assessing whether it should be retired.

---

## 6. Sudden Sentiment Swings

**Symptoms:** Large changes in sentiment distribution within a short period (>2σ from rolling mean triggers a trend alert).

**Diagnosis:**
- Check the trend alert log for which brand and metric triggered the alert.
- Investigate whether a real-world event explains the shift (outage, billing system error, viral complaint thread).

**Actions:**
- Investigate **real-world events** (service outages, billing disruptions, viral social threads) using the timestamp of the spike.
- Validate **noise filtering** — check if spam or bot content slipped through. Run the cleaning log for that batch.
- Spot-check posts from the spike date for accuracy in sentiment, intent, and emotion classification.
- If the swing is real (event-driven), surface it in the executive insight brief with context.
- If the swing is noise (bot activity, data pipeline issue), exclude the affected batch and re-run after cleaning.

---

## 7. Platform API Failures

**Symptoms:** A platform returns fewer than 400 posts; API returns 429 (rate limit) or 503 (service unavailable).

**Actions by platform:**

| Platform | Issue | Response |
|---|---|---|
| **Instagram Graph API** | Rate limit exceeded | Retry with exponential backoff; reduce batch size to 25 requests; spread collection over 48-hour window |
| **Instagram Graph API** | Insufficient data (<400 posts) | Supplement with hashtag discovery (#tmobile, #att, #verizon); consider third-party provider (Brandwatch, Sprinklr) as backup |
| **Reddit API** | 503 Service Unavailable | Retry after 60s; switch to Pushshift.io as backup data source if Reddit API is persistently unavailable |
| **X/Twitter API** | Rate limit (429) | Exponential backoff; switch to lower-frequency polling; use Pro tier rate limits if volume is consistently insufficient |

For any platform contributing fewer than 300 posts after retries, halt the pipeline and log a critical data gap. Do not publish a dashboard with severely imbalanced platform representation.

---

## 8. Claude API Downtime

**Symptoms:** Claude API returns 5xx errors during the classification run; `classification_status: "failed"` rate spikes.

**Actions:**
- Implement retry logic: up to 3 attempts per batch with exponential backoff (2s → 4s → 8s → 16s).
- If Claude API remains unavailable after 3 retries, pause the pipeline and wait up to 2 hours before a full retry.
- Maintain a **24-hour buffer** between the scheduled pipeline run (Sunday 02:00 UTC) and the dashboard publish deadline (Monday 07:00 UTC) to absorb API outage recovery time.
- If the full classification run cannot complete within the buffer window, notify the project lead and delay the dashboard publish.
- Check [Anthropic status page] for ongoing incidents before retrying.

---

## 9. Taxonomy Version Mismatch

**Symptoms:** Post records from different taxonomy versions are mixed in the same trend chart; aggregation totals look inconsistent.

**Diagnosis:**
- Check `taxonomy_version` values across post records in the current cycle. There should be exactly one taxonomy version per cycle.

**Actions:**
- **Do not mix records from different taxonomy versions in the same trend computation.** This creates false trend signals when Pillar or Topic labels change.
- If a taxonomy update was applied mid-cycle, re-classify all posts from the current cycle under the new taxonomy version before aggregating.
- For cross-cycle trend charts (7-day), if a taxonomy major version bump occurred, add a visual indicator on the dashboard trend line showing the taxonomy change date.
- Follow `TAXONOMY-VERSIONING.md` for all version bump procedures.

---

## 10. Best Practices

- **Daily monitoring:** Check pipeline health dashboard for volume, sentiment, and classification confidence after each run.
- **Immutable correction protocol:** Never edit a published post record in-place. Write a new record with `supersedes` pointing to the original `post_id`.
- **Log manual interventions:** Maintain a structured log of all manual interventions (prompt patches, taxonomy edits, batch re-runs) keyed to `pipeline_run_id`.
- **Cross-reference versions:** When investigating anomalies, always check `taxonomy_version`, `schema_version`, and `prompt_version` together — mismatches between any two are a common root cause.
- **Update prompts proactively:** Regularly review and update Claude prompts in `CLAUDE-PROMPT-LIBRARY.md` to adapt to new telecom language trends (new product names, new complaint terminology). Schedule a quarterly prompt review.
- **Automate alerts:** Configure automated alerts for: brand coverage drops, sentiment spikes, Low-confidence rate breaches, classification success rate <95%. See `TREND-ANALYSIS.md` for threshold definitions.

---

This troubleshooting guide ensures **fast diagnosis, controlled remediation, and reliable outputs** for the enterprise-level social listening pipeline for **T-Mobile US** benchmarked against **AT&T Mobility** and **Verizon**.
