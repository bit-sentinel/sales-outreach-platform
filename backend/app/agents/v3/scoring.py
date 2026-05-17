"""
v3 EvidenceAggregator + ScoringEngine + pipeline gates.

Deterministic, explainable. The ScoringEngine never calls an LLM.
Every score traces to per-signal breakdown rows, each carrying the
content-hashes of the evidence that justified it.

Scoring model: v2 LaunchHouse Signal-Tune (5-signal normalized).
Weights reflect the original v2 point allocation (69 pts total):
  CVENT 24 → 34.8 %, OUTSOURCING 20 → 29.0 %, EVENT_TEAM 12 → 17.4 %,
  ORG_GRAPH 9 → 13.0 %, BUDGET 4 → 5.8 %.
EVENT_VOLUME and HIRING are loaded as context for caps/gates but do not
contribute scoring points directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.v3.contracts import AgentResult, SignalType

# ── Scoring weights — must sum to 1.0 ──────────────────────────────────────
SIGNAL_WEIGHTS: dict[SignalType, float] = {
    SignalType.CVENT:       0.348,   # S1 urgency
    SignalType.OUTSOURCING: 0.290,   # S2 capacity gap
    SignalType.EVENT_TEAM:  0.174,   # S5 persona authority
    SignalType.ORG_GRAPH:   0.130,   # S6 industry fit
    SignalType.BUDGET:      0.058,   # S7 financial guardrail
}

TIER_HOT = 75.0
TIER_WARM = 50.0

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


# ── Signal value helpers ───────────────────────────────────────────────────

def _urgency_value(r: AgentResult) -> float:
    """Map CVENT payload → urgency score. Optimal window: 31-120 days out."""
    payload = r.payload
    soonest = payload.get("soonest_days")
    if soonest is None:
        # Detected historically but no upcoming event — still a weak signal
        return 0.15 if payload.get("detected") else 0.0
    soonest = int(soonest)
    if soonest <= 30:
        return 0.85   # very soon — we can still pitch but window is tight
    if soonest <= 120:
        return 1.0    # optimal buying window (6 weeks – 4 months)
    if soonest <= 180:
        return 0.60   # worth pursuing
    return 0.30       # far out, low urgency


def _persona_value(results: dict[SignalType, AgentResult]) -> float:
    """
    Derive buyer persona strength from IDENTITY seniority/title.
    Falls back to EVENT_TEAM agent value if IDENTITY is unavailable.
    """
    identity = results.get(SignalType.IDENTITY)
    if identity and identity.is_usable():
        combined = (
            (identity.payload.get("seniority") or "") + " " +
            (identity.payload.get("title") or "")
        ).lower()
        if any(k in combined for k in (
            "vp", "vice president", "director", "head of", "chief",
            "ceo", "coo", "cmo", "cxo", "president",
        )):
            return 1.0
        if any(k in combined for k in ("manager", "senior", "lead", "principal")):
            return 0.75
        if any(k in combined for k in ("coordinator", "specialist", "associate", "planner")):
            return 0.45
    team = results.get(SignalType.EVENT_TEAM)
    if team and team.is_usable():
        return team.value
    return 0.0


def _signal_value(signal: SignalType, results: dict[SignalType, AgentResult]) -> float:
    """Effective value for a signal, applying enriched extractors for CVENT/EVENT_TEAM."""
    if signal == SignalType.CVENT:
        r = results.get(SignalType.CVENT)
        return _urgency_value(r) if (r and r.is_usable()) else 0.0
    if signal == SignalType.EVENT_TEAM:
        return _persona_value(results)
    r = results.get(signal)
    return r.value if (r and r.is_usable()) else 0.0


def _apply_caps(
    raw_score: float,
    results: dict[SignalType, AgentResult],
    urgency_v: float,
    persona_v: float,
) -> float:
    """Three caps that prevent a single signal from gaming the tier threshold."""
    outsourcing = results.get(SignalType.OUTSOURCING)
    outsourcing_v = outsourcing.value if (outsourcing and outsourcing.is_usable()) else 0.0

    # Cap 1: Cvent-only — event detected but no capacity or persona evidence
    if raw_score > 50 and urgency_v > 0.4 and outsourcing_v < 0.30 and persona_v < 0.30:
        raw_score = min(raw_score, 45.0)

    # Cap 2: No buyer — can't exceed Warm threshold without a decision-maker signal
    if raw_score > 70 and persona_v < 0.40:
        raw_score = min(raw_score, 70.0)

    # Cap 3: No event evidence — org/outsourcing strength without any event signal
    event_vol = results.get(SignalType.EVENT_VOLUME)
    event_vol_v = event_vol.value if (event_vol and event_vol.is_usable()) else 0.0
    cvent = results.get(SignalType.CVENT)
    cvent_raw = cvent.value if (cvent and cvent.is_usable()) else 0.0
    if raw_score > 65 and urgency_v < 0.20 and cvent_raw < 0.20 and event_vol_v < 0.20:
        raw_score = min(raw_score, 65.0)

    return raw_score


def _hot_compound_gate(
    urgency_v: float,
    outsourcing_v: float,
    persona_v: float,
    results: dict[SignalType, AgentResult],
) -> bool:
    """Hot tier requires ≥2 strong confirming signals to prevent false positives."""
    hiring = results.get(SignalType.HIRING)
    hiring_v = hiring.value if (hiring and hiring.is_usable()) else 0.0
    strong = sum([
        urgency_v >= 0.60,
        outsourcing_v >= 0.60,
        persona_v >= 0.75,
        hiring_v >= 0.60,
    ])
    return strong >= 2


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

    def score(
        self, results: dict[SignalType, AgentResult], completeness: float
    ) -> ScoreResult:
        urgency_v = _signal_value(SignalType.CVENT, results)
        persona_v = _persona_value(results)
        outsourcing_r = results.get(SignalType.OUTSOURCING)
        outsourcing_v = outsourcing_r.value if (outsourcing_r and outsourcing_r.is_usable()) else 0.0

        breakdown: list[BreakdownRow] = []
        signal_scores: dict[str, float] = {}
        total = 0.0
        conf_acc = 0.0
        conf_wt = 0.0

        for signal, weight in SIGNAL_WEIGHTS.items():
            r = results.get(signal)
            if r and r.is_usable():
                value = _signal_value(signal, results)
                conf = r.confidence
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

        total = _apply_caps(total, results, urgency_v, persona_v)
        overall = round(max(0.0, min(100.0, total)), 1)
        confidence = round(conf_acc / conf_wt, 3) if conf_wt else 0.0

        # Hot requires compound confirmation; otherwise fall through to warm/cold
        if overall >= TIER_HOT and _hot_compound_gate(urgency_v, outsourcing_v, persona_v, results):
            tier = "hot"
        elif overall >= TIER_WARM:
            tier = "warm"
        else:
            tier = "cold"

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
