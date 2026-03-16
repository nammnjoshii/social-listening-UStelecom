blend and make a 10/10 Multi-Label Classification md for claude code 

"""
# Multi-Label Classification — U.S. Telecom Social Listening

This document defines the **multi-label and single-label classification framework** for social media posts referencing **T-Mobile US** (client) and its main competitors **AT&T Mobility** and **Verizon**. It ensures consistent, actionable insights for **taxonomic hierarchy, sentiment, intent, and executive dashboards**.

> **Client:** T-Mobile US | **Competitors:** AT&T Mobility, Verizon

---

## Supported Multi-Label Areas

| Area | Labeling Type | Notes |
|------|---------------|-------|
| **Brands** | Multi | A single post can reference multiple brands. Example: “Switched from AT&T to Verizon and considered T‑Mobile” → `["AT&T Mobility", "Verizon", "T-Mobile US"]` |
| **Intent** | Single | Each post has a primary intent: Complaint, Inquiry, Praise, Recommendation |
| **Emotion** | Single | Each post conveys one dominant emotion: Frustration, Excitement, Confusion, Satisfaction |
| **Topic** | Single | Maps to one most relevant taxonomy Topic to maintain clean aggregation |

**Rationale for Single Topic per Post:**  
- Prevents **analytics fragmentation**.  
- Ensures **clear aggregation** of volume, sentiment, and trends per topic.  
- Supports **coherent executive dashboards** without double counting.

---

## Example Post Classification

**Post Text:**  
*"Switched from AT&T to Verizon and considered T‑Mobile due to terrible speeds."*

**Classification Output:**

```json
{
  "brands": ["AT&T Mobility", "Verizon", "T-Mobile US"],
  "intent": "Complaint",
  "sentiment": "Negative",
  "emotion": "Frustration",
  "topic": "Data Speed"
}


"""

"""
# Multi-Label Classification

## Purpose

Social media posts often reference multiple signals simultaneously.

The system must support multi-label classification across:

- brand mentions
- sentiment
- intent
- emotion
- topic classification

---

## Example

Post:

"Switched from AT&T to Verizon because the speeds were terrible."

Labels:

Brands: AT&T Mobility, Verizon  
Sentiment: Negative  
Intent: Complaint  
Topic: Network Performance

---

## Implementation Strategy

Each post is evaluated independently for:

- brand references
- emotional tone
- intent
- sentiment
- taxonomy classification

---

## Expected Outcome

Accurate representation of complex customer conversations across multiple dimensions."""