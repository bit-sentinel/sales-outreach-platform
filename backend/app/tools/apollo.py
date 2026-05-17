"""Apollo.io contact enrichment helpers."""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

APOLLO_PEOPLE_MATCH_URL = "https://api.apollo.io/api/v1/people/match"


def _first_phone(phone_numbers: list[dict[str, Any]] | None) -> str | None:
    if not phone_numbers:
        return None
    for phone in phone_numbers:
        value = phone.get("sanitized_number") or phone.get("raw_number") or phone.get("number")
        if value:
            return str(value)
    return None


def _normalize_apollo_person(data: dict[str, Any], fallback_email: str) -> dict[str, Any]:
    person = data.get("person") or data.get("contact") or data.get("data") or {}
    organization = person.get("organization") or person.get("account") or {}
    technology_names = []
    for tech in organization.get("technologies") or []:
        if isinstance(tech, dict):
            name = tech.get("name") or tech.get("technology")
        else:
            name = tech
        if name:
            technology_names.append(str(name))

    return {
        "email": person.get("email") or fallback_email,
        "first_name": person.get("first_name"),
        "last_name": person.get("last_name"),
        "name": " ".join(
            part for part in [person.get("first_name"), person.get("last_name")] if part
        ).strip() or None,
        "title": person.get("title"),
        "seniority": person.get("seniority"),
        "department": person.get("department") or person.get("function") or person.get("functions"),
        "linkedin_url": person.get("linkedin_url"),
        "phone": _first_phone(person.get("phone_numbers")),
        "organization": {
            "name": organization.get("name"),
            "domain": organization.get("primary_domain") or organization.get("website_url"),
            "website_url": organization.get("website_url"),
            "linkedin_url": organization.get("linkedin_url"),
            "employee_count": organization.get("estimated_num_employees"),
            "industry": organization.get("industry") or organization.get("industry_tag") or organization.get("keywords"),
            "keywords": organization.get("keywords") or [],
            "technologies": technology_names,
            "short_description": organization.get("short_description") or organization.get("description"),
        },
        "raw": data,
    }


async def enrich_person_by_email(email: str, api_key: str) -> dict[str, Any]:
    """Resolve a contact and company profile from an email via Apollo."""
    if not api_key or not email:
        return {}

    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": api_key,
    }
    payload = {
        "email": email,
        "reveal_personal_emails": False,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(APOLLO_PEOPLE_MATCH_URL, headers=headers, json=payload)
            response.raise_for_status()
            return _normalize_apollo_person(response.json(), email)
    except Exception as exc:
        logger.warning("Apollo enrichment failed for %s: %s", email, exc)
        return {}