# 12. Future Channel Expansion Design

## Multi-Channel Architecture

The messaging abstraction layer is designed for plug-and-play channel addition. Each channel implements the `MessageChannel` interface with zero changes to upstream services.

---

## Channel Expansion Roadmap

### Phase 2: WhatsApp Business API (Month 11-14)

```
Provider: Twilio WhatsApp Business API
Requirements:
- WhatsApp Business Account (verified)
- Twilio account with WhatsApp sandbox or production
- Template approval (WhatsApp requires pre-approved templates)

Implementation:
┌─────────────────────────────────────────────┐
│  WhatsAppChannel                             │
│  ├── TwilioWhatsAppProvider                  │
│  │   ├── send(message) → Twilio API          │
│  │   ├── handle_webhook(payload) → status    │
│  │   └── template_management()               │
│  ├── Template Approval Flow                  │
│  │   └── Submit template → WhatsApp review   │
│  └── Compliance                              │
│      ├── 24-hour message window              │
│      ├── Opt-in requirement                  │
│      └── Template-only for business-initiated│
└─────────────────────────────────────────────┘
```

**Key Constraints:**
- Business-initiated messages must use pre-approved templates
- 24-hour session window for free-form conversation after user reply
- Opt-in consent required before sending
- Message templates need variable slots matching our personalization

**Database Changes:**
```sql
ALTER TABLE contacts ADD COLUMN whatsapp_number VARCHAR(20);
ALTER TABLE contacts ADD COLUMN whatsapp_opt_in BOOLEAN DEFAULT false;
ALTER TABLE contacts ADD COLUMN whatsapp_opt_in_at TIMESTAMPTZ;
```

---

### Phase 2: LinkedIn Outreach (Month 11-14)

```
Provider: LinkedIn API + Proxycurl + Browser Automation (fallback)
Requirements:
- LinkedIn Sales Navigator (recommended)
- API access or authorized scraping
- Connection request limits awareness (100/week)

Implementation:
┌─────────────────────────────────────────────┐
│  LinkedInChannel                             │
│  ├── LinkedInAPIProvider                     │
│  │   ├── send_connection_request(message)    │
│  │   ├── send_inmail(message)                │
│  │   ├── send_message(message) — connections │
│  │   └── check_connection_status()           │
│  ├── BrowserAutomationProvider (fallback)    │
│  │   └── Playwright-based automation         │
│  └── Compliance                              │
│      ├── Daily connection limits             │
│      ├── Personalized invitation notes       │
│      └── Rate limiting (human-like pacing)   │
└─────────────────────────────────────────────┘
```

**Key Constraints:**
- Connection requests: ~100/week (LinkedIn limits)
- InMail: depends on Sales Navigator subscription
- Must pace requests to avoid account restrictions
- Multi-step: Connect → Wait for acceptance → Send message

**Sequence Extension:**
```json
{
  "steps": [
    {"channel": "linkedin", "action": "connect", "delay_days": 0},
    {"channel": "linkedin", "action": "message", "delay_days": 3, "condition": "connected"},
    {"channel": "email", "action": "send", "delay_days": 5, "condition": "no_reply"},
    {"channel": "email", "action": "follow_up", "delay_days": 10, "condition": "no_reply"}
  ]
}
```

---

### Phase 3: SMS (Month 15-18)

```
Provider: Twilio SMS
Requirements:
- Twilio account
- Registered A2P 10DLC campaign (US compliance)
- Opt-in consent

Implementation:
┌─────────────────────────────────────────────┐
│  SMSChannel                                  │
│  ├── TwilioSMSProvider                       │
│  │   ├── send(message) → Twilio API          │
│  │   ├── handle_webhook(payload) → status    │
│  │   └── handle_inbound(payload) → reply     │
│  └── Compliance                              │
│      ├── A2P 10DLC registration              │
│      ├── Opt-out keyword handling (STOP)     │
│      ├── Quiet hours enforcement             │
│      └── Character limit (160 / 1600)        │
└─────────────────────────────────────────────┘
```

**Database Changes:**
```sql
ALTER TABLE contacts ADD COLUMN phone_mobile VARCHAR(20);
ALTER TABLE contacts ADD COLUMN sms_opt_in BOOLEAN DEFAULT false;
ALTER TABLE contacts ADD COLUMN sms_opt_in_at TIMESTAMPTZ;
```

---

### Phase 3: Slack (Month 15-18)

```
Provider: Slack API (Web API + Events API)
Use Case: Internal notifications, not outbound sales

Implementation:
┌─────────────────────────────────────────────┐
│  SlackChannel                                │
│  ├── SlackAPIProvider                        │
│  │   ├── send_dm(message) → Slack DM         │
│  │   ├── send_channel(message) → Channel msg │
│  │   └── handle_event(event) → interaction   │
│  └── Use Cases                               │
│      ├── Notify sales team of hot replies    │
│      ├── Daily campaign summary to #sales    │
│      └── Approval workflow via Slack DMs     │
└─────────────────────────────────────────────┘
```

---

### CRM Integrations (Month 15-18)

```
┌─────────────────────────────────────────────┐
│  CRM Integration Layer                       │
│  ├── SalesforceConnector                     │
│  │   ├── sync_leads(direction: bidirectional)│
│  │   ├── create_salesforce_lead(lead)        │
│  │   ├── update_salesforce_contact(lead)     │
│  │   ├── log_activity(message)               │
│  │   └── sync_opportunities()                │
│  ├── HubSpotConnector                        │
│  │   ├── sync_contacts(direction: bi)        │
│  │   ├── create_hubspot_deal(lead)           │
│  │   ├── log_engagement(message)             │
│  │   └── sync_pipeline()                     │
│  └── Custom CRM (Webhook-based)             │
│      ├── Outbound webhooks on events         │
│      └── Inbound API for lead sync           │
└─────────────────────────────────────────────┘
```

**Sync Model:**
- Bidirectional sync with conflict resolution (last-write-wins or manual)
- Field mapping configuration per tenant
- Real-time sync via webhooks + periodic full sync
- Activity logging: every email sent/opens/reply logged in CRM

---

## Multi-Channel Sequence Builder

### Future Sequence Schema

```json
{
  "name": "Enterprise Multi-Channel Outreach",
  "steps": [
    {
      "step": 1,
      "channel": "linkedin",
      "action": "connection_request",
      "delay_days": 0,
      "message_template": "linkedin_connect_v1",
      "condition": null
    },
    {
      "step": 2,
      "channel": "email",
      "action": "send",
      "delay_days": 1,
      "message_template": "initial_outreach_v1",
      "condition": null
    },
    {
      "step": 3,
      "channel": "linkedin",
      "action": "message",
      "delay_days": 3,
      "message_template": "linkedin_followup_v1",
      "condition": "linkedin_connected AND no_email_reply"
    },
    {
      "step": 4,
      "channel": "email",
      "action": "send",
      "delay_days": 5,
      "message_template": "email_followup_v1",
      "condition": "no_reply_any_channel"
    },
    {
      "step": 5,
      "channel": "whatsapp",
      "action": "send",
      "delay_days": 10,
      "message_template": "whatsapp_template_v1",
      "condition": "has_whatsapp AND no_reply_any_channel"
    },
    {
      "step": 6,
      "channel": "email",
      "action": "send",
      "delay_days": 14,
      "message_template": "breakup_email_v1",
      "condition": "no_reply_any_channel"
    }
  ],
  "global_stop_conditions": [
    "replied_on_any_channel",
    "unsubscribed",
    "bounced_on_all_channels",
    "manual_stop"
  ]
}
```

### Cross-Channel Reply Tracking

When a lead replies on ANY channel, the system must:
1. Cancel pending messages on ALL channels
2. Consolidate the reply into the unified inbox
3. Maintain conversation thread across channels
4. Allow response on the same channel the reply came on

```
┌───────────────────────────────────────────────────────────┐
│  Unified Inbox                                             │
│                                                           │
│  Thread: John Doe — Acme Corp                             │
│  ┌──────────────────────────────────────────────────────┐ │
│  │ 📧 You (Email, Apr 3)                                │ │
│  │ "Hi John, congrats on the Series C..."               │ │
│  ├──────────────────────────────────────────────────────┤ │
│  │ 🔗 You (LinkedIn Connection, Apr 4)                   │ │
│  │ "Hi John, I'd love to connect..."                    │ │
│  ├──────────────────────────────────────────────────────┤ │
│  │ 🔗 John (LinkedIn Message, Apr 5)                     │ │
│  │ "Hey Amit, thanks for reaching out! Happy to chat."  │ │
│  │ Intent: Interested 🟢  •  Channel: LinkedIn           │ │
│  ├──────────────────────────────────────────────────────┤ │
│  │ ⚠️ Cancelled: Email follow-up (was scheduled Apr 8)  │ │
│  │ ⚠️ Cancelled: WhatsApp message (was scheduled Apr 13)│ │
│  └──────────────────────────────────────────────────────┘ │
│                                                           │
│  Reply on: [📧 Email] [🔗 LinkedIn] [💬 WhatsApp]       │
└───────────────────────────────────────────────────────────┘
```

---

## Channel Feature Matrix

| Feature | Email | LinkedIn | WhatsApp | SMS | Slack |
|---|---|---|---|---|---|
| Outbound messaging | ✅ | ✅ | ✅ | ✅ | ✅ |
| Open tracking | ✅ | ❌ | ✅ (read receipts) | ❌ | ❌ |
| Click tracking | ✅ | ❌ | ❌ | ✅ | ❌ |
| Reply detection | ✅ | ✅ | ✅ | ✅ | ✅ |
| Rich HTML | ✅ | ❌ | Limited | ❌ | ✅ (blocks) |
| Attachments | ✅ | ✅ | ✅ | ❌ | ✅ |
| Templates | ✅ | ❌ | Required | ✅ | ✅ |
| Scheduling | ✅ | ✅ | ✅ | ✅ | ✅ |
| Rate limits | Provider | 100 conn/wk | 1000/day | 1 msg/sec | 1 msg/sec |
| Opt-in required | ❌ (CAN-SPAM) | ❌ | ✅ | ✅ | ❌ |
| AI personalization | ✅ | ✅ | ✅ | ✅ | Limited |
