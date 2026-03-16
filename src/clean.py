"""Preprocessing & noise filtering pipeline.

Implements all rules from NOISE-FILTERING.md:
  - Exact deduplication (SHA-256)
  - Near-duplicate removal (MinHash LSH, Jaccard ≥ 0.85)
  - Spam / promotional filtering
  - Text normalization (lowercase, URL removal, hashtag expansion, @mention masking)
  - Language filtering (English only via langdetect)
  - Minimum-length filtering (≥ 15 words)
"""
from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from collections import Counter

from datasketch import MinHash, MinHashLSH
from langdetect import detect, LangDetectException

from src.config import cfg
from src.models import CleanPost, RawPost

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Promotional phrase blocklist
# ─────────────────────────────────────────────
PROMO_PHRASES: list[str] = [
    "click the link in bio",
    "use code",
    "limited time offer",
    "sign up now",
    "ad:",
    "sponsored",
    "check out our deal",
    "visit our store",
    "dm us for",
    "swipe up",
    "link in bio",
]

URL_RE = re.compile(r"https?://\S+|www\.\S+")
HASHTAG_RE = re.compile(r"#(\w+)")          # expand: keep word, drop #
MENTION_RE = re.compile(r"@\w+")
WHITESPACE_RE = re.compile(r"\s+")
PUNCT_RE = re.compile(r"[^\w\s]")           # used only for MinHash tokenisation


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _normalize(text: str) -> str:
    """Apply full normalization pipeline per NOISE-FILTERING.md §4.3."""
    text = text.lower()
    text = URL_RE.sub(" ", text)
    text = HASHTAG_RE.sub(r"\1 ", text)     # expand: #tmobile → tmobile
    text = MENTION_RE.sub("[USER]", text)
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode()  # strip non-ASCII / emoji
    text = WHITESPACE_RE.sub(" ", text).strip()
    return text


def _word_count(text: str) -> int:
    return len(text.split())


def _is_english(text: str) -> bool:
    try:
        return detect(text) == "en"
    except LangDetectException:
        return False


def _has_promo_phrase(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in PROMO_PHRASES)


def _hashtag_count(raw_text: str) -> int:
    return len(re.findall(r"#\w+", raw_text))


def _is_url_only(text: str) -> bool:
    stripped = URL_RE.sub("", text).strip()
    return len(stripped) == 0


def _minhash(text: str, num_perm: int = 128) -> MinHash:
    tokens = PUNCT_RE.sub("", text.lower()).split()
    m = MinHash(num_perm=num_perm)
    for token in tokens:
        m.update(token.encode())
    return m


# ─────────────────────────────────────────────
# Main filter pipeline
# ─────────────────────────────────────────────
def filter_posts(
    raw_posts: list[RawPost],
    platform_target: int = cfg.posts_per_platform,
) -> tuple[list[CleanPost], dict]:
    """
    Apply full noise filtering pipeline.

    Returns:
        (clean_posts, stats_dict) where stats_dict records removal counts per rule.
    """
    stats: Counter = Counter()
    seen_hashes: set[str] = set()
    clean: list[CleanPost] = []

    # MinHash LSH for near-duplicate detection
    lsh = MinHashLSH(threshold=cfg.near_duplicate_threshold, num_perm=128)
    lsh_keys: set[str] = set()

    for post in raw_posts:
        raw = post.raw_text

        # 0. Official brand account — filter before content-based checks
        if post.is_official_account:
            stats["official_brand_account"] += 1
            continue

        # 1. URL-only
        if _is_url_only(raw):
            stats["url_only"] += 1
            continue

        # 2. Excessive hashtags
        if _hashtag_count(raw) > cfg.max_hashtags:
            stats["hashtag_count"] += 1
            continue

        # 3. Promotional phrase
        if _has_promo_phrase(raw):
            stats["promotional_phrase"] += 1
            continue

        # 4. Normalize text
        normalized = _normalize(raw)

        # 5. Language filter
        if not _is_english(normalized):
            stats["non_english"] += 1
            continue

        # 6. Minimum length
        if _word_count(normalized) < cfg.min_post_words:
            stats["min_length"] += 1
            continue

        # 7. Exact duplicate
        h = _sha256(normalized)
        if h in seen_hashes:
            stats["duplicate"] += 1
            continue
        seen_hashes.add(h)

        # 8. Near-duplicate (MinHash LSH)
        mh = _minhash(normalized)
        if lsh.query(mh) and post.post_id not in lsh_keys:
            stats["near_duplicate"] += 1
            continue
        try:
            lsh.insert(post.post_id, mh)
            lsh_keys.add(post.post_id)
        except ValueError:
            pass  # post_id already inserted (shouldn't happen after exact dedup)

        clean.append(CleanPost(
            post_id=post.post_id,
            platform=post.platform,
            timestamp=post.timestamp,
            normalized_text=normalized,
            signal=True,
            filter_applied=None,
        ))

    # Per-platform cap at target quota (keep highest-engagement posts first)
    # Note: engagement sorting would happen upstream in ingest.py
    from collections import defaultdict
    by_platform: dict[str, list[CleanPost]] = defaultdict(list)
    for p in clean:
        by_platform[p.platform].append(p)

    capped: list[CleanPost] = []
    for platform, posts in by_platform.items():
        kept = posts[:platform_target]
        capped.extend(kept)
        if len(posts) > platform_target:
            stats[f"capped_{platform}"] += len(posts) - platform_target

    total_removed = sum(v for k, v in stats.items() if not k.startswith("capped_"))
    logger.info(
        "Filtering complete — input=%d kept=%d removed=%d | breakdown=%s",
        len(raw_posts), len(capped), total_removed, dict(stats),
    )
    return capped, dict(stats)
