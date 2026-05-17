'use client';

import Link from 'next/link';
import { Suspense, useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react';
import { useSearchParams } from 'next/navigation';
import {
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from '@tanstack/react-table';
import {
  ArrowUpDown,
  BriefcaseBusiness,
  Building2,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Copy,
  Database,
  ExternalLink,
  FileSpreadsheet,
  Filter,
  Loader2,
  Mail,
  MoreHorizontal,
  RefreshCw,
  RotateCcw,
  Search,
  Sparkles,
  Upload,
  UserRound,
  Wand2,
  X,
  XCircle,
  Zap,
} from 'lucide-react';
import { api, apiClient, type PaginatedData } from '@/lib/api-client';
import { cn } from '@/lib/utils';

interface EnrichmentJob {
  id: string;
  lead_id: string;
  lead_name: string | null;
  job_type: string;
  status: string;
  error: string | null;
  duration_ms: number | null;
  tokens_used: number | null;
  created_at: string;
  completed_at: string | null;
}

const JOB_STATUS_CFG: Record<string, { label: string; dot: string; text: string; bg: string }> = {
  pending:    { label: 'Pending',    dot: 'bg-white/30',     text: 'text-white/50',   bg: 'bg-white/[0.06]' },
  processing: { label: 'Running',    dot: 'bg-amber-400',   text: 'text-amber-300',  bg: 'bg-amber-500/20' },
  completed:  { label: 'Completed',  dot: 'bg-emerald-500', text: 'text-emerald-300', bg: 'bg-emerald-500/20' },
  failed:     { label: 'Failed',     dot: 'bg-rose-500',    text: 'text-rose-300',   bg: 'bg-rose-500/20' },
};

const JOB_TYPE_LABEL: Record<string, string> = {
  web_research: 'Web Research',
  company:      'Company Intel',
  scoring:      'AI Scoring',
  contact:      'Contact Data',
};

function EnrichmentStatusDrawer({ onClose }: { onClose: () => void }) {
  const [jobs, setJobs] = useState<EnrichmentJob[]>([]);
  const [loading, setLoading] = useState(true);

  async function fetchJobs(quiet = false) {
    if (!quiet) setLoading(true);
    try {
      const data = await api<EnrichmentJob[]>({ method: 'GET', url: '/enrichment/jobs?limit=100' });
      setJobs(Array.isArray(data) ? data : []);
    } catch { /* silent */ } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchJobs();
    const interval = setInterval(() => fetchJobs(true), 4000);
    return () => clearInterval(interval);
  }, []);

  const byLead = useMemo(() => {
    const map = new Map<string, { lead_name: string | null; jobs: EnrichmentJob[] }>();
    for (const j of jobs) {
      if (!map.has(j.lead_id)) map.set(j.lead_id, { lead_name: j.lead_name, jobs: [] });
      map.get(j.lead_id)!.jobs.push(j);
    }
    // Only show leads that have at least one active (pending/processing) job
    return Array.from(map.values()).filter(({ jobs: leadJobs }) =>
      leadJobs.some(j => j.status === 'pending' || j.status === 'processing')
    );
  }, [jobs]);

  const running = jobs.filter(j => j.status === 'pending' || j.status === 'processing').length;

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="flex h-full w-full max-w-md flex-col" style={{ background: '#0d1525', borderLeft: '1px solid rgba(255,255,255,0.07)' }}>
        {/* Header */}
        <div className="flex items-center justify-between border-b border-white/[0.07] px-5 py-4">
          <div className="flex items-center gap-2.5">
            <Zap className="h-4 w-4 text-cyan-400" />
            <h2 className="text-base font-bold tracking-[-0.03em] text-white">Enrichment Status</h2>
            {running > 0 && (
              <span className="flex items-center gap-1 rounded-full bg-amber-500/20 px-2.5 py-0.5 text-[10px] font-semibold text-amber-300">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-400" />
                {running} running
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => fetchJobs()} disabled={loading} className="rounded-full p-1.5 text-white/40 hover:bg-white/[0.07] hover:text-white disabled:opacity-40">
              <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
            </button>
            <button onClick={onClose} className="rounded-full p-1.5 text-white/40 hover:bg-white/[0.07] hover:text-white">
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
          {loading ? (
            <div className="flex items-center justify-center gap-2 py-16 text-white/30">
              <Loader2 className="h-5 w-5 animate-spin" />
              <span className="text-sm">Loading jobs…</span>
            </div>
          ) : byLead.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 py-16 text-center">
              <Zap className="h-8 w-8 text-white/20" />
              <p className="text-sm font-semibold text-white/60">No active enrichment</p>
              <p className="text-xs text-white/30">All jobs are complete. Select leads and click Re-enrich to start a new run.</p>
            </div>
          ) : (
            byLead.map(({ lead_name, jobs: leadJobs }) => {
              const allDone = leadJobs.every(j => j.status === 'completed' || j.status === 'failed');
              const anyFailed = leadJobs.some(j => j.status === 'failed');
              const anyRunning = leadJobs.some(j => j.status === 'pending' || j.status === 'processing');
              const overallDot = anyFailed ? 'bg-rose-500' : anyRunning ? 'bg-amber-400 animate-pulse' : 'bg-emerald-500';
              return (
                <div key={leadJobs[0].lead_id} className="rounded-[18px] border border-white/[0.08] bg-white/[0.04] p-4">
                  <div className="mb-3 flex items-center gap-2">
                    <span className={cn('h-2 w-2 rounded-full', overallDot)} />
                    <span className="text-sm font-semibold text-white">{lead_name ?? 'Unknown lead'}</span>
                  </div>
                  <div className="space-y-2">
                    {leadJobs.map((job) => {
                      const cfg = JOB_STATUS_CFG[job.status] ?? JOB_STATUS_CFG.pending;
                      return (
                        <div key={job.id} className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2 min-w-0">
                            <span className={cn('flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold', cfg.bg, cfg.text)}>
                              <span className={cn('h-1.5 w-1.5 rounded-full', cfg.dot, job.status==='processing' && 'animate-pulse')} />
                              {cfg.label}
                            </span>
                            <span className="text-xs text-white/50">{JOB_TYPE_LABEL[job.job_type] ?? job.job_type}</span>
                          </div>
                          <div className="flex shrink-0 items-center gap-2 text-[10px] text-white/25">
                            {job.duration_ms != null && (
                              <span>{(job.duration_ms / 1000).toFixed(1)}s</span>
                            )}
                            {job.tokens_used != null && (
                              <span>{job.tokens_used} tok</span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  {leadJobs.some(j => j.error) && (
                    <p className="mt-2 truncate text-[10px] text-rose-400" title={leadJobs.find(j => j.error)?.error ?? ''}>
                      {leadJobs.find(j => j.error)?.error}
                    </p>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Footer summary */}
        {byLead.length > 0 && (
          <div className="border-t border-white/[0.07] px-5 py-3 flex items-center justify-between text-xs text-white/30">
            <span>{byLead.length} lead{byLead.length !== 1 ? 's' : ''} active</span>
            <span>{jobs.filter(j => j.status === 'pending' || j.status === 'processing').length} jobs in progress</span>
            <span>{jobs.filter(j => j.status === 'failed').length} failed</span>
          </div>
        )}
      </div>
    </div>
  );
}

interface LeadCompany {
  name: string;
  industry?: string | null;
  location?: string | null;
}

interface LeadContact {
  first_name: string;
  last_name: string;
  email: string;
  title?: string | null;
  department?: string | null;
}

interface ApiLead {
  id: string;
  status: string;
  source: string | null;
  enrichment_status: string;
  created_at: string;
  updated_at: string;
  company?: LeadCompany | null;
  contact?: LeadContact | null;
  score_tier?: string | null;
  score_value?: number | null;
  active_campaign_name?: string | null;
}

interface LeadRow {
  id: string;
  name: string;
  email: string;
  company: string;
  title: string;
  status: string;
  enrichmentStatus: string;
  source: string;
  updatedAt: string;
  scoreTier: string | null;
  scoreValue: number | null;
  activeCampaignName: string | null;
}

const tierConfig: Record<string, { label: string; className: string }> = {
  hot:  { label: 'Hot',  className: 'bg-rose-500/20 text-rose-300' },
  warm: { label: 'Warm', className: 'bg-amber-500/20 text-amber-300' },
  cold: { label: 'Cold', className: 'bg-white/10 text-white/40' },
};

const statusConfig: Record<string, { label: string; className: string }> = {
  new: { label: 'New', className: 'bg-white/[0.08] text-white/60' },
  enriching: { label: 'Enriching', className: 'bg-amber-500/20 text-amber-300' },
  enriched: { label: 'Enriched', className: 'bg-cyan-500/20 text-cyan-300' },
  scored: { label: 'Scored', className: 'bg-indigo-500/20 text-indigo-300' },
  campaign_active: { label: 'In Campaign', className: 'bg-violet-500/20 text-violet-300' },
  replied: { label: 'Replied', className: 'bg-orange-500/20 text-orange-300' },
  converted: { label: 'Converted', className: 'bg-emerald-500/20 text-emerald-300' },
};

const enrichmentConfig: Record<string, { label: string; className: string }> = {
  pending: { label: 'Pending', className: 'bg-white/[0.07] text-white/40' },
  processing: { label: 'Processing', className: 'bg-amber-500/20 text-amber-300' },
  completed: { label: 'Completed', className: 'bg-emerald-500/20 text-emerald-300' },
  enriched: { label: 'Enriched', className: 'bg-cyan-500/20 text-cyan-300' },
  failed: { label: 'Failed', className: 'bg-rose-500/20 text-rose-300' },
};

function formatRelativeTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return 'Unknown';
  }

  const diffMs = Date.now() - date.getTime();
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffHours / 24);

  if (diffHours < 1) return 'Just now';
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;

  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function RowActionsMenu({ row, onEnrich }: { row: LeadRow; onEnrich: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}
        className="rounded-full p-2 text-white/30 transition-colors hover:bg-white/[0.07] hover:text-white"
      >
        <MoreHorizontal className="h-4 w-4" />
      </button>
      {open && (
        <div className="absolute right-0 top-full z-50 mt-1 w-44 origin-top-right overflow-hidden rounded-2xl border border-white/[0.1] py-1 shadow-xl" style={{ background: '#0d1525' }}>
          <Link
            href={`/leads/${row.id}`}
            onClick={() => setOpen(false)}
            className="flex w-full items-center gap-2 px-3.5 py-2.5 text-sm text-white/70 hover:bg-white/[0.06]"
          >
            <ExternalLink className="h-3.5 w-3.5 text-white/30" />
            View details
          </Link>
          <button
            onClick={() => { setOpen(false); onEnrich(row.id); }}
            className="flex w-full items-center gap-2 px-3.5 py-2.5 text-sm text-white/70 hover:bg-white/[0.06]"
          >
            <RotateCcw className="h-3.5 w-3.5 text-white/30" />
            Re-enrich
          </button>
          <button
            onClick={() => { navigator.clipboard.writeText(row.email); setOpen(false); }}
            className="flex w-full items-center gap-2 px-3.5 py-2.5 text-sm text-white/70 hover:bg-white/[0.06]"
          >
            <Copy className="h-3.5 w-3.5 text-white/30" />
            Copy email
          </button>
        </div>
      )}
    </div>
  );
}

function makeColumns(onEnrich: (id: string) => void): ColumnDef<LeadRow>[] {
  return [
  {
    id: 'select',
    header: ({ table }) => (
      <input
        type="checkbox"
        className="h-3.5 w-3.5 cursor-pointer rounded border-white/20 accent-indigo-500"
        checked={table.getIsAllPageRowsSelected()}
        ref={(el) => { if (el) el.indeterminate = table.getIsSomePageRowsSelected(); }}
        onChange={table.getToggleAllPageRowsSelectedHandler()}
        aria-label="Select all"
      />
    ),
    cell: ({ row }) => (
      <input
        type="checkbox"
        className="h-3.5 w-3.5 cursor-pointer rounded border-white/20 accent-indigo-500"
        checked={row.getIsSelected()}
        onChange={row.getToggleSelectedHandler()}
        aria-label="Select row"
        onClick={(e) => e.stopPropagation()}
      />
    ),
  },
  {
    accessorKey: 'name',
    header: ({ column }) => (
      <button className="flex items-center gap-1 text-xs font-semibold text-slate-500" onClick={() => column.toggleSorting()}>
        Contact <ArrowUpDown className="h-3 w-3" />
      </button>
    ),
    cell: ({ row }) => (
      <div className="min-w-[220px]">
        <div className="flex items-center gap-2">
          <Link href={`/leads/${row.original.id}`} className="text-sm font-semibold text-white transition-colors hover:text-indigo-400">
            {row.original.name}
          </Link>
          {row.original.scoreTier ? (
            <span className={cn('inline-flex rounded-full px-2 py-0.5 text-[10px] font-bold', tierConfig[row.original.scoreTier]?.className ?? 'bg-white/10 text-white/40')}>
              {tierConfig[row.original.scoreTier]?.label ?? row.original.scoreTier}
              {row.original.scoreValue != null ? ` · ${row.original.scoreValue}` : ''}
            </span>
          ) : null}
          {row.original.activeCampaignName ? (
            <span className="inline-flex rounded-full border border-violet-500/30 bg-violet-500/10 px-2 py-0.5 text-[10px] font-semibold text-violet-300">
              {row.original.activeCampaignName}
            </span>
          ) : null}
        </div>
        <div className="mt-1 flex items-center gap-1.5 text-xs text-white/40">
          <Mail className="h-3.5 w-3.5" />
          {row.original.email}
        </div>
      </div>
    ),
  },
  {
    accessorKey: 'company',
    header: ({ column }) => (
      <button className="flex items-center gap-1 text-xs font-semibold text-white/40" onClick={() => column.toggleSorting()}>
        Company <ArrowUpDown className="h-3 w-3" />
      </button>
    ),
    cell: ({ row }) => (
      <div className="min-w-[210px]">
        <p className="text-sm font-semibold text-white">{row.original.company}</p>
        <div className="mt-1 flex items-center gap-1.5 text-xs text-white/40">
          <BriefcaseBusiness className="h-3.5 w-3.5" />
          {row.original.title}
        </div>
      </div>
    ),
  },
  {
    accessorKey: 'status',
    header: () => <span className="text-xs font-semibold text-white/40">Status</span>,
    cell: ({ row }) => {
      const config = statusConfig[row.original.status] ?? statusConfig.new;
      return <span className={cn('inline-flex rounded-full px-2.5 py-1 text-xs font-semibold', config.className)}>{config.label}</span>;
    },
  },
  {
    accessorKey: 'enrichmentStatus',
    header: () => <span className="text-xs font-semibold text-white/40">Enrichment</span>,
    cell: ({ row }) => {
      const config = enrichmentConfig[row.original.enrichmentStatus] ?? enrichmentConfig.pending;
      return <span className={cn('inline-flex rounded-full px-2.5 py-1 text-xs font-semibold', config.className)}>{config.label}</span>;
    },
  },
  {
    accessorKey: 'source',
    header: () => <span className="text-xs font-semibold text-white/40">Source</span>,
    cell: ({ row }) => <span className="rounded-full bg-white/[0.07] px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-white/50">{row.original.source}</span>,
  },
  {
    accessorKey: 'updatedAt',
    header: ({ column }) => (
      <button className="flex items-center gap-1 text-xs font-semibold text-white/40" onClick={() => column.toggleSorting()}>
        Updated <ArrowUpDown className="h-3 w-3" />
      </button>
    ),
    cell: ({ row }) => <span className="text-xs text-white/30">{row.original.updatedAt}</span>,
  },
  {
    id: 'actions',
    cell: ({ row }) => <RowActionsMenu row={row.original} onEnrich={onEnrich} />,
  },
  ];
}

function LeadsPageInner() {
  const searchParams = useSearchParams();
  const [sorting, setSorting] = useState<SortingState>([{ id: 'updatedAt', desc: true }]);
  const [globalFilter, setGlobalFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [enrichmentFilter, setEnrichmentFilter] = useState('');
  const [tierFilter, setTierFilter] = useState('');
  const [activeCard, setActiveCard] = useState<string | null>(null);
  const [rowSelection, setRowSelection] = useState<Record<string, boolean>>({});
  const [importing, setImporting] = useState(false);
  const [enriching, setEnriching] = useState(false);
  const [enrichResult, setEnrichResult] = useState<{ count: number } | null>(null);
  const [enrichError, setEnrichError] = useState<string | null>(null);
  const [showEnrichStatus, setShowEnrichStatus] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [leads, setLeads] = useState<ApiLead[]>([]);
  const [totalLeads, setTotalLeads] = useState(0);
  const [importResult, setImportResult] = useState<{ success: number; errors: number; fileName: string } | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function fetchLeads(showLoader = false) {
    if (showLoader) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    try {
      const data = await api<PaginatedData<ApiLead>>({
        url: '/leads',
        method: 'GET',
        params: { page: 1, page_size: 1000, sort_by: 'updated_at', sort_dir: 'desc' },
      });
      setLeads(data.items);
      setTotalLeads(data.total);
      setLoadError(null);
    } catch (error: unknown) {
      const message = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setLoadError(message || 'Unable to load leads right now.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    fetchLeads();
  }, []);

  useEffect(() => {
    setGlobalFilter(searchParams.get('q') ?? '');
  }, [searchParams]);

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!fileInputRef.current) return;
    fileInputRef.current.value = '';
    if (!file) return;

    setImporting(true);
    setImportError(null);
    setImportResult(null);

    try {
      const formData = new FormData();
      formData.append('file', file);
      const response = await apiClient.post('/leads/import', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const data = response.data.data;
      setImportResult({
        success: data.success_rows ?? 0,
        errors: data.error_rows ?? 0,
        fileName: data.file_name ?? file.name,
      });
      await fetchLeads(true);
    } catch (error: unknown) {
      const message = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setImportError(message || 'Import failed. Check the file columns and try again.');
    } finally {
      setImporting(false);
    }
  }

  const STATUS_PRIORITY: Record<string, number> = {
    scored: 0,
    enriched: 1,
    campaign_active: 2,
    replied: 3,
    converted: 4,
    enriching: 5,
    new: 6,
    disqualified: 7,
  };

  const rows = useMemo<LeadRow[]>(() => {
    return leads
      .map((lead) => {
        const firstName = lead.contact?.first_name?.trim() ?? '';
        const lastName = lead.contact?.last_name?.trim() ?? '';
        const fullName = `${firstName} ${lastName}`.trim() || 'Unknown contact';

        return {
          id: lead.id,
          name: fullName,
          email: lead.contact?.email ?? 'No email',
          company: lead.company?.name ?? 'Unknown company',
          title: lead.contact?.title || lead.contact?.department || 'Role pending enrichment',
          status: lead.status,
          enrichmentStatus: lead.enrichment_status,
          source: (lead.source || 'manual').replaceAll('_', ' '),
          updatedAt: formatRelativeTime(lead.updated_at),
          scoreTier: lead.score_tier ?? null,
          scoreValue: lead.score_value ?? null,
          activeCampaignName: lead.active_campaign_name ?? null,
        };
      })
      .sort((a, b) => {
        const pa = STATUS_PRIORITY[a.status] ?? 99;
        const pb = STATUS_PRIORITY[b.status] ?? 99;
        if (pa !== pb) return pa - pb;
        // within same status: higher score first, then alpha by name
        if ((b.scoreValue ?? -1) !== (a.scoreValue ?? -1)) return (b.scoreValue ?? -1) - (a.scoreValue ?? -1);
        return a.name.localeCompare(b.name);
      });
  }, [leads]);

  const filteredRows = useMemo(() => {
    const search = globalFilter.trim().toLowerCase();
    return rows.filter((row) => {
      const matchesStatus = !statusFilter || row.status === statusFilter;
      const matchesEnrichment = !enrichmentFilter || row.enrichmentStatus === enrichmentFilter;
      const matchesTier = !tierFilter || row.scoreTier === tierFilter;
      const matchesSearch =
        !search ||
        row.name.toLowerCase().includes(search) ||
        row.email.toLowerCase().includes(search) ||
        row.company.toLowerCase().includes(search);
      return matchesStatus && matchesEnrichment && matchesTier && matchesSearch;
    });
  }, [globalFilter, rows, statusFilter, enrichmentFilter, tierFilter]);

  async function handleSingleEnrich(leadId: string) {
    setEnriching(true);
    setEnrichError(null);
    setEnrichResult(null);
    try {
      await api({
        method: 'POST',
        url: '/enrichment/enrich',
        data: { lead_ids: [leadId], enrichment_types: ['web_research', 'company', 'scoring'] },
      });
      setEnrichResult({ count: 1 });
      setShowEnrichStatus(true);
      await fetchLeads(true);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setEnrichError(detail ?? 'Failed to trigger enrichment. Please try again.');
    } finally {
      setEnriching(false);
    }
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const columns = useMemo(() => makeColumns(handleSingleEnrich), []);

  const table = useReactTable({
    data: filteredRows,
    columns,
    state: { sorting, rowSelection },
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    enableRowSelection: true,
    getRowId: (row) => row.id,
    initialState: { pagination: { pageSize: 12 } },
  });

  async function handleBulkEnrich() {
    const selectedIds = Object.keys(rowSelection);
    if (selectedIds.length === 0) return;
    setEnriching(true);
    setEnrichError(null);
    setEnrichResult(null);
    try {
      await api({
        method: 'POST',
        url: '/enrichment/enrich',
        data: { lead_ids: selectedIds, enrichment_types: ['web_research', 'company', 'scoring'] },
      });
      setEnrichResult({ count: selectedIds.length });
      setRowSelection({});
      setShowEnrichStatus(true);
      await fetchLeads(true);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setEnrichError(detail ?? 'Failed to trigger enrichment. Please try again.');
    } finally {
      setEnriching(false);
    }
  }

  async function handleEnrichAll() {
    setEnriching(true);
    setEnrichError(null);
    setEnrichResult(null);
    try {
      const result = await api<{ lead_count: number }>({ method: 'POST', url: '/enrichment/enrich-all' });
      setEnrichResult({ count: result.lead_count });
      setShowEnrichStatus(true);
      await fetchLeads(true);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setEnrichError(detail ?? 'Failed to trigger enrichment. Please try again.');
    } finally {
      setEnriching(false);
    }
  }

  const selectedCount = Object.keys(rowSelection).length;
  const enrichedCount = leads.filter((lead) => ['completed', 'enriched'].includes(lead.enrichment_status)).length;
  const readyCount = leads.filter((lead) => ['scored', 'campaign_active', 'replied', 'converted'].includes(lead.status)).length;
  const newCount = leads.filter((lead) => lead.status === 'new').length;
  const hotCount = leads.filter((lead) => lead.score_tier === 'hot').length;
  const warmCount = leads.filter((lead) => lead.score_tier === 'warm').length;
  const coldCount = leads.filter((lead) => lead.score_tier === 'cold').length;

  function handleCardClick(cardKey: string) {
    if (activeCard === cardKey) {
      setActiveCard(null);
      setStatusFilter('');
      setEnrichmentFilter('');
      setTierFilter('');
      return;
    }
    setActiveCard(cardKey);
    setStatusFilter('');
    setEnrichmentFilter('');
    setTierFilter('');
    if (cardKey === 'new') {
      setStatusFilter('new');
    } else if (cardKey === 'enriched') {
      setEnrichmentFilter('enriched');
    } else if (cardKey === 'ready') {
      setStatusFilter('scored');
    } else if (cardKey === 'hot') {
      setTierFilter('hot');
    } else if (cardKey === 'warm') {
      setTierFilter('warm');
    } else if (cardKey === 'cold') {
      setTierFilter('cold');
    }
  }

  return (
    <div className="space-y-5">
      <input ref={fileInputRef} type="file" accept=".csv,.xlsx" className="hidden" onChange={handleFileChange} />
      {showEnrichStatus && <EnrichmentStatusDrawer onClose={() => setShowEnrichStatus(false)} />}

      <section
        className="relative overflow-hidden rounded-2xl p-6 lg:p-7"
        style={{
          background: 'linear-gradient(135deg, #0d2540 0%, #09131f 55%, #1c4d73 100%)',
          boxShadow: '0 8px 32px rgba(13,37,64,0.18)',
        }}
      >
        <div className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full bg-white/3" />
        <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <p className="text-[10px] font-bold uppercase tracking-widest mb-2" style={{ color: 'rgba(255,255,255,0.35)' }}>Lead operations</p>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <h1 className="text-[1.65rem] font-extrabold tracking-tight text-white leading-tight sm:text-[2rem]">Turn raw sheets into enrichment-ready pipeline.</h1>
              <span className="rounded-full bg-indigo-600 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-white">Live data</span>
            </div>
            <p className="mt-3 max-w-2xl text-sm leading-6 sm:text-base" style={{ color: 'rgba(255,255,255,0.50)' }}>
              Import your customer sheet, review operational status instantly, and send only the accounts that are ready for scraping, scoring, and campaign routing.
            </p>
          </div>

          <div className="flex flex-wrap gap-2.5">
            <button
              onClick={() => setShowEnrichStatus(true)}
              className="inline-flex items-center gap-2 rounded-full border border-white/[0.12] bg-white/[0.06] px-4 py-2.5 text-sm font-semibold text-white/70 transition-colors hover:bg-white/[0.1]"
            >
              <Zap className="h-4 w-4 text-cyan-400" />
              Enrichment Status
            </button>
            <button
              onClick={() => fetchLeads(true)}
              disabled={refreshing || loading}
              className="inline-flex items-center gap-2 rounded-full border border-white/[0.12] bg-white/[0.06] px-4 py-2.5 text-sm font-semibold text-white/70 transition-colors hover:bg-white/[0.1] disabled:opacity-60"
            >
              <RefreshCw className={cn('h-4 w-4', refreshing && 'animate-spin')} />
              Refresh
            </button>
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={importing}
              className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-indigo-600 to-violet-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-900/40 transition-transform hover:-translate-y-0.5 disabled:opacity-60"
            >
              {importing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
              {importing ? 'Importing...' : 'Import CSV / XLSX'}
            </button>
          </div>
        </div>

        {/* ── Pipeline progress strip ─────────────────────────────── */}
        <div className="mt-6 rounded-2xl border border-white/[0.08] bg-white/[0.04] px-5 py-4">
          <div className="flex flex-wrap items-center gap-0">
            {[
              { key: 'all',      label: 'Total',     value: leads.length,   color: 'text-white',         dot: 'bg-white/40'        },
              { key: 'new',      label: 'New',        value: newCount,       color: 'text-amber-300',     dot: 'bg-amber-400'       },
              { key: 'enriched', label: 'Enriched',   value: enrichedCount,  color: 'text-emerald-300',   dot: 'bg-emerald-400'     },
              { key: 'ready',    label: 'Scored',     value: readyCount,     color: 'text-violet-300',    dot: 'bg-violet-400'      },
            ].map((item, i) => {
              const isActive = activeCard === item.key || (activeCard === null && item.key === 'all');
              return (
                <div key={item.key} className="flex items-center">
                  {i > 0 && (
                    <div className="mx-3 flex items-center text-white/15">
                      <div className="h-px w-6 bg-white/10" />
                      <ChevronRight className="h-3.5 w-3.5 -ml-1" />
                    </div>
                  )}
                  <button
                    onClick={() => handleCardClick(item.key)}
                    className={cn(
                      'rounded-xl px-3.5 py-2 text-left transition-all hover:bg-white/[0.06]',
                      isActive && 'bg-white/[0.08]',
                    )}
                  >
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <span className={cn('h-1.5 w-1.5 rounded-full', item.dot)} />
                      <span className="text-[11px] font-medium text-white/40">{item.label}</span>
                      {isActive && <span className="text-[10px] text-white/25">↓</span>}
                    </div>
                    <span className={cn('text-2xl font-extrabold tracking-tight tabular-nums', item.color)}>
                      {item.value.toLocaleString()}
                    </span>
                  </button>
                </div>
              );
            })}

            {/* Progress bar */}
            <div className="ml-auto hidden xl:block w-36">
              <p className="text-[10px] text-white/25 mb-1.5 text-right">Pipeline fill</p>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.08]">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-violet-500 transition-all"
                  style={{ width: totalLeads > 0 ? `${Math.round((readyCount / totalLeads) * 100)}%` : '0%' }}
                />
              </div>
              <p className="text-[10px] text-white/25 mt-1 text-right">
                {totalLeads > 0 ? Math.round((readyCount / totalLeads) * 100) : 0}% campaign-ready
              </p>
            </div>
          </div>
        </div>

        <div className="mt-3 grid gap-3 md:grid-cols-3">
          {[
            { key: 'hot',  label: 'Hot leads',  value: hotCount,  bg: 'bg-rose-500/25',  border: 'border-rose-500/40',  activeBorder: 'border-rose-400/80',  dot: 'bg-rose-400',  labelCls: 'text-rose-200',  valueCls: 'text-rose-50',  subCls: 'text-rose-300/60'  },
            { key: 'warm', label: 'Warm leads', value: warmCount, bg: 'bg-amber-500/25', border: 'border-amber-500/40', activeBorder: 'border-amber-400/80', dot: 'bg-amber-400', labelCls: 'text-amber-200', valueCls: 'text-amber-50', subCls: 'text-amber-300/60' },
            { key: 'cold', label: 'Cold leads', value: coldCount, bg: 'bg-sky-500/25',   border: 'border-sky-500/40',   activeBorder: 'border-sky-400/80',   dot: 'bg-sky-400',   labelCls: 'text-sky-200',   valueCls: 'text-sky-50',   subCls: 'text-sky-300/60'   },
          ].map((item) => {
            const isActive = activeCard === item.key;
            return (
              <button
                key={item.key}
                onClick={() => handleCardClick(item.key)}
                className={cn(
                  'rounded-[26px] border p-4 text-left transition-all hover:-translate-y-0.5',
                  item.bg,
                  isActive ? `${item.activeBorder} shadow-lg` : item.border,
                )}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className={cn('h-2 w-2 rounded-full', item.dot)} />
                    <p className={cn('text-sm font-semibold', item.labelCls)}>{item.label}</p>
                  </div>
                  {isActive && <p className={cn('text-[10px] font-semibold', item.labelCls)}>Filtered ↓</p>}
                </div>
                <p className={cn('mt-3 text-[1.9rem] font-extrabold tracking-[-0.04em]', item.valueCls)}>{item.value.toLocaleString()}</p>
                <p className={cn('mt-0.5 text-xs font-medium', item.subCls)}>
                  {totalLeads > 0 ? `${Math.round((item.value / totalLeads) * 100)}% of pipeline` : '—'}
                </p>
              </button>
            );
          })}
        </div>

        <p className="mt-4 text-[11px] text-white/25 leading-relaxed">
          <FileSpreadsheet className="inline h-3 w-3 mr-1 -mt-px" />
          CSV / XLSX accepted — minimum columns: <span className="text-white/40">Name · Customer Name · Customer Email</span>. Optional: Named Acct · Success Experience · Country Region. Select contacts and click <span className="text-white/40">Enrich selected</span> to start the pipeline.
        </p>
      </section>

      {importResult ? (
        <div className="glass-card flex items-center gap-3 rounded-[24px] border-emerald-500/30 px-4 py-3 text-sm">
          <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
          <p className="text-white/70">
            Imported <span className="font-semibold text-white">{importResult.success}</span> rows from <span className="font-semibold text-white">{importResult.fileName}</span>
            {importResult.errors > 0 ? <span className="text-orange-400"> with {importResult.errors} skipped.</span> : <span className="text-emerald-400"> with no errors.</span>}
          </p>
          <button onClick={() => setImportResult(null)} className="ml-auto text-white/30 transition-colors hover:text-white">Dismiss</button>
        </div>
      ) : null}

      {importError ? (
        <div className="glass-card flex items-center gap-3 rounded-[24px] border-rose-500/30 px-4 py-3 text-sm">
          <XCircle className="h-4 w-4 shrink-0 text-rose-400" />
          <p className="text-rose-400">{importError}</p>
          <button onClick={() => setImportError(null)} className="ml-auto text-rose-400/50 transition-colors hover:text-rose-300">Dismiss</button>
        </div>
      ) : null}

      {enrichResult ? (
        <div className="glass-card flex items-center gap-3 rounded-[24px] border-emerald-500/30 px-4 py-3 text-sm">
          <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
          <p className="text-white/70">Re-enrichment triggered for <span className="font-semibold text-white">{enrichResult.count}</span> lead{enrichResult.count !== 1 ? 's' : ''}. This may take a few minutes.</p>
          <button onClick={() => setEnrichResult(null)} className="ml-auto text-white/30 transition-colors hover:text-white">Dismiss</button>
        </div>
      ) : null}

      {enrichError ? (
        <div className="glass-card flex items-center gap-3 rounded-[24px] border-rose-500/30 px-4 py-3 text-sm">
          <XCircle className="h-4 w-4 shrink-0 text-rose-400" />
          <p className="text-rose-400">{enrichError}</p>
          <button onClick={() => setEnrichError(null)} className="ml-auto text-rose-400/50 transition-colors hover:text-rose-300">Dismiss</button>
        </div>
      ) : null}

      <section className="glass-card overflow-hidden rounded-[30px]">
        <div className="border-b border-white/[0.07] px-4 py-4 sm:px-5">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
            <div>
              <h2 className="text-lg font-bold tracking-[-0.03em] text-white">Lead roster</h2>
              <p className="mt-1 text-sm text-white/40">Review imported accounts, track enrichment state, and route the right leads downstream.</p>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <div className="relative min-w-[260px]">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-white/30" />
                <input
                  value={globalFilter}
                  onChange={(event) => setGlobalFilter(event.target.value)}
                  placeholder="Search contact, company, or email"
                  className="w-full rounded-full border border-white/[0.1] bg-white/[0.05] px-10 py-2.5 text-sm text-white placeholder:text-white/25 focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                />
              </div>

              <div className="flex items-center gap-2">
                <div className="inline-flex items-center gap-2 rounded-full border border-white/[0.1] bg-white/[0.05] px-3 py-2.5 text-sm text-white/60">
                  <Filter className="h-4 w-4 text-white/30" />
                  <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} className="bg-transparent pr-2 text-sm text-white/60">
                    <option value="">All statuses</option>
                    {Object.entries(statusConfig).map(([key, value]) => (
                      <option key={key} value={key}>{value.label}</option>
                    ))}
                  </select>
                </div>
                <div className="flex items-center gap-2">
                  {selectedCount > 0 ? (
                    <>
                      <span className="rounded-full bg-indigo-500/20 px-3 py-2 text-sm font-semibold text-indigo-300">{selectedCount} selected</span>
                      <button
                        onClick={handleBulkEnrich}
                        disabled={enriching}
                        className="inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-indigo-600 to-violet-600 px-3.5 py-2 text-sm font-semibold text-white transition-colors hover:opacity-90 disabled:opacity-60"
                      >
                        {enriching ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
                        {enriching ? 'Triggering…' : 'Enrich selected'}
                      </button>
                      <button
                        onClick={() => setRowSelection({})}
                        className="rounded-full border border-white/[0.1] px-3 py-2 text-sm font-semibold text-white/50 hover:bg-white/[0.05]"
                      >
                        Clear
                      </button>
                    </>
                  ) : null}
                  <button
                    onClick={handleEnrichAll}
                    disabled={enriching || totalLeads === 0}
                    className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-3.5 py-2 text-sm font-semibold text-amber-300 transition-colors hover:bg-amber-500/20 disabled:opacity-50"
                  >
                    {enriching ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Zap className="h-3.5 w-3.5" />}
                    {enriching ? 'Triggering…' : `Enrich all (${totalLeads.toLocaleString()})`}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {loadError ? (
          <div className="px-5 py-10 text-center">
            <p className="text-base font-semibold text-white">Could not load leads</p>
            <p className="mt-1 text-sm text-white/40">{loadError}</p>
            <button onClick={() => fetchLeads(true)} className="mt-4 rounded-full bg-gradient-to-r from-indigo-600 to-violet-600 px-4 py-2 text-sm font-semibold text-white">Try again</button>
          </div>
        ) : loading ? (
          <div className="flex items-center justify-center gap-3 px-5 py-16 text-white/40">
            <Loader2 className="h-5 w-5 animate-spin" />
            Loading lead roster...
          </div>
        ) : filteredRows.length === 0 ? (
          <div className="px-5 py-14 text-center">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-3xl bg-white/[0.07] text-white/40">
              <Building2 className="h-6 w-6" />
            </div>
            <p className="mt-4 text-lg font-bold tracking-[-0.03em] text-white">No leads match the current view</p>
            <p className="mt-2 text-sm text-white/40">Adjust the search or import your first sheet to populate this workspace.</p>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto px-2 pb-2 pt-2 sm:px-3">
              <table className="w-full min-w-[920px] text-left">
                <thead>
                  <tr>
                    {table.getFlatHeaders().map((header) => (
                      <th key={header.id} className="px-3 py-3 text-left">
                        {flexRender(header.column.columnDef.header, header.getContext())}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {table.getRowModel().rows.map((row) => (
                    <tr key={row.id} className="border-t border-white/[0.05] transition-colors hover:bg-white/[0.03]">
                      {row.getVisibleCells().map((cell) => (
                        <td key={cell.id} className="px-3 py-4 align-middle">
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex flex-col gap-3 border-t border-white/[0.06] px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
              <p className="text-sm text-white/40">
                Showing {table.getState().pagination.pageIndex * table.getState().pagination.pageSize + 1} to {Math.min((table.getState().pagination.pageIndex + 1) * table.getState().pagination.pageSize, filteredRows.length)} of {filteredRows.length} leads
              </p>
              <div className="flex items-center gap-2">
                <button onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()} className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/[0.1] text-white/50 disabled:opacity-40">
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <div className="rounded-full bg-white/[0.07] px-3 py-2 text-sm font-semibold text-white/60">
                  Page {table.getState().pagination.pageIndex + 1} of {Math.max(table.getPageCount(), 1)}
                </div>
                <button onClick={() => table.nextPage()} disabled={!table.getCanNextPage()} className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/[0.1] text-white/50 disabled:opacity-40">
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

export default function LeadsPage() {
  return (
    <Suspense fallback={
      <div className="flex items-center justify-center py-20">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-[#1d7ea9] border-t-transparent" />
      </div>
    }>
      <LeadsPageInner />
    </Suspense>
  );
}