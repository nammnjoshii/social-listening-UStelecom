"""Pydantic models — canonical data contracts for the pipeline.

Aligned with OUTPUT-SCHEMA.md. Every Claude output and DB record
must validate against PostClassification before proceeding.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Platform = Literal["Instagram", "Reddit", "X", "YouTube", "AppReview"]
Brand = Literal["T-Mobile US", "Verizon", "AT&T Mobility"]
Sentiment = Literal["Positive", "Neutral", "Negative"]
Intent = Literal["Complaint", "Inquiry", "Praise", "Recommendation"]
Emotion = Literal["Frustration", "Satisfaction", "Confusion", "Excitement"]
BrandConfidence = Literal["High", "Medium", "Low"]
ClassificationConfidence = Literal["High", "Medium", "Low"]
ClassificationStatus = Literal["success", "failed", "retry", "flagged"]


class RawPost(BaseModel):
    """Staging record written by ingest.py before any processing."""
    post_id: str
    platform: Platform
    timestamp: datetime
    raw_text: str
    author_id: str = "[ANONYMIZED]"
    engagement_metrics: dict[str, int] = Field(default_factory=dict)
    brand_keywords_matched: list[str] = Field(default_factory=list)


class CleanPost(BaseModel):
    """Post after noise filtering and text normalization."""
    post_id: str
    platform: Platform
    timestamp: datetime
    normalized_text: str
    signal: bool = True
    filter_applied: str | None = None


class BrandTaggedPost(BaseModel):
    """Post after brand entity recognition."""
    post_id: str
    platform: Platform
    timestamp: datetime
    normalized_text: str
    brands: list[Brand]
    brand_confidence: BrandConfidence
    is_multi_brand: bool

    @model_validator(mode="after")
    def set_multi_brand(self) -> BrandTaggedPost:
        object.__setattr__(self, "is_multi_brand", len(self.brands) > 1)
        return self


class PostClassification(BaseModel):
    """Full per-post output record — written to the posts table."""
    post_id: str
    platform: Platform
    timestamp: datetime
    normalized_text: str
    brands: list[Brand]
    brand_confidence: BrandConfidence
    is_multi_brand: bool
    pillar: str
    category: str
    theme: str
    topic: str
    sentiment: Sentiment
    intent: Intent
    emotion: Emotion
    confidence: ClassificationConfidence
    classification_status: ClassificationStatus
    taxonomy_version: str
    schema_version: str
    pipeline_run_id: str
    supersedes: str | None = None

    @model_validator(mode="after")
    def flag_low_confidence(self) -> PostClassification:
        if self.confidence == "Low" and self.classification_status == "success":
            object.__setattr__(self, "classification_status", "flagged")
        return self


class AggregatedMetrics(BaseModel):
    """Brand-level aggregated metrics for the dashboard."""
    pipeline_run_id: str
    taxonomy_version: str
    schema_version: str
    period_start: datetime
    period_end: datetime
    brand: str
    total_posts: int
    conversation_share_pct: float
    positive_pct: float
    neutral_pct: float
    negative_pct: float
    net_sentiment_score: float          # % Positive − % Negative
    complaint_pct: float
    inquiry_pct: float
    praise_pct: float
    recommendation_pct: float
    complaint_to_praise_ratio: float
    frustration_pct: float
    satisfaction_pct: float
    confusion_pct: float
    excitement_pct: float


class ExecutiveInsight(BaseModel):
    """Claude-generated weekly executive brief."""
    pipeline_run_id: str
    generated_at: datetime
    top_complaints: list[dict]
    emerging_topics: list[dict]
    sentiment_gaps: dict
    emotion_signals: dict
    strategic_recommendations: list[str]
    conversation_share: dict = {}        # brand → share %
    intent_distribution: dict = {}       # brand → {Complaint, Inquiry, Praise, Recommendation} %
    topic_hierarchy: list[dict] = []     # top topics with pillar/category/theme/topic + volume
    data_quality_notes: list[str] = []  # platform coverage caveats


class PlatformScore(BaseModel):
    """Per-platform quality score produced by src/experiment.py."""
    experiment_run_id: str
    pipeline_run_id: str
    platform: str
    post_count: int
    snr_pct: float                # % posts that are genuine telecom signals
    complaint_rate_pct: float     # % posts classified as Complaint
    topic_diversity_score: float  # distinct topics, normalised 0–100
    sentiment_clarity_pct: float  # % posts with High confidence
    composite_score: float
    rank: int
    recommended_allocation: int   # suggested posts per run
    computed_at: datetime
