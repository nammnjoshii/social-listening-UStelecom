# U.S. Telecom Social Listening Intelligence Dashboard

## Overview

This project analyzes social media conversations about major U.S. telecom providers and produces an **executive social listening dashboard**.

> **Client:** T-Mobile US | **Competitors:** AT&T Mobility, Verizon

The analysis focuses on the following companies:

- **T-Mobile US** *(client)*
- Verizon *(competitor)*
- AT&T Mobility *(competitor)*

Customer conversations are collected from major social media platforms and analyzed using large language model (LLM) assisted workflows.

The system extracts structured insights including:

- discussion topics
- sentiment
- customer intent
- emotional signals

These insights are organized into a hierarchical taxonomy and aggregated into executive-level metrics.

---

# Business Objective

Enable telecom leadership teams to monitor:

- customer sentiment
- emerging service issues
- brand perception
- competitive positioning

The final output is an **executive dashboard comparing the three telecom providers across social listening metrics.**

---

# Data Scope

The analysis uses recent social media conversations collected from:

- Instagram
- Reddit
- X (Twitter)

### Sampling Strategy

Posts are collected using **stratified sampling** to ensure balanced platform representation.

| Platform | Sample Size |
|--------|--------|
Instagram | 500 posts |
Reddit | 500 posts |
X (Twitter) | 500 posts |

**Total dataset size:** 1,500 posts

### Time Window

Posts are collected from the **last 7 days**.

### Brand Filter

Posts must reference at least one of:

- **T-Mobile US** *(client)*
- Verizon *(competitor)*
- AT&T Mobility *(competitor)*

Posts referencing multiple brands are tagged accordingly.

---

# Analytics Framework

The system extracts four types of insights.

## 1 Topic Hierarchy

Customer discussions are structured into a taxonomy.


Example:

| Pillar | Category | Theme | Topic |
|------|------|------|------|
Network Performance | Coverage | Urban Coverage | Signal loss in subway |
Customer Experience | Support | Call Center | Long wait times |
Pricing & Plans | Billing | Billing Transparency | Unexpected charges |

---

## 2 Sentiment Analysis

Classifies post polarity:

- Positive
- Neutral
- Negative

---

## 3 Customer Intent

Identifies the purpose of the post.

Intent categories:

- Complaint
- Inquiry
- Praise
- Recommendation

---

## 4 Emotion Detection

Emotional signals expressed in the post.

Examples:

- Frustration
- Satisfaction
- Confusion
- Excitement

---

# Executive Dashboard Metrics

The dashboard provides a comparative view across the three telecom providers.

Key metrics include:

### Conversation Share

Percentage of discussions mentioning each brand.

### Sentiment Distribution

Positive / Neutral / Negative breakdown.

### Topic Hierarchy Analysis

Discussion volume by:

### Customer Intent Trends

Complaint vs praise vs inquiry volume.

### Emotion Signals

Emotional sentiment across brands.

---

# Comparative Trend Charts (Last 7 Days)

The dashboard includes cross-company trend analysis for:

- conversation volume
- sentiment trends
- complaint trends
- emotion signals
- topic volume

These charts enable leadership teams to detect:

- service disruptions
- emerging operational issues
- changes in customer perception

---

# Documentation

| File | Purpose |
|-----|-----|
CLAUDE.md | Prompt engineering strategy |
WORKFLOW.md | Data processing pipeline |
ARCHITECTURE.md | System design |

---

# Final Deliverable

An **executive social listening dashboard** comparing **T-Mobile US** (client) against its main competitors **AT&T Mobility** and **Verizon**:

- **T-Mobile US** *(client)*
- Verizon *(competitor)*
- AT&T Mobility *(competitor)*

The dashboard highlights:

- customer complaints
- emerging discussion themes
- sentiment trends
- brand comparison metrics

This enables leadership teams to quickly identify operational issues and monitor customer experience signals across social media.


