# Contextual Sentiment Analysis — U.S. Telecom Social Listening

This document defines **post-level sentiment classification rules** for social media posts referencing **T-Mobile US** (client) and its main competitors **AT&T Mobility** and **Verizon**.
Sentiment is determined with **telecom-specific contextual nuances** and feeds directly into **taxonomy metrics, trend analysis, and executive dashboards**.

> **Client:** T-Mobile US | **Competitors:** AT&T Mobility, Verizon

---

## 1. Purpose

- Capture nuanced sentiment in telecom conversations.
- Prioritize **service complaints and operational issues** when sentiment is mixed.
- Handle **comparative and competitive mentions** with per-brand attribution.
- Enable **accurate downstream aggregation** for executive insights.

**Example:**

> "5G speeds are fast but coverage is terrible." → **Negative** (coverage issue dominates)

---

## 2. Sentiment Labels

- **Positive** — The post expresses satisfaction, praise, or approval about a telecom brand or service.
- **Neutral** — The post is informational, factual, or balanced with no dominant emotional valence.
- **Negative** — The post expresses dissatisfaction, frustration, complaint, or criticism.

---

## 3. Telecom-Specific Nuance

**Negative takes precedence** in mixed sentiment cases. Operational failures (coverage, speed, billing, support) are primary customer experience signals and outweigh positive mentions of secondary features.

| Post Text | Assigned Sentiment | Rationale |
|---|---|---|
| "Fast but unreliable network" | Negative | Reliability outweighs speed for customer experience |
| "Great speed, terrible coverage" | Negative | Coverage dominates the experience |
| "Smooth upgrade process, very satisfied" | Positive | Successful service interaction |
| "Monthly update from Verizon" | Neutral | Informational; no emotional tone |
| "T-Mobile's 5G is impressive but their billing is a nightmare" | Negative | Billing complaint dominates |
| "AT&T support actually helped me today, shocked" | Positive | Positive resolution; surprise doesn't negate the outcome |

---

## 4. Special Rules

| Context | Sentiment |
|---|---|
| Network outages | Negative |
| Billing or plan issues | Negative |
| Device failures | Negative |
| Customer service complaints | Negative |
| Successful support interactions | Positive |
| Praise for coverage or speed | Positive |
| Informational updates or news posts | Neutral |
| Mixed positive & negative signals | Negative takes precedence |
| Sarcasm / irony | Apply the intended sentiment, not the literal words (see Section 5) |
| Comparative mentions | Per-brand attribution required (see Section 6) |

**Telecom jargon signals:** Terms like "dropped calls," "slow LTE," "mid-band issues," "throttled," "dead zone," "roaming charges," "port-in nightmare" should **strongly influence** Negative sentiment. Claude must recognize these domain terms even without explicit complaint language.

---

## 5. Sarcasm & Irony Handling

Sarcasm is common in telecom complaints on X and Reddit. Literal classification will produce incorrect sentiment.

**Rule:** If the post contains ironic praise that implies a negative experience, classify as **Negative**.

| Post Text | Literal Reading | Correct Sentiment |
|---|---|---|
| "Oh great, AT&T is down AGAIN. Love it." | Positive (praise) | **Negative** (sarcastic) |
| "Wow, T-Mobile support only kept me on hold for 45 minutes. Amazing service!" | Positive | **Negative** (sarcastic) |
| "Verizon charges me for things I never signed up for. But hey, at least they're consistent!" | Mixed | **Negative** |

**Sarcasm indicators Claude should recognize:** ALL CAPS on positive words ("LOVE", "GREAT", "AMAZING"), punctuation patterns ("Love it. 🙄"), explicit time/effort quantification that implies failure ("only 3 hours to resolve"), "classic [brand]" as a complaint pattern.

---

## 6. Comparative & Competitive Mention Rules

Posts comparing two or more brands require **per-brand sentiment attribution**. Do not assign a single sentiment to the whole post — classify sentiment independently for each referenced brand.

**Rule:** A statement that is positive about Brand A is implicitly neutral-to-negative for Brand B, and vice versa.

| Post Text | T-Mobile Sentiment | Verizon Sentiment | AT&T Sentiment |
|---|---|---|---|
| "Switched from Verizon to T-Mobile — coverage is so much better." | Positive | Negative | — |
| "T-Mobile is the only carrier not throttling me during peak hours." | Positive | Negative (implied) | Negative (implied) |
| "AT&T and Verizon are both better than T-Mobile for rural coverage." | Negative | Positive | Positive |
| "All three carriers have terrible customer service." | Negative | Negative | Negative |

**Implementation note:** When `is_multi_brand: true`, Claude must return a sentiment value that reflects the brand specified in the `brand` field of the classification call. Each brand in a multi-brand post generates a separate classification record.

---

## 7. Neutral Classification Criteria

A post is **Neutral** only when it meets all of the following:

- No clear positive or negative emotional language.
- No complaint, praise, or frustration signal.
- Content is factual, informational, or a question without an implied sentiment.

**Examples of genuinely Neutral posts:**
- "Does T-Mobile offer international roaming in Japan?"
- "Verizon announced new 5G coverage expansion in the Midwest."
- "Comparing AT&T and T-Mobile plan pricing side by side."

---

## 8. Output Schema

Sentiment must be output in **structured JSON** as part of the unified classification response defined in `OUTPUT-SCHEMA.md`:

```json
{
  "brand": "T-Mobile US",
  "sentiment": "Positive | Neutral | Negative"
}
```

For multi-brand posts, sentiment is assigned per brand in separate classification records. Each record carries the `brand` field to indicate which brand the sentiment applies to.

---

## 9. Best Practices

- **Domain jargon awareness:** Ensure Claude prompt examples include telecom-specific negative signals (throttling, dead zones, roaming charges, dropped calls) so Claude does not miss these even when phrased indirectly.
- **Precedence rule enforcement:** Explicitly instruct Claude in the prompt: *"If a post contains both positive and negative signals about the same brand, classify as Negative. Operational failures always take precedence."*
- **Sarcasm instruction:** Include sarcasm detection examples in the classification prompt examples (few-shot) for X/Twitter posts where irony is common.
- **Per-brand attribution for multi-brand posts:** For posts with `is_multi_brand: true`, Claude receives the specific `brand` to evaluate. It should assess sentiment **only for that brand's mentions** within the post.
- **Feed discrepancies into prompt tuning:** Sentiment misclassifications surfaced in weekly spot-checks (see `DATA-QUALITY-CHECKS.md`) should be added as corrective few-shot examples to the classification prompt.
