# System Architecture — U.S. Telecom Social Listening Intelligence

## Overview

This document describes the **enterprise-grade architecture** powering the telecom social listening intelligence system. The pipeline analyzes social media conversations for **T-Mobile US** (client) and its main competitors **AT&T Mobility** and **Verizon**, extracts structured insights, and feeds an **executive dashboard**.

> **Client:** T-Mobile US | **Competitors:** AT&T Mobility, Verizon  

Claude is the **central LLM** driving topic discovery, taxonomy creation, and post-level attribute extraction (sentiment, intent, emotion).

---

## Architectural Components

1. **Social Media Data Ingestion**  
   - Collects posts from Instagram, Reddit, and X (Twitter)  
   - Stratified sampling: 500 posts per platform (1,500 total)  
   - Time window: last 7 days

2. **Preprocessing & Noise Filtering**  
   - Deduplication and spam removal  
   - Text normalization  
   - Removal of non-customer experience posts  

3. **Brand Entity Recognition**  
   - Detects mentions of T-Mobile US, Verizon, and AT&T Mobility  
   - Normalizes brand variations and multi-brand references  

4. **Claude Intelligence Layer**  
   - Performs semantic reasoning on posts:  
     - Topic discovery  
     - Dynamic taxonomy creation (Pillar → Category → Theme → Topic)  
     - Sentiment classification (Positive, Neutral, Negative)  
     - Intent detection (Complaint, Inquiry, Praise, Recommendation)  
     - Emotion extraction (Frustration, Satisfaction, Confusion, Excitement)  

5. **Aggregation & Trend Engine**  
   - Computes brand-level metrics: conversation share, sentiment distribution, intent trends, emotion signals  
   - Tracks 7-day trends and emerging topics  

6. **Executive Dashboard**  
   - Visualizes key insights for leadership:  
     - Brand comparison charts  
     - Topic hierarchy tables  
     - Sentiment and intent trends  
     - Complaint volume and emotion distributions  

---

## Architectural Flow

```text
Social Media Platforms (Instagram, Reddit, X)
           │
           ▼
   Data Ingestion Layer
           │
           ▼
    Preprocessing & Noise Filtering
           │
           ▼
     Stratified Sampling
      (500 posts/platform)
           │
           ▼
     Brand Entity Recognition
           │
           ▼
       Claude Intelligence Layer
    ┌───────────────┬───────────────┐
    │Topic Discovery│Sentiment Analysis│
    │Taxonomy Creation│Intent Detection│
    │                 Emotion Extraction│
    └───────────────┴───────────────┘
           │
           ▼
     Analytics Aggregation
           │
           ▼
     Executive Dashboard