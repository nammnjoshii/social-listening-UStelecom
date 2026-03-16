blend and make a 10/10 hierarchical taxonomy md skill for claude code 

"""
# Hierarchical Taxonomy Design — U.S. Telecom Social Listening

This document defines the **hierarchical taxonomy structure** used to classify social media conversations for **T-Mobile US** (client) and its main competitors **AT&T Mobility** and **Verizon**. It ensures consistency, operational meaning, and integration with Claude-powered pipelines.

> **Client:** T-Mobile US | **Competitors:** AT&T Mobility, Verizon

---

## Structure


Pillar → Category → Theme → Topic


- **Pillar:** Highest-level domain (e.g., Network Performance, Customer Experience)  
- **Category:** Sub-domain under Pillar (e.g., Coverage, Support)  
- **Theme:** Group of related topics (e.g., Urban Coverage, Call Center)  
- **Topic:** Most granular unit; actionable discussion point (e.g., “subway dead zones,” “long wait times”)  

---

## Requirements

1. **Single Parent per Node**  
   - Each child must have exactly **one parent** in the level above.  
2. **No Duplicates**  
   - Each Topic must be unique and mapped to only one Theme.  
3. **Clear Hierarchy**  
   - Logical flow from Pillar → Topic; prevents ambiguity in analysis.  
4. **Operationally Meaningful Topics**  
   - Topics must reflect actionable or monitorable customer experience insights.

---

## Benefits

- **Structured Insights:** Allows coherent grouping and analysis of customer conversations.  
- **Easy Aggregation:** Facilitates metrics calculation at multiple levels (Pillar → Topic).  
- **Executive-Ready Metrics:** Supports dashboards, trend charts, and decision-making.  

---

## Canonical Taxonomy

- The **master taxonomy** is stored in: `taxonomy.md`  
- All topic discovery, Claude prompts, and dashboard aggregation **reference this file**.  
- Periodically update `taxonomy.md` as new topics emerge or obsolete topics are retired.

---

## Notes & Best Practices

- Use **taxonomy governance** to prevent drift and duplication.  
- Ensure **Claude prompts** explicitly reference this hierarchy for post classification.  
- Apply **versioning** for each iteration of the taxonomy to track changes over time.  
- Integrate with **brand recognition, sentiment, and intent modules** for end-to-end analysis.

"""

"""

# Hierarchical Taxonomy Design

## Purpose

Customer discussions are organized into a hierarchical taxonomy to transform raw conversations into structured business insights.

Hierarchy structure:

Pillar → Category → Theme → Topic

---

## Example Telecom Taxonomy

| Pillar | Category | Theme | Topic |
|------|------|------|------|
Network Performance | Coverage | Urban Coverage | Signal loss in subway |
Customer Experience | Support | Call Center | Long wait times |
Pricing & Plans | Billing | Billing Transparency | Unexpected charges |

---

## Taxonomy Requirements

A valid taxonomy must satisfy the following:

- each topic has a single parent theme
- each theme belongs to one category
- each category belongs to one pillar

---

## Benefits

This hierarchy allows executives to trace customer feedback from:

strategic business areas → specific operational issues."""