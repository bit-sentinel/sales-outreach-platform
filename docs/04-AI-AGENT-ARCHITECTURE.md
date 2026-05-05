# 4. AI Agent Architecture

## Agent Design Philosophy

Every AI agent in OutreachAI follows these principles:

1. **Structured Outputs** — Agents produce Pydantic-validated JSON, never free-text
2. **Tool-Based** — Agents access external systems through defined tools only
3. **Memory-Aware** — Agents have access to conversation history and lead context
4. **Retry-Resilient** — Built-in retry with exponential backoff for LLM and tool failures
5. **Rate-Limited** — Per-provider rate limiting to avoid API throttling
6. **Observable** — All agent runs are logged with inputs, outputs, token usage, latency
7. **Cost-Tracked** — Token usage and cost tracked per agent invocation

## Agent Framework: LangGraph

We use **LangGraph** (LangChain's stateful graph framework) for agent orchestration:

```
┌──────────────────────────────────────────────────────────────┐
│                    AI ORCHESTRATOR SERVICE                     │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                  LangGraph Runtime                      │  │
│  │                                                        │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐            │  │
│  │  │ Research  │  │ Enrichmt │  │ Insight  │            │  │
│  │  │  Graph   │──▶│  Graph   │──▶│  Graph   │            │  │
│  │  └──────────┘  └──────────┘  └────┬─────┘            │  │
│  │                                    │                   │  │
│  │  ┌──────────┐  ┌──────────┐  ┌────▼─────┐            │  │
│  │  │ Persona- │  │ Reply    │  │ Scoring  │            │  │
│  │  │ lization │  │ Analysis │  │  Graph   │            │  │
│  │  │  Graph   │  │  Graph   │  └──────────┘            │  │
│  │  └──────────┘  └──────────┘                           │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                   Shared Components                     │  │
│  │                                                        │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐            │  │
│  │  │  LLM     │  │  Tool    │  │  Memory  │            │  │
│  │  │ Provider │  │ Registry │  │  Store   │            │  │
│  │  └──────────┘  └──────────┘  └──────────┘            │  │
│  │                                                        │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐            │  │
│  │  │  Rate    │  │  Cost    │  │  Output  │            │  │
│  │  │ Limiter  │  │ Tracker  │  │ Validator│            │  │
│  │  └──────────┘  └──────────┘  └──────────┘            │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

## LLM Provider Strategy

```python
# Multi-model strategy with fallback chain
LLM_CONFIG = {
    "primary": {
        "provider": "openai",
        "model": "gpt-4o",
        "temperature": 0.3,
        "max_tokens": 4096,
        "timeout": 60,
    },
    "fallback": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "temperature": 0.3,
        "max_tokens": 4096,
        "timeout": 90,
    },
    "fast": {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "temperature": 0.2,
        "max_tokens": 2048,
        "timeout": 30,
    },
    "embeddings": {
        "provider": "openai",
        "model": "text-embedding-3-small",
        "dimensions": 1536,
    }
}
```

---

## Agent 1: Research Agent

**Purpose**: Execute web searches and scrape relevant pages for a company/contact.

### Graph Definition

```python
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field

class ResearchState(BaseModel):
    company_name: str
    domain: str | None = None
    contact_name: str | None = None
    contact_title: str | None = None
    search_queries: list[str] = Field(default_factory=list)
    search_results: list[dict] = Field(default_factory=list)
    scraped_pages: list[dict] = Field(default_factory=list)
    news_results: list[dict] = Field(default_factory=list)
    event_results: list[dict] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    iteration: int = 0
    max_iterations: int = 3

# Graph nodes
def plan_research(state: ResearchState) -> ResearchState:
    """Generate search queries based on company/contact context."""
    ...

def execute_web_search(state: ResearchState) -> ResearchState:
    """Run searches via SerpAPI/Tavily."""
    ...

def scrape_company_website(state: ResearchState) -> ResearchState:
    """Scrape company website via Firecrawl."""
    ...

def search_news(state: ResearchState) -> ResearchState:
    """Search for recent news about the company."""
    ...

def search_events(state: ResearchState) -> ResearchState:
    """Search for events, conferences, and event programs."""
    ...

def evaluate_completeness(state: ResearchState) -> str:
    """Decide if we have enough data or need more research."""
    ...

# Build graph
research_graph = StateGraph(ResearchState)
research_graph.add_node("plan", plan_research)
research_graph.add_node("search", execute_web_search)
research_graph.add_node("scrape", scrape_company_website)
research_graph.add_node("news", search_news)
research_graph.add_node("events", search_events)
research_graph.add_node("evaluate", evaluate_completeness)

research_graph.set_entry_point("plan")
research_graph.add_edge("plan", "search")
research_graph.add_edge("search", "scrape")
research_graph.add_edge("scrape", "news")
research_graph.add_edge("news", "events")
research_graph.add_edge("events", "evaluate")
research_graph.add_conditional_edges("evaluate", evaluate_completeness, {
    "sufficient": END,
    "needs_more": "plan",
})
```

### Tools

| Tool | Provider | Rate Limit |
|---|---|---|
| `search_web(query, num_results)` | SerpAPI / Tavily | 100/min |
| `scrape_url(url)` | Firecrawl | 50/min |
| `search_news(query, date_range)` | Tavily News | 60/min |
| `search_events(company)` | SerpAPI + custom | 60/min |

### System Prompt

```
You are a Research Agent for OutreachAI. Your job is to gather comprehensive 
business intelligence about a company and its key contacts.

RESEARCH GOALS:
1. Understand what the company does, its size, industry, and market position
2. Find recent news, funding announcements, and growth signals
3. Identify event marketing activities — upcoming events, past conferences, 
   event programs, sponsorships, and event technology usage
4. Find information about the specific contact — their role, background, 
   and professional activities
5. Look for technology stack indicators, especially event management platforms 
   (Cvent, Eventbrite, Bizzabo, etc.)

SEARCH STRATEGY:
- Start with broad company search, then narrow to events and tech stack
- Always search for "[company] events conferences" and "[company] Cvent"
- Check the company website's events/news section
- Search for the contact on professional networks
- Look for press releases and funding announcements

OUTPUT: Return all raw research data organized by source. Do NOT interpret 
or summarize — that is the job of downstream agents.

CONSTRAINTS:
- Maximum 10 search queries per lead
- Maximum 5 page scrapes per lead
- Skip paywalled content
- Record all source URLs for attribution
```

---

## Agent 2: Enrichment Agent

**Purpose**: Extract structured company and contact data from raw research.

### Structured Output Schema

```python
class CompanyEnrichment(BaseModel):
    industry: str | None = None
    sub_industry: str | None = None
    size_range: str | None = None  # 1-10, 11-50, 51-200, 201-500, 501-1000, 1000+
    employee_count: int | None = None
    category: str | None = None  # enterprise, sme, startup, ngo, nonprofit, government
    funding_total: int | None = None
    funding_stage: str | None = None
    latest_funding_date: str | None = None
    annual_revenue_range: str | None = None
    tech_stack: list[str] = Field(default_factory=list)
    headquarters: str | None = None
    description: str | None = None

class EventEnrichment(BaseModel):
    event_marketing_maturity: str | None = None  # none, basic, intermediate, advanced
    upcoming_events: list[EventInfo] = Field(default_factory=list)
    past_events: list[EventInfo] = Field(default_factory=list)
    conference_participation: list[str] = Field(default_factory=list)
    event_budget_estimate: str | None = None
    uses_cvent: bool | None = None
    event_tech_platforms: list[str] = Field(default_factory=list)

class SignalEnrichment(BaseModel):
    recent_news: list[NewsItem] = Field(default_factory=list)
    hiring_activity: str | None = None  # none, low, moderate, high
    growth_signals: list[GrowthSignal] = Field(default_factory=list)
    relevant_announcements: list[str] = Field(default_factory=list)

class EnrichmentOutput(BaseModel):
    company: CompanyEnrichment
    events: EventEnrichment
    signals: SignalEnrichment
    completeness_score: float  # 0.0 to 1.0
    confidence_notes: list[str] = Field(default_factory=list)
```

### System Prompt

```
You are an Enrichment Agent for OutreachAI. You receive raw research data 
collected about a company and must extract structured business intelligence.

INPUT: Raw research data including search results, scraped web pages, news 
articles, and event information.

YOUR TASK:
1. Extract factual company information (industry, size, funding, tech stack)
2. Assess event marketing maturity based on evidence
3. Identify upcoming and past events with dates
4. Detect growth signals, hiring activity, and recent news
5. Rate your confidence for each extracted field

RULES:
- Only extract information you can verify from the provided sources
- If information conflicts across sources, use the most recent/reliable source
- If a field cannot be determined, leave it null — do NOT guess
- For event_marketing_maturity, use this rubric:
  * "advanced": Dedicated events team, multiple annual events, uses event tech
  * "intermediate": Participates in conferences, hosts some events
  * "basic": Occasional event mentions, no dedicated program
  * "none": No event activity found
- Always provide confidence_notes explaining low-confidence extractions

OUTPUT: Structured JSON matching the EnrichmentOutput schema exactly.
```

---

## Agent 3: Insight Extraction Agent

**Purpose**: Generate actionable business insights and personalization hooks from enriched data.

### Structured Output Schema

```python
class InsightOutput(BaseModel):
    company_summary: str  # 2-3 sentence executive summary
    pain_points: list[PainPoint]  # identified business challenges
    opportunities: list[Opportunity]  # outreach-relevant opportunities
    personalization_hooks: list[PersonalizationHook]  # specific talking points
    competitive_landscape: str | None  # who are they competing with
    recommended_approach: str  # how to approach this lead
    talking_points: list[str]  # key points for the outreach email
    event_strategy_assessment: str | None
    cvent_usage_indicators: list[str]
    event_program_complexity: str | None  # simple, moderate, complex

class PersonalizationHook(BaseModel):
    hook: str  # e.g., "Recently raised $50M Series C"
    context: str  # e.g., "They'll be scaling events as part of growth"
    source: str  # e.g., "TechCrunch article from Jan 2026"
    relevance_score: float  # 0.0 to 1.0
```

### System Prompt

```
You are an Insight Extraction Agent for OutreachAI. You analyze enriched 
company data to generate actionable business insights for sales outreach.

CONTEXT: We are a consultancy that helps companies manage events on the 
Cvent platform. We need insights that help personalize our outreach.

INPUT: Enriched company data including industry, size, funding, events, 
news, hiring activity, and growth signals.

YOUR TASK:
1. Write a concise 2-3 sentence company summary
2. Identify pain points relevant to event management consulting
3. Identify opportunities where our services could add value
4. Generate 3-5 personalization hooks — specific, timely, relevant facts 
   that can be referenced in the outreach email
5. Assess their event program complexity and potential needs
6. Recommend the best outreach approach (tone, angle, value proposition)

PERSONALIZATION HOOKS MUST BE:
- Based on real, sourced information (not generic)
- Timely (prefer recent events/news)
- Relevant to event management / Cvent consulting
- Specific enough to show genuine research

EXAMPLES OF GOOD HOOKS:
✓ "Congratulations on your upcoming Global Summit 2026 — managing 5000+ 
   attendees across multiple tracks requires sophisticated event tech."
✓ "I noticed you recently expanded into APAC — international events often 
   need specialized registration and compliance workflows."

EXAMPLES OF BAD HOOKS:
✗ "I noticed your company is doing well." (generic)
✗ "Events are important for business growth." (obvious)

OUTPUT: Structured JSON matching InsightOutput schema.
```

---

## Agent 4: Lead Scoring Agent

**Purpose**: Calculate composite lead scores based on enrichment data and engagement signals.

### Structured Output Schema

```python
class ScoringOutput(BaseModel):
    total_score: float  # 0.0 to 100.0
    tier: str  # hot, warm, cold
    signal_scores: dict[str, SignalScore]
    top_signals: list[str]  # top 3 scoring signals
    scoring_rationale: str  # brief explanation of the score
    recommended_priority: str  # immediate, this_week, this_month, backlog

class SignalScore(BaseModel):
    score: float
    max_score: float
    evidence: str
    confidence: float  # 0.0 to 1.0
```

### System Prompt

```
You are a Lead Scoring Agent for OutreachAI. You analyze enriched company 
data and engagement metrics to calculate a lead quality score.

INPUT:
- Enriched company data (industry, size, funding, events, etc.)
- AI insights (opportunities, pain points, hooks)
- Engagement data (opens, clicks, replies — if available)
- Scoring profile weights

SCORING SIGNALS AND WEIGHTS:
{scoring_profile_weights}

SCORING RULES:
1. Calculate each signal score based on the evidence available
2. Weight each signal according to the scoring profile
3. Calculate total score as percentage of maximum possible
4. Assign tier: Hot (>=75), Warm (>=40), Cold (<40)
5. Identify top 3 contributing signals
6. Provide brief rationale for the score

IMPORTANT:
- Do NOT inflate scores without evidence
- If data is missing for a signal, score it as 0 (not null)
- Engagement signals can boost or lower the score from enrichment-only baseline
- Companies currently using Cvent get a +10 bonus (tech_stack_compatibility)
- Companies with upcoming large events in the next 3 months are strong Hot signals

OUTPUT: Structured JSON matching ScoringOutput schema.
```

---

## Agent 5: Personalization Agent

**Purpose**: Generate highly personalized outreach emails using enrichment data and insights.

### Structured Output Schema

```python
class EmailOutput(BaseModel):
    subject_line: str
    subject_line_variants: list[str]  # 2 alternatives for A/B testing
    body_html: str
    body_text: str  # plain text version
    personalization_elements: list[str]  # list of personalized elements used
    tone: str  # detected tone used
    word_count: int
    estimated_read_time_seconds: int

class SequenceOutput(BaseModel):
    emails: list[EmailOutput]
    sequence_strategy: str  # brief explanation of the sequence logic
```

### System Prompt

```
You are a Personalization Agent for OutreachAI. You write highly personalized, 
human-sounding outreach emails for sales campaigns.

CONTEXT:
- Sender: {sender_name}, {sender_title} at {sender_company}
- Value Proposition: {value_proposition}
- Tone: {tone}  (professional / conversational / consultative)
- Campaign Goal: {campaign_goal}

LEAD CONTEXT:
- Contact: {contact_name}, {contact_title} at {company_name}
- Company: {company_summary}
- Key Insights: {insights}
- Personalization Hooks: {hooks}
- Lead Score: {score} ({tier})
- Sequence Position: Email {step} of {total_steps}

WRITING RULES:
1. Open with a personalized hook referencing something specific about their 
   company or recent activity — NEVER "I hope this finds you well"
2. Show you've done your research in the first 2 sentences
3. Connect their situation to your value proposition naturally
4. Keep it concise: 80-120 words for initial outreach, 50-80 for follow-ups
5. Include ONE clear call-to-action (not multiple)
6. Sound like a human — not a template. No buzzwords, no corporate jargon.
7. Use their first name naturally
8. Reference specific events, news, or signals when available

SUBJECT LINE RULES:
- Under 50 characters
- Personalized (include company name or reference)
- No spam trigger words (free, guarantee, urgent, limited time)
- Generate 3 variants with different angles

SEQUENCE LOGIC (if generating multi-step):
- Email 1: Initial outreach — establish relevance, soft CTA
- Email 2 (Day 3): Follow-up — add new value, reference previous email briefly
- Email 3 (Day 7): Different angle — share a case study or insight
- Email 4 (Day 14): Breakup email — respectful close, leave door open

FORBIDDEN:
- Generic opening lines ("I came across your profile...")
- Fake flattery ("I'm a huge fan of your company...")
- Pressure tactics ("This offer expires...")
- Misleading subject lines
- Emails longer than 150 words (initial) or 100 words (follow-up)

OUTPUT: Structured JSON matching EmailOutput or SequenceOutput schema.
```

---

## Agent 6: Reply Analysis Agent

**Purpose**: Analyze incoming email replies to classify intent, sentiment, and extract action items.

### Structured Output Schema

```python
class ReplyAnalysis(BaseModel):
    summary: str  # 1-2 sentence summary
    intent: str  # interested, not_interested, out_of_office, wrong_person, 
                  # question, meeting_request, unsubscribe, referral
    sentiment: str  # positive, neutral, negative
    urgency: str  # low, medium, high
    action_items: list[str]
    key_entities: list[str]  # dates, names, topics mentioned
    out_of_office_return_date: str | None  # if detected
    referred_to: str | None  # if redirected to another person
    meeting_preferences: dict | None  # if meeting requested
    follow_up_recommendation: str  # what to do next
```

### System Prompt

```
You are a Reply Analysis Agent for OutreachAI. You analyze email replies 
from sales outreach recipients.

INPUT:
- Original outreach email (what we sent)
- Reply content (what they responded)
- Conversation history (if multi-turn)
- Lead context (company, enrichment data)

YOUR TASK:
1. Summarize the reply in 1-2 sentences
2. Classify the intent (see categories below)
3. Detect sentiment (positive / neutral / negative)
4. Assess urgency (how quickly should we respond)
5. Extract action items
6. Identify entities (dates, people, topics)
7. Recommend next action

INTENT CATEGORIES:
- "interested": Shows interest in learning more, positive response
- "meeting_request": Wants to schedule a call/meeting
- "question": Has questions before proceeding
- "not_interested": Explicit decline or not the right fit
- "out_of_office": Auto-reply or manual OOO message
- "wrong_person": Not the right contact, may refer someone else
- "referral": Directing you to someone else at the company
- "unsubscribe": Requests to stop contact
- "unclear": Cannot determine intent confidently

RULES:
- Be precise about intent — when uncertain, use "unclear" not a guess
- Extract OOO return dates when present
- If they refer to another person, extract that person's details
- Urgency "high" = they want to meet this week or have a deadline

OUTPUT: Structured JSON matching ReplyAnalysis schema.
```

---

## Agent 7: Response Generation Agent

**Purpose**: Generate contextual reply suggestions based on reply analysis.

### System Prompt

```
You are a Response Generation Agent for OutreachAI. You generate suggested 
replies to leads who responded to our outreach.

INPUT:
- Original outreach email
- Their reply
- Reply analysis (intent, sentiment, urgency)
- Lead context (company, enrichment, insights)
- Conversation history
- Campaign context (goals, value proposition)

RESPONSE STRATEGY BY INTENT:
- "interested": Enthusiastic, propose next step (call, demo, meeting)
- "meeting_request": Confirm availability, share calendar link
- "question": Answer directly with specific information
- "referral": Thank them, acknowledge the referral, reach out to new contact
- "out_of_office": Do NOT respond (schedule follow-up after return date)
- "not_interested": Graceful acceptance, leave door open
- "unsubscribe": Confirm removal (auto-handled, no response needed)

WRITING RULES:
1. Match their tone and energy level
2. Address their specific points/questions
3. Keep it short (50-80 words max)
4. Include a clear next step
5. Reference the conversation context naturally
6. If they asked a question, answer it directly first before pitching

OUTPUT: Suggested reply text (plain text, ready to send).
```

---

## Agent Orchestration Pipeline

### Full Enrichment Pipeline

```
                    ┌─────────────────┐
                    │  Trigger:       │
                    │  lead.created   │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Research Agent │
                    │  (Web Search +  │
                    │   Scraping)     │
                    │  ~30-60 sec     │
                    └────────┬────────┘
                             │ raw research data
                    ┌────────▼────────┐
                    │ Enrichment Agent│
                    │ (Data Extraction│
                    │  + Structuring) │
                    │  ~10-15 sec     │
                    └────────┬────────┘
                             │ structured enrichment
                    ┌────────▼────────┐
                    │  Insight Agent  │
                    │ (Analysis +     │
                    │  Hooks)         │
                    │  ~10-15 sec     │
                    └────────┬────────┘
                             │ insights + hooks
                    ┌────────▼────────┐
                    │  Scoring Agent  │
                    │  (Score + Tier) │
                    │  ~5-10 sec      │
                    └────────┬────────┘
                             │ score + tier
                    ┌────────▼────────┐
                    │  Store Results  │
                    │  Emit Events    │
                    └─────────────────┘
```

### Campaign Execution Pipeline

```
               ┌──────────────────┐
               │  Trigger:        │
               │  campaign.launch │
               └────────┬─────────┘
                        │
               ┌────────▼─────────┐
               │ For each lead:   │
               │ Personalization  │──── (parallel, max 10 concurrent)
               │ Agent            │
               └────────┬─────────┘
                        │ generated emails
               ┌────────▼─────────┐
               │ Human Review     │  (optional, based on campaign settings)
               │ Queue / Auto-    │
               │ approve          │
               └────────┬─────────┘
                        │
               ┌────────▼─────────┐
               │ Messaging Service│
               │ (Send via Email) │
               └────────┬─────────┘
                        │
               ┌────────▼─────────┐
               │ Schedule Follow  │
               │ ups (if sequence)│
               └──────────────────┘
```

---

## Rate Limiting & Cost Management

### LLM Rate Limits

```python
RATE_LIMITS = {
    "openai": {
        "gpt-4o": {"rpm": 500, "tpm": 800000},
        "gpt-4o-mini": {"rpm": 1000, "tpm": 2000000},
        "text-embedding-3-small": {"rpm": 3000, "tpm": 1000000},
    },
    "anthropic": {
        "claude-sonnet-4-20250514": {"rpm": 400, "tpm": 400000},
    }
}
```

### Cost Estimation Per Lead (Full Pipeline)

| Agent | Model | Avg Tokens | Cost Estimate |
|---|---|---|---|
| Research Agent | gpt-4o | ~2000 in + 500 out | ~$0.015 |
| Enrichment Agent | gpt-4o | ~3000 in + 800 out | ~$0.020 |
| Insight Agent | gpt-4o | ~2000 in + 600 out | ~$0.015 |
| Scoring Agent | gpt-4o-mini | ~1000 in + 300 out | ~$0.001 |
| Personalization Agent | gpt-4o | ~1500 in + 400 out | ~$0.012 |
| Embeddings | text-embedding-3-small | ~500 | ~$0.00001 |
| **Total per lead** | | | **~$0.06** |

**10,000 leads full enrichment: ~$600**
**100,000 leads full enrichment: ~$6,000**

### External API Costs

| Provider | Per Request | Estimated per Lead | Monthly (10k leads) |
|---|---|---|---|
| SerpAPI | $0.01/search | ~$0.03 (3 searches) | $300 |
| Firecrawl | $0.004/page | ~$0.02 (5 scrapes) | $200 |
| Tavily | $0.01/search | ~$0.02 (2 searches) | $200 |
| **Total** | | **~$0.07** | **$700** |

### Total Cost Per Lead: ~$0.13

At 10,000 leads: **~$1,300** for full enrichment + email generation.
