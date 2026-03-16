"""Claude multi-label classification — async, batched, with retry.

Hybrid routing (two paths per post):

  FAST PATH  — sentence-transformers cosine similarity assigns Pillar + Category
               when similarity >= SIMILARITY_THRESHOLD (~65-70% of posts).
               Claude only resolves Theme, Topic, Sentiment, Intent, Emotion.
               Smaller prompt → lower token cost, faster response.

  FULL PATH  — full Claude call used when:
               • embedding similarity is below threshold (ambiguous/niche post)
               • sentence-transformers is not installed (graceful fallback)

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
import time
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


class CreditExhaustedError(Exception):
    """Raised when the Anthropic credit balance is exhausted.
    Distinct from APIError — halts classification immediately rather than
    producing failed records that corrupt the quality gate.
    """
    def __init__(self, message: str, classified_so_far: int = 0):
        super().__init__(message)
        self.classified_so_far = classified_so_far

# ─────────────────────────────────────────────
# Prompt templates
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

# Full prompt — used when embeddings are unavailable or below threshold
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

# Reduced prompt — used when embeddings have already assigned Pillar + Category
EMBEDDING_ASSISTED_PROMPT_TEMPLATE = """\
Classify this telecom social media post. Pillar and Category have already been determined.

Pillar: {pillar}
Category: {category}

POST (brand already detected: {brands}):
{post_text}

Return exactly this JSON. Use the Pillar and Category provided above.

{{
  "brand": "<primary brand: T-Mobile US | Verizon | AT&T Mobility | Multiple>",
  "sentiment": "<Positive | Neutral | Negative>",
  "intent": "<Complaint | Inquiry | Praise | Recommendation>",
  "emotion": "<Frustration | Satisfaction | Confusion | Excitement>",
  "pillar": "{pillar}",
  "category": "{category}",
  "theme": "<theme name — infer from the post>",
  "topic": "<specific topic — be concise>",
  "confidence": "<High | Medium | Low>"
}}

Rules:
- Negative sentiment takes precedence in mixed posts.
- Sarcasm: assign the intended sentiment, not the literal words.
- If is_multi_brand is true, classify sentiment for the primary brand only.
- confidence = Low if the post is ambiguous.
"""


def _build_prompt(post: BrandTaggedPost) -> str:
    """Build the appropriate prompt — reduced (embedding-assisted) or full."""
    brand_str = ", ".join(post.brands) if post.brands else "Unknown"

    # Attempt embedding classification
    try:
        from src.embeddings import get_classifier
        classifier = get_classifier()
        if classifier.available:
            result = classifier.classify(post.normalized_text)
            if result and result.above_threshold:
                logger.debug(
                    "Embedding fast path: post=%s pillar=%s (%.2f) category=%s (%.2f)",
                    post.post_id, result.pillar, result.pillar_score,
                    result.category, result.category_score,
                )
                return EMBEDDING_ASSISTED_PROMPT_TEMPLATE.format(
                    pillar=result.pillar,
                    category=result.category,
                    brands=brand_str,
                    post_text=post.normalized_text,
                )
    except Exception as e:
        logger.debug("Embedding classifier error — falling back to full Claude prompt: %s", e)

    # Full Claude path
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
    wait=wait_exponential(multiplier=2, min=10, max=90),
    stop=stop_after_attempt(8),
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
            if not response.content:
                logger.warning("Claude returned empty content for post %s — marking failed", post.post_id)
                return None
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
        except anthropic.BadRequestError as e:
            if "credit balance" in str(e).lower():
                logger.critical("Credit balance exhausted — stopping classification immediately")
                raise CreditExhaustedError(str(e)) from e
            logger.error("Claude BadRequest for post %s: %s", post.post_id, e)
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
    on_batch_complete: callable = None,
) -> list[PostClassification]:
    """
    Classify all posts using hybrid embedding + Claude routing.
    Processes in batches of cfg.claude_batch_size.
    Calls on_batch_complete(batch_results) after each batch if provided.
    Returns list of PostClassification records (including failed ones).
    """
    results: list[PostClassification] = []
    batch_size = cfg.claude_batch_size

    # Pre-warm the embedding classifier once before batches begin
    try:
        from src.embeddings import get_classifier
        clf = get_classifier()
        if clf.available:
            logger.info("Embedding classifier ready — hybrid routing enabled")
        else:
            logger.info("Embedding classifier unavailable — all posts via full Claude path")
    except Exception:
        logger.info("Embedding classifier init failed — all posts via full Claude path")

    logger.info("Starting classification — %d posts, batch_size=%d", len(posts), batch_size)
    start = datetime.now(timezone.utc)

    for i in range(0, len(posts), batch_size):
        batch = posts[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(posts) + batch_size - 1) // batch_size
        logger.info("Classifying batch %d/%d (%d posts)", batch_num, total_batches, len(batch))

        try:
            batch_results = asyncio.run(_classify_all_async(batch, run_id))
        except CreditExhaustedError:
            logger.critical(
                "Credit exhausted during batch %d/%d — stopping. %d posts classified so far.",
                batch_num, total_batches, len(results),
            )
            raise CreditExhaustedError(
                f"Credit exhausted at batch {batch_num}/{total_batches}",
                classified_so_far=len(results),
            )
        results.extend(batch_results)

        if on_batch_complete:
            on_batch_complete(batch_results)

        # Pace batches to stay within 30k input tokens/minute rate limit
        if i + batch_size < len(posts):
            time.sleep(20)

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    success = sum(1 for r in results if r.classification_status == "success")
    flagged = sum(1 for r in results if r.classification_status == "flagged")
    failed = sum(1 for r in results if r.classification_status == "failed")

    logger.info(
        "Classification complete — total=%d success=%d flagged=%d failed=%d elapsed=%.1fs",
        len(results), success, flagged, failed, elapsed,
    )
    return results
