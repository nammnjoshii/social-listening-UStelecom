# Python Pipeline Standards — U.S. Telecom Social Listening

Adapted from `python-pro` skill. Defines type-safe, async-ready Python standards for the telecom social listening pipeline running on Python 3.10+.

> **Client:** T-Mobile US | **Competitors:** AT&T Mobility, Verizon

---

## Design Principles

- All pipeline functions must have **full type annotations**
- Use **Pydantic models** for all Claude API inputs and outputs (aligned with `OUTPUT-SCHEMA.md`)
- Use **async/await** for concurrent Claude API classification calls
- Use **structured error handling** — never bare `except:`, always log before re-raising
- Use **pytest fixtures** to mock Claude API responses in unit tests

---

## 1. Pydantic Output Model

The `PostClassification` model must align exactly with the JSON schema in `OUTPUT-SCHEMA.md`:

```python
from __future__ import annotations
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, model_validator

Platform = Literal["Instagram", "Reddit", "X"]
Brand = Literal["T-Mobile US", "Verizon", "AT&T Mobility"]
Sentiment = Literal["Positive", "Neutral", "Negative"]
Intent = Literal["Complaint", "Inquiry", "Praise", "Recommendation"]
Emotion = Literal["Frustration", "Satisfaction", "Confusion", "Excitement"]
ClassificationStatus = Literal["classified", "flagged", "review_required"]


class PostClassification(BaseModel):
    post_id: str
    platform: Platform
    timestamp: datetime
    normalized_text: str
    brands: list[Brand]
    brand_confidence: float = Field(ge=0.0, le=1.0)
    pillar: str
    category: str
    theme: str
    topic: str
    sentiment: Sentiment
    intent: Intent
    emotion: Emotion
    confidence: float = Field(ge=0.0, le=1.0)
    classification_status: ClassificationStatus
    taxonomy_version: str
    schema_version: str
    pipeline_run_id: str

    @model_validator(mode="after")
    def flag_low_confidence(self) -> PostClassification:
        if self.confidence <= 0.15:
            self.classification_status = "flagged"
        return self
```

---

## 2. Async Claude API Classification

Classify posts concurrently using `asyncio` to maximize throughput while respecting rate limits:

```python
import asyncio
import anthropic
import logging
from typing import Sequence

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-6"
MAX_CONCURRENT = 10  # concurrent API calls


async def classify_post(
    client: anthropic.AsyncAnthropic,
    post_text: str,
    prompt_template: str,
    semaphore: asyncio.Semaphore,
) -> dict:
    async with semaphore:
        try:
            response = await client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt_template.format(post=post_text)}],
            )
            return response.content[0].text
        except anthropic.RateLimitError:
            logger.warning("Rate limit hit — backing off 10s before retry")
            await asyncio.sleep(10)
            raise
        except anthropic.APIError as e:
            logger.error("Claude API error: %s", e)
            raise


async def classify_batch(
    posts: Sequence[str],
    prompt_template: str,
) -> list[dict]:
    client = anthropic.AsyncAnthropic()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    tasks = [classify_post(client, post, prompt_template, semaphore) for post in posts]
    return await asyncio.gather(*tasks, return_exceptions=False)
```

---

## 3. Schema Validation at Pipeline Boundaries

Validate all Claude outputs against the Pydantic model before writing to storage. Reject malformed records and log them separately for review:

```python
import json
from pathlib import Path

def validate_and_parse(
    raw_output: str,
    run_id: str,
) -> PostClassification | None:
    try:
        data = json.loads(raw_output)
        data["pipeline_run_id"] = run_id
        return PostClassification.model_validate(data)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("Schema validation failed for run %s: %s", run_id, e)
        return None
```

---

## 4. Pipeline Entry Point with Structured Logging

```python
import logging
import uuid
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","run_id":"%(run_id)s","msg":"%(message)s"}',
)


def run_pipeline(posts: list[str], prompt_template: str) -> list[PostClassification]:
    run_id = str(uuid.uuid4())
    log = logging.LoggerAdapter(logger, {"run_id": run_id})

    log.info("Pipeline started — %d posts to classify", len(posts))
    start = datetime.now(timezone.utc)

    raw_outputs = asyncio.run(classify_batch(posts, prompt_template))

    results: list[PostClassification] = []
    flagged: int = 0
    for raw in raw_outputs:
        parsed = validate_and_parse(raw, run_id)
        if parsed:
            results.append(parsed)
            if parsed.classification_status == "flagged":
                flagged += 1

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    log.info(
        "Pipeline complete — classified=%d flagged=%d elapsed_s=%.1f",
        len(results), flagged, elapsed,
    )
    return results
```

---

## 5. Pytest Fixtures for Claude API Mocking

Unit tests must never call the real Claude API. Use fixtures to inject deterministic responses:

```python
import pytest
from unittest.mock import AsyncMock, patch

MOCK_CLASSIFICATION = json.dumps({
    "brands": ["T-Mobile US"],
    "brand_confidence": 0.95,
    "sentiment": "Negative",
    "intent": "Complaint",
    "emotion": "Frustration",
    "pillar": "Network Performance",
    "category": "Coverage",
    "theme": "Urban Coverage",
    "topic": "Signal loss in subway",
    "confidence": 0.88,
    "classification_status": "classified",
    "taxonomy_version": "2.0.0",
    "schema_version": "1.0",
    "post_id": "test_001",
    "platform": "Reddit",
    "timestamp": "2026-03-14T10:00:00Z",
    "normalized_text": "lost signal again on the subway tmobile is terrible",
    "pipeline_run_id": "test-run-001",
})


@pytest.fixture
def mock_claude_response():
    with patch("anthropic.AsyncAnthropic") as mock_client:
        instance = mock_client.return_value.__aenter__.return_value
        instance.messages.create = AsyncMock(
            return_value=type("Response", (), {"content": [type("Block", (), {"text": MOCK_CLASSIFICATION})()]})()
        )
        yield mock_client


def test_classify_post_returns_valid_model(mock_claude_response):
    results = asyncio.run(classify_batch(["lost signal again on the subway"], "{post}"))
    assert len(results) == 1
```

---

## 6. Error Handling Hierarchy

| Error Type | Handler | Action |
|-----------|---------|--------|
| `anthropic.RateLimitError` | Retry with backoff | Wait 10s, retry once, then fail |
| `anthropic.APIError` | Log and raise | Surface to caller, do not swallow |
| `json.JSONDecodeError` | Log warning | Record as `None`, continue batch |
| `pydantic.ValidationError` | Log warning | Record as `None`, flag for review |
| Quota assertion failure | Raise immediately | Abort pipeline — do not proceed with partial data |

---

## Constraints

**MUST:**
- Use `from __future__ import annotations` for deferred evaluation
- Annotate all function signatures (parameters + return types)
- Use Pydantic `model_validate()` — not `parse_obj()` (deprecated)
- Use `asyncio.Semaphore` to cap concurrent API calls
- Log run_id on every log line for traceability

**MUST NOT:**
- Use bare `except:` — always catch specific exception types
- Call the real Claude API in unit tests — always mock
- Ignore `pydantic.ValidationError` — treat as a data quality issue requiring investigation
- Use `print()` for pipeline output — use `logging` with structured format

---

## Related Skills

- [CLAUDE-PROMPT-LIBRARY.md](CLAUDE-PROMPT-LIBRARY.md) — prompt templates used in `classify_post()`
- [OUTPUT-SCHEMA.md](../OUTPUT-SCHEMA.md) — canonical JSON schema that Pydantic models mirror
- [EVALUATION-METRICS.md](EVALUATION-METRICS.md) — tracking accuracy and flagged post rates per run
- [PANDAS-DATA-PIPELINE.md](PANDAS-DATA-PIPELINE.md) — downstream aggregation of `PostClassification` records
