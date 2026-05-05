# 6. API Architecture

## API Design Principles

1. **RESTful** — Resource-oriented URLs, proper HTTP methods
2. **Versioned** — `/api/v1/` prefix for all endpoints
3. **Consistent** — Uniform response envelopes, error formats, pagination
4. **Authenticated** — JWT Bearer tokens for all endpoints except auth routes
5. **Rate Limited** — Per-tenant, per-user rate limiting
6. **Documented** — Auto-generated OpenAPI 3.1 spec via FastAPI

## Authentication

```
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
POST /api/v1/auth/forgot-password
POST /api/v1/auth/reset-password
POST /api/v1/auth/verify-email
```

**JWT Token Structure:**
```json
{
  "sub": "user-uuid",
  "tenant_id": "tenant-uuid",
  "role": "admin",
  "exp": 1735689600,
  "iat": 1735603200,
  "jti": "unique-token-id"
}
```

- Access token TTL: 15 minutes
- Refresh token TTL: 7 days (stored in HttpOnly cookie)
- Refresh token rotation on use

## Standard Response Envelope

```json
// Success
{
  "status": "success",
  "data": { ... },
  "meta": {
    "page": 1,
    "per_page": 25,
    "total": 1500,
    "total_pages": 60
  }
}

// Error
{
  "status": "error",
  "error": {
    "code": "LEAD_NOT_FOUND",
    "message": "Lead with ID abc-123 not found",
    "details": null
  }
}

// Validation Error
{
  "status": "error",
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": [
      {"field": "email", "message": "Invalid email format"},
      {"field": "name", "message": "Name is required"}
    ]
  }
}
```

## Pagination

Cursor-based for large datasets, offset-based for admin views:

```
# Cursor-based (default for leads, messages, events)
GET /api/v1/leads?cursor=eyJpZCI6MTIzfQ&limit=25

# Offset-based (analytics, admin)
GET /api/v1/analytics/campaigns?page=1&per_page=25
```

---

## Complete API Endpoint Reference

### Leads API

```
# CRUD
GET    /api/v1/leads                          # List leads (filterable, sortable, searchable)
POST   /api/v1/leads                          # Create single lead
GET    /api/v1/leads/{lead_id}                # Get lead details
PUT    /api/v1/leads/{lead_id}                # Update lead
DELETE /api/v1/leads/{lead_id}                # Delete lead (soft)

# Bulk operations
POST   /api/v1/leads/import                   # Import leads from CSV/Excel
GET    /api/v1/leads/import/{batch_id}         # Get import status
POST   /api/v1/leads/import/{batch_id}/rollback # Rollback import
POST   /api/v1/leads/bulk/tag                  # Bulk add/remove tags
POST   /api/v1/leads/bulk/assign               # Bulk assign to user
POST   /api/v1/leads/bulk/delete               # Bulk delete
POST   /api/v1/leads/bulk/stage                # Bulk change pipeline stage
POST   /api/v1/leads/export                    # Export leads to CSV

# Pipeline
GET    /api/v1/leads/pipeline/summary          # Pipeline stage counts
PUT    /api/v1/leads/{lead_id}/stage            # Change pipeline stage

# Activity
GET    /api/v1/leads/{lead_id}/activities       # Lead activity timeline
POST   /api/v1/leads/{lead_id}/notes            # Add note to lead

# Search
GET    /api/v1/leads/search?q=&filters=         # Full-text + faceted search
```

**Query Parameters for `GET /api/v1/leads`:**
```
?stage=new,enriched,scored          # filter by pipeline stage
&tier=hot,warm                      # filter by score tier
&tags=enterprise,cvent              # filter by tags (AND)
&assigned_to=user-uuid              # filter by assignee
&source=csv_import                  # filter by source
&min_score=50                       # minimum lead score
&max_score=100                      # maximum lead score
&company_size=201-500,501-1000      # filter by company size
&industry=technology,healthcare     # filter by industry
&created_after=2026-01-01           # date range filter
&created_before=2026-04-01
&sort=score_desc                    # sort: created_desc, score_desc, name_asc, last_contacted
&cursor=xxx                         # pagination cursor
&limit=25                           # page size (max 100)
```

### Companies API

```
GET    /api/v1/companies                       # List companies
POST   /api/v1/companies                       # Create company
GET    /api/v1/companies/{company_id}           # Get company details
PUT    /api/v1/companies/{company_id}           # Update company
GET    /api/v1/companies/{company_id}/contacts  # List contacts at company
GET    /api/v1/companies/{company_id}/leads     # List leads for company
```

### Contacts API

```
GET    /api/v1/contacts                        # List contacts
POST   /api/v1/contacts                        # Create contact
GET    /api/v1/contacts/{contact_id}            # Get contact details
PUT    /api/v1/contacts/{contact_id}            # Update contact
```

### Enrichment API

```
POST   /api/v1/enrichment/leads/{lead_id}       # Trigger enrichment for single lead
POST   /api/v1/enrichment/batch                  # Trigger enrichment for batch
GET    /api/v1/enrichment/leads/{lead_id}/status  # Get enrichment status
GET    /api/v1/enrichment/leads/{lead_id}/data    # Get enrichment data
GET    /api/v1/enrichment/leads/{lead_id}/research # Get raw research data
GET    /api/v1/enrichment/leads/{lead_id}/insights # Get AI insights
POST   /api/v1/enrichment/leads/{lead_id}/re-enrich # Force re-enrichment
```

### Scoring API

```
GET    /api/v1/scoring/leads/{lead_id}           # Get lead score
POST   /api/v1/scoring/leads/{lead_id}/rescore    # Force rescore
GET    /api/v1/scoring/distribution               # Score tier distribution
GET    /api/v1/scoring/profiles                    # List scoring profiles
POST   /api/v1/scoring/profiles                    # Create scoring profile
PUT    /api/v1/scoring/profiles/{profile_id}       # Update scoring profile
POST   /api/v1/scoring/profiles/{profile_id}/apply # Apply profile to all leads
```

### Campaigns API

```
# Campaign CRUD
GET    /api/v1/campaigns                         # List campaigns
POST   /api/v1/campaigns                         # Create campaign
GET    /api/v1/campaigns/{campaign_id}            # Get campaign details
PUT    /api/v1/campaigns/{campaign_id}            # Update campaign
DELETE /api/v1/campaigns/{campaign_id}            # Delete campaign (draft only)

# Campaign lifecycle
POST   /api/v1/campaigns/{campaign_id}/generate    # Generate emails for campaign leads
POST   /api/v1/campaigns/{campaign_id}/launch       # Launch campaign
POST   /api/v1/campaigns/{campaign_id}/pause        # Pause campaign
POST   /api/v1/campaigns/{campaign_id}/resume       # Resume campaign
POST   /api/v1/campaigns/{campaign_id}/cancel       # Cancel campaign

# Campaign leads & messages
GET    /api/v1/campaigns/{campaign_id}/leads        # List leads in campaign
POST   /api/v1/campaigns/{campaign_id}/leads        # Add leads to campaign
DELETE /api/v1/campaigns/{campaign_id}/leads/{lead_id}  # Remove lead from campaign
GET    /api/v1/campaigns/{campaign_id}/messages     # List messages in campaign
GET    /api/v1/campaigns/{campaign_id}/metrics       # Campaign performance metrics

# A/B Testing
POST   /api/v1/campaigns/{campaign_id}/ab-test      # Configure A/B test
GET    /api/v1/campaigns/{campaign_id}/ab-test/results # Get A/B test results
```

### Messages API

```
GET    /api/v1/messages                          # List messages (inbox view)
GET    /api/v1/messages/{message_id}             # Get message details
PUT    /api/v1/messages/{message_id}             # Edit message (draft/approved only)
POST   /api/v1/messages/{message_id}/approve      # Approve message for sending
POST   /api/v1/messages/{message_id}/regenerate    # Regenerate with AI
POST   /api/v1/messages/bulk/approve               # Bulk approve messages

# Outbox
GET    /api/v1/messages/outbox                    # Messages queued for sending
GET    /api/v1/messages/sent                      # Sent messages
```

### Replies API

```
GET    /api/v1/replies                           # List replies (inbox)
GET    /api/v1/replies/unread                     # Unread replies
GET    /api/v1/replies/{reply_id}                 # Get reply details + analysis
PUT    /api/v1/replies/{reply_id}/read             # Mark as read
POST   /api/v1/replies/{reply_id}/generate-response # Generate AI response
POST   /api/v1/replies/{reply_id}/send-response    # Send reply
GET    /api/v1/replies/{reply_id}/thread            # Get full conversation thread
```

### Templates API

```
GET    /api/v1/templates                         # List templates
POST   /api/v1/templates                         # Create template
GET    /api/v1/templates/{template_id}            # Get template
PUT    /api/v1/templates/{template_id}            # Update template
DELETE /api/v1/templates/{template_id}            # Delete template
POST   /api/v1/templates/generate                  # AI-generate template from prompt
```

### Analytics API

```
# Dashboard
GET    /api/v1/analytics/dashboard                # Main dashboard metrics

# Campaign analytics
GET    /api/v1/analytics/campaigns                # Campaign performance overview
GET    /api/v1/analytics/campaigns/{campaign_id}  # Single campaign detailed metrics
GET    /api/v1/analytics/campaigns/{campaign_id}/timeline # Time-series metrics

# Lead analytics
GET    /api/v1/analytics/leads/pipeline            # Pipeline stage distribution
GET    /api/v1/analytics/leads/scoring              # Score distribution
GET    /api/v1/analytics/leads/engagement            # Most engaged leads

# Global metrics
GET    /api/v1/analytics/metrics/open-rate          # Overall open rate
GET    /api/v1/analytics/metrics/reply-rate          # Overall reply rate
GET    /api/v1/analytics/metrics/conversion-rate     # Overall conversion rate
GET    /api/v1/analytics/metrics/daily               # Daily send/open/reply counts
```

### Sender Accounts API

```
GET    /api/v1/sender-accounts                    # List connected email accounts
POST   /api/v1/sender-accounts/gmail/connect       # Connect Gmail (OAuth flow)
POST   /api/v1/sender-accounts/sendgrid/connect     # Connect SendGrid (API key)
POST   /api/v1/sender-accounts/ses/connect           # Connect SES (credentials)
GET    /api/v1/sender-accounts/{id}                 # Get account details + health
PUT    /api/v1/sender-accounts/{id}                 # Update settings
DELETE /api/v1/sender-accounts/{id}                 # Disconnect account
GET    /api/v1/sender-accounts/{id}/health           # Deliverability health check
```

### Notifications API

```
GET    /api/v1/notifications                     # List notifications
GET    /api/v1/notifications/unread/count          # Unread count
PUT    /api/v1/notifications/{id}/read              # Mark as read
POST   /api/v1/notifications/mark-all-read          # Mark all as read
PUT    /api/v1/notifications/preferences             # Update notification preferences
```

### Admin API

```
# Users
GET    /api/v1/admin/users                        # List users
POST   /api/v1/admin/users/invite                  # Invite user
PUT    /api/v1/admin/users/{user_id}/role           # Change role
DELETE /api/v1/admin/users/{user_id}                # Deactivate user

# Teams
GET    /api/v1/admin/teams                         # List teams
POST   /api/v1/admin/teams                         # Create team
PUT    /api/v1/admin/teams/{team_id}                # Update team
POST   /api/v1/admin/teams/{team_id}/members        # Add members

# Settings
GET    /api/v1/admin/settings                      # Get tenant settings
PUT    /api/v1/admin/settings                      # Update tenant settings

# Audit
GET    /api/v1/admin/audit-log                     # Query audit log

# API Keys
GET    /api/v1/admin/api-keys                      # List API keys
POST   /api/v1/admin/api-keys                      # Create API key
DELETE /api/v1/admin/api-keys/{key_id}              # Revoke API key
```

### Webhooks (Inbound)

```
POST   /api/v1/webhooks/sendgrid                  # SendGrid event webhooks
POST   /api/v1/webhooks/ses                        # SES event notifications
POST   /api/v1/webhooks/gmail                      # Gmail push notifications
POST   /api/v1/webhooks/sendgrid/inbound            # SendGrid inbound parse
```

---

## Rate Limiting

| Tier | Requests/min | Requests/hour | Concurrent |
|---|---|---|---|
| Starter | 60 | 1,000 | 5 |
| Pro | 300 | 10,000 | 20 |
| Enterprise | 1,000 | 50,000 | 50 |

Rate limit headers in every response:
```
X-RateLimit-Limit: 300
X-RateLimit-Remaining: 295
X-RateLimit-Reset: 1735603260
```

## Websocket API

```
WS /api/v1/ws

// Client subscribes to channels:
{"type": "subscribe", "channel": "notifications"}
{"type": "subscribe", "channel": "campaign:{campaign_id}"}
{"type": "subscribe", "channel": "replies"}

// Server pushes events:
{"type": "notification", "data": {"id": "...", "title": "New reply from John", ...}}
{"type": "campaign_update", "data": {"campaign_id": "...", "sent": 150, "opened": 42}}
{"type": "reply_received", "data": {"reply_id": "...", "lead_name": "John Doe", ...}}
```
