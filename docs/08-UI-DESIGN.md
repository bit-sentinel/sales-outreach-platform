# 8. UI/UX Architecture

## Design System

### Stack
- **Next.js 14** (App Router with Server Components)
- **React 18** (Client Components where needed)
- **Tailwind CSS** (utility-first styling)
- **shadcn/ui** (enterprise component library — Radix primitives + Tailwind)
- **Lucide Icons** (icon system)
- **Tremor** (dashboard charts and KPIs)
- **TanStack Table** (data grids)
- **TanStack Query** (server state management)
- **Zustand** (lightweight client state)
- **React Hook Form + Zod** (form validation)
- **Socket.IO** (real-time updates)
- **Framer Motion** (subtle animations)

### Design Tokens

```css
/* Color System (HSL, Dark mode supported) */
--background: 0 0% 100%;
--foreground: 222.2 84% 4.9%;
--primary: 221.2 83.2% 53.3%;      /* Brand blue */
--primary-foreground: 210 40% 98%;
--secondary: 210 40% 96%;
--accent: 210 40% 96%;
--destructive: 0 84.2% 60.2%;       /* Red for errors */
--success: 142 76% 36%;             /* Green for positive */
--warning: 38 92% 50%;              /* Amber for warnings */
--hot: 0 84% 60%;                   /* Hot leads — red */
--warm: 38 92% 50%;                 /* Warm leads — amber */
--cold: 210 40% 60%;                /* Cold leads — blue-gray */

/* Typography */
--font-sans: 'Inter', system-ui, sans-serif;
--font-mono: 'JetBrains Mono', monospace;

/* Spacing Scale (Tailwind default) */
/* Shadows, Borders */
--radius: 0.5rem;
```

---

## Application Layout

```
┌──────────────────────────────────────────────────────────────────┐
│  ┌────────┐  OutreachAI    [Search...]     🔔 3  👤 Amit ▼     │
│  │  Logo  │                                                      │
├──┴────────┴─┬────────────────────────────────────────────────────┤
│             │                                                     │
│  Dashboard  │   ┌─────────────────────────────────────────────┐  │
│             │   │                                              │  │
│  Leads      │   │         MAIN CONTENT AREA                   │  │
│   ├ All     │   │                                              │  │
│   ├ Hot     │   │   Renders based on active route:             │  │
│   ├ Warm    │   │   - Dashboard                                │  │
│   └ Cold    │   │   - Lead list / detail                       │  │
│             │   │   - Campaign builder                         │  │
│  Companies  │   │   - Email editor                             │  │
│             │   │   - Inbox                                    │  │
│  Campaigns  │   │   - Analytics                                │  │
│   ├ Active  │   │   - Settings                                 │  │
│   ├ Drafts  │   │                                              │  │
│   └ Compl.  │   │                                              │  │
│             │   │                                              │  │
│  Inbox      │   │                                              │  │
│   └ 12 new  │   │                                              │  │
│             │   │                                              │  │
│  Analytics  │   │                                              │  │
│             │   │                                              │  │
│  Templates  │   │                                              │  │
│             │   └─────────────────────────────────────────────┘  │
│  Settings   │                                                     │
│             │                                                     │
│  ─────────  │                                                     │
│  Help       │                                                     │
│  Logout     │                                                     │
└─────────────┴─────────────────────────────────────────────────────┘
```

---

## Page Designs

### 1. Dashboard (`/dashboard`)

```
┌─────────────────────────────────────────────────────────────────┐
│  Dashboard                                          This Week ▼ │
│                                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │   1,247  │ │    342   │ │   24.3%  │ │   8.7%   │          │
│  │ Total    │ │  Emails  │ │  Open    │ │  Reply   │          │
│  │ Leads    │ │  Sent    │ │  Rate    │ │  Rate    │          │
│  │ ↑ +123   │ │ ↑ +89    │ │ ↑ +2.1% │ │ ↑ +1.3% │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│                                                                  │
│  ┌──────────────────────┐  ┌──────────────────────────────┐    │
│  │  Lead Score          │  │  Campaign Performance         │    │
│  │  Distribution        │  │  (line chart — time series)   │    │
│  │  ┌─────┐             │  │                                │    │
│  │  │ 🔴  │ 156 Hot     │  │  ─── Sent                    │    │
│  │  │ 🟡  │ 487 Warm    │  │  ─── Opened                  │    │
│  │  │ 🔵  │ 604 Cold    │  │  ─── Replied                 │    │
│  │  └─────┘             │  │                                │    │
│  │  (donut chart)       │  │  ▁▂▃▅▇█▇▅▃▂▁                 │    │
│  └──────────────────────┘  └──────────────────────────────────┘ │
│                                                                  │
│  ┌──────────────────────┐  ┌──────────────────────────────┐    │
│  │  Pipeline Stages      │  │  Recent Activity              │    │
│  │  (horizontal bar)     │  │                                │    │
│  │  New      ████████ 89 │  │  • John Doe replied (Hot) 2m  │    │
│  │  Enriched ██████  67  │  │  • 50 leads enriched       5m │    │
│  │  Scored   ████████ 92 │  │  • Campaign "Q1" 80% done 10m│    │
│  │  Contacted████████ 156│  │  • Lisa Chen opened email  15m│    │
│  │  Replied  ████    42  │  │  • New import: 200 leads   1h │    │
│  │  Converted███     28  │  │                                │    │
│  └──────────────────────┘  └──────────────────────────────────┘ │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  Hot Leads Requiring Action                                  ││
│  │  ┌──────┬──────────────┬────────┬────────┬────────────────┐ ││
│  │  │ Name │ Company      │ Score  │ Intent │ Action         │ ││
│  │  ├──────┼──────────────┼────────┼────────┼────────────────┤ ││
│  │  │ John │ Acme Corp    │ 92 🔴  │Meeting │ [Reply] [View] │ ││
│  │  │ Lisa │ TechStart    │ 87 🔴  │Interest│ [Reply] [View] │ ││
│  │  │ Mike │ GlobaCorp    │ 78 🔴  │Question│ [Reply] [View] │ ││
│  │  └──────┴──────────────┴────────┴────────┴────────────────┘ ││
│  └─────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────┘
```

### 2. Lead Management (`/leads`)

```
┌─────────────────────────────────────────────────────────────────┐
│  Leads (1,247)          [Search leads...]     [Import] [+ Add]  │
│                                                                  │
│  Filters: [Stage ▼] [Score ▼] [Tags ▼] [Industry ▼] [Size ▼]  │
│           [Assigned ▼] [Date Range] [Clear All]                  │
│                                                                  │
│  Quick: [All] [🔴 Hot (156)] [🟡 Warm (487)] [🔵 Cold (604)]   │
│                                                                  │
│  ☐ Select All  │ Showing 1-25 of 1,247  │ ◀ 1 2 3 ... 50 ▶    │
│                                                                  │
│  ┌──┬──────────────┬──────────────┬────────┬──────┬──────┬────┐ │
│  │☐ │ Contact      │ Company      │ Score  │Stage │ Last │Act │ │
│  │  │              │              │        │      │ Cont │    │ │
│  ├──┼──────────────┼──────────────┼────────┼──────┼──────┼────┤ │
│  │☐ │ John Doe     │ Acme Corp    │ 92 🔴  │Repl  │ 2d   │ ⋯ │ │
│  │  │ VP Marketing │ Technology   │        │      │ ago  │    │ │
│  │  │ john@acme.co │ 500+ emp     │        │      │      │    │ │
│  ├──┼──────────────┼──────────────┼────────┼──────┼──────┼────┤ │
│  │☐ │ Lisa Chen    │ TechStart    │ 87 🔴  │Cont  │ 1d   │ ⋯ │ │
│  │  │ Events Dir.  │ SaaS         │        │      │ ago  │    │ │
│  │  │ lisa@tech.io │ 200+ emp     │        │      │      │    │ │
│  ├──┼──────────────┼──────────────┼────────┼──────┼──────┼────┤ │
│  │☐ │ Sarah Kim    │ MegaEvent    │ 65 🟡  │Scored│ —    │ ⋯ │ │
│  │  │ CMO          │ Events       │        │      │      │    │ │
│  │  │ s@mega.com   │ 50+ emp      │        │      │      │    │ │
│  └──┴──────────────┴──────────────┴────────┴──────┴──────┴────┘ │
│                                                                  │
│  Bulk Actions: [Tag ▼] [Assign ▼] [Stage ▼] [Campaign ▼] [Del]│
└──────────────────────────────────────────────────────────────────┘
```

### 3. Lead Detail (`/leads/:id`)

```
┌─────────────────────────────────────────────────────────────────┐
│  ← Back to Leads                                                │
│                                                                  │
│  ┌──────────────────────────────────┬──────────────────────────┐│
│  │ 👤 John Doe                      │ Score: 92 🔴 Hot         ││
│  │ VP of Marketing                  │                          ││
│  │ Acme Corporation                 │ Stage: [Replied ▼]       ││
│  │ john@acme.co  •  +1-555-1234    │ Assigned: [Amit ▼]       ││
│  │ San Francisco, CA               │                          ││
│  │                                  │ Tags: [enterprise] [cvent]││
│  │ [Email] [LinkedIn] [Edit]       │ [+ Add Tag]              ││
│  └──────────────────────────────────┴──────────────────────────┘│
│                                                                  │
│  [Overview] [Enrichment] [Scoring] [Emails] [Activity]           │
│                                                                  │
│  ╔═══════════════════════════════════════════════════════════╗   │
│  ║  ENRICHMENT TAB                                          ║   │
│  ║                                                          ║   │
│  ║  Company Intelligence          Completeness: 87% ████░  ║   │
│  ║  ├── Industry: Technology / SaaS                         ║   │
│  ║  ├── Size: 501-1000 employees                            ║   │
│  ║  ├── Funding: $120M (Series C, Jan 2026)                 ║   │
│  ║  ├── Category: Enterprise                                ║   │
│  ║  ├── Revenue: $50-100M (estimated)                       ║   │
│  ║  └── Tech Stack: Cvent, Salesforce, Marketo              ║   │
│  ║                                                          ║   │
│  ║  Event Intelligence                                      ║   │
│  ║  ├── Maturity: Advanced ████████                         ║   │
│  ║  ├── Upcoming: Global Summit 2026 (Jun), User Conf (Sep) ║   │
│  ║  ├── Past: 12 events in 2025                             ║   │
│  ║  └── Budget Est: $500K-$1M                               ║   │
│  ║                                                          ║   │
│  ║  Signals                                                 ║   │
│  ║  ├── 🟢 Recent $50M funding (Jan 2026)                   ║   │
│  ║  ├── 🟢 Hiring 3 event managers                          ║   │
│  ║  ├── 🟢 Expanding to APAC region                         ║   │
│  ║  └── 🟡 Currently uses Cvent (may have internal team)    ║   │
│  ║                                                          ║   │
│  ║  AI Insights                                             ║   │
│  ║  "Acme Corp is a fast-growing SaaS company that recently ║   │
│  ║   raised $50M Series C. They run 12+ events annually     ║   │
│  ║   using Cvent and are expanding internationally. Their    ║   │
│  ║   hiring of event managers suggests scaling event ops —   ║   │
│  ║   a strong fit for consulting services."                  ║   │
│  ║                                                          ║   │
│  ║  Personalization Hooks                                    ║   │
│  ║  • "Congratulations on the Series C — exciting growth"    ║   │
│  ║  • "Global Summit 2026 looks ambitious — 5000 attendees"  ║   │
│  ║  • "APAC expansion means new compliance requirements"     ║   │
│  ╚═══════════════════════════════════════════════════════════╝   │
│                                                                  │
│  ╔═══════════════════════════════════════════════════════════╗   │
│  ║  SCORING TAB                                              ║   │
│  ║                                                          ║   │
│  ║  Total Score: 92/100  ████████████████████░  HOT 🔴      ║   │
│  ║                                                          ║   │
│  ║  Signal Breakdown:                                       ║   │
│  ║  Upcoming Events      15/15  ████████████████  ██████    ║   │
│  ║  Event Maturity       15/15  ████████████████  ██████    ║   │
│  ║  Recent Funding       12/12  ████████████████  ██████    ║   │
│  ║  Company Size         10/10  ████████████████  ██████    ║   │
│  ║  Tech Compatibility   10/10  ████████████████  ██████    ║   │
│  ║  Growth Signals       10/10  ████████████████  ██████    ║   │
│  ║  Hiring Activity       8/8   ████████████████  ██████    ║   │
│  ║  Engagement (opens)    8/8   ████████████████  ██████    ║   │
│  ║  Company Category      4/5   ████████████████  █████░    ║   │
│  ║  Engagement (replies)  0/7   ░░░░░░░░░░░░░░░░  ░░░░░░    ║   │
│  ╚═══════════════════════════════════════════════════════════╝   │
└──────────────────────────────────────────────────────────────────┘
```

### 4. Campaign Builder (`/campaigns/new`)

```
┌─────────────────────────────────────────────────────────────────┐
│  Create Campaign                                    [Save Draft]│
│                                                                  │
│  ┌── Step 1: Setup ──── Step 2: Audience ─── Step 3: Content ──┐│
│  │   Step 4: Schedule ── Step 5: Review & Launch               ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ╔═══════════ STEP 3: Content ══════════════════════════════╗   │
│  ║                                                          ║   │
│  ║  Email Sequence                                          ║   │
│  ║                                                          ║   │
│  ║  ┌─ Email 1: Initial Outreach ──────────────────────┐   ║   │
│  ║  │  Delay: Immediate                                 │   ║   │
│  ║  │  Template: [AI-Generated Personalized ▼]          │   ║   │
│  ║  │  Tone: [Consultative ▼]                           │   ║   │
│  ║  │  [Preview] [Edit Template]                        │   ║   │
│  ║  └──────────────────────────────────────────────────┘   ║   │
│  ║       │                                                  ║   │
│  ║       ▼ Wait 3 days · Condition: No Reply               ║   │
│  ║                                                          ║   │
│  ║  ┌─ Email 2: Follow-up ─────────────────────────────┐   ║   │
│  ║  │  Delay: 3 days after Email 1                      │   ║   │
│  ║  │  Template: [Value-Add Follow-up ▼]                │   ║   │
│  ║  │  [Preview] [Edit Template]                        │   ║   │
│  ║  └──────────────────────────────────────────────────┘   ║   │
│  ║       │                                                  ║   │
│  ║       ▼ Wait 7 days · Condition: No Reply               ║   │
│  ║                                                          ║   │
│  ║  ┌─ Email 3: Case Study ────────────────────────────┐   ║   │
│  ║  │  Delay: 7 days after Email 2                      │   ║   │
│  ║  │  Template: [Case Study Share ▼]                   │   ║   │
│  ║  │  [Preview] [Edit Template]                        │   ║   │
│  ║  └──────────────────────────────────────────────────┘   ║   │
│  ║       │                                                  ║   │
│  ║       ▼ Wait 14 days · Condition: No Reply              ║   │
│  ║                                                          ║   │
│  ║  ┌─ Email 4: Breakup ──────────────────────────────┐    ║   │
│  ║  │  Delay: 14 days after Email 3                     │   ║   │
│  ║  │  Template: [Respectful Close ▼]                   │   ║   │
│  ║  │  [Preview] [Edit Template]                        │   ║   │
│  ║  └──────────────────────────────────────────────────┘   ║   │
│  ║                                                          ║   │
│  ║  [+ Add Step]                                            ║   │
│  ║                                                          ║   │
│  ║              [← Back]  [Generate Emails →]               ║   │
│  ╚══════════════════════════════════════════════════════════╝   │
└──────────────────────────────────────────────────────────────────┘
```

### 5. Email Preview & Editor (`/campaigns/:id/emails/:messageId`)

```
┌─────────────────────────────────────────────────────────────────┐
│  Email Preview — John Doe, Acme Corp     [← Prev] [Next →]     │
│                                           Email 42/500          │
│                                                                  │
│  ┌──────────────────────────┬──────────────────────────────────┐│
│  │  GENERATED EMAIL          │  LEAD CONTEXT                   ││
│  │                          │                                   ││
│  │  From: amit@consult.com  │  👤 John Doe                     ││
│  │  To: john@acme.co       │  VP Marketing, Acme Corp          ││
│  │                          │  Score: 92 🔴 Hot                ││
│  │  Subject:                │                                   ││
│  │  ┌──────────────────┐   │  Key Signals:                     ││
│  │  │ Quick question    │   │  • Series C ($50M, Jan 2026)     ││
│  │  │ about Global      │   │  • Global Summit 2026 planned    ││
│  │  │ Summit 2026       │   │  • Hiring event managers         ││
│  │  └──────────────────┘   │  • Uses Cvent                     ││
│  │                          │                                   ││
│  │  Body:                   │  AI Hooks Used:                   ││
│  │  ┌──────────────────┐   │  ✓ Series C congratulation        ││
│  │  │ Hi John,          │   │  ✓ Global Summit reference        ││
│  │  │                   │   │  ✓ APAC expansion mention         ││
│  │  │ Congrats on       │   │                                   ││
│  │  │ Acme's Series C — │   │  Enrichment Completeness: 87%    ││
│  │  │ exciting times.   │   │                                   ││
│  │  │                   │   │  Previous Contact:                ││
│  │  │ I noticed you're  │   │  None                             ││
│  │  │ planning Global   │   │                                   ││
│  │  │ Summit 2026 for   │   │  ──────────────────────           ││
│  │  │ 5000+ attendees.  │   │  [View Full Profile]              ││
│  │  │ Managing events   │   │  [View Enrichment]                ││
│  │  │ at that scale on  │   │  [Re-enrich Lead]                 ││
│  │  │ Cvent needs a     │   │                                   ││
│  │  │ specialized       │   │                                   ││
│  │  │ approach...       │   │                                   ││
│  │  │                   │   │                                   ││
│  │  │ Would you be open │   │                                   ││
│  │  │ to a 15-min chat? │   │                                   ││
│  │  └──────────────────┘   │                                   ││
│  │                          │                                   ││
│  │  Word count: 94          │                                   ││
│  │  AI Model: GPT-4o       │                                   ││
│  │  Spam Score: Low ✓      │                                   ││
│  └──────────────────────────┴──────────────────────────────────┘│
│                                                                  │
│  [✎ Edit] [🔄 Regenerate] [✓ Approve] [✕ Skip] [Approve All]  │
└──────────────────────────────────────────────────────────────────┘
```

### 6. Reply Inbox (`/inbox`)

```
┌─────────────────────────────────────────────────────────────────┐
│  Inbox (12 unread)       [All] [Unread] [Action Needed] [Hot]   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │  🔴 John Doe — Acme Corp                              2 min ││
│  │  Intent: 🤝 Meeting Request  •  Sentiment: 😊 Positive      ││
│  │  "Hi Amit, thanks for reaching out. We're indeed ramping    ││
│  │   up our events. Would love to chat — how about Thursday?"  ││
│  │  AI Summary: Prospect wants to schedule a call Thursday.    ││
│  │  [View] [Reply] [AI Reply ✨]                               ││
│  ├──────────────────────────────────────────────────────────────┤│
│  │  🟡 Lisa Chen — TechStart                             1 hr  ││
│  │  Intent: ❓ Question  •  Sentiment: 😐 Neutral               ││
│  │  "Can you share more about your Cvent consulting rates?"    ││
│  │  AI Summary: Prospect asking about pricing.                 ││
│  │  [View] [Reply] [AI Reply ✨]                               ││
│  ├──────────────────────────────────────────────────────────────┤│
│  │  🔵 Bob Smith — MegaCorp                              3 hr  ││
│  │  Intent: 🏖️ Out of Office  •  Auto-handled                  ││
│  │  "I'm OOO until April 15. Contact sarah@mega for urgent."  ││
│  │  AI Action: Follow-up rescheduled to April 16.              ││
│  │  [View]                                                     ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ── Reply Detail (expanded view) ──                              │
│  ┌──────────────────────────┬───────────────────────────────────┐│
│  │  Conversation Thread     │  AI Reply Assistant               ││
│  │                          │                                   ││
│  │  ▸ You (Apr 3, 10:00)   │  Suggested Response:              ││
│  │    "Hi John, Congrats..."│  ┌─────────────────────────────┐  ││
│  │                          │  │ Hi John,                     │  ││
│  │  ◂ John (Apr 6, 09:15)  │  │                              │  ││
│  │    "Hi Amit, thanks..."  │  │ Great to hear! Thursday      │  ││
│  │                          │  │ works perfectly. How about    │  ││
│  │                          │  │ 2pm ET? Here's my calendar   │  ││
│  │                          │  │ link: [calendly.com/amit]    │  ││
│  │                          │  │                              │  ││
│  │                          │  │ Looking forward to           │  ││
│  │                          │  │ discussing how we can help   │  ││
│  │                          │  │ with Global Summit 2026.     │  ││
│  │                          │  │                              │  ││
│  │                          │  │ Best, Amit                   │  ││
│  │                          │  └─────────────────────────────┘  ││
│  │                          │                                   ││
│  │                          │  [✎ Edit] [🔄 Regenerate]        ││
│  │                          │  [📤 Send Response]               ││
│  └──────────────────────────┴───────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────┘
```

### 7. Analytics Dashboard (`/analytics`)

```
┌─────────────────────────────────────────────────────────────────┐
│  Analytics                     [Last 7 days ▼] [Export Report]  │
│                                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │   5,423  │ │   4,891  │ │   1,189  │ │    423   │          │
│  │  Sent    │ │ Delivered│ │  Opened  │ │ Replied  │          │
│  │          │ │  90.2%   │ │  24.3%   │ │  8.6%    │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  Daily Performance (area chart)                              ││
│  │                                                              ││
│  │  400 ┤                  ╭─╮                                  ││
│  │  300 ┤             ╭───╯  ╰──╮                               ││
│  │  200 ┤        ╭───╯         ╰──╮                             ││
│  │  100 ┤   ╭───╯                  ╰──╮                         ││
│  │    0 ┤──╯                          ╰──                       ││
│  │       Mon   Tue   Wed   Thu   Fri   Sat   Sun                ││
│  │       ─── Sent   ─── Opened   ─── Replied                   ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌──────────────────────────┐ ┌────────────────────────────────┐│
│  │  Top Campaigns            │ │  Most Engaged Leads            ││
│  │                           │ │                                ││
│  │  1. Q1 Enterprise  32.1%  │ │  1. John Doe (92) — 5 opens   ││
│  │     reply rate            │ │  2. Lisa Chen (87) — replied   ││
│  │  2. Cvent Users    28.4%  │ │  3. Mike Ross (78) — 3 clicks ││
│  │     reply rate            │ │  4. Amy Liu (75) — 4 opens     ││
│  │  3. Events Pros    19.2%  │ │  5. Sam Park (71) — replied    ││
│  │     reply rate            │ │                                ││
│  └──────────────────────────┘ └────────────────────────────────┘│
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  Campaign Comparison Table                                   ││
│  │  ┌──────────────┬──────┬─────┬──────┬──────┬──────┬──────┐ ││
│  │  │ Campaign     │ Sent │ Del │ Open │ Click│ Reply│ Conv │ ││
│  │  ├──────────────┼──────┼─────┼──────┼──────┼──────┼──────┤ ││
│  │  │ Q1 Enterprise│ 2000 │ 95% │ 28%  │ 12%  │ 32%  │ 8%  │ ││
│  │  │ Cvent Users  │ 1500 │ 93% │ 25%  │ 10%  │ 28%  │ 6%  │ ││
│  │  │ Events Pros  │ 1923 │ 91% │ 21%  │  8%  │ 19%  │ 4%  │ ││
│  │  └──────────────┴──────┴─────┴──────┴──────┴──────┴──────┘ ││
│  └─────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────┘
```

### 8. Settings (`/settings`)

```
Tabs: [General] [Email Accounts] [AI Config] [Team] [Scoring] [Billing]

Email Accounts tab:
┌─────────────────────────────────────────────────────────────────┐
│  Connected Email Accounts                   [+ Connect Account] │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ 📧 amit@consultfirm.com                                     ││
│  │ Provider: Gmail  •  Status: ✅ Active  •  Health: 98%       ││
│  │ Daily Limit: 150  •  Sent Today: 42  •  Warmup: Complete   ││
│  │ SPF: ✅  DKIM: ✅  DMARC: ✅                                ││
│  │ Bounce Rate: 1.2%  •  Spam Rate: 0.02%                     ││
│  │ [Settings] [Pause] [Disconnect]                             ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ 📧 sales@consultfirm.com                                    ││
│  │ Provider: SendGrid  •  Status: ⚠️ Warming Up (Day 12/30)   ││
│  │ Daily Limit: 80  •  Sent Today: 12  •  Warmup: 40%         ││
│  │ SPF: ✅  DKIM: ✅  DMARC: ⬜ Pending                        ││
│  │ [Settings] [Pause] [Disconnect]                             ││
│  └─────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────┘
```

---

## Frontend Directory Structure

```
frontend/
├── app/                          # Next.js App Router
│   ├── (auth)/                   # Auth layout group
│   │   ├── login/page.tsx
│   │   ├── register/page.tsx
│   │   └── layout.tsx
│   ├── (dashboard)/              # Main app layout group
│   │   ├── dashboard/page.tsx
│   │   ├── leads/
│   │   │   ├── page.tsx          # Lead list
│   │   │   ├── [id]/page.tsx     # Lead detail
│   │   │   └── import/page.tsx   # Import wizard
│   │   ├── companies/
│   │   │   ├── page.tsx
│   │   │   └── [id]/page.tsx
│   │   ├── campaigns/
│   │   │   ├── page.tsx          # Campaign list
│   │   │   ├── new/page.tsx      # Campaign builder
│   │   │   └── [id]/
│   │   │       ├── page.tsx      # Campaign detail
│   │   │       ├── emails/page.tsx  # Email review
│   │   │       └── analytics/page.tsx
│   │   ├── inbox/
│   │   │   ├── page.tsx          # Reply inbox
│   │   │   └── [id]/page.tsx     # Reply thread
│   │   ├── analytics/page.tsx
│   │   ├── templates/page.tsx
│   │   ├── settings/
│   │   │   ├── page.tsx          # General settings
│   │   │   ├── email-accounts/page.tsx
│   │   │   ├── team/page.tsx
│   │   │   ├── scoring/page.tsx
│   │   │   ├── ai/page.tsx
│   │   │   └── billing/page.tsx
│   │   └── layout.tsx            # Dashboard shell (sidebar + header)
│   ├── api/                      # Next.js API routes (BFF proxy)
│   │   └── [...proxy]/route.ts
│   ├── layout.tsx                # Root layout
│   └── globals.css
├── components/
│   ├── ui/                       # shadcn/ui components
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   ├── dialog.tsx
│   │   ├── dropdown-menu.tsx
│   │   ├── input.tsx
│   │   ├── select.tsx
│   │   ├── table.tsx
│   │   ├── tabs.tsx
│   │   ├── badge.tsx
│   │   ├── toast.tsx
│   │   └── ...
│   ├── leads/
│   │   ├── lead-table.tsx
│   │   ├── lead-card.tsx
│   │   ├── lead-detail-panel.tsx
│   │   ├── lead-enrichment-view.tsx
│   │   ├── lead-scoring-view.tsx
│   │   ├── lead-import-wizard.tsx
│   │   └── lead-filters.tsx
│   ├── campaigns/
│   │   ├── campaign-builder.tsx
│   │   ├── sequence-editor.tsx
│   │   ├── email-preview.tsx
│   │   ├── email-editor.tsx
│   │   ├── campaign-metrics.tsx
│   │   └── audience-selector.tsx
│   ├── inbox/
│   │   ├── reply-list.tsx
│   │   ├── reply-thread.tsx
│   │   ├── ai-reply-panel.tsx
│   │   └── intent-badge.tsx
│   ├── analytics/
│   │   ├── kpi-cards.tsx
│   │   ├── pipeline-chart.tsx
│   │   ├── score-distribution.tsx
│   │   ├── campaign-comparison.tsx
│   │   └── engagement-timeline.tsx
│   ├── layout/
│   │   ├── sidebar.tsx
│   │   ├── header.tsx
│   │   ├── notification-bell.tsx
│   │   └── user-menu.tsx
│   └── shared/
│       ├── data-table.tsx        # Reusable TanStack Table wrapper
│       ├── score-badge.tsx       # Hot/Warm/Cold badge
│       ├── activity-timeline.tsx
│       ├── empty-state.tsx
│       ├── loading-skeleton.tsx
│       └── error-boundary.tsx
├── lib/
│   ├── api-client.ts             # Axios/fetch client for backend API
│   ├── auth.ts                   # Auth utilities
│   ├── socket.ts                 # Socket.IO client
│   ├── utils.ts                  # Utility functions
│   └── constants.ts
├── hooks/
│   ├── use-leads.ts              # TanStack Query hooks for leads
│   ├── use-campaigns.ts
│   ├── use-replies.ts
│   ├── use-analytics.ts
│   ├── use-notifications.ts
│   ├── use-websocket.ts
│   └── use-auth.ts
├── stores/
│   ├── notification-store.ts     # Zustand stores
│   └── ui-store.ts
├── types/
│   ├── lead.ts
│   ├── campaign.ts
│   ├── message.ts
│   ├── reply.ts
│   ├── analytics.ts
│   └── user.ts
├── tailwind.config.ts
├── next.config.mjs
├── package.json
└── tsconfig.json
```
