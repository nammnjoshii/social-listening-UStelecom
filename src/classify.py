"""Claude multi-label classification — async, batched, with retry.

All five classification tasks (taxonomy, sentiment, intent, emotion,
brand confirmation) are resolved in a single Claude call per post,
per WORKFLOW.md §Step 6.

Batches: cfg.claude_batch_size posts per call, concurrency capped
at cfg.claude_concurrency simultaneous requests.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

import anthropic
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import cfg
from src.models import BrandTaggedPost, PostClassification

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Prompt template (unified — all 5 tasks)
# ─────────────────────────────────────────────
TAXONOMY_JSON = """
{
  "pillars": [
    {"pillar": "Network Performance", "categories": ["Coverage", "Speed", "Reliability", "5G Experience"]},
    {"pillar": "Customer Experience",  "categories": ["Support", "Retail", "Digital Experience"]},
    {"pillar": "Pricing & Plans",      "categories": ["Billing", "Plan Structure", "Fees"]},
    {"pillar": "Device & Equipment",   "categories": ["Upgrades", "Trade-Ins", "Equipment Issues"]},
    {"pillar": "Data & Privacy",       "categories": ["Data Throttling", "Privacy Concerns"]},
    {"pillar": "Competitive Switching","categories": ["Switching Intent", "Carrier Comparison"]}
  ]
}
"""

SYSTEM_PROMPT = """\
You are a telecom social media analyst classifying posts about T-Mobile US, Verizon, and AT&T Mobility.
Return ONLY valid JSON. No explanation text before or after.
"""

USER_PROMPT_TEMPLATE = """\
Classify this telecom social media post using the taxonomy below.

TAXONOMY:
{taxonomy}

POST (brand already detected: {brands}):
{post_text}

Return exactly this JSON — use only values from the taxonomy above.
If the post fits no taxonomy node, use pillar "Uncategorized" and leave category/theme/topic as "Uncategorized".

{{
  "brand": "<primary brand: T-Mobile US | Verizon | AT&T Mobility | Multiple>",
  "sentiment": "<Positive | Neutral | Negative>",
  "intent": "<Complaint | Inquiry | Praise | Recommendation>",
  "emotion": "<Frustration | Satisfaction | Confusion | Excitement>",
  "pillar": "<pillar name>",
  "category": "<category name>",
  "theme": "<theme name>",
  "topic": "<specific topic — be concise>",
  "confidence": "<High | Medium | Low>"
}}

Rules:
- Negative sentiment takes precedence in mixed posts.
- Sarcasm: assign the intended sentiment, not the literal words.
- If is_multi_brand is true, classify sentiment for the primary brand only.
- confidence = Low if the post is ambiguous or barely fits the taxonomy.
"""


def _build_prompt(post: BrandTaggedPost) -> str:
    brand_str = ", ".join(post.brands) if post.brands else "Unknown"
    return USER_PROMPT_TEMPLATE.format(
        taxonomy=TAXONOMY_JSON,
        brands=brand_str,
        post_text=post.normalized_text,
    )


# ─────────────────────────────────────────────
# Async classification with retry
# ─────────────────────────────────────────────
@retry(
    retry=retry_if_exception_type(anthropic.RateLimitError),
    wait=wait_exponential(multiplier=1, min=2, max=16),
    stop=stop_after_attempt(4),
)
async def _call_claude(
    client: anthropic.AsyncAnthropic,
    semaphore: asyncio.Semaphore,
    post: BrandTaggedPost,
    run_id: str,
) -> PostClassification | None:
    async with semaphore:
        try:
            response = await client.messages.create(
                model=cfg.claude_model,
                max_tokens=cfg.claude_max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": _build_prompt(post)}],
            )
            raw = response.content[0].text.strip()

            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            data = json.loads(raw)
            data.update({
                "post_id": post.post_id,
                "platform": post.platform,
                "timestamp": post.timestamp.isoformat(),
                "normalized_text": post.normalized_text,
                "brands": post.brands,
                "brand_confidence": post.brand_confidence,
                "is_multi_brand": post.is_multi_brand,
                "classification_status": "success",
                "taxonomy_version": cfg.taxonomy_version,
                "schema_version": cfg.schema_version,
                "pipeline_run_id": run_id,
            })
            return PostClassification.model_validate(data)

        except anthropic.RateLimitError:
            logger.warning("Rate limit hit for post %s — retrying", post.post_id)
            raise
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Parse error for post %s: %s", post.post_id, e)
            return _failed_record(post, run_id)
        except anthropic.APIError as e:
            logger.error("Claude API error for post %s: %s", post.post_id, e)
            return _failed_record(post, run_id)


def _failed_record(post: BrandTaggedPost, run_id: str) -> PostClassification:
    return PostClassification(
        post_id=post.post_id,
        platform=post.platform,
        timestamp=post.timestamp,
        normalized_text=post.normalized_text,
        brands=post.brands,
        brand_confidence=post.brand_confidence,
        is_multi_brand=post.is_multi_brand,
        pillar="Uncategorized",
        category="Uncategorized",
        theme="Uncategorized",
        topic="Uncategorized",
        sentiment="Neutral",
        intent="Inquiry",
        emotion="Confusion",
        confidence="Low",
        classification_status="failed",
        taxonomy_version=cfg.taxonomy_version,
        schema_version=cfg.schema_version,
        pipeline_run_id=run_id,
    )


async def _classify_all_async(
    posts: list[BrandTaggedPost],
    run_id: str,
) -> list[PostClassification]:
    client = anthropic.AsyncAnthropic(api_key=cfg.claude_api_key)
    semaphore = asyncio.Semaphore(cfg.claude_concurrency)

    tasks = [_call_claude(client, semaphore, post, run_id) for post in posts]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return [r for r in results if r is not None]


# ─────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────
def classify_posts(
    posts: list[BrandTaggedPost],
    run_id: str,
) -> list[PostClassification]:
    """
    Classify all posts. Processes in batches of cfg.claude_batch_size.
    Returns list of PostClassification records (including failed ones).
    """
    results: list[PostClassification] = []
    batch_size = cfg.claude_batch_size

    logger.info("Starting classification — %d posts, batch_size=%d", len(posts), batch_size)
    start = datetime.now(timezone.utc)

    for i in range(0, len(posts), batch_size):
        batch = posts[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(posts) + batch_size - 1) // batch_size
        logger.info("Classifying batch %d/%d (%d posts)", batch_num, total_batches, len(batch))

        batch_results = asyncio.run(_classify_all_async(batch, run_id))
        results.extend(batch_results)

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    success = sum(1 for r in results if r.classification_status == "success")
    flagged = sum(1 for r in results if r.classification_status == "flagged")
    failed = sum(1 for r in results if r.classification_status == "failed")

    logger.info(
        "Classification complete — total=%d success=%d flagged=%d failed=%d elapsed=%.1fs",
        len(results), success, flagged, failed, elapsed,
    )
    return results
