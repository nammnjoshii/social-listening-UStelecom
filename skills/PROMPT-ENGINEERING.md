# Prompt Engineering Strategy

## Purpose

Prompt engineering ensures consistent, structured outputs from the LLM when analyzing telecom-related social media posts.

The objective is to guarantee reproducible classification across posts referencing:

- **T-Mobile US** *(client)*
- AT&T Mobility *(competitor)*
- Verizon *(competitor)*

> **Client:** T-Mobile US | **Competitors:** AT&T Mobility, Verizon

---

## Design Principles

Professional prompts must be:

- deterministic
- structured
- schema-driven
- domain-aware

---

## Output Schema

All LLM responses must conform to the following structure:

Brand  
Sentiment  
Intent  
Emotion  
Pillar  
Category  
Theme  
Topic

---

## Example Prompt

Analyze the following telecom-related social media post.

Return the output in the following structure:

Brand:
Sentiment:
Intent:
Emotion:
Pillar:
Category:
Theme:
Topic:

---

## Best Practices

- use explicit formatting rules
- include domain examples
- restrict vocabulary when possible
- enforce machine-readable output

---

## Expected Outcome

Consistent structured outputs that can be aggregated into analytics pipelines and executive dashboards.

---

## Prompt Versioning

Every prompt deployed to the full 1,500-post pipeline run must include a version header block. This ties evaluation results to the exact prompt used.

```
prompt_id: sentiment-v2
version: 2.1.0
last_tested_date: 2026-03-14
taxonomy_version: 2.0.0
accuracy_baseline: 0.87
```

Version format follows `MAJOR.MINOR.PATCH`:
- **MAJOR** — changes that alter output schema or label vocabulary
- **MINOR** — changes to examples, tone, or instructions that may shift accuracy
- **PATCH** — typo fixes or whitespace-only edits

---

## Few-Shot Examples by Task

### Sentiment Classification

```
Post: "T-Mobile just knocked out my signal for the 3rd time this week. Unacceptable."
→ Sentiment: Negative

Post: "Switched from AT&T to T-Mobile last month. Coverage is honestly the same but saving $30/mo."
→ Sentiment: Neutral

Post: "Verizon's 5G speeds in downtown are insane. Streaming 4K on my phone no problem."
→ Sentiment: Positive
```

### Intent Detection

```
Post: "Why is my bill $20 higher this month with no explanation? @TMobile"
→ Intent: Complaint

Post: "Does T-Mobile offer any military discounts? Asking for my dad."
→ Intent: Inquiry

Post: "Shoutout to the AT&T store rep who stayed 30 min late to fix my SIM issue."
→ Intent: Praise

Post: "If you're in a rural area, Verizon is hands-down the best option. Go with them."
→ Intent: Recommendation
```

### Emotion Detection

```
Post: "I've called Verizon support 4 times and still no resolution. I give up."
→ Emotion: Frustration

Post: "Finally got my T-Mobile trade-in credited. Smooth process, happy customer!"
→ Emotion: Satisfaction

Post: "My AT&T plan suddenly changed and I have no idea what I'm paying for anymore."
→ Emotion: Confusion

Post: "Just got T-Mobile Home Internet — 300 Mbps for $50/mo. Game changer!"
→ Emotion: Excitement
```

### Multi-Brand Chain-of-Thought (for posts mentioning 2+ brands)

When a post references multiple brands, extract each brand independently before classifying sentiment/intent/emotion:

```
Post: "Switched from Verizon to T-Mobile and honestly Verizon's network is better but T-Mobile's price is hard to beat."

Step 1 — Identify brands: ["Verizon", "T-Mobile US"]
Step 2 — Classify per brand:
  Verizon: Sentiment=Positive, Intent=Praise, Emotion=Satisfaction
  T-Mobile US: Sentiment=Positive, Intent=Recommendation, Emotion=Satisfaction
Step 3 — Output two records, one per brand.
```

---

## Evaluation Rubric

Before deploying a prompt revision to a full 1,500-post run, validate it against a 50-post labeled test set:

| Criterion | Pass Threshold | Action if Failing |
|-----------|---------------|-------------------|
| Sentiment Accuracy | ≥ 85% | Revise examples or instructions |
| Intent Accuracy | ≥ 80% | Add clarifying examples for edge cases |
| Emotion Accuracy | ≥ 78% | Tighten vocabulary constraints |
| Brand Detection Recall | ≥ 95% | Expand brand alias list in prompt |
| Schema Compliance | 100% | Enforce JSON output format explicitly |
| Multi-brand split rate | Matches ground truth ± 5% | Review chain-of-thought instruction |

Log test results against the prompt version header before promoting to production.

---

## Before / After Optimization Example

**Before (vague, underspecified):**
```
Analyze this telecom post and tell me the sentiment.
```

**After (schema-driven, domain-aware, vocabulary-constrained):**
```
You are analyzing a U.S. telecom social media post.

Classify the sentiment using ONLY one of these labels: Positive, Neutral, Negative.

Rules:
- If the post contains both praise and complaint, choose Negative (complaint takes precedence)
- Sarcasm and irony should be classified as Negative
- Price comparisons without complaints are Neutral

Post: {post_text}

Return JSON: {"sentiment": "<label>"}
```