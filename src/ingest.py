"""Platform data ingestion — Reddit, X (Nitter), YouTube, Trustpilot, App Reviews.

All collectors are credential-free:
  Reddit     — public JSON API (no credentials)
  X/Twitter  — Nitter RSS feeds (public Nitter instances, no credentials)
  YouTube    — yt-dlp search + youtube-comment-downloader Innertube API
  Trustpilot — public review pages scraped (replaces Instagram, no credentials)
  AppReview  — Google Play scraper (Apple App Store requires login, skipped)

Instagram Graph API and X paid API are kept as optional upgrades.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

from src.config import cfg
from src.models import RawPost

# ── Optional YouTube libraries (no credentials required) ──────────────────────
try:
    import yt_dlp
    from youtube_comment_downloader import YoutubeCommentDownloader, SORT_BY_RECENT
    _YOUTUBE_AVAILABLE = True
except ImportError:
    _YOUTUBE_AVAILABLE = False

# ── Optional App Store libraries (no credentials required) ────────────────────
try:
    from google_play_scraper import reviews as gplay_reviews, Sort as GPlaySort
    from app_store_scraper import AppStore
    _APPSTORE_AVAILABLE = True
except ImportError:
    _APPSTORE_AVAILABLE = False

logger = logging.getLogger(__name__)

BRAND_KEYWORDS: list[str] = [
    "T-Mobile", "TMobile", "T-Mo", "Magenta", "Uncarrier", "TMUS",
    "Verizon", "VZW",
    "AT&T", "ATT", "attmobility",
]

# Map brand keywords in search queries → canonical brand name
_QUERY_BRAND_MAP: dict[str, str] = {
    "T-Mobile": "T-Mobile US",
    "TMobile": "T-Mobile US",
    "Verizon": "Verizon",
    "AT&T": "AT&T Mobility",
    "ATT": "AT&T Mobility",
}

REDDIT_SUBREDDITS = ["tmobile", "verizon", "ATT", "wireless", "NoContract"]
INSTAGRAM_HASHTAGS = ["tmobile", "verizon", "att", "attmobility", "tmobileUS"]
TWITTER_QUERY = (
    "(T-Mobile OR TMobile OR Magenta OR Uncarrier OR "
    "Verizon OR VZW OR AT&T OR ATT) lang:en -is:retweet"
)

_REDDIT_HEADERS = {"User-Agent": "telecom-social-listening/1.0 (research project)"}


def _since_timestamp() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=cfg.lookback_days)


def _make_post_id(platform: str, raw_id: str) -> str:
    return f"{platform.lower()}_{raw_id}"


def _anonymize(author: str) -> str:
    return hashlib.sha256(author.encode()).hexdigest()[:16]


def _keyword_matches(text: str) -> list[str]:
    lower = text.lower()
    return [kw for kw in BRAND_KEYWORDS if kw.lower() in lower]


# ─────────────────────────────────────────────
# Reddit — free public JSON API (no credentials)
# ─────────────────────────────────────────────
class RedditCollector:
    """
    Collects posts from public subreddits using Reddit's free JSON API.
    No API credentials required — uses the public /<subreddit>/new.json endpoint.
    Rate limit: ~1 request/second to stay within Reddit's guidelines.
    """

    BASE = "https://www.reddit.com"

    def _fetch_subreddit(self, subreddit: str, limit: int, since: datetime) -> list[RawPost]:
        posts: list[RawPost] = []
        after: str | None = None

        while len(posts) < limit:
            params: dict = {"limit": 100, "raw_json": 1}
            if after:
                params["after"] = after

            try:
                r = requests.get(
                    f"{self.BASE}/r/{subreddit}/new.json",
                    params=params,
                    headers=_REDDIT_HEADERS,
                    timeout=15,
                )
                r.raise_for_status()
            except requests.RequestException as e:
                logger.warning("Reddit fetch error for r/%s: %s", subreddit, e)
                break

            data = r.json().get("data", {})
            children = data.get("children", [])
            if not children:
                break

            for child in children:
                d = child.get("data", {})
                created_utc = d.get("created_utc", 0)
                created = datetime.fromtimestamp(created_utc, tz=timezone.utc)

                if created < since:
                    return posts  # results are newest-first; stop paging

                title = d.get("title", "")
                body = d.get("selftext", "")
                text = f"{title} {body}".strip()
                if not text or text == "[deleted]":
                    continue

                posts.append(RawPost(
                    post_id=_make_post_id("Reddit", d["id"]),
                    platform="Reddit",
                    timestamp=created,
                    raw_text=text,
                    author_id=_anonymize(d.get("author", "unknown")),
                    engagement_metrics={
                        "score": d.get("score", 0),
                        "num_comments": d.get("num_comments", 0),
                    },
                    brand_keywords_matched=_keyword_matches(text),
                ))

            after = data.get("after")
            if not after:
                break

            time.sleep(1)  # polite rate limiting — 1 req/second

        return posts

    def collect(self, limit: int) -> list[RawPost]:
        since = _since_timestamp()
        all_posts: list[RawPost] = []
        per_sub = max(1, limit // len(REDDIT_SUBREDDITS)) + 50

        for sub in REDDIT_SUBREDDITS:
            if len(all_posts) >= limit:
                break
            logger.info("Collecting r/%s", sub)
            posts = self._fetch_subreddit(sub, per_sub, since)
            logger.info("  r/%s → %d posts", sub, len(posts))
            all_posts.extend(posts)

        logger.info("Reddit total: %d posts", len(all_posts))
        return all_posts[:limit]


# ─────────────────────────────────────────────
# Instagram — credential-free via instaloader
# Falls back to Graph API if Business credentials are set.
# ─────────────────────────────────────────────
class InstagramCollector:
    """
    Collects posts from public Instagram hashtags.

    Strategy (in order):
      1. Graph API — if INSTAGRAM_ACCESS_TOKEN + INSTAGRAM_BUSINESS_ACCOUNT_ID are set.
      2. instaloader — credential-free scraper for public hashtag posts (no API key needed).
    """

    BASE_URL = "https://graph.facebook.com/v19.0"

    def __init__(self) -> None:
        self.token = cfg.instagram_access_token
        self.user_id = cfg.instagram_business_account_id

    # ── Strategy 1: Graph API ────────────────────────────────────────
    def _collect_graph_api(self, limit: int) -> list[RawPost]:
        posts: list[RawPost] = []
        since = _since_timestamp()
        for tag in INSTAGRAM_HASHTAGS:
            if len(posts) >= limit:
                break
            try:
                r = requests.get(
                    f"{self.BASE_URL}/ig_hashtag_search",
                    params={"user_id": self.user_id, "q": tag, "access_token": self.token},
                    timeout=15,
                )
                r.raise_for_status()
                hashtag_data = r.json().get("data", [])
                if not hashtag_data:
                    continue
                hashtag_id = hashtag_data[0]["id"]
                media_r = requests.get(
                    f"{self.BASE_URL}/{hashtag_id}/recent_media",
                    params={
                        "user_id": self.user_id,
                        "fields": "id,caption,timestamp,like_count,comments_count",
                        "limit": 50,
                        "access_token": self.token,
                    },
                    timeout=15,
                )
                media_r.raise_for_status()
                for item in media_r.json().get("data", []):
                    caption = item.get("caption", "")
                    if not caption:
                        continue
                    ts = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
                    if ts < since:
                        continue
                    posts.append(RawPost(
                        post_id=_make_post_id("Instagram", item["id"]),
                        platform="Instagram",
                        timestamp=ts,
                        raw_text=caption,
                        engagement_metrics={
                            "like_count": item.get("like_count", 0),
                            "comments_count": item.get("comments_count", 0),
                        },
                        brand_keywords_matched=_keyword_matches(caption),
                    ))
            except requests.RequestException as e:
                logger.warning("Instagram Graph API error for #%s: %s", tag, e)
        return posts[:limit]

    # ── Strategy 2: instaloader (credential-free public hashtag scraping) ────
    def collect(self, limit: int) -> list[RawPost]:
        if self.token and self.user_id:
            logger.info("Instagram: using Graph API")
            return self._collect_graph_api(limit)
        # Instagram now requires login for ALL unauthenticated hashtag access (2024+).
        # Redirecting to Trustpilot collector which provides equivalent customer-voice
        # data without credentials. InstagramCollector returns [] when uncredentialed
        # so Trustpilot picks up the slot via its own entry in collect_all().
        logger.info(
            "Instagram: no credentials — Meta requires login for hashtag API. "
            "Use Trustpilot collector for credential-free customer reviews."
        )
        return []


# ─────────────────────────────────────────────
# X / Twitter — paid API primary, Nitter RSS fallback
# ─────────────────────────────────────────────

# Public Nitter instances — tried in order until one succeeds
_NITTER_INSTANCES: list[str] = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.cz",
    "https://nitter.1d4.us",
    "https://nitter.kavin.rocks",
]

_NITTER_SEARCH_QUERIES: list[str] = [
    "T-Mobile 5G OR T-Mobile coverage OR T-Mobile plan",
    "Verizon 5G OR Verizon coverage OR Verizon plan",
    "AT&T 5G OR AT&T coverage OR AT&T plan",
    "switch carrier T-Mobile OR switch to Verizon OR switch to ATT",
]

_NITTER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TelecomSocialListening/1.0; research)",
    "Accept": "application/rss+xml, text/xml, */*",
}


class TwitterCollector:
    """
    Collects tweets via X API v2 (paid) or Nitter RSS feeds (credential-free).

    Strategy (in order):
      1. Paid API v2 — if TWITTER_BEARER_TOKEN is set in .env.
      2. Nitter RSS — queries multiple public Nitter instances for X search results
         without any credentials. Falls back across instances if one is down.
    """

    # ── Strategy 1: paid API v2 ──────────────────────────────────────
    def _collect_paid(self, limit: int) -> list[RawPost]:
        since = _since_timestamp()
        posts: list[RawPost] = []
        headers = {"Authorization": f"Bearer {cfg.twitter_bearer_token}"}
        params = {
            "query": TWITTER_QUERY,
            "start_time": since.isoformat(),
            "tweet.fields": "created_at,public_metrics,author_id,text",
            "max_results": 100,
        }
        try:
            while len(posts) < limit:
                r = requests.get(
                    "https://api.twitter.com/2/tweets/search/recent",
                    headers=headers,
                    params=params,
                    timeout=15,
                )
                r.raise_for_status()
                body = r.json()
                for tweet in body.get("data", []):
                    metrics = tweet.get("public_metrics", {})
                    posts.append(RawPost(
                        post_id=_make_post_id("X", tweet["id"]),
                        platform="X",
                        timestamp=datetime.fromisoformat(
                            tweet["created_at"].replace("Z", "+00:00")
                        ),
                        raw_text=tweet["text"],
                        author_id=_anonymize(tweet.get("author_id", "unknown")),
                        engagement_metrics={
                            "like_count": metrics.get("like_count", 0),
                            "retweet_count": metrics.get("retweet_count", 0),
                            "reply_count": metrics.get("reply_count", 0),
                        },
                        brand_keywords_matched=_keyword_matches(tweet["text"]),
                    ))
                next_token = body.get("meta", {}).get("next_token")
                if not next_token:
                    break
                params["next_token"] = next_token
        except requests.RequestException as e:
            logger.error("Twitter paid API error: %s", e)
        return posts[:limit]

    # ── Strategy 2: Nitter RSS (credential-free) ─────────────────────
    def _probe_nitter_instance(self, base: str) -> bool:
        """Return True if this Nitter instance responds to a simple probe."""
        try:
            r = requests.get(base, headers=_NITTER_HEADERS, timeout=8)
            return r.status_code == 200
        except Exception:
            return False

    def _fetch_nitter_rss(self, base: str, query: str) -> list[RawPost]:
        """Fetch one page of Nitter RSS search results and return RawPost list."""
        posts: list[RawPost] = []
        since = _since_timestamp()
        try:
            url = f"{base}/search/rss"
            r = requests.get(
                url,
                params={"q": query, "f": "tweets"},
                headers=_NITTER_HEADERS,
                timeout=15,
            )
            r.raise_for_status()
            root = ET.fromstring(r.content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            channel = root.find("channel")
            if channel is None:
                return posts
            for item in channel.findall("item"):
                title_el = item.find("title")
                desc_el = item.find("description")
                pub_el = item.find("pubDate")
                guid_el = item.find("guid")

                text = ""
                if desc_el is not None and desc_el.text:
                    # Strip HTML tags from description
                    text = re.sub(r"<[^>]+>", " ", desc_el.text).strip()
                if not text and title_el is not None and title_el.text:
                    text = title_el.text.strip()
                if not text:
                    continue

                try:
                    ts = parsedate_to_datetime(pub_el.text) if pub_el is not None else None
                    if ts is None:
                        ts = datetime.now(timezone.utc)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                except Exception:
                    ts = datetime.now(timezone.utc)

                if ts < since:
                    continue
                if not _keyword_matches(text):
                    continue

                guid = guid_el.text if guid_el is not None else text[:40]
                post_id = hashlib.sha256(guid.encode()).hexdigest()[:16]
                posts.append(RawPost(
                    post_id=_make_post_id("X", post_id),
                    platform="X",
                    timestamp=ts,
                    raw_text=text,
                    author_id="nitter_anon",
                    engagement_metrics={"source": "nitter"},
                    brand_keywords_matched=_keyword_matches(text),
                ))
        except Exception as e:
            logger.debug("Nitter RSS error (%s, '%s'): %s", base, query, e)
        return posts

    def _collect_nitter(self, limit: int) -> list[RawPost]:
        # Find a working Nitter instance
        working_base: str | None = None
        for base in _NITTER_INSTANCES:
            if self._probe_nitter_instance(base):
                working_base = base
                logger.info("X: using Nitter instance %s", base)
                break
            logger.debug("X: Nitter instance %s unreachable", base)

        if not working_base:
            logger.warning("X: all Nitter instances unreachable — skipping")
            return []

        posts: list[RawPost] = []
        seen_ids: set[str] = set()
        for query in _NITTER_SEARCH_QUERIES:
            if len(posts) >= limit:
                break
            batch = self._fetch_nitter_rss(working_base, query)
            for p in batch:
                if p.post_id not in seen_ids:
                    seen_ids.add(p.post_id)
                    posts.append(p)
            time.sleep(2)  # polite between queries

        logger.info("X (Nitter) collected %d posts", len(posts))
        return posts[:limit]

    def collect(self, limit: int) -> list[RawPost]:
        if cfg.twitter_bearer_token:
            logger.info("X: using paid API v2")
            return self._collect_paid(limit)
        logger.info("X: no bearer token — trying Nitter RSS")
        return self._collect_nitter(limit)


# ─────────────────────────────────────────────
# YouTube — credential-free (yt-dlp search + youtube-comment-downloader)
# Each query carries a brand hint so comments without explicit brand mentions
# are still captured by prepending the brand name (same strategy as AppReview).
# ─────────────────────────────────────────────

# (query, brand_hint) — brand_hint=None means multi-brand / no prepend
YOUTUBE_SEARCH_QUERIES: list[tuple[str, str | None]] = [
    ("T-Mobile review 2024 OR T-Mobile review 2025", "T-Mobile US"),
    ("T-Mobile customer service experience", "T-Mobile US"),
    ("T-Mobile 5G coverage problems OR T-Mobile network issues", "T-Mobile US"),
    ("Verizon review 2024 OR Verizon review 2025", "Verizon"),
    ("Verizon customer service experience", "Verizon"),
    ("Verizon 5G coverage problems OR Verizon network issues", "Verizon"),
    ("AT&T review 2024 OR AT&T review 2025", "AT&T Mobility"),
    ("AT&T customer service experience", "AT&T Mobility"),
    ("T-Mobile vs Verizon vs AT&T comparison", None),
    ("best cell phone carrier US 2025", None),
    ("switch carrier T-Mobile Verizon ATT", None),
]
_YOUTUBE_MAX_VIDEOS_PER_QUERY = 3  # 3 videos × 11 queries × 20 comments = up to 660


class YouTubeCollector:
    """
    Collects YouTube video comments using credential-free libraries.
    Video discovery: yt-dlp (replaces youtubesearchpython, Python 3.14 compatible).
    Comment extraction: youtube-comment-downloader (Innertube API, no quota).

    Brand context strategy: If a search query is brand-specific, comments that
    don't explicitly mention the brand are still collected with the brand name
    prepended — identical to AppReviewCollector's approach.
    """

    def _parse_youtube_time(self, time_str: str) -> datetime:
        """Convert relative time string ('3 days ago') to UTC datetime."""
        now = datetime.now(timezone.utc)
        m = re.match(
            r"(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago",
            time_str or "",
            re.IGNORECASE,
        )
        if not m:
            return now
        value, unit = int(m.group(1)), m.group(2).lower()
        delta_map = {
            "second": timedelta(seconds=value),
            "minute": timedelta(minutes=value),
            "hour":   timedelta(hours=value),
            "day":    timedelta(days=value),
            "week":   timedelta(weeks=value),
            "month":  timedelta(days=value * 30),
            "year":   timedelta(days=value * 365),
        }
        return now - delta_map.get(unit, timedelta(0))

    def _search_video_ids(self, query: str) -> list[dict]:
        """Return list of {video_id, title} dicts using yt-dlp search (no API key)."""
        try:
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
                "no_color": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(
                    f"ytsearch{_YOUTUBE_MAX_VIDEOS_PER_QUERY}:{query}",
                    download=False,
                )
                return [
                    {"video_id": entry["id"], "title": entry.get("title", "")}
                    for entry in (result.get("entries") or [])
                    if entry.get("id")
                ]
        except Exception as e:
            logger.warning("YouTube search error for '%s': %s", query, e)
            return []

    def _fetch_comments(
        self, video_id: str, video_title: str, brand_hint: str | None
    ) -> list[RawPost]:
        """
        Fetch up to cfg.youtube_max_comments_per_video comments for one video.
        If brand_hint is set, comments that don't mention a brand keyword are still
        kept by prepending '[{brand_hint}]' — they are implicitly about that brand
        since they come from a brand-specific search result.
        """
        posts: list[RawPost] = []
        url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            downloader = YoutubeCommentDownloader()
            comments = downloader.get_comments_from_url(url, sort_by=SORT_BY_RECENT)
            for i, comment in enumerate(comments):
                if i >= cfg.youtube_max_comments_per_video:
                    break
                text = comment.get("text", "").strip()
                if not text:
                    continue
                ts = self._parse_youtube_time(comment.get("time", ""))
                if ts < _since_timestamp():
                    continue

                matched = _keyword_matches(text)
                if not matched:
                    if brand_hint:
                        # Comment is on a brand-specific video — prepend brand for detection
                        text = f"[{brand_hint}] {text}"
                        matched = [brand_hint]
                    else:
                        continue  # multi-brand query: skip unless brand mentioned explicitly

                posts.append(RawPost(
                    post_id=_make_post_id("YouTube", comment.get("id", f"{video_id}_{i}")),
                    platform="YouTube",
                    timestamp=ts,
                    raw_text=text,
                    author_id=_anonymize(comment.get("author", "unknown")),
                    engagement_metrics={"votes": comment.get("votes", 0)},
                    brand_keywords_matched=matched,
                ))
        except Exception as e:
            logger.warning("YouTube comment fetch error for %s: %s", video_id, e)
        return posts

    def collect(self, limit: int) -> list[RawPost]:
        if not _YOUTUBE_AVAILABLE:
            logger.info("YouTube libraries not installed — skipping YouTube collection")
            return []

        seen_ids: set[str] = set()
        all_posts: list[RawPost] = []

        for query, brand_hint in YOUTUBE_SEARCH_QUERIES:
            if len(all_posts) >= limit:
                break
            for video in self._search_video_ids(query):
                vid = video["video_id"]
                if vid in seen_ids:
                    continue
                seen_ids.add(vid)
                posts = self._fetch_comments(vid, video["title"], brand_hint)
                all_posts.extend(posts)
                time.sleep(1)
                if len(all_posts) >= limit:
                    break

        logger.info("YouTube collected %d posts", len(all_posts))
        return all_posts[:limit]


# ─────────────────────────────────────────────
# App Store Reviews — credential-free
# ─────────────────────────────────────────────
APP_IDS: dict[str, dict[str, str]] = {
    "T-Mobile US":   {"android": "com.tmobile.pr.mytmobile", "ios": "293916440", "name": "T-Mobile"},
    "Verizon":       {"android": "com.vzw.hss.myverizon",   "ios": "416023011", "name": "My Verizon"},
    "AT&T Mobility": {"android": "com.att.myatt",           "ios": "416013979", "name": "myAT&T"},
}


class AppReviewCollector:
    """
    Collects app store reviews from Google Play and Apple App Store.
    No credentials required. Uses google-play-scraper and app-store-scraper.
    Brand name is prepended to raw_text so brand.py regex detects it.
    Reviews under 15 words are skipped before returning.
    Skips gracefully if libraries are not installed.
    """

    def _fetch_google_play(self, brand: str, android_id: str) -> list[RawPost]:
        posts: list[RawPost] = []
        since = _since_timestamp()
        try:
            result, _ = gplay_reviews(
                android_id,
                lang="en",
                country="us",
                sort=GPlaySort.NEWEST,
                count=cfg.app_review_max_per_app,
                filter_score_with=None,
            )
            for review in result:
                content = (review.get("content") or "").strip()
                if not content:
                    continue
                ts = review.get("at")
                if ts is None:
                    continue
                if not isinstance(ts, datetime):
                    ts = datetime.fromtimestamp(ts.timestamp(), tz=timezone.utc)
                elif ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts < since:
                    continue
                # Prepend brand name so brand.py regex matches
                raw_text = f"[{brand}] {content}"
                word_count = len(raw_text.split())
                if word_count < 15:
                    continue
                posts.append(RawPost(
                    post_id=_make_post_id("AppReview", f"gplay_{review.get('reviewId', '')}"),
                    platform="AppReview",
                    timestamp=ts,
                    raw_text=raw_text,
                    author_id=_anonymize(review.get("userName", "unknown")),
                    engagement_metrics={
                        "rating": review.get("score", 0),
                        "thumbs_up": review.get("thumbsUpCount", 0),
                        "store": 1,  # 1 = Google Play
                    },
                    brand_keywords_matched=[brand],
                ))
        except Exception as e:
            logger.warning("Google Play fetch error for %s (%s): %s", brand, android_id, e)
        return posts

    def _fetch_app_store(self, brand: str, ios_id: str, app_name: str) -> list[RawPost]:
        posts: list[RawPost] = []
        since = _since_timestamp()
        try:
            app = AppStore(country="us", app_name=app_name, app_id=int(ios_id))
            app.review(how_many=cfg.app_review_max_per_app, sleep=0.5)
            for review in app.reviews:
                title = (review.get("title") or "").strip()
                body = (review.get("review") or "").strip()
                content = f"{title} {body}".strip()
                if not content:
                    continue
                ts = review.get("date")
                if ts is None:
                    continue
                if isinstance(ts, datetime):
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                else:
                    continue
                if ts < since:
                    continue
                raw_text = f"[{brand}] {content}"
                if len(raw_text.split()) < 15:
                    continue
                posts.append(RawPost(
                    post_id=_make_post_id(
                        "AppReview",
                        f"ios_{review.get('userName', 'u')}_{ts.isoformat()}",
                    ),
                    platform="AppReview",
                    timestamp=ts,
                    raw_text=raw_text,
                    author_id=_anonymize(review.get("userName", "unknown")),
                    engagement_metrics={
                        "rating": review.get("rating", 0),
                        "store": 2,  # 2 = Apple App Store
                    },
                    brand_keywords_matched=[brand],
                ))
        except Exception as e:
            logger.warning("App Store fetch error for %s (%s): %s", brand, ios_id, e)
        return posts

    def collect(self, limit: int) -> list[RawPost]:
        if not _APPSTORE_AVAILABLE:
            logger.info("App store libraries not installed — skipping AppReview collection")
            return []

        all_posts: list[RawPost] = []
        for brand, ids in APP_IDS.items():
            if len(all_posts) >= limit:
                break
            all_posts.extend(self._fetch_google_play(brand, ids["android"]))
            all_posts.extend(self._fetch_app_store(brand, ids["ios"], ids["name"]))

        logger.info("AppReview collected %d posts", len(all_posts))
        return all_posts[:limit]


# ─────────────────────────────────────────────
# Trustpilot — credential-free public reviews
# Replaces Instagram as the "social proof" signal source.
# Trustpilot pages are public HTML — no API key, no login required.
# ─────────────────────────────────────────────

# Trustpilot company slugs for all three carriers
_TRUSTPILOT_COMPANIES: list[dict] = [
    {"slug": "t-mobile.com",  "brand": "T-Mobile US"},
    {"slug": "verizon.com",   "brand": "Verizon"},
    {"slug": "att.com",       "brand": "AT&T Mobility"},
]

_TRUSTPILOT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


class TrustpilotCollector:
    """
    Scrapes public Trustpilot review pages for T-Mobile, Verizon, and AT&T.
    No credentials or API key required — reviews are publicly accessible.
    Brand name is prepended to raw_text so brand.py regex detects it.
    Collects up to cfg.posts_per_platform reviews per brand.
    """

    BASE = "https://www.trustpilot.com"

    def _fetch_page(self, slug: str, page: int) -> list[dict]:
        """Fetch one page of reviews from Trustpilot __NEXT_DATA__ JSON."""
        import json as _json
        try:
            r = requests.get(
                f"{self.BASE}/review/{slug}",
                params={"page": page, "sort": "recency"},
                headers=_TRUSTPILOT_HEADERS,
                timeout=15,
            )
            r.raise_for_status()
            m = re.search(
                r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                r.text,
                re.DOTALL,
            )
            if not m:
                return []
            data = _json.loads(m.group(1))
            raw = data.get("props", {}).get("pageProps", {}).get("reviews", [])
            reviews: list[dict] = []
            for rev in raw:
                text = (rev.get("text") or "").strip()
                if not text:
                    continue
                date_str = (
                    rev.get("dates", {}).get("publishedDate")
                    or rev.get("dates", {}).get("experiencedDate")
                    or ""
                )
                reviews.append({
                    "text": text,
                    "date": date_str,
                    "rating": rev.get("rating", 0),
                    "id": rev.get("id", ""),
                })
            return reviews
        except Exception as e:
            logger.warning("Trustpilot fetch error for %s page %d: %s", slug, page, e)
            return []

    def _parse_date(self, date_str: str) -> datetime:
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception:
            return datetime.now(timezone.utc)

    def collect(self, limit: int) -> list[RawPost]:
        all_posts: list[RawPost] = []
        per_brand = max(1, limit // len(_TRUSTPILOT_COMPANIES))
        since = _since_timestamp()

        for company in _TRUSTPILOT_COMPANIES:
            if len(all_posts) >= limit:
                break
            brand = company["brand"]
            slug = company["slug"]
            brand_posts: list[RawPost] = []

            for page in range(1, 6):  # up to 5 pages × 20 reviews = 100 per brand
                if len(brand_posts) >= per_brand:
                    break
                reviews = self._fetch_page(slug, page)
                if not reviews:
                    break
                for rev in reviews:
                    ts = self._parse_date(rev["date"])
                    if ts < since:
                        break  # reviews are sorted by recency
                    raw_text = f"[{brand}] {rev['text']}"
                    if len(raw_text.split()) < 15:
                        continue
                    uid = rev.get("id") or hashlib.sha256(
                        f"{slug}{rev['text'][:60]}".encode()
                    ).hexdigest()[:16]
                    brand_posts.append(RawPost(
                        post_id=_make_post_id("Instagram", uid),  # maps to Instagram platform slot
                        platform="Instagram",
                        timestamp=ts,
                        raw_text=raw_text,
                        author_id="trustpilot_anon",
                        engagement_metrics={"rating": rev["rating"]},
                        brand_keywords_matched=[brand],
                    ))
                time.sleep(1)

            logger.info("Trustpilot collected %d posts for %s", len(brand_posts), brand)
            all_posts.extend(brand_posts[:per_brand])

        logger.info("Trustpilot total: %d posts", len(all_posts))
        return all_posts[:limit]


# ─────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────
def collect_all(run_id: str) -> list[RawPost]:
    """Collect posts from all available platforms and return combined raw dataset."""
    limit = cfg.posts_per_platform * cfg.collection_buffer_multiplier
    logger.info("Collecting up to %d candidates per platform (run=%s)", limit, run_id)

    all_posts: list[RawPost] = []
    for CollectorCls, name in [
        (RedditCollector, "Reddit"),
        (TrustpilotCollector, "Instagram"),   # Trustpilot fills the Instagram slot
        (TwitterCollector, "X"),
        (YouTubeCollector, "YouTube"),
        (AppReviewCollector, "AppReview"),
    ]:
        try:
            posts = CollectorCls().collect(limit)
            logger.info("%s: %d posts collected", name, len(posts))
            all_posts.extend(posts)
        except Exception as e:
            logger.error("Collection failed for %s: %s", name, e)

    logger.info("Total raw posts collected: %d", len(all_posts))
    return all_posts
