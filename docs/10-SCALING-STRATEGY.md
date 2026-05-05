# 10. Scaling Strategy

## Scale Targets

| Phase | Leads | Users | Emails/Day | AI Enrichments/Day |
|---|---|---|---|---|
| MVP (V1) | 10,000 | 5 | 1,000 | 500 |
| Growth (V2) | 100,000 | 500 | 50,000 | 10,000 |
| Scale (V3) | 1,000,000 | 100,000+ | 1,000,000 | 100,000 |

---

## Database Scaling

### Phase 1: Single PostgreSQL (10k-100k leads)
- **RDS db.r6g.large** (2 vCPU, 16GB RAM)
- Connection pooling via **PgBouncer** (max 200 connections)
- Read replicas for analytics queries
- Materialized views refreshed every 15 minutes
- Indexes optimized for common query patterns

### Phase 2: Read Replicas + Partitioning (100k-1M leads)
- **RDS db.r6g.2xlarge** primary (8 vCPU, 64GB RAM)
- 2 read replicas for dashboard/analytics queries
- Table partitioning for:
  - `email_events` (monthly partitions)
  - `messages` (monthly partitions)
  - `lead_activities` (monthly partitions)
  - `audit_logs` (monthly partitions, auto-drop after 2 years)
- Connection routing: writes → primary, reads → replica pool

```sql
-- Example: Partitioning email_events
CREATE TABLE email_events (
    ...
) PARTITION BY RANGE (created_at);

CREATE TABLE email_events_2026_01 PARTITION OF email_events
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
CREATE TABLE email_events_2026_02 PARTITION OF email_events
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
-- Auto-create future partitions via pg_partman
```

### Phase 3: Sharding + Elasticsearch (1M+ leads)
- **Tenant-based sharding** (each large tenant gets dedicated schema/database)
- **Citus** extension for distributed PostgreSQL (or migrate to CockroachDB)
- **Elasticsearch** for lead search, replacing PostgreSQL full-text search
- Separate analytics database (read-optimized, columnar — TimescaleDB or ClickHouse)
- Archive old data to S3 (email_events older than 1 year)

---

## Caching Strategy

### Layer 1: Application Cache (Redis)

```python
CACHE_KEYS = {
    # Dashboard metrics (refreshed every 5 min)
    "dashboard:{tenant_id}": TTL(300),

    # Lead scores (refreshed on rescore)
    "lead_score:{lead_id}": TTL(3600),

    # Campaign metrics (refreshed on event)
    "campaign_metrics:{campaign_id}": TTL(300),

    # User sessions
    "session:{user_id}": TTL(900),

    # Rate limiting
    "rate_limit:{tenant_id}:{endpoint}": TTL(60),

    # Enrichment cache (reuse for same domain)
    "enrichment_cache:{domain}": TTL(2592000),  # 30 days
}
```

### Layer 2: CDN Cache (CloudFlare)
- Static assets: 7 day cache
- API responses: no-cache (dynamic)
- Tracking pixel: edge-served (no origin hit)
- Click redirect: edge-served → redirect → log async

### Layer 3: Query Cache (PostgreSQL)
- Materialized views for expensive aggregations
- Prepared statements for frequent queries
- Connection pooling with PgBouncer

---

## Celery Worker Scaling

### Queue Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Celery Queues                                               │
│                                                              │
│  ┌──────────────┐  Workers: 4   Concurrency: 5              │
│  │  enrichment  │  Rate: 30/min  Memory: 1GB per worker     │
│  │  queue       │  CPU-bound (LLM calls)                    │
│  └──────────────┘                                            │
│                                                              │
│  ┌──────────────┐  Workers: 2   Concurrency: 20             │
│  │  messaging   │  Rate: 50/min  Memory: 512MB per worker   │
│  │  queue       │  IO-bound (API calls)                     │
│  └──────────────┘                                            │
│                                                              │
│  ┌──────────────┐  Workers: 2   Concurrency: 10             │
│  │  ai          │  Rate: 20/min  Memory: 1GB per worker     │
│  │  queue       │  CPU-bound (LLM calls)                    │
│  └──────────────┘                                            │
│                                                              │
│  ┌──────────────┐  Workers: 2   Concurrency: 10             │
│  │  scoring     │  Rate: 60/min  Memory: 512MB per worker   │
│  │  queue       │  Light compute                             │
│  └──────────────┘                                            │
│                                                              │
│  ┌──────────────┐  Workers: 1   Concurrency: 5              │
│  │  analytics   │  Rate: 30/min  Memory: 1GB per worker     │
│  │  queue       │  Aggregation queries                       │
│  └──────────────┘                                            │
│                                                              │
│  ┌──────────────┐  Workers: 1   Beat scheduler               │
│  │  scheduler   │  Runs cron jobs                            │
│  │  (beat)      │  Single instance only                      │
│  └──────────────┘                                            │
└─────────────────────────────────────────────────────────────┘
```

### Scaling Worker Counts

| Load Level | Enrichment | Messaging | AI | Scoring | Analytics |
|---|---|---|---|---|---|
| Low (1k leads) | 2 | 1 | 1 | 1 | 1 |
| Medium (50k leads) | 4 | 2 | 2 | 2 | 1 |
| High (500k leads) | 8 | 4 | 4 | 2 | 2 |
| Very High (1M+) | 16 | 8 | 8 | 4 | 4 |

### Kubernetes HPA (Horizontal Pod Autoscaler)

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: enrichment-worker-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: enrichment-worker
  minReplicas: 2
  maxReplicas: 16
  metrics:
    - type: External
      external:
        metric:
          name: celery_queue_length
          selector:
            matchLabels:
              queue: enrichment
        target:
          type: AverageValue
          averageValue: "100"  # Scale up when > 100 pending tasks
```

---

## API Gateway Scaling

### Load Balancer
- **AWS ALB** with path-based routing
- Health check: `/health` endpoint
- Connection draining: 30 seconds
- Sticky sessions: disabled (stateless JWT)

### API Service Scaling

| Scale Level | Instances | CPU | Memory | Req/sec |
|---|---|---|---|---|
| Low | 2 | 1 vCPU | 1GB | 100 |
| Medium | 4 | 2 vCPU | 2GB | 500 |
| High | 8 | 4 vCPU | 4GB | 2,000 |
| Very High | 20 | 4 vCPU | 4GB | 10,000 |

---

## Email Deliverability Scaling Strategy

### Domain Warming Schedule

```
Day 1-3:    20 emails/day per domain
Day 4-7:    50 emails/day
Day 8-14:   100 emails/day
Day 15-21:  200 emails/day
Day 22-28:  500 emails/day
Day 29+:    1000 emails/day (max per domain)
```

### Multi-Domain Strategy (for 100k+ emails/month)

```
┌────────────────────────────────────────────┐
│  Email Domain Pool                          │
│                                            │
│  outreach.consultfirm.com    → 1000/day    │
│  hello.consultfirm.com       → 1000/day    │
│  team.consultfirm.com        → 1000/day    │
│  sales.consultfirm.com       → 1000/day    │
│  connect.consultfirm.com     → 1000/day    │
│                                            │
│  Total daily capacity: 5000 emails/day     │
│  Monthly capacity: ~100k-150k emails       │
└────────────────────────────────────────────┘
```

### Provider Distribution

```
Primary:   SendGrid (60% of volume) — best deliverability analytics
Secondary: Amazon SES (30% of volume) — lowest cost
Fallback:  Gmail API (10% of volume) — highest trust, personal feel
```

### IP Reputation Management
- Dedicated IPs for high-volume senders (SendGrid dedicated IP add-on)
- IP warmup over 30 days
- Monitor blacklists (MXToolbox, Spamhaus)
- Maintain bounce rate < 2%
- Maintain spam complaint rate < 0.1%
- Automatic suppression of bounced/spam-reported emails
- Regular list hygiene (verify emails before campaigns)

---

## AI/LLM Scaling

### Cost Optimization at Scale

| Volume | Strategy | Estimated Monthly Cost |
|---|---|---|
| 10k leads | GPT-4o for all agents | $1,300 |
| 100k leads | GPT-4o-mini for scoring/enrichment, GPT-4o for personalization | $5,000 |
| 1M leads | Fine-tuned GPT-4o-mini + cache layer + batch API | $20,000 |

### Optimization Techniques

1. **Response caching**: Cache enrichment for same company domain (30-day TTL)
2. **Batch API**: Use OpenAI Batch API for non-urgent enrichments (50% discount)
3. **Model routing**: Use cheaper models for simple tasks (scoring → gpt-4o-mini)
4. **Prompt optimization**: Minimize token usage with concise prompts
5. **Embedding cache**: Cache embeddings, regenerate only on data change
6. **Incremental enrichment**: Only re-enrich changed/stale data
7. **Fine-tuning**: Fine-tune smaller models on high-quality outputs (V3+)

### Rate Limit Management

```python
# Token bucket rate limiter per provider
class LLMRateLimiter:
    def __init__(self):
        self.limiters = {
            "openai/gpt-4o": TokenBucket(rpm=500, tpm=800000),
            "openai/gpt-4o-mini": TokenBucket(rpm=1000, tpm=2000000),
            "anthropic/claude-sonnet": TokenBucket(rpm=400, tpm=400000),
        }

    async def acquire(self, model: str, estimated_tokens: int):
        limiter = self.limiters[model]
        await limiter.wait_for_capacity(estimated_tokens)
```

---

## Kubernetes Architecture (Production)

```yaml
# Namespace: outreach-ai
apiVersion: v1
kind: Namespace
metadata:
  name: outreach-ai

# Services deployed:
# - api-gateway (Deployment, 2-8 replicas)
# - frontend (Deployment, 2-4 replicas)
# - enrichment-worker (Deployment, 2-16 replicas)
# - messaging-worker (Deployment, 1-8 replicas)
# - ai-worker (Deployment, 1-8 replicas)
# - scoring-worker (Deployment, 1-4 replicas)
# - analytics-worker (Deployment, 1-4 replicas)
# - scheduler (Deployment, 1 replica — singleton)
# - notification-service (Deployment, 1-2 replicas)

# Infrastructure (managed):
# - RDS PostgreSQL (db.r6g.xlarge → 2xlarge)
# - ElastiCache Redis (cache.r6g.large)
# - S3 bucket (uploads, exports)
# - CloudFront (CDN for frontend)
# - ALB (load balancer)
# - Route 53 (DNS)
```

## Cost Estimate (AWS)

### MVP (10k leads, 5 users)

| Resource | Spec | Monthly Cost |
|---|---|---|
| EKS Cluster | 1 cluster | $75 |
| EC2 (3 nodes) | t3.large | $190 |
| RDS PostgreSQL | db.t3.large | $150 |
| ElastiCache Redis | cache.t3.medium | $65 |
| S3 | 50 GB | $5 |
| ALB | 1 LB | $25 |
| Route 53 | 1 hosted zone | $5 |
| AI (OpenAI) | 10k enrichments | $1,300 |
| External APIs | SerpAPI, Firecrawl | $700 |
| SendGrid | Pro plan | $90 |
| **Total** | | **~$2,600/mo** |

### Growth (100k leads, 500 users)

| Resource | Spec | Monthly Cost |
|---|---|---|
| EKS Cluster | 1 cluster | $75 |
| EC2 (8 nodes) | c6g.xlarge | $900 |
| RDS PostgreSQL | db.r6g.2xlarge + replica | $800 |
| ElastiCache Redis | cache.r6g.large | $250 |
| S3 | 500 GB | $15 |
| CloudFront | 100 GB transfer | $25 |
| ALB | 1 LB | $50 |
| AI (OpenAI) | 100k enrichments batch | $5,000 |
| External APIs | All providers | $3,500 |
| SendGrid | Premier plan | $300 |
| **Total** | | **~$11,000/mo** |
