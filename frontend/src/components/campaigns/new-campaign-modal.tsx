'use client';

import { useEffect, useRef, useState } from 'react';
import { X, Plus, Trash2, Loader2, ChevronDown, Search, Check, Users } from 'lucide-react';
import { api } from '@/lib/api-client';
import { cn } from '@/lib/utils';

interface SequenceStep {
  step: number;
  delay_days: number;
  subject_template: string;
  body_template: string;
  ai_generate: boolean;
  condition: string | null;
}

interface SenderAccount {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
}

interface ScoredLead {
  id: string;
  name: string;
  title: string;
  company: string;
  score_tier: string | null;
  score_value: number | null;
  active_campaign_name: string | null;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}


const tierConfig: Record<string, { label: string; className: string }> = {
  hot:  { label: 'Hot',  className: 'bg-rose-500/20 text-rose-300' },
  warm: { label: 'Warm', className: 'bg-amber-500/20 text-amber-300' },
  cold: { label: 'Cold', className: 'bg-white/10 text-white/40' },
};

function addBusinessDays(start: Date, days: number): Date {
  const result = new Date(start);
  let added = 0;
  while (added < days) {
    result.setDate(result.getDate() + 1);
    const dow = result.getDay(); // 0=Sun,1=Mon,...,5=Sat,6=Sun
    if (dow >= 1 && dow <= 4) added++; // Mon–Thu only
  }
  return result;
}

function formatIST(date: Date): string {
  return date.toLocaleString('en-IN', {
    timeZone: 'Asia/Kolkata',
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  }) + ' IST';
}

function defaultStep(n: number): SequenceStep {
  return {
    step: n,
    delay_days: n === 1 ? 0 : 3,
    subject_template: '',
    body_template: '',
    ai_generate: true,
    condition: n === 1 ? null : 'no_reply',
  };
}

export function NewCampaignModal({ open, onClose, onCreated }: Props) {
  const [tab, setTab] = useState<'sequence' | 'leads'>('sequence');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [vertical] = useState('Events Technology');
  const [campaignType] = useState('outbound');
  const [steps, setSteps] = useState<SequenceStep[]>([defaultStep(1)]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // Sender accounts
  const [senderAccounts, setSenderAccounts] = useState<SenderAccount[]>([]);
  const [senderAccountId, setSenderAccountId] = useState<string>('');

  // Lead picker state
  const [leads, setLeads] = useState<ScoredLead[]>([]);
  const [leadsLoading, setLeadsLoading] = useState(false);
  const [leadSearch, setLeadSearch] = useState('');
  const [selectedLeadIds, setSelectedLeadIds] = useState<Set<string>>(new Set());

  const backdropRef = useRef<HTMLDivElement>(null);

  // Reset form when opened
  useEffect(() => {
    if (open) {
      setTab('sequence');
      setName(''); setDescription('');
      setSteps([defaultStep(1)]);
      setError('');
      setLeadSearch('');
      setSelectedLeadIds(new Set());
      setSenderAccountId('');
      fetchLeads();
      fetchSenderAccounts();
    }
  }, [open]);

  async function fetchSenderAccounts() {
    try {
      const data = await api<SenderAccount[]>({ method: 'GET', url: '/admin/sender-accounts' });
      const active = (Array.isArray(data) ? data : []).filter((a) => a.is_active);
      setSenderAccounts(active);
      if (active.length === 1) setSenderAccountId(active[0].id);
    } catch {
      setSenderAccounts([]);
    }
  }

  async function fetchLeads() {
    setLeadsLoading(true);
    try {
      const data = await api<{ items: Array<{
        id: string;
        status: string;
        contact?: { first_name?: string; last_name?: string; title?: string | null } | null;
        company?: { name?: string } | null;
        score_tier?: string | null;
        score_value?: number | null;
        active_campaign_name?: string | null;
      }> }>({
        method: 'GET',
        url: '/leads',
        params: { page: 1, page_size: 100, sort_by: 'updated_at', sort_dir: 'desc' },
      });
      const scored = data.items
        .filter((l) => l.score_tier != null)
        .map((l) => ({
          id: l.id,
          name: `${l.contact?.first_name ?? ''} ${l.contact?.last_name ?? ''}`.trim() || 'Unknown',
          title: l.contact?.title ?? '',
          company: l.company?.name ?? 'Unknown company',
          score_tier: l.score_tier ?? null,
          score_value: l.score_value ?? null,
          active_campaign_name: l.active_campaign_name ?? null,
        }));
      setLeads(scored);
    } catch {
      // Non-fatal: leads picker just shows empty
    } finally {
      setLeadsLoading(false);
    }
  }

  // Close on Escape
  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose(); }
    if (open) document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  function addStep() {
    setSteps((prev) => [...prev, defaultStep(prev.length + 1)]);
  }

  function removeStep(i: number) {
    setSteps((prev) => prev.filter((_, idx) => idx !== i).map((s, idx) => ({ ...s, step: idx + 1 })));
  }

  function updateStep(i: number, patch: Partial<SequenceStep>) {
    setSteps((prev) => prev.map((s, idx) => idx === i ? { ...s, ...patch } : s));
  }

  function toggleLead(id: string) {
    setSelectedLeadIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) { setError('Campaign name is required.'); setTab('sequence'); return; }
    if (!senderAccountId) { setError('Select a sender account to send from.'); setTab('sequence'); return; }
    if (steps.length === 0) { setError('Add at least one sequence step.'); setTab('sequence'); return; }
    setError('');
    setSaving(true);
    try {
      const res = await api<{ id: string }>({
        method: 'POST',
        url: '/campaigns',
        data: {
          name: name.trim(),
          description: description.trim() || null,
          campaign_type: campaignType,
          vertical: vertical || null,
          sequence: steps,
          sender_account_id: senderAccountId || null,
        },
      });
      // Enroll selected leads if any
      const leadIds = [...selectedLeadIds];
      if (leadIds.length > 0 && res?.id) {
        await api({
          method: 'POST',
          url: `/campaigns/${res.id}/leads`,
          data: { lead_ids: leadIds },
        });
      }
      onCreated();
      onClose();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? 'Failed to create campaign. Please try again.');
    } finally {
      setSaving(false);
    }
  }

  const filteredLeads = leads.filter((l) => {
    const q = leadSearch.toLowerCase();
    return !q || l.name.toLowerCase().includes(q) || l.company.toLowerCase().includes(q);
  });

  if (!open) return null;

  // Compute estimated send date for each step (business days Mon–Thu, skipping Fri/Sat/Sun)
  const stepDates = steps.reduce<Date[]>((acc, step, i) => {
    if (i === 0) return [...acc, new Date()];
    const prev = acc[i - 1];
    return [...acc, addBusinessDays(new Date(prev), Math.max(step.delay_days, 1))];
  }, []);

  return (
    <div
      ref={backdropRef}
      onClick={(e) => { if (e.target === backdropRef.current) onClose(); }}
      className="fixed inset-0 z-50 flex items-end justify-end bg-black/60 backdrop-blur-sm sm:items-center sm:justify-center"
    >
      <div className="flex h-[92dvh] w-full flex-col overflow-hidden rounded-t-[32px] bg-[#0d1929] border border-white/[0.08] shadow-[0_-24px_80px_rgba(0,0,0,0.5)] sm:h-auto sm:max-h-[90dvh] sm:w-[640px] sm:rounded-[32px]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-white/[0.08] px-6 py-5">
          <div>
            <h2 className="text-lg font-bold tracking-[-0.04em] text-white">New Campaign</h2>
            <p className="text-xs text-white/50">Define your sequence and targeting before launch.</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-full p-2 text-white/40 transition-colors hover:bg-white/[0.08] hover:text-white"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-white/[0.08] px-6">
          {([
            { id: 'sequence', label: 'Sequence' },
            { id: 'leads',    label: `Select Leads${selectedLeadIds.size > 0 ? ` (${selectedLeadIds.size})` : ''}` },
          ] as const).map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={cn(
                'mr-4 border-b-2 py-3 text-sm font-semibold transition-colors',
                tab === t.id
                  ? 'border-[#1c8ed4] text-white'
                  : 'border-transparent text-white/40 hover:text-white/70',
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} className="flex flex-1 flex-col overflow-hidden">
          <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">

            {tab === 'sequence' && (
              <>
                {/* Name */}
                <div>
                  <label className="mb-1.5 block text-xs font-semibold uppercase tracking-[0.12em] text-white/50">
                    Campaign Name <span className="text-red-400">*</span>
                  </label>
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Cvent Directors Q2"
                    className="w-full rounded-[14px] border border-white/[0.10] bg-white/[0.06] px-4 py-3 text-sm text-white placeholder:text-white/30 focus:border-[#1c8ed4] focus:outline-none"
                  />
                </div>

                {/* Description */}
                <div>
                  <label className="mb-1.5 block text-xs font-semibold uppercase tracking-[0.12em] text-white/50">
                    Description
                  </label>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="What's the goal of this campaign?"
                    rows={2}
                    className="w-full resize-none rounded-[14px] border border-white/[0.10] bg-white/[0.06] px-4 py-3 text-sm text-white placeholder:text-white/30 focus:border-[#1c8ed4] focus:outline-none"
                  />
                </div>

                {/* Sender Account */}
                <div>
                  <label className="mb-1.5 block text-xs font-semibold uppercase tracking-[0.12em] text-white/50">
                    Send from <span className="text-red-400">*</span>
                  </label>
                  {senderAccounts.length === 0 ? (
                    <p className="rounded-[14px] border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-300">
                      No active sender accounts found. Add one in <strong>Settings → Email Accounts</strong> first.
                    </p>
                  ) : (
                    <div className="relative">
                      <select
                        value={senderAccountId}
                        onChange={(e) => setSenderAccountId(e.target.value)}
                        className="w-full appearance-none rounded-[14px] border border-white/[0.10] bg-[#0d1929] px-4 py-3 pr-9 text-sm text-white focus:border-[#1c8ed4] focus:outline-none"
                        required
                      >
                        <option value="">— Select a sender —</option>
                        {senderAccounts.map((a) => (
                          <option key={a.id} value={a.id}>
                            {a.display_name} ({a.email})
                          </option>
                        ))}
                      </select>
                      <ChevronDown className="pointer-events-none absolute right-3 top-3.5 h-4 w-4 text-white/40" />
                    </div>
                  )}
                </div>

                {/* Sequence Steps */}
                <div>
                  <div className="mb-2 flex items-center justify-between">
                    <label className="text-xs font-semibold uppercase tracking-[0.12em] text-white/50">
                      Sequence Steps <span className="text-red-400">*</span>
                    </label>
                    <button
                      type="button"
                      onClick={addStep}
                      className="flex items-center gap-1 rounded-full bg-[#1c8ed4] px-3 py-1.5 text-[11px] font-semibold text-white hover:bg-[#1577b5]"
                    >
                      <Plus className="h-3 w-3" /> Add step
                    </button>
                  </div>

                  <div className="space-y-3">
                    {steps.map((step, i) => (
                      <div key={i} className="rounded-[18px] border border-white/[0.08] bg-white/[0.04] p-4">
                        <div className="mb-3 flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[#1c8ed4] text-[10px] font-bold text-white">
                              {step.step}
                            </span>
                            <span className="text-xs font-semibold text-white/70">Step {step.step}</span>
                          </div>
                          <div className="flex items-center gap-3">
                            <label className="flex items-center gap-1.5 text-[11px] text-white/50 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={step.ai_generate}
                                onChange={(e) => updateStep(i, { ai_generate: e.target.checked })}
                                className="h-3.5 w-3.5 accent-[#1c8ed4]"
                              />
                              AI-generate copy
                            </label>
                            {steps.length > 1 && (
                              <button
                                type="button"
                                onClick={() => removeStep(i)}
                                className="rounded-full p-1 text-white/30 hover:text-red-400"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </button>
                            )}
                          </div>
                        </div>

                        {i > 0 && (
                          <div className="mb-3 flex flex-wrap items-center gap-4">
                            <div>
                              <label className="mb-1 block text-[11px] font-semibold text-white/40">Delay (business days after previous)</label>
                              <input
                                type="number"
                                min={1}
                                max={30}
                                value={step.delay_days}
                                onChange={(e) => updateStep(i, { delay_days: Number(e.target.value) })}
                                className="w-24 rounded-[10px] border border-white/[0.10] bg-white/[0.06] px-3 py-1.5 text-sm text-white focus:border-[#1c8ed4] focus:outline-none"
                              />
                              <p className="mt-1 text-[10px] text-[#60b7e8]/80">
                                {formatIST(stepDates[i])}
                              </p>
                            </div>
                            <label className="flex items-center gap-1.5 cursor-pointer mt-4">
                              <input
                                type="checkbox"
                                checked={step.condition === 'no_reply'}
                                onChange={(e) => updateStep(i, { condition: e.target.checked ? 'no_reply' : null })}
                                className="h-3.5 w-3.5 accent-[#1c8ed4]"
                              />
                              <span className="text-[11px] font-semibold text-white/60">Only send if no reply</span>
                            </label>
                          </div>
                        )}

                        {i > 0 && step.condition === 'no_reply' && (
                          <p className="mb-3 rounded-[10px] bg-emerald-500/10 px-3 py-2 text-[11px] text-emerald-300">
                            ↩ This step will only send if the prospect hasn't replied to the previous step.
                          </p>
                        )}

                        {!step.ai_generate && (
                          <div className="space-y-2">
                            <input
                              value={step.subject_template}
                              onChange={(e) => updateStep(i, { subject_template: e.target.value })}
                              placeholder="Email subject line"
                              className="w-full rounded-[10px] border border-white/[0.08] bg-white/[0.06] px-3 py-2 text-sm text-white placeholder:text-white/30 focus:border-[#1c8ed4] focus:outline-none"
                            />
                            <textarea
                              value={step.body_template}
                              onChange={(e) => updateStep(i, { body_template: e.target.value })}
                              placeholder="Email body…"
                              rows={3}
                              className="w-full resize-none rounded-[10px] border border-white/[0.08] bg-white/[0.06] px-3 py-2 text-sm text-white placeholder:text-white/30 focus:border-[#1c8ed4] focus:outline-none"
                            />
                          </div>
                        )}

                        {step.ai_generate && (
                          <p className="rounded-[10px] bg-[#1c8ed4]/10 px-3 py-2 text-[11px] text-[#60b7e8]">
                            ✦ AI will generate personalized copy for each contact based on their enrichment data.
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}

            {tab === 'leads' && (
              <div>
                <div className="mb-3 flex items-center justify-between">
                  <div>
                    <p className="text-sm font-semibold text-white">Select scored leads to enroll</p>
                    <p className="text-xs text-white/50 mt-0.5">Only leads with a score are shown. Leads already in a campaign are tagged.</p>
                  </div>
                  {selectedLeadIds.size > 0 && (
                    <span className="rounded-full bg-[#1c8ed4] px-3 py-1 text-[11px] font-semibold text-white">
                      {selectedLeadIds.size} selected
                    </span>
                  )}
                </div>

                {/* Search */}
                <div className="relative mb-3">
                  <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-white/40" />
                  <input
                    value={leadSearch}
                    onChange={(e) => setLeadSearch(e.target.value)}
                    placeholder="Search by name or company…"
                    className="w-full rounded-[14px] border border-white/[0.10] bg-white/[0.06] px-10 py-2.5 text-sm text-white placeholder:text-white/30 focus:border-[#1c8ed4] focus:outline-none"
                  />
                </div>

                {leadsLoading ? (
                  <div className="flex items-center justify-center py-10">
                    <Loader2 className="h-5 w-5 animate-spin text-white/40" />
                  </div>
                ) : filteredLeads.length === 0 ? (
                  <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
                    <Users className="h-8 w-8 text-white/20" />
                    <p className="text-sm text-white/50">No scored leads found.</p>
                    <p className="text-xs text-white/30">Score your leads first to enroll them in this campaign.</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {filteredLeads.map((lead) => {
                      const isSelected = selectedLeadIds.has(lead.id);
                      return (
                        <button
                          key={lead.id}
                          type="button"
                          onClick={() => toggleLead(lead.id)}
                          className={cn(
                            'w-full flex items-center gap-3 rounded-[16px] border p-3.5 text-left transition-all',
                            isSelected
                              ? 'border-[#1c8ed4] bg-[#1c8ed4]/10'
                              : 'border-white/[0.08] bg-white/[0.03] hover:border-white/[0.16] hover:bg-white/[0.06]',
                          )}
                        >
                          {/* Checkbox */}
                          <div className={cn(
                            'flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 transition-colors',
                            isSelected ? 'border-[#1c8ed4] bg-[#1c8ed4]' : 'border-white/30',
                          )}>
                            {isSelected && <Check className="h-3 w-3 text-white" />}
                          </div>

                          {/* Avatar initials */}
                          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#1c8ed4]/20 text-[11px] font-bold text-[#60b7e8]">
                            {lead.name.split(' ').map((n) => n[0]).slice(0, 2).join('')}
                          </div>

                          {/* Info */}
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="text-sm font-semibold text-white truncate">{lead.name}</span>
                              {lead.score_tier && (
                                <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-bold', tierConfig[lead.score_tier]?.className ?? 'bg-white/10 text-white/40')}>
                                  {tierConfig[lead.score_tier]?.label ?? lead.score_tier}
                                  {lead.score_value != null ? ` · ${lead.score_value}` : ''}
                                </span>
                              )}
                              {lead.active_campaign_name && (
                                <span className="rounded-full border border-white/[0.12] bg-white/[0.08] px-2 py-0.5 text-[10px] font-semibold text-white/60">
                                  In: {lead.active_campaign_name}
                                </span>
                              )}
                            </div>
                            <p className="mt-0.5 truncate text-xs text-white/50">{lead.title} · {lead.company}</p>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {error && (
              <p className="rounded-[12px] bg-red-500/10 border border-red-500/20 px-4 py-2.5 text-sm text-red-400">{error}</p>
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between gap-3 border-t border-white/[0.08] px-6 py-4">
            <div className="text-xs text-white/40">
              {selectedLeadIds.size > 0
                ? `${selectedLeadIds.size} lead${selectedLeadIds.size > 1 ? 's' : ''} will be enrolled`
                : 'No leads selected yet'}
            </div>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={onClose}
                className="rounded-full border border-white/[0.12] px-5 py-2.5 text-sm font-semibold text-white/60 transition-colors hover:bg-white/[0.08] hover:text-white"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                className={cn(
                  'flex items-center gap-2 rounded-full bg-[#1c8ed4] px-5 py-2.5 text-sm font-semibold text-white shadow-[0_12px_24px_rgba(28,142,212,0.25)] transition-all hover:bg-[#1577b5] disabled:opacity-60'
                )}
              >
                {saving && <Loader2 className="h-4 w-4 animate-spin" />}
                {saving ? 'Creating…' : 'Create Campaign'}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
