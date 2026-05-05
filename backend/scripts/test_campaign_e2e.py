#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════
  E2E Campaign Workflow Test  –  REST APIs + Real IMAP Reply Detection
  3 leads × 3-step sequence with automatic reply capture via IMAP
═══════════════════════════════════════════════════════════════════

What this does:
  1. Calls the real backend REST APIs (campaign visible in UI immediately)
  2. Uses Claude AI to generate personalised emails per lead/step
  3. Sends via SendGrid from cto@launchhouse.events
  4. Polls the sender's Gmail inbox via IMAP to auto-detect real replies
  5. Ingests each reply via POST /api/v1/replies/ingest → visible in Replies tab
  6. Enforces no_reply conditional logic: once a lead replies, steps skip

Scenarios tested:
  Lead 1 (hitdasamit@gmail.com)   – expected to reply after step 1
  Lead 2 (amit.softpro@gmail.com) – expected to reply after step 2
  Lead 3 (amitd.iitb@gmail.com)   – expected to reply after step 3

Pre-requisites:
  • GMAIL_APP_PASSWORD in .env  (Google Workspace app password)
  • Generate at: https://myaccount.google.com/apppasswords

Run inside API container:
  docker compose exec -it api python3 /app/scripts/test_campaign_e2e.py

Run locally (venv activated, from repo root):
  python3 backend/scripts/test_campaign_e2e.py
"""

import email as email_lib
import imaplib
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from email.header import decode_header

import requests

# ── path & env bootstrap ─────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_env_path = os.path.join(_repo_root, ".env")
if os.path.exists(_env_path):
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_path, override=False)
    except ImportError:
        with open(_env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

# ── Config ────────────────────────────────────────────────────────────────────
API_BASE    = os.environ.get("API_BASE_URL", "http://localhost:8000/api/v1")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL",  "cto@launchhouse.events")
ADMIN_PASS  = os.environ.get("ADMIN_PASS",   "Admin123!")

IMAP_HOST = "imap.gmail.com"
IMAP_USER = os.environ.get("GMAIL_IMAP_USER",    "cto@launchhouse.events")
IMAP_PASS = os.environ.get("GMAIL_APP_PASSWORD", "")

LEAD_EMAILS = [
    "hitdasamit@gmail.com",
    "amit.softpro@gmail.com",
    "amitd.iitb@gmail.com",
]

REPLY_POLL_INTERVAL = 15   # seconds between IMAP checks
REPLY_POLL_TIMEOUT  = 600  # 10-minute max wait per step

# ── ANSI colours ──────────────────────────────────────────────────────────────
G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"
B = "\033[94m"; C = "\033[96m"; DIM = "\033[2m"; BOLD = "\033[1m"; RST = "\033[0m"

def hdr(t):  print(f"\n{BOLD}{C}{'═'*62}{RST}\n{BOLD}{C}  {t}{RST}\n{BOLD}{C}{'═'*62}{RST}")
def ok(m):   print(f"  {G}✔{RST}  {m}")
def info(m): print(f"  {B}→{RST}  {m}")
def warn(m): print(f"  {Y}⚠{RST}  {m}")
def skip(m): print(f"  {Y}⊘{RST}  {DIM}{m}{RST}")
def err(m):  print(f"  {R}✖{RST}  {m}")


# ═════════════════════════════════════════════════════════════════════════════
#  REST API CLIENT
# ═════════════════════════════════════════════════════════════════════════════

class APIClient:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.token: str | None = None
        self._s = requests.Session()

    def _h(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def login(self, email: str, password: str) -> bool:
        r = self._s.post(f"{self.base}/auth/login",
                         json={"email": email, "password": password},
                         headers={"Content-Type": "application/json"})
        if r.status_code == 200:
            self.token = r.json().get("data", {}).get("access_token")
            self._email = email
            self._password = password
            return bool(self.token)
        err(f"Login {r.status_code}: {r.text[:200]}")
        return False

    def _reauth(self) -> None:
        """Re-login using stored credentials (called automatically on 401)."""
        ok("JWT expired – refreshing token…")
        self.login(self._email, self._password)

    def get(self, path: str, params: dict | None = None) -> dict:
        r = self._s.get(f"{self.base}{path}", headers=self._h(), params=params)
        if r.status_code == 401:
            self._reauth()
            r = self._s.get(f"{self.base}{path}", headers=self._h(), params=params)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, body: dict | None = None) -> dict:
        r = self._s.post(f"{self.base}{path}", headers=self._h(), json=body or {})
        if r.status_code == 401:
            self._reauth()
            r = self._s.post(f"{self.base}{path}", headers=self._h(), json=body or {})
        r.raise_for_status()
        return r.json()

    def patch(self, path: str, body: dict | None = None) -> dict:
        r = self._s.patch(f"{self.base}{path}", headers=self._h(), json=body or {})
        if r.status_code == 401:
            self._reauth()
            r = self._s.patch(f"{self.base}{path}", headers=self._h(), json=body or {})
        r.raise_for_status()
        return r.json()


# ═════════════════════════════════════════════════════════════════════════════
#  GMAIL IMAP REPLY POLLER
# ═════════════════════════════════════════════════════════════════════════════

def _decode_header_val(value: str) -> str:
    parts = decode_header(value or "")
    out = []
    for part, enc in parts:
        if isinstance(part, bytes):
            out.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(part)
    return "".join(out)


def _plain_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and \
               "attachment" not in str(part.get("Content-Disposition", "")):
                charset = part.get_content_charset() or "utf-8"
                return part.get_payload(decode=True).decode(charset, errors="replace")
    else:
        charset = msg.get_content_charset() or "utf-8"
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode(charset, errors="replace")
    return ""


def poll_for_reply(from_email: str, subject_contains: str,
                   since_utc: datetime) -> dict | None:
    """
    Poll Gmail IMAP until a reply arrives.  Returns
    {"subject": ..., "body_text": ..., "from": ...} or None on timeout.
    """
    if not IMAP_PASS:
        warn("GMAIL_APP_PASSWORD not set – cannot auto-detect replies.")
        warn("Set GMAIL_APP_PASSWORD=<app-password> in .env and re-run.")
        return None

    deadline = time.time() + REPLY_POLL_TIMEOUT
    since_str = since_utc.strftime("%d-%b-%Y")

    info(f"  Polling inbox for reply from {from_email}")
    info(f"  Subject must contain: \"{subject_contains[:50]}\"")
    info(f"  Checking every {REPLY_POLL_INTERVAL}s (max {REPLY_POLL_TIMEOUT//60}min)…")

    while time.time() < deadline:
        try:
            mail = imaplib.IMAP4_SSL(IMAP_HOST)
            mail.login(IMAP_USER, IMAP_PASS)
            mail.select("INBOX")

            status, data = mail.search(
                None, f'(FROM "{from_email.lower()}" SINCE {since_str})'
            )
            if status == "OK":
                for mid in reversed(data[0].split()):
                    st2, raw = mail.fetch(mid, "(RFC822)")
                    if st2 != "OK":
                        continue
                    raw_bytes = raw[0][1] if isinstance(raw[0], tuple) else b""
                    parsed = email_lib.message_from_bytes(raw_bytes)

                    subj = _decode_header_val(parsed.get("Subject", ""))
                    frm  = _decode_header_val(parsed.get("From", ""))

                    if "re:" not in subj.lower():
                        continue
                    if subject_contains.lower() not in subj.lower():
                        continue

                    body = _plain_body(parsed)
                    mail.logout()
                    ok(f"  Reply detected: \"{subj}\"  from {frm}")
                    return {"subject": subj, "body_text": body[:2000], "from": frm}

            mail.logout()
        except Exception as exc:
            warn(f"  IMAP error (will retry): {exc}")

        remaining = int(deadline - time.time())
        print(f"  {DIM}  No reply yet – {remaining}s remaining…{RST}", end="\r", flush=True)
        time.sleep(REPLY_POLL_INTERVAL)

    print()
    warn(f"Timed out waiting for reply from {from_email}")
    return None


# ═════════════════════════════════════════════════════════════════════════════
#  HELPER FUNCTIONS
# ═════════════════════════════════════════════════════════════════════════════

def create_lead(api: APIClient, first: str, last: str, email: str,
                company_name: str, industry: str, title: str, dept: str) -> dict:
    """POST /companies → POST /companies/{id}/contacts → POST /leads"""
    company = api.post("/companies", {
        "name": company_name, "industry": industry, "tags": ["e2e-test"],
    })["data"]

    contact = api.post(f"/companies/{company['id']}/contacts", {
        "first_name": first, "last_name": last, "email": email,
        "title": title, "department": dept, "tags": ["e2e-test"],
    })["data"]

    lead = api.post("/leads", {
        "company_id": company["id"],
        "contact_id": contact["id"],
        "source": "e2e-test",
        "tags": ["e2e-test"],
    })["data"]

    ok(f"Lead created: {first} {last} <{email}>  lead_id={lead['id']}")
    return {"lead": lead, "contact": contact, "company": company,
            "name": f"{first} {last}", "email": email, "title": title}


def wait_for_drafts(api: APIClient, campaign_id: str, sequence_step: int,
                    expected: int, timeout: int = 180) -> list[dict]:
    """Poll until `expected` draft messages appear for the given 0-based sequence_step."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        msgs = api.get(f"/campaigns/{campaign_id}/messages", {"status": "draft"})["data"]
        step_msgs = [m for m in msgs if m.get("sequence_step") == sequence_step]
        if len(step_msgs) >= expected:
            print()
            return step_msgs
        remaining = int(deadline - time.time())
        print(
            f"  {DIM}Waiting for step {sequence_step+1} drafts:"
            f" {len(step_msgs)}/{expected}  ({remaining}s){RST}",
            end="\r", flush=True,
        )
        time.sleep(4)
    print()
    msgs = api.get(f"/campaigns/{campaign_id}/messages", {"status": "draft"})["data"]
    return [m for m in msgs if m.get("sequence_step") == sequence_step]


def send_draft(api: APIClient, campaign_id: str, msg: dict) -> None:
    """POST /campaigns/{id}/messages/{msg_id}/send"""
    api.post(f"/campaigns/{campaign_id}/messages/{msg['id']}/send")
    ok(f"{msg.get('lead_name','?')}  step {(msg.get('sequence_step') or 0)+1}"
       f"  → queued  subject: \"{msg.get('subject','')}\"")


def wait_for_sent(api: APIClient, campaign_id: str, msg_id: str,
                  label: str, timeout: int = 90) -> dict | None:
    """Poll until the specific message reaches 'sent' or 'failed'."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        all_msgs = api.get(f"/campaigns/{campaign_id}/messages")["data"]
        match = next((m for m in all_msgs if m["id"] == msg_id), None)
        if match and match["status"] in ("sent", "delivered", "failed"):
            if match["status"] == "failed":
                err(f"{label} send FAILED: {match.get('error_message','?')}")
            else:
                ok(f"{label} → SENT  subject: \"{match.get('subject','')}\"")
            return match
        time.sleep(5)
    warn(f"{label}: message {msg_id} did not reach 'sent' within {timeout}s")
    return None


def ingest_reply(api: APIClient, message_id: str, lead_id: str,
                 subject: str, body_text: str, lead_name: str) -> dict:
    """POST /replies/ingest to record the reply in the platform."""
    reply = api.post("/replies/ingest", {
        "message_id": message_id,
        "lead_id": lead_id,
        "subject": subject,
        "body_text": body_text,
        "intent": "interested",
        "sentiment": "positive",
        "priority": "high",
    })["data"]
    ok(f"{G}{BOLD}{lead_name} reply ingested → visible in Replies tab{RST}"
       f"  reply_id={reply['id']}")
    return reply


def advance(api: APIClient, campaign_id: str) -> int:
    """POST /campaigns/{id}/advance – dispatch process_campaign_lead for active leads."""
    resp = api.post(f"/campaigns/{campaign_id}/advance")
    n = resp["data"]["dispatched"]
    ok(f"Advance dispatched for {n} active lead(s)")
    return n


def print_summary(api: APIClient, campaign_id: str, lead_records: list) -> None:
    hdr("FINAL STATE SUMMARY")

    camp = api.get(f"/campaigns/{campaign_id}")["data"]
    print(f"\n  Campaign: {BOLD}{camp['name']}{RST}")
    sc = G if camp["status"] == "active" else Y
    print(f"  Status : {sc}{camp['status']}{RST}")
    print(f"  Sent={camp['sent_count']}  Leads={camp['total_leads']}"
          f"  Replies={camp['reply_count']}")

    all_msgs  = api.get(f"/campaigns/{campaign_id}/messages")["data"]
    all_reps  = api.get("/replies")["data"]["items"]

    print(f"\n  {'Lead':<22} {'Sent':<6} {'Replied'}")
    print(f"  {'─'*22} {'─'*6} {'─'*10}")
    for lr in lead_records:
        lid = lr["lead"]["id"]
        sent = [m for m in all_msgs if m["lead_id"] == lid
                and m["status"] in ("sent", "delivered")]
        replied = any(r["lead_id"] == lid for r in all_reps)
        rep_str = f"{G}Yes{RST}" if replied else f"{R}No{RST}"
        print(f"  {lr['name']:<22} {len(sent):<6} {rep_str}")

    print(f"\n  {BOLD}Per-lead message breakdown:{RST}")
    for lr in lead_records:
        lid = lr["lead"]["id"]
        msgs = sorted([m for m in all_msgs if m["lead_id"] == lid],
                      key=lambda m: m.get("sequence_step") or 0)
        print(f"\n    {BOLD}{lr['name']}{RST}  ({lr['email']})")
        if not msgs:
            print("      (no messages)")
        for m in msgs:
            step = (m.get("sequence_step") or 0) + 1
            sc = G if m["status"] in ("sent","delivered") else Y if m["status"]=="draft" else DIM
            print(f"      Step {step}  {sc}{m['status']:<8}{RST}  \"{m.get('subject','')}\"")

    replies_page = api.get("/replies")["data"]
    print(f"\n  {BOLD}Replies tab ({replies_page['total']} total):{RST}")
    for r in replies_page["items"]:
        print(f"    intent={r['intent']}  \"{r.get('subject','')}\"")


# ═════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════════════════════════════════════════

def main():
    hdr("E2E CAMPAIGN TEST  –  REST APIs + IMAP REPLY DETECTION")
    print(f"  API base:  {G}{API_BASE}{RST}")
    print(f"  Sender:    {G}{IMAP_USER}{RST}  (via SendGrid)")
    print(f"  IMAP host: {G}{IMAP_HOST}{RST}  user={IMAP_USER}")
    if not IMAP_PASS:
        print(f"\n  {R}{BOLD}WARNING: GMAIL_APP_PASSWORD not set.{RST}")
        print(f"  {Y}Reply auto-detection will be skipped.{RST}")
        print(f"  {Y}Add GMAIL_APP_PASSWORD=<app-pass> to .env and re-run for full test.{RST}")
    print(f"\n  {Y}This will send REAL emails.  Press Enter or Ctrl+C to abort.{RST}")
    input("  > ")

    # ── Auth ──────────────────────────────────────────────────────────────────
    api = APIClient(API_BASE)
    if not api.login(ADMIN_EMAIL, ADMIN_PASS):
        err(f"Auth failed for {ADMIN_EMAIL} – check ADMIN_EMAIL / ADMIN_PASS")
        sys.exit(1)
    ok(f"Authenticated as {ADMIN_EMAIL}")

    # ── Phase 1: Create 3 test leads ─────────────────────────────────────────
    hdr("PHASE 1 – Create 3 Test Leads via API")
    personas = [
        ("Alice",  "Johnson",  LEAD_EMAILS[0], "[TEST] Maple Leaf Association",
         "Non-profit / Association",  "Director of Conferences",    "Events"),
        ("Bob",    "Martinez", LEAD_EMAILS[1], "[TEST] SalesForce Events Corp",
         "Corporate Events",          "Corporate Events Manager",   "Marketing"),
        ("Carol",  "Chen",     LEAD_EMAILS[2], "[TEST] National Chapter Network",
         "Association",               "VP of Operations",           "Operations"),
    ]
    lead_records = [create_lead(api, *p) for p in personas]

    # ── Phase 2: Create campaign ──────────────────────────────────────────────
    hdr("PHASE 2 – Create 3-Step Campaign via API")
    campaign = api.post("/campaigns", {
        "name": "[TEST] E2E 3-Step Outreach",
        "description": "Automated E2E test – safe to delete",
        "campaign_type": "outbound",
        "vertical": "Events Technology",
        "sequence": [
            {"step": 1, "channel": "email", "delay_days": 0,
             "ai_generate": True, "condition": None},
            {"step": 2, "channel": "email", "delay_days": 3,
             "ai_generate": True, "condition": "no_reply"},
            {"step": 3, "channel": "email", "delay_days": 5,
             "ai_generate": True, "condition": "no_reply"},
        ],
        "schedule": {
            "timezone": "UTC",
            "send_days": ["monday","tuesday","wednesday","thursday","friday"],
            "send_start_hour": 9, "send_end_hour": 17,
        },
    })["data"]
    cid = campaign["id"]
    ok(f"Campaign: '{campaign['name']}'  id={cid}")
    ok(f"→ visible at http://localhost:3000/campaigns")

    # ── Phase 3: Enroll leads & launch ───────────────────────────────────────
    hdr("PHASE 3 – Enroll Leads & Launch Campaign")
    enroll = api.post(f"/campaigns/{cid}/leads",
                      {"lead_ids": [lr["lead"]["id"] for lr in lead_records]})["data"]
    ok(f"Enrolled {enroll['added']} leads")

    api.post(f"/campaigns/{cid}/launch")
    ok("Campaign launched – Celery generating step-1 AI drafts now…")

    # ── Phase 4: Wait for step 1 drafts & send ───────────────────────────────
    hdr("PHASE 4 – Wait for Step 1 Drafts & Send via SendGrid")
    t_step1 = datetime.now(timezone.utc)
    drafts1 = wait_for_drafts(api, cid, sequence_step=0, expected=3)
    if not drafts1:
        err("No step-1 drafts generated – check Celery worker logs")
        sys.exit(1)

    step1_by_lead: dict[str, dict] = {d["lead_id"]: d for d in drafts1}
    for lr in lead_records:
        d = step1_by_lead.get(lr["lead"]["id"])
        if d:
            send_draft(api, cid, d)
            time.sleep(1)

    sent1: dict[str, dict] = {}
    for lr in lead_records:
        d = step1_by_lead.get(lr["lead"]["id"])
        if d:
            m = wait_for_sent(api, cid, d["id"], lr["name"])
            if m:
                sent1[lr["lead"]["id"]] = m

    # ── Phase 5: Wait for Lead 1 (Alice) to reply ────────────────────────────
    hdr("PHASE 5 – Wait for Lead 1 (Alice / hitdasamit@gmail.com) to Reply")
    lr1 = lead_records[0]
    s1_msg = sent1.get(lr1["lead"]["id"])
    seed_subj1 = (s1_msg or {}).get("subject", "")
    info(f"Sent subject: \"{seed_subj1}\"")

    reply1 = poll_for_reply(lr1["email"], seed_subj1[:40], t_step1)
    if reply1 and s1_msg:
        ingest_reply(api, s1_msg["id"], lr1["lead"]["id"],
                     reply1["subject"], reply1["body_text"], lr1["name"])
        lr1["replied"] = True
    else:
        warn("No reply detected for Alice – conditional skip will NOT apply")

    # ── Phase 6: Advance → step 2 ────────────────────────────────────────────
    hdr("PHASE 6 – Advance to Step 2  (skipped leads depend on replies above)")
    t_step2 = datetime.now(timezone.utc)
    advance(api, cid)
    time.sleep(8)  # give Celery time to pick up tasks

    # leads that replied will be skipped by Celery (condition=no_reply)
    leads_with_reply = {lr["lead"]["id"] for lr in lead_records if lr.get("replied")}
    expected2 = len(lead_records) - len(leads_with_reply)
    info(f"Expecting {expected2} step-2 drafts ({len(leads_with_reply)} lead(s) replied → skipped)")

    drafts2 = wait_for_drafts(api, cid, sequence_step=1, expected=expected2, timeout=300)
    step2_by_lead: dict[str, dict] = {d["lead_id"]: d for d in drafts2}

    for lr in lead_records:
        lid = lr["lead"]["id"]
        d = step2_by_lead.get(lid)
        if d:
            send_draft(api, cid, d)
            time.sleep(1)
        elif lid in leads_with_reply:
            skip(f"{lr['name']} – no step-2 draft (correctly skipped after reply)")
        else:
            warn(f"{lr['name']} – step-2 draft missing (still generating?)")

    sent2: dict[str, dict] = {}
    for lr in lead_records:
        d = step2_by_lead.get(lr["lead"]["id"])
        if d:
            m = wait_for_sent(api, cid, d["id"], lr["name"])
            if m:
                sent2[lr["lead"]["id"]] = m

    # ── Phase 7: Wait for Lead 2 (Bob) to reply ──────────────────────────────
    hdr("PHASE 7 – Wait for Lead 2 (Bob / amit.softpro@gmail.com) to Reply")
    lr2 = lead_records[1]
    s2_msg = sent2.get(lr2["lead"]["id"])
    seed_subj2 = (s2_msg or {}).get("subject", "")
    info(f"Sent subject: \"{seed_subj2}\"")

    reply2 = poll_for_reply(lr2["email"], seed_subj2[:40], t_step2)
    if reply2 and s2_msg:
        ingest_reply(api, s2_msg["id"], lr2["lead"]["id"],
                     reply2["subject"], reply2["body_text"], lr2["name"])
        lr2["replied"] = True
    else:
        warn("No reply detected for Bob")

    # ── Phase 8: Advance → step 3 ────────────────────────────────────────────
    hdr("PHASE 8 – Advance to Step 3  (skipped leads depend on replies above)")
    t_step3 = datetime.now(timezone.utc)
    leads_with_reply.update(lid for lr in lead_records if lr.get("replied")
                            for lid in [lr["lead"]["id"]])
    advance(api, cid)
    time.sleep(8)

    expected3 = len(lead_records) - len(leads_with_reply)
    info(f"Expecting {expected3} step-3 drafts ({len(leads_with_reply)} lead(s) replied → skipped)")
    drafts3 = wait_for_drafts(api, cid, sequence_step=2, expected=expected3, timeout=300)
    step3_by_lead: dict[str, dict] = {d["lead_id"]: d for d in drafts3}

    lr3 = lead_records[2]
    sent3: dict[str, dict] = {}
    for lr in lead_records:
        lid = lr["lead"]["id"]
        d = step3_by_lead.get(lid)
        if d:
            send_draft(api, cid, d)
            time.sleep(1)
            m = wait_for_sent(api, cid, d["id"], lr["name"])
            if m:
                sent3[lid] = m
        elif lid in leads_with_reply:
            skip(f"{lr['name']} – correctly absent at step 3 (reply on record)")
        else:
            warn(f"{lr['name']} – step-3 draft missing (may still be generating)")

    # ── Phase 9: Wait for Lead 3 (Carol) to reply ────────────────────────────
    hdr("PHASE 9 – Wait for Lead 3 (Carol / amitd.iitb@gmail.com) to Reply")
    # Use whichever step message we last sent to Carol (step3 if available, else step2 etc.)
    s3_msg = sent3.get(lr3["lead"]["id"]) or sent2.get(lr3["lead"]["id"])
    seed_subj3 = (s3_msg or {}).get("subject", "")
    info(f"Sent subject: \"{seed_subj3}\"")

    reply3 = poll_for_reply(lr3["email"], seed_subj3[:40], t_step3)
    if reply3 and s3_msg:
        ingest_reply(api, s3_msg["id"], lr3["lead"]["id"],
                     reply3["subject"], reply3["body_text"], lr3["name"])
        lr3["replied"] = True
    else:
        warn("No reply detected for Carol")

    # ── Final summary ─────────────────────────────────────────────────────────
    print_summary(api, cid, lead_records)

    print(f"\n  {G}{BOLD}E2E test complete.{RST}")
    print(f"  {DIM}Campaign at: http://localhost:3000/campaigns{RST}")
    print(f"  {DIM}Replies at:  http://localhost:3000/replies{RST}")
    print()
    print(f"  {DIM}Clean up test data:{RST}")
    print(f"  {DIM}  docker compose exec postgres psql -U outreach -d outreachai -c \\{RST}")
    print(f"  {DIM}  \"DELETE FROM campaigns WHERE name LIKE '[TEST]%';  -- cascades replies/messages{RST}")
    print(f"  {DIM}  DELETE FROM leads WHERE 'e2e-test' = ANY(tags::text[]);{RST}")
    print(f"  {DIM}  DELETE FROM contacts WHERE 'e2e-test' = ANY(tags::text[]);{RST}")
    print(f"  {DIM}  DELETE FROM companies WHERE 'e2e-test' = ANY(tags::text[]);\"{RST}")
    print()


if __name__ == "__main__":
    main()

