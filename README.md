# OutreachAI

**Modular, AI-Native Sales Outreach Platform**

An enterprise-grade platform that combines AI-powered research, lead enrichment, hyper-personalized email generation, and intelligent campaign management. Built for consultancy firms and sales teams managing large-scale outreach across multiple verticals.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     Next.js 14 Frontend                 │
│         (App Router · TanStack Query · Zustand)         │
└──────────────────────────┬──────────────────────────────┘
                           │ REST / WebSocket
┌──────────────────────────▼──────────────────────────────┐
│                    FastAPI Backend                       │
│       (Async · SQLAlchemy 2.0 · Pydantic v2)           │
├─────────────┬──────────────┬────────────┬───────────────┤
│  AI Agents  │   Services   │  Events    │  Middleware    │
│  (LangChain │  (Lead/Cam-  │  (Redis    │  (Rate Limit  │
│   LangGraph)│   paign/Auth)│   Streams) │   Tenant/Log) │
└──────┬──────┴──────┬───────┴─────┬──────┴───────────────┘
       │             │             │
  ┌────▼────┐  ┌─────▼─────┐  ┌───▼────┐
  │ Celery  │  │PostgreSQL │  │ Redis  │
  │ Workers │  │ + PGVector│  │  7.x   │
  └─────────┘  └───────────┘  └────────┘
```

## Key Features

- **Evidence-Based Lead Intelligence (v3)** — A six-stage agent pipeline (identity → event fit → pressure → targeted research → synthesis → outreach) scores leads against auditable `EvidenceItem` citations rather than an opaque number. Weighted scoring applies anti-gaming caps and requires a compound gate of ≥2 independently strong signals before a lead is classified "hot."
- **Autonomous Outreach Loop** — A Celery-scheduled loop scores candidate leads, plans a multi-step campaign, and generates step-0 emails end to end, with no human in the loop unless test mode is on.
- **Dual AI QA Gate on Every Email** — Generated subject lines and bodies are scored by an LLM reviewer against a fixed rubric (subject ≥75/100, body ≥70/100) before send, with up to 3 regenerate attempts and rubric-driven rewrite suggestions.
- **Weekly Strategy Feedback Loop** — A weekly job aggregates open/reply-rate performance by messaging angle, has an LLM synthesize what's working, and injects those learnings into the next campaign's email generation as strategy context.
- **Human-Paced Sending** — Business-hour/business-day send windows plus a randomized 5–10 minute pre-send delay avoid bulk-sender patterns; sender accounts rotate by least-loaded, capped by daily limits.
- **Cost-Controlled Research** — The targeted-research agent multiplexes multiple providers (Tavily, SerpAPI, Perplexity, Firecrawl) behind a daily spend budget and a negative cache so known dead-end leads aren't re-queried.
- **Reply Analysis** — Automatic intent detection, sentiment, and suggested responses from inbound replies (IMAP polling + SendGrid webhooks).
- **Self-Built Health Monitoring** — A periodic health-check task watches sender/provider connectivity and writes alerts the admin dashboard surfaces, plus an LLM-powered ops chatbot that can query live Docker/DB/Redis/Celery health conversationally.
- **Multi-Tenant** — Row-level tenant isolation across leads, campaigns, and sender accounts.
- **Test Mode** — Full dry-run path (redirected sends, collapsed delays, tagged campaigns) so the autonomous loop can be exercised safely before going live.

## Tech Stack

| Layer         | Technology                                             |
|---------------|--------------------------------------------------------|
| Frontend      | Next.js 14, React 18, Tailwind CSS, shadcn/ui, Zustand |
| Backend       | Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2 |
| AI / LLM      | GPT-4o / GPT-4o-mini and Claude 3.5 Sonnet / Haiku, used per-agent depending on task cost/quality tradeoff |
| Database      | PostgreSQL 16, PGVector (embeddings), pg_trgm          |
| Queue / Cache | Redis 7, Celery 5.4                                   |
| Infrastructure| Docker Compose on a Hetzner VPS (production), Caddy reverse proxy + TLS; Kubernetes manifests available under `infra/k8s/` for teams that want to run on EKS instead |
| Monitoring    | Self-built health-check task + admin alert dashboard + LLM ops chatbot; optional Sentry and Prometheus hooks exist in `main.py` for teams that wire them up |

## Project Structure

```
├── docs/                          # Architecture & strategy documentation
│   ├── 01-PRODUCT-VISION.md
│   ├── 02-SYSTEM-ARCHITECTURE.md
│   ├── 03-CORE-MODULES.md
│   ├── 04-AI-AGENT-ARCHITECTURE.md
│   ├── 05-DATA-MODEL.md
│   ├── 06-API-ARCHITECTURE.md
│   ├── 07-EVENT-WORKFLOWS.md
│   ├── 08-UI-DESIGN.md
│   ├── 09-DEVELOPMENT-PLAN.md
│   ├── 10-SCALING-STRATEGY.md
│   ├── 11-SECURITY-AND-MONITORING.md
│   ├── 12-FUTURE-EXPANSION.md
│   ├── Campaign_Email_Strategy.md     # Email generation + QA rubric design
│   ├── Lead_Enrichment_Strategy.md    # v3 evidence-based scoring design
│   └── remote-deployment-runbook.md   # Production deploy/runbook steps
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app factory
│   │   ├── config.py              # Pydantic settings
│   │   ├── celery_app.py          # Celery configuration
│   │   ├── db/                    # Database engine & base models
│   │   ├── models/                # SQLAlchemy models (tenant, lead, campaign)
│   │   ├── schemas/               # Pydantic request/response schemas
│   │   ├── api/routes/            # API routes (admin, analytics, campaigns, chat, leads, replies, webhooks, …)
│   │   ├── services/              # Business logic (auth, lead, campaign, enrichment)
│   │   ├── agents/                # AI agents — orchestrator, personalization, reply analysis,
│   │   │                          #   legacy signal-based scorer, and the v3/ evidence pipeline
│   │   │                          #   (identity, event_fit, pressure, targeted_research, synthesis, outreach)
│   │   ├── tasks/                 # Celery tasks (orchestrator loop, campaign follow-ups, email send, enrichment)
│   │   ├── middleware/            # Rate limit, tenant, logging
│   │   └── events/               # Redis Streams event bus
│   ├── alembic/                   # Database migrations
│   ├── requirements.txt
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/                   # Next.js App Router pages
│   │   ├── components/            # UI components (layout, dashboard)
│   │   ├── hooks/                 # React Query hooks
│   │   ├── stores/                # Zustand state management
│   │   └── lib/                   # API client, utilities
│   ├── package.json
│   ├── tailwind.config.js
│   └── Dockerfile
├── infra/
│   ├── k8s/                       # Kubernetes manifests
│   │   ├── namespace.yaml
│   │   ├── configmap.yaml
│   │   ├── secrets.yaml
│   │   ├── api.yaml               # Deployment + Service + HPA
│   │   ├── celery.yaml            # Workers + Beat + HPA
│   │   ├── frontend.yaml          # Deployment + Service
│   │   └── ingress.yaml           # TLS + routing
│   └── postgres/
│       └── init.sql               # Extension setup
├── .github/workflows/ci.yml      # CI/CD pipeline
├── docker-compose.yml             # Local development
├── Makefile                       # Developer shortcuts
├── .env.example                   # Environment template
└── .gitignore
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- OpenAI API key (required for AI features)

### 1. Clone & Configure

```bash
git clone <repo-url> outreachai
cd outreachai
cp .env.example .env
# Edit .env with your API keys
```

### 2. Start Services

```bash
make dev
# Or directly:
docker compose up -d
```

This starts 7 services:
- **API** → http://localhost:8000
- **API Docs** → http://localhost:8000/docs
- **Frontend** → http://localhost:3000
- **Flower** (Celery monitor) → http://localhost:5555
- PostgreSQL, Redis (internal)

### 3. Run Migrations

```bash
make migrate
```

### 4. Verify

```bash
curl http://localhost:8000/health
# → {"status": "healthy"}
```

## Development

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Lint
ruff check . && ruff format --check .

# Create migration
alembic revision --autogenerate -m "description"
```

### Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
npm run lint
npm test
```

### Useful Make Targets

```bash
make help            # List all commands
make dev             # Start everything
make stop            # Stop everything
make logs            # Tail all logs
make test            # Run backend tests
make lint-fix        # Auto-fix lint issues
make db-shell        # Open psql
make migrate-create MSG="add table"
```

## API Authentication

All API endpoints (except `/health`, `/api/v1/auth/login`, `/api/v1/auth/register`) require a JWT bearer token:

```bash
# Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "SecurePass123!", "full_name": "Admin", "tenant_name": "My Company"}'

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "SecurePass123!"}'
# → {"access_token": "eyJ...", "refresh_token": "eyJ..."}

# Use token
curl http://localhost:8000/api/v1/leads \
  -H "Authorization: Bearer eyJ..."
```

## Deployment

### Production (current: Docker Compose on a single VPS)

Production runs on a Hetzner VPS via Docker Compose, not Kubernetes:

```bash
ssh -i ~/.ssh/id_ed25519 deploy@<prod-host>
cd /opt/outreachai
git pull origin feat/v3-event-intelligence
docker stop outreachai-api outreachai-celery-worker
docker rm outreachai-api outreachai-celery-worker
docker compose -f docker-compose.prod.yml --env-file .env.prod build api celery-worker
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

Caddy handles the reverse proxy and TLS termination (`Caddyfile`); reload after config changes with:

```bash
docker exec outreachai-caddy caddy reload --config /etc/caddy/Caddyfile
```

Full step-by-step runbook: [docs/remote-deployment-runbook.md](docs/remote-deployment-runbook.md).

### Alternative: Kubernetes

Manifests for an EKS-style deployment are available under `infra/k8s/` if you'd rather run on Kubernetes:

```bash
aws eks update-kubeconfig --name outreachai-prod
kubectl apply -f infra/k8s/
kubectl rollout status deployment/api -n outreachai
```

CI/CD via GitHub Actions builds and tests on every push (`.github/workflows/ci.yml`); deployment itself is currently manual via the Compose flow above.

## Documentation

Architecture and strategy documentation lives in the `docs/` directory:

| Doc | Description |
|-----|-------------|
| [01-PRODUCT-VISION](docs/01-PRODUCT-VISION.md) | Mission, target users, competitive positioning |
| [02-SYSTEM-ARCHITECTURE](docs/02-SYSTEM-ARCHITECTURE.md) | Service topology, data flow, infrastructure |
| [03-CORE-MODULES](docs/03-CORE-MODULES.md) | Module specifications with interfaces |
| [04-AI-AGENT-ARCHITECTURE](docs/04-AI-AGENT-ARCHITECTURE.md) | AI agents, LangGraph graphs & prompts |
| [05-DATA-MODEL](docs/05-DATA-MODEL.md) | Database schema, indexes, RLS |
| [06-API-ARCHITECTURE](docs/06-API-ARCHITECTURE.md) | REST endpoint design |
| [07-EVENT-WORKFLOWS](docs/07-EVENT-WORKFLOWS.md) | Event bus, Celery task flows |
| [08-UI-DESIGN](docs/08-UI-DESIGN.md) | Page layouts and component specs |
| [09-DEVELOPMENT-PLAN](docs/09-DEVELOPMENT-PLAN.md) | Phased roadmap |
| [10-SCALING-STRATEGY](docs/10-SCALING-STRATEGY.md) | DB, cache, worker scaling guides |
| [11-SECURITY-AND-MONITORING](docs/11-SECURITY-AND-MONITORING.md) | Security model, monitoring approach |
| [12-FUTURE-EXPANSION](docs/12-FUTURE-EXPANSION.md) | WhatsApp, LinkedIn, SMS, CRM integrations |
| [Campaign_Email_Strategy](docs/Campaign_Email_Strategy.md) | Email generation flow, QA rubric, CTA design |
| [Lead_Enrichment_Strategy](docs/Lead_Enrichment_Strategy.md) | v3 evidence-based scoring pipeline design |
| [remote-deployment-runbook](docs/remote-deployment-runbook.md) | Production deploy steps for the live VPS |

## License

Proprietary — All rights reserved.
