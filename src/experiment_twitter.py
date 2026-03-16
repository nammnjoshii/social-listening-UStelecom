"""
X / Twitter Ingestion Experiment — three alternative approaches.

Run standalone:
    python -m src.experiment_twitter

Methods tested
──────────────
1. LobeHub opentwitter / 6551 API  — ai.6551.io       (needs TWITTER_TOKEN from 6551.io/mcp)
2. Playwright headless              — X.com / Nitter   (blocked — Cloudflare / login wall)
3. Nitter RSS                       — nitter.perennialte.ch  (WORKING, no credentials)

Experiment results (as of 2026-03-16)
──────────────────────────────────────
Method 1 (opentwitter/6551):  API live, endpoint confirmed (HTTP 401 without token).
                              Up to 100 tweets/request, date/lang/engagement filters.
                              Token required — visit https://6551.io/mcp in browser,
                              then set TWITTER_TOKEN in .env.
Method 2 (Playwright):        BLOCKED — x.com redirects to /i/flow/login; Nitter
                              instances trigger Cloudflare JS challenge in headless mode.
Method 3 (Nitter RSS):        WORKING — 80 tweets across 4 queries today, no credentials.
                              Cloudflare does not challenge plain RSS HTTP requests.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import xml.etree.ElementTree as ET
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

LOOKBACK_DAYS = 7
TELECOM_QUERIES = [
    "T-Mobile 5G OR T-Mobile coverage OR T-Mobile plan",
    "Verizon 5G OR Verizon coverage OR Verizon plan",
    "AT&T 5G OR AT&T coverage OR AT&T plan",
    "switch carrier T-Mobile OR switch to Verizon OR switch ATT",
]


def _since() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)


# ─────────────────────────────────────────────────────────────────────────────
# Method 1 — LobeHub opentwitter / 6551 REST API
#
# The LobeHub opentwitter MCP skill is a thin wrapper around the 6551 API.
# We call it directly from Python — no MCP server needed.
#
# API base:  https://ai.6551.io
# Token:     https://6551.io/mcp  (visit in browser — free tier available)
# .env:      TWITTER_TOKEN=<your_6551_token>
#
# Capabilities vs Nitter RSS:
#   ✓ Up to 100 tweets per request (Nitter: ~20)
#   ✓ Date range filter (sinceDate / untilDate)
#   ✓ Language filter
#   ✓ Engagement filters (minLikes, minRetweets)
#   ✓ Exclude retweets / replies
#   ✓ Full metadata: id, retweetCount, favoriteCount, replyCount, hashtags
#   ✓ Real-time WebSocket stream at wss://ai.6551.io/open/twitter_wss?token=TOKEN
# ─────────────────────────────────────────────────────────────────────────────

_6551_BASE = "https://ai.6551.io"

_TELECOM_SEARCH_PAYLOADS = [
    {"keywords": "T-Mobile plan OR T-Mobile 5G OR T-Mobile coverage", "lang": "en", "excludeRetweets": True},
    {"keywords": "Verizon plan OR Verizon 5G OR Verizon coverage",     "lang": "en", "excludeRetweets": True},
    {"keywords": "ATT plan OR AT&T 5G OR AT&T coverage",               "lang": "en", "excludeRetweets": True},
    {"keywords": "switch carrier T-Mobile OR switch to Verizon OR switch ATT", "lang": "en", "excludeRetweets": True},
]


def method1_opentwitter(max_per_query: int = 50) -> list[dict]:
    """
    Search tweets via the 6551 API (LobeHub opentwitter backend).

    Requires TWITTER_TOKEN in .env — get yours at https://6551.io/mcp
    Returns normalised tweet dicts comparable to Nitter RSS output.
    """
    token = os.getenv("TWITTER_TOKEN", "")
    if not token:
        logger.warning(
            "Method 1 SKIPPED — set TWITTER_TOKEN in .env\n"
            "  Get your free token at: https://6551.io/mcp  (visit in browser)"
        )
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    since = _since()
    tweets: list[dict] = []

    for payload in _TELECOM_SEARCH_PAYLOADS:
        body = {
            **payload,
            "product": "Latest",
            "maxResults": min(max_per_query, 100),
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
            data = r.json()
            # 6551 response: {"success": true, "data": [...tweets...]}
            for tweet in data.get("data", []):
                tweets.append({
                    "id":           tweet.get("id", ""),
                    "text":         tweet.get("text", ""),
                    "created_at":   tweet.get("createdAt", ""),
                    "author":       tweet.get("userScreenName", "unknown"),
                    "metrics": {
                        "like_count":    tweet.get("favoriteCount", 0),
                        "retweet_count": tweet.get("retweetCount", 0),
                        "reply_count":   tweet.get("replyCount", 0),
                    },
                    "hashtags":     tweet.get("hashtags", []),
                    "source":       "opentwitter_6551",
                    "query":        payload["keywords"],
                })
            logger.info(
                "Method 1 (opentwitter): %d tweets for '%s'",
                len(data.get("data", [])), payload["keywords"][:40],
            )
        except requests.HTTPError as e:
            logger.error("Method 1 HTTP error: %s — %s", e, r.text[:200])
        except Exception as e:
            logger.error("Method 1 error: %s", e)
        time.sleep(1)

    logger.info("Method 1 (opentwitter) total: %d tweets", len(tweets))
    return tweets


# ─────────────────────────────────────────────────────────────────────────────
# Method 2 — Playwright headless browser
# RESULT: BLOCKED
#   - X.com forces /i/flow/login for all unauthenticated searches.
#   - nitter.perennialte.ch triggers Cloudflare JS challenge for browser traffic.
#
# Potential unblock: pip install playwright-stealth, then call stealth_async(page)
# before page.goto(). Not yet tested.
# ─────────────────────────────────────────────────────────────────────────────


async def method2_playwright_nitter(query: str = "T-Mobile plan", max_results: int = 20) -> list[dict]:
    """
    Attempt to scrape tweets with Playwright on Nitter instances without Cloudflare.
    nitter.perennialte.ch is blocked in headless mode — tries alternatives.
    """
    try:
        from playwright.async_api import async_playwright  # type: ignore
    except ImportError:
        logger.warning("Method 2 SKIPPED — playwright not installed.")
        return []

    tweets: list[dict] = []
    nitter_candidates = [
        "https://nitter.net",
        "https://nitter.it",
        "https://nitter.rawbit.ninja",
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for nitter_base in nitter_candidates:
            page = await browser.new_page()
            try:
                url = f"{nitter_base}/search?q={requests.utils.quote(query)}&f=tweets"
                await page.goto(url, timeout=15000)
                await page.wait_for_timeout(3000)

                title = await page.title()
                if "moment" in title.lower() or "checking" in title.lower():
                    logger.debug("Method 2: %s — Cloudflare blocked", nitter_base)
                    await page.close()
                    continue

                for selector in [".tweet-content", ".tweet-body", "[class*='tweet']"]:
                    els = await page.locator(selector).all()
                    for el in els[:max_results]:
                        text = (await el.inner_text()).strip()
                        if text:
                            tweets.append({"text": text, "source": f"playwright+{nitter_base}"})
                    if tweets:
                        break

                if tweets:
                    logger.info("Method 2 (Playwright): found %d tweets from %s", len(tweets), nitter_base)
                    await page.close()
                    break
            except Exception as e:
                logger.debug("Method 2 page error (%s): %s", nitter_base, e)
            finally:
                if not page.is_closed():
                    await page.close()
        await browser.close()

    if not tweets:
        logger.warning(
            "Method 2: all Nitter instances blocked by Cloudflare in headless mode. "
            "Use method3_nitter_rss() which bypasses Cloudflare via plain HTTP."
        )
    return tweets


def method2_run(query: str = "T-Mobile plan", max_results: int = 20) -> list[dict]:
    """Synchronous wrapper around the async Playwright function."""
    return asyncio.run(method2_playwright_nitter(query, max_results))


# ─────────────────────────────────────────────────────────────────────────────
# Method 3 — Nitter RSS (best free method, no credentials)
# nitter.perennialte.ch confirmed working 2026-03-16: 20 tweets / query.
# Cloudflare does not challenge plain RSS HTTP requests.
# ─────────────────────────────────────────────────────────────────────────────
_NITTER_WORKING = "https://nitter.perennialte.ch"
_NITTER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TelecomSocialListening/1.0; research)",
    "Accept": "application/rss+xml, text/xml, */*",
}


def method3_nitter_rss(query: str = "T-Mobile plan", max_results: int = 20) -> list[dict]:
    """Fetch tweets from the working Nitter RSS endpoint."""
    tweets: list[dict] = []
    since = _since()
    try:
        r = requests.get(
            f"{_NITTER_WORKING}/search/rss",
            params={"q": query, "f": "tweets"},
            headers=_NITTER_HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        root = ET.fromstring(r.content)
        channel = root.find("channel")
        for item in (channel.findall("item") if channel is not None else []):
            desc = item.findtext("description", "") or item.findtext("title", "")
            text = re.sub(r"<[^>]+>", " ", desc).strip() if desc else ""
            if not text:
                continue
            pub_raw = item.findtext("pubDate", "")
            try:
                ts = parsedate_to_datetime(pub_raw) if pub_raw else datetime.now(timezone.utc)
            except Exception:
                ts = datetime.now(timezone.utc)
            if ts < since:
                continue
            tweets.append({
                "text":       text,
                "created_at": ts.isoformat(),
                "source":     "nitter_rss",
                "query":      query,
            })
            if len(tweets) >= max_results:
                break
    except Exception as e:
        logger.error("Nitter RSS error: %s", e)
    return tweets


# ─────────────────────────────────────────────────────────────────────────────
# Experiment runner
# ─────────────────────────────────────────────────────────────────────────────

def run_experiment():
    print("\n" + "=" * 60)
    print("X / TWITTER INGESTION EXPERIMENT")
    print("=" * 60)

    results: dict[str, object] = {}

    # Method 1 — opentwitter / 6551 API
    print("\n[1/3] opentwitter / 6551 API  (TWITTER_TOKEN required)")
    m1 = method1_opentwitter(max_per_query=50)
    results["opentwitter_6551"] = {"count": len(m1), "sample": m1[:2]}
    print(f"      Tweets: {len(m1)}")

    # Method 2 — Playwright
    print("\n[2/3] Playwright headless (Nitter fallback)")
    m2 = method2_run(query="T-Mobile plan", max_results=10)
    results["playwright_nitter"] = {"count": len(m2), "sample": m2[:2]}
    print(f"      Tweets: {len(m2)}")

    # Method 3 — Nitter RSS
    print("\n[3/3] Nitter RSS (nitter.perennialte.ch)")
    all_nitter: list[dict] = []
    for q in TELECOM_QUERIES:
        batch = method3_nitter_rss(q, max_results=20)
        all_nitter.extend(batch)
        time.sleep(2)
    results["nitter_rss"] = {"count": len(all_nitter), "sample": all_nitter[:2]}
    print(f"      Tweets: {len(all_nitter)}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for method, data in results.items():
        count = data.get("count", "N/A") if isinstance(data, dict) else "N/A"
        status = "✓ WORKING" if isinstance(count, int) and count > 0 else "✗ needs key/setup"
        print(f"  {method:<25} {count:>4} tweets  {status}")

    print("\n  Active path (no key):   nitter_rss — free, 20 tweets/query, no credentials")
    print("  Upgrade path (with key): opentwitter_6551 — 100 tweets/query, richer metadata")
    print()
    return results


if __name__ == "__main__":
    run_experiment()
