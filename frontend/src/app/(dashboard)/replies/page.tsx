'use client';

import { useEffect, useState, useMemo, useRef } from 'react';
import type React from 'react';
import {
  Mail, ThumbsUp, ThumbsDown, HelpCircle, Calendar,
  Archive, Reply, Forward, Sparkles, Clock, Loader2, MessageSquare,
  ChevronDown, ChevronRight, Check, Info, ArrowLeft, Send, Eye, BarChart2,
} from 'lucide-react';
import { api, type PaginatedData } from '@/lib/api-client';
import { cn } from '@/lib/utils';

// ── Types ────────────────────────────────────────────────────────────────────

interface ReplyThread {
  id: string;
  message_id: string;
  lead_id: string;
  contact_name: string | null;
  company_name: string | null;
  subject: string | null;
  body_text: string | null;
  created_at: string;
  intent: string | null;
  sentiment: string | null;
  priority: string;
  is_read: boolean;
  suggested_response: string | null;
  ai_summary: string | null;
  suggested_action: string | null;
  outbound_subject: string | null;
  outbound_body_text: string | null;
  campaign_id: string | null;
  campaign_name: string | null;
  campaign_sent_count: number | null;
  responded_at: string | null;
}

interface CampaignGroup {
  campaign_id: string;
  campaign_name: string;
  sent_count: number;
  replies: ReplyThread[];
}

// ── Intent helpers ───────────────────────────────────────────────────────────

type IntentKey = 'interested' | 'not_interested' | 'maybe' | 'meeting_request';

function intentCategory(intent: string | null): IntentKey {
  if (intent === 'interested') return 'interested';
  if (intent === 'meeting_request') return 'meeting_request';
  if (intent === 'unsubscribe' || intent === 'not_interested' || intent === 'objection') return 'not_interested';
  if (intent === 'not_now' || intent === 'question') return 'maybe';
  return 'maybe';
}

const INTENT_CFG: Record<IntentKey, { label: string; icon: React.ElementType; bg: string; text: string; border: string }> = {
  interested:      { label: 'Interested',      icon: ThumbsUp,   bg: 'bg-emerald-500/15', text: 'text-emerald-400', border: 'border-emerald-500/25' },
  not_interested:  { label: 'Not Interested',  icon: ThumbsDown, bg: 'bg-red-500/15',     text: 'text-red-400',    border: 'border-red-500/25'     },
  maybe:           { label: 'Maybe',           icon: HelpCircle, bg: 'bg-amber-500/15',   text: 'text-amber-400',  border: 'border-amber-500/25'   },
  meeting_request: { label: 'Meeting Request', icon: Calendar,   bg: 'bg-indigo-500/15',  text: 'text-indigo-400', border: 'border-indigo-500/25'  },
};

function getCfg(intent: string | null) { return INTENT_CFG[intentCategory(intent)]; }

function relTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  const h = Math.floor(m / 60);
  const d = Math.floor(h / 24);
  if (m < 1) return 'Just now';
  if (m < 60) return `${m}m ago`;
  if (h < 24) return `${h}h ago`;
  return `${d}d ago`;
}

function initials(name: string | null): string {
  if (!name) return '?';
  return name.split(' ').map((n) => n[0]).join('').slice(0, 2).toUpperCase();
}

function intentCounts(replies: ReplyThread[]): Record<IntentKey, number> {
  const c: Record<IntentKey, number> = { interested: 0, not_interested: 0, maybe: 0, meeting_request: 0 };
  replies.forEach((r) => { c[intentCategory(r.intent)]++; });
  return c;
}

// ── Toast ────────────────────────────────────────────────────────────────────

function Toast({ msg, onDone }: { msg: string; onDone: () => void }) {
  useEffect(() => { const t = setTimeout(onDone, 2800); return () => clearTimeout(t); }, [onDone]);
  return (
    <div className="fixed bottom-5 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 rounded-2xl border border-white/[0.1] bg-[#0d1525]/95 px-4 py-3 text-sm text-white shadow-xl backdrop-blur-xl animate-in fade-in slide-in-from-bottom-2">
      <Check className="h-4 w-4 text-emerald-400" />{msg}
    </div>
  );
}

// ── CampaignCard (left sidebar) ──────────────────────────────────────────────

function CampaignCard({ group, isActive, onClick }: {
  group: CampaignGroup;
  isActive: boolean;
  onClick: () => void;
}) {
  const unread = group.replies.filter((r) => !r.is_read).length;
  const actioned = group.replies.filter((r) => r.responded_at != null).length;
  const counts = intentCounts(group.replies);

  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full rounded-2xl border p-4 text-left transition-all',
        isActive
          ? 'border-indigo-500/40 bg-indigo-600/10 shadow-lg shadow-indigo-900/20'
          : 'border-white/[0.07] bg-white/[0.03] hover:bg-white/[0.06]',
      )}
    >
      {/* Name + unread badge */}
      <div className="flex items-start justify-between gap-2 mb-2.5">
        <span className={cn('text-sm font-bold leading-snug', isActive ? 'text-white' : 'text-white/80')}>{group.campaign_name}</span>
        {unread > 0 && (
          <span className="flex-shrink-0 rounded-full bg-indigo-500 px-2 py-0.5 text-[10px] font-bold text-white leading-none">
            {unread}
          </span>
        )}
      </div>

      {/* Mini stats row */}
      <div className="flex items-center gap-2.5 mb-3 text-[11px] text-white/40">
        <span><span className="font-semibold text-white/70">{group.replies.length}</span> replies</span>
        <span className="text-white/15">·</span>
        <span>{group.sent_count} sent</span>
        {actioned > 0 && (
          <>
            <span className="text-white/15">·</span>
            <span className="text-emerald-400">{actioned} actioned</span>
          </>
        )}
      </div>

      {/* Intent bar (compact) */}
      <IntentBar replies={group.replies} />
    </button>
  );
}

// ── IntentBar ────────────────────────────────────────────────────────────────

const INTENT_BAR_COLORS: Record<IntentKey, string> = {
  interested:     'bg-emerald-500',
  meeting_request:'bg-indigo-500',
  maybe:          'bg-amber-500',
  not_interested: 'bg-red-500',
};

function IntentBar({ replies }: { replies: ReplyThread[] }) {
  const counts = intentCounts(replies);
  const total = replies.length;
  if (total === 0) return null;
  const order: IntentKey[] = ['interested', 'meeting_request', 'maybe', 'not_interested'];
  return (
    <div>
      {/* stacked bar */}
      <div className="flex h-2 w-full overflow-hidden rounded-full gap-px">
        {order.map((key) => {
          const pct = (counts[key] / total) * 100;
          if (pct === 0) return null;
          return <div key={key} className={cn(INTENT_BAR_COLORS[key])} style={{ width: `${pct}%` }} />;
        })}
      </div>
      {/* legend */}
      <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1">
        {order.map((key) => {
          if (counts[key] === 0) return null;
          const cfg = INTENT_CFG[key];
          const Icon = cfg.icon;
          return (
            <span key={key} className="flex items-center gap-1.5">
              <span className={cn('h-2 w-2 rounded-full flex-shrink-0', INTENT_BAR_COLORS[key])} />
              <span className={cn('text-[11px] font-semibold tabular-nums', cfg.text)}>{counts[key]}</span>
              <span className="text-[11px] text-white/35">{cfg.label}</span>
            </span>
          );
        })}
      </div>
    </div>
  );
}

// ── CampaignDetail (right panel: campaign selected) ──────────────────────────

function CampaignDetail({ group, onSelectReply }: {
  group: CampaignGroup;
  onSelectReply: (r: ReplyThread) => void;
}) {
  const unread = group.replies.filter((r) => !r.is_read).length;
  const actioned = group.replies.filter((r) => r.responded_at != null).length;
  const replyRate = group.sent_count > 0 ? Math.round((group.replies.length / group.sent_count) * 100) : 0;

  return (
    <div className="space-y-3">
      {/* ── Campaign header ─────────────────────────────────────────── */}
      <div className="glass-card rounded-2xl px-5 py-4">
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            <p className="app-label mb-1">Campaign</p>
            <h2 className="text-lg font-bold tracking-tight text-white leading-snug">{group.campaign_name}</h2>
          </div>
          {unread > 0 && (
            <span className="flex-shrink-0 rounded-full bg-indigo-600 px-2.5 py-1 text-[11px] font-bold text-white">
              {unread} unread
            </span>
          )}
        </div>

        {/* Inline stats row */}
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 mb-4 text-sm">
          <span className="flex items-center gap-1.5 text-white/50">
            <Send className="h-3.5 w-3.5 text-cyan-400" />
            <span className="font-semibold text-white">{group.sent_count}</span> sent
          </span>
          <span className="text-white/15">·</span>
          <span className="flex items-center gap-1.5 text-white/50">
            <Mail className="h-3.5 w-3.5 text-violet-400" />
            <span className="font-semibold text-white">{group.replies.length}</span> {group.replies.length === 1 ? 'reply' : 'replies'}
          </span>
          <span className="text-white/15">·</span>
          <span className="flex items-center gap-1.5 text-white/50">
            <BarChart2 className="h-3.5 w-3.5 text-emerald-400" />
            <span className="font-semibold text-emerald-400">{replyRate}%</span> reply rate
          </span>
          {actioned > 0 && (
            <>
              <span className="text-white/15">·</span>
              <span className="flex items-center gap-1.5 text-white/50">
                <Check className="h-3.5 w-3.5 text-amber-400" />
                <span className="font-semibold text-amber-400">{actioned}</span> actioned
              </span>
            </>
          )}
        </div>

        {/* Intent bar */}
        <IntentBar replies={group.replies} />
      </div>

      {/* ── Reply list ──────────────────────────────────────────────── */}
      <div className="glass-card rounded-2xl overflow-hidden">
        <div className="border-b border-white/[0.06] px-5 py-3">
          <h3 className="text-sm font-semibold text-white/60">
            {group.replies.length === 0 ? 'No replies yet' : `${group.replies.length} ${group.replies.length === 1 ? 'reply' : 'replies'}`}
          </h3>
        </div>

        <div className="divide-y divide-white/[0.04]">
          {group.replies.length === 0 ? (
            <div className="flex flex-col items-center py-12 text-center">
              <MessageSquare className="h-8 w-8 text-white/10 mb-3" />
              <p className="text-sm text-white/40">No replies for this campaign yet.</p>
            </div>
          ) : group.replies.map((reply) => {
            const cfg = getCfg(reply.intent);
            const accentColor: Record<IntentKey, string> = {
              interested: 'border-l-emerald-500', not_interested: 'border-l-red-500',
              maybe: 'border-l-amber-500', meeting_request: 'border-l-indigo-500',
            };
            return (
              <button
                key={reply.id}
                onClick={() => onSelectReply(reply)}
                className={cn(
                  'w-full border-l-2 pl-4 pr-5 py-3.5 text-left transition-colors hover:bg-white/[0.03] group',
                  accentColor[intentCategory(reply.intent)],
                )}
              >
                <div className="flex items-center gap-3">
                  {/* Avatar */}
                  <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-white/[0.08] text-[10px] font-bold text-white/70">
                    {initials(reply.contact_name)}
                  </div>

                  {/* Main content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className={cn('text-sm font-semibold truncate', !reply.is_read ? 'text-white' : 'text-white/55')}>
                        {reply.contact_name ?? 'Unknown'}
                        {reply.company_name && <span className="ml-1.5 font-normal text-white/35 text-xs">{reply.company_name}</span>}
                      </span>
                      <span className="text-[11px] text-white/30 flex-shrink-0 tabular-nums">{relTime(reply.created_at)}</span>
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <p className="text-xs text-white/40 truncate flex-1">{reply.subject ?? '(no subject)'}</p>
                      <span className={cn('flex-shrink-0 text-[10px] font-semibold', cfg.text)}>{cfg.label}</span>
                      {!reply.is_read && <div className="h-1.5 w-1.5 rounded-full bg-indigo-400 flex-shrink-0" />}
                    </div>
                  </div>

                  <ChevronRight className="h-4 w-4 text-white/15 group-hover:text-white/40 flex-shrink-0 transition-colors" />
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── ThreadView (right panel: reply selected) ─────────────────────────────────

function ThreadView({ reply, onBack, onArchive, showOutbound, setShowOutbound, showReplyBox, setShowReplyBox, replyText, setReplyText, onGenerateReply, onBookMeeting, setToast, onReplySent }: {
  reply: ReplyThread;
  onBack: () => void;
  onArchive: (r: ReplyThread) => void;
  showOutbound: boolean;
  setShowOutbound: (v: boolean) => void;
  showReplyBox: boolean;
  setShowReplyBox: (v: boolean) => void;
  replyText: string;
  setReplyText: (v: string) => void;
  onGenerateReply: () => void;
  onBookMeeting: () => void;
  setToast: (v: string) => void;
  onReplySent: () => void;
}) {
  const [sending, setSending] = useState(false);
  const cfg = getCfg(reply.intent);
  const Icon = cfg.icon;

  return (
    <div className="space-y-4">
      {/* Breadcrumb back */}
      <button
        onClick={onBack}
        className="flex items-center gap-1.5 text-xs font-semibold text-white/40 hover:text-white transition-colors"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to {reply.campaign_name ?? 'Campaign'}
      </button>

      {/* Email thread */}
      <div className="glass-card rounded-2xl overflow-hidden">
        <div className="border-b border-white/[0.06] px-5 py-4">
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              <h3 className="mb-1.5 text-base font-bold tracking-tight text-white truncate">{reply.subject ?? '(no subject)'}</h3>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs text-white/50">
                  From: <strong className="text-white/80">{reply.contact_name ?? 'Unknown'}</strong>
                  {reply.company_name ? ` · ${reply.company_name}` : ''}
                </span>
                <span className="flex items-center gap-1 text-xs text-white/30">
                  <Clock className="h-3 w-3" /> {relTime(reply.created_at)}
                </span>
                <span className={cn('inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium', cfg.bg, cfg.text, cfg.border)}>
                  <Icon className="h-3 w-3" />{cfg.label}
                </span>
                {reply.sentiment && (
                  <span className="rounded-full bg-white/[0.07] px-2 py-0.5 text-[11px] font-medium text-white/50 capitalize">{reply.sentiment}</span>
                )}
              </div>
            </div>
            <div className="flex flex-shrink-0 items-center gap-1.5">
              <button
                onClick={() => { setShowReplyBox(true); setReplyText(''); }}
                className="flex items-center gap-1.5 rounded-xl border border-white/[0.1] px-3 py-2 text-xs font-medium text-white/60 transition-colors hover:bg-white/[0.05]"
              >
                <Reply className="h-3.5 w-3.5" /> Reply
              </button>
              <button
                onClick={() => setToast('Forward: connect your email integration to enable this action.')}
                className="flex items-center gap-1.5 rounded-xl border border-white/[0.1] px-3 py-2 text-xs font-medium text-white/60 transition-colors hover:bg-white/[0.05]"
              >
                <Forward className="h-3.5 w-3.5" /> Forward
              </button>
              <button
                onClick={() => onArchive(reply)}
                title="Archive"
                className="rounded-xl border border-white/[0.1] p-2 text-white/30 transition-colors hover:bg-white/[0.05] hover:text-white/60"
              >
                <Archive className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </div>

        {/* Original outbound (collapsible) */}
        {reply.outbound_subject && (
          <div className="border-b border-white/[0.05] bg-white/[0.02] px-5 py-3">
            <button className="flex w-full items-center gap-2 text-left" onClick={() => setShowOutbound(!showOutbound)}>
              {showOutbound ? <ChevronDown className="h-3.5 w-3.5 text-white/30" /> : <ChevronRight className="h-3.5 w-3.5 text-white/30" />}
              <span className="text-[10px] font-bold uppercase tracking-widest text-white/30">Original Email Sent</span>
              <span className="ml-1 truncate text-[11px] text-white/40">{reply.outbound_subject}</span>
            </button>
            {showOutbound && reply.outbound_body_text && (
              <div className="mt-3 ml-5 border-l-2 border-white/[0.08] pl-4">
                <p className="whitespace-pre-line text-xs leading-relaxed text-white/40">{reply.outbound_body_text}</p>
              </div>
            )}
          </div>
        )}

        {/* Reply body */}
        <div className="px-5 py-5">
          <p className="whitespace-pre-line text-sm leading-relaxed text-white/70">
            {reply.body_text ?? '(empty reply body)'}
          </p>
        </div>

        {/* Compose box */}
        {showReplyBox && (
          <div className="border-t border-white/[0.06] px-5 py-4 space-y-3">
            <p className="text-[10px] font-bold uppercase tracking-widest text-white/30">Compose Reply</p>
            <textarea
              value={replyText}
              onChange={(e) => setReplyText(e.target.value)}
              rows={5}
              placeholder="Type your reply…"
              className="w-full rounded-xl border border-white/[0.1] bg-white/[0.05] px-4 py-3 text-sm text-white placeholder:text-white/25 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
            />
            <div className="flex gap-2">
              <button
                disabled={sending || !replyText.trim()}
                onClick={async () => {
                  setSending(true);
                  try {
                    await api({ method: 'POST', url: `/replies/${reply.id}/respond`, data: { body_text: replyText } });
                    setToast('Reply sent successfully');
                    setShowReplyBox(false);
                    setReplyText('');
                    onReplySent();
                  } catch {
                    setToast('Failed to send reply. Please try again.');
                  } finally {
                    setSending(false);
                  }
                }}
                className="flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-4 py-2 text-xs font-semibold text-white shadow-lg shadow-indigo-900/40 transition-transform hover:-translate-y-px disabled:opacity-50"
              >
                {sending && <Loader2 className="h-3 w-3 animate-spin" />}
                {sending ? 'Sending…' : 'Send Reply'}
              </button>
              <button
                onClick={() => setShowReplyBox(false)}
                className="rounded-xl border border-white/[0.1] px-4 py-2 text-xs font-medium text-white/40 hover:bg-white/[0.04] transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      {/* AI Analysis */}
      {(reply.ai_summary || reply.suggested_action || reply.suggested_response) ? (
        <div className="glass-card rounded-[28px] overflow-hidden">
          <div className="border-b border-white/[0.06] px-5 py-4 flex items-center gap-2" style={{ background: 'linear-gradient(135deg, rgba(99,102,241,0.08) 0%, rgba(139,92,246,0.05) 100%)' }}>
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-500/20">
              <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
            </div>
            <h3 className="text-sm font-bold text-white">AI Analysis</h3>
            <span className="ml-auto rounded-full bg-white/[0.07] px-2.5 py-1 text-[10px] font-semibold text-indigo-300 border border-indigo-500/20">
              Claude Sonnet
            </span>
          </div>
          <div className="px-5 py-4 space-y-4">
            {reply.ai_summary && (
              <div>
                <p className="mb-1.5 text-[10px] font-bold uppercase tracking-widest text-indigo-400">Summary</p>
                <p className="text-sm leading-relaxed text-white/70">{reply.ai_summary}</p>
              </div>
            )}
            {reply.suggested_action && (
              <div>
                <p className="mb-1.5 text-[10px] font-bold uppercase tracking-widest text-indigo-400">Suggested Action</p>
                <p className="text-sm leading-relaxed text-white/70">{reply.suggested_action}</p>
              </div>
            )}
            {reply.suggested_response && (
              <div>
                <p className="mb-1.5 text-[10px] font-bold uppercase tracking-widest text-indigo-400">Suggested Response</p>
                <p className="text-sm leading-relaxed text-white/70">{reply.suggested_response}</p>
              </div>
            )}
            <div className="flex gap-2 pt-1">
              <button
                onClick={onGenerateReply}
                className="flex-1 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-3 py-2.5 text-xs font-semibold text-white shadow-lg shadow-indigo-900/40 transition-transform hover:-translate-y-px"
              >
                Use as Reply Draft
              </button>
              <button
                onClick={onBookMeeting}
                className="flex-1 rounded-xl border border-white/[0.1] px-3 py-2.5 text-xs font-semibold text-white/60 hover:bg-white/[0.05] transition-colors"
              >
                Book Meeting
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="glass-card rounded-[28px] px-5 py-4">
          <div className="flex items-start gap-3 mb-3">
            <Info className="mt-0.5 h-4 w-4 flex-shrink-0 text-white/30" />
            <div>
              <p className="text-sm font-semibold text-white/70">No AI analysis yet</p>
              <p className="mt-0.5 text-xs text-white/40">AI analysis runs automatically for new replies. Check back shortly.</p>
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={onGenerateReply}
              className="rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-3 py-2 text-xs font-semibold text-white shadow-lg shadow-indigo-900/40"
            >
              Generate AI Reply
            </button>
            <button
              onClick={onBookMeeting}
              className="rounded-xl border border-white/[0.1] px-3 py-2 text-xs font-semibold text-white/50 hover:bg-white/[0.05] transition-colors"
            >
              Book Meeting
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function RepliesPage() {
  const [replies, setReplies] = useState<ReplyThread[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCampaign, setSelectedCampaign] = useState<CampaignGroup | null>(null);
  const [selectedReply, setSelectedReply] = useState<ReplyThread | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [replyText, setReplyText] = useState('');
  const [showReplyBox, setShowReplyBox] = useState(false);
  const [showOutbound, setShowOutbound] = useState(true);
  const [headerFilter, setHeaderFilter] = useState<'campaigns' | 'total' | 'unread' | 'meeting'>('campaigns');
  const markedRef = useRef<Set<string>>(new Set());

  const load = () => {
    setLoading(true);
    api<PaginatedData<ReplyThread>>({ method: 'GET', url: '/replies', params: { page: 1, page_size: 200 } })
      .then((data) => setReplies(data.items))
      .catch(() => setReplies([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Poll every 15 s for new replies
  useEffect(() => {
    const id = setInterval(() => {
      api<PaginatedData<ReplyThread>>({ method: 'GET', url: '/replies', params: { page: 1, page_size: 200 } })
        .then((data) => setReplies(data.items))
        .catch(() => {});
    }, 15_000);
    return () => clearInterval(id);
  }, []);

  // Group replies by campaign
  const campaigns = useMemo<CampaignGroup[]>(() => {
    const groups: Record<string, CampaignGroup> = {};
    for (const r of replies) {
      const cid = r.campaign_id ?? '__none__';
      if (!groups[cid]) {
        groups[cid] = {
          campaign_id: cid,
          campaign_name: r.campaign_name ?? 'Uncategorized',
          sent_count: r.campaign_sent_count ?? 0,
          replies: [],
        };
      }
      groups[cid].replies.push(r);
    }
    return Object.values(groups).sort((a, b) => {
      const aLast = Math.max(...a.replies.map((r) => new Date(r.created_at).getTime()));
      const bLast = Math.max(...b.replies.map((r) => new Date(r.created_at).getTime()));
      return bLast - aLast;
    });
  }, [replies]);

  const displayCampaigns = useMemo(() => {
    if (headerFilter === 'campaigns' || headerFilter === 'total') return campaigns;
    return campaigns
      .map((cg) => ({
        ...cg,
        replies: cg.replies.filter((r) =>
          headerFilter === 'unread' ? !r.is_read : r.intent === 'meeting_request'
        ),
      }))
      .filter((cg) => cg.replies.length > 0);
  }, [campaigns, headerFilter]);

  const selectedGroupForDisplay = useMemo(() => {
    if (!selectedCampaign) return null;
    if (headerFilter === 'campaigns' || headerFilter === 'total') return selectedCampaign;
    return {
      ...selectedCampaign,
      replies: selectedCampaign.replies.filter((r) =>
        headerFilter === 'unread' ? !r.is_read : r.intent === 'meeting_request'
      ),
    };
  }, [selectedCampaign, headerFilter]);

  // Auto-select first campaign
  useEffect(() => {
    if (!loading && displayCampaigns.length > 0 && !selectedCampaign) {
      setSelectedCampaign(displayCampaigns[0]);
    }
  }, [loading, displayCampaigns]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-mark as read when reply selected
  useEffect(() => {
    if (!selectedReply || markedRef.current.has(selectedReply.id)) return;
    markedRef.current.add(selectedReply.id);
    if (selectedReply.is_read) return;
    api({ method: 'PATCH', url: `/replies/${selectedReply.id}/read` })
      .then(() => setReplies((prev) => prev.map((r) => r.id === selectedReply.id ? { ...r, is_read: true } : r)))
      .catch(() => {});
  }, [selectedReply]);

  const handleArchive = (reply: ReplyThread) => {
    api({ method: 'PATCH', url: `/replies/${reply.id}/archive` })
      .then(() => {
        setReplies((prev) => prev.filter((r) => r.id !== reply.id));
        setSelectedReply(null);
        setToast('Archived');
      })
      .catch(() => setToast('Archive failed'));
  };

  // Global stats
  const totalReplies = replies.length;
  const unreadCount = replies.filter((r) => !r.is_read).length;
  const meetingCount = replies.filter((r) => r.intent === 'meeting_request').length;

  return (
    <div className="space-y-5">
      {toast && <Toast msg={toast} onDone={() => setToast(null)} />}

      {/* Header */}
      <section
        className="relative overflow-hidden rounded-2xl p-6 lg:p-7"
        style={{
          background: 'linear-gradient(135deg, #0d2540 0%, #09131f 55%, #1c4d73 100%)',
          boxShadow: '0 8px 32px rgba(13,37,64,0.18)',
        }}
      >
        <div className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full bg-white/3" />
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <p className="text-[10px] font-bold uppercase tracking-widest mb-2" style={{ color: 'rgba(255,255,255,0.35)' }}>
              Reply Tracker
            </p>
            <h1 className="text-[1.65rem] font-extrabold tracking-tight text-white leading-tight sm:text-[2rem]">
              Track replies, campaign by campaign.
            </h1>
            <p className="mt-2 text-sm leading-relaxed" style={{ color: 'rgba(255,255,255,0.50)' }}>
              See who replied, their buying intent, and what actions have been taken — organized by campaign.
            </p>
          </div>
        </div>

        {/* Stat cards inside hero */}
        <div className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {([
            { label: 'Campaigns',     value: loading ? '—' : String(campaigns.length), key: 'campaigns', accent: '#1c8ed4', icon: MessageSquare },
            { label: 'Total Replies', value: loading ? '—' : String(totalReplies),      key: 'total',     accent: '#7c4dcc', icon: Mail          },
            { label: 'Unread',        value: loading ? '—' : String(unreadCount),       key: 'unread',    accent: '#d97706', icon: Eye           },
            { label: 'Meeting Req.',  value: loading ? '—' : String(meetingCount),      key: 'meeting',   accent: '#059669', icon: Calendar      },
          ] as { label: string; value: string; key: string; accent: string; icon: React.ElementType }[]).map((s) => {
            const isActive = headerFilter === s.key;
            const SIcon = s.icon;
            return (
              <button
                key={s.label}
                onClick={() => setHeaderFilter(s.key as 'campaigns' | 'total' | 'unread' | 'meeting')}
                className="relative overflow-hidden rounded-[26px] p-4 text-left transition-all hover:-translate-y-0.5"
                style={isActive
                  ? { background: 'linear-gradient(135deg, #4f46e5, #7c3aed)', boxShadow: '0 8px 24px rgba(79,70,229,0.35)' }
                  : { background: `linear-gradient(135deg, #0d2540 0%, #09131f 50%, ${s.accent} 100%)`, boxShadow: '0 6px 24px rgba(13,37,64,0.22)' }
                }
              >
                {/* white orbs always visible */}
                <div className="pointer-events-none absolute -right-8 -top-8 h-28 w-28 rounded-full bg-white/5" />
                <div className="pointer-events-none absolute -bottom-6 right-4 h-20 w-20 rounded-full bg-white/4" />
                <div className="relative flex items-center justify-between">
                  <p className="text-sm font-semibold text-white/60">{s.label}</p>
                  <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-white/12">
                    <SIcon className="h-4 w-4 text-white/80" />
                  </div>
                </div>
                <p className="relative mt-4 text-[1.9rem] font-extrabold tracking-[-0.04em] text-white tabular-nums">{s.value}</p>
                <p className="relative mt-1 text-[11px] font-semibold text-white/40">
                  {isActive ? 'Filtered ↓ click to clear' : 'Click to filter'}
                </p>
                <SIcon className="pointer-events-none absolute bottom-3 right-3 h-10 w-10 text-white/[0.05]" />
              </button>
            );
          })}
        </div>
      </section>

      {loading ? (
        <div className="flex items-center justify-center gap-3 py-24 text-white/40">
          <Loader2 className="h-5 w-5 animate-spin" />Loading replies…
        </div>
      ) : replies.length === 0 ? (
        <div className="glass-card rounded-[28px] px-5 py-20 text-center">
          <MessageSquare className="mx-auto h-10 w-10 text-white/10 mb-4" />
          <p className="text-base font-semibold text-white/70">No replies yet</p>
          <p className="mt-1 text-sm text-white/40">Launch a campaign to start receiving responses from prospects.</p>
        </div>
      ) : (
        <div className="flex h-[calc(100vh-280px)] gap-5">

          {/* Left: Campaign list */}
          <div className="w-[300px] flex-shrink-0 overflow-y-auto space-y-2.5 pr-0.5">
            {displayCampaigns.length === 0 ? (
              <p className="px-4 py-10 text-center text-sm text-white/40">No replies match this filter.</p>
            ) : displayCampaigns.map((cg) => (
              <CampaignCard
                key={cg.campaign_id}
                group={cg}
                isActive={selectedCampaign?.campaign_id === cg.campaign_id && !selectedReply}
                onClick={() => { setSelectedCampaign(cg); setSelectedReply(null); setShowReplyBox(false); }}
              />
            ))}
          </div>

          {/* Right: Detail panel */}
          <div className="flex-1 min-w-0 overflow-y-auto">
            {selectedReply ? (
              <ThreadView
                reply={selectedReply}
                onBack={() => setSelectedReply(null)}
                onArchive={handleArchive}
                showOutbound={showOutbound}
                setShowOutbound={setShowOutbound}
                showReplyBox={showReplyBox}
                setShowReplyBox={setShowReplyBox}
                replyText={replyText}
                setReplyText={setReplyText}
                onGenerateReply={() => {
                  setReplyText(selectedReply?.suggested_response || 'Hi,\n\nThank you for your reply! I would love to connect and discuss further.\n\nBest regards');
                  setShowReplyBox(true);
                }}
                onBookMeeting={() => setToast('Book Meeting: connect your calendar integration to enable this action.')}
                setToast={setToast}
                onReplySent={load}
              />
            ) : selectedGroupForDisplay ? (
              <CampaignDetail
                group={selectedGroupForDisplay}
                onSelectReply={(r) => { setSelectedReply(r); setShowReplyBox(false); }}
              />
            ) : (
              <div className="glass-card flex h-full flex-col items-center justify-center rounded-[28px] py-20 text-center">
                <MessageSquare className="mx-auto h-10 w-10 text-white/10 mb-4" />
                <p className="text-base font-semibold text-white/50">Select a campaign to view replies</p>
              </div>
            )}
          </div>

        </div>
      )}
    </div>
  );
}
