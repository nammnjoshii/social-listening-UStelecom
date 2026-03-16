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


# Official brand account handles — posts FROM these accounts are brand PR/marketing,
# not organic customer conversation, and must be filtered before analysis.
OFFICIAL_BRAND_ACCOUNTS: frozenset[str] = frozenset({
    "tmobile", "tmobilehelp",
    "verizon", "vzwsupport",
    "att", "atthelp",
    "t-mobile", "at&t",         # YouTube channel display names (lowercase)
})


def _is_official_account(username: str) -> bool:
    """Return True if username belongs to a known official brand account."""
    return username.strip().lower() in OFFICIAL_BRAND_ACCOUNTS


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

                author = d.get("author", "unknown")
                posts.append(RawPost(
                    post_id=_make_post_id("Reddit", d["id"]),
                    platform="Reddit",
                    timestamp=created,
                    raw_text=text,
                    author_id=_anonymize(author),
                    engagement_metrics={
                        "score": d.get("score", 0),
                        "num_comments": d.get("num_comments", 0),
                    },
                    brand_keywords_matched=_keyword_matches(text),
                    is_official_account=_is_official_account(author),
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

# Public Nitter instances — probed for actual RSS search capability (not just homepage).
# Many instances are volunteer-run and may come and go; the collector handles failures
# gracefully and falls back to brand-account timelines when search is unavailable.
_NITTER_INSTANCES: list[str] = [
    "https://nitter.perennialte.ch",
    "https://nitter.net",
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.1d4.us",
    "https://nitter.kavin.rocks",
    "https://nitter.tiekoetter.com",
    "https://nitter.pussthecat.org",
    "https://nitter.weiler.rocks",
]

# nitter.net is search-broken but timeline RSS works reliably; always use for timelines
_NITTER_TIMELINE_BASE = "https://nitter.net"

_NITTER_SEARCH_QUERIES: list[str] = [
    # ── T-Mobile: network & coverage ────────────────────────────────────
    "T-Mobile 5G coverage OR T-Mobile network issues",
    "T-Mobile signal OR T-Mobile outage OR T-Mobile down",
    "T-Mobile home internet OR T-Mobile WiFi calling",
    # ── T-Mobile: plan & pricing ─────────────────────────────────────────
    "T-Mobile plan price OR T-Mobile billing OR T-Mobile overcharge",
    "T-Mobile unlimited OR T-Mobile deal OR T-Mobile promotion",
    "TMobile customer service OR TMobile support complaint",
    "Magenta plan OR Uncarrier OR TMUS network",
    # ── T-Mobile: switching & sentiment ──────────────────────────────────
    "switch from T-Mobile OR leave T-Mobile OR cancel T-Mobile",
    "@TMobile frustrated OR @TMobile awful OR @TMobile worst",
    "@TMobile great OR @TMobile love OR @TMobile best",
    # ── Verizon: network & coverage ──────────────────────────────────────
    "Verizon 5G coverage OR Verizon network issues",
    "Verizon signal OR Verizon outage OR Verizon down",
    "Verizon home internet OR VZW fios OR Verizon LTE",
    # ── Verizon: plan & pricing ───────────────────────────────────────────
    "Verizon plan price OR Verizon billing OR Verizon overcharge",
    "Verizon unlimited OR VZW deal OR Verizon promotion",
    "Verizon customer service OR VZW support complaint",
    # ── Verizon: switching & sentiment ───────────────────────────────────
    "switch from Verizon OR leave Verizon OR cancel Verizon",
    "@Verizon frustrated OR @VZWSupport awful OR @Verizon worst",
    "@Verizon great OR @Verizon love OR @Verizon best",
    # ── AT&T: network & coverage ─────────────────────────────────────────
    "ATT 5G coverage OR AT&T network issues",
    "AT&T signal OR AT&T outage OR AT&T down",
    "AT&T FirstNet OR AT&T fiber bundle OR attmobility LTE",
    # ── AT&T: plan & pricing ──────────────────────────────────────────────
    "ATT plan price OR AT&T billing OR AT&T overcharge",
    "AT&T unlimited OR ATT deal OR attmobility promotion",
    "ATT customer service OR ATT support complaint",
    # ── AT&T: switching & sentiment ───────────────────────────────────────
    "switch from ATT OR leave AT&T OR cancel AT&T",
    "@ATT frustrated OR @ATTHelp awful OR @ATT worst",
    "@ATT great OR @ATT love OR @ATT best",
    # ── Cross-carrier comparisons ─────────────────────────────────────────
    "T-Mobile vs Verizon vs AT&T comparison",
    "best cell carrier US 2025 OR best wireless plan 2025",
    "switch carrier TMobile Verizon ATT 2025",
    "unlimited data plan comparison T-Mobile Verizon ATT",
    "prepaid carrier T-Mobile Verizon ATT review",
]

# Official brand + support handles for timeline RSS.
# Format: (username, canonical_brand, include_with_replies)
# with_replies=True → also fetch /<user>/with_replies/rss (customer complaints/praise)
_NITTER_BRAND_ACCOUNTS: list[tuple[str, str, bool]] = [
    ("TMobile",     "T-Mobile US",    True),
    ("TMobileHelp", "T-Mobile US",    True),   # support replies = customer issues
    ("Verizon",     "Verizon",        True),
    ("ATT",         "AT&T Mobility",  True),
    ("ATTHelp",     "AT&T Mobility",  True),   # support replies = customer issues
]

_NITTER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TelecomSocialListening/1.0; research)",
    "Accept": "application/rss+xml, text/xml, */*",
}


_6551_BASE = "https://ai.6551.io"

_6551_SEARCH_PAYLOADS: list[dict] = [
    {"keywords": "T-Mobile plan OR T-Mobile 5G OR T-Mobile coverage", "lang": "en", "excludeRetweets": True},
    {"keywords": "Verizon plan OR Verizon 5G OR Verizon coverage",     "lang": "en", "excludeRetweets": True},
    {"keywords": "ATT plan OR AT&T 5G OR AT&T coverage",               "lang": "en", "excludeRetweets": True},
    {"keywords": "switch carrier T-Mobile OR switch to Verizon OR switch ATT", "lang": "en", "excludeRetweets": True},
]


class TwitterCollector:
    """
    Collects tweets via opentwitter/6551 API or Nitter RSS.

    Strategy (in order):
      1. opentwitter/6551  — if TWITTER_TOKEN is set in .env.
                             Up to 100 tweets/request, date/lang/engagement filters.
                             Get a free token at: https://6551.io/mcp
      2. Nitter RSS        — credential-free fallback; ~20 tweets/query.
    """

    # ── Strategy 1: opentwitter / 6551 API ───────────────────────────
    def _collect_6551(self, limit: int) -> list[RawPost]:
        since = _since_timestamp()
        posts: list[RawPost] = []
        headers = {
            "Authorization": f"Bearer {cfg.twitter_6551_token}",
            "Content-Type": "application/json",
        }
        seen_ids: set[str] = set()

        for payload in _6551_SEARCH_PAYLOADS:
            if len(posts) >= limit:
                break
            body = {
                **payload,
                "product": "Latest",
                "maxResults": 100,
                "sinceDate": since.strftime("%Y-%m-%d"),
                "untilDate": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            }
            try:
                r = requests.post(
                    f"{_6551_BASE}/open/twitter_search",
                    json=body,
                    headers=headers,
                    timeout=15,
                )
                r.raise_for_status()
                for tweet in r.json().get("data", []):
                    text = tweet.get("text", "")
                    if not text or not _keyword_matches(text):
                        continue
                    tweet_id = tweet.get("id", "")
                    post_id = _make_post_id("X", tweet_id or hashlib.sha256(text[:40].encode()).hexdigest()[:16])
                    if post_id in seen_ids:
                        continue
                    seen_ids.add(post_id)
                    try:
                        ts = datetime.fromisoformat(tweet["createdAt"].replace("Z", "+00:00"))
                    except Exception:
                        ts = datetime.now(timezone.utc)
                    screen_name = tweet.get("userScreenName", "unknown")
                    posts.append(RawPost(
                        post_id=post_id,
                        platform="X",
                        timestamp=ts,
                        raw_text=text,
                        author_id=_anonymize(screen_name),
                        engagement_metrics={
                            "like_count":    tweet.get("favoriteCount", 0),
                            "retweet_count": tweet.get("retweetCount", 0),
                            "reply_count":   tweet.get("replyCount", 0),
                        },
                        brand_keywords_matched=_keyword_matches(text),
                        is_official_account=_is_official_account(screen_name),
                    ))
            except requests.RequestException as e:
                logger.error("X (6551) error for '%s': %s", payload["keywords"][:40], e)
            time.sleep(1)

        logger.info("X (opentwitter/6551) collected %d posts", len(posts))
        return posts[:limit]

    # ── Strategy 2: Nitter RSS (credential-free) ─────────────────────
    def _probe_nitter_instance(self, base: str) -> bool:
        """Return True if this Nitter instance actually returns valid RSS search results."""
        try:
            r = requests.get(
                f"{base}/search/rss",
                params={"q": "T-Mobile", "f": "tweets"},
                headers=_NITTER_HEADERS,
                timeout=10,
            )
            return r.status_code == 200 and r.content[:5] == b"<?xml"
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
                    engagement_metrics={},
                    brand_keywords_matched=_keyword_matches(text),
                ))
        except Exception as e:
            logger.debug("Nitter RSS error (%s, '%s'): %s", base, query, e)
        return posts

    def _find_working_instances(self, max_instances: int = 3) -> list[str]:
        """Probe all Nitter instances and return up to max_instances working ones."""
        working: list[str] = []
        for base in _NITTER_INSTANCES:
            if self._probe_nitter_instance(base):
                working.append(base)
                logger.info("X: Nitter instance available: %s", base)
                if len(working) >= max_instances:
                    break
            else:
                logger.debug("X: Nitter instance %s unreachable", base)
        return working

    def _fetch_nitter_timeline(
        self,
        base: str,
        username: str,
        brand_hint: str,
        with_replies: bool = False,
    ) -> list[RawPost]:
        """Fetch the public RSS timeline for a Twitter/X account via Nitter.

        brand_hint — canonical brand name (e.g. "T-Mobile US"). Tweets from an
        official brand account that don't explicitly mention the brand keyword are
        still on-topic; we prepend [brand_hint] so brand.py can detect them —
        identical strategy to AppReviewCollector and YouTubeCollector.

        with_replies=True fetches /<user>/with_replies/rss — captures customer
        replies directed at the brand (complaints, praise, inquiries).
        """
        posts: list[RawPost] = []
        since = _since_timestamp()
        path = f"/{username}/with_replies/rss" if with_replies else f"/{username}/rss"
        try:
            r = requests.get(f"{base}{path}", headers=_NITTER_HEADERS, timeout=15)
            if r.status_code != 200 or r.content[:5] != b"<?xml":
                return posts
            root = ET.fromstring(r.content)
            channel = root.find("channel")
            if channel is None:
                return posts
            for item in channel.findall("item"):
                title_el = item.find("title")
                desc_el  = item.find("description")
                pub_el   = item.find("pubDate")
                guid_el  = item.find("guid")

                text = ""
                if desc_el is not None and desc_el.text:
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

                matched = _keyword_matches(text)
                if not matched:
                    # Brand account tweet with no explicit brand keyword —
                    # prepend brand so downstream detection works (same as YouTube/AppReview)
                    text = f"[{brand_hint}] {text}"
                    matched = [brand_hint]

                guid = guid_el.text if guid_el is not None else text[:40]
                suffix = "replies" if with_replies else "tl"
                post_id = hashlib.sha256(f"{username}_{suffix}_{guid}".encode()).hexdigest()[:16]
                posts.append(RawPost(
                    post_id=_make_post_id("X", post_id),
                    platform="X",
                    timestamp=ts,
                    raw_text=text,
                    author_id=_anonymize(username),
                    engagement_metrics={},
                    brand_keywords_matched=matched,
                    is_official_account=not with_replies,  # own timeline=True; customer reply feed=False
                ))
        except Exception as e:
            logger.debug("Nitter timeline error (%s, @%s with_replies=%s): %s", base, username, with_replies, e)
        return posts

    def _collect_nitter(self, limit: int) -> list[RawPost]:
        posts: list[RawPost] = []
        seen_ids: set[str] = set()

        # ── Phase 1: search queries on any working search-capable instances ──
        search_instances = self._find_working_instances(max_instances=3)
        if search_instances:
            for base in search_instances:
                if len(posts) >= limit:
                    break
                logger.info("X: running %d search queries on %s", len(_NITTER_SEARCH_QUERIES), base)
                for query in _NITTER_SEARCH_QUERIES:
                    if len(posts) >= limit:
                        break
                    batch = self._fetch_nitter_rss(base, query)
                    for p in batch:
                        if p.post_id not in seen_ids:
                            seen_ids.add(p.post_id)
                            posts.append(p)
                    time.sleep(1.5)
        else:
            logger.info("X: no search-capable Nitter instances — using timelines only")

        # ── Phase 2: brand account timelines (always run; nitter.net works) ──
        for username, brand_hint, with_replies in _NITTER_BRAND_ACCOUNTS:
            for use_replies in ([False, True] if with_replies else [False]):
                if len(posts) >= limit:
                    break
                batch = self._fetch_nitter_timeline(
                    _NITTER_TIMELINE_BASE, username, brand_hint=brand_hint, with_replies=use_replies
                )
                new = 0
                for p in batch:
                    if p.post_id not in seen_ids:
                        seen_ids.add(p.post_id)
                        posts.append(p)
                        new += 1
                feed = "with_replies" if use_replies else "timeline"
                logger.info("X: @%s %s → %d new posts", username, feed, new)
                time.sleep(1.5)

        logger.info(
            "X (Nitter) collected %d posts — %d search instance(s) + %d brand account feeds",
            len(posts), len(search_instances), len(_NITTER_BRAND_ACCOUNTS) * 2,
        )
        return posts[:limit]

    def collect(self, limit: int) -> list[RawPost]:
        if cfg.twitter_6551_token:
            logger.info("X: using opentwitter/6551 API")
            return self._collect_6551(limit)
        logger.info("X: no token set — trying Nitter RSS")
        return self._collect_nitter(limit)


# ─────────────────────────────────────────────
# YouTube — credential-free (yt-dlp search + youtube-comment-downloader)
# Each query carries a brand hint so comments without explicit brand mentions
# are still captured by prepending the brand name (same strategy as AppReview).
# ─────────────────────────────────────────────

# (query, brand_hint) — brand_hint=None means multi-brand / no prepend
YOUTUBE_SEARCH_QUERIES: list[tuple[str, str | None]] = [
    ("T-Mobile review 2025 OR T-Mobile review 2026", "T-Mobile US"),
    ("T-Mobile customer service experience 2025 OR 2026", "T-Mobile US"),
    ("T-Mobile 5G coverage problems OR T-Mobile network issues", "T-Mobile US"),
    ("T-Mobile billing problem OR T-Mobile overcharged", "T-Mobile US"),
    ("T-Mobile plan price increase OR T-Mobile deal", "T-Mobile US"),
    ("Verizon review 2025 OR Verizon review 2026", "Verizon"),
    ("Verizon customer service experience 2025 OR 2026", "Verizon"),
    ("Verizon 5G coverage problems OR Verizon network issues", "Verizon"),
    ("Verizon price increase OR Verizon billing issue", "Verizon"),
    ("AT&T review 2025 OR AT&T review 2026", "AT&T Mobility"),
    ("AT&T customer service experience 2025 OR 2026", "AT&T Mobility"),
    ("AT&T 5G coverage problems OR AT&T network issues", "AT&T Mobility"),
    ("AT&T FirstNet OR AT&T fiber bundle", "AT&T Mobility"),
    ("T-Mobile vs Verizon vs AT&T comparison 2025", None),
    ("best cell phone carrier US 2025 OR 2026", None),
    ("switch carrier T-Mobile Verizon ATT 2025 OR 2026", None),
    ("unlimited plan comparison T-Mobile Verizon ATT", None),
    ("prepaid vs postpaid carrier comparison US", None),
]
_YOUTUBE_MAX_VIDEOS_PER_QUERY = 5  # 5 videos × 18 queries × 50 comments = up to 4,500


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

                author = comment.get("author", "unknown")
                posts.append(RawPost(
                    post_id=_make_post_id("YouTube", comment.get("id", f"{video_id}_{i}")),
                    platform="YouTube",
                    timestamp=ts,
                    raw_text=text,
                    author_id=_anonymize(author),
                    engagement_metrics={"votes": comment.get("votes", 0)},
                    brand_keywords_matched=matched,
                    is_official_account=_is_official_account(author),
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

            for page in range(1, 51):  # up to 50 pages × 20 reviews = 1,000 per brand (10-week window)
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
