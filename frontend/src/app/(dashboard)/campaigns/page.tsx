'use client';

import { useEffect, useState } from 'react';
import { Archive, BarChart2, Clock, FileText, Loader2, Mail, MoreHorizontal, Pause, Play, Plus, Sparkles, Target, Zap } from 'lucide-react';
import { api, type PaginatedData } from '@/lib/api-client';
import { cn } from '@/lib/utils';
import { NewCampaignModal } from '@/components/campaigns/new-campaign-modal';
import { CampaignDraftsPanel } from '@/components/campaigns/campaign-drafts-panel';
import { CampaignReportPanel } from '@/components/campaigns/campaign-report-panel';

interface Campaign {
  id: string;
  name: string;
  description: string | null;
  status: string;
  campaign_type: string;
  vertical: string | null;
  total_leads: number;
  sent_count: number;
  sequence_steps: number;
  open_count: number;
  reply_count: number;
  bounce_count: number;
  launched_at: string | null;
  created_at: string;
  settings: { test_mode_snapshot?: { enabled?: boolean; emails?: { email: string; enabled: boolean }[] } } | null;
}

function openRate(c: Campaign): string {
  if (!c.sent_count) return '—';
  return `${((c.open_count / c.sent_count) * 100).toFixed(1)}%`;
}

function replyRate(c: Campaign): string {
  if (!c.sent_count) return '—';
  return `${((c.reply_count / c.sent_count) * 100).toFixed(1)}%`;
}

function relTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const h = Math.floor(diff / 3600000);
  const d = Math.floor(h / 24);
  if (h < 1) return 'Just now';
  if (h < 24) return `${h}h ago`;
  return `${d}d ago`;
}

const statusConfig: Record<string, { label: string; dot: string; text: string; bg: string; border: string; animate: boolean }> = {
  active:    { label: 'Active',    dot: 'bg-emerald-400', text: 'text-emerald-300', bg: 'bg-emerald-500/15', border: 'border-emerald-500/30', animate: true  },
  paused:    { label: 'Paused',    dot: 'bg-amber-400',   text: 'text-amber-300',   bg: 'bg-amber-500/15',   border: 'border-amber-500/30',   animate: false },
  draft:     { label: 'Draft',     dot: 'bg-white/30',    text: 'text-white/50',    bg: 'bg-white/[0.07]',   border: 'border-white/[0.12]',   animate: false },
  completed: { label: 'Completed', dot: 'bg-sky-400',     text: 'text-sky-300',     bg: 'bg-sky-500/15',     border: 'border-sky-500/30',     animate: false },
  archived:  { label: 'Archived',  dot: 'bg-white/20',    text: 'text-white/40',    bg: 'bg-white/[0.05]',   border: 'border-white/[0.08]',   animate: false },
};

function StatPill({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="flex flex-col">
      <span className={cn('text-base font-bold tabular-nums', color)}>{value}</span>
      <span className="text-[11px] text-gray-400">{label}</span>
    </div>
  );
}

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusTab, setStatusTab] = useState('all');
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [draftPanel, setDraftPanel] = useState<{ id: string; name: string } | null>(null);
  const [reportPanel, setReportPanel] = useState<{ id: string; name: string } | null>(null);
  const [openMenu, setOpenMenu] = useState<string | null>(null);

  useEffect(() => {
    if (!openMenu) return;
    const close = () => setOpenMenu(null);
    const closeKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpenMenu(null); };
    document.addEventListener('click', close);
    document.addEventListener('keydown', closeKey);
    return () => {
      document.removeEventListener('click', close);
      document.removeEventListener('keydown', closeKey);
    };
  }, [openMenu]);

  async function fetchCampaigns() {
    try {
      const data = await api<PaginatedData<Campaign>>({
        method: 'GET',
        url: '/campaigns',
        params: { page: 1, page_size: 50 },
      });
      setCampaigns(data.items);
    } catch {
      setCampaigns([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { fetchCampaigns(); }, []);

  // Auto-refresh every 10 s while any campaign is active
  useEffect(() => {
    const hasActive = campaigns.some((c) => c.status === 'active');
    if (!hasActive) return;
    const id = setInterval(fetchCampaigns, 10_000);
    return () => clearInterval(id);
  }, [campaigns]);

  async function handleAction(id: string, action: 'launch' | 'pause' | 'resume' | 'archive') {
    setActionLoading(id);
    try {
      await api({ method: 'POST', url: `/campaigns/${id}/${action}` });
      await fetchCampaigns();
      // Auto-open review panel after launch so user can review + approve drafts
      if (action === 'launch') {
        const launched = campaigns.find((c) => c.id === id);
        if (launched) setDraftPanel({ id: launched.id, name: launched.name });
      }
    } finally {
      setActionLoading(null);
    }
  }

  const tabs = ['all', 'active', 'paused', 'draft', 'completed'];

  const filtered = statusTab === 'all'
    ? campaigns
    : statusTab === 'with-leads'
    ? campaigns.filter((c) => c.total_leads > 0)
    : statusTab === 'with-sent'
    ? campaigns.filter((c) => c.sent_count > 0)
    : campaigns.filter((c) => c.status === statusTab);

  const activeCampaigns = campaigns.filter((c) => c.status === 'active').length;
  const totalLeads = campaigns.reduce((s, c) => s + c.total_leads, 0);
  const totalSent = campaigns.reduce((s, c) => s + c.sent_count, 0);

  const statCards = [
    { label: 'Live campaigns',    value: loading ? '—' : String(activeCampaigns),     icon: Sparkles,  filter: 'active',     accent: '#059669', accentBg: '#ecfdf5' },
    { label: 'Total campaigns',   value: loading ? '—' : String(campaigns.length),    icon: Target,    filter: 'all',        accent: '#1c8ed4', accentBg: '#e8f4fb' },
    { label: 'Contacts enrolled', value: loading ? '—' : totalLeads.toLocaleString(), icon: Zap,       filter: 'with-leads', accent: '#7c4dcc', accentBg: '#f0ebfd' },
    { label: 'Emails sent',       value: loading ? '—' : totalSent.toLocaleString(),  icon: BarChart2, filter: 'with-sent',  accent: '#d97706', accentBg: '#fffbeb' },
  ];

  return (
    <div className="space-y-5">
      {/* ── Hero section ──────────────────────────────── */}
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
              Campaign orchestration
            </p>
            <h1 className="text-[1.65rem] font-extrabold tracking-tight text-white leading-tight sm:text-[2rem]">
              Ship sequences with better control over quality, pace, and follow-up.
            </h1>
            <p className="mt-2 text-sm leading-relaxed" style={{ color: 'rgba(255,255,255,0.50)' }}>
              See which programs are compounding, which ones need intervention, and where attention should go next.
            </p>
          </div>
          <button
            onClick={() => setShowCreate(true)}
            className="inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold text-white transition-all hover:-translate-y-0.5 flex-shrink-0 self-start lg:self-auto"
            style={{ background: '#1c8ed4', boxShadow: '0 4px 14px rgba(28,142,212,0.35)' }}
          >
            <Plus className="h-4 w-4" />
            New Campaign
          </button>
        </div>

        {/* Stat cards inside hero */}
        <div className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {statCards.map((item) => {
            const isSelected = statusTab === item.filter;
            const Icon = item.icon;
            return (
              <button
                key={item.label}
                onClick={() => setStatusTab(item.filter)}
                className="relative overflow-hidden rounded-[26px] p-4 text-left transition-all hover:-translate-y-0.5"
                style={isSelected
                  ? { background: 'linear-gradient(135deg, #4f46e5, #7c3aed)', boxShadow: '0 8px 24px rgba(79,70,229,0.35)' }
                  : { background: `linear-gradient(135deg, #0d2540 0%, #09131f 50%, ${item.accent} 100%)`, boxShadow: '0 6px 24px rgba(13,37,64,0.22)' }
                }
              >
                {/* white orbs always visible */}
                <div className="pointer-events-none absolute -right-8 -top-8 h-28 w-28 rounded-full bg-white/5" />
                <div className="pointer-events-none absolute -bottom-6 right-4 h-20 w-20 rounded-full bg-white/4" />
                <div className="relative flex items-center justify-between">
                  <p className="text-sm font-semibold text-white/60">{item.label}</p>
                  <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-white/12">
                    <Icon className="h-4 w-4 text-white/80" />
                  </div>
                </div>
                <p className="relative mt-4 text-[1.9rem] font-extrabold tracking-[-0.04em] text-white tabular-nums">{item.value}</p>
                <p className="relative mt-1 text-[11px] font-semibold text-white/40">
                  {isSelected ? 'Filtered ↓ click to clear' : 'Click to filter'}
                </p>
                <Icon className="pointer-events-none absolute bottom-3 right-3 h-10 w-10 text-white/[0.05]" />
              </button>
            );
          })}
        </div>
      </section>

      {/* ── Status tab bar ────────────────────────────── */}
      <div className="flex w-fit gap-1 rounded-xl border border-white/[0.08] bg-white/[0.04] p-1">
        {tabs.map((tab) => (
          <button
            key={tab}
            onClick={() => setStatusTab(tab)}
            className={cn(
              'rounded-lg px-3.5 py-1.5 text-xs font-semibold capitalize transition-all',
              statusTab === tab
                ? 'bg-white/[0.12] text-white shadow-sm'
                : 'text-white/40 hover:text-white hover:bg-white/[0.06]'
            )}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* ── Campaign list ─────────────────────────────── */}
      {loading ? (
        <div className="flex items-center justify-center gap-3 py-20 text-white/40">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span className="text-sm">Loading campaigns…</span>
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-white/[0.07] bg-white/[0.03] py-16 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-white/[0.07] mb-4">
            <Sparkles className="h-6 w-6 text-white/30" />
          </div>
          <p className="text-base font-semibold text-white/70">
            {statusTab === 'all' ? 'No campaigns yet' : `No ${statusTab} campaigns`}
          </p>
          <p className="mt-1 text-sm text-white/40">Create your first campaign to start sending.</p>
          <button
            onClick={() => setShowCreate(true)}
            className="mt-4 inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold text-white"
            style={{ background: '#1c8ed4' }}
          >
            <Plus className="h-4 w-4" /> New Campaign
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {filtered.map((campaign) => {
            const cfg = statusConfig[campaign.status] ?? statusConfig.draft;
            const busy = actionLoading === campaign.id;
            const menuOpen = openMenu === campaign.id;
            const steps = campaign.sequence_steps || 1;
            const totalExpected = steps * campaign.total_leads;
            const progress = totalExpected > 0
              ? Math.min(100, Math.round((campaign.sent_count / totalExpected) * 100))
              : 0;
            return (
              <div
                key={campaign.id}
                className="group relative rounded-2xl border border-white/[0.08] bg-white/[0.04] p-5 transition-all hover:-translate-y-0.5 hover:border-white/[0.14] hover:bg-white/[0.06]"
                style={{ boxShadow: '0 4px 20px rgba(13,37,64,0.18)' }}
              >
                {/* Header */}
                <div className="mb-4 flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="mb-2 flex items-center gap-2 flex-wrap">
                      <span className={cn('inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold border', cfg.bg, cfg.text, cfg.border)}>
                        <span className={cn('h-1.5 w-1.5 rounded-full', cfg.dot, cfg.animate && 'animate-pulse')} />
                        {cfg.label}
                      </span>
                      {campaign.vertical && (
                        <span className="rounded-full border border-white/[0.1] bg-white/[0.06] px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-white/50">
                          {campaign.vertical}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <h3 className="truncate text-base font-bold tracking-tight text-white">{campaign.name}</h3>
                      {campaign.settings?.test_mode_snapshot?.enabled && (
                        <span className="flex-shrink-0 rounded-full bg-amber-500/20 border border-amber-500/30 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-300">
                          Test
                        </span>
                      )}
                    </div>
                    {campaign.description && (
                      <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-white/40">{campaign.description}</p>
                    )}
                  </div>
                  {/* 3-dot menu */}
                  <div className="relative flex-shrink-0">
                    <button
                      onClick={(e) => { e.stopPropagation(); setOpenMenu(menuOpen ? null : campaign.id); }}
                      className={cn(
                        'rounded-lg p-2 text-white/30 transition-colors hover:bg-white/[0.07] hover:text-white',
                        menuOpen && 'bg-white/[0.07] text-white',
                      )}
                    >
                      <MoreHorizontal className="h-4 w-4" />
                    </button>
                    {menuOpen && (
                      <div
                        onClick={(e) => e.stopPropagation()}
                        className="absolute right-0 top-full z-50 mt-1 w-48 rounded-xl border border-white/[0.1] overflow-hidden"
                        style={{ background: '#0d1525', boxShadow: '0 12px 32px rgba(0,0,0,0.4)' }}
                      >
                        <div className="py-1">
                          <button
                            onClick={() => { setOpenMenu(null); setDraftPanel({ id: campaign.id, name: campaign.name }); }}
                            className="flex w-full items-center gap-2.5 px-4 py-2.5 text-sm text-white/70 hover:bg-white/[0.06] transition-colors"
                          >
                            <Mail className="h-3.5 w-3.5 text-sky-400" />
                            Review email drafts
                          </button>
                          {campaign.status === 'draft' && (
                            <button
                              disabled={busy}
                              onClick={() => handleAction(campaign.id, 'launch')}
                              className="flex w-full items-center gap-2.5 px-4 py-2.5 text-sm text-emerald-300 hover:bg-white/[0.06] transition-colors disabled:opacity-60"
                            >
                              <Play className="h-3.5 w-3.5" /> Launch campaign
                            </button>
                          )}
                          {campaign.status === 'active' && (
                            <button
                              disabled={busy}
                              onClick={() => handleAction(campaign.id, 'pause')}
                              className="flex w-full items-center gap-2.5 px-4 py-2.5 text-sm text-amber-300 hover:bg-white/[0.06] transition-colors disabled:opacity-60"
                            >
                              <Pause className="h-3.5 w-3.5" /> Pause campaign
                            </button>
                          )}
                          {campaign.status === 'paused' && (
                            <button
                              disabled={busy}
                              onClick={() => handleAction(campaign.id, 'resume')}
                              className="flex w-full items-center gap-2.5 px-4 py-2.5 text-sm text-emerald-300 hover:bg-white/[0.06] transition-colors disabled:opacity-60"
                            >
                              <Play className="h-3.5 w-3.5" /> Resume campaign
                            </button>
                          )}
                          <div className="mx-3 my-1 border-t border-white/[0.07]" />
                          <button
                            onClick={() => handleAction(campaign.id, 'archive')}
                            className="flex w-full items-center gap-2.5 px-4 py-2.5 text-sm text-rose-400 hover:bg-white/[0.06] transition-colors"
                          >
                            <Archive className="h-3.5 w-3.5" /> Archive
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Stats row */}
                <div className="mb-4 grid grid-cols-4 gap-3 rounded-xl bg-white/[0.04] p-3 border border-white/[0.06]">
                  {[
                    { label: 'Leads',   value: campaign.total_leads.toLocaleString(), color: 'text-white'        },
                    { label: 'Sent',    value: campaign.sent_count.toLocaleString(),  color: 'text-sky-300'     },
                    { label: 'Open %',  value: openRate(campaign),                    color: 'text-emerald-300' },
                    { label: 'Reply %', value: replyRate(campaign),                   color: 'text-violet-300'  },
                  ].map((s) => (
                    <div key={s.label} className="flex flex-col">
                      <span className={cn('text-base font-bold tabular-nums leading-none', s.color)}>{s.value}</span>
                      <span className="mt-0.5 text-[10px] text-white/35">{s.label}</span>
                    </div>
                  ))}
                </div>

                {/* Progress bar */}
                <div className="mb-4">
                  <div className="mb-1.5 flex items-center justify-between">
                    <span className="text-[11px] text-white/35">Campaign progress</span>
                    <span className="text-[11px] font-semibold text-white/50 tabular-nums">{campaign.sent_count}/{totalExpected} sent · {progress}%</span>
                  </div>
                  <div className="h-1.5 w-full rounded-full bg-white/[0.08] overflow-hidden">
                    <div
                      className={cn('h-full rounded-full transition-all duration-500')}
                      style={{
                        width: `${progress}%`,
                        background: campaign.status === 'active'
                          ? 'linear-gradient(90deg,#059669,#10b981)'
                          : campaign.status === 'completed'
                          ? '#3b82f6'
                          : campaign.status === 'paused'
                          ? '#f59e0b'
                          : '#94a3b8',
                      }}
                    />
                  </div>
                </div>

                {/* Footer */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-[11px] text-white/35">
                    <Clock className="h-3 w-3" />
                    {campaign.launched_at ? relTime(campaign.launched_at) : relTime(campaign.created_at)}
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setDraftPanel({ id: campaign.id, name: campaign.name })}
                      className="flex items-center gap-1.5 rounded-lg border border-white/[0.1] bg-white/[0.05] px-2.5 py-1.5 text-[11px] font-semibold text-white/60 transition-colors hover:bg-white/[0.09]"
                    >
                      <Mail className="h-3.5 w-3.5" /> Review
                    </button>
                    <button
                      onClick={() => setReportPanel({ id: campaign.id, name: campaign.name })}
                      className="flex items-center gap-1.5 rounded-lg border border-[#1c8ed4]/25 bg-[#1c8ed4]/10 px-2.5 py-1.5 text-[11px] font-semibold text-[#5bb8f5] transition-colors hover:bg-[#1c8ed4]/20"
                    >
                      <FileText className="h-3.5 w-3.5" /> Report
                    </button>
                    {campaign.status === 'active' ? (
                      <button
                        disabled={busy || progress === 100}
                        onClick={() => handleAction(campaign.id, 'pause')}
                        className="flex items-center gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/15 px-2.5 py-1.5 text-[11px] font-semibold text-amber-300 transition-colors hover:bg-amber-500/25 disabled:opacity-40"
                      >
                        {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Pause className="h-3 w-3" />} Pause
                      </button>
                    ) : campaign.status === 'paused' ? (
                      <button
                        disabled={busy}
                        onClick={() => handleAction(campaign.id, 'resume')}
                        className="flex items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/15 px-2.5 py-1.5 text-[11px] font-semibold text-emerald-300 transition-colors hover:bg-emerald-500/25 disabled:opacity-60"
                      >
                        {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />} Resume
                      </button>
                    ) : campaign.status === 'draft' ? (
                      <button
                        disabled={busy}
                        onClick={() => handleAction(campaign.id, 'launch')}
                        className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] font-semibold text-white transition-all hover:-translate-y-px disabled:opacity-60"
                        style={{ background: 'linear-gradient(135deg,#1c8ed4,#0e6bab)', boxShadow: '0 3px 10px rgba(28,142,212,0.3)' }}
                      >
                        {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />} Launch
                      </button>
                    ) : null}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <NewCampaignModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={fetchCampaigns}
      />

      {reportPanel && (
        <CampaignReportPanel
          campaignId={reportPanel.id}
          campaignName={reportPanel.name}
          onClose={() => setReportPanel(null)}
        />
      )}

      {draftPanel && (() => {
        const c = campaigns.find((c) => c.id === draftPanel.id);
        const snap = c?.settings?.test_mode_snapshot;
        const testEmails = snap?.enabled
          ? (snap.emails?.filter((e) => e.enabled).map((e) => e.email) ?? [])
          : [];
        return (
          <CampaignDraftsPanel
            campaignId={draftPanel.id}
            campaignName={draftPanel.name}
            testEmails={testEmails}
            onClose={() => setDraftPanel(null)}
          />
        );
      })()}
    </div>
  );
}
