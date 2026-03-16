# Executive Insight Generation — U.S. Telecom Social Listening

This document defines **how post-level analytics and social listening data are transformed into concise, actionable insights** for telecom leadership.
The output is **executive-ready narratives** derived from Claude-classified posts, taxonomy trends, and aggregated metrics for **T-Mobile US** (client) benchmarked against its main competitors **AT&T Mobility** and **Verizon**.

> **Client:** T-Mobile US | **Competitors:** AT&T Mobility, Verizon

---

## 1. Purpose

- Translate **raw analytics into high-level, actionable insights**.  
- Support **decision-making for leadership teams** across customer experience, network operations, and brand management.  
- Highlight **emerging issues, sentiment trends, and competitive positioning**.  

---

## 2. Insight Categories

Insights generated should focus on:

1. **Emerging Complaints**  
   - Detect new or trending issues in network, billing, device, or support.  

2. **Sentiment Shifts**  
   - Identify rapid changes in positive, neutral, or negative sentiment.  

3. **Brand Comparison**  
   - Compare conversation volume, sentiment, intent, and emotional signals across brands.  

4. **Competitive Perception**  
   - Highlight discussions comparing brands, including multi-brand posts.  

5. **Service Disruptions**  
   - Detect outages, slowdowns, or operational failures impacting customers.  

---

## 3. Example Insight Templates

| Insight Type | Example |
|--------------|---------|
| Emerging Complaint | "T-Mobile US reports rising complaints about LTE coverage in suburban areas over the past 7 days." |
| Sentiment Shift | "Verizon experienced a spike in negative sentiment due to call center delays, increasing 20% from the previous week." |
| Brand Comparison | "AT&T Mobility outperformed Verizon in customer satisfaction following recent trade-in promotions." |
| Service Disruption | "Verizon network outages affected major urban centers for 2 hours, triggering elevated frustration in social media posts." |

**Guidelines:**

- Keep insights **short, clear, and actionable**.  
- Include **brand, topic, time window, and trend magnitude**.  
- Highlight **emerging patterns or anomalies**.  

---

## 4. Requirements

1. **Actionable**  
   - Provide clear next steps or areas requiring leadership attention.  

2. **Telecom-Specific**  
   - Focus on network, service, billing, device, and plan experiences.  

3. **Data-Driven**  
   - Each insight must be backed by **taxonomy volumes, sentiment, intent, or emotion trends**.  

4. **Executive-Friendly**  
   - Avoid technical jargon; concise, results-focused language.  

---

## 5. Best Practices

- Combine outputs from **Claude taxonomy, sentiment, intent, and emotion classification**.  
- Use **cross-brand and cross-platform context** for comparative insights.  
- Prioritize **emerging complaints and high-impact topics**.  
- Update insights **daily or per ingestion cycle** for real-time decision support.  
- Maintain **auditability**: log source posts, metrics, and taxonomy references for each insight.

---

## 6. Output Schema

Each executive insight should follow **structured JSON**:

```json
{
  "brand": "Verizon",
  "topic": "5G Performance",
  "trend": "Increasing complaints",
  "sentiment": "Negative",
  "time_window": "Last 48 hours",
  "insight_text": "Verizon saw rising frustration tied to 5G performance in urban areas over the past 48 hours."
}

Notes:

Multiple insights per brand are allowed.

Insights may reference multi-brand posts with appropriate attribution.

Feed structured outputs into dashboards, reports, or alerts for leadership.