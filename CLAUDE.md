# Claude Usage Guide

## Purpose

Claude is used as the primary reasoning engine for analyzing social media conversations and generating structured insights.

Claude performs the following tasks:

- topic discovery
- taxonomy construction
- post classification
- sentiment analysis
- intent detection
- emotion detection
- insight summarization

---

# Input Data

> **Client:** T-Mobile US | **Competitors:** AT&T Mobility, Verizon

Claude processes a dataset consisting of:

- 1,500 social media posts
- collected within the last 7 days
- sourced from:
  - Instagram
  - Reddit
  - X (Twitter)

Posts reference at least one of:

- **T-Mobile US** *(client)*
- Verizon *(competitor)*
- AT&T Mobility *(competitor)*

---

# Task 1: Topic Discovery

Claude analyzes posts to identify recurring telecom discussion themes.

The output taxonomy follows this hierarchy:


Pillar → Category → Theme → Topic


Prompt example:


Analyze the following telecom social media posts.

Identify recurring discussion topics and organize them using the structure:

Pillar → Category → Theme → Topic

Ensure topics are concise and logically grouped.


---

# Task 2: Post Classification

Each post is mapped to the taxonomy.

Prompt example:


Classify the following telecom social media post using this taxonomy:

Pillar → Category → Theme → Topic


---

# Task 3: Sentiment Detection

Claude classifies the sentiment of each post.

Possible labels:

- Positive
- Neutral
- Negative

Prompt example:


Determine the sentiment expressed in this telecom-related post.


---

# Task 4: Intent Detection

Claude identifies why the user posted.

Intent categories:

- Complaint
- Inquiry
- Praise
- Recommendation

Prompt example:


Identify the intent of the user in this telecom social media post.


---

# Task 5: Emotion Detection

Claude extracts emotional tone.

Possible labels:

- Frustration
- Satisfaction
- Confusion
- Excitement

Prompt example:


Identify the emotional tone expressed in this post.


---

# Task 6: Insight Generation

Claude generates executive insights such as:

- top complaints
- emerging topics
- sentiment shifts

Prompt example:


Summarize key insights for telecom executives based on this dataset.


---

# Output Format

Claude outputs structured JSON for downstream analytics.

Example:

```json
{
  "brand": "Verizon",
  "sentiment": "Negative",
  "intent": "Complaint",
  "emotion": "Frustration",
  "pillar": "Network Performance",
  "category": "Coverage",
  "theme": "Urban Coverage",
  "topic": "Signal loss in subway"
}

Structured outputs allow easy integration into analytics pipelines.


---

# WORKFLOW.md

```markdown
# Data Processing Workflow

## Overview

This document describes the step-by-step workflow used to generate social listening insights for telecom companies.

---

# Step 1: Data Collection

Social media posts are collected from:

- Instagram
- Reddit
- X (Twitter)

Filtering rules:

- must reference telecom providers
- must be posted within the last 7 days

---

# Step 2: Stratified Sampling

To ensure balanced analysis, the system collects:

| Platform | Posts |
|------|------|
Instagram | 500 |
Reddit | 500 |
X (Twitter) | 500 |

Total dataset:

1,500 posts

---

# Step 3: Data Cleaning

The dataset is cleaned to remove:

- duplicates
- spam
- promotional content
- irrelevant mentions

Text normalization includes:

- URL removal
- hashtag cleanup
- lowercase conversion

---

# Step 4: Brand Tagging

Posts are scanned for references to:

- **T-Mobile US** *(client)*
- Verizon *(competitor)*
- AT&T Mobility *(competitor)*

Posts may contain multiple brands.

---

# Step 5: Topic Discovery

Claude analyzes posts and identifies recurring discussion themes.

The taxonomy is generated using the hierarchy:


Pillar → Category → Theme → Topic


---

# Step 6: Post Classification

Each post is mapped to the taxonomy.

Example classification:


Network Performance → Coverage → Urban Coverage → Signal loss in subway


---

# Step 7: Sentiment Analysis

Each post receives a sentiment label.

Possible values:

- Positive
- Neutral
- Negative

---

# Step 8: Intent Detection

Intent categories include:

- Complaint
- Inquiry
- Praise
- Recommendation

---

# Step 9: Emotion Detection

Claude identifies emotional signals.

Examples:

- Frustration
- Satisfaction
- Confusion
- Excitement

---

# Step 10: Data Aggregation

Results are aggregated to produce dashboard metrics.

Examples:

- conversation share
- sentiment distribution
- complaint frequency
- topic volume

---

# Step 11: Trend Analysis

Trend charts are generated for the last 7 days.

Comparisons include:

- brand conversation volume
- sentiment trends
- complaint trends
- emotional signals

---

# Step 12: Dashboard Generation

The final dataset is used to generate an executive social listening dashboard.