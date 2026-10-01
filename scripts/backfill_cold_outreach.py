"""
One-off script: re-trigger Stage 6 (outreach) for cold leads that have no cached outreach signal.
Run inside the API container: python scripts/backfill_cold_outreach.py
"""
import asyncio
import hashlib
import sys

LEAD_IDS = [
    "01d7baa1-972e-4202-bd02-d26779c89be2", "5cf0fe65-888b-4e9c-b91f-bb1fdced228c",
    "c49af7cb-3fb4-4787-b8e9-d17843b2c89f", "6f0bdd9b-cbe0-4103-921f-d2401360192f",
    "053299ff-76ce-4d45-8f3e-826b4a2b87ff", "327e8f56-325e-4d70-808f-8e84b5c80c92",
    "d8706924-aac7-408f-9ba3-c9887fb8cf2a", "abb3da7b-2993-4944-b5a9-115df2bb6799",
    "8606ed70-1a63-48b1-851f-5110c3148b94", "749fbcf9-f942-4153-8873-19ec2fe778eb",
    "d4ef420e-829a-45c5-a22a-6671eb99511c", "57784bc9-a956-4360-b901-2e666b6c4a3a",
    "555bef50-2a52-41cf-b657-16317c58da2f", "b9f5335e-49b6-43e0-a03f-de7758ba5b03",
    "1bfb90af-cc03-4bbe-a898-df33d7528c63", "9e856583-2441-47ea-8ff2-b79d1756a9d7",
    "6005b755-1b14-44d4-a1e4-92848da34407", "b875ca2b-af29-4dce-9471-69dd7358360f",
    "b562d376-28a5-42cd-b3e6-14f64058bbf7", "c1cbc28e-9869-4ebd-851d-fb623f9d7c6b",
    "54fd9dc5-9475-40da-a5f0-5f414f564fac", "1a5b5336-2beb-4554-9b73-7b805ece07aa",
    "fc177049-0b44-4643-9c09-b616e954a113", "3644a613-1bb4-460f-b3b6-889de9d20c38",
    "daa3f881-026e-413b-ae95-ef775208b57d", "1704f4a8-028e-489b-80e5-75738a6269de",
    "944d54f4-f7bc-4cc8-80f1-9a67ba80fb09", "78d541ff-dae8-4b51-a0ef-4823eddfa9f3",
    "9a442cde-80a2-4245-84c2-2f9ff49c590c", "0cb0ede5-33c0-4c37-92f5-b2715a1015e6",
    "f436d765-8c6b-4446-9354-dec730832cf7", "ad267e79-d683-4cf4-8f49-49325759b22f",
    "90a15be6-fc62-4323-a116-133a165c6e7d", "3d6b776a-a9d0-4878-b9cb-09a4bad9b030",
    "3237bdc6-2ce7-4e0f-b9b1-606c4036f0e6", "4aa117b3-d1fd-4778-94f8-5d2a59ce5889",
    "b79fe148-e6e4-4d6f-bef2-82960148ee80", "b58dab44-c2b0-44a5-9fe6-9aaed1de86ef",
    "6b46612c-539c-427d-98ca-dda683539001", "637a12d4-ac6d-4458-a8ca-699d0988299a",
    "6116928b-a5ac-46f0-9891-94eb97fd82d3", "ef072d76-84c5-4c74-8ac4-73973bac58f5",
    "13b237b1-7a28-40c6-97b4-f59a036e7a71", "8c08bcac-9f2f-4a23-9dfd-44acb1f22897",
    "08b1fe63-a3f2-4e6e-9c76-d32a4d4eb301", "bdc276e3-3e87-42e6-949f-3b3a05b24b03",
    "d6c2d869-b855-4928-9741-54e88db4069e", "22128dec-8b78-48b6-b645-d3ab6b357724",
    "7cbf03b5-da26-4a60-9e34-1ac0c6724074", "e6cd5191-3afe-40b6-b27f-1a98e71b67ee",
    "a6550723-1983-4ed9-ad76-ad34318cfbb0", "d426151c-0b74-435a-9a89-44f66048733a",
    "2ceebd65-84d9-423f-a789-b5e217b6fd39",
]


def _hashed(*parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]
    return f"v3res:{digest}"


async def main():
    from uuid import UUID
    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.config import get_settings
    from app.models.lead import Lead, Contact

    settings = get_settings()
    engine = create_async_engine(str(settings.database_url), pool_size=5)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    to_backfill = []

    async with factory() as session:
        for lead_id_str in LEAD_IDS:
            lead = (await session.execute(
                select(Lead).where(Lead.id == UUID(lead_id_str))
            )).scalar_one_or_none()
            if not lead:
                print(f"  SKIP {lead_id_str} — lead not found")
                continue

            contact = (await session.execute(
                select(Contact).where(Contact.id == lead.contact_id)
            )).scalar_one_or_none()
            contact_id = (contact.email if contact else "") or ""

            cache_key = _hashed("outreach", "contact", contact_id.lower().strip())
            row = (await session.execute(
                text("SELECT 1 FROM signal_cache WHERE cache_key = :k AND expires_at > NOW()"),
                {"k": cache_key},
            )).first()

            if row:
                print(f"  SKIP {lead_id_str} — outreach already cached")
            else:
                print(f"  QUEUE {lead_id_str} — missing outreach")
                to_backfill.append(lead_id_str)

    await engine.dispose()

    if not to_backfill:
        print("\nAll cold leads already have outreach cached. Nothing to do.")
        return

    print(f"\nTriggering pipeline for {len(to_backfill)} leads...")
    from app.tasks.v3.stage_tasks import orchestrate_event_intelligence
    for lead_id_str in to_backfill:
        orchestrate_event_intelligence(lead_id_str)
        print(f"  dispatched {lead_id_str}")

    print(f"\nDone. {len(to_backfill)} leads queued for Stage 1→6.")


if __name__ == "__main__":
    asyncio.run(main())
