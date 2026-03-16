"""BERTopic-based unsupervised topic discovery.

Runs on the full cleaned corpus BEFORE classification to surface data-driven
topics from actual post language — complementing the expert-designed taxonomy.

Discovered topics are:
  1. Clustered via HDBSCAN on sentence embeddings (BERTopic)
  2. Labeled by Claude with concise human-readable names
  3. Printed as a discovery report in the pipeline console

This is a corpus-level analysis step, not a per-post classifier.
The output informs the analyst about what users are actually discussing;
it does not replace the PostClassification taxonomy fields.

Usage:
    from src.topic_discovery import discover_topics, print_topic_report
    topics = discover_topics(texts)
    print_topic_report(topics)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredTopic:
    topic_id: int
    keywords: list[str]
    label: str                          # Claude-generated name, or keyword fallback
    post_count: int
    representative_docs: list[str] = field(default_factory=list)


def discover_topics(
    texts: list[str],
    min_topic_size: int = 8,
    nr_topics: int | str = "auto",
    label_with_claude: bool = True,
) -> list[DiscoveredTopic]:
    """Run BERTopic on post texts and return discovered topics.

    Args:
        texts:            Normalized post texts (cleaned corpus).
        min_topic_size:   Minimum posts required to form a topic cluster.
        nr_topics:        Target cluster count or "auto" (let HDBSCAN decide).
        label_with_claude: Whether to use Claude to name each cluster.

    Returns:
        List of DiscoveredTopic, sorted by post_count descending.
        Empty list if BERTopic/sentence-transformers are not installed or corpus
        is too small.
    """
    try:
        from bertopic import BERTopic
        from sentence_transformers import SentenceTransformer
    except ImportError:
        logger.warning(
            "BERTopic or sentence-transformers not installed — skipping topic discovery. "
            "Install with: pip install bertopic sentence-transformers"
        )
        return []

    if len(texts) < min_topic_size * 2:
        logger.warning(
            "Corpus too small for BERTopic (%d texts, need >= %d) — skipping",
            len(texts),
            min_topic_size * 2,
        )
        return []

    logger.info(
        "Running BERTopic on %d posts (min_topic_size=%d, nr_topics=%s)",
        len(texts), min_topic_size, nr_topics,
    )

    embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

    topic_model = BERTopic(
        embedding_model=embedding_model,
        min_topic_size=min_topic_size,
        nr_topics=nr_topics,
        calculate_probabilities=False,
        verbose=False,
    )

    topic_model.fit_transform(texts)

    topic_info = topic_model.get_topic_info()
    # Topic -1 is the HDBSCAN noise/outlier cluster — skip it
    topic_info = topic_info[topic_info["Topic"] != -1]

    results: list[DiscoveredTopic] = []
    for _, row in topic_info.iterrows():
        topic_id = int(row["Topic"])
        keywords = [word for word, _ in topic_model.get_topic(topic_id)[:8]]
        rep_docs = topic_model.get_representative_docs(topic_id)[:3]
        post_count = int(row["Count"])
        # Default label from top keywords until Claude names it
        label = " / ".join(keywords[:4])

        results.append(DiscoveredTopic(
            topic_id=topic_id,
            keywords=keywords,
            label=label,
            post_count=post_count,
            representative_docs=rep_docs,
        ))

    if label_with_claude and results:
        results = _label_topics_with_claude(results)

    results.sort(key=lambda t: t.post_count, reverse=True)
    logger.info("BERTopic discovered %d topics (excl. outliers)", len(results))
    return results


def _label_topics_with_claude(topics: list[DiscoveredTopic]) -> list[DiscoveredTopic]:
    """Ask Claude to generate concise human-readable labels for each cluster."""
    try:
        import anthropic
        from src.config import cfg
    except ImportError:
        return topics

    client = anthropic.Anthropic(api_key=cfg.claude_api_key)

    topics_text = "\n".join(
        f'Topic {t.topic_id}: keywords=[{", ".join(t.keywords[:6])}] '
        f'example="{t.representative_docs[0][:150] if t.representative_docs else ""}"'
        for t in topics
    )

    prompt = (
        "You are analyzing clusters of telecom social media posts (T-Mobile, Verizon, AT&T).\n"
        "For each cluster below, provide a concise 3-5 word label capturing the main theme.\n"
        "Return ONLY a JSON object mapping topic_id (as string) to label string. No extra text.\n\n"
        f"{topics_text}"
    )

    try:
        response = client.messages.create(
            model=cfg.claude_model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        labels: dict[str, str] = json.loads(raw)
        for topic in topics:
            key = str(topic.topic_id)
            if key in labels:
                topic.label = labels[key]

        logger.info("Claude labeled %d/%d topics", len(labels), len(topics))

    except Exception as e:
        logger.warning("Claude topic labeling failed — keeping keyword labels: %s", e)

    return topics


def print_topic_report(topics: list[DiscoveredTopic]) -> None:
    """Print a BERTopic discovery summary to stdout."""
    if not topics:
        print("  [dim]BERTopic: no topics discovered (corpus too small or library not installed)")
        return

    print(f"\n  {'─' * 56}")
    print(f"  BERTopic Discovery — {len(topics)} topics found")
    print(f"  {'─' * 56}")
    for t in topics:
        print(f"  [{t.post_count:4d} posts]  {t.label}")
        print(f"              keywords: {', '.join(t.keywords[:6])}")
    print(f"  {'─' * 56}\n")
