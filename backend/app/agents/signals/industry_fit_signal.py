"""
IndustryFitSignalAgent — static industry fit lookup.

Zero external API calls.  Scores the company's industry against a lookup
table of how event-heavy each vertical typically is.

Scoring is purely deterministic.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.agents.signals.base_signal import BaseSignalAgent, SignalResult

logger = logging.getLogger(__name__)

# Industry → event-intensity score (0.0-1.0)
# Ordered by descending specificity so more-specific entries win first.
_INDUSTRY_MAP: list[tuple[str, float]] = [
    # Pure event industry — events ARE the product
    ("event services",          1.00),
    ("events services",         1.00),
    ("conferences",             1.00),
    ("trade shows",             1.00),
    ("tradeshow",               1.00),
    ("meeting planning",        1.00),
    ("hospitality",             0.90),
    # Financial & professional services — heavy event calendars
    ("financial services",      0.85),
    ("banking",                 0.82),
    ("insurance",               0.80),
    ("accounting",              0.78),
    ("consulting",              0.80),
    ("professional services",   0.80),
    ("legal",                   0.72),
    # Healthcare & life sciences — compliance + education events
    ("pharmaceutical",          0.88),
    ("pharma",                  0.88),
    ("biotechnology",           0.85),
    ("medical devices",         0.82),
    ("healthcare",              0.80),
    ("health",                  0.75),
    # Technology
    ("software",                0.78),
    ("saas",                    0.78),
    ("technology",              0.75),
    ("information technology",  0.72),
    ("telecommunications",      0.70),
    ("media",                   0.72),
    # Commercial real estate & construction
    ("real estate",             0.68),
    ("commercial real estate",  0.72),
    # Retail & CPG — trade shows + launches
    ("retail",                  0.60),
    ("consumer goods",          0.62),
    ("food and beverage",       0.58),
    # Education
    ("education",               0.55),
    ("higher education",        0.65),
    # Manufacturing / logistics
    ("manufacturing",           0.48),
    ("logistics",               0.45),
    ("transportation",          0.42),
    # Government / non-profit
    ("non-profit",              0.65),
    ("nonprofit",               0.65),
    ("government",              0.35),
    ("public sector",           0.38),
    # Low-fit
    ("construction",            0.30),
    ("agriculture",             0.25),
    ("mining",                  0.20),
]


def _score_industry(industry: str | None) -> tuple[float, str]:
    if not industry:
        return 0.40, "unknown"

    canon = re.sub(r"\s+", " ", (industry or "").lower().strip())

    for keyword, score in _INDUSTRY_MAP:
        if keyword in canon:
            return score, keyword

    # Partial word match fallback
    for keyword, score in _INDUSTRY_MAP:
        first_word = keyword.split()[0]
        if first_word in canon:
            return score, f"{keyword} (partial)"

    return 0.40, f"unmapped:{industry[:40]}"


class IndustryFitSignalAgent(BaseSignalAgent):
    signal_type = "industry_fit"

    async def collect(
        self,
        company: Any = None,
        identity_profile: dict | None = None,
        **kwargs: Any,
    ) -> SignalResult:
        # Prefer Apollo-resolved industry over DB record
        org = (identity_profile or {}).get("organization") or {}
        industry_raw = (
            org.get("industry")
            or (company.industry if company else None)
        )
        if isinstance(industry_raw, list):
            industry_raw = ", ".join(str(i) for i in industry_raw if i)

        score, matched_label = _score_industry(industry_raw)

        evidence = {
            "industry_raw": industry_raw or "unknown",
            "matched_label": matched_label,
            "fit_score": round(score, 3),
        }

        return SignalResult(
            signal_type=self.signal_type,
            value=score,
            evidence=evidence,
            provider="rule_engine",
            confidence=0.90 if industry_raw else 0.40,
        )
