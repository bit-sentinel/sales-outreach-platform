# 5. Data Model — Complete Database Schema

## Entity Relationship Overview

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│    Tenant    │────▶│     User     │────▶│   Permission     │
└──────┬───────┘     └──────┬───────┘     └──────────────────┘
       │                    │
       │              ┌─────▼──────┐
       │              │   Team     │
       │              └────────────┘
       │
       ├──────────────────────────────────────────────────────┐
       │                                                      │
┌──────▼───────┐     ┌──────────────┐     ┌──────────────────▼┐
│   Company    │◀───▶│   Contact    │◀───▶│      Lead         │
└──────┬───────┘     └──────────────┘     └──────┬────────────┘
       │                                         │
┌──────▼───────┐     ┌──────────────┐     ┌──────▼────────────┐
│ Enrichment   │     │  AI Insight  │     │   Lead Score      │
│    Data      │     │              │     │                   │
└──────────────┘     └──────────────┘     └───────────────────┘
                                                 │
                                          ┌──────▼────────────┐
                                          │    Campaign       │
                                          └──────┬────────────┘
                                                 │
                                          ┌──────▼────────────┐
                                          │ Campaign Lead     │
                                          └──────┬────────────┘
                                                 │
                                          ┌──────▼────────────┐
                                          │    Message        │
                                          └──────┬────────────┘
                                                 │
                            ┌────────────────────┼────────────────────┐
                            │                    │                    │
                     ┌──────▼──────┐     ┌──────▼──────┐     ┌──────▼──────┐
                     │ Email Event │     │  Follow-up  │     │   Reply     │
                     └─────────────┘     └─────────────┘     └─────────────┘
```

---

## Complete SQL Schema

```sql
-- ============================================================================
-- OUTREACH AI PLATFORM — DATABASE SCHEMA
-- PostgreSQL 16 + PGVector Extension
-- ============================================================================

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- fuzzy text search

-- ============================================================================
-- MULTI-TENANCY & USER MANAGEMENT
-- ============================================================================

CREATE TABLE tenants (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(255) NOT NULL,
    slug            VARCHAR(100) NOT NULL UNIQUE,
    domain          VARCHAR(255),
    logo_url        TEXT,
    settings        JSONB NOT NULL DEFAULT '{}',
    subscription_tier VARCHAR(50) NOT NULL DEFAULT 'starter',  -- starter, pro, enterprise
    subscription_status VARCHAR(50) NOT NULL DEFAULT 'active', -- active, trial, suspended, cancelled
    trial_ends_at   TIMESTAMPTZ,
    max_leads       INTEGER NOT NULL DEFAULT 10000,
    max_users       INTEGER NOT NULL DEFAULT 5,
    max_campaigns_per_month INTEGER NOT NULL DEFAULT 50,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email           VARCHAR(320) NOT NULL,
    password_hash   TEXT NOT NULL,
    first_name      VARCHAR(100),
    last_name       VARCHAR(100),
    avatar_url      TEXT,
    role            VARCHAR(50) NOT NULL DEFAULT 'member',  -- owner, admin, manager, member, viewer
    is_active       BOOLEAN NOT NULL DEFAULT true,
    last_login_at   TIMESTAMPTZ,
    email_verified  BOOLEAN NOT NULL DEFAULT false,
    mfa_enabled     BOOLEAN NOT NULL DEFAULT false,
    mfa_secret      TEXT,
    preferences     JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, email)
);

CREATE TABLE teams (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE team_members (
    team_id         UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role            VARCHAR(50) NOT NULL DEFAULT 'member',  -- lead, member
    joined_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (team_id, user_id)
);

CREATE TABLE permissions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    role            VARCHAR(50) NOT NULL,
    resource        VARCHAR(100) NOT NULL,  -- leads, campaigns, analytics, admin, settings
    action          VARCHAR(50) NOT NULL,   -- create, read, update, delete, export, launch
    allowed         BOOLEAN NOT NULL DEFAULT true,
    UNIQUE(role, resource, action)
);

-- Seed default permissions
INSERT INTO permissions (role, resource, action, allowed) VALUES
    ('owner', 'leads', 'create', true),
    ('owner', 'leads', 'read', true),
    ('owner', 'leads', 'update', true),
    ('owner', 'leads', 'delete', true),
    ('owner', 'leads', 'export', true),
    ('owner', 'campaigns', 'create', true),
    ('owner', 'campaigns', 'read', true),
    ('owner', 'campaigns', 'launch', true),
    ('owner', 'campaigns', 'delete', true),
    ('owner', 'analytics', 'read', true),
    ('owner', 'admin', 'read', true),
    ('owner', 'admin', 'update', true),
    ('owner', 'settings', 'read', true),
    ('owner', 'settings', 'update', true),
    ('admin', 'leads', 'create', true),
    ('admin', 'leads', 'read', true),
    ('admin', 'leads', 'update', true),
    ('admin', 'leads', 'delete', true),
    ('admin', 'leads', 'export', true),
    ('admin', 'campaigns', 'create', true),
    ('admin', 'campaigns', 'read', true),
    ('admin', 'campaigns', 'launch', true),
    ('admin', 'analytics', 'read', true),
    ('admin', 'settings', 'read', true),
    ('manager', 'leads', 'create', true),
    ('manager', 'leads', 'read', true),
    ('manager', 'leads', 'update', true),
    ('manager', 'leads', 'export', true),
    ('manager', 'campaigns', 'create', true),
    ('manager', 'campaigns', 'read', true),
    ('manager', 'campaigns', 'launch', true),
    ('manager', 'analytics', 'read', true),
    ('member', 'leads', 'read', true),
    ('member', 'leads', 'update', true),
    ('member', 'campaigns', 'read', true),
    ('member', 'analytics', 'read', true),
    ('viewer', 'leads', 'read', true),
    ('viewer', 'campaigns', 'read', true),
    ('viewer', 'analytics', 'read', true);

CREATE TABLE api_keys (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    key_hash        TEXT NOT NULL,  -- SHA-256 of the key; raw key shown only once
    key_prefix      VARCHAR(10) NOT NULL,  -- first 8 chars for identification
    scopes          TEXT[] NOT NULL DEFAULT '{}',
    last_used_at    TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Audit log for compliance
CREATE TABLE audit_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    action          VARCHAR(100) NOT NULL,
    resource_type   VARCHAR(100) NOT NULL,
    resource_id     UUID,
    old_value       JSONB,
    new_value       JSONB,
    ip_address      INET,
    user_agent      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- COMPANIES & CONTACTS
-- ============================================================================

CREATE TABLE companies (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name            VARCHAR(500) NOT NULL,
    domain          VARCHAR(255),
    website         TEXT,
    industry        VARCHAR(255),
    sub_industry    VARCHAR(255),
    size_range      VARCHAR(50),   -- 1-10, 11-50, 51-200, 201-500, 501-1000, 1000+
    employee_count  INTEGER,
    annual_revenue_range VARCHAR(100),
    category        VARCHAR(100),  -- enterprise, sme, startup, ngo, nonprofit, government
    funding_total   BIGINT,        -- in cents/smallest currency unit
    funding_stage   VARCHAR(50),   -- seed, series_a, series_b, ..., public, bootstrapped
    latest_funding_date DATE,
    headquarters    VARCHAR(500),
    city            VARCHAR(255),
    state           VARCHAR(255),
    country         VARCHAR(100),
    description     TEXT,
    logo_url        TEXT,
    linkedin_url    TEXT,
    twitter_url     TEXT,
    tech_stack      TEXT[],
    tags            TEXT[] NOT NULL DEFAULT '{}',
    custom_fields   JSONB NOT NULL DEFAULT '{}',
    -- Deduplication
    domain_normalized VARCHAR(255),
    name_normalized   VARCHAR(500),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_companies_tenant ON companies(tenant_id);
CREATE INDEX idx_companies_domain ON companies(tenant_id, domain_normalized);
CREATE INDEX idx_companies_name_trgm ON companies USING gin(name_normalized gin_trgm_ops);
CREATE INDEX idx_companies_tags ON companies USING gin(tags);
CREATE INDEX idx_companies_industry ON companies(tenant_id, industry);

CREATE TABLE contacts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    company_id      UUID REFERENCES companies(id) ON DELETE SET NULL,
    email           VARCHAR(320) NOT NULL,
    first_name      VARCHAR(100),
    last_name       VARCHAR(100),
    full_name       VARCHAR(255),
    title           VARCHAR(255),
    department      VARCHAR(255),
    phone           VARCHAR(50),
    linkedin_url    TEXT,
    location        VARCHAR(500),
    seniority_level VARCHAR(50),  -- c_level, vp, director, manager, contributor, intern
    email_verified  BOOLEAN DEFAULT false,
    email_status    VARCHAR(50) DEFAULT 'unknown',  -- valid, invalid, catch_all, unknown
    tags            TEXT[] NOT NULL DEFAULT '{}',
    custom_fields   JSONB NOT NULL DEFAULT '{}',
    -- Deduplication
    email_normalized VARCHAR(320),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_contacts_email ON contacts(tenant_id, email_normalized);
CREATE INDEX idx_contacts_company ON contacts(company_id);
CREATE INDEX idx_contacts_tenant ON contacts(tenant_id);
CREATE INDEX idx_contacts_name_trgm ON contacts USING gin(full_name gin_trgm_ops);

-- ============================================================================
-- LEADS (Join of Contact + Company with Pipeline State)
-- ============================================================================

CREATE TABLE leads (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    contact_id      UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    company_id      UUID REFERENCES companies(id) ON DELETE SET NULL,
    -- Pipeline
    stage           VARCHAR(50) NOT NULL DEFAULT 'new',
    -- new, enriching, enriched, scored, contacted, replied, qualified, converted, lost, archived
    source          VARCHAR(100),  -- csv_import, manual, api, web_form, linkedin_import
    source_detail   VARCHAR(255),  -- e.g., filename for csv_import
    -- Assignment
    assigned_to     UUID REFERENCES users(id) ON DELETE SET NULL,
    -- Metadata
    tags            TEXT[] NOT NULL DEFAULT '{}',
    custom_fields   JSONB NOT NULL DEFAULT '{}',
    notes           TEXT,
    -- Tracking
    first_contacted_at   TIMESTAMPTZ,
    last_contacted_at    TIMESTAMPTZ,
    last_replied_at      TIMESTAMPTZ,
    total_emails_sent    INTEGER NOT NULL DEFAULT 0,
    total_emails_opened  INTEGER NOT NULL DEFAULT 0,
    total_replies        INTEGER NOT NULL DEFAULT 0,
    total_clicks         INTEGER NOT NULL DEFAULT 0,
    -- Import tracking
    import_batch_id UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_leads_tenant ON leads(tenant_id);
CREATE INDEX idx_leads_stage ON leads(tenant_id, stage);
CREATE INDEX idx_leads_assigned ON leads(tenant_id, assigned_to);
CREATE INDEX idx_leads_contact ON leads(contact_id);
CREATE INDEX idx_leads_company ON leads(company_id);
CREATE INDEX idx_leads_tags ON leads USING gin(tags);
CREATE INDEX idx_leads_import_batch ON leads(import_batch_id);
CREATE INDEX idx_leads_created ON leads(tenant_id, created_at DESC);

CREATE TABLE lead_activities (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    activity_type   VARCHAR(100) NOT NULL,
    -- created, imported, enriched, scored, stage_changed, email_sent, email_opened,
    -- email_clicked, replied, follow_up_scheduled, note_added, assigned, tagged
    description     TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_lead_activities_lead ON lead_activities(lead_id, created_at DESC);

CREATE TABLE import_batches (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id),
    filename        VARCHAR(500),
    file_url        TEXT,
    status          VARCHAR(50) NOT NULL DEFAULT 'processing',  -- processing, completed, failed, rolled_back
    total_rows      INTEGER NOT NULL DEFAULT 0,
    imported_rows   INTEGER NOT NULL DEFAULT 0,
    skipped_rows    INTEGER NOT NULL DEFAULT 0,
    error_rows      INTEGER NOT NULL DEFAULT 0,
    duplicate_rows  INTEGER NOT NULL DEFAULT 0,
    column_mapping  JSONB NOT NULL DEFAULT '{}',
    errors          JSONB NOT NULL DEFAULT '[]',
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- ENRICHMENT & RESEARCH
-- ============================================================================

CREATE TABLE enrichment_jobs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    status          VARCHAR(50) NOT NULL DEFAULT 'pending',
    -- pending, researching, extracting, completed, failed, partial
    sources_used    TEXT[] NOT NULL DEFAULT '{}',
    error_message   TEXT,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_enrichment_jobs_lead ON enrichment_jobs(lead_id);
CREATE INDEX idx_enrichment_jobs_status ON enrichment_jobs(tenant_id, status);

CREATE TABLE research_data (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    enrichment_job_id UUID NOT NULL REFERENCES enrichment_jobs(id) ON DELETE CASCADE,
    lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    company_id      UUID REFERENCES companies(id) ON DELETE SET NULL,
    source          VARCHAR(100) NOT NULL,  -- serpapi, firecrawl, tavily, linkedin, crunchbase, manual
    source_url      TEXT,
    query_used      TEXT,
    raw_content     TEXT,           -- raw scraped/searched content
    content_type    VARCHAR(50),    -- search_result, web_page, news_article, company_page
    relevance_score FLOAT,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_research_data_lead ON research_data(lead_id);
CREATE INDEX idx_research_data_job ON research_data(enrichment_job_id);

CREATE TABLE enrichment_data (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    company_id      UUID REFERENCES companies(id) ON DELETE SET NULL,
    -- Company enrichment
    industry_enriched        VARCHAR(255),
    size_enriched            VARCHAR(50),
    employee_count_enriched  INTEGER,
    funding_enriched         JSONB,  -- {total, stage, latest_date, rounds: [...]}
    category_enriched        VARCHAR(100),
    tech_stack_enriched      TEXT[],
    headquarters_enriched    VARCHAR(500),
    annual_revenue_enriched  VARCHAR(100),
    -- Event-specific enrichment
    event_marketing_maturity VARCHAR(50),  -- none, basic, intermediate, advanced
    upcoming_events          JSONB NOT NULL DEFAULT '[]',  -- [{name, date, type, url}]
    past_events              JSONB NOT NULL DEFAULT '[]',
    conference_participation JSONB NOT NULL DEFAULT '[]',
    event_budget_estimate    VARCHAR(100),
    -- Signal enrichment
    recent_news              JSONB NOT NULL DEFAULT '[]',  -- [{title, url, date, summary}]
    hiring_activity          VARCHAR(50),  -- none, low, moderate, high
    growth_signals           JSONB NOT NULL DEFAULT '[]',  -- [{signal, evidence, strength}]
    relevant_announcements   JSONB NOT NULL DEFAULT '[]',
    -- Completeness
    completeness_score       FLOAT NOT NULL DEFAULT 0.0,  -- 0.0 to 1.0
    enrichment_version       INTEGER NOT NULL DEFAULT 1,
    last_enriched_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(lead_id)
);

CREATE INDEX idx_enrichment_data_lead ON enrichment_data(lead_id);
CREATE INDEX idx_enrichment_data_company ON enrichment_data(company_id);

-- ============================================================================
-- AI INSIGHTS & SCORING
-- ============================================================================

CREATE TABLE ai_insights (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    company_id      UUID REFERENCES companies(id) ON DELETE SET NULL,
    -- Extracted insights
    company_summary         TEXT,
    key_decision_makers     JSONB NOT NULL DEFAULT '[]',
    pain_points             JSONB NOT NULL DEFAULT '[]',
    opportunities           JSONB NOT NULL DEFAULT '[]',
    personalization_hooks   JSONB NOT NULL DEFAULT '[]',  -- [{hook, context, source}]
    competitive_landscape   TEXT,
    recommended_approach    TEXT,
    talking_points          JSONB NOT NULL DEFAULT '[]',
    -- Event-specific insights
    event_strategy_assessment TEXT,
    cvent_usage_indicators  JSONB NOT NULL DEFAULT '[]',
    event_program_complexity VARCHAR(50),
    -- Confidence
    confidence_score        FLOAT NOT NULL DEFAULT 0.0,
    model_used              VARCHAR(100),
    token_usage             JSONB,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(lead_id)
);

CREATE INDEX idx_ai_insights_lead ON ai_insights(lead_id);

CREATE TABLE lead_scores (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    scoring_profile VARCHAR(100) NOT NULL DEFAULT 'default',
    -- Composite score
    total_score     FLOAT NOT NULL DEFAULT 0.0,  -- 0.0 to 100.0
    tier            VARCHAR(20) NOT NULL DEFAULT 'cold',  -- hot, warm, cold
    -- Signal breakdown
    signal_scores   JSONB NOT NULL DEFAULT '{}',
    -- {
    --   "upcoming_events": {"score": 15, "max": 15, "evidence": "3 upcoming events found"},
    --   "event_maturity": {"score": 10, "max": 15, "evidence": "intermediate maturity"},
    --   "company_size": {"score": 8, "max": 10, "evidence": "201-500 employees"},
    --   ...
    -- }
    -- Engagement component
    engagement_score FLOAT NOT NULL DEFAULT 0.0,
    -- Metadata
    scoring_version  INTEGER NOT NULL DEFAULT 1,
    model_used       VARCHAR(100),
    scored_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(lead_id, scoring_profile)
);

CREATE INDEX idx_lead_scores_lead ON lead_scores(lead_id);
CREATE INDEX idx_lead_scores_tier ON lead_scores(tier);
CREATE INDEX idx_lead_scores_total ON lead_scores(total_score DESC);

CREATE TABLE scoring_profiles (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    slug            VARCHAR(100) NOT NULL,
    description     TEXT,
    weights         JSONB NOT NULL,  -- {"upcoming_events": 15, "company_size": 10, ...}
    thresholds      JSONB NOT NULL DEFAULT '{"hot": 75, "warm": 40}',
    is_default      BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, slug)
);

-- ============================================================================
-- VECTOR EMBEDDINGS (PGVector)
-- ============================================================================

CREATE TABLE lead_embeddings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    embedding_type  VARCHAR(50) NOT NULL,  -- enrichment_summary, company_profile, email_content
    embedding       vector(1536) NOT NULL, -- OpenAI text-embedding-3-small dimension
    content_hash    VARCHAR(64) NOT NULL,  -- SHA-256 of source content for cache invalidation
    model_used      VARCHAR(100) NOT NULL DEFAULT 'text-embedding-3-small',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(lead_id, embedding_type)
);

CREATE INDEX idx_lead_embeddings_vector ON lead_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ============================================================================
-- CAMPAIGNS & MESSAGING
-- ============================================================================

CREATE TABLE sender_accounts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email           VARCHAR(320) NOT NULL,
    display_name    VARCHAR(255),
    provider        VARCHAR(50) NOT NULL,  -- gmail, sendgrid, ses
    credentials     JSONB NOT NULL DEFAULT '{}',  -- encrypted OAuth tokens / API keys
    -- Deliverability
    domain          VARCHAR(255),
    spf_verified    BOOLEAN NOT NULL DEFAULT false,
    dkim_verified   BOOLEAN NOT NULL DEFAULT false,
    dmarc_verified  BOOLEAN NOT NULL DEFAULT false,
    -- Warm-up tracking
    daily_limit     INTEGER NOT NULL DEFAULT 50,
    warmup_stage    INTEGER NOT NULL DEFAULT 0,
    warmup_started_at TIMESTAMPTZ,
    -- Stats
    total_sent      INTEGER NOT NULL DEFAULT 0,
    bounce_rate     FLOAT NOT NULL DEFAULT 0.0,
    spam_rate       FLOAT NOT NULL DEFAULT 0.0,
    -- Status
    is_active       BOOLEAN NOT NULL DEFAULT true,
    last_synced_at  TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE campaigns (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    created_by      UUID NOT NULL REFERENCES users(id),
    name            VARCHAR(500) NOT NULL,
    description     TEXT,
    campaign_type   VARCHAR(50) NOT NULL DEFAULT 'email_sequence',
    -- email_sequence, single_blast, ab_test
    status          VARCHAR(50) NOT NULL DEFAULT 'draft',
    -- draft, generating, ready, active, paused, completed, cancelled
    -- Targeting
    target_segment  JSONB NOT NULL DEFAULT '{}',
    -- {"score_tier": ["hot","warm"], "tags": [...], "enrichment_filters": {...}}
    -- Sequence
    sequence_config JSONB NOT NULL DEFAULT '[]',
    -- [{"step":1, "delay_days":0, "template_id":"...", "condition":"no_reply"}]
    -- Schedule
    schedule_config JSONB NOT NULL DEFAULT '{}',
    -- {"timezone":"America/New_York", "send_window":{"start":"09:00","end":"17:00"}, ...}
    -- Sender
    sender_account_id UUID REFERENCES sender_accounts(id),
    -- A/B Test config
    ab_test_config  JSONB,
    -- Metrics (denormalized for fast dashboard queries)
    total_leads     INTEGER NOT NULL DEFAULT 0,
    total_sent      INTEGER NOT NULL DEFAULT 0,
    total_delivered  INTEGER NOT NULL DEFAULT 0,
    total_opened    INTEGER NOT NULL DEFAULT 0,
    total_clicked   INTEGER NOT NULL DEFAULT 0,
    total_replied   INTEGER NOT NULL DEFAULT 0,
    total_bounced   INTEGER NOT NULL DEFAULT 0,
    total_unsubscribed INTEGER NOT NULL DEFAULT 0,
    -- Dates
    scheduled_at    TIMESTAMPTZ,
    launched_at     TIMESTAMPTZ,
    paused_at       TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_campaigns_tenant ON campaigns(tenant_id);
CREATE INDEX idx_campaigns_status ON campaigns(tenant_id, status);
CREATE INDEX idx_campaigns_created ON campaigns(tenant_id, created_at DESC);

CREATE TABLE campaign_leads (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    campaign_id     UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    status          VARCHAR(50) NOT NULL DEFAULT 'pending',
    -- pending, generating, ready, sending, sent, delivered, opened, clicked, replied, bounced, unsubscribed, skipped
    current_step    INTEGER NOT NULL DEFAULT 0,
    -- Per-lead campaign metrics
    emails_sent     INTEGER NOT NULL DEFAULT 0,
    emails_opened   INTEGER NOT NULL DEFAULT 0,
    emails_clicked  INTEGER NOT NULL DEFAULT 0,
    replied         BOOLEAN NOT NULL DEFAULT false,
    unsubscribed    BOOLEAN NOT NULL DEFAULT false,
    bounced         BOOLEAN NOT NULL DEFAULT false,
    -- Exclusion
    excluded        BOOLEAN NOT NULL DEFAULT false,
    exclusion_reason VARCHAR(255),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(campaign_id, lead_id)
);

CREATE INDEX idx_campaign_leads_campaign ON campaign_leads(campaign_id);
CREATE INDEX idx_campaign_leads_lead ON campaign_leads(lead_id);
CREATE INDEX idx_campaign_leads_status ON campaign_leads(campaign_id, status);

CREATE TABLE email_templates (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name            VARCHAR(500) NOT NULL,
    category        VARCHAR(100),  -- initial_outreach, follow_up, breakup, meeting_request, custom
    subject_template TEXT NOT NULL,
    body_template   TEXT NOT NULL,  -- supports {{variable}} placeholders
    tone            VARCHAR(50) DEFAULT 'professional',  -- professional, casual, consultative, formal
    variables       TEXT[] NOT NULL DEFAULT '{}',
    is_ai_generated BOOLEAN NOT NULL DEFAULT false,
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE messages (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    campaign_id     UUID REFERENCES campaigns(id) ON DELETE SET NULL,
    campaign_lead_id UUID REFERENCES campaign_leads(id) ON DELETE SET NULL,
    lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    contact_id      UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    sender_account_id UUID REFERENCES sender_accounts(id),
    -- Message content
    channel         VARCHAR(50) NOT NULL DEFAULT 'email',  -- email, whatsapp, linkedin, sms, slack
    direction       VARCHAR(10) NOT NULL DEFAULT 'outbound',  -- outbound, inbound
    subject         TEXT,
    body_html       TEXT,
    body_text       TEXT,
    -- AI generation metadata
    is_ai_generated BOOLEAN NOT NULL DEFAULT false,
    ai_model_used   VARCHAR(100),
    template_id     UUID REFERENCES email_templates(id),
    personalization_context JSONB,
    -- Sequence position
    sequence_step   INTEGER,
    -- Status
    status          VARCHAR(50) NOT NULL DEFAULT 'draft',
    -- draft, approved, queued, sending, sent, delivered, failed
    -- Provider tracking
    provider        VARCHAR(50),
    provider_message_id VARCHAR(500),
    -- Review
    reviewed_by     UUID REFERENCES users(id),
    reviewed_at     TIMESTAMPTZ,
    edited_by       UUID REFERENCES users(id),
    edited_at       TIMESTAMPTZ,
    -- Dates
    scheduled_at    TIMESTAMPTZ,
    sent_at         TIMESTAMPTZ,
    delivered_at    TIMESTAMPTZ,
    failed_at       TIMESTAMPTZ,
    failure_reason  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_messages_tenant ON messages(tenant_id);
CREATE INDEX idx_messages_lead ON messages(lead_id);
CREATE INDEX idx_messages_campaign ON messages(campaign_id);
CREATE INDEX idx_messages_status ON messages(tenant_id, status);
CREATE INDEX idx_messages_sent ON messages(tenant_id, sent_at DESC);
CREATE INDEX idx_messages_direction ON messages(tenant_id, direction, created_at DESC);
CREATE INDEX idx_messages_provider_id ON messages(provider, provider_message_id);

-- ============================================================================
-- EMAIL EVENTS & TRACKING
-- ============================================================================

CREATE TABLE email_events (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    message_id      UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    campaign_id     UUID REFERENCES campaigns(id) ON DELETE SET NULL,
    lead_id         UUID REFERENCES leads(id) ON DELETE SET NULL,
    event_type      VARCHAR(50) NOT NULL,
    -- sent, delivered, opened, clicked, bounced, deferred, dropped, spam_complaint, unsubscribed
    provider        VARCHAR(50),
    provider_event_id VARCHAR(500),
    -- Event data
    metadata        JSONB NOT NULL DEFAULT '{}',
    -- For opens: {user_agent, ip_country}
    -- For clicks: {url, user_agent}
    -- For bounces: {bounce_type, reason, code}
    -- Dedup
    event_hash      VARCHAR(64),  -- prevent duplicate webhook events
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_email_events_message ON email_events(message_id);
CREATE INDEX idx_email_events_campaign ON email_events(campaign_id);
CREATE INDEX idx_email_events_lead ON email_events(lead_id);
CREATE INDEX idx_email_events_type ON email_events(event_type, created_at DESC);
CREATE UNIQUE INDEX idx_email_events_dedup ON email_events(event_hash) WHERE event_hash IS NOT NULL;

-- ============================================================================
-- FOLLOW-UPS
-- ============================================================================

CREATE TABLE follow_ups (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    campaign_id     UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    campaign_lead_id UUID NOT NULL REFERENCES campaign_leads(id) ON DELETE CASCADE,
    lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    previous_message_id UUID REFERENCES messages(id),
    sequence_step   INTEGER NOT NULL,
    condition       VARCHAR(50) NOT NULL DEFAULT 'no_reply',
    -- no_reply, no_open, always
    status          VARCHAR(50) NOT NULL DEFAULT 'scheduled',
    -- scheduled, generating, ready, sent, cancelled, condition_not_met, failed
    due_at          TIMESTAMPTZ NOT NULL,
    executed_at     TIMESTAMPTZ,
    result_message_id UUID REFERENCES messages(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_follow_ups_due ON follow_ups(status, due_at) WHERE status = 'scheduled';
CREATE INDEX idx_follow_ups_campaign ON follow_ups(campaign_id);
CREATE INDEX idx_follow_ups_lead ON follow_ups(lead_id);

-- ============================================================================
-- REPLIES
-- ============================================================================

CREATE TABLE replies (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    lead_id         UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    contact_id      UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    campaign_id     UUID REFERENCES campaigns(id) ON DELETE SET NULL,
    original_message_id UUID REFERENCES messages(id) ON DELETE SET NULL,
    message_id      UUID REFERENCES messages(id),  -- the inbound message record
    -- Reply content
    subject         TEXT,
    body_text       TEXT,
    body_html       TEXT,
    -- AI Analysis
    analysis_status VARCHAR(50) NOT NULL DEFAULT 'pending',  -- pending, analyzing, completed, failed
    summary         TEXT,
    intent          VARCHAR(50),
    -- interested, not_interested, out_of_office, wrong_person, question, meeting_request, unsubscribe
    sentiment       VARCHAR(20),  -- positive, neutral, negative
    urgency         VARCHAR(20),  -- low, medium, high
    action_items    JSONB NOT NULL DEFAULT '[]',
    key_entities    JSONB NOT NULL DEFAULT '[]',
    -- AI Response
    suggested_response TEXT,
    response_approved  BOOLEAN,
    response_sent_at   TIMESTAMPTZ,
    -- Provider
    provider_message_id VARCHAR(500),
    -- Status
    is_read         BOOLEAN NOT NULL DEFAULT false,
    read_at         TIMESTAMPTZ,
    is_actioned     BOOLEAN NOT NULL DEFAULT false,
    actioned_at     TIMESTAMPTZ,
    actioned_by     UUID REFERENCES users(id),
    received_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_replies_tenant ON replies(tenant_id);
CREATE INDEX idx_replies_lead ON replies(lead_id);
CREATE INDEX idx_replies_campaign ON replies(campaign_id);
CREATE INDEX idx_replies_unread ON replies(tenant_id, is_read) WHERE is_read = false;
CREATE INDEX idx_replies_intent ON replies(tenant_id, intent);
CREATE INDEX idx_replies_received ON replies(tenant_id, received_at DESC);

-- ============================================================================
-- SUPPRESSION & COMPLIANCE
-- ============================================================================

CREATE TABLE suppression_list (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email           VARCHAR(320) NOT NULL,
    reason          VARCHAR(100) NOT NULL,  -- unsubscribed, bounced, spam_complaint, manual
    source          VARCHAR(100),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, email)
);

CREATE INDEX idx_suppression_email ON suppression_list(tenant_id, email);

-- ============================================================================
-- NOTIFICATIONS
-- ============================================================================

CREATE TABLE notifications (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type            VARCHAR(100) NOT NULL,
    -- reply_received, lead_scored_hot, campaign_completed, enrichment_done, system_alert
    title           VARCHAR(500) NOT NULL,
    body            TEXT,
    priority        VARCHAR(20) NOT NULL DEFAULT 'medium',  -- low, medium, high, urgent
    is_read         BOOLEAN NOT NULL DEFAULT false,
    read_at         TIMESTAMPTZ,
    action_url      TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_notifications_user ON notifications(user_id, is_read, created_at DESC);

-- ============================================================================
-- ANALYTICS (Materialized Views)
-- ============================================================================

-- Daily campaign metrics (refreshed every 15 minutes)
CREATE MATERIALIZED VIEW mv_campaign_daily_metrics AS
SELECT
    c.tenant_id,
    c.id AS campaign_id,
    DATE(ee.created_at) AS metric_date,
    COUNT(*) FILTER (WHERE ee.event_type = 'sent') AS sent_count,
    COUNT(*) FILTER (WHERE ee.event_type = 'delivered') AS delivered_count,
    COUNT(*) FILTER (WHERE ee.event_type = 'opened') AS opened_count,
    COUNT(*) FILTER (WHERE ee.event_type = 'clicked') AS clicked_count,
    COUNT(*) FILTER (WHERE ee.event_type = 'bounced') AS bounced_count,
    COUNT(*) FILTER (WHERE ee.event_type = 'spam_complaint') AS spam_count
FROM campaigns c
LEFT JOIN email_events ee ON ee.campaign_id = c.id
GROUP BY c.tenant_id, c.id, DATE(ee.created_at);

CREATE UNIQUE INDEX idx_mv_campaign_daily ON mv_campaign_daily_metrics(campaign_id, metric_date);

-- Lead pipeline distribution (refreshed every 5 minutes)
CREATE MATERIALIZED VIEW mv_lead_pipeline AS
SELECT
    tenant_id,
    stage,
    COUNT(*) AS lead_count,
    AVG(ls.total_score) AS avg_score
FROM leads l
LEFT JOIN lead_scores ls ON ls.lead_id = l.id AND ls.scoring_profile = 'default'
GROUP BY tenant_id, stage;

CREATE UNIQUE INDEX idx_mv_pipeline ON mv_lead_pipeline(tenant_id, stage);

-- Score tier distribution
CREATE MATERIALIZED VIEW mv_score_distribution AS
SELECT
    ls.scoring_profile,
    l.tenant_id,
    ls.tier,
    COUNT(*) AS lead_count,
    AVG(ls.total_score) AS avg_score,
    MIN(ls.total_score) AS min_score,
    MAX(ls.total_score) AS max_score
FROM lead_scores ls
JOIN leads l ON l.id = ls.lead_id
GROUP BY ls.scoring_profile, l.tenant_id, ls.tier;

CREATE UNIQUE INDEX idx_mv_score_dist ON mv_score_distribution(tenant_id, scoring_profile, tier);

-- ============================================================================
-- REFRESH FUNCTIONS
-- ============================================================================

-- Function to refresh all materialized views (called by Celery Beat)
CREATE OR REPLACE FUNCTION refresh_materialized_views()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_campaign_daily_metrics;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_lead_pipeline;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_score_distribution;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- ROW LEVEL SECURITY (Multi-tenant isolation)
-- ============================================================================

ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE replies ENABLE ROW LEVEL SECURITY;

-- Example RLS policy (applied to each table)
CREATE POLICY tenant_isolation_leads ON leads
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

CREATE POLICY tenant_isolation_companies ON companies
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

CREATE POLICY tenant_isolation_campaigns ON campaigns
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

CREATE POLICY tenant_isolation_messages ON messages
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);
```

---

## Index Strategy Summary

| Table | Key Indexes | Purpose |
|---|---|---|
| leads | tenant + stage, tenant + created_at, tags (GIN) | Pipeline queries, dashboard, filtering |
| companies | domain (unique per tenant), name (trigram) | Dedup, fuzzy search |
| contacts | email (unique per tenant), full_name (trigram) | Dedup, search |
| messages | lead + campaign, status, sent_at | Inbox, campaign tracking |
| email_events | message, campaign, type + date | Analytics aggregation |
| lead_scores | tier, total_score DESC | Score-based filtering, leaderboards |
| follow_ups | status + due_at (partial) | Scheduler efficient queries |
| replies | tenant + is_read (partial), received_at | Inbox unread counts |

## Partitioning Strategy (Scale Phase)

For tables expected to grow beyond 100M rows:

| Table | Partition Key | Strategy |
|---|---|---|
| email_events | created_at | Monthly range partitions |
| messages | created_at | Monthly range partitions |
| lead_activities | created_at | Monthly range partitions |
| audit_logs | created_at | Monthly range partitions, auto-drop after 2 years |
| research_data | created_at | Monthly range partitions |
