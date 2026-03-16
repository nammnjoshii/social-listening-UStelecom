# Claude Prompt Library — U.S. Telecom Social Listening

This document defines the **library of Claude prompts** used across the social listening pipeline for **T-Mobile US** (client) and its main competitors **AT&T Mobility** and **Verizon**. The prompts ensure **consistent, telecom-specific reasoning** for topic discovery, post classification, sentiment, intent, and emotion extraction.

> **Client:** T-Mobile US | **Competitors:** AT&T Mobility, Verizon

---

## Purpose

- Centralize and standardize **all Claude prompt templates**.  
- Ensure outputs are **structured, accurate, and compatible** with downstream analytics.  
- Facilitate **taxonomy discovery, post-level classification, and executive insight generation**.  

---

## 1. Topic Discovery

**Objective:**  
Analyze posts and generate a **hierarchical taxonomy**: Pillar → Category → Theme → Topic.

**Prompt Guidelines:**  
- Extract **telecom-specific topics** only.  
- Avoid **duplicate or overlapping topics**.  
- Respect canonical hierarchy and governance rules.  
- Highlight **emerging topics** when they appear in recent posts.

**Expected Output:**  
```json
{
  "pillar": "Network Performance",
  "category": "Coverage",
  "theme": "Urban Coverage",
  "topic": "Signal loss in subway"
}
2. Post Classification

Objective:
Assign multi-label and single-label attributes to each post.

Prompt Guidelines:

Include brands (multi-label), taxonomy path, sentiment, intent, and emotion.

Refer to canonical taxonomy.md and brand-entity-recognition.md.

Ensure single-topic assignment per post for clean aggregation.

Expected Output:

{
  "brands": ["T-Mobile US", "Verizon"],
  "taxonomy": {
    "pillar": "Network Performance",
    "category": "Coverage",
    "theme": "Urban Coverage",
    "topic": "Signal loss in subway"
  },
  "sentiment": "Negative",
  "intent": "Complaint",
  "emotion": "Frustration"
}
3. Sentiment Analysis

Objective:
Classify sentiment contextually for telecom.

Prompt Guidelines:

Consider telecom-specific nuance:

“Fast but unreliable” → Negative

“Great speed, terrible coverage” → Negative

Prioritize negative polarity in mixed posts.

Align with signal/noise filtering rules.

4. Intent & Emotion Assignment

Objective:
Assign single dominant intent and emotion.

Intent Categories:

Complaint

Inquiry

Praise

Recommendation

Emotion Categories:

Frustration

Satisfaction

Confusion

Excitement

Prompt Guidelines:

Identify primary intent even if post contains multiple cues.

Extract dominant emotion, ignoring minor or secondary feelings.

Maintain consistency across posts and brands.

Best Practices

Always reference canonical taxonomy and brand lists.

Apply noise filtering before prompting to remove irrelevant content.

Use structured JSON outputs for downstream aggregation and dashboards.

Periodically update prompts to reflect emerging topics, new trends, or model improvements.

Version prompts for traceability and reproducibility in enterprise pipelines.