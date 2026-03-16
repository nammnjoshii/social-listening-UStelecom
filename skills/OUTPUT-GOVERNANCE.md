blend and make a 10/10 output governance md skill for claude code

"""

# Output Governance — U.S. Telecom Social Listening

This document defines the **governance framework for post-classification and analytics outputs** in the social listening pipeline for **T-Mobile US** (client) and its main competitors **AT&T Mobility** and **Verizon**. Proper governance ensures **consistent, reliable, and auditable insights** across dashboards and reports.

> **Client:** T-Mobile US | **Competitors:** AT&T Mobility, Verizon

---

## Goals

- **Maintain Stable Taxonomy**  
  Prevent accidental changes that compromise hierarchical consistency (Pillar → Category → Theme → Topic).  

- **Avoid Label Drift**  
  Ensure **sentiment, intent, emotion, and topic labels** remain accurate over time.  

- **Maintain Consistent Schema**  
  Guarantee outputs conform to defined **JSON structures** for multi-label classification, executive insights, and dashboards.  

---

## Governance Rules

1. **Schema Enforcement**  
   - Validate every output against **canonical JSON schemas** before aggregation.  
   - Reject or flag any outputs that **violate schema**.  

2. **Canonical Taxonomy Usage**  
   - Only use **labels from `taxonomy.md`** for topics, themes, categories, and pillars.  
   - Prevent creation of new ad-hoc topics without **formal versioning approval**.  

3. **Version Control for Taxonomy**  
   - Maintain a **versioned taxonomy registry**.  
   - Each change must include **author, timestamp, rationale, and effective date**.  

4. **Claude Output Validation**  
   - Compare LLM predictions against **canonical rules and historical distributions**.  
   - Flag anomalous outputs for human review or automated retraining.  

5. **Avoid Duplication Across Labels**  
   - Ensure distinct topic labels do not overlap.  
   - Example: Avoid creating separate labels for `Customer Support`, `Customer Service`, or `Customer Care`—map all to a **single canonical theme**.  

---

## Best Practices

- **Periodic Audits:** Regularly sample outputs to ensure **compliance and accuracy**.  
- **Automated Checks:** Implement **pipeline-level validation** for schema, brand names, and taxonomy labels.  
- **Clear Documentation:** Track all **taxonomy, classification, and schema changes** in a central repository.  
- **Training Feedback Loop:** Use **misclassified or anomalous posts** to refine Claude prompts and rules.  

---

## Example JSON Validation

```json
{
  "post_id": "12345",
  "brands": ["T-Mobile US", "Verizon"],
  "topic": "Data Speed",
  "intent": "Complaint",
  "emotion": "Frustration",
  "sentiment": "Negative",
  "signal": true,
  "schema_version": "1.2.0",
  "taxonomy_version": "2026-03-15_v1"
}

"""

"""
# Output Governance

## Purpose

Ensure consistent and stable analytics outputs across runs.

---

## Governance Rules

- enforce output schema
- restrict taxonomy vocabulary
- validate classification outputs
- prevent taxonomy drift

---

## Example Problem

Without governance:

Customer Support  
Customer Service  
Customer Care

These represent the same category.

---

## Governance Solution

Standardize taxonomy labels.

---

## Result

Reliable analytics that support long-term trend analysis and executive reporting."""