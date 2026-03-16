# Brand Entity Recognition — U.S. Telecom Social Listening

This document defines the **canonical brands, normalization rules, confidence scoring, and extraction logic** for identifying mentions of **T-Mobile US** (client) and its main competitors **AT&T Mobility** and **Verizon** in social media posts. Accurate brand recognition is critical for **taxonomy mapping, sentiment aggregation, and executive dashboards**.

> **Client:** T-Mobile US | **Competitors:** AT&T Mobility, Verizon

---

## 1. Purpose

- Detect telecom providers referenced in social media conversations.
- Enable reliable **conversation share analysis**, **trend monitoring**, and **cross-brand comparison**.

**Target Entities:**

- **T-Mobile US** *(client)*
- **AT&T Mobility** *(competitor)*
- **Verizon** *(competitor)*

---

## 2. Canonical Alias Dictionary

All variants must map to canonical brand names. Matching is **case-insensitive** and uses **word-boundary regex** to prevent false positives (e.g., "attend" ≠ "AT&T").

| Canonical Brand | Aliases |
|---|---|
| T-Mobile US | T-Mobile, TMobile, T-Mo, TMo, Magenta, Magenta Max, Uncarrier, @TMobile, #tmobile, TMUS, Sprint (legacy — Medium confidence) |
| Verizon | Verizon, Verizon Wireless, VZW, Big Red, @Verizon, #verizon |
| AT&T Mobility | AT&T, ATT, AT and T, AT & T, @ATT, #att, #attmobility, AT&T Mobility |

**Sprint note:** Sprint references are tagged as T-Mobile US with **Medium** confidence due to the 2020 merger. Legacy Sprint customer complaints (billing, device issues) are still relevant T-Mobile customer experience signals.

---

## 3. Confidence Scoring

Every brand tag receives a confidence level, which is stored in the `brand_confidence` field of the output schema.

| Confidence | Trigger | Example |
|---|---|---|
| **High** | Exact canonical name match | "T-Mobile dropped my call" |
| **Medium** | Alias or hashtag match | "Magenta's 5G is fast", "#verizon is terrible" |
| **Low** | Contextual inference only — requires Claude validation | "the pink carrier", "Big Carrier with the checkmark logo" |

**Low-confidence resolution:** For Low-confidence detections (~5–10% of posts), run a Claude validation pass:

> *"Does this post reference T-Mobile US, Verizon, AT&T Mobility, another carrier, or none of the above? Return a JSON array of canonical brand names only. If uncertain, return an empty array."*

Posts that remain unresolved after Claude validation are excluded from the dataset and logged.

---

## 4. Multi-Brand Detection

Posts may reference multiple brands simultaneously. Tag **all** confirmed brands. Multi-brand posts are high-value for competitive comparison and should be flagged with `is_multi_brand: true`.

**Example post:**

> "Verizon is faster than AT&T, but T-Mobile is improving."

**Output:**

```json
{
  "brands": ["Verizon", "AT&T Mobility", "T-Mobile US"],
  "brand_confidence": "High",
  "is_multi_brand": true
}
```

For mixed-confidence multi-brand posts (e.g., one brand detected at High, another at Medium), the `brand_confidence` field reflects the **lowest** confidence level across all detected brands.

---

## 5. Extraction Rules

**Case-insensitive matching:** Recognize brands regardless of capitalization (`verizon` → `Verizon`).

**Word-boundary matching:** Use regex word boundaries (`\b`) to prevent false positives:
- `\bATT\b` matches "ATT" but not "ATTENDANCE"
- `\bAT&T\b` matches "AT&T" but not mid-word
- `\batt\b` (case-insensitive) matches hashtag expansion of `#att`

**Hashtag expansion:** Hashtags are expanded before matching (e.g., `#tmobile` → `tmobile`). Do not strip hashtags entirely — the brand signal is preserved in the expanded form.

**Special characters:** Normalize hyphens and ampersands before matching (`T-Mobile` and `TMobile` both match; `AT&T` and `ATT` both match).

**Platform consistency:** Apply uniformly across Instagram, Reddit, and X (Twitter). Instagram caption text must be extracted from image posts before brand matching is applied.

---

## 6. Output Schema

Brand recognition output must conform to the fields defined in `OUTPUT-SCHEMA.md`:

```json
{
  "brands": ["T-Mobile US"],
  "brand_confidence": "High | Medium | Low",
  "is_multi_brand": false
}
```

**Rules:**
- Each post must contain at least one confirmed brand for downstream analytics. Posts with no confirmed brand are excluded and logged.
- `brands` must contain only canonical brand names — never raw aliases or hashtag forms.
- `is_multi_brand` is `true` when `brands` contains more than one entry.
- Multi-brand posts generate separate aggregation records per brand (each brand receives full credit).

---

## 7. False Positive Prevention

Common false positive patterns to guard against:

| Raw text | Issue | Correct handling |
|---|---|---|
| "I need to attend the meeting" | "att" matches "attend" | Word-boundary regex prevents this |
| "T-Mobile home internet router" | May match if router context ≠ mobile service | Keep — device/equipment is in-scope |
| "Verizon Media" | Old brand name for Yahoo | Contextual filter: exclude if post is about media/entertainment, not telecom service |
| "I used to have Sprint" | Sprint → T-Mobile US | Tag as T-Mobile US, Medium confidence |

---

## 8. Best Practices

- **Regular alias updates:** Review the alias dictionary monthly. New brand campaigns (e.g., T-Mobile's "Go5G", AT&T's "FirstNet") introduce new terms that should be added.
- **Integration with OUTPUT-GOVERNANCE.md:** Follow schema validation rules; `brands` must validate against the canonical brand list.
- **Spot-check validation:** Include brand detection accuracy in the weekly spot-check protocol (target: ≥97% brand recall per `EVALUATION-METRICS.md`).
- **Version control:** Track alias dictionary version alongside `taxonomy_version` and `schema_version` for full auditability.
