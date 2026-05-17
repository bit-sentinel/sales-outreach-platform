"""
Pure-Python scoring engine for the signal-centric v2 pipeline.

No LLM.  No external I/O.  Takes a list of SignalResult objects and
returns a final score (0-100), tier, and a structured breakdown.

The LLM (ExplainerAgent) is called separately — after scoring — so the
score is always deterministic and auditable independent of explanation.
"""

from __future__ import annotations

from typing import Any

from app.agents.signals.base_signal import SIGNAL_WEIGHTS, SignalResult


def compute_score(signals: list[SignalResult]) -> dict[str, Any]:
    """
    Aggregate signal results into a final 0-100 score.

    Returns:
        overall_score   float       0-100
        tier            str         "hot" | "warm" | "cold"
        signal_scores   dict        signal_type → raw value (0-1)  [legacy compat]
        signal_breakdown dict       signal_type → {value, weight, contribution, evidence}
        weights_used    dict        signal_type → weight applied
        coverage        float       fraction of signal types that were actually collected
    """
    signal_map: dict[str, SignalResult] = {s.signal_type: s for s in signals}

    # Fill any missing signal types with a zero-value placeholder
    all_types = list(SIGNAL_WEIGHTS.keys())
    coverage = len(signal_map) / max(len(all_types), 1)

    # Weighted sum — weights are normalised inside SignalResult.__post_init__
    # so this is already a true weighted average over the signals we have.
    # For missing signals we scale down the score proportionally (honest penalty).
    weight_collected = sum(SIGNAL_WEIGHTS[t] for t in signal_map)
    if weight_collected <= 0:
        return _empty_result()

    raw_weighted = sum(s.weighted_contribution() for s in signal_map.values())
    # Normalise to the weight actually collected (so 5/6 signals still gives a fair score)
    normalised = raw_weighted / weight_collected  # 0-1
    overall_score = round(normalised * 100, 1)

    # Tier thresholds
    if overall_score >= 75:
        tier = "hot"
    elif overall_score >= 50:
        tier = "warm"
    else:
        tier = "cold"

    signal_scores: dict[str, float] = {
        t: round(signal_map[t].value, 3) if t in signal_map else 0.0
        for t in all_types
    }
    signal_breakdown: dict[str, Any] = {
        t: {
            "value":        round(signal_map[t].value, 3) if t in signal_map else 0.0,
            "weight":       SIGNAL_WEIGHTS[t],
            "contribution": round(signal_map[t].weighted_contribution(), 3) if t in signal_map else 0.0,
            "provider":     signal_map[t].provider if t in signal_map else "missing",
            "confidence":   signal_map[t].confidence if t in signal_map else 0.0,
            "evidence":     signal_map[t].evidence if t in signal_map else {},
        }
        for t in all_types
    }

    return {
        "overall_score":     overall_score,
        "tier":              tier,
        "signal_scores":     signal_scores,
        "signal_breakdown":  signal_breakdown,
        "weights_used":      SIGNAL_WEIGHTS,
        "coverage":          round(coverage, 2),
        "pipeline_version":  "v2",
    }


def _empty_result() -> dict[str, Any]:
    return {
        "overall_score":    0.0,
        "tier":             "cold",
        "signal_scores":    {t: 0.0 for t in SIGNAL_WEIGHTS},
        "signal_breakdown": {},
        "weights_used":     SIGNAL_WEIGHTS,
        "coverage":         0.0,
        "pipeline_version": "v2",
    }
