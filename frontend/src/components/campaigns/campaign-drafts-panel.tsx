'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  Check,
  ChevronDown,
  ChevronUp,
  Loader2,
  Mail,
  Pencil,
  RefreshCw,
  Send,
  Sparkles,
  X,
} from 'lucide-react';
import { api } from '@/lib/api-client';
import { cn } from '@/lib/utils';

interface MessageDraft {
  id: string;
  campaign_id: string;
  lead_id: string;
  lead_name: string | null;
  lead_email: string | null;
  lead_company: string | null;
  from_email: string | null;
  from_name: string | null;
  sequence_step: number | null;
  subject: string | null;
  body_html: string | null;
  body_text: string | null;
  status: string;
  error_message: string | null;
  ai_generated: boolean;
  personalization_hooks: string[] | null;
  created_at: string;
}

interface EditState {
  subject: string;
  body_text: string;
  saving: boolean;
  saved: boolean;
}

interface Props {
  campaignId: string;
  campaignName: string;
  testEmails?: string[];
  onClose: () => void;
}

const statusConfig: Record<string, { label: string; className: string }> = {
  draft:   { label: 'Draft',   className: 'bg-amber-500/20 text-amber-300 border-amber-500/30' },
  queued:  { label: 'Queued',  className: 'bg-blue-500/20 text-blue-300 border-blue-500/30' },
  sending: { label: 'Sending', className: 'bg-sky-500/20 text-sky-300 border-sky-500/30' },
  sent:    { label: 'Sent',    className: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' },
  failed:  { label: 'Failed',  className: 'bg-red-500/20 text-red-300 border-red-500/30' },
};

export function CampaignDraftsPanel({ campaignId, campaignName, testEmails, onClose }: Props) {
  const [messages, setMessages] = useState<MessageDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editState, setEditState] = useState<EditState | null>(null);
  const [sendingId, setSendingId] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchMessages = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const data = await api<MessageDraft[]>({
        method: 'GET',
        url: `/campaigns/${campaignId}/messages`,
      });
      setMessages(data);
    } catch {
      if (!silent) setError('Failed to load messages. The campaign may still be generating drafts.');
    } finally {
      if (!silent) setLoading(false);
    }
  }, [campaignId]);

  useEffect(() => {
    fetchMessages();
  }, [fetchMessages]);

  // Poll every 4 s while we have 0 drafts (AI is still generating)
  useEffect(() => {
    const hasDrafts = messages.some((m) => m.status === 'draft');
    const stillEmpty = messages.length === 0;
    if (stillEmpty || hasDrafts) {
      if (!pollRef.current) {
        pollRef.current = setInterval(() => fetchMessages(true), 4000);
      }
    } else {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    }
    return () => {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    };
  }, [messages, fetchMessages]);

  function startEdit(msg: MessageDraft) {
    setEditingId(msg.id);
    setEditState({ subject: msg.subject ?? '', body_text: msg.body_text ?? '', saving: false, saved: false });
  }

  function cancelEdit() {
    setEditingId(null);
    setEditState(null);
  }

  async function saveEdit(msgId: string) {
    if (!editState) return;
    setEditState((s) => s ? { ...s, saving: true } : s);
    try {
      await api({
        method: 'PATCH',
        url: `/campaigns/${campaignId}/messages/${msgId}`,
        data: { subject: editState.subject, body_text: editState.body_text },
      });
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId
            ? { ...m, subject: editState.subject, body_text: editState.body_text }
            : m
        )
      );
      setEditState((s) => s ? { ...s, saving: false, saved: true } : s);
      setTimeout(() => { setEditingId(null); setEditState(null); }, 800);
    } catch {
      setEditState((s) => s ? { ...s, saving: false } : s);
      setError('Failed to save changes.');
    }
  }

  async function handleSend(message: MessageDraft) {
    if (sendingId) return;
    setSendingId(message.id);
    try {
      await api({
        method: 'POST',
        url: `/campaigns/${campaignId}/messages/${message.id}/send`,
      });
      setMessages((prev) =>
        prev.map((m) => (m.id === message.id ? { ...m, status: 'queued' } : m))
      );
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? 'Failed to send message.');
    } finally {
      setSendingId(null);
    }
  }

  async function handleSendAll() {
    const drafts = messages.filter((m) => m.status === 'draft');
    for (const draft of drafts) {
      await handleSend(draft);
    }
  }

  const draftCount = messages.filter((m) => m.status === 'draft').length;
  const sentCount = messages.filter((m) => ['sent', 'queued', 'sending'].includes(m.status)).length;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="flex h-[90dvh] w-full max-w-2xl flex-col overflow-hidden rounded-[32px] bg-[#0d1929] border border-white/[0.08] shadow-[0_40px_100px_rgba(0,0,0,0.5)]">
        {/* Header */}
        <div className="flex items-start justify-between border-b border-white/[0.08] px-6 py-5">
          <div>
            <div className="flex items-center gap-2">
              <Mail className="h-4 w-4 text-[#1c8ed4]" />
              <h2 className="text-lg font-bold tracking-[-0.04em] text-white">Review Drafts</h2>
            </div>
            <p className="mt-0.5 text-xs text-white/50">{campaignName}</p>
            <div className="mt-2 flex items-center gap-2">
              {draftCount > 0 && (
                <span className="rounded-full bg-amber-500/20 px-2.5 py-0.5 text-[10px] font-semibold text-amber-300">
                  {draftCount} pending review
                </span>
              )}
              {sentCount > 0 && (
                <span className="rounded-full bg-emerald-500/20 px-2.5 py-0.5 text-[10px] font-semibold text-emerald-300">
                  {sentCount} sent / queued
                </span>
              )}
              {testEmails && testEmails.length > 0 && (
                <span className="rounded-full bg-[#1c8ed4]/20 px-2.5 py-0.5 text-[10px] font-semibold text-[#60b7e8]">
                  → {testEmails.join(', ')}
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {draftCount > 0 && (
              <button
                onClick={handleSendAll}
                disabled={!!sendingId}
                className="flex items-center gap-1.5 rounded-full bg-[#1c8ed4] px-3.5 py-2 text-[11px] font-semibold text-white hover:bg-[#1577b5] disabled:opacity-60"
              >
                {sendingId ? <Loader2 className="h-3 w-3 animate-spin" /> : <Send className="h-3 w-3" />}
                Send all ({draftCount})
              </button>
            )}
            <button
              onClick={() => fetchMessages(false)}
              disabled={loading}
              className="rounded-full border border-white/[0.12] p-2 text-white/60 hover:bg-white/[0.08] hover:text-white disabled:opacity-50"
              title="Refresh"
            >
              <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
            </button>
            <button
              onClick={onClose}
              className="rounded-full p-2 text-white/40 hover:bg-white/[0.08] hover:text-white"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
          {error && (
            <div className="flex items-start gap-2 rounded-[14px] border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
              <p>{error}</p>
              <button onClick={() => setError(null)} className="ml-auto text-rose-400/60 hover:text-rose-300">
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )}

          {loading ? (
            <div className="flex flex-col items-center justify-center gap-3 py-16 text-white/50">
              <Loader2 className="h-6 w-6 animate-spin text-[#1c8ed4]" />
              <p className="text-sm font-medium">Loading email drafts…</p>
              <p className="text-xs text-white/30">AI is generating personalized emails for your leads.</p>
            </div>
          ) : messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
              <Loader2 className="h-6 w-6 animate-spin text-[#1c8ed4]" />
              <p className="text-sm font-semibold text-white/70">Generating drafts…</p>
              <p className="text-xs text-white/30 max-w-xs">
                AI is personalizing emails for each lead. This panel will update automatically.
              </p>
            </div>
          ) : (
            messages.map((msg) => {
              const cfg = statusConfig[msg.status] ?? statusConfig.draft;
              const isExpanded = expandedId === msg.id;
              const isEditing = editingId === msg.id;
              const isSending = sendingId === msg.id;
              const isDraft = msg.status === 'draft';

              return (
                <div
                  key={msg.id}
                  className={cn(
                    'rounded-[20px] border overflow-hidden transition-all',
                    isDraft
                      ? 'border-white/[0.12] bg-white/[0.05] shadow-[0_4px_16px_rgba(0,0,0,0.2)]'
                      : 'border-white/[0.06] bg-white/[0.03]'
                  )}
                >
                  {/* Message header row */}
                  <div className="flex items-center gap-3 px-4 py-3.5">
                    {/* Avatar */}
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#1c8ed4]/20 text-[10px] font-bold text-[#60b7e8]">
                      {(msg.lead_name ?? '?').split(' ').map((n) => n[0]).slice(0, 2).join('')}
                    </div>

                    {/* Lead info */}
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="text-sm font-semibold text-white truncate">
                          {msg.lead_name ?? 'Unknown'}
                        </span>
                        {msg.lead_company && (
                          <span className="text-xs text-white/50">· {msg.lead_company}</span>
                        )}
                        <span
                          className={cn('rounded-full border px-2 py-0.5 text-[10px] font-semibold', cfg.className)}
                          title={msg.status === 'failed' && msg.error_message ? msg.error_message : undefined}
                        >
                          {cfg.label}
                        </span>
                        {msg.sequence_step != null && (
                          <span className="rounded-full bg-white/[0.08] border border-white/[0.10] px-2 py-0.5 text-[10px] font-semibold text-white/60">
                            Step {msg.sequence_step + 1}
                          </span>
                        )}
                        {msg.ai_generated && (
                          <Sparkles className="h-3 w-3 text-[#1c8ed4]" />
                        )}
                      </div>
                      <p className="mt-0.5 truncate text-xs text-white/50">{msg.subject ?? '(no subject)'}</p>
                      {msg.status === 'failed' && msg.error_message && (
                        <p className="mt-0.5 truncate text-[10px] text-red-400" title={msg.error_message}>
                          {msg.error_message}
                        </p>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1.5 shrink-0">
                      {isDraft && (
                        <button
                          onClick={() => isEditing ? cancelEdit() : startEdit(msg)}
                          className={cn(
                            'rounded-full p-1.5 text-white/40 hover:bg-white/[0.08] hover:text-white transition-colors',
                            isEditing && 'bg-white/[0.08] text-white'
                          )}
                          title="Edit email"
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </button>
                      )}
                      {isDraft ? (
                        <button
                          disabled={isSending || !!sendingId}
                          onClick={() => handleSend(msg)}
                          className="flex items-center gap-1 rounded-full bg-[#1c8ed4] px-3 py-1.5 text-[11px] font-semibold text-white hover:bg-[#1577b5] disabled:opacity-60"
                        >
                          {isSending ? <Loader2 className="h-3 w-3 animate-spin" /> : <Send className="h-3 w-3" />}
                          Send
                        </button>
                      ) : msg.status === 'sent' ? (
                        <span className="flex items-center gap-1 text-[11px] font-semibold text-emerald-400">
                          <Check className="h-3.5 w-3.5" /> Sent
                        </span>
                      ) : null}
                      <button
                        onClick={() => { setExpandedId(isExpanded ? null : msg.id); if (isEditing) cancelEdit(); }}
                        className="rounded-full p-1.5 text-white/40 hover:bg-white/[0.08] hover:text-white"
                      >
                        {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>

                  {/* Expanded email preview / edit */}
                  {isExpanded && (
                    <div className="border-t border-white/[0.08] px-4 py-4 space-y-3">
                      {/* To / From / Subject */}
                      <div className="rounded-[12px] bg-white/[0.05] border border-white/[0.06] p-3 space-y-1.5 text-xs">
                        <div className="flex gap-2">
                          <span className="w-14 shrink-0 font-semibold text-white/40">To</span>
                          <span className="text-white/70">
                            {msg.lead_email ?? 'unknown'}
                            {testEmails && testEmails.length > 0 && (
                              <span className="font-semibold text-[#1c8ed4]"> → {testEmails.join(', ')}</span>
                            )}
                          </span>
                        </div>
                        <div className="flex gap-2">
                          <span className="w-14 shrink-0 font-semibold text-white/40">From</span>
                          <span className="text-white/70">
                            {msg.from_name ? `${msg.from_name} <${msg.from_email}>` : (msg.from_email ?? '—')}
                          </span>
                        </div>
                        {isEditing && editState ? (
                          <div className="flex gap-2 items-start">
                            <span className="w-14 shrink-0 font-semibold text-white/40 pt-1.5">Subject</span>
                            <input
                              className="flex-1 rounded-lg border border-white/[0.15] bg-white/[0.08] px-3 py-1.5 text-xs text-white placeholder-white/30 focus:border-[#1c8ed4]/60 focus:outline-none"
                              value={editState.subject}
                              onChange={(e) => setEditState((s) => s ? { ...s, subject: e.target.value } : s)}
                              placeholder="Subject line"
                            />
                          </div>
                        ) : (
                          <div className="flex gap-2">
                            <span className="w-14 shrink-0 font-semibold text-white/40">Subject</span>
                            <span className="text-white font-medium">{msg.subject ?? '(no subject)'}</span>
                          </div>
                        )}
                      </div>

                      {/* Body — editable or preview */}
                      {isEditing && editState ? (
                        <div className="space-y-2">
                          <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-white/40">Edit Email Body</p>
                          <textarea
                            className="w-full rounded-[12px] border border-white/[0.15] bg-white/[0.06] px-4 py-3 text-sm text-white/85 placeholder-white/25 focus:border-[#1c8ed4]/60 focus:outline-none leading-relaxed resize-none"
                            rows={12}
                            value={editState.body_text}
                            onChange={(e) => setEditState((s) => s ? { ...s, body_text: e.target.value } : s)}
                            placeholder="Email body…"
                          />
                          <div className="flex items-center justify-end gap-2">
                            <button
                              onClick={cancelEdit}
                              className="rounded-full border border-white/[0.12] px-3.5 py-1.5 text-[11px] font-semibold text-white/60 hover:bg-white/[0.08] hover:text-white"
                            >
                              Cancel
                            </button>
                            <button
                              onClick={() => saveEdit(msg.id)}
                              disabled={editState.saving}
                              className="flex items-center gap-1.5 rounded-full bg-emerald-600 px-3.5 py-1.5 text-[11px] font-semibold text-white hover:bg-emerald-500 disabled:opacity-60"
                            >
                              {editState.saving ? (
                                <Loader2 className="h-3 w-3 animate-spin" />
                              ) : editState.saved ? (
                                <Check className="h-3 w-3" />
                              ) : null}
                              {editState.saved ? 'Saved' : 'Save changes'}
                            </button>
                          </div>
                        </div>
                      ) : msg.body_html ? (
                        <div className="rounded-[12px] border border-white/[0.08] bg-white overflow-hidden">
                          <div className="flex items-center justify-between border-b border-gray-200 bg-gray-50 px-3 py-2">
                            <span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-gray-400">Email Preview</span>
                            {isDraft && (
                              <button
                                onClick={() => startEdit(msg)}
                                className="flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1 text-[10px] font-semibold text-gray-500 hover:bg-gray-200"
                              >
                                <Pencil className="h-2.5 w-2.5" /> Edit
                              </button>
                            )}
                          </div>
                          <iframe
                            srcDoc={msg.body_html}
                            className="w-full"
                            style={{ height: '300px', border: 'none' }}
                            sandbox="allow-same-origin"
                            title="Email preview"
                          />
                        </div>
                      ) : msg.body_text ? (
                        <div className="rounded-[12px] bg-white/[0.05] border border-white/[0.06] p-4 text-sm text-white/70 whitespace-pre-wrap font-mono leading-relaxed">
                          {msg.body_text}
                        </div>
                      ) : null}

                      {/* Personalization hooks */}
                      {!isEditing && msg.personalization_hooks && msg.personalization_hooks.length > 0 && (
                        <div>
                          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-white/40">AI Personalization Hooks</p>
                          <div className="flex flex-wrap gap-1.5">
                            {msg.personalization_hooks.map((hook, i) => (
                              <span key={i} className="rounded-full bg-[#1c8ed4]/10 border border-[#1c8ed4]/20 px-2.5 py-1 text-[11px] text-[#60b7e8]">
                                {hook}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-white/[0.08] px-6 py-4">
          {testEmails && testEmails.length > 0 ? (
            <p className="text-[11px] text-white/30 text-center">
              Test mode — emails will be delivered to{' '}
              <span className="font-semibold text-white/50">{testEmails.join(', ')}</span>{' '}
              instead of the original recipients.
            </p>
          ) : (
            <p className="text-[11px] text-white/30 text-center">
              Review and edit each email before sending. Follow-up emails are sent automatically.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
