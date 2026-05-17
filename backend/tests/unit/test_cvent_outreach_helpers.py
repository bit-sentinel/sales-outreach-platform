from app.tasks.personalization_payloads import build_personalization_payload
from app.tools.serpapi import build_cvent_query


class _Insight:
    def __init__(self, insight_type, content, confidence=0.8, source_data=None):
        self.insight_type = insight_type
        self.content = content
        self.confidence = confidence
        self.source_data = source_data or {}


class _Research:
    def __init__(self, source, title, url=None, content=None, metadata_=None):
        self.source = source
        self.title = title
        self.url = url
        self.content = content
        self.metadata_ = metadata_ or {}


class _Enrichment:
    def __init__(self, data_type, data):
        self.data_type = data_type
        self.data = data


def test_build_cvent_query_uses_company_and_domain():
    query = build_cvent_query("Acme Events", "acme.com")

    assert query == 'site:cvent.com ("Acme Events" OR "acme.com")'


def test_personalization_payload_keeps_structured_records():
    insights = [_Insight("research_summary", "Upcoming summit in September")]
    research_rows = [
        _Research(
            "cvent_event_page",
            "Acme Partner Summit",
            url="https://cvent.com/acme-summit",
            content="Registration site is live",
            metadata_={"days_out": 60},
        )
    ]
    enrich_rows = [
        _Enrichment("identity_profile", {"title": "Director, Events"}),
        _Enrichment("company_contact", {"personalization": {"subject_angles": ["Before Acme Partner Summit"]}}),
    ]

    research_payload, enrichment_payload = build_personalization_payload(
        insights,
        research_rows,
        enrich_rows,
    )

    assert research_payload["insights"][0]["type"] == "research_summary"
    assert research_payload["research_records"][0]["metadata"]["days_out"] == 60
    assert enrichment_payload["identity_profile"]["title"] == "Director, Events"
    assert enrichment_payload["company_contact"]["personalization"]["subject_angles"] == ["Before Acme Partner Summit"]