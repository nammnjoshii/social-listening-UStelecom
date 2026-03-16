"""Pipeline configuration — loaded from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    # Claude
    claude_api_key: str = field(default_factory=lambda: os.getenv("CLAUDE_API_KEY", ""))
    claude_model: str = "claude-sonnet-4-6"
    claude_max_tokens: int = 512
    claude_concurrency: int = 3
    claude_batch_size: int = 50

    # Database (SQLite — local file, no server required)
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", "data/telecom.db"))

    # Platform APIs
    # Reddit: no credentials needed — uses free public JSON API
    # Instagram: optional — requires Business account token
    instagram_access_token: str = field(default_factory=lambda: os.getenv("INSTAGRAM_ACCESS_TOKEN", ""))
    instagram_business_account_id: str = field(default_factory=lambda: os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", ""))
    # opentwitter / 6551 API: optional — free token at https://6551.io/mcp
    twitter_6551_token: str = field(default_factory=lambda: os.getenv("TWITTER_TOKEN", ""))

    # YouTube: no API key required (uses youtubesearchpython + youtube-comment-downloader)
    youtube_max_comments_per_video: int = 50
    # App Store reviews: no credentials required (uses google-play-scraper + app-store-scraper)
    app_review_max_per_app: int = 400

    # Pipeline parameters
    posts_per_platform: int = 2000
    collection_buffer_multiplier: int = 2      # collect 2× target to allow attrition
    lookback_days: int = 70                    # 10-week historical window
    min_post_words: int = 15
    max_hashtags: int = 5
    near_duplicate_threshold: float = 0.85     # Jaccard similarity for MinHash LSH
    low_confidence_halt_pct: float = 0.15      # halt if >15% Low confidence
    low_confidence_warn_pct: float = 0.10      # warn if >10% Low confidence

    # Versioning
    taxonomy_version: str = "v1.0.0"
    schema_version: str = "v1.0.0"
    prompt_version: str = "v1.0.0"

    # Canonical values
    brands: tuple[str, ...] = ("T-Mobile US", "Verizon", "AT&T Mobility")
    platforms: tuple[str, ...] = ("Instagram", "Reddit", "X", "YouTube", "AppReview")
    sentiments: tuple[str, ...] = ("Positive", "Neutral", "Negative")
    intents: tuple[str, ...] = ("Complaint", "Inquiry", "Praise", "Recommendation")
    emotions: tuple[str, ...] = ("Frustration", "Satisfaction", "Confusion", "Excitement")
    confidence_levels: tuple[str, ...] = ("High", "Medium", "Low")


# Singleton — import this everywhere
cfg = Config()
