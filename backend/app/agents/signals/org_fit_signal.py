"""
OrgFitSignalAgent — scores contact seniority / department fit AND company size fit.

Data flow:
  - Purely from Apollo identity_profile + company/contact DB records
  - Zero external API calls

Scoring (pure rule-based, deterministic):
  Combined score = (seniority_score * 0.35) + (dept_score * 0.35) + (size_score * 0.30)
  Each sub-score is 0.0 – 1.0.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.signals.base_signal import BaseSignalAgent, SignalResult

logger = logging.getLogger(__name__)

# ── Seniority scoring ─────────────────────────────────────────────────────
_SENIORITY_SCORES: dict[str, float] = {
    "director":    1.00,  # sweet spot — owns decisions, not too removed
    "manager":     0.90,
    "c_suite":     0.60,  # decision maker but may delegate; harder to reach for ops topics
    "vp":          0.70,
    "senior":      0.80,
    "individual_contributor": 0.60,
    "entry":       0.30,
}

# ── Department scoring ───────────────────────────────────────────────────
_DEPT_KEYWORDS: list[tuple[list[str], float]] = [
    (["event", "events", "conference", "meeting"],   1.00),
    (["field marketing", "demand gen"],              0.95),
    (["marketing", "brand", "communications"],       0.75),
    (["sales", "business development", "revenue"],   0.55),
    (["it", "information technology", "operations"], 0.40),
    (["hr", "human resources", "people"],            0.25),
    (["finance", "legal", "admin"],                  0.15),
]

# ── Company size scoring (employee count) ─────────────────────────────────
def _size_score(employee_count: int | None) -> float:
    if employee_count is None:
        return 0.30  # unknown
    if 500 <= employee_count <= 5000:
        return 1.00  # sweet spot
    if 5001 <= employee_count <= 20000:
        return 0.75  # larger but still outsource overflow
    if 200 <= employee_count < 500:
        return 0.60
    if employee_count > 20000:
        return 0.30  # likely has in-house team
    return 0.20  # < 200, too small


def _seniority_score(seniority: str | None, title: str | None) -> tuple[float, str]:
    raw = (seniority or title or "").lower()
    if not raw:
        return 0.30, "unknown"
    for key, score in _SENIORITY_SCORES.items():
        if key in raw:
            return score, key
    # Fallback: title keyword scan
    if any(w in raw for w in ("chief", "ceo", "cmo", "coo", "cto", "president")):
        return _SENIORITY_SCORES["c_suite"], "c_suite"
    if any(w in raw for w in ("vp", "vice president")):
        return _SENIORITY_SCORES["vp"], "vp"
    if "director" in raw:
        return _SENIORITY_SCORES["director"], "director"
    if "manager" in raw:
        return _SENIORITY_SCORES["manager"], "manager"
    if any(w in raw for w in ("coordinator", "specialist", "associate", "analyst")):
        return _SENIORITY_SCORES["individual_contributor"], "individual_contributor"
    return 0.30, "unknown"


def _dept_score(department: str | None, title: str | None) -> tuple[float, str]:
    raw = (department or title or "").lower()
    if not raw:
        return 0.30, "unknown"
    for keywords, score in _DEPT_KEYWORDS:
        for kw in keywords:
            if kw in raw:
                return score, keywords[0]
    return 0.30, "other"


class OrgFitSignalAgent(BaseSignalAgent):
    signal_type = "org_fit"

    async def collect(
        self,
        identity_profile: dict | None = None,
        contact: Any = None,
        company: Any = None,
        **kwargs: Any,
    ) -> SignalResult:
        # Resolve values — prefer Apollo identity_profile over DB records
        profile = identity_profile or {}

        seniority_raw = profile.get("seniority") or (contact.title if contact else None)
        title_raw = profile.get("title") or (contact.title if contact else None)
        dept_raw = (
            profile.get("department")
            or (contact.department if contact else None)
        )
        if isinstance(dept_raw, list):
            dept_raw = ", ".join(str(d) for d in dept_raw if d)

        emp_count: int | None = None
        org = profile.get("organization") or {}
        emp_raw = org.get("employee_count")
        if emp_raw:
            try:
                emp_count = int(emp_raw)
            except (ValueError, TypeError):
                pass
        if emp_count is None and company and company.employee_count:
            emp_count = company.employee_count

        seniority_val, seniority_label = _seniority_score(seniority_raw, title_raw)
        dept_val, dept_label = _dept_score(dept_raw, title_raw)
        size_val = _size_score(emp_count)

        combined = (seniority_val * 0.35) + (dept_val * 0.35) + (size_val * 0.30)

        has_apollo = bool(profile)
        evidence = {
            "seniority_label": seniority_label,
            "seniority_score": seniority_val,
            "department_label": dept_label,
            "department_score": dept_val,
            "company_size": emp_count,
            "size_score": size_val,
            "combined_score": round(combined, 3),
            "title_used": title_raw or "",
            "department_used": dept_raw or "",
            "data_source": "apollo" if has_apollo else "import",
        }

        return SignalResult(
            signal_type=self.signal_type,
            value=combined,
            evidence=evidence,
            provider="apollo" if has_apollo else "import_data",
            confidence=0.95 if has_apollo else 0.55,
        )
