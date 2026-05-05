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

- **AI Research Agents** — Automated company & contact research via SerpAPI, Firecrawl, Tavily
- **Intelligent Lead Scoring** — 10-signal weighted scoring with hot/warm/cold classification
- **Hyper-Personalized Emails** — GPT-4o generated with Hook→Insight→Value→CTA framework
- **Reply Analysis** — Automatic intent detection (9 categories), sentiment, and suggested responses
- **Multi-Channel Ready** — Email now, extensible to LinkedIn, WhatsApp, SMS
- **Campaign Automation** — Multi-step sequences with scheduling, throttling, and follow-up logic
- **Multi-Tenant** — Row-level security, per-tenant isolation
- **Event-Driven** — Redis Streams event bus with 40+ event types

## Tech Stack

| Layer         | Technology                                             |
|---------------|--------------------------------------------------------|
| Frontend      | Next.js 14, React 18, Tailwind CSS, shadcn/ui, Zustand |
| Backend       | Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2 |
| AI / LLM      | LangChain, LangGraph, GPT-4o, Claude 3.5 Sonnet       |
| Database      | PostgreSQL 16, PGVector (embeddings), pg_trgm          |
| Queue / Cache | Redis 7, Celery 5.4                                   |
| Infrastructure| Docker, Kubernetes (EKS), GitHub Actions CI/CD         |
| Monitoring    | Prometheus, Grafana, Sentry, structlog                 |

## Project Structure

```
├── docs/                          # Architecture documentation (12 files)
│   ├── 01-PRODUCT-VISION.md
│   ├── 02-SYSTEM-ARCHITECTURE.md
│   ├── 03-CORE-MODULES.md
│   ├── 04-AI-AGENTS.md
│   ├── 05-DATABASE-SCHEMA.md
│   ├── 06-API-SPECIFICATION.md
│   ├── 07-EVENT-WORKFLOW-AUTOMATION.md
│   ├── 08-UI-WIREFRAMES.md
│   ├── 09-DEVELOPMENT-PLAN.md
│   ├── 10-SCALING-STRATEGY.md
│   ├── 11-SECURITY-MODEL.md
│   └── 12-FUTURE-EXPANSION.md
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app factory
│   │   ├── config.py              # Pydantic settings
│   │   ├── celery_app.py          # Celery configuration
│   │   ├── db/                    # Database engine & base models
│   │   ├── models/                # SQLAlchemy models (tenant, lead, campaign)
│   │   ├── schemas/               # Pydantic request/response schemas
│   │   ├── api/                   # API routes (10 router modules)
│   │   ├── services/              # Business logic (auth, lead, campaign, enrichment)
│   │   ├── agents/                # AI agents (research, enrichment, scoring, personalization, reply analysis)
│   │   ├── tasks/                 # Celery tasks (enrichment, campaign, email)
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

### Staging / Production (Kubernetes)

```bash
# Configure kubectl for your EKS cluster
aws eks update-kubeconfig --name outreachai-prod

# Apply manifests
kubectl apply -f infra/k8s/

# Check rollout
kubectl rollout status deployment/api -n outreachai
```

CI/CD via GitHub Actions automatically builds, tests, and deploys to staging on merge to `main`.

## Documentation

Comprehensive architecture documentation is in the `docs/` directory:

| Doc | Description |
|-----|-------------|
| [01-PRODUCT-VISION](docs/01-PRODUCT-VISION.md) | Mission, target users, competitive positioning |
| [02-SYSTEM-ARCHITECTURE](docs/02-SYSTEM-ARCHITECTURE.md) | Service topology, data flow, infrastructure |
| [03-CORE-MODULES](docs/03-CORE-MODULES.md) | 19 module specifications with interfaces |
| [04-AI-AGENTS](docs/04-AI-AGENTS.md) | 7 AI agents with LangGraph graphs & prompts |
| [05-DATABASE-SCHEMA](docs/05-DATABASE-SCHEMA.md) | 25+ tables with indexes, RLS, partitioning |
| [06-API-SPECIFICATION](docs/06-API-SPECIFICATION.md) | 100+ REST endpoints with schemas |
| [07-EVENT-WORKFLOW-AUTOMATION](docs/07-EVENT-WORKFLOW-AUTOMATION.md) | Event bus, 40+ events, Celery task flows |
| [08-UI-WIREFRAMES](docs/08-UI-WIREFRAMES.md) | 8 page wireframes with component specs |
| [09-DEVELOPMENT-PLAN](docs/09-DEVELOPMENT-PLAN.md) | 6-phase roadmap (~22 weeks) |
| [10-SCALING-STRATEGY](docs/10-SCALING-STRATEGY.md) | DB, cache, workers, K8s scaling guides |
| [11-SECURITY-MODEL](docs/11-SECURITY-MODEL.md) | 6-layer security, OWASP, JWT RS256 |
| [12-FUTURE-EXPANSION](docs/12-FUTURE-EXPANSION.md) | WhatsApp, LinkedIn, SMS, CRM integrations |

## License

Proprietary — All rights reserved.
