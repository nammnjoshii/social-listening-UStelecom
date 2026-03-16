"""Embedding-based taxonomy classifier.

Uses sentence-transformers to embed posts and taxonomy node descriptions,
then assigns Pillar + Category via cosine similarity.

If similarity < SIMILARITY_THRESHOLD, returns above_threshold=False and
classify.py falls back to a full Claude call.

The module is optional — if sentence-transformers is not installed, all
classify calls pass through to Claude unmodified.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)

# Below this cosine similarity score → defer to Claude for taxonomy assignment
SIMILARITY_THRESHOLD = 0.38

# Rich, descriptive text per taxonomy node — quality of description directly
# determines embedding quality. More context = better separation in vector space.
TAXONOMY_DESCRIPTIONS: dict[str, dict] = {
    "Network Performance": {
        "description": (
            "cellular network signal quality, coverage areas, connection reliability, "
            "data speeds, network outages, dropped calls, 5G LTE service"
        ),
        "categories": {
            "Coverage": (
                "no signal, dead zones, poor reception, coverage gaps, rural service, "
                "indoor signal weak, no service area, spotty coverage, black spots"
            ),
            "Speed": (
                "slow data, fast internet, download speed, upload speed, buffering, "
                "Mbps bandwidth, speed test result, throttled speeds, lag"
            ),
            "Reliability": (
                "dropped calls, network outage, service interruption, connection dropping, "
                "network down, unreliable service, keeps disconnecting, frequent outages"
            ),
            "5G Experience": (
                "5G network, 5G speed, 5G coverage, mmWave, mid-band 5G, C-band, "
                "5G rollout, 5G availability, next generation network, 5G signal"
            ),
        },
    },
    "Customer Experience": {
        "description": (
            "customer service quality, support interactions, store experience, "
            "app usability, wait times, problem resolution, agent helpfulness"
        ),
        "categories": {
            "Support": (
                "customer service, tech support, call center, long wait time, "
                "unhelpful representative, support chat, problem not resolved, agent rude"
            ),
            "Retail": (
                "store visit, in-store experience, retail staff, store hours, "
                "walk-in support, physical store location, staff knowledge"
            ),
            "Digital Experience": (
                "mobile app crash, website broken, online account issue, app bug, "
                "login problem, autopay failure, digital self-service, app not working"
            ),
        },
    },
    "Pricing & Plans": {
        "description": (
            "monthly bill amount, plan cost, pricing changes, unexpected charges, "
            "promotional offers, plan value, cost comparison"
        ),
        "categories": {
            "Billing": (
                "unexpected charge, wrong bill amount, overcharged, billing error, "
                "invoice dispute, payment issue, charge I didn't authorize"
            ),
            "Plan Structure": (
                "unlimited plan, data plan, family plan, prepaid, postpaid, "
                "plan features, data cap, mobile hotspot, plan tiers"
            ),
            "Fees": (
                "hidden fees, activation fee, upgrade fee, line access fee, taxes, "
                "surcharges, administrative fee, regulatory fee, extra charges"
            ),
        },
    },
    "Device & Equipment": {
        "description": (
            "phone hardware, device upgrades, trade-in programs, equipment issues, "
            "SIM card problems, mobile router, device compatibility"
        ),
        "categories": {
            "Upgrades": (
                "phone upgrade eligibility, new device promotion, latest phone release, "
                "upgrade program, device installment plan, next upgrade"
            ),
            "Trade-Ins": (
                "trade-in value, device trade-in offer, phone exchange credit, "
                "trade-in promotion, old phone return, trade-in appraisal"
            ),
            "Equipment Issues": (
                "broken phone, SIM card not working, device malfunction, "
                "hotspot device issue, router problem, equipment failure, defective device"
            ),
        },
    },
    "Data & Privacy": {
        "description": (
            "data usage limits, throttling after cap, privacy concerns, "
            "personal information handling, data collection practices"
        ),
        "categories": {
            "Data Throttling": (
                "data deprioritization, speed reduced after limit, throttled after cap, "
                "data slowdown, reduced speeds at 50GB, network management"
            ),
            "Privacy Concerns": (
                "selling customer data, personal information shared, privacy policy change, "
                "data tracking, data breach, location data sold, privacy violation"
            ),
        },
    },
    "Competitive Switching": {
        "description": (
            "switching mobile carriers, comparing providers, canceling service, "
            "porting phone number, carrier switch decision"
        ),
        "categories": {
            "Switching Intent": (
                "switching to Verizon, leaving T-Mobile, canceling AT&T service, "
                "porting my number, switching carriers, cancel contract, moving to"
            ),
            "Carrier Comparison": (
                "T-Mobile vs Verizon, AT&T compared to, better carrier option, "
                "which carrier is best, coverage comparison, carrier review"
            ),
        },
    },
}


@dataclass
class EmbeddingResult:
    pillar: str
    category: str
    pillar_score: float
    category_score: float
    above_threshold: bool


class TaxonomyEmbeddingClassifier:
    """Classifies posts into taxonomy Pillar + Category using cosine similarity.

    Thread-safe after __init__ — the model and pre-computed embeddings are
    read-only at inference time.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(model_name)
            self._available = True
            logger.info("Loaded sentence transformer: %s", model_name)
        except ImportError:
            logger.warning(
                "sentence-transformers not installed — embedding classifier disabled. "
                "Install with: pip install sentence-transformers"
            )
            self._available = False
            return

        self._pillar_embeddings: dict[str, np.ndarray] = {}
        self._category_embeddings: dict[str, dict[str, np.ndarray]] = {}
        self._precompute_taxonomy_embeddings()

    def _precompute_taxonomy_embeddings(self) -> None:
        for pillar, data in TAXONOMY_DESCRIPTIONS.items():
            pillar_text = f"{pillar}: {data['description']}"
            self._pillar_embeddings[pillar] = self._model.encode(
                pillar_text, normalize_embeddings=True
            )
            self._category_embeddings[pillar] = {}
            for cat, cat_desc in data["categories"].items():
                cat_text = f"{pillar} > {cat}: {cat_desc}"
                self._category_embeddings[pillar][cat] = self._model.encode(
                    cat_text, normalize_embeddings=True
                )
        logger.info(
            "Pre-computed taxonomy embeddings: %d pillars, %d categories total",
            len(self._pillar_embeddings),
            sum(len(v) for v in self._category_embeddings.values()),
        )

    @property
    def available(self) -> bool:
        return self._available

    def classify(self, text: str) -> EmbeddingResult | None:
        """Classify text into the nearest taxonomy Pillar + Category.

        Returns None if classifier is unavailable (sentence-transformers not installed).
        Returns EmbeddingResult with above_threshold=False when similarity is too low.
        """
        if not self._available:
            return None

        # Truncate to ~512 tokens worth of characters to stay within model limits
        post_emb = self._model.encode(text[:1000], normalize_embeddings=True)

        # Score all pillars
        pillar_scores = {
            p: float(np.dot(post_emb, emb))
            for p, emb in self._pillar_embeddings.items()
        }
        best_pillar = max(pillar_scores, key=pillar_scores.get)
        best_pillar_score = pillar_scores[best_pillar]

        # Score all categories within the best pillar
        cat_scores = {
            c: float(np.dot(post_emb, emb))
            for c, emb in self._category_embeddings[best_pillar].items()
        }
        best_category = max(cat_scores, key=cat_scores.get)
        best_category_score = cat_scores[best_category]

        return EmbeddingResult(
            pillar=best_pillar,
            category=best_category,
            pillar_score=best_pillar_score,
            category_score=best_category_score,
            above_threshold=best_pillar_score >= SIMILARITY_THRESHOLD,
        )


# ── Module-level singleton — initialized once, reused across all batches ──────
_classifier: TaxonomyEmbeddingClassifier | None = None


def get_classifier() -> TaxonomyEmbeddingClassifier:
    """Return the module-level singleton classifier, initializing if needed."""
    global _classifier
    if _classifier is None:
        _classifier = TaxonomyEmbeddingClassifier()
    return _classifier
