"""
v3 EvidenceAggregator + ScoringEngine + pipeline gates.

Deterministic, explainable. The ScoringEngine never calls an LLM.
Every score traces to per-signal breakdown rows, each carrying the
content-hashes of the evidence that justified it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.v3.contracts import AgentResult, SignalType

# ── Scoring weights — must sum to 1.0 ──────────────────────────────────────
SIGNAL_WEIGHTS: dict[SignalType, float] = {
    SignalType.CVENT:        0.22,
    SignalType.EVENT_VOLUME: 0.20,
    SignalType.OUTSOURCING:  0.20,
    SignalType.EVENT_TEAM:   0.13,
    SignalType.HIRING:       0.13,
    SignalType.BUDGET:       0.07,
    SignalType.ORG_GRAPH:    0.05,   # industry fit
}

TIER_HOT = 65.0
TIER_WARM = 40.0

# ── Gate 1 thresholds (after Stage 2 — event-fit detection) ────────────────
GATE1_MIN_CVENT = 0.25
GATE1_MIN_VOLUME = 0.30
GATE1_MIN_INDUSTRY = 0.45


@dataclass
class BreakdownRow:
    signal_type: SignalType
    raw_value: float
    weight: float
    contribution: float            # points (0..100 scale) added by this signal
    confidence: float
    evidence_hashes: list[str]
    rationale: str


@dataclass
class ScoreResult:
    overall_score: float
    tier: str                      # hot | warm | cold
    confidence: float
    completeness: float
    disqualified_reason: str | None
    gate_passed: str               # gate1 | gate2 | disqualified
    breakdown: list[BreakdownRow] = field(default_factory=list)
    signal_scores: dict[str, float] = field(default_factory=dict)


# ── EvidenceAggregator ─────────────────────────────────────────────────────
class EvidenceAggregator:
    """
    Normalizes the raw AgentResults: resolves usability, computes per-signal
    confidence, the overall data-completeness score, and the missing-evidence
    list that TargetedResearchAgent consumes.
    """

    def aggregate(self, results: dict[SignalType, AgentResult]) -> dict:
        usable = {s: r for s, r in results.items() if r and r.is_usable()}
        scoring_signals = set(SIGNAL_WEIGHTS)
        present = scoring_signals & set(usable)
        completeness = len(present) / len(scoring_signals) if scoring_signals else 0.0

        gaps = [
            s.value for s in scoring_signals
            if s not in usable or usable[s].confidence < 0.6
        ]
        return {
            "usable": usable,
            "completeness": round(completeness, 3),
            "gaps": gaps,
        }


# ── ScoringEngine ──────────────────────────────────────────────────────────
class ScoringEngine:
    """Deterministic weighted scorer. confidence down-weights each signal."""

    def score(self, results: dict[SignalType, AgentResult],
              completeness: float) -> ScoreResult:
        breakdown: list[BreakdownRow] = []
        signal_scores: dict[str, float] = {}
        total = 0.0
        conf_acc = 0.0
        conf_wt = 0.0

        for signal, weight in SIGNAL_WEIGHTS.items():
            r = results.get(signal)
            if r and r.is_usable():
                value, conf = r.value, r.confidence
                hashes = [e.content_hash for e in r.evidence]
                rationale = (r.evidence[0].claim if r.evidence
                             else f"{signal.value} signal")
            else:
                value, conf, hashes = 0.0, 0.0, []
                rationale = f"{signal.value} signal unavailable"

            # confidence-weighted contribution, on a 0..100 scale
            contribution = value * weight * (0.5 + 0.5 * conf) * 100
            total += contribution
            conf_acc += conf * weight
            conf_wt += weight
            signal_scores[signal.value] = round(value, 3)
            breakdown.append(BreakdownRow(
                signal_type=signal, raw_value=value, weight=weight,
                contribution=round(contribution, 2), confidence=conf,
                evidence_hashes=hashes, rationale=rationale,
            ))

        overall = round(max(0.0, min(100.0, total)), 1)
        confidence = round(conf_acc / conf_wt, 3) if conf_wt else 0.0
        tier = "hot" if overall >= TIER_HOT else "warm" if overall >= TIER_WARM else "cold"

        return ScoreResult(
            overall_score=overall, tier=tier, confidence=confidence,
            completeness=completeness, disqualified_reason=None,
            gate_passed="gate2" if overall >= TIER_WARM else "gate1",
            breakdown=breakdown, signal_scores=signal_scores,
        )


# ── Gates ──────────────────────────────────────────────────────────────────
def gate1_event_fit(results: dict[SignalType, AgentResult]) -> tuple[bool, str | None]:
    """
    After Stage 2. Disqualify a lead only when ALL event-fit evidence is weak:
    no Cvent, low event volume, and off-ICP industry. Saves Stages 3-6.
    """
    cvent = results.get(SignalType.CVENT)
    volume = results.get(SignalType.EVENT_VOLUME)
    org = results.get(SignalType.ORG_GRAPH)

    cvent_v = cvent.value if cvent and cvent.is_usable() else 0.0
    volume_v = volume.value if volume and volume.is_usable() else 0.0
    industry_v = org.value if org and org.is_usable() else 0.0

    if (cvent_v < GATE1_MIN_CVENT and volume_v < GATE1_MIN_VOLUME
            and industry_v < GATE1_MIN_INDUSTRY):
        return False, "no_cvent_low_volume_off_icp"
    return True, None


def gate2_score(score: ScoreResult) -> bool:
    """After Stage 5. Only warm+ leads earn the expensive Stage 6 research."""
    return score.tier in ("warm", "hot")
