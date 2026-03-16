"""Unit tests for src/clean.py — noise filtering and text normalization."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.clean import (
    _hashtag_count,
    _has_promo_phrase,
    _is_english,
    _is_url_only,
    _normalize,
    _word_count,
    filter_posts,
)
from src.models import RawPost


def _make_post(text: str, platform: str = "Reddit", post_id: str = "test_001") -> RawPost:
    return RawPost(
        post_id=post_id,
        platform=platform,
        timestamp=datetime.now(timezone.utc),
        raw_text=text,
    )


# ── Normalization ──────────────────────────────────────────────────────
class TestNormalize:
    def test_lowercase(self):
        assert _normalize("T-Mobile IS Great") == "t-mobile is great"

    def test_url_removal(self):
        result = _normalize("Check https://tmobile.com for deals")
        assert "https" not in result
        assert "tmobile.com" not in result

    def test_hashtag_expansion(self):
        result = _normalize("#tmobile is great #5g")
        assert "tmobile" in result
        assert "5g" in result
        assert "#" not in result

    def test_mention_masking(self):
        result = _normalize("Thanks @TMobileHelp for the fix")
        assert "@" not in result
        assert "[USER]" in result

    def test_emoji_stripped(self):
        result = _normalize("T-Mobile is 🔥 amazing 📱")
        assert "🔥" not in result
        assert "📱" not in result

    def test_whitespace_collapsed(self):
        result = _normalize("too   many    spaces")
        assert "  " not in result


# ── Filter rules ───────────────────────────────────────────────────────
class TestFilterRules:
    def test_url_only_detected(self):
        assert _is_url_only("https://example.com/deal")

    def test_not_url_only_when_has_text(self):
        assert not _is_url_only("Check this out https://example.com")

    def test_hashtag_count(self):
        assert _hashtag_count("#a #b #c #d #e #f") == 6
        assert _hashtag_count("#tmobile #verizon") == 2

    def test_promo_phrase_detected(self):
        assert _has_promo_phrase("Click the link in bio to get a deal")
        assert _has_promo_phrase("Use code SAVE20 for discount")

    def test_no_promo_in_organic_post(self):
        assert not _has_promo_phrase("T-Mobile dropped my call again on the highway")

    def test_word_count(self):
        assert _word_count("t-mobile signal dropped again on the subway today") == 8
        assert _word_count("short") == 1


# ── Full filter pipeline ───────────────────────────────────────────────
class TestFilterPosts:
    def _make_batch(self) -> list[RawPost]:
        posts = [
            _make_post("T-Mobile signal dropped again on the subway and now I am really angry about the terrible coverage", "Reddit", "p001"),
            _make_post("https://tmobile.com/deals", "X", "p002"),             # URL only
            _make_post("#a #b #c #d #e #f tmobile", "Instagram", "p003"),     # Too many hashtags
            _make_post("click the link in bio for t-mobile discount", "Instagram", "p004"),  # Promo
            _make_post("t-mobile service bad today", "Reddit", "p005"),          # Too short (<15 words)
            _make_post("Verizon coverage is absolutely terrible in rural areas and no one seems to care about fixing it", "Reddit", "p006"),
        ]
        return posts

    def test_removes_noise(self):
        posts = self._make_batch()
        clean, stats = filter_posts(posts, platform_target=500)
        clean_ids = {p.post_id for p in clean}
        assert "p002" not in clean_ids   # URL only
        assert "p003" not in clean_ids   # Too many hashtags
        assert "p004" not in clean_ids   # Promo
        assert "p005" not in clean_ids   # Too short

    def test_keeps_signal_posts(self):
        posts = self._make_batch()
        clean, _ = filter_posts(posts, platform_target=500)
        clean_ids = {p.post_id for p in clean}
        assert "p001" in clean_ids
        assert "p006" in clean_ids

    def test_stats_populated(self):
        posts = self._make_batch()
        _, stats = filter_posts(posts, platform_target=500)
        assert stats.get("url_only", 0) >= 1
        assert stats.get("hashtag_count", 0) >= 1
        assert stats.get("promotional_phrase", 0) >= 1
        assert stats.get("min_length", 0) >= 1

    def test_normalized_text_no_hashtag_symbol(self):
        posts = [_make_post("#tmobile dropped my call again on the highway today morning", "X", "p010")]
        clean, _ = filter_posts(posts, platform_target=500)
        if clean:
            assert "#" not in clean[0].normalized_text
            assert "tmobile" in clean[0].normalized_text
