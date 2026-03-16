"""Brand entity recognition.

Implements the canonical alias dictionary and confidence scoring
from BRAND-ENTITY-RECOGNITION.md. Uses word-boundary regex to
prevent false positives (e.g., "attend" ≠ "AT&T").
"""
from __future__ import annotations

import logging
import re

from src.config import cfg
from src.models import BrandTaggedPost, CleanPost

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Canonical alias dictionary
# ─────────────────────────────────────────────
ALIAS_MAP: dict[str, tuple[str, str]] = {
    # (canonical_brand, confidence)
    # T-Mobile US — High
    "t-mobile": ("T-Mobile US", "High"),
    "t-mobile us": ("T-Mobile US", "High"),
    # T-Mobile US — Medium (aliases)
    "tmobile": ("T-Mobile US", "Medium"),
    "t-mo": ("T-Mobile US", "Medium"),
    "tmo": ("T-Mobile US", "Medium"),
    "tmus": ("T-Mobile US", "Medium"),
    "magenta": ("T-Mobile US", "Medium"),
    "magenta max": ("T-Mobile US", "Medium"),
    "uncarrier": ("T-Mobile US", "Medium"),
    # Sprint — legacy T-Mobile, Medium
    "sprint": ("T-Mobile US", "Medium"),

    # Verizon — High
    "verizon": ("Verizon", "High"),
    "verizon wireless": ("Verizon", "High"),
    # Verizon — Medium
    "vzw": ("Verizon", "Medium"),
    "big red": ("Verizon", "Medium"),

    # AT&T Mobility — High
    "at&t": ("AT&T Mobility", "High"),
    "at&t mobility": ("AT&T Mobility", "High"),
    # AT&T Mobility — Medium
    "att": ("AT&T Mobility", "Medium"),
    "at and t": ("AT&T Mobility", "Medium"),
    "at & t": ("AT&T Mobility", "Medium"),
}

# Confidence priority for mixed-confidence multi-brand posts
_CONFIDENCE_RANK = {"High": 3, "Medium": 2, "Low": 1}


def _compile_patterns() -> list[tuple[re.Pattern, str, str]]:
    """Build sorted (longest-first) compiled regex patterns."""
    patterns = []
    for alias, (brand, confidence) in ALIAS_MAP.items():
        escaped = re.escape(alias)
        # Word-boundary match, case-insensitive
        pattern = re.compile(r"\b" + escaped + r"\b", re.IGNORECASE)
        patterns.append((pattern, brand, confidence))
    # Sort longest alias first to prefer specific matches
    patterns.sort(key=lambda x: -len(x[0].pattern))
    return patterns


_PATTERNS = _compile_patterns()


def detect_brands(text: str) -> tuple[list[str], str]:
    """
    Return (canonical_brands_list, lowest_confidence_among_detected).
    Empty list means no brand was detected.
    """
    found: dict[str, str] = {}  # brand → highest confidence detected

    for pattern, brand, confidence in _PATTERNS:
        if pattern.search(text):
            existing = found.get(brand)
            if existing is None or _CONFIDENCE_RANK[confidence] > _CONFIDENCE_RANK[existing]:
                found[brand] = confidence

    if not found:
        return [], "Low"

    brands = list(found.keys())
    # Overall confidence = lowest across all detected brands
    min_confidence = min(found.values(), key=lambda c: _CONFIDENCE_RANK[c])
    return brands, min_confidence


def tag_posts(clean_posts: list[CleanPost]) -> tuple[list[BrandTaggedPost], list[str]]:
    """
    Tag each post with detected brands. Returns:
      - tagged_posts: posts with at least one confirmed brand
      - unresolved_ids: post_ids with no brand match (excluded from pipeline)
    """
    tagged: list[BrandTaggedPost] = []
    unresolved: list[str] = []

    for post in clean_posts:
        brands, confidence = detect_brands(post.normalized_text)

        if not brands:
            unresolved.append(post.post_id)
            logger.debug("No brand detected in post %s", post.post_id)
            continue

        tagged.append(BrandTaggedPost(
            post_id=post.post_id,
            platform=post.platform,
            timestamp=post.timestamp,
            normalized_text=post.normalized_text,
            brands=brands,
            brand_confidence=confidence,
            is_multi_brand=len(brands) > 1,
        ))

    logger.info(
        "Brand tagging — tagged=%d unresolved=%d",
        len(tagged), len(unresolved),
    )
    return tagged, unresolved
