"""Unit tests for src/brand.py — brand entity recognition."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.brand import detect_brands, tag_posts
from src.models import CleanPost


def _make_clean(text: str, post_id: str = "test_001") -> CleanPost:
    return CleanPost(
        post_id=post_id,
        platform="Reddit",
        timestamp=datetime.now(timezone.utc),
        normalized_text=text,
    )


class TestDetectBrands:
    def test_canonical_tmobile(self):
        brands, conf = detect_brands("t-mobile dropped my call again")
        assert "T-Mobile US" in brands
        assert conf == "High"

    def test_alias_magenta(self):
        brands, conf = detect_brands("magenta has the best 5g coverage")
        assert "T-Mobile US" in brands
        assert conf == "Medium"

    def test_alias_uncarrier(self):
        brands, conf = detect_brands("uncarrier just changed their plans again")
        assert "T-Mobile US" in brands

    def test_sprint_legacy(self):
        brands, conf = detect_brands("sprint merged with t-mobile and now service is worse")
        assert "T-Mobile US" in brands

    def test_verizon_canonical(self):
        brands, conf = detect_brands("verizon coverage is excellent in rural areas")
        assert "Verizon" in brands
        assert conf == "High"

    def test_vzw_alias(self):
        brands, _ = detect_brands("vzw raised prices again this month")
        assert "Verizon" in brands

    def test_att_with_ampersand(self):
        brands, conf = detect_brands("at&t support was useless today")
        assert "AT&T Mobility" in brands
        assert conf == "High"

    def test_att_without_ampersand(self):
        brands, _ = detect_brands("att keeps throttling my hotspot data")
        assert "AT&T Mobility" in brands

    def test_multi_brand_detection(self):
        brands, _ = detect_brands("switched from verizon to t-mobile last week")
        assert "T-Mobile US" in brands
        assert "Verizon" in brands

    def test_false_positive_attend(self):
        brands, _ = detect_brands("i need to attend the conference tomorrow")
        assert "AT&T Mobility" not in brands

    def test_no_brand(self):
        brands, _ = detect_brands("the weather is nice today outside")
        assert brands == []

    def test_confidence_lowest_in_multi_brand(self):
        # magenta (Medium) + verizon (High) → should yield Medium overall
        brands, conf = detect_brands("magenta beats verizon on 5g speed")
        assert conf == "Medium"


class TestTagPosts:
    def test_tagged_posts_have_brands(self):
        posts = [
            _make_clean("t-mobile dropped my call on the highway again today", "p001"),
            _make_clean("verizon raised prices for the second time this year what", "p002"),
        ]
        tagged, unresolved = tag_posts(posts)
        assert len(tagged) == 2
        assert len(unresolved) == 0

    def test_unresolved_excluded(self):
        posts = [
            _make_clean("the weather is sunny today and I feel great outside", "no_brand"),
        ]
        tagged, unresolved = tag_posts(posts)
        assert len(tagged) == 0
        assert "no_brand" in unresolved

    def test_is_multi_brand_flag(self):
        posts = [
            _make_clean("switched from verizon to t-mobile for better coverage deal", "multi"),
        ]
        tagged, _ = tag_posts(posts)
        assert tagged[0].is_multi_brand is True

    def test_single_brand_not_multi(self):
        posts = [
            _make_clean("t-mobile has the best 5g network in urban areas everywhere", "single"),
        ]
        tagged, _ = tag_posts(posts)
        assert tagged[0].is_multi_brand is False
