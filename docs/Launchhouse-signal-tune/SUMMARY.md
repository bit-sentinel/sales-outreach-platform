# LaunchHouse Signal-Tune Package — Summary

**Package version:** `market_signals_v2_2026_05`  
**Prepared for:** LaunchHouse Events — CTO and engineering team  
**Source of truth:** `LaunchHouse_Market_Signals_Lead_Scoring_Report_v2_CTO_Handoff.pdf` (19 pages)  
**Supporting docs:** `Market_Signal_Scoring_Tune_CTO_Implementation_Handoff.docx` · `Signal_Library_Appendix.docx` · `CTO_Handoff_Checklist.docx`

---

## 1. Core Strategic Shift

The previous scoring model treated **Cvent usage as a primary scoring driver**.  
The v2 model flips this: **Cvent usage is now a qualification gate** — it narrows the pool but does not itself produce a high score.

> "Your agent should not ask: 'Who uses Cvent?' It should ask: 'Which Cvent-using event team has a real operating reason to need execution help *now*?'"

High scores now come from **compound evidence of operational pressure**:
- A verified upcoming event (hard deadline)
- An active event/Cvent hiring gap (capacity strain)
- Visible Cvent complexity / advanced module usage (delivery risk)
- MarTech and reporting pressure (data flow stakes)
- The right buyer persona (authority to convert)

---

## 2. Project Scope — What This Is and Isn't

| In scope | Out of scope |
|---|---|
| ResearchAgent query sets | New pipeline architecture |
| EnrichmentAgent extraction prompts | New database tables or schema migrations |
| ScoringAgent weights, caps, tier rules | New external data providers |
| PersonalizationAgent routing and hook language | Template rebuilding |

**Non-negotiable constraint:** Prefer prompt/config changes and existing JSONB storage. Only add optional Pydantic fields (default=None) if strict schema validation forces it. No migration should be needed.

---

## 3. Updated 8-Signal Scoring Model

Replaces the prior 10-signal model. Total weight sums to 100%.

| # | Signal | Weight | Role |
|---|---|---|---|
| S1 | Verified upcoming event urgency | **24%** | Primary urgency driver |
| S2 | Event/Cvent hiring and capacity gap | **20%** | Best proxy for capacity strain |
| S3 | Cvent complexity / advanced module usage | **16%** | Delivery risk indicator |
| S4 | MarTech, reporting, and data pressure | **14%** | Business-criticality of Cvent quality |
| S5 | Buyer / persona authority | **12%** | Conversion likelihood |
| S6 | Event program + industry pattern | **9%** | Repeatability and ongoing need |
| S7 | Company fit / budget maturity | **4%** | Guardrail only — do not inflate |
| S8 | Cvent Certified profile signal | **1%** | Sophistication bonus only |

---

## 4. Signal Definitions and Scoring Logic

### S1 — Verified Upcoming Event Urgency (24%)
- **Qualifies:** Official event page, Cvent registration page, press release, or industry calendar with a confirmed future date. Internal mentions without a date do not qualify.
- **Scoring windows:** 31–120 days = maximum score; 0–30 days = high (route to rush support); 120+ days = nurture/planning; no future date = cap temporal score at 40% of max urgency weight.
- **Extract:** `event_name`, `event_date`, `days_until_event`, `registration_url`, `source_url`, `source_confidence`

### S2 — Event/Cvent Hiring and Capacity Gap (20%)
- **Qualifies:** Active job posting for event execution or Cvent technology role. Score higher when posting explicitly mentions Cvent, Attendee Hub, OnArrival, registration, integrations, Salesforce, Marketo, HubSpot, or reporting.
- **Scoring:** Very High when multiple open roles or Cvent-specific wording. Medium when generic event coordinator with no tech mention.
- **Posting age:** 0–14 days = very high urgency; 15–45 days = high; 46–90 days = medium (potential gap); 90+ days = medium/low (stale).
- **Extract:** `role_title`, `posting_url`, `cvent_terms_in_jd`, `integration_terms`, `posting_date`, `posting_age_days`, `signal_strength`

### S3 — Cvent Complexity / Advanced Module Usage (16%)
- **Qualifies:** Public evidence of advanced Cvent features beyond basic registration.
- **High-value complexity signals:** Attendee Hub, OnArrival, Appointments, exhibitor/sponsor management, housing module, payment processing via Cvent, Salesforce/Marketo/HubSpot/Workday/Snowflake integrations, Cvent Data Bridge, API usage, multi-track sessions, complex approval flows.
- **Score higher:** more modules + more attendee-facing risk; evidence from event pages or job descriptions beats generic platform claims.
- **Extract:** `modules_detected`, `integration_targets`, `complexity_source_urls`, `complexity_confidence`

### S4 — MarTech, Reporting, and Data Pressure (14%)
- **Qualifies:** Evidence that event data flows into marketing/revenue systems or that there is pressure around reporting, attribution, or data quality.
- **Signal terms:** Salesforce, HubSpot, Marketo, Snowflake, Data Cloud, Cvent Data Bridge, attribution, campaign reporting, lead flow, pipeline, revenue reporting, CRM sync, data hygiene, registration data quality, post-event reporting, event ROI.
- **Score High when:** event data is tied to revenue reporting, pipeline attribution, or executive reporting.
- **Extract:** `martech_tools_detected`, `reporting_pressure_terms`, `data_flow_evidence`, `source_urls`

### S5 — Buyer / Persona Authority (12%)
- **Highest:** Head/Director/VP Events, Event Operations, Event Technology, Field Marketing, Marketing Ops, Demand Gen, RevOps, CMO/COO (in SMB).
- **Lower:** Junior coordinators unless paired with clear pain signals.
- **Score reduced** if no qualifying buyer is identified.
- **Seniority tier mapping:** Director/VP/Head = top; Manager = high; Coordinator/Specialist = medium; IC without ownership signals = low.

### S6 — Event Program + Industry Pattern (9%)
- **Score the event motion, not the industry label.** A fintech user conference scores the same as an association annual summit.
- **Priority program types:** (1) Annual conference/summit; (2) User/customer conference; (3) Trade show/expo; (4) Roadshow/regional series; (5) SKO/revenue kickoff; (6) Investor/analyst day; (7) VIP/executive events; (8) Partner/channel events; (9) Incentive trips/recognition travel.
- **Score higher:** repeatability evidence + registration page + attendee-facing complexity.
- **Incentive trips** qualify because they create significant Cvent complexity (housing, travel logistics, VIP handling, approval workflows).

### S7 — Company Fit / Budget Maturity (4%)
- **Guardrail only.** Mid-market to enterprise, commercial events, dedicated event staff, meaningful event volume.
- **Do not inflate.** This should prevent tiny companies from scoring high — it should not add significant points for large companies with no visible pain.

### S8 — Cvent Certified Profile Signal (1%)
- **Qualifies:** Target contact or current event ops employee has any of: `Cvent Certified`, `#CventCertified`, `Cvent Event Management Certified`, `Cvent Attendee Hub Certified`, `Cvent System Administrator Certification`, or equivalent.
- **Important:** Do not use "I saw you are Cvent Certified" in cold outreach. Use as background sophistication signal only.
- **Bonus rule:** Cvent Certified person who recently left + active hiring for similar role → flag `capacity_stress_index: "high"` as a compound signal.

---

## 5. Score Caps and Tier Rules

| Scenario | Cap |
|---|---|
| Only proof is that the company uses Cvent | 45 max |
| No verified event, no hiring signal, no complexity | 65 max |
| No relevant buyer/persona found | 70 max |
| Event inferred but no specific future date | Temporal score capped at 40% of urgency signal weight |
| Low source confidence across key claims | Cannot be Hot |
| Job posting mentions events but no Cvent/registration/platform language | Capacity signal capped at Medium |
| Generic funding news only | No score lift unless tied to event expansion evidence |

**Tier thresholds (from PDF):**
- **Hot:** 75+ (requires ≥2 strong dynamic signals — never Hot on one weak signal alone)
- **Warm:** 50–74
- **Cold / Nurture:** <50

---

## 6. ResearchAgent Query Updates

**Primary tool:** Tavily. **Fallback:** Firecrawl for direct URL content extraction.

**Query Set 1 — Verified Upcoming Event Urgency**
- Target: event name, date, venue, registration URL. Reject snippets with no confirmed future date.

**Query Set 2 — Hiring and Capacity Gap**
- Target: role title, posting URL, Cvent/tech mentions, posting date.
- Sources (priority order for USA/Canada): company careers pages → Greenhouse → Lever → Workday → Ashby → SmartRecruiters → iCIMS → Jobvite → Canada Job Bank.

**Query Set 3 — Cvent Complexity Signals**
- Target: module names, integration targets, complexity descriptors, source URLs.

**Query Set 4 — MarTech and Reporting Pressure**
- Target: CRM, MAP, data warehouse names; reporting/attribution language; data hygiene references.

**Query Set 5 — Cvent Certified Profile (S8)**
- Target: profile URL, certification name.

**Example query templates:**
```
site:boards.greenhouse.io "{company_name}" ("event" OR "Cvent" OR "field marketing" OR "marketing operations")
"{company_name}" AND ("Cvent Certified" OR "#CventCertified" OR "Cvent Event Management Certified")
"{company_name}" AND ("Annual Conference" OR "Customer Summit" OR "Roadshow" OR "Sales Kickoff" OR "Incentive Trip") AND ("register" OR "agenda" OR "sponsor")
"{company_name}" ("Salesforce" OR "HubSpot" OR "Marketo") ("Cvent" OR "event data" OR "CRM sync" OR "event attribution")
```

---

## 7. EnrichmentAgent Updates

**Output schema additions** (store in existing `enrichment_data.data` JSONB):

```json
{
  "event_hiring_signals": {
    "has_open_cvent_role": true,
    "role_titles_found": ["Cvent Administrator", "Event Operations Manager"],
    "posting_urls": ["https://..."],
    "cvent_terms_in_jd": ["Attendee Hub", "Salesforce integration"],
    "posting_age_days": 12,
    "signal_strength": "very_high"
  },
  "cvent_complexity_signals": {
    "modules_detected": ["Attendee Hub", "OnArrival", "Appointments"],
    "integration_targets": ["Salesforce", "Marketo"],
    "complexity_level": "high",
    "source_urls": ["https://..."]
  },
  "cvent_certified_signal": {
    "found": true,
    "person_relevance": "target_contact_or_current_event_ops_employee",
    "certification_phrase": "Cvent Event Management Certified",
    "source_url_or_snippet": "...",
    "confidence": 0.84
  },
  "program_pattern_signals": [
    {"program_type": "Incentive Trip", "matched_title": "President Club", "repeatability": "annual", "confidence": 0.78}
  ],
  "capacity_stress_index": "high",
  "source_confidence_summary": "high",
  "recommended_template_driver": "capacity_gap_plus_event_window"
}
```

**Source confidence hierarchy** (highest to lowest): official event page / careers page → ATS platform (Greenhouse, Lever, Workday) → verified press release → industry calendar → search snippet → inferred/estimated.

---

## 8. ScoringAgent Instruction Block

Replace existing scoring instruction with:

```
Score using the v2 LaunchHouse market signals model:
- Verified upcoming event urgency: 24%
- Event/Cvent hiring and capacity gap: 20%
- Cvent complexity / advanced module usage: 16%
- MarTech, reporting, and data pressure: 14%
- Buyer/persona authority: 12%
- Event program + industry pattern: 9%
- Company fit / budget maturity: 4%
- Cvent Certified profile signal: 1%

Treat Cvent usage as a gate, not a high-weight signal. For each score provide:
1. Numeric sub-score (0.0–1.0)
2. Source-backed reasoning
3. Source confidence
4. Score caps applied (if any)
5. recommended_template_driver

Never score a lead Hot if key evidence is low confidence.
Hot tier requires at least two strong dynamic signals.
```

---

## 9. PersonalizationAgent Updates

Campaign routing by primary signal driver:

| Primary driver | Template | Messaging angle | Avoid |
|---|---|---|---|
| Verified event 31–120 days out | **T8** Build Scoping | Scope is being locked; fixed-fee Cvent implementation before the rush | Generic staff augmentation language |
| Verified event 0–30 days out | **T7** Rush | Final-stretch support for unresolved registration, Attendee Hub, integrations | Overpromising large rebuilds without scoping |
| Event/Cvent hiring gap | **T6** or capacity-led **T1** | Bridge Cvent/event ops capacity while internal team scales | Quoting job titles directly in opening |
| Cvent complexity | **T1/T6** or **T8** if event exists | Registration architecture, multi-track setup, onsite/mobile, Attendee Hub, integrations | Mentioning modules unless evidence is strong |
| MarTech/reporting pressure | **T6** or **T9** if news-triggered | Cleaner Cvent setup improves downstream reporting and CRM/event data flow | Vague ROI claims |
| Program pattern only | **T6** Fit-Based | Overflow capacity for repeatable event programs | Creating false urgency |
| Cvent Certified only | No dedicated template | Use as background signal — not the hook | "I saw you are Cvent Certified" in cold outreach |

**Personalization hook fields** to write into `message.personalization_hooks`:
- `recommended_template_driver` — primary routing decision
- `dominant_signal` — the highest-scoring signal type
- `opening_hook` — one sentence referencing the dominant signal
- `top_evidence_snippets` — 2–3 evidence strings passed to campaign routing
- `capacity_stress_index` — "high" / "medium" / "low"

---

## 10. Minimal Implementation Plan (Phased)

| Phase | Change | Code impact |
|---|---|---|
| **1. Scoring weights** | Replace old 10-signal prompt with v2 8-signal model | ScoringAgent prompt/config only |
| **2. Research query expansion** | Add USA/Canada job sources, ATS title library, program titles, Cvent Certified, MarTech queries | ResearchAgent query list/prompt. No new data provider. |
| **3. Evidence extraction** | Ask EnrichmentAgent to extract structured signal blocks | Prefer optional JSON keys in `enrichment_data.data`. Optional Pydantic fields only if strict validation forces it. |
| **4. Score caps** | Add cap logic to ScoringAgent | ScoringAgent prompt/config only |
| **5. PersonalizationAgent routing** | Update routing conditions and hook language | Routing decision logic + `personalization_hooks` fields |

---

## 11. QA Test Scenarios

| Scenario | Expected score / tier | Expected routing |
|---|---|---|
| QA-01: Red-hot compound — verified event 58 days out + open Event Ops Manager (Cvent, Attendee Hub, Salesforce) + Director of Events contact | **85–95 / Hot** | T8 with capacity-aware personalization |
| QA-02: Hot event complexity — annual summit 80 days out + multi-track sessions + Head of Field Marketing | **78–88 / Hot** | T8 build scoping angle |
| QA-03: Capacity-led warm — open Cvent Administrator + Marketing Ops role; no verified event | **65–75 / Warm** (Hot only if very high confidence) | T6 or capacity-led T1; re-enrich monthly |
| QA-04: Program pattern high — annual incentive trip / Presidents Club with registration/travel details; no Cvent evidence | **58–72 / Warm** | Fit-based sequence; no false Cvent-specific claim |
| QA-05: Certification-only — Cvent Certified profile, no event timing/hiring/complexity/reporting | **Do not exceed Warm** | No certification-led email hook |
| QA-06: Nurture — known Cvent user in high-fit industry, no event timing/hiring/complexity/pressure | **35–50 / Cold or Nurture** | Hold or low-touch |

---

## 12. Acceptance Criteria

The tuning is complete when:
1. All 6 QA scenarios produce the expected tier and routing.
2. No lead scores Hot on a single weak signal.
3. Cvent usage alone never produces a Hot lead.
4. Every Hot-score lead includes at least one high-confidence source URL for its primary signal driver.
5. Event dates and job titles are not used in email copy unless source confidence is high.
6. `recommended_template_driver` is present in `message.personalization_hooks` for all scored leads.

---

## 13. What Is Optional / Future (Do Not Implement in This Pass)

- New database tables or schema migrations
- New external data providers or new queues
- Redesigning the 4-agent pipeline
- Europe job sources (ESCO, EURES) — intentionally excluded
- Template rebuilding (T1–T17 playbook is preserved as-is)

---

## 14. Key Reference Libraries (from Signal_Library_Appendix.docx)

### Job Sources — USA/Canada Priority Order
Greenhouse → Lever → Workday → Ashby → SmartRecruiters → iCIMS → Jobvite → Canada Job Bank → company careers pages (always highest-trust).

### Cvent Certified Keywords
`Cvent Certified`, `#CventCertified`, `Cvent Certification`, `Cvent Event Management Certified`, `Cvent Attendee Hub Certified`, `Cvent System Administrator Certification`, `Cvent Account Administrator Certification`.

### Event Program Keyword Block (flat, for query expansion)
Annual Conference, Annual Meeting, Annual Convention, Global Conference, National Conference, User Conference, Customer Conference, Client Conference, Partner Conference, Association Conference, Annual Summit, Global Summit, Customer Summit, User Summit, Partner Summit, Leadership Summit, Executive Summit, Industry Summit, Business Summit, Community Summit, Forum, Symposium, Congress, Convention, Trade Show, Expo, Exhibition, Roadshow, Executive Roadshow, Product Roadshow, Investor Roadshow, City Tour, Multi-City Event, Investor Day, Analyst Day, Capital Markets Day, Sales Kickoff, SKO, Revenue Kickoff, GTM Kickoff, National Sales Meeting, Leadership Offsite, Executive Offsite, Training, Workshop, Seminar, Bootcamp, Masterclass, Webinar, Virtual Event, Hybrid Event, Online Summit, Virtual Conference, Partner Day, Incentive Trip, Presidents Club, President's Club, Recognition Trip, Reward Trip.

### Source Confidence Rules
- **High confidence:** official event page, company careers page, live ATS posting
- **Medium confidence:** press release, industry calendar with date
- **Low confidence:** search snippet, estimated/inferred dates or titles
- Hard rule: Do not hallucinate job postings, event dates, or certifications. Every Hot lead must have a high-confidence source URL for its primary signal.

---

*Summary created from: LaunchHouse_Market_Signals_Lead_Scoring_Report_v2_CTO_Handoff.pdf (source of truth) · Market_Signal_Scoring_Tune_CTO_Implementation_Handoff.docx · Signal_Library_Appendix.docx · CTO_Handoff_Checklist.docx*
