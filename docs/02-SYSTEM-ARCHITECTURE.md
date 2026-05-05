# 2. System Architecture

## High-Level Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                          OUTREACH AI PLATFORM                                    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────────┐  │
│  │                        PRESENTATION LAYER                                   │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  ┌───────────────┐   │  │
│  │  │  Dashboard    │  │  Campaign    │  │  Lead Mgmt  │  │  Analytics    │   │  │
│  │  │  (Next.js)   │  │  Builder     │  │  Views      │  │  & Reports   │   │  │
│  │  └──────────────┘  └──────────────┘  └─────────────┘  └───────────────┘   │  │
│  └─────────────────────────────────────────────────────────────────────────────┘  │
│                                    │                                              │
│                          ┌─────────▼──────────┐                                  │
│                          │    API GATEWAY      │                                  │
│                          │   (FastAPI + Auth)  │                                  │
│                          └─────────┬──────────┘                                  │
│                                    │                                              │
│  ┌─────────────────────────────────┼─────────────────────────────────────────┐   │
│  │                     SERVICE MESH (Internal APIs)                           │   │
│  │                                                                           │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │   │
│  │  │ Lead Service  │  │ Enrichment   │  │  Campaign    │  │  Messaging   │  │   │
│  │  │              │  │  Service     │  │  Service     │  │  Service     │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘  │   │
│  │                                                                           │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │   │
│  │  │  Scoring     │  │  Reply       │  │  Analytics   │  │  Notification│  │   │
│  │  │  Service     │  │  Service     │  │  Service     │  │  Service     │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘  │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│  ┌─────────────────────────────────┼─────────────────────────────────────────┐   │
│  │                     AI AGENT LAYER                                         │   │
│  │                                                                           │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │   │
│  │  │  Research    │  │  Enrichment  │  │  Scoring     │  │  Personal-   │  │   │
│  │  │  Agent       │  │  Agent       │  │  Agent       │  │  ization Agt │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘  │   │
│  │                                                                           │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                    │   │
│  │  │  Insight     │  │  Reply       │  │  Response    │                    │   │
│  │  │  Agent       │  │  Analysis Agt│  │  Gen Agent   │                    │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘                    │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│  ┌─────────────────────────────────┼─────────────────────────────────────────┐   │
│  │                     EVENT BUS & QUEUE LAYER                                │   │
│  │           ┌─────────────────────────────────────────┐                     │   │
│  │           │  Redis Streams + Celery Workers         │                     │   │
│  │           │  (Event Bus / Task Queue / Pub-Sub)     │                     │   │
│  │           └─────────────────────────────────────────┘                     │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│  ┌─────────────────────────────────┼─────────────────────────────────────────┐   │
│  │                     DATA LAYER                                             │   │
│  │                                                                           │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │   │
│  │  │ PostgreSQL   │  │  PGVector    │  │  Redis       │  │  S3/MinIO    │  │   │
│  │  │ (Primary DB) │  │ (Embeddings) │  │  (Cache)     │  │  (Files)     │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘  │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                              │
│  ┌─────────────────────────────────┼─────────────────────────────────────────┐   │
│  │                     EXTERNAL INTEGRATIONS                                  │   │
│  │                                                                           │   │
│  │  ┌─────────┐ ┌─────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌─────────┐  │   │
│  │  │Gmail API│ │SendGrid │ │SerpAPI │ │Firecrawl│ │Tavily  │ │OpenAI / │  │   │
│  │  │         │ │/ SES    │ │        │ │        │ │        │ │Anthropic│  │   │
│  │  └─────────┘ └─────────┘ └────────┘ └────────┘ └────────┘ └─────────┘  │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

## Microservices Architecture

### Service Decomposition

| Service | Responsibility | Port | Technology |
|---|---|---|---|
| **api-gateway** | Authentication, routing, rate limiting | 8000 | FastAPI |
| **lead-service** | Lead CRUD, import, export, pipeline | 8001 | FastAPI |
| **enrichment-service** | Web research, data enrichment orchestration | 8002 | FastAPI + Celery |
| **scoring-service** | Lead scoring, ranking, segmentation | 8003 | FastAPI |
| **campaign-service** | Campaign CRUD, scheduling, sequencing | 8004 | FastAPI |
| **messaging-service** | Channel abstraction, message dispatch | 8005 | FastAPI + Celery |
| **reply-service** | Reply detection, AI analysis, response gen | 8006 | FastAPI + Celery |
| **analytics-service** | Metrics aggregation, reporting | 8007 | FastAPI |
| **notification-service** | Real-time notifications, webhooks | 8008 | FastAPI + WebSocket |
| **scheduler-service** | Follow-up scheduling, cron jobs | 8009 | Celery Beat + Temporal |
| **ai-orchestrator** | AI agent coordination, LLM management | 8010 | FastAPI + LangChain |

### Inter-Service Communication

```
┌─────────────────────────────────────────────────────────┐
│                COMMUNICATION PATTERNS                    │
│                                                         │
│  Synchronous (Request/Response):                        │
│  ├── REST APIs (service-to-service via internal mesh)   │
│  └── gRPC (future: high-throughput internal calls)      │
│                                                         │
│  Asynchronous (Event-Driven):                           │
│  ├── Redis Streams (event bus)                          │
│  ├── Celery Tasks (background processing)               │
│  └── WebSocket (real-time UI updates)                   │
│                                                         │
│  Event Flow:                                            │
│  lead.created ──► enrichment-service                    │
│  lead.enriched ──► scoring-service                      │
│  lead.scored ──► campaign-service (auto-segment)        │
│  campaign.launched ──► messaging-service                 │
│  message.sent ──► analytics-service                     │
│  message.delivered ──► analytics-service                 │
│  reply.received ──► reply-service                       │
│  reply.analyzed ──► notification-service                 │
│  followup.due ──► messaging-service                     │
└─────────────────────────────────────────────────────────┘
```

### Service Interaction Diagram

```
                    ┌──────────┐
                    │  Client  │
                    │ (Next.js)│
                    └────┬─────┘
                         │ HTTPS
                    ┌────▼─────┐
                    │   API    │
                    │ Gateway  │◄──── JWT Auth + Rate Limit
                    └────┬─────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
   ┌────▼────┐     ┌────▼─────┐    ┌────▼──────┐
   │  Lead   │     │ Campaign │    │ Analytics │
   │ Service │     │ Service  │    │  Service  │
   └────┬────┘     └────┬─────┘    └───────────┘
        │               │
   ┌────▼────────┐ ┌───▼──────────┐
   │ Enrichment  │ │  Messaging   │
   │  Service    │ │  Service     │
   └─────┬───────┘ └──────┬───────┘
         │                 │
   ┌─────▼───────┐   ┌───▼───────┐
   │ AI Orchestr │   │  Email    │
   │ (LangChain) │   │  Provider │
   └─────┬───────┘   └───────────┘
         │
   ┌─────▼───────┐
   │  External   │
   │  APIs       │
   │ (Firecrawl, │
   │  SerpAPI,   │
   │  Tavily)    │
   └─────────────┘
```

## Technology Stack Detail

### Backend Layer

| Component | Technology | Justification |
|---|---|---|
| API Framework | **FastAPI** (Python 3.12+) | Async-first, auto-docs, Pydantic validation, fastest Python framework |
| Task Queue | **Celery 5.x** + Redis broker | Battle-tested, distributed task execution, retries, rate limiting |
| Event Bus | **Redis Streams** | Lightweight pub/sub, consumer groups, persistence |
| Workflow Engine | **Temporal** (future) | Complex multi-step workflows with durable execution |
| ORM | **SQLAlchemy 2.0** + Alembic | Async ORM, migration management |
| Validation | **Pydantic v2** | Schema validation, serialization, LLM structured outputs |

### AI Layer

| Component | Technology | Justification |
|---|---|---|
| LLM Orchestration | **LangChain** + **LangGraph** | Agent graphs, tool calling, memory, structured outputs |
| Primary LLM | **GPT-4o** (OpenAI) | Best reasoning, function calling, structured outputs |
| Fallback LLM | **Claude 3.5 Sonnet** (Anthropic) | Redundancy, long-context analysis |
| Embeddings | **text-embedding-3-small** (OpenAI) | Vector similarity for lead matching, deduplication |
| Vector Store | **PGVector** (PostgreSQL extension) | Co-located with primary DB, no extra infra |
| Agent Framework | **LangGraph** | Stateful agent graphs with tool nodes |

### Data Layer

| Component | Technology | Justification |
|---|---|---|
| Primary Database | **PostgreSQL 16** | ACID, JSON support, PGVector extension, battle-tested |
| Vector Storage | **PGVector** extension | Embeddings co-located, no extra infrastructure |
| Cache | **Redis 7** | Session cache, rate limiting, pub/sub, task broker |
| Object Storage | **AWS S3** / MinIO (local) | CSV uploads, attachments, exports |
| Search | **PostgreSQL Full-Text Search** (v1), **Elasticsearch** (v2) | Lead search, analytics |

### Frontend Layer

| Component | Technology | Justification |
|---|---|---|
| Framework | **Next.js 14** (App Router) | SSR, API routes, file-based routing, React Server Components |
| UI Library | **React 18** | Component model, hooks, concurrent rendering |
| Styling | **Tailwind CSS** + **shadcn/ui** | Utility-first, enterprise component library |
| State Management | **Zustand** + **TanStack Query** | Lightweight global state + server state caching |
| Charts | **Recharts** / **Tremor** | Dashboard visualizations |
| Tables | **TanStack Table** | Advanced data grids for lead management |
| Real-time | **Socket.IO** client | Live notifications, inbox updates |
| Forms | **React Hook Form** + **Zod** | Type-safe form validation |

### Infrastructure

| Component | Technology | Justification |
|---|---|---|
| Containers | **Docker** + Docker Compose | Local dev, CI/CD, deployment consistency |
| Orchestration | **Kubernetes** (EKS) | Production scaling, service mesh, auto-scaling |
| CI/CD | **GitHub Actions** | Automated testing, building, deployment |
| Monitoring | **Prometheus** + **Grafana** | Metrics collection, dashboarding |
| Logging | **Loki** + **Grafana** | Centralized log aggregation |
| Tracing | **OpenTelemetry** + **Jaeger** | Distributed tracing across services |
| DNS/CDN | **CloudFlare** | Edge caching, DDoS protection, SSL |
| Secrets | **AWS Secrets Manager** / Vault | Credential management |

## Network Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                        AWS VPC                                  │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Public Subnet                                          │   │
│  │  ┌────────────┐  ┌──────────────┐  ┌────────────────┐  │   │
│  │  │ ALB / NLB  │  │ CloudFront   │  │ NAT Gateway    │  │   │
│  │  │            │  │ (CDN)        │  │                │  │   │
│  │  └──────┬─────┘  └──────────────┘  └────────────────┘  │   │
│  └─────────┼───────────────────────────────────────────────┘   │
│            │                                                    │
│  ┌─────────┼───────────────────────────────────────────────┐   │
│  │  Private Subnet (Application)                           │   │
│  │         │                                               │   │
│  │  ┌──────▼─────────────────────────────────────────┐    │   │
│  │  │         EKS Cluster (Kubernetes)                │    │   │
│  │  │                                                 │    │   │
│  │  │  ┌─────────┐ ┌─────────┐ ┌─────────┐          │    │   │
│  │  │  │ API GW  │ │ Workers │ │ Frontend│          │    │   │
│  │  │  │ Pods    │ │ Pods    │ │ Pods    │          │    │   │
│  │  │  └─────────┘ └─────────┘ └─────────┘          │    │   │
│  │  └─────────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Private Subnet (Data)                                  │   │
│  │  ┌──────────┐  ┌──────────┐  ┌───────────────────┐    │   │
│  │  │ RDS      │  │ ElastiCa │  │ S3 Gateway        │    │   │
│  │  │ (Postgres)│  │ (Redis)  │  │ Endpoint          │    │   │
│  │  └──────────┘  └──────────┘  └───────────────────┘    │   │
│  └─────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────┘
```

## Request Lifecycle Example

### "User uploads 1000 leads and launches a campaign"

```
1. Client ──POST /api/v1/leads/import──► API Gateway
2. API Gateway ──validates JWT──► Lead Service
3. Lead Service ──parses CSV──► PostgreSQL (bulk insert)
4. Lead Service ──emits event──► Redis: "leads.batch_created" {batch_id, count: 1000}
5. Enrichment Service ──consumes event──► Spawns 1000 Celery tasks
6. Each Celery task:
   a. Research Agent ──queries──► Firecrawl, SerpAPI, Tavily
   b. Enrichment Agent ──extracts──► Structured company data
   c. Insight Agent ──analyzes──► AI insights, signals
   d. ──stores──► PostgreSQL (enrichment_data, ai_insights)
   e. ──emits──► "lead.enriched" {lead_id}
7. Scoring Service ──consumes "lead.enriched"──► Scoring Agent
8. Scoring Agent ──calculates score──► PostgreSQL (lead_scores)
9. ──emits──► "lead.scored" {lead_id, score, tier}
10. User ──POST /api/v1/campaigns──► Campaign Service (create campaign)
11. User ──POST /api/v1/campaigns/{id}/launch──► Campaign Service
12. Campaign Service ──for each lead──►
    a. Personalization Agent ──generates email──► stores draft
    b. ──emits──► "message.ready" {message_id}
13. Messaging Service ──consumes "message.ready"──►
    a. ──resolves channel──► Email Delivery Service
    b. ──sends via──► SendGrid / Gmail API / SES
    c. ──emits──► "message.sent" {message_id, provider_id}
14. Analytics Service ──records──► email_events table
15. Scheduler Service ──schedules──► follow-up in 7 days
16. Webhook ──receives open/click──► Analytics Service
17. Reply Listener ──detects reply──► Reply Service
18. Reply Analysis Agent ──analyzes──► intent, summary
19. Notification Service ──pushes──► WebSocket to UI
```
