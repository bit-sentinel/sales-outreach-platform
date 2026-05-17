"""Helpers for building personalization context payloads."""


def build_personalization_payload(
    insights_rows: list,
    research_rows: list,
    enrich_rows: list,
) -> tuple[dict | None, dict | None]:
    """Keep structured research and enrichment data intact for email generation."""
    research_payload: dict[str, object] = {}
    enrichment_payload: dict[str, object] = {}

    if insights_rows:
        research_payload["insights"] = [
            {
                "type": row.insight_type,
                "content": row.content,
                "confidence": row.confidence,
                "source_data": row.source_data,
            }
            for row in insights_rows
            if row.content
        ]
    if research_rows:
        research_payload["research_records"] = [
            {
                "source": row.source,
                "title": row.title,
                "url": row.url,
                "content": row.content,
                "metadata": row.metadata_,
            }
            for row in research_rows
        ]
    if enrich_rows:
        enrichment_payload = {
            row.data_type: row.data
            for row in enrich_rows
        }

    return (research_payload or None, enrichment_payload or None)