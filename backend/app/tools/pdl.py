"""People Data Labs (PDL) contact enrichment."""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

PDL_ENRICH_URL = "https://api.peopledatalabs.com/v5/person/enrich"

_SENIORITY_MAP = {
    "c_suite": "c-suite",
    "owner": "owner",
    "partner": "partner",
    "vp": "vp",
    "director": "director",
    "manager": "manager",
    "senior": "senior",
    "entry": "entry",
    "training": "training",
}


def _normalize_pdl_person(data: dict[str, Any], fallback_email: str) -> dict[str, Any]:
    person = data.get("data") or {}

    levels: list[str] = person.get("job_title_levels") or []
    seniority = _SENIORITY_MAP.get(levels[0], levels[0]) if levels else None

    dept = person.get("job_title_sub_role") or person.get("job_title_role") or None
    if isinstance(dept, list):
        dept = dept[0] if dept else None

    phone = None
    phones = person.get("phone_numbers")
    if isinstance(phones, list) and phones:
        phone = str(phones[0])
    else:
        mobile = person.get("mobile_phone")
        if isinstance(mobile, str) and mobile:
            phone = mobile

    linkedin = person.get("linkedin_url") or None
    if linkedin and not linkedin.startswith("http"):
        linkedin = f"https://{linkedin}"

    emp_count = person.get("job_company_employee_count") or None

    co_linkedin = person.get("job_company_linkedin_url") or None
    if co_linkedin and not co_linkedin.startswith("http"):
        co_linkedin = f"https://{co_linkedin}"

    return {
        "email": person.get("work_email") or fallback_email,
        "first_name": person.get("first_name"),
        "last_name": person.get("last_name"),
        "name": person.get("full_name"),
        "title": person.get("job_title"),
        "seniority": seniority,
        "department": dept,
        "linkedin_url": linkedin,
        "phone": phone,
        "organization": {
            "name": person.get("job_company_name"),
            "domain": person.get("job_company_website"),
            "website_url": person.get("job_company_website"),
            "linkedin_url": co_linkedin,
            "employee_count": emp_count,
            "industry": person.get("job_company_industry") or person.get("industry"),
            "keywords": [],
            "technologies": [],
            "short_description": person.get("summary"),
        },
        "raw": data,
    }


async def enrich_person_by_email(email: str, api_key: str) -> dict[str, Any]:
    """Resolve a contact and company profile from an email via PDL."""
    if not api_key or not email:
        return {}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                PDL_ENRICH_URL,
                headers={"X-Api-Key": api_key},
                params={"email": email, "min_likelihood": 2},
            )
            if response.status_code == 404:
                return {}
            response.raise_for_status()
            data = response.json()
            if data.get("status") != 200 or not data.get("data"):
                return {}
            return _normalize_pdl_person(data, email)
    except Exception as exc:
        logger.warning("PDL enrichment failed for %s: %s", email, exc)
        return {}
