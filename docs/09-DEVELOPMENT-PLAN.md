# 9. Development Plan & Roadmap

## Phase Overview

```
Phase 0: Foundation (Weeks 1-2)
Phase 1: Core Lead Management (Weeks 3-5)
Phase 2: AI Enrichment Pipeline (Weeks 6-9)
Phase 3: Campaign Engine (Weeks 10-13)
Phase 4: Reply Intelligence (Weeks 14-16)
Phase 5: Analytics & Polish (Weeks 17-19)
Phase 6: Production Hardening (Weeks 20-22)

Total MVP: ~22 weeks (5.5 months) for a 2-3 person team
```

---

## Phase 0: Foundation (Weeks 1-2)

### Goals
- Project scaffolding
- Local development environment
- Database setup
- Authentication system
- CI/CD pipeline

### Deliverables

| Task | Days | Details |
|---|---|---|
| Monorepo setup | 1 | Backend + Frontend + Infrastructure |
| Docker Compose dev environment | 1 | PostgreSQL, Redis, MinIO, Mailhog |
| Database schema + migrations | 2 | Alembic migrations for all core tables |
| FastAPI project structure | 1 | API gateway, service template, middleware |
| Authentication system | 2 | JWT auth, registration, login, RBAC |
| Next.js project setup | 1 | shadcn/ui, Tailwind, layout, auth pages |
| CI/CD pipeline | 1 | GitHub Actions: lint, test, build |
| API documentation | 1 | OpenAPI auto-generation, Swagger UI |

### Definition of Done
- `docker compose up` starts full stack locally
- User can register, login, see empty dashboard
- All tables created via migrations
- CI pipeline runs on push

---

## Phase 1: Core Lead Management (Weeks 3-5)

### Goals
- Lead CRUD
- CSV import
- Company/Contact management
- Lead pipeline
- Lead list UI with filtering

### Deliverables

| Task | Days | Details |
|---|---|---|
| Company/Contact/Lead models & API | 3 | CRUD endpoints, validation, dedup |
| CSV import pipeline | 3 | Upload, parse, validate, column mapping, bulk insert |
| Lead pipeline & stage management | 2 | Stage transitions, activity logging |
| Search & filtering | 2 | Full-text search, faceted filters, sorting |
| Lead list UI | 3 | Data table, filters, bulk actions, pagination |
| Lead detail UI | 2 | Profile view, enrichment placeholder, activity timeline |
| Import wizard UI | 2 | File upload, column mapping, progress |
| Tagging & bulk operations | 1 | Tag CRUD, bulk tag/assign/delete |

### Definition of Done
- Can upload 10,000 leads via CSV
- Lead list with real-time filtering
- Lead detail page with all fields
- Pipeline stage management works

---

## Phase 2: AI Enrichment Pipeline (Weeks 6-9)

### Goals
- Web research agent
- Data enrichment agent
- Insight extraction agent
- Lead scoring agent
- Enrichment UI

### Deliverables

| Task | Days | Details |
|---|---|---|
| AI Orchestrator service setup | 2 | LangChain, LangGraph, LLM provider config |
| Research Agent | 4 | SerpAPI, Firecrawl, Tavily integration + graph |
| Enrichment Agent | 3 | Structured extraction from raw research |
| Insight Extraction Agent | 3 | Hook generation, pain points, opportunities |
| Lead Scoring Agent | 2 | Scoring model, signal breakdown |
| Scoring profiles CRUD | 1 | Custom scoring weights per tenant |
| Celery enrichment pipeline | 2 | Async batch enrichment + retries + rate limiting |
| Enrichment data storage | 1 | Store research, enrichment, insights, scores |
| Enrichment UI | 2 | Enrichment view, scoring view, signal breakdown |
| Scoring dashboard UI | 1 | Score distribution, Hot/Warm/Cold filtering |
| Batch enrichment controls | 1 | Trigger batch enrichment, progress tracking |

### Definition of Done
- Upload leads → auto-enrichment runs
- Each lead has enrichment data, insights, score
- Lead list filterable by score tier
- Enrichment detail view shows full data

---

## Phase 3: Campaign Engine (Weeks 10-13)

### Goals
- Campaign CRUD
- Email generation with AI
- Email preview & editing
- Email sending via providers
- Tracking (opens, clicks)
- Follow-up scheduling

### Deliverables

| Task | Days | Details |
|---|---|---|
| Campaign service | 3 | CRUD, lifecycle, segment resolution |
| Email template system | 2 | Template CRUD, variable interpolation |
| Personalization Agent | 3 | AI email generation per lead |
| Email generation pipeline | 2 | Batch generation with Celery |
| Messaging channel layer | 2 | Abstract interface, email channel |
| Gmail API integration | 2 | OAuth, send, tracking pixel, link wrapping |
| SendGrid integration | 1 | API key auth, send, webhooks |
| Email tracking system | 2 | Open pixel, click redirect, webhook handlers |
| Follow-up scheduler | 2 | Celery Beat, condition checking, auto-send |
| Sender account management | 1 | Connect accounts, health monitoring |
| Campaign builder UI | 3 | Wizard, audience selector, sequence editor |
| Email preview/editor UI | 2 | Preview, edit, approve, bulk approve |
| Campaign monitoring UI | 1 | Status, metrics, lead progress |

### Definition of Done
- Can create campaign, generate emails, review, launch
- Emails sent via Gmail or SendGrid
- Open/click tracking works
- Follow-ups auto-schedule and auto-send

---

## Phase 4: Reply Intelligence (Weeks 14-16)

### Goals
- Reply detection
- AI reply analysis
- AI response generation
- Reply inbox UI
- Notification system

### Deliverables

| Task | Days | Details |
|---|---|---|
| Reply listener (Gmail watch) | 2 | Pub/Sub notifications, IMAP fallback |
| Reply matching | 1 | Match replies to leads/campaigns via headers |
| Reply Analysis Agent | 2 | Intent, sentiment, urgency, action items |
| Response Generation Agent | 2 | Context-aware reply suggestions |
| Auto-actions on reply | 1 | Cancel follow-ups, update stages, score boost |
| Notification service | 2 | In-app notifications, WebSocket push |
| Reply inbox UI | 3 | List, thread view, AI reply panel |
| Notification bell UI | 1 | Real-time badge, dropdown, mark read |

### Definition of Done
- Replies auto-detected and analyzed
- Inbox shows replies with AI analysis
- Can generate and send AI response
- Notifications push in real-time

---

## Phase 5: Analytics & Polish (Weeks 17-19)

### Goals
- Analytics dashboards
- Dashboard homepage
- Materialized views
- Export capabilities
- UX polish

### Deliverables

| Task | Days | Details |
|---|---|---|
| Analytics service | 2 | Aggregation queries, materialized views |
| Dashboard homepage | 3 | KPIs, charts, pipeline, recent activity, hot leads |
| Campaign analytics | 2 | Per-campaign metrics, comparison table |
| Lead analytics | 1 | Pipeline distribution, score distribution |
| Export system | 1 | CSV export for leads, campaign results |
| Settings pages | 2 | All settings tabs: team, AI, scoring, accounts |
| Admin: user management | 1 | Invite, role change, deactivate |
| Email deliverability dashboard | 1 | Account health, bounce rates, SPF/DKIM status |
| UX polish | 2 | Loading states, error handling, empty states, animations |

### Definition of Done
- Dashboard shows real-time metrics
- All analytics views populated with data
- Settings fully functional
- All CRUD flows polished

---

## Phase 6: Production Hardening (Weeks 20-22)

### Goals
- Security audit
- Performance optimization
- Deployment pipeline
- Monitoring & logging
- Documentation

### Deliverables

| Task | Days | Details |
|---|---|---|
| Security audit & fixes | 2 | Input validation, OWASP, rate limiting, CORS |
| Performance optimization | 2 | Query optimization, caching, lazy loading |
| Docker production builds | 1 | Multi-stage builds, security scanning |
| Kubernetes manifests | 2 | Deployments, services, HPA, ingress |
| Monitoring setup | 2 | Prometheus, Grafana, health checks |
| Logging setup | 1 | Structured logging, Loki, log levels |
| Error tracking | 1 | Sentry integration (backend + frontend) |
| Load testing | 1 | k6 scripts, 10k lead simulation |
| Documentation | 2 | API docs, user guide, deployment guide |
| Warm-up & domain setup | 1 | SPF/DKIM/DMARC, sender warm-up plan |

### Definition of Done
- Deployed to staging environment
- Handles 10k leads without performance issues
- Monitoring dashboards operational
- All security controls in place
- Documentation complete

---

## Post-MVP Roadmap

### V1.1 (Month 7-8)
- A/B testing for email subject lines
- Advanced campaign analytics
- Custom scoring formulas
- Lead deduplication improvements
- Mobile-responsive dashboard

### V1.2 (Month 9-10)
- Multi-user collaboration features
- Team-based lead assignment
- Shared inbox for replies
- Campaign templates marketplace
- Webhook integrations

### V2.0 (Month 11-14)
- WhatsApp channel integration
- LinkedIn connection request automation
- Multi-channel sequences (email → LinkedIn → email)
- Advanced CRM integrations (Salesforce, HubSpot)
- Custom AI prompt editor

### V2.5 (Month 15-18)
- SMS channel
- Slack notifications
- Advanced workflow builder (visual DAG)
- Custom enrichment source plugins
- API marketplace for third-party integrations

### V3.0 (Month 19-24)
- Multi-tenant SaaS deployment
- White-label capabilities
- SOC2 compliance
- Enterprise SSO (SAML/OIDC)
- AI model fine-tuning per tenant
- Real-time collaboration (live editing)
