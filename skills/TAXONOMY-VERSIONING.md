# Taxonomy Versioning — U.S. Telecom Social Listening

This document defines the **versioning framework for hierarchical taxonomies** used in the Claude Code social listening pipeline for **T-Mobile US** (client) and its main competitors **AT&T Mobility** and **Verizon**. Proper versioning ensures **historical consistency, reproducibility, and executive-level trust**.

> **Client:** T-Mobile US | **Competitors:** AT&T Mobility, Verizon

---

## 1. Why Version?

- **Prevent Breaking Historical Trends:** Changes to taxonomy labels or structure can invalidate comparisons across time.  
- **Enable Auditable Analysis:** Each dataset and dashboard can be traced to a specific taxonomy version.  
- **Facilitate Controlled Updates:** New topics or hierarchical adjustments can be introduced **without affecting past analytics**.

---

## 2. Versioning Rules

| Rule | Description |
|------|-------------|
| **Semantic Versioning** | Use `MAJOR.MINOR.PATCH` format (e.g., 1.2.0) |
| **Backward-Compatible by Default** | Add new topics or subcategories **without renaming existing nodes** |
| **Topic Renaming** | Never rename a topic directly. Map old → new labels using a **migration dictionary** |
| **Deprecation** | Mark obsolete topics as deprecated but retain them for historical data |

---

## 3. File Management

- **Canonical Files:**  
  - `taxonomy_v1.json` → initial version  
  - `taxonomy_v2.json` → updated version  
- **Version Metadata:** Include:  
  - `version_number`  
  - `date_created`  
  - `author`  
  - `change_summary`  
- **Migration Tables:** Maintain a mapping of renamed or merged topics for backward compatibility.

---

## 4. Best Practices

- **Reference Version in Output:** Each post JSON should include `taxonomy_version` for traceability.  
- **Dashboard Consistency:** Use the same taxonomy version across **aggregation and executive dashboards**.  
- **Change Documentation:** Log **all additions, merges, deprecations, or structural changes**.  
- **Integration with Governance:** Ensure all versioned taxonomies comply with `output-governance.md` rules.  
- **Testing:** Validate new versions against **sample historical posts** to ensure **no conflicts or misclassifications**.

---

## 5. Example JSON Metadata

```json
{
  "taxonomy_version": "2.0.0",
  "date_created": "2026-03-15",
  "author": "Data Science Team",
  "change_summary": "Added new topics for 5G mid-band coverage and urban outages; deprecated old LTE speed topics"
}