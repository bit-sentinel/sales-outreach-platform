# 11. Security Model

## Security Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                    SECURITY LAYERS                                │
│                                                                  │
│  Layer 1: Edge Security                                          │
│  ├── CloudFlare WAF (DDoS, bot protection)                      │
│  ├── TLS 1.3 (HTTPS everywhere)                                 │
│  ├── Rate limiting (per IP, per tenant)                          │
│  └── CORS whitelist                                              │
│                                                                  │
│  Layer 2: Authentication & Authorization                         │
│  ├── JWT tokens (RS256 signing)                                  │
│  ├── Refresh token rotation                                      │
│  ├── RBAC (owner, admin, manager, member, viewer)               │
│  ├── API key authentication (for programmatic access)           │
│  └── MFA (TOTP, WebAuthn — future)                              │
│                                                                  │
│  Layer 3: Application Security                                   │
│  ├── Input validation (Pydantic schemas on every endpoint)      │
│  ├── SQL injection prevention (SQLAlchemy ORM, parameterized)   │
│  ├── XSS prevention (React auto-escaping, CSP headers)          │
│  ├── CSRF protection (SameSite cookies, CSRF tokens)            │
│  ├── Tenant isolation (RLS, middleware tenant_id check)          │
│  └── File upload validation (type, size, virus scan)            │
│                                                                  │
│  Layer 4: Data Security                                          │
│  ├── Encryption at rest (AWS KMS, RDS encryption)               │
│  ├── Encryption in transit (TLS everywhere)                     │
│  ├── Credential encryption (Fernet / AES-256 for API keys)     │
│  ├── PII handling (email addresses encrypted, masked in logs)   │
│  └── Data retention policies                                    │
│                                                                  │
│  Layer 5: Infrastructure Security                                │
│  ├── VPC isolation (private subnets for DB/cache)               │
│  ├── Security groups (minimal port exposure)                    │
│  ├── Secrets management (AWS Secrets Manager)                   │
│  ├── Container scanning (Trivy, ECR scanning)                   │
│  └── Network policies (Kubernetes)                              │
│                                                                  │
│  Layer 6: Monitoring & Compliance                                │
│  ├── Audit logging (all state changes)                          │
│  ├── Intrusion detection                                        │
│  ├── Dependency vulnerability scanning (Dependabot, Snyk)      │
│  └── SOC2 readiness controls                                    │
└──────────────────────────────────────────────────────────────────┘
```

---

## Authentication Flow

### JWT Implementation

```python
# Access token: short-lived, in Authorization header
# Refresh token: long-lived, in HttpOnly secure cookie

ACCESS_TOKEN_CONFIG = {
    "algorithm": "RS256",         # Asymmetric signing
    "expiry": timedelta(minutes=15),
    "issuer": "outreach-ai",
}

REFRESH_TOKEN_CONFIG = {
    "algorithm": "RS256",
    "expiry": timedelta(days=7),
    "rotation": True,             # New refresh token on each use
    "reuse_detection": True,      # Detect token replay attacks
}
```

### Token Refresh Flow

```
1. Client sends request with expired access token
2. Server returns 401
3. Client sends refresh token (from HttpOnly cookie)
4. Server validates refresh token:
   a. Check not expired
   b. Check not revoked (Redis blacklist)
   c. Check token family (detect reuse)
5. Issue new access token + new refresh token
6. Invalidate old refresh token
7. Return tokens to client
```

### Password Security

```python
# Argon2id hashing (memory-hard, GPU resistant)
from argon2 import PasswordHasher

hasher = PasswordHasher(
    time_cost=3,        # iterations
    memory_cost=65536,  # 64MB
    parallelism=4,
    hash_len=32,
    salt_len=16,
)
```

---

## Multi-Tenant Isolation

### Database Level (PostgreSQL RLS)

```sql
-- Every request sets the tenant context
SET app.current_tenant_id = 'tenant-uuid';

-- RLS policies ensure queries only return tenant's data
CREATE POLICY tenant_isolation ON leads
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

-- Applied to ALL tenant-scoped tables
```

### Application Level (FastAPI Middleware)

```python
class TenantMiddleware:
    """Extract tenant_id from JWT and set on request + DB session."""

    async def __call__(self, request: Request, call_next):
        token_data = get_current_user(request)
        request.state.tenant_id = token_data.tenant_id
        request.state.user_id = token_data.sub

        # Set PostgreSQL session variable for RLS
        async with get_db_session() as session:
            await session.execute(
                text(f"SET app.current_tenant_id = '{token_data.tenant_id}'")
            )

        response = await call_next(request)
        return response
```

### API Key Security

```python
# API keys are generated with crypto-random bytes
# Only the SHA-256 hash is stored; raw key shown once at creation
import secrets
import hashlib

def generate_api_key() -> tuple[str, str]:
    raw_key = f"oai_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:12]
    return raw_key, key_hash, key_prefix
```

---

## Credential Encryption

Email provider credentials (OAuth tokens, API keys) are encrypted at rest:

```python
from cryptography.fernet import Fernet

class CredentialEncryptor:
    """Encrypt/decrypt sensitive credentials stored in database."""

    def __init__(self, encryption_key: str):
        self.fernet = Fernet(encryption_key)  # Key from AWS Secrets Manager

    def encrypt(self, plaintext: str) -> str:
        return self.fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self.fernet.decrypt(ciphertext.encode()).decode()
```

---

## OWASP Top 10 Mitigations

| Risk | Mitigation |
|---|---|
| **A01: Broken Access Control** | RBAC + RLS + tenant isolation middleware |
| **A02: Cryptographic Failures** | AES-256 at rest, TLS 1.3 in transit, Argon2id passwords |
| **A03: Injection** | Pydantic validation, SQLAlchemy ORM (parameterized), no raw SQL |
| **A04: Insecure Design** | Threat modeling, input validation, output encoding |
| **A05: Security Misconfiguration** | Infrastructure-as-code, security headers, no debug in prod |
| **A06: Vulnerable Components** | Dependabot, Snyk scanning, minimal base images |
| **A07: Auth Failures** | JWT RS256, refresh rotation, MFA, account lockout |
| **A08: Data Integrity** | Signed JWTs, HMAC webhook verification, checksum uploads |
| **A09: Logging Failures** | Structured logging, audit trail, PII masking |
| **A10: SSRF** | URL validation for scraping targets, allowlist domains, private IP blocking |

---

## Security Headers

```python
# Applied via FastAPI middleware
SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' wss:",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
```

---

## Data Retention & Compliance

| Data Type | Retention | Justification |
|---|---|---|
| Lead data | Active while tenant exists | Core business data |
| Message content | 2 years | Legal compliance |
| Email events | 1 year | Analytics, then archive to S3 |
| Audit logs | 2 years | Compliance requirement |
| Research data | 6 months | Stale after re-enrichment |
| Session tokens | 7 days | Security best practice |
| API access logs | 90 days | Debugging, security analysis |

### Email Compliance
- **CAN-SPAM**: Unsubscribe link in every email, physical address in footer
- **GDPR**: Data processing consent, right to deletion, data export
- **CCPA**: Opt-out mechanism, data disclosure on request
- Suppression list management (global and per-tenant)

---

## Webhook Security

```python
# All inbound webhooks verified via HMAC signature
import hmac
import hashlib

def verify_sendgrid_webhook(payload: bytes, signature: str, timestamp: str) -> bool:
    """Verify SendGrid Event Webhook signature."""
    expected = hmac.new(
        key=SENDGRID_WEBHOOK_VERIFICATION_KEY.encode(),
        msg=timestamp.encode() + payload,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)  # Constant-time comparison
```

---

# 12. Monitoring & Logging Strategy

## Observability Stack

```
┌──────────────────────────────────────────────────────────────┐
│                    OBSERVABILITY                              │
│                                                              │
│  ┌──────────────────┐                                        │
│  │  Application      │                                        │
│  │  Services         │──── Metrics (Prometheus) ────► Grafana │
│  │                   │──── Logs (structured) ───────► Loki    │
│  │                   │──── Traces (OpenTelemetry) ──► Jaeger  │
│  │                   │──── Errors ──────────────────► Sentry  │
│  └──────────────────┘                                        │
│                                                              │
│  ┌──────────────────┐                                        │
│  │  Infrastructure   │                                        │
│  │  (K8s, RDS, Redis)│──── Metrics ────────────────► Grafana │
│  │                   │──── Health Checks ──────────► PagerDuty│
│  └──────────────────┘                                        │
└──────────────────────────────────────────────────────────────┘
```

## Key Metrics (Prometheus)

### Application Metrics

```python
# Custom Prometheus metrics
from prometheus_client import Counter, Histogram, Gauge

# API metrics
api_requests_total = Counter(
    "api_requests_total",
    "Total API requests",
    ["method", "endpoint", "status_code", "tenant_id"]
)

api_request_duration = Histogram(
    "api_request_duration_seconds",
    "API request duration",
    ["method", "endpoint"],
    buckets=[.01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10]
)

# Lead metrics
leads_total = Gauge("leads_total", "Total leads", ["tenant_id", "stage"])
leads_enriched = Counter("leads_enriched_total", "Leads enriched", ["tenant_id", "status"])

# Campaign metrics
emails_sent_total = Counter("emails_sent_total", "Emails sent", ["tenant_id", "provider", "status"])
emails_opened_total = Counter("emails_opened_total", "Emails opened", ["tenant_id"])
emails_replied_total = Counter("emails_replied_total", "Emails replied", ["tenant_id"])

# AI metrics
ai_agent_duration = Histogram(
    "ai_agent_duration_seconds",
    "AI agent execution time",
    ["agent_name", "model"],
    buckets=[1, 2, 5, 10, 30, 60, 120]
)
ai_tokens_used = Counter("ai_tokens_used_total", "LLM tokens used", ["model", "agent_name", "direction"])
ai_agent_errors = Counter("ai_agent_errors_total", "AI agent failures", ["agent_name", "error_type"])

# Queue metrics
celery_task_duration = Histogram("celery_task_duration_seconds", "Celery task duration", ["task_name"])
celery_queue_length = Gauge("celery_queue_length", "Celery queue depth", ["queue_name"])
```

### Grafana Dashboards

1. **Platform Overview**: Request rate, error rate, latency P50/P95/P99
2. **AI Operations**: Agent execution times, token usage, costs, error rates
3. **Email Delivery**: Send rate, delivery rate, bounce rate, spam rate per provider
4. **Campaign Performance**: Active campaigns, emails in queue, follow-ups pending
5. **Infrastructure**: CPU, memory, disk, network per service
6. **Database**: Connection pool, query latency, replication lag
7. **Redis**: Memory usage, hit rate, key count, pub/sub throughput

---

## Structured Logging

```python
import structlog

logger = structlog.get_logger()

# Standard log format
logger.info(
    "email_sent",
    tenant_id=tenant_id,
    lead_id=lead_id,
    campaign_id=campaign_id,
    provider="sendgrid",
    duration_ms=145,
    # PII fields are masked
    recipient_email="j***@acme.co",
)

# Log output (JSON for Loki ingestion):
{
    "timestamp": "2026-04-06T10:30:00Z",
    "level": "info",
    "event": "email_sent",
    "service": "messaging-service",
    "tenant_id": "abc-123",
    "lead_id": "def-456",
    "campaign_id": "ghi-789",
    "provider": "sendgrid",
    "duration_ms": 145,
    "recipient_email": "j***@acme.co",
    "correlation_id": "trace-001",
    "instance_id": "pod-xyz"
}
```

### PII Masking Rules

| Field | Masking Rule |
|---|---|
| email | First char + `***` + `@domain` |
| phone | Last 4 digits only |
| name | In logs: initials only (J.D.) |
| IP address | Anonymize last octet |
| API keys | First 8 chars only |

---

## Alerting Rules

| Alert | Condition | Severity | Channel |
|---|---|---|---|
| API Error Rate > 5% | 5xx rate > 5% for 5 min | Critical | PagerDuty + Slack |
| API Latency P99 > 5s | P99 > 5s for 10 min | Warning | Slack |
| Email Bounce Rate > 5% | Per provider, 1 hour window | Critical | Slack + Email |
| Email Spam Rate > 0.5% | Per provider, 1 hour window | Critical | PagerDuty |
| Celery Queue Depth > 10,000 | Any queue, sustained 15 min | Warning | Slack |
| AI Agent Error Rate > 10% | Per agent, 30 min window | Warning | Slack |
| Database CPU > 80% | Sustained 10 min | Warning | Slack |
| Database Connections > 80% | Pool utilization | Critical | PagerDuty |
| Redis Memory > 80% | Memory usage | Warning | Slack |
| Disk Usage > 85% | Any volume | Warning | Slack |
| SSL Certificate Expiry < 30d | Certificate check | Warning | Email |

---

## Health Checks

```python
# /health endpoint for Kubernetes probes
@router.get("/health")
async def health_check():
    checks = {
        "database": await check_database(),
        "redis": await check_redis(),
        "celery": await check_celery(),
    }
    all_healthy = all(c["status"] == "ok" for c in checks.values())
    return {
        "status": "healthy" if all_healthy else "degraded",
        "checks": checks,
        "version": APP_VERSION,
        "uptime": get_uptime(),
    }

# Kubernetes probes
# Liveness:  GET /health (checks if process is running)
# Readiness: GET /health (checks if can serve traffic)
# Startup:   GET /health (initial startup check, 60s timeout)
```
