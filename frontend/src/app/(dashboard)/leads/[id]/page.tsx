'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import {
  ArrowLeft,
  Building2,
  CheckCircle2,
  Mail,
  Globe,
  MapPin,
  RotateCcw,
  RefreshCw,
  Send,
  Users,
  Sparkles,
  Clock,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  TrendingUp,
  Target,
  Zap,
  Briefcase,
  CalendarDays,
  CalendarCheck,
  CalendarClock,
  XCircle,
  Megaphone,
  Lightbulb,
  Star,
} from 'lucide-react';
import { api } from '@/lib/api-client';
import { cn } from '@/lib/utils';

// ──────────────────────────────── Types ───────────────────────────────────────

interface ActivityEvent {
  id: string;
  type: 'email' | 'enrichment' | 'campaign';
  ts: string;
  status: string;
  // email
  subject?: string | null;
  campaign_name?: string | null;
  sequence_step?: number | null;
  ai_generated?: boolean;
  // enrichment
  job_type?: string;
  job_label?: string;
  duration_ms?: number | null;
  tokens_used?: number | null;
  // campaign
  current_step?: number;
  // shared
  error?: string | null;
}

interface ContactInfo {
  first_name: string;
  last_name: string;
  email: string;
  phone?: string | null;
  title?: string | null;
  department?: string | null;
  linkedin_url?: string | null;
}

interface CompanyInfo {
  name: string;
  industry?: string | null;
  location?: string | null;
  website?: string | null;
  employee_count?: number | null;
  revenue?: string | null;
}

interface LeadDetail {
  id: string;
  status: string;
  source: string | null;
  enrichment_status: string;
  enriched_at: string | null;
  tags: string[] | null;
  created_at: string;
  updated_at: string;
  company: CompanyInfo | null;
  contact: ContactInfo | null;
  scores: ScoreItem[];
}

interface SignalBreakdownEntry {
  value: number;
  weight: number;
  contribution: number;
  provider: string;
  confidence: number;
  evidence: Record<string, unknown>;
}

interface ScoreItem {
  id: string;
  overall_score: number;
  tier: string;
  signal_scores: Record<string, number>;
  signal_breakdown?: Record<string, SignalBreakdownEntry>;
  explanation: string | null;
  pipeline_version?: string;
  created_at: string;
}

interface ScoreData {
  overall_score: number;
  tier: string;
  signal_scores: Record<string, number>;
  signal_breakdown?: Record<string, SignalBreakdownEntry>;
  explanation: string | null;
  model: string | null;
  pipeline_version?: string;
  created_at: string;
}

interface AIInsight {
  id: string;
  type: string;
  content: string;
  source_data: Record<string, unknown> | null;
  confidence: number | null;
  model: string | null;
  created_at: string;
}

interface ResearchItem {
  id: string;
  source: string;
  url: string | null;
  title: string | null;
  content: string | null;
  relevance_score: number | null;
}

interface EnrichmentDataItem {
  id: string;
  data_type: string;
  provider: string;
  data: Record<string, unknown>;
  confidence: number | null;
  created_at: string;
}

interface SignalDetail {
  score: number;
  weight: number;
  reasoning: string;
  signal_name: string;
}

interface EventItem {
  event: string;
  year?: number | null;
  month?: string | null;
  date_label?: string | null;
  type?: 'past' | 'upcoming' | 'recurring' | string;
  role?: 'attendee' | 'sponsor' | 'host' | 'speaker' | 'unknown' | string;
  confirmed?: boolean;
  url?: string | null;
  description?: string;
}

interface OutreachAngle {
  angle: string;
  why: string;
  backed_by_signal: string;
}

interface OutreachEventRef {
  event_name: string;
  detail: string;
  why_relevant: string;
  source_url?: string | null;
}

interface OutreachServiceRec {
  service: string;
  rationale: string;
  matched_signal: string;
}

interface OutreachIntelligence {
  recommended_contact_role: string;
  subject_line: string;
  email_body: string;
  angles: OutreachAngle[];
  event_references: OutreachEventRef[];
  timing_recommendation: string;
  timing_rationale: string;
  service_recommendations: OutreachServiceRec[];
  generation_basis: Record<string, unknown>;
  confidence: number;
  generated_at?: string | null;
}

// ──────────────────────────────── Helpers ─────────────────────────────────────

const tierConfig: Record<string, { label: string; bg: string; text: string; barColor: string; scoreColor: string }> = {
  hot: {
    label: 'Hot',
    bg: 'bg-rose-500/15',
    text: 'text-rose-300',
    barColor: 'bg-rose-400',
    scoreColor: 'text-rose-300',
  },
  warm: {
    label: 'Warm',
    bg: 'bg-amber-500/15',
    text: 'text-amber-300',
    barColor: 'bg-amber-400',
    scoreColor: 'text-amber-300',
  },
  cold: {
    label: 'Cold',
    bg: 'bg-white/10',
    text: 'text-slate-300',
    barColor: 'bg-slate-500',
    scoreColor: 'text-slate-300',
  },
};

const statusConfig: Record<string, { label: string; className: string }> = {
  new: { label: 'New', className: 'bg-white/10 text-slate-300 border border-white/10' },
  enriching: { label: 'Enriching', className: 'bg-amber-500/15 text-amber-300 border border-amber-500/20' },
  enriched: { label: 'Enriched', className: 'bg-sky-500/15 text-sky-300 border border-sky-500/20' },
  scored: { label: 'Scored', className: 'bg-indigo-500/15 text-indigo-300 border border-indigo-500/20' },
  campaign_active: { label: 'In Campaign', className: 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/20' },
  replied: { label: 'Replied', className: 'bg-orange-500/15 text-orange-300 border border-orange-500/20' },
  converted: { label: 'Converted', className: 'bg-emerald-500/20 text-emerald-200 border border-emerald-500/30' },
};

const enrichmentStatusConfig: Record<string, { label: string; className: string }> = {
  pending: { label: 'Pending', className: 'bg-white/10 text-slate-300 border border-white/10' },
  processing: { label: 'Processing', className: 'bg-amber-500/15 text-amber-300 border border-amber-500/20' },
  enriched: { label: 'Enriched', className: 'bg-sky-500/15 text-sky-300 border border-sky-500/20' },
  failed: { label: 'Failed', className: 'bg-rose-500/15 text-rose-300 border border-rose-500/20' },
};

function Badge({ label, className }: { label: string; className: string }) {
  return (
    <span className={cn('inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold', className)}>
      {label}
    </span>
  );
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  if (value === null || value === undefined || value === '') return null;
  return (
    <div className="flex items-start gap-2 py-2 border-b border-white/[0.06] last:border-0">
      <span className="w-36 shrink-0 text-xs font-medium text-slate-500 uppercase tracking-wide pt-0.5">{label}</span>
      <span className="text-sm text-slate-200 flex-1">{value}</span>
    </div>
  );
}

/** Safely coerce any LLM-returned value to a renderable string. */
function toStr(v: unknown): string | undefined {
  if (v == null) return undefined;
  if (typeof v === 'string') return v || undefined;
  if (typeof v === 'number' || typeof v === 'boolean') return String(v);
  if (Array.isArray(v)) return v.map((i) => toStr(i)).filter(Boolean).join(', ') || undefined;
  if (typeof v === 'object')
    return Object.entries(v as Record<string, unknown>)
      .filter(([, val]) => val != null && val !== '')
      .map(([k, val]) => `${k.replace(/_/g, ' ')}: ${val}`)
      .join(' · ') || undefined;
  return undefined;
}

function ConfidenceBadge({ level }: { level?: string }) {
  if (!level) return null;
  const cfg =
    level === 'high'
      ? { cls: 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/20', label: 'High confidence' }
      : level === 'medium'
      ? { cls: 'bg-amber-500/15 text-amber-300 border border-amber-500/20', label: 'Medium confidence' }
      : { cls: 'bg-white/10 text-slate-400 border border-white/10', label: 'Low confidence' };
  return (
    <span className={cn('text-xs rounded-full px-2 py-0.5 font-medium', cfg.cls)}>{cfg.label}</span>
  );
}

// ──────────────────────────────── Tab Components ──────────────────────────────

function OverviewTab({ lead, score, events }: { lead: LeadDetail; score: ScoreData | null; events: EventItem[] }) {
  const { contact, company } = lead;
  const tier = score ? tierConfig[score.tier] ?? tierConfig.cold : null;

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
      {/* Contact Card */}
      <div className="glass-card rounded-[28px] p-6">
        <p className="app-label mb-4">Contact</p>
        {contact ? (
          <div className="space-y-3">
            <div>
              <h3 className="text-xl font-bold text-white">
                {contact.first_name} {contact.last_name}
              </h3>
              {contact.title && <p className="mt-0.5 text-sm text-slate-400">{contact.title}</p>}
              {contact.department && <p className="text-xs text-slate-500">{contact.department}</p>}
            </div>
            <div className="space-y-1.5 pt-1">
              {contact.email && (
                <a href={`mailto:${contact.email}`} className="flex items-center gap-2 text-sm text-indigo-400 hover:text-indigo-300 hover:underline">
                  <Mail className="h-3.5 w-3.5 shrink-0" />
                  {contact.email}
                </a>
              )}
              {contact.linkedin_url && (
                <a href={contact.linkedin_url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-sm text-indigo-400 hover:text-indigo-300 hover:underline">
                  <ExternalLink className="h-3.5 w-3.5 shrink-0" />
                  LinkedIn Profile
                </a>
              )}
            </div>
          </div>
        ) : (
          <p className="text-sm text-slate-500">No contact info</p>
        )}
      </div>

      {/* Company Card */}
      <div className="glass-card rounded-[28px] p-6">
        <p className="app-label mb-4">Company</p>
        {company ? (
          <div className="space-y-2">
            <h3 className="text-xl font-bold text-white">{company.name}</h3>
            <div className="space-y-1.5 pt-1">
              {company.industry && (
                <div className="flex items-center gap-2 text-sm text-slate-400">
                  <Briefcase className="h-3.5 w-3.5 shrink-0 text-slate-500" />
                  {company.industry}
                </div>
              )}
              {company.location && (
                <div className="flex items-center gap-2 text-sm text-slate-400">
                  <MapPin className="h-3.5 w-3.5 shrink-0 text-slate-500" />
                  {company.location}
                </div>
              )}
              {company.website && (
                <a href={company.website.startsWith('http') ? company.website : `https://${company.website}`} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-sm text-indigo-400 hover:text-indigo-300 hover:underline">
                  <Globe className="h-3.5 w-3.5 shrink-0" />
                  {company.website}
                </a>
              )}
              {company.employee_count && (
                <div className="flex items-center gap-2 text-sm text-slate-400">
                  <Users className="h-3.5 w-3.5 shrink-0 text-slate-500" />
                  {company.employee_count.toLocaleString()} employees
                </div>
              )}
            </div>
          </div>
        ) : (
          <p className="text-sm text-slate-500">No company info</p>
        )}
      </div>

      {/* Score Widget */}
      <div className="glass-card rounded-[28px] p-6">
        <p className="app-label mb-4">AI Lead Score</p>
        {score && tier ? (
          <div className="flex flex-col gap-4">
            <div className="flex items-end gap-3">
              <span className={cn('text-6xl font-extrabold tracking-tight', tier.scoreColor)}>
                {Math.round(score.overall_score)}
              </span>
              <div className="mb-1.5 flex flex-col gap-1">
                <span className="text-sm text-slate-500">/ 100</span>
                <span className={cn('inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold', tier.bg, tier.text)}>
                  {tier.label}
                </span>
              </div>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
              <div className={cn('h-full rounded-full transition-all', tier.barColor)} style={{ width: `${score.overall_score}%` }} />
            </div>
            <p className="text-xs text-slate-500 leading-relaxed line-clamp-3">{score.explanation}</p>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-6 text-center">
            <Sparkles className="h-6 w-6 text-slate-600 mb-2" />
            <p className="text-sm text-slate-500">Not yet scored</p>
          </div>
        )}
      </div>

      {/* Lead meta */}
      <div className="glass-card rounded-[28px] p-6 lg:col-span-3">
        <p className="app-label mb-4">Lead Details</p>
        <div className="grid grid-cols-2 gap-x-12 lg:grid-cols-4">
          <InfoRow
            label="Status"
            value={<Badge label={(statusConfig[lead.status] ?? { label: lead.status, className: '' }).label} className={(statusConfig[lead.status] ?? { label: lead.status, className: 'bg-white/10 text-slate-300' }).className} />}
          />
          <InfoRow
            label="Enrichment"
            value={<Badge label={(enrichmentStatusConfig[lead.enrichment_status] ?? { label: lead.enrichment_status, className: '' }).label} className={(enrichmentStatusConfig[lead.enrichment_status] ?? { label: lead.enrichment_status, className: 'bg-white/10 text-slate-300' }).className} />}
          />
          <InfoRow label="Source" value={lead.source ?? '—'} />
          <InfoRow label="Added" value={new Date(lead.created_at).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })} />
        </div>
        {lead.tags && lead.tags.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {lead.tags.map((tag) => (
              <span key={tag} className="inline-flex items-center rounded-full bg-indigo-500/15 px-2.5 py-0.5 text-xs font-medium text-indigo-300 border border-indigo-500/20">
                {tag}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Events preview */}
      {events.length > 0 && (
        <div className="glass-card rounded-[28px] p-6 lg:col-span-3">
          <div className="flex items-center gap-2 mb-4">
            <CalendarDays className="h-4 w-4 text-indigo-400" />
            <p className="app-label">Events Radar</p>
            <button
              className="ml-auto text-xs text-indigo-400 hover:text-indigo-300 hover:underline"
              onClick={() => document.getElementById('tab-Research')?.click()}
            >
              View full calendar →
            </button>
          </div>
          <EventsSection events={events} compact />
        </div>
      )}
    </div>
  );
}

// ──────────────────────────────── Events Section (shared) ─────────────────────

function eventRoleConfig(role?: string) {
  switch (role) {
    case 'host':     return { label: 'Host',     cls: 'bg-purple-500/15 text-purple-300 border-purple-500/20' };
    case 'sponsor':  return { label: 'Sponsor',  cls: 'bg-sky-500/15 text-sky-300 border-sky-500/20' };
    case 'speaker':  return { label: 'Speaker',  cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/20' };
    case 'attendee': return { label: 'Attendee', cls: 'bg-white/10 text-slate-400 border-white/10' };
    default:         return { label: 'Unknown',  cls: 'bg-white/10 text-slate-500 border-white/10' };
  }
}

function EventsSection({ events, compact }: { events: EventItem[]; compact?: boolean }) {
  if (events.length === 0) return null;

  const currentYear = new Date().getFullYear();
  const past = events.filter((e) => e.type === 'past' || (e.year != null && e.year < currentYear));
  const upcoming = events.filter((e) => e.type === 'upcoming' || (e.year != null && e.year >= currentYear));
  const recurring = events.filter(
    (e) => e.type === 'recurring' && !past.includes(e) && !upcoming.includes(e)
  );

  // When no explicit type field, treat all as unclassified
  const unclassified = events.filter(
    (e) => !past.includes(e) && !upcoming.includes(e) && !recurring.includes(e)
  );

  const groups: Array<{ label: string; icon: React.ReactNode; items: EventItem[] }> = [];
  if (upcoming.length > 0)
    groups.push({ label: 'Upcoming', icon: <CalendarClock className="h-4 w-4 text-indigo-400" />, items: upcoming });
  if (past.length > 0)
    groups.push({ label: 'Past Events', icon: <CalendarCheck className="h-4 w-4 text-slate-500" />, items: past });
  if (recurring.length > 0)
    groups.push({ label: 'Recurring Industry Events', icon: <CalendarDays className="h-4 w-4 text-amber-400" />, items: recurring });
  if (unclassified.length > 0)
    groups.push({ label: 'Industry Events', icon: <CalendarDays className="h-4 w-4 text-indigo-400" />, items: unclassified });

  if (compact) {
    // Compact view: show all as a pill list for Overview tab
    return (
      <div className="space-y-2">
        {events.map((ev, i) => {
          const role = eventRoleConfig(ev.role);
          const isPast = ev.type === 'past' || (ev.year != null && ev.year < currentYear);
          return (
            <div key={i} className="flex items-center gap-2">
              <span className={cn('h-1.5 w-1.5 rounded-full shrink-0', isPast ? 'bg-slate-600' : 'bg-indigo-400')} />
              <span className={cn('text-sm', isPast ? 'text-slate-500' : 'text-slate-200 font-medium')}>
                {ev.event}
              </span>
              {ev.date_label && <span className="text-xs text-slate-400">{ev.date_label}</span>}
              <span className={cn('ml-auto text-[10px] font-semibold rounded-full px-2 py-0.5 border', role.cls)}>
                {role.label}
              </span>
              {!ev.confirmed && <span className="text-[10px] text-slate-400 italic">unconfirmed</span>}
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div className="glass-card rounded-[28px] p-6">
      <div className="flex items-center gap-2 mb-5">
        <CalendarDays className="h-4 w-4 text-indigo-400" />
        <h3 className="text-sm font-semibold text-white">Event Calendar</h3>
        <span className="ml-auto text-xs text-slate-500">{events.length} event{events.length !== 1 ? 's' : ''} found</span>
      </div>

      <div className="space-y-6">
        {groups.map((group) => (
          <div key={group.label}>
            <div className="flex items-center gap-2 mb-3">
              {group.icon}
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{group.label}</p>
              <span className="text-xs text-slate-600">({group.items.length})</span>
            </div>
            <div className="space-y-3 pl-2 border-l-2 border-white/[0.06]">
              {group.items.map((ev, i) => {
                const role = eventRoleConfig(ev.role);
                return (
                  <div
                    key={i}
                    className={cn(
                      'relative rounded-2xl border p-4',
                      group.label === 'Upcoming'
                        ? 'border-indigo-500/20 bg-indigo-500/10'
                        : 'border-white/[0.06] bg-white/[0.03]'
                    )}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="flex-1">
                        <div className="flex flex-wrap items-center gap-2 mb-1">
                          <p className="text-sm font-semibold text-slate-200">{ev.event}</p>
                          {!ev.confirmed && (
                            <span className="text-[10px] italic text-slate-500">(unconfirmed)</span>
                          )}
                        </div>
                        {ev.description && (
                          <p className="text-xs text-slate-500 leading-relaxed">{ev.description}</p>
                        )}
                      </div>
                      <div className="flex flex-col items-end gap-1.5 shrink-0">
                        <span className={cn('text-[10px] font-semibold rounded-full px-2 py-0.5 border', role.cls)}>
                          {role.label}
                        </span>
                        {(ev.date_label || ev.year) && (
                          <span className="text-xs text-slate-500 font-medium">
                            {ev.date_label ?? ev.year}
                          </span>
                        )}
                      </div>
                    </div>
                    {ev.url && (
                      <a
                        href={ev.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="mt-2 inline-flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 hover:underline"
                      >
                        <ExternalLink className="h-3 w-3" />
                        Event website
                      </a>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ──────────────────────────────── Research Tab ────────────────────────────────

function ResearchTab({ insights, research }: { insights: AIInsight[]; research: ResearchItem[] }) {
  const researchInsight = insights.find((i) => i.type === 'research_summary');
  const rawData = researchInsight?.source_data as {
    company_summary?: string;
    key_people?: Array<{ name: string; title: string; linkedin_url?: string }>;
    recent_news?: Array<{ title: string; date: string; summary: string; url?: string }>;
    events_attended?: EventItem[];
    technology_stack?: string[] | { confirmed?: string[]; inferred?: string[]; tech_stack_confidence?: string };
    industry_signals?: string[];
    competitor_info?: string[];
    data_gaps?: string[];
    relevance_score?: number;
    funding_info?: string | Record<string, unknown> | null;
  } | null ?? null;

  if (!rawData && research.length === 0) {
    return (
      <div className="glass-card rounded-[28px] p-10 text-center">
        <Sparkles className="mx-auto h-8 w-8 text-slate-600 mb-3" />
        <p className="text-slate-500">No research data yet — enrich this lead to gather intelligence.</p>
      </div>
    );
  }

  const techStack = rawData?.technology_stack;
  const techConfirmed: string[] = Array.isArray(techStack) ? [] : (techStack?.confirmed ?? []);
  const techInferred: string[] = Array.isArray(techStack) ? techStack : (techStack?.inferred ?? []);
  const techConfidence = Array.isArray(techStack) ? 'low' : (techStack?.tech_stack_confidence ?? 'low');

  return (
    <div className="space-y-5">
      {rawData?.company_summary && (
        <div className="glass-card rounded-[28px] p-6">
          <div className="flex items-center gap-2 mb-3">
            <Building2 className="h-4 w-4 text-indigo-400" />
            <h3 className="text-sm font-semibold text-white">Company Summary</h3>
            {rawData.relevance_score !== undefined && (
              <span className="ml-auto text-xs text-slate-500">Relevance: {Math.round((rawData.relevance_score ?? 0) * 100)}%</span>
            )}
          </div>
          <p className="text-sm text-slate-400 leading-relaxed">{rawData.company_summary}</p>
        </div>
      )}

      {rawData?.funding_info && (
        <div className="glass-card rounded-[28px] p-6">
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp className="h-4 w-4 text-indigo-400" />
            <h3 className="text-sm font-semibold text-white">Funding</h3>
          </div>
          <p className="text-sm text-slate-400">
            {typeof rawData.funding_info === 'string'
              ? rawData.funding_info
              : Object.entries(rawData.funding_info)
                  .filter(([, v]) => v != null && v !== '')
                  .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`)
                  .join(' · ')}
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {rawData?.key_people && rawData.key_people.length > 0 && (
          <div className="glass-card rounded-[28px] p-6">
            <div className="flex items-center gap-2 mb-4">
              <Users className="h-4 w-4 text-indigo-400" />
              <h3 className="text-sm font-semibold text-white">Key People</h3>
            </div>
            <div className="space-y-3">
              {rawData.key_people.map((person, i) => (
                <div key={i} className="flex items-start justify-between">
                  <div>
                    <p className="text-sm font-medium text-slate-200">{person.name}</p>
                    <p className="text-xs text-slate-500">{person.title}</p>
                  </div>
                  {person.linkedin_url && (
                    <a href={person.linkedin_url} target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:text-indigo-300">
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="glass-card rounded-[28px] p-6">
          <div className="flex items-center gap-2 mb-4">
            <Zap className="h-4 w-4 text-indigo-400" />
            <h3 className="text-sm font-semibold text-white">Technology Stack</h3>
    <span className={cn('ml-auto text-xs rounded-full px-2 py-0.5 font-medium border', techConfidence === 'high' ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/20' : techConfidence === 'medium' ? 'bg-amber-500/15 text-amber-300 border-amber-500/20' : 'bg-white/10 text-slate-400 border-white/10')}>
              {techConfidence} confidence
            </span>
          </div>
          {techConfirmed.length > 0 && (
            <div className="mb-3">
              <p className="text-xs font-medium text-emerald-400 mb-1.5">Confirmed</p>
              <div className="flex flex-wrap gap-1.5">
                {techConfirmed.map((t, i) => (
                  <span key={i} className="rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-xs text-emerald-300 border border-emerald-500/20">{t}</span>
                ))}
              </div>
            </div>
          )}
          {techInferred.length > 0 ? (
            <div>
              {techConfirmed.length > 0 && <p className="text-xs font-medium text-slate-500 mb-1.5">Inferred</p>}
              <div className="flex flex-wrap gap-1.5">
                {techInferred.map((t, i) => (
                  <span key={i} className="rounded-full bg-white/10 px-2.5 py-0.5 text-xs text-slate-400">{t}</span>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-500">No technology data found</p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {rawData?.recent_news && rawData.recent_news.length > 0 && (
          <div className="glass-card rounded-[28px] p-6">
            <div className="flex items-center gap-2 mb-4">
              <Clock className="h-4 w-4 text-indigo-400" />
              <h3 className="text-sm font-semibold text-white">Recent News</h3>
            </div>
            <div className="space-y-3">
              {rawData.recent_news.map((news, i) => (
                <div key={i} className="border-b border-white/[0.06] pb-3 last:border-0 last:pb-0">
                  <p className="text-sm font-medium text-slate-200">{news.title}</p>
                  {news.date && news.date !== 'N/A' && <p className="text-xs text-slate-500 mt-0.5">{news.date}</p>}
                  <p className="text-xs text-slate-500 mt-1">{news.summary}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {rawData?.industry_signals && rawData.industry_signals.length > 0 && (
          <div className="glass-card rounded-[28px] p-6">
            <div className="flex items-center gap-2 mb-4">
              <TrendingUp className="h-4 w-4 text-indigo-400" />
              <h3 className="text-sm font-semibold text-white">Industry Signals</h3>
            </div>
            <ul className="space-y-2">
              {rawData.industry_signals.map((signal, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-indigo-400" />
                  <span className="text-sm text-slate-400">{signal}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <EventsSection events={rawData?.events_attended ?? []} />

      {rawData?.data_gaps && rawData.data_gaps.length > 0 && (
        <div className="rounded-[28px] border border-amber-500/20 bg-amber-500/10 p-6">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle className="h-4 w-4 text-amber-400" />
            <h3 className="text-sm font-semibold text-amber-300">Data Gaps</h3>
          </div>
          <p className="text-xs text-amber-400/80 mb-3">The following data points couldn&apos;t be found or verified:</p>
          <ul className="space-y-1.5">
            {rawData.data_gaps.map((gap, i) => (
              <li key={i} className="flex items-center gap-2 text-sm text-amber-300">
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" />
                {gap}
              </li>
            ))}
          </ul>
        </div>
      )}

      {!rawData && research.length > 0 && (
        <div className="space-y-4">
          {research.map((item) => (
            <div key={item.id} className="glass-card rounded-[28px] p-6">
              <div className="flex items-start justify-between mb-2">
                <h3 className="text-sm font-semibold text-white">{item.title ?? 'Research'}</h3>
                {item.url && (
                  <a href={item.url} target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:text-indigo-300">
                    <ExternalLink className="h-4 w-4" />
                  </a>
                )}
              </div>
              {item.content && <p className="text-sm text-slate-400 leading-relaxed">{item.content}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ──────────────────────────────── Enrichment Tab ─────────────────────────────

function EnrichmentTab({ insights, enrichmentData }: { insights: AIInsight[]; enrichmentData: EnrichmentDataItem[] }) {
  const enrichInsight = insights.find((i) => i.type === 'company_enrichment');
  const rawInsightData = enrichInsight?.source_data as {
    company?: {
      name?: string; domain?: string; industry?: string; sub_sector?: string;
      headquarters?: string; employee_count_estimate?: string; employee_count_confidence?: string;
      revenue_estimate?: string; revenue_confidence?: string; business_model?: string;
      funding_status?: string; ownership_type?: string; geographic_reach?: string;
      website_inferred?: string; products_and_services?: string[]; customer_segments?: string[];
      key_competitors?: string[]; data_gaps?: string[];
    };
    contact?: {
      name?: string; email?: string; title_raw?: string | null; title_inferred?: string;
      title_confirmed?: boolean; seniority_estimate?: string; seniority_confidence?: string;
      department_estimate?: string; department_confidence?: string; decision_maker_status?: string;
      decision_maker_confidence?: string; buying_authority?: string; email_confidence?: string;
    };
  } | null ?? null;

  const tableData = enrichmentData.find((d) => d.data_type === 'company_contact' || d.data_type === 'company_event_profile');
  const raw = rawInsightData ?? (tableData?.data as unknown as typeof rawInsightData) ?? null;

  // v3 event profile data (different shape from v2 company_contact)
  const v3Profile = tableData?.data_type === 'company_event_profile'
    ? tableData.data as {
        company?: {
          cvent_status?: string; cvent_confidence?: number; event_volume_tier?: string;
          estimated_events_per_year?: number; complexity_tier?: string;
          estimated_budget_band?: string; budget_confidence?: number;
          outsourcing_tier?: string; outsourcing_propensity?: number;
          event_team_size?: number; event_team_under_resourced?: boolean;
          registration_urls?: string[]; pipeline_version?: string;
        };
        contact?: {
          title_inferred?: string; seniority_estimate?: string;
          department_estimate?: string; decision_maker_status?: string;
        };
      }
    : null;

  if (!rawInsightData && !v3Profile && !enrichmentData.find(d => d.data_type === 'company_contact')) {
    return (
      <div className="glass-card rounded-[28px] p-10 text-center">
        <Sparkles className="mx-auto h-8 w-8 text-slate-600 mb-3" />
        <p className="text-slate-500">No enrichment data yet — run enrichment to extract company intel.</p>
      </div>
    );
  }

  // Render v3 event profile if that's what we have
  if (v3Profile) {
    const cp = v3Profile.company;
    const ct = v3Profile.contact;
    const cventColor = cp?.cvent_status === 'confirmed' ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/20'
      : cp?.cvent_status === 'likely' ? 'bg-amber-500/15 text-amber-300 border-amber-500/20'
      : 'bg-white/10 text-slate-400 border-white/10';
    return (
      <div className="space-y-5">
        <div className="glass-card rounded-[28px] p-6">
          <div className="flex items-center gap-2 mb-4">
            <Zap className="h-4 w-4 text-indigo-400" />
            <h3 className="text-sm font-semibold text-white">Event Operations Profile</h3>
            <span className="ml-auto text-xs text-slate-500">v3 pipeline</span>
          </div>
          <div className="grid grid-cols-1 gap-x-10 lg:grid-cols-2">
            <div>
              <InfoRow label="Cvent Status" value={cp?.cvent_status ? (
                <span className={cn('text-xs rounded-full px-2.5 py-0.5 border font-semibold', cventColor)}>{cp.cvent_status}</span>
              ) : undefined} />
              <InfoRow label="Event Volume" value={cp?.event_volume_tier ? `${cp.event_volume_tier} (${cp.estimated_events_per_year ?? '?'} events/yr)` : undefined} />
              <InfoRow label="Complexity" value={cp?.complexity_tier} />
              <InfoRow label="Budget Band" value={cp?.estimated_budget_band} />
            </div>
            <div>
              <InfoRow label="Outsourcing" value={cp?.outsourcing_tier ? `${cp.outsourcing_tier}${cp.outsourcing_propensity != null ? ` (${Math.round((cp.outsourcing_propensity || 0) * 100)}%)` : ''}` : undefined} />
              <InfoRow label="Event Team" value={cp?.event_team_size ? `~${cp.event_team_size} people${cp.event_team_under_resourced ? ' · under-resourced' : ''}` : undefined} />
              {ct?.title_inferred && <InfoRow label="Contact Title" value={ct.title_inferred} />}
              {ct?.seniority_estimate && <InfoRow label="Seniority" value={ct.seniority_estimate} />}
              {ct?.decision_maker_status && <InfoRow label="Decision Maker" value={ct.decision_maker_status} />}
            </div>
          </div>
          {cp?.registration_urls && cp.registration_urls.length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">Cvent Registration URLs</p>
              <div className="space-y-1">
                {cp.registration_urls.slice(0, 4).map((url, i) => (
                  <a key={i} href={url} target="_blank" rel="noopener noreferrer"
                    className="flex items-center gap-1.5 text-xs text-indigo-400 hover:text-indigo-300 hover:underline truncate">
                    <ExternalLink className="h-3 w-3 shrink-0" />{url}
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  const company = rawInsightData?.company ?? (tableData?.data as typeof rawInsightData)?.company;
  const contact = rawInsightData?.contact ?? (tableData?.data as typeof rawInsightData)?.contact;

  return (
    <div className="space-y-5">
      {company && (
        <div className="glass-card rounded-[28px] p-6">
          <div className="flex items-center gap-2 mb-4">
            <Building2 className="h-4 w-4 text-indigo-400" />
            <h3 className="text-sm font-semibold text-white">Company Intelligence</h3>
          </div>
          <div className="grid grid-cols-1 gap-x-10 lg:grid-cols-2">
            <div>
              <InfoRow label="Name" value={toStr(company.name)} />
              <InfoRow label="Domain" value={toStr(company.domain)} />
              <InfoRow label="Industry" value={toStr(company.industry)} />
              <InfoRow label="Sub-sector" value={toStr(company.sub_sector)} />
              <InfoRow label="HQ" value={toStr(company.headquarters)} />
              <InfoRow label="Geographic Reach" value={toStr(company.geographic_reach)} />
              <InfoRow label="Business Model" value={toStr(company.business_model)} />
            </div>
            <div>
              <InfoRow label="Team Size" value={company.employee_count_estimate ? <span className="flex items-center gap-2">{toStr(company.employee_count_estimate)}<ConfidenceBadge level={company.employee_count_confidence} /></span> : undefined} />
              <InfoRow label="Revenue" value={company.revenue_estimate ? <span className="flex items-center gap-2">{toStr(company.revenue_estimate)}<ConfidenceBadge level={company.revenue_confidence} /></span> : undefined} />
              <InfoRow label="Funding Status" value={toStr(company.funding_status)} />
              <InfoRow label="Ownership" value={toStr(company.ownership_type)} />
            </div>
          </div>
          {company.products_and_services && company.products_and_services.length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">Products &amp; Services</p>
              <div className="flex flex-wrap gap-1.5">
                {company.products_and_services.map((s, i) => <span key={i} className="rounded-full bg-indigo-500/15 px-2.5 py-0.5 text-xs text-indigo-300 border border-indigo-500/20">{s}</span>)}
              </div>
            </div>
          )}
          {company.customer_segments && company.customer_segments.length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">Customer Segments</p>
              <div className="flex flex-wrap gap-1.5">
                {company.customer_segments.map((s, i) => <span key={i} className="rounded-full bg-white/10 px-2.5 py-0.5 text-xs text-slate-400">{s}</span>)}
              </div>
            </div>
          )}
          {company.key_competitors && company.key_competitors.length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">Key Competitors</p>
              <div className="flex flex-wrap gap-1.5">
                {company.key_competitors.map((c, i) => <span key={i} className="rounded-full bg-rose-500/15 px-2.5 py-0.5 text-xs text-rose-300 border border-rose-500/20">{c}</span>)}
              </div>
            </div>
          )}
          {company.data_gaps && company.data_gaps.length > 0 && (
            <div className="mt-4 rounded-2xl border border-amber-500/20 bg-amber-500/10 p-4">
              <div className="flex items-center gap-1.5 mb-2">
                <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />
                <p className="text-xs font-semibold text-amber-300">Data Gaps</p>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {company.data_gaps.map((gap, i) => <span key={i} className="rounded-full bg-amber-500/15 px-2.5 py-0.5 text-xs text-amber-300 border border-amber-500/20">{gap}</span>)}
              </div>
            </div>
          )}
        </div>
      )}

      {contact && (
        <div className="glass-card rounded-[28px] p-6">
          <div className="flex items-center gap-2 mb-4">
            <Users className="h-4 w-4 text-indigo-400" />
            <h3 className="text-sm font-semibold text-white">Contact Intelligence</h3>
          </div>
          <div className="grid grid-cols-1 gap-x-10 lg:grid-cols-2">
            <div>
              <InfoRow label="Title (raw)" value={toStr(contact.title_raw) ?? <span className="text-slate-400 italic">Not found</span>} />
              <InfoRow label="Title (inferred)" value={contact.title_inferred ? <span className="flex items-center gap-2">{toStr(contact.title_inferred)}{!contact.title_confirmed && <span className="text-xs text-slate-400 italic">unconfirmed</span>}</span> : undefined} />
              <InfoRow label="Seniority" value={contact.seniority_estimate ? <span className="flex items-center gap-2">{toStr(contact.seniority_estimate)}<ConfidenceBadge level={contact.seniority_confidence} /></span> : undefined} />
              <InfoRow label="Department" value={contact.department_estimate ? <span className="flex items-center gap-2">{toStr(contact.department_estimate)}<ConfidenceBadge level={contact.department_confidence} /></span> : undefined} />
            </div>
            <div>
              <InfoRow label="Decision Maker" value={contact.decision_maker_status ? <span className="flex items-center gap-2">{toStr(contact.decision_maker_status)}<ConfidenceBadge level={contact.decision_maker_confidence} /></span> : undefined} />
              <InfoRow label="Buying Authority" value={toStr(contact.buying_authority)} />
              <InfoRow label="Email" value={contact.email ? <span className="flex items-center gap-2">{toStr(contact.email)}<ConfidenceBadge level={contact.email_confidence} /></span> : undefined} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ──────────────────────────────── Shared signal labels ───────────────────────

const SIGNAL_LABELS: Record<string, string> = {
  // v3 signal names
  identity:          'Identity & Fit',
  cvent:             'Cvent Detection',
  event_volume:      'Event Volume',
  event_team:        'Event Team',
  hiring:            'Hiring Activity',
  budget:            'Budget Signal',
  outsourcing:       'Outsourcing Propensity',
  org_graph:         'Org Graph',
  targeted_research: 'Targeted Research',
  outreach:          'Outreach Intelligence',
  // v1/v2 signal names (legacy)
  cvent_events:      'Cvent Events',
  hiring_signal:     'Hiring Activity',
  org_fit:           'Org Fit',
  news_signal:       'News Signal',
  industry_fit:      'Industry Fit',
};

// ──────────────────────────────── Outreach Tab ───────────────────────────────

function OutreachTab({ outreach }: { outreach: OutreachIntelligence | null }) {
  const [copied, setCopied] = useState(false);

  if (!outreach) {
    return (
      <div className="glass-card rounded-[28px] p-10 text-center">
        <Megaphone className="mx-auto h-8 w-8 text-slate-600 mb-3" />
        <p className="font-semibold text-slate-400">No outreach intelligence yet</p>
        <p className="mt-1 text-sm text-slate-500">Run enrichment to generate a personalized outreach package.</p>
      </div>
    );
  }

  function copyEmail() {
    navigator.clipboard.writeText(outreach!.email_body);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="space-y-5">
      {/* Email Package */}
      <div className="glass-card-strong rounded-[28px] p-6">
        <div className="flex items-center gap-2 mb-5">
          <Mail className="h-4 w-4 text-indigo-400" />
          <h3 className="text-sm font-semibold text-white">Outreach Package</h3>
          {outreach.recommended_contact_role && (
            <span className="ml-2 text-xs rounded-full bg-indigo-500/15 border border-indigo-500/20 text-indigo-300 px-2.5 py-0.5">
              Target: {outreach.recommended_contact_role}
            </span>
          )}
          <button
            onClick={copyEmail}
            className="ml-auto inline-flex items-center gap-1.5 rounded-full border border-white/[0.1] bg-white/[0.05] px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-white/[0.08]"
          >
            {copied ? <CheckCircle2 className="h-3 w-3 text-emerald-400" /> : <Send className="h-3 w-3" />}
            {copied ? 'Copied!' : 'Copy email'}
          </button>
        </div>

        {outreach.subject_line && (
          <div className="mb-4 rounded-xl border border-white/[0.06] bg-white/[0.03] p-4">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Subject Line</p>
            <p className="text-sm font-medium text-white">{outreach.subject_line}</p>
          </div>
        )}

        {outreach.email_body && (
          <div className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Email Body</p>
            <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-line">{outreach.email_body}</p>
          </div>
        )}
      </div>

      {/* Angles + Timing */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {outreach.angles.length > 0 && (
          <div className="glass-card rounded-[28px] p-6">
            <div className="flex items-center gap-2 mb-4">
              <Lightbulb className="h-4 w-4 text-amber-400" />
              <h3 className="text-sm font-semibold text-white">Outreach Angles</h3>
            </div>
            <div className="space-y-3">
              {outreach.angles.map((angle, i) => (
                <div key={i} className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-3">
                  <p className="text-sm font-medium text-slate-200">{angle.angle}</p>
                  <p className="text-xs text-slate-500 mt-1">{angle.why}</p>
                  {angle.backed_by_signal && angle.backed_by_signal !== 'unknown' && (
                    <span className="mt-1.5 inline-flex text-[10px] font-semibold rounded-full bg-indigo-500/15 border border-indigo-500/20 text-indigo-300 px-2 py-0.5">
                      {SIGNAL_LABELS[angle.backed_by_signal] ?? angle.backed_by_signal}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-4">
          {(outreach.timing_recommendation || outreach.timing_rationale) && (
            <div className="glass-card rounded-[28px] p-6">
              <div className="flex items-center gap-2 mb-3">
                <Clock className="h-4 w-4 text-indigo-400" />
                <h3 className="text-sm font-semibold text-white">Timing</h3>
              </div>
              {outreach.timing_recommendation && (
                <p className="text-sm font-medium text-slate-200">{outreach.timing_recommendation}</p>
              )}
              {outreach.timing_rationale && (
                <p className="text-xs text-slate-500 mt-1">{outreach.timing_rationale}</p>
              )}
            </div>
          )}

          {outreach.service_recommendations.length > 0 && (
            <div className="glass-card rounded-[28px] p-6">
              <div className="flex items-center gap-2 mb-4">
                <Star className="h-4 w-4 text-amber-400" />
                <h3 className="text-sm font-semibold text-white">Service Recommendations</h3>
              </div>
              <div className="space-y-3">
                {outreach.service_recommendations.map((rec, i) => (
                  <div key={i} className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-3">
                    <p className="text-sm font-medium text-slate-200">{rec.service}</p>
                    <p className="text-xs text-slate-500 mt-1">{rec.rationale}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Event References */}
      {outreach.event_references.length > 0 && (
        <div className="glass-card rounded-[28px] p-6">
          <div className="flex items-center gap-2 mb-4">
            <CalendarDays className="h-4 w-4 text-indigo-400" />
            <h3 className="text-sm font-semibold text-white">Event References</h3>
            <span className="ml-auto text-xs text-slate-500">{outreach.event_references.length} event(s) cited</span>
          </div>
          <div className="space-y-3">
            {outreach.event_references.map((ref, i) => (
              <div key={i} className="flex items-start gap-3 rounded-xl border border-indigo-500/20 bg-indigo-500/10 p-4">
                <Zap className="mt-0.5 h-3.5 w-3.5 shrink-0 text-indigo-400" />
                <div className="flex-1">
                  <div className="flex flex-wrap items-center gap-2 mb-1">
                    <p className="text-sm font-semibold text-slate-200">{ref.event_name}</p>
                    {ref.source_url && (
                      <a href={ref.source_url} target="_blank" rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300">
                        <ExternalLink className="h-3 w-3" />
                        Source
                      </a>
                    )}
                  </div>
                  <p className="text-xs text-slate-400">{ref.detail}</p>
                  <p className="text-xs text-slate-500 mt-1 italic">{ref.why_relevant}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Generation basis */}
      {outreach.generation_basis && Object.keys(outreach.generation_basis).length > 0 && (
        <div className="rounded-[28px] border border-white/[0.06] bg-white/[0.02] p-5">
          <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide mb-3">Generated from</p>
          <div className="flex flex-wrap gap-2">
            {(outreach.generation_basis.signals_used as string[] | undefined)?.map((s) => (
              <span key={s} className="rounded-full bg-white/[0.06] border border-white/[0.08] px-2.5 py-0.5 text-xs text-slate-400">
                {SIGNAL_LABELS[s] ?? s}
              </span>
            ))}
            {outreach.generation_basis.evidence_count != null && (
              <span className="rounded-full bg-white/[0.06] border border-white/[0.08] px-2.5 py-0.5 text-xs text-slate-400">
                {String(outreach.generation_basis.evidence_count)} evidence items
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ──────────────────────────────── Scoring Tab ─────────────────────────────────

function SignalRow({ signal }: { signal: SignalDetail }) {
  const [expanded, setExpanded] = useState(false);
  const pct = Math.round(signal.score * 100);
  const tier = signal.score >= 0.6 ? 'high' : signal.score >= 0.35 ? 'medium' : 'low';
  const barColor = tier === 'high' ? 'bg-emerald-400' : tier === 'medium' ? 'bg-amber-400' : 'bg-rose-400';
  const scoreColor = tier === 'high' ? 'text-emerald-300' : tier === 'medium' ? 'text-amber-300' : 'text-rose-300';

  return (
    <div className="border-b border-white/[0.06] last:border-0 py-3">
      <div className="flex cursor-pointer items-center gap-4" onClick={() => setExpanded((v) => !v)}>
        <div className="w-48 shrink-0 text-sm font-medium text-slate-300">{signal.signal_name}</div>
        <div className="flex-1 h-2 overflow-hidden rounded-full bg-white/10">
          <div className={cn('h-full rounded-full transition-all', barColor)} style={{ width: `${pct}%` }} />
        </div>
        <div className={cn('w-10 text-right text-sm font-semibold tabular-nums', scoreColor)}>{pct}%</div>
        <div className="w-16 text-right text-xs text-slate-500 shrink-0">wt {Math.round(signal.weight * 100)}%</div>
        <button className="ml-1 text-slate-500 hover:text-slate-300 transition-colors">
          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
      </div>
      {expanded && (
        <div className="mt-2 ml-52 rounded-xl bg-white/[0.04] border border-white/[0.06] px-4 py-3">
          <p className="text-xs text-slate-400 leading-relaxed">{signal.reasoning}</p>
        </div>
      )}
    </div>
  );
}

function reasoningFromEvidence(signalType: string, evidence: Record<string, unknown>): string {
  switch (signalType) {
    // ── v3 signal types ──
    case 'cvent': {
      const detected = evidence.detected as boolean | undefined;
      const count = evidence.upcoming_count as number | undefined;
      const days = evidence.soonest_days as number | undefined;
      if (detected) {
        const base = 'Cvent usage confirmed';
        if (days != null && days >= 0) return `${base} · ${count ?? '?'} upcoming event(s), soonest in ${days}d`;
        return base;
      }
      return 'Cvent usage not confirmed';
    }
    case 'event_volume': {
      const epy = evidence.estimated_events_per_year as number | null | undefined;
      const cmx = evidence.complexity_tier as string | undefined;
      return `~${epy ?? '?'} events/year · complexity: ${cmx ?? 'unknown'}`;
    }
    case 'event_team': {
      const size = evidence.event_team_size as number | undefined;
      const under = evidence.under_resourced as boolean | undefined;
      return size ? `Team size ~${size}${under ? ' (under-resourced)' : ''}` : 'Event team data unavailable';
    }
    case 'hiring': {
      const roles = evidence.roles as Array<{title?: string}> | undefined;
      if (roles?.length) return `${roles.length} event role(s) open: ${roles.slice(0, 2).map(r => r.title).join(', ')}`;
      return 'No open event roles found';
    }
    case 'budget': {
      const band = evidence.estimated_budget_band as string | undefined;
      const annual = evidence.estimated_annual_usd as number | undefined;
      return band ? `Est. budget ${band}${annual ? ` (~$${(annual/1000).toFixed(0)}k/yr)` : ''}` : 'Budget estimate unavailable';
    }
    case 'outsourcing': {
      const tier = evidence.outsourcing_tier as string | undefined;
      return tier ? `Outsourcing propensity: ${tier}` : 'Outsourcing signal unavailable';
    }
    case 'identity':
      return (evidence.reason as string | undefined) ?? 'Identity & fit assessed';
    case 'org_graph': {
      const hc = evidence.headcount_total as number | undefined;
      return hc ? `Org size ~${hc.toLocaleString()} headcount` : 'Org data assessed';
    }
    case 'targeted_research': {
      const gaps = evidence.gaps as number | undefined;
      return gaps ? `Targeted ${gaps} data gap(s)` : 'All signals above confidence threshold';
    }
    // ── v1/v2 legacy signal types ──
    case 'cvent_events': {
      const days = evidence.soonest_days as number | undefined;
      const count = evidence.upcoming_count as number | undefined;
      if (days != null && days >= 0) return `${count ?? '?'} upcoming event(s) — soonest in ${days}d`;
      const pages = evidence.total_pages_found as number | undefined;
      return pages ? `${pages} Cvent page(s) found, no upcoming dates confirmed` : 'No Cvent pages found';
    }
    case 'hiring_signal': {
      const kw = evidence.matched_keywords as string[] | undefined;
      return kw?.length ? `${kw.length} role keyword(s) matched: ${kw.slice(0, 3).join(', ')}` : 'No event job postings found';
    }
    case 'org_fit': {
      const sen = evidence.seniority_label as string | undefined;
      const dept = evidence.department_label as string | undefined;
      const size = evidence.company_size as number | string | undefined;
      return `Seniority: ${sen ?? '?'} · Dept: ${dept ?? '?'} · Size: ${size ?? '?'}`;
    }
    case 'news_signal':
      return (evidence.reason as string | undefined) ?? 'No relevant news';
    case 'industry_fit':
      return `Industry: ${evidence.industry_raw as string | undefined ?? '?'} → ${evidence.matched_label as string | undefined ?? '?'}`;
    default:
      return 'No evidence available';
  }
}

function ScoringTab({ score, insights }: { score: ScoreData | null; insights: AIInsight[] }) {
  const scoreInsight = insights.find((i) => i.type === 'lead_score');
  const rawSignals = (scoreInsight?.source_data as { signals?: SignalDetail[] } | null)?.signals ?? [];

  const signals: SignalDetail[] =
    rawSignals.length > 0
      ? rawSignals
      : score?.signal_breakdown
      ? Object.entries(score.signal_breakdown).map(([stype, detail]) => ({
          signal_name: SIGNAL_LABELS[stype] ?? stype,
          score: detail.value,
          weight: detail.weight,
          reasoning: reasoningFromEvidence(stype, detail.evidence ?? {}),
        }))
      : score
      ? Object.entries(score.signal_scores).map(([name, val]) => ({
          signal_name: SIGNAL_LABELS[name] ?? name,
          score: val,
          weight: 0.1,
          reasoning: 'Detailed reasoning not available.',
        }))
      : [];

  const dataGaps = signals.filter((s) => s.score < 0.3);

  if (!score) {
    return (
      <div className="glass-card rounded-[28px] p-10 text-center">
        <Sparkles className="mx-auto h-8 w-8 text-slate-600 mb-3" />
        <p className="text-slate-500">Lead hasn&apos;t been scored yet.</p>
      </div>
    );
  }

  const tier = tierConfig[score.tier] ?? tierConfig.cold;

  return (
    <div className="space-y-5">
      <div className="glass-card-strong rounded-[28px] p-8">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-center">
          <div className="flex items-end gap-4">
            <span className={cn('text-8xl font-extrabold tracking-tight', tier.scoreColor)}>
              {Math.round(score.overall_score)}
            </span>
            <div className="mb-2 flex flex-col gap-2">
              <span className="text-xl text-slate-500">/ 100</span>
              <span className={cn('inline-flex items-center rounded-full px-3 py-1 text-sm font-bold', tier.bg, tier.text)}>
                {tier.label}
              </span>
            </div>
          </div>
          <div className="flex-1">
            <div className="h-3 w-full overflow-hidden rounded-full bg-white/10 mb-3">
              <div className={cn('h-full rounded-full transition-all', tier.barColor)} style={{ width: `${score.overall_score}%` }} />
            </div>
            {score.model && (
              <p className="text-xs text-slate-500">
                Scored by {score.model} · {new Date(score.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
              </p>
            )}
          </div>
        </div>
        {score.explanation && (
          <div className="mt-6 rounded-2xl bg-white/[0.04] border border-white/[0.06] p-4">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Scoring Rationale</p>
            <p className="text-sm text-slate-300 leading-relaxed">{score.explanation}</p>
          </div>
        )}
      </div>

      {signals.length > 0 && (
        <div className="glass-card rounded-[28px] p-6">
          <div className="flex items-center gap-2 mb-1">
            <Target className="h-4 w-4 text-indigo-400" />
            <h3 className="text-sm font-semibold text-white">Signal Breakdown</h3>
            <span className="ml-auto text-xs text-slate-500">Click a signal to see AI reasoning</span>
          </div>
          <p className="text-xs text-slate-500 mb-4">{signals.length} signals evaluated · lower score = weaker fit</p>
          <div>
            {[...signals].sort((a, b) => b.score - a.score).map((s, i) => (
              <SignalRow key={i} signal={s} />
            ))}
          </div>
        </div>
      )}

      {dataGaps.length > 0 && (
        <div className="rounded-[28px] border border-amber-500/20 bg-amber-500/10 p-6">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle className="h-4 w-4 text-amber-400" />
            <h3 className="text-sm font-semibold text-amber-300">Weak Signals / Data Gaps</h3>
          </div>
          <p className="text-xs text-amber-400/80 mb-4">
            These signals scored below 30% — likely due to missing data or poor fit. Gather more context to improve accuracy.
          </p>
          <div className="space-y-3">
            {dataGaps.map((s, i) => (
              <div key={i} className="flex items-start gap-3 rounded-xl bg-amber-500/15 border border-amber-500/20 px-4 py-3">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400" />
                <div>
                  <p className="text-sm font-semibold text-amber-300">{s.signal_name}</p>
                  <p className="text-xs text-amber-400/80 mt-0.5">{s.reasoning}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ──────────────────────────────── Activity Tab ───────────────────────────────

function formatTs(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

const EMAIL_STATUS_CFG: Record<string, { icon: React.ReactNode; dot: string; label: string }> = {
  sent:      { icon: <Send className="h-3.5 w-3.5" />,         dot: 'bg-emerald-500', label: 'Sent' },
  delivered: { icon: <CheckCircle2 className="h-3.5 w-3.5" />, dot: 'bg-emerald-600', label: 'Delivered' },
  draft:     { icon: <Mail className="h-3.5 w-3.5" />,         dot: 'bg-slate-400',   label: 'Draft' },
  queued:    { icon: <Clock className="h-3.5 w-3.5" />,        dot: 'bg-amber-400',   label: 'Queued' },
  sending:   { icon: <Clock className="h-3.5 w-3.5" />,        dot: 'bg-amber-500',   label: 'Sending' },
  failed:    { icon: <XCircle className="h-3.5 w-3.5" />,      dot: 'bg-rose-500',    label: 'Failed' },
  bounced:   { icon: <XCircle className="h-3.5 w-3.5" />,      dot: 'bg-rose-400',    label: 'Bounced' },
};

const ENRICH_STATUS_CFG: Record<string, { dot: string; label: string }> = {
  completed:  { dot: 'bg-emerald-500', label: 'Completed' },
  processing: { dot: 'bg-amber-400 animate-pulse', label: 'Running' },
  pending:    { dot: 'bg-slate-400',   label: 'Pending' },
  failed:     { dot: 'bg-rose-500',    label: 'Failed' },
};

function ActivityTab({ leadId }: { leadId: string }) {
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  async function fetchActivity(quiet = false) {
    if (!quiet) setLoading(true); else setRefreshing(true);
    try {
      const data = await api<ActivityEvent[]>({ method: 'GET', url: `/leads/${leadId}/activity` });
      setEvents(Array.isArray(data) ? data : []);
    } catch {
      setEvents([]);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => { fetchActivity(); }, [leadId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-16 text-slate-500">
        <div className="h-4 w-4 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
        Loading activity…
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <div className="glass-card rounded-[28px] p-10 text-center">
        <Clock className="mx-auto h-8 w-8 text-slate-600 mb-3" />
        <p className="font-semibold text-slate-400">No activity yet</p>
        <p className="mt-1 text-sm text-slate-500">Activity will appear once emails are sent or enrichment runs.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between px-1">
        <p className="text-xs text-slate-400">{events.length} event{events.length !== 1 ? 's' : ''}</p>
        <button
          onClick={() => fetchActivity(true)}
          disabled={refreshing}
          className="inline-flex items-center gap-1.5 rounded-full border border-white/[0.1] bg-white/[0.05] px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-white/[0.08] disabled:opacity-50"
        >
          <RefreshCw className={cn('h-3 w-3', refreshing && 'animate-spin')} />
          Refresh
        </button>
      </div>
      {events.map((ev) => {
        if (ev.type === 'email') {
          const cfg = EMAIL_STATUS_CFG[ev.status] ?? EMAIL_STATUS_CFG.draft;
          return (
            <div key={ev.id} className="glass-card flex items-start gap-4 rounded-[22px] p-4">
              <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-indigo-500/15 text-indigo-300">
                {cfg.icon}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold text-slate-200">{ev.subject ?? '(No subject)'}</span>
                  <span className={cn('flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold border',
                    ev.status === 'failed' || ev.status === 'bounced' ? 'bg-rose-500/15 text-rose-300 border-rose-500/20' :
                    ev.status === 'sent' || ev.status === 'delivered' ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/20' :
                    'bg-white/10 text-slate-400 border-white/10'
                  )}>
                    <span className={cn('h-1.5 w-1.5 rounded-full', cfg.dot)} />
                    {cfg.label}
                  </span>
                  {ev.ai_generated && (
                    <span className="rounded-full bg-violet-500/15 px-2 py-0.5 text-[10px] font-semibold text-violet-300 border border-violet-500/20">AI</span>
                  )}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                  <span>{formatTs(ev.ts)}</span>
                  {ev.campaign_name && <span className="rounded-full bg-indigo-500/15 px-2 py-0.5 text-[10px] font-semibold text-indigo-300 border border-indigo-500/20">{ev.campaign_name}</span>}
                  {ev.sequence_step != null && <span>Step {ev.sequence_step + 1}</span>}
                </div>
                {ev.error && <p className="mt-1 text-xs text-rose-400">{ev.error}</p>}
              </div>
            </div>
          );
        }

        if (ev.type === 'enrichment') {
          const cfg = ENRICH_STATUS_CFG[ev.status] ?? ENRICH_STATUS_CFG.pending;
          return (
            <div key={ev.id} className="glass-card flex items-start gap-4 rounded-[22px] p-4">
              <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-amber-500/15 text-amber-300">
                <RotateCcw className="h-3.5 w-3.5" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold text-slate-200">{ev.job_label ?? ev.job_type}</span>
                  <span className={cn('flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold border',
                    ev.status === 'completed' ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/20' :
                    ev.status === 'failed' ? 'bg-rose-500/15 text-rose-300 border-rose-500/20' :
                    'bg-amber-500/15 text-amber-300 border-amber-500/20'
                  )}>
                    <span className={cn('h-1.5 w-1.5 rounded-full', cfg.dot)} />
                    {cfg.label}
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                  <span>{formatTs(ev.ts)}</span>
                  {ev.duration_ms != null && <span>{(ev.duration_ms / 1000).toFixed(1)}s</span>}
                  {ev.tokens_used != null && <span>{ev.tokens_used} tokens</span>}
                </div>
                {ev.error && <p className="mt-1 text-xs text-rose-400">{ev.error}</p>}
              </div>
            </div>
          );
        }

        // campaign enrollment
        return (
          <div key={ev.id} className="glass-card flex items-start gap-4 rounded-[22px] p-4">
            <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-300">
              <Zap className="h-3.5 w-3.5" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-slate-200">Added to campaign</span>
                {ev.campaign_name && (
                  <span className="rounded-full bg-indigo-500/15 px-2 py-0.5 text-[10px] font-semibold text-indigo-300 border border-indigo-500/20">{ev.campaign_name}</span>
                )}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                <span>{formatTs(ev.ts)}</span>
                <span className="capitalize">{ev.status}</span>
                {ev.current_step != null && ev.current_step > 0 && <span>Step {ev.current_step}</span>}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ──────────────────────────────── Main Page ───────────────────────────────────

const TABS = ['Overview', 'Research', 'Enrichment', 'Outreach', 'Scoring', 'Activity'] as const;
type Tab = (typeof TABS)[number];

export default function LeadDetailPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const [activeTab, setActiveTab] = useState<Tab>('Overview');
  const [lead, setLead] = useState<LeadDetail | null>(null);
  const [score, setScore] = useState<ScoreData | null>(null);
  const [insights, setInsights] = useState<AIInsight[]>([]);
  const [research, setResearch] = useState<ResearchItem[]>([]);
  const [enrichmentData, setEnrichmentData] = useState<EnrichmentDataItem[]>([]);
  const [outreach, setOutreach] = useState<OutreachIntelligence | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [leadResult, scoreResult, insightsResult, researchResult, enrichResult, outreachResult] = await Promise.allSettled([
          api<LeadDetail>({ method: 'GET', url: `/leads/${id}` }),
          api<ScoreData>({ method: 'GET', url: `/enrichment/lead/${id}/score` }),
          api<AIInsight[]>({ method: 'GET', url: `/enrichment/lead/${id}/insights` }),
          api<ResearchItem[]>({ method: 'GET', url: `/enrichment/lead/${id}/research` }),
          api<EnrichmentDataItem[]>({ method: 'GET', url: `/enrichment/lead/${id}/data` }),
          api<OutreachIntelligence>({ method: 'GET', url: `/enrichment/lead/${id}/outreach` }),
        ]);
        if (leadResult.status === 'fulfilled') setLead(leadResult.value);
        else setError('Lead not found');
        if (scoreResult.status === 'fulfilled') setScore(scoreResult.value);
        if (insightsResult.status === 'fulfilled') setInsights(insightsResult.value);
        if (researchResult.status === 'fulfilled') setResearch(researchResult.value);
        if (enrichResult.status === 'fulfilled') setEnrichmentData(enrichResult.value);
        if (outreachResult.status === 'fulfilled') setOutreach(outreachResult.value);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id]);

  const contact = lead?.contact;
  const company = lead?.company;
  const fullName = contact ? `${contact.first_name} ${contact.last_name}`.trim() : 'Unknown Contact';
  const tierCfg = score ? (tierConfig[score.tier] ?? tierConfig.cold) : null;

  const researchInsight = insights.find((i) => i.type === 'research_summary');
  const overviewEvents: EventItem[] = (researchInsight?.source_data as { events_attended?: EventItem[] } | null)
    ?.events_attended ?? [];

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
      </div>
    );
  }

  if (error || !lead) {
    return (
      <div className="glass-card rounded-[28px] p-10 text-center">
        <p className="text-slate-500">{error ?? 'Lead not found'}</p>
        <Link href="/leads" className="mt-4 inline-flex items-center gap-1.5 text-sm text-indigo-400 hover:text-indigo-300 hover:underline">
          <ArrowLeft className="h-4 w-4" /> Back to leads
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Hero */}
      <section className="glass-card-strong data-grid rounded-[28px] p-6">
        <Link href="/leads" className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors mb-4">
          <ArrowLeft className="h-3.5 w-3.5" />
          All Leads
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-[1.75rem] font-extrabold tracking-[-0.04em] text-white">{fullName}</h1>
            <div className="mt-1.5 flex flex-wrap items-center gap-3">
              {contact?.title && <span className="text-sm text-slate-400">{contact.title}</span>}
              {company?.name && (
                <span className="flex items-center gap-1 text-sm text-slate-400">
                  <Building2 className="h-3.5 w-3.5" />
                  {company.name}
                </span>
              )}
              {contact?.email && (
                <a href={`mailto:${contact.email}`} className="flex items-center gap-1 text-sm text-indigo-400 hover:text-indigo-300 hover:underline">
                  <Mail className="h-3.5 w-3.5" />
                  {contact.email}
                </a>
              )}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {lead.enrichment_status && (
              <Badge
                label={(enrichmentStatusConfig[lead.enrichment_status] ?? { label: lead.enrichment_status, className: '' }).label}
                className={(enrichmentStatusConfig[lead.enrichment_status] ?? { label: lead.enrichment_status, className: 'bg-white/10 text-slate-300' }).className}
              />
            )}
            {lead.status && (
              <Badge
                label={(statusConfig[lead.status] ?? { label: lead.status, className: '' }).label}
                className={(statusConfig[lead.status] ?? { label: lead.status, className: 'bg-white/10 text-slate-300' }).className}
              />
            )}
            {score && tierCfg && (
              <span className={cn('inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold', tierCfg.bg, tierCfg.text)}>
                <Sparkles className="h-3 w-3" />
                {Math.round(score.overall_score)} · {tierCfg.label}
              </span>
            )}
          </div>
        </div>
      </section>

      {/* Tab Nav */}
      <div className="border-b border-white/[0.08]">
        <nav className="-mb-px flex space-x-1">
          {TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={cn(
                'whitespace-nowrap border-b-2 px-4 py-3 text-sm font-semibold transition-colors',
                activeTab === tab ? 'border-indigo-400 text-white' : 'border-transparent text-slate-500 hover:border-white/20 hover:text-slate-300'
              )}
            >
              {tab}
              {tab === 'Scoring' && score && (
                <span className={cn('ml-1.5 inline-flex h-4 w-7 items-center justify-center rounded-full text-[10px] font-bold', tierCfg?.bg ?? 'bg-white/10', tierCfg?.text ?? 'text-slate-400')}>
                  {Math.round(score.overall_score)}
                </span>
              )}
              {tab === 'Outreach' && outreach && (
                <span className="ml-1.5 inline-flex h-4 w-4 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-300 text-[9px] font-bold">
                  ✓
                </span>
              )}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab Content */}
      {activeTab === 'Overview' && <OverviewTab lead={lead} score={score} events={overviewEvents} />}
      {activeTab === 'Research' && <ResearchTab insights={insights} research={research} />}
      {activeTab === 'Enrichment' && <EnrichmentTab insights={insights} enrichmentData={enrichmentData} />}
      {activeTab === 'Outreach' && <OutreachTab outreach={outreach} />}
      {activeTab === 'Scoring' && <ScoringTab score={score} insights={insights} />}
      {activeTab === 'Activity' && <ActivityTab leadId={id} />}
    </div>
  );
}

