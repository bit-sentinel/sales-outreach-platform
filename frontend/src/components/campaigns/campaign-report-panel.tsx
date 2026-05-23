'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  Building2,
  Calendar,
  ChevronDown,
  ChevronUp,
  Clock,
  FileText,
  Loader2,
  Mail,
  MailOpen,
  MailQuestion,
  MessageSquare,
  MessageSquareReply,
  RefreshCw,
  Send,
  Tag,
  User,
  X,
  Zap,
} from 'lucide-react';
import { api } from '@/lib/api-client';
import { cn } from '@/lib/utils';

// ── Types ──────────────────────────────────────────────────────────────────

interface ReportReply {
  id: string;
  received_at: string;
  subject: string | null;
  body_text: string | null;
  body_html: string | null;
  intent: string | null;
  sentiment: string | null;
  responded_at: string | null;
  response_body: string | null;
}

interface ReportMessage {
  id: string;
  sequence_step: number | null;
  step_label: string;
  subject: string | null;
  body_html: string | null;
  body_text: string | null;
  status: string;
  sent_at: string | null;
  delivered_at: string | null;
  opened_at: string | null;
  ai_generated: boolean;
  replies: ReportReply[];
}

interface ReportLead {
  lead_id: string;
  name: string | null;
  email: string | null;
  effective_email: string | null;
  company: string | null;
  title: string | null;
  campaign_status: string;
  messages: ReportMessage[];
}

interface SequenceStep {
  step: int;
  delay_days: number;
  channel: string;
  subject_template: string | null;
  ai_generate: boolean;
}

// We use `int` at runtime as `number` in TS
type int = number;

interface CampaignReport {
  id: string;
  name: string;
  description: string | null;
  status: string;
  campaign_type: string;
  vertical: string | null;
  test_mode_enabled: boolean;
  test_emails: string[];
  from_email: string | null;
  from_name: string | null;
  created_at: string;
  launched_at: string | null;
  completed_at: string | null;
  total_leads: number;
  sent_count: number;
  open_count: number;
  reply_count: number;
  bounce_count: number;
  sequence: SequenceStep[];
  leads: ReportLead[];
}

interface Props {
  campaignId: string;
  campaignName: string;
  onClose: () => void;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function fmtDate(iso: string | null, opts?: Intl.DateTimeFormatOptions): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: 'numeric', minute: '2-digit',
    ...opts,
  });
}

function fmtShort(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-US', {
    month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit',
  });
}

const intentColors: Record<string, string> = {
  interested:      'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  not_interested:  'bg-rose-500/20 text-rose-300 border-rose-500/30',
  question:        'bg-sky-500/20 text-sky-300 border-sky-500/30',
  auto_reply:      'bg-white/10 text-white/40 border-white/10',
  meeting_request: 'bg-violet-500/20 text-violet-300 border-violet-500/30',
  unsubscribe:     'bg-amber-500/20 text-amber-300 border-amber-500/30',
};

const sentimentColors: Record<string, string> = {
  positive: 'text-emerald-400',
  neutral:  'text-white/50',
  negative: 'text-rose-400',
};

const leadStatusConfig: Record<string, { label: string; cls: string }> = {
  pending:       { label: 'Pending',       cls: 'bg-white/[0.08] text-white/40 border-white/[0.1]' },
  active:        { label: 'Active',        cls: 'bg-sky-500/15 text-sky-300 border-sky-500/30' },
  completed:     { label: 'Completed',     cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30' },
  replied:       { label: 'Replied',       cls: 'bg-violet-500/15 text-violet-300 border-violet-500/30' },
  bounced:       { label: 'Bounced',       cls: 'bg-rose-500/15 text-rose-300 border-rose-500/30' },
  unsubscribed:  { label: 'Unsubscribed',  cls: 'bg-amber-500/15 text-amber-300 border-amber-500/30' },
  paused:        { label: 'Paused',        cls: 'bg-amber-500/15 text-amber-300 border-amber-500/30' },
};

const msgStatusConfig: Record<string, { label: string; cls: string; icon: React.ElementType }> = {
  draft:     { label: 'Draft',     cls: 'bg-white/[0.08] text-white/50',     icon: FileText  },
  queued:    { label: 'Queued',    cls: 'bg-blue-500/15 text-blue-300',      icon: Clock     },
  sending:   { label: 'Sending',   cls: 'bg-sky-500/15 text-sky-300',        icon: Send      },
  sent:      { label: 'Sent',      cls: 'bg-emerald-500/15 text-emerald-300', icon: Mail     },
  delivered: { label: 'Delivered', cls: 'bg-teal-500/15 text-teal-300',      icon: MailOpen  },
  bounced:   { label: 'Bounced',   cls: 'bg-rose-500/15 text-rose-300',      icon: AlertCircle },
  failed:    { label: 'Failed',    cls: 'bg-rose-500/15 text-rose-300',      icon: AlertCircle },
};

function Initials({ name }: { name: string | null }) {
  const parts = (name ?? '?').trim().split(' ');
  const text = parts.length >= 2
    ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
    : (parts[0][0] ?? '?').toUpperCase();
  return (
    <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#1c8ed4] to-[#12344d] text-xs font-bold text-white">
      {text}
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────

function EmailBodyPreview({ html, text }: { html: string | null; text: string | null }) {
  const [expanded, setExpanded] = useState(false);
  const preview = text?.slice(0, 120) + (text && text.length > 120 ? '…' : '');
  return (
    <div className="mt-2">
      {!expanded ? (
        <div className="flex items-start gap-2">
          <p className="flex-1 text-xs leading-relaxed text-white/40 line-clamp-2">{preview || '—'}</p>
          {(html || text) && (
            <button onClick={() => setExpanded(true)} className="flex-shrink-0 text-[10px] font-semibold text-[#1c8ed4] hover:underline whitespace-nowrap">
              Read more
            </button>
          )}
        </div>
      ) : (
        <div>
          {html ? (
            <iframe
              srcDoc={html}
              className="w-full rounded-xl border border-white/[0.07] bg-white"
              style={{ height: 320 }}
              sandbox="allow-same-origin"
            />
          ) : (
            <pre className="whitespace-pre-wrap rounded-xl border border-white/[0.07] bg-white/[0.03] p-4 text-xs leading-relaxed text-white/70">
              {text}
            </pre>
          )}
          <button onClick={() => setExpanded(false)} className="mt-1 text-[10px] font-semibold text-[#1c8ed4] hover:underline">
            Collapse
          </button>
        </div>
      )}
    </div>
  );
}

function ReplyCard({ reply, idx }: { reply: ReportReply; idx: number }) {
  const intentCls = intentColors[reply.intent ?? ''] ?? 'bg-white/[0.07] text-white/40 border-white/[0.1]';
  const sentimentCls = sentimentColors[reply.sentiment ?? ''] ?? 'text-white/40';
  return (
    <div className="ml-8 mt-2 rounded-xl border border-violet-500/20 bg-violet-500/[0.06] p-3.5">
      {/* Reply header */}
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <div className="flex items-center gap-1.5">
          <MessageSquare className="h-3.5 w-3.5 text-violet-400" />
          <span className="text-[11px] font-bold text-violet-300">Reply received</span>
        </div>
        <span className="text-[10px] text-white/35">{fmtShort(reply.received_at)}</span>
        {reply.intent && (
          <span className={cn('rounded-full border px-2 py-0.5 text-[10px] font-semibold capitalize', intentCls)}>
            {reply.intent.replace(/_/g, ' ')}
          </span>
        )}
        {reply.sentiment && (
          <span className={cn('text-[10px] font-semibold capitalize', sentimentCls)}>
            {reply.sentiment}
          </span>
        )}
      </div>
      {reply.subject && (
        <p className="mb-1 text-[11px] font-semibold text-white/60">Subject: {reply.subject}</p>
      )}
      <EmailBodyPreview html={reply.body_html} text={reply.body_text} />

      {/* Our response */}
      {reply.responded_at && (
        <div className="ml-4 mt-3 rounded-lg border border-emerald-500/20 bg-emerald-500/[0.06] p-3">
          <div className="flex items-center gap-1.5 mb-1.5">
            <MessageSquareReply className="h-3 w-3 text-emerald-400" />
            <span className="text-[11px] font-bold text-emerald-300">Response sent</span>
            <span className="text-[10px] text-white/35">{fmtShort(reply.responded_at)}</span>
          </div>
          {reply.response_body ? (
            <p className="text-xs leading-relaxed text-white/50 line-clamp-3">{reply.response_body}</p>
          ) : (
            <p className="text-[10px] text-white/30 italic">Response sent (content not stored)</p>
          )}
        </div>
      )}
    </div>
  );
}

function MessageRow({ message, isLast }: { message: ReportMessage; isLast: boolean }) {
  const [open, setOpen] = useState(false);
  const cfg = msgStatusConfig[message.status] ?? msgStatusConfig.draft;
  const StatusIcon = cfg.icon;
  const hasReplies = message.replies.length > 0;

  return (
    <div className="relative">
      {/* Vertical connector line */}
      {!isLast && (
        <div className="absolute left-[15px] top-8 bottom-0 w-px bg-white/[0.07]" />
      )}

      <div className="relative flex gap-3">
        {/* Step icon bubble */}
        <div className={cn(
          'flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full border text-[10px] font-bold',
          message.status === 'sent' || message.status === 'delivered'
            ? 'border-emerald-500/40 bg-emerald-500/15 text-emerald-300'
            : message.status === 'bounced' || message.status === 'failed'
            ? 'border-rose-500/40 bg-rose-500/15 text-rose-300'
            : 'border-white/[0.12] bg-white/[0.06] text-white/40'
        )}>
          <StatusIcon className="h-3.5 w-3.5" />
        </div>

        <div className="flex-1 pb-4">
          {/* Message header row */}
          <button
            onClick={() => setOpen((v) => !v)}
            className="flex w-full items-start justify-between gap-2 text-left"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-sky-500/30 bg-sky-500/15 px-2 py-0.5 text-[10px] font-bold text-sky-300">
                {message.step_label}
              </span>
              {message.subject && (
                <span className="text-xs font-semibold text-white/80 truncate max-w-[280px]">
                  {message.subject}
                </span>
              )}
              {message.ai_generated && (
                <span className="rounded-full bg-violet-500/15 border border-violet-500/25 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-violet-300">
                  AI
                </span>
              )}
              {message.delivered_at && (
                <span className="flex items-center gap-1 rounded-full bg-sky-500/15 border border-sky-500/30 px-2 py-0.5 text-[10px] font-semibold text-sky-300">
                  <MailOpen className="h-3 w-3" />
                  Delivered
                </span>
              )}
              {message.opened_at && (
                <span className="flex items-center gap-1 rounded-full bg-emerald-500/15 border border-emerald-500/30 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">
                  <MailOpen className="h-3 w-3" />
                  Opened
                </span>
              )}
              <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-semibold', cfg.cls)}>
                {cfg.label}
              </span>
              {hasReplies && (
                <span className="rounded-full bg-violet-500/15 border border-violet-500/25 px-1.5 py-0.5 text-[10px] font-semibold text-violet-300">
                  {message.replies.length} repl{message.replies.length === 1 ? 'y' : 'ies'}
                </span>
              )}
            </div>
            <div className="flex flex-shrink-0 items-center gap-2">
              <span className="text-[10px] text-white/35 whitespace-nowrap">
                {message.sent_at ? fmtShort(message.sent_at) : '—'}
              </span>
              {open ? (
                <ChevronUp className="h-3.5 w-3.5 text-white/30" />
              ) : (
                <ChevronDown className="h-3.5 w-3.5 text-white/30" />
              )}
            </div>
          </button>

          {/* Expanded body */}
          {open && (
            <div className="mt-2">
              <EmailBodyPreview html={message.body_html} text={message.body_text} />
            </div>
          )}

          {/* Replies */}
          {hasReplies && (
            <div className="mt-2 space-y-2">
              {message.replies.map((r, i) => (
                <ReplyCard key={r.id} reply={r} idx={i} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function LeadAccordion({ lead, defaultOpen }: { lead: ReportLead; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen ?? false);
  const lsCfg = leadStatusConfig[lead.campaign_status] ?? leadStatusConfig.pending;
  const sentCount = lead.messages.filter((m) => m.status === 'sent' || m.status === 'delivered').length;
  const replyCount = lead.messages.reduce((s, m) => s + m.replies.length, 0);

  return (
    <div className="rounded-2xl border border-white/[0.07] bg-white/[0.03] overflow-hidden transition-all">
      {/* Lead header */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 p-4 text-left hover:bg-white/[0.03] transition-colors"
      >
        <Initials name={lead.name} />

        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-bold text-white truncate">{lead.name ?? 'Unknown'}</span>
            <span className={cn('rounded-full border px-2 py-0.5 text-[10px] font-semibold', lsCfg.cls)}>
              {lsCfg.label}
            </span>
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5">
            {lead.email && (
              <span className="text-[11px] text-white/40 flex items-center gap-1">
                <Mail className="h-3 w-3" />
                {lead.effective_email ? (
                  <span>
                    <span className="line-through opacity-40">{lead.email}</span>
                    <span className="ml-1 text-amber-300">{lead.effective_email}</span>
                  </span>
                ) : lead.email}
              </span>
            )}
            {lead.company && (
              <span className="text-[11px] text-white/40 flex items-center gap-1">
                <Building2 className="h-3 w-3" />
                {lead.company}
              </span>
            )}
            {lead.title && (
              <span className="text-[11px] text-white/30">{lead.title}</span>
            )}
          </div>
        </div>

        {/* Quick stats */}
        <div className="flex items-center gap-3 flex-shrink-0">
          <div className="flex flex-col items-center">
            <span className="text-sm font-bold text-sky-300 tabular-nums">{sentCount}</span>
            <span className="text-[9px] text-white/30">sent</span>
          </div>
          <div className="flex flex-col items-center">
            <span className="text-sm font-bold text-violet-300 tabular-nums">{replyCount}</span>
            <span className="text-[9px] text-white/30">replies</span>
          </div>
          {open ? (
            <ChevronUp className="h-4 w-4 text-white/25" />
          ) : (
            <ChevronDown className="h-4 w-4 text-white/25" />
          )}
        </div>
      </button>

      {/* Email chain */}
      {open && (
        <div className="border-t border-white/[0.06] px-4 pt-3 pb-4">
          {lead.messages.length === 0 ? (
            <p className="py-4 text-center text-xs text-white/30">No emails sent yet</p>
          ) : (
            <div className="mt-1">
              {lead.messages.map((m, i) => (
                <MessageRow
                  key={m.id}
                  message={m}
                  isLast={i === lead.messages.length - 1}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main Panel ─────────────────────────────────────────────────────────────

export function CampaignReportPanel({ campaignId, campaignName, onClose }: Props) {
  const [report, setReport] = useState<CampaignReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [activeSection, setActiveSection] = useState<'overview' | 'leads'>('overview');
  const leadsRef = useRef<HTMLDivElement>(null);
  const overviewRef = useRef<HTMLDivElement>(null);

  const fetchReport = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const data = await api<CampaignReport>({ method: 'GET', url: `/campaigns/${campaignId}/report` });
      setReport(data);
    } catch {
      if (!silent) setError('Failed to load report. Please try again.');
    } finally {
      if (!silent) setLoading(false);
    }
  }, [campaignId]);

  useEffect(() => { fetchReport(); }, [fetchReport]);

  // Keyboard close
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  const filteredLeads = report?.leads.filter((l) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      l.name?.toLowerCase().includes(q) ||
      l.email?.toLowerCase().includes(q) ||
      l.company?.toLowerCase().includes(q)
    );
  }) ?? [];

  const totalReplies = report?.leads.reduce(
    (s, l) => s + l.messages.reduce((ms, m) => ms + m.replies.length, 0),
    0
  ) ?? 0;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Panel */}
      <div
        className="fixed inset-y-0 right-0 z-50 flex w-full flex-col md:w-[90vw] lg:w-[78vw] xl:w-[70vw]"
        style={{ maxWidth: 1100, background: '#0a111e', boxShadow: '-8px 0 48px rgba(0,0,0,0.6)' }}
      >
        {/* ── Top bar ── */}
        <div
          className="flex flex-shrink-0 items-center gap-4 border-b border-white/[0.07] px-6 py-4"
          style={{ background: 'linear-gradient(135deg, #0d1a2e 0%, #081220 100%)' }}
        >
          <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-[#1c8ed4]/20">
            <FileText className="h-4.5 w-4.5 text-[#1c8ed4]" style={{ height: 18, width: 18 }} />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-widest text-white/30">Campaign Report</p>
            <h2 className="truncate text-base font-bold text-white">{campaignName}</h2>
          </div>
          {/* Nav pills */}
          <div className="hidden md:flex items-center gap-1 rounded-xl border border-white/[0.08] bg-white/[0.04] p-1">
            {(['overview', 'leads'] as const).map((s) => (
              <button
                key={s}
                onClick={() => {
                  setActiveSection(s);
                  (s === 'overview' ? overviewRef : leadsRef).current?.scrollIntoView({ behavior: 'smooth' });
                }}
                className={cn(
                  'rounded-lg px-3 py-1.5 text-xs font-semibold capitalize transition-all',
                  activeSection === s
                    ? 'bg-white/[0.12] text-white'
                    : 'text-white/40 hover:text-white hover:bg-white/[0.06]'
                )}
              >
                {s === 'overview' ? 'Overview' : `Leads (${report?.leads.length ?? '—'})`}
              </button>
            ))}
          </div>
          <button
            onClick={() => fetchReport()}
            disabled={loading}
            className="rounded-lg p-2 text-white/30 transition-colors hover:bg-white/[0.07] hover:text-white disabled:opacity-40"
            title="Refresh"
          >
            <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
          </button>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-white/30 transition-colors hover:bg-white/[0.07] hover:text-white"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* ── Body ── */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex h-full items-center justify-center gap-3 text-white/40">
              <Loader2 className="h-5 w-5 animate-spin" />
              <span className="text-sm">Building report…</span>
            </div>
          ) : error ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
              <AlertCircle className="h-8 w-8 text-rose-400" />
              <p className="text-sm text-white/60">{error}</p>
              <button
                onClick={() => fetchReport()}
                className="rounded-xl bg-white/[0.07] px-4 py-2 text-sm font-semibold text-white hover:bg-white/[0.1]"
              >
                Retry
              </button>
            </div>
          ) : report ? (
            <div className="space-y-0">

              {/* ══ SECTION 1: Overview ══════════════════════════ */}
              <div ref={overviewRef} className="border-b border-white/[0.06] px-6 py-6 space-y-6">

                {/* Meta grid */}
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {/* Campaign Info */}
                  <div className="rounded-2xl border border-white/[0.07] bg-white/[0.03] p-4 space-y-3">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-white/30">Campaign Info</p>
                    <div className="space-y-2">
                      <div>
                        <p className="text-[10px] text-white/30">Name</p>
                        <p className="text-sm font-semibold text-white">{report.name}</p>
                      </div>
                      {report.description && (
                        <div>
                          <p className="text-[10px] text-white/30">Description</p>
                          <p className="text-xs text-white/60 leading-relaxed">{report.description}</p>
                        </div>
                      )}
                      <div className="flex flex-wrap gap-2 pt-1">
                        <span className="rounded-full border border-white/[0.1] bg-white/[0.06] px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-white/50">
                          {report.campaign_type}
                        </span>
                        {report.vertical && (
                          <span className="rounded-full border border-white/[0.1] bg-white/[0.06] px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-white/50">
                            {report.vertical}
                          </span>
                        )}
                        {report.test_mode_enabled && (
                          <span className="rounded-full border border-amber-500/30 bg-amber-500/15 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-amber-300">
                            Test Mode
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Dates & Sender */}
                  <div className="rounded-2xl border border-white/[0.07] bg-white/[0.03] p-4 space-y-3">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-white/30">Dates & Sender</p>
                    <div className="space-y-2">
                      <div className="flex items-start gap-2">
                        <Calendar className="h-3.5 w-3.5 text-white/30 mt-0.5 flex-shrink-0" />
                        <div>
                          <p className="text-[10px] text-white/30">Created</p>
                          <p className="text-xs font-medium text-white/70">{fmtDate(report.created_at)}</p>
                        </div>
                      </div>
                      <div className="flex items-start gap-2">
                        <Zap className="h-3.5 w-3.5 text-emerald-400/60 mt-0.5 flex-shrink-0" />
                        <div>
                          <p className="text-[10px] text-white/30">Launched</p>
                          <p className="text-xs font-medium text-white/70">{fmtDate(report.launched_at)}</p>
                        </div>
                      </div>
                      <div className="flex items-start gap-2">
                        <Mail className="h-3.5 w-3.5 text-sky-400/60 mt-0.5 flex-shrink-0" />
                        <div>
                          <p className="text-[10px] text-white/30">From</p>
                          <p className="text-xs font-medium text-white/70">
                            {report.from_name ? `${report.from_name} ` : ''}
                            <span className="text-white/50">&lt;{report.from_email}&gt;</span>
                          </p>
                        </div>
                      </div>
                      {report.test_mode_enabled && report.test_emails.length > 0 && (
                        <div className="flex items-start gap-2">
                          <Tag className="h-3.5 w-3.5 text-amber-400/60 mt-0.5 flex-shrink-0" />
                          <div>
                            <p className="text-[10px] text-white/30">Test recipients</p>
                            <p className="text-xs font-medium text-amber-300">{report.test_emails.join(', ')}</p>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Stats */}
                  <div className="rounded-2xl border border-white/[0.07] bg-white/[0.03] p-4 space-y-3">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-white/30">Performance</p>
                    <div className="grid grid-cols-2 gap-3">
                      {[
                        { label: 'Total Leads',  value: report.total_leads,  color: 'text-white' },
                        { label: 'Emails Sent',  value: report.sent_count,   color: 'text-sky-300' },
                        { label: 'Opened',       value: report.open_count,   color: 'text-teal-300' },
                        { label: 'Replies',      value: report.reply_count,  color: 'text-violet-300' },
                        { label: 'Bounced',      value: report.bounce_count, color: 'text-rose-300' },
                        { label: 'Resp. chains', value: totalReplies,        color: 'text-amber-300' },
                      ].map((s) => (
                        <div key={s.label} className="flex flex-col">
                          <span className={cn('text-xl font-extrabold tabular-nums leading-none', s.color)}>
                            {s.value}
                          </span>
                          <span className="mt-0.5 text-[10px] text-white/35">{s.label}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Sequence timeline */}
                {report.sequence.length > 0 && (
                  <div>
                    <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-white/30">
                      Sequence · {report.sequence.length} step{report.sequence.length !== 1 ? 's' : ''}
                    </p>
                    <div className="flex flex-wrap items-center gap-0">
                      {report.sequence.map((step, i) => (
                        <div key={step.step} className="flex items-center">
                          <div className="rounded-xl border border-white/[0.09] bg-white/[0.04] px-3 py-2.5 min-w-[100px]">
                            <div className="flex items-center gap-1.5 mb-1">
                              <span className="text-[9px] font-bold uppercase tracking-widest text-white/25">
                                {i === 0 ? 'Initial' : `Follow-up ${i}`}
                              </span>
                            </div>
                            {step.subject_template && (
                              <p className="text-[11px] font-semibold text-white/70 truncate max-w-[120px]">
                                {step.subject_template}
                              </p>
                            )}
                            <p className="mt-0.5 text-[10px] text-white/30">
                              {step.ai_generate ? '✦ AI generated' : 'Template'}
                            </p>
                          </div>
                          {i < report.sequence.length - 1 && (
                            <div className="flex items-center gap-1 px-2">
                              <div className="h-px w-6 bg-white/[0.1]" />
                              <div className="rounded-full border border-white/[0.1] bg-white/[0.04] px-2 py-0.5 text-[9px] font-semibold text-white/35 whitespace-nowrap">
                                +{report.sequence[i + 1]?.delay_days ?? 0}d
                              </div>
                              <div className="h-px w-6 bg-white/[0.1]" />
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* ══ SECTION 2: Leads ═════════════════════════════ */}
              <div ref={leadsRef} className="px-6 py-6">
                <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-widest text-white/30">Lead contacts</p>
                    <p className="mt-0.5 text-sm font-semibold text-white">
                      {report.leads.length} lead{report.leads.length !== 1 ? 's' : ''} enrolled
                    </p>
                  </div>
                  <input
                    type="search"
                    placeholder="Search by name, email, or company…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="rounded-xl border border-white/[0.1] bg-white/[0.04] px-3.5 py-2 text-sm text-white placeholder:text-white/25 outline-none focus:border-[#1c8ed4]/50 focus:bg-white/[0.06] w-full sm:w-72"
                  />
                </div>

                {filteredLeads.length === 0 ? (
                  <div className="flex flex-col items-center justify-center rounded-2xl border border-white/[0.06] bg-white/[0.02] py-14 text-center">
                    <User className="h-8 w-8 text-white/15 mb-3" />
                    <p className="text-sm text-white/40">
                      {search ? 'No leads match your search' : 'No leads enrolled yet'}
                    </p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {filteredLeads.map((lead, i) => (
                      <LeadAccordion
                        key={lead.lead_id}
                        lead={lead}
                        defaultOpen={i === 0 && filteredLeads.length === 1}
                      />
                    ))}
                  </div>
                )}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </>
  );
}
