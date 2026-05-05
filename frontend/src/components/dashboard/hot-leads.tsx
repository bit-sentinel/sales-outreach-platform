'use client';

import { useEffect, useState } from 'react';
import { ExternalLink, ArrowRight, Flame } from 'lucide-react';
import Link from 'next/link';
import { api } from '@/lib/api-client';

interface HotLead {
  id: string;
  name: string;
  title: string;
  company: string;
  score: number;
  tier: string;
  status: string;
}

function ScoreRing({ score }: { score: number }) {
  const r = 14;
  const circ = 2 * Math.PI * r;
  const fill = (score / 100) * circ;
    const color = score >= 85 ? '#f97316' : score >= 75 ? '#f59e0b' : '#6366f1';
  return (
    <svg width="36" height="36" viewBox="0 0 36 36" className="flex-shrink-0">
      <circle cx="18" cy="18" r={r} fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth="3" />
      <circle
        cx="18" cy="18" r={r}
        fill="none"
        stroke={color}
        strokeWidth="3"
        strokeDasharray={`${fill.toFixed(1)} ${circ.toFixed(1)}`}
        strokeLinecap="round"
        transform="rotate(-90 18 18)"
      />
      <text x="18" y="22" textAnchor="middle" fontSize="9" fontWeight="800" fill={color}>{score}</text>
    </svg>
  );
}

const tierColors: Record<string, string> = {
  hot:  'bg-orange-500/20 text-orange-300',
  warm: 'bg-amber-500/20 text-amber-300',
  cold: 'bg-white/10 text-white/40',
};

export function HotLeads() {
  const [leads, setLeads] = useState<HotLead[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<HotLead[]>({ method: 'GET', url: '/analytics/hot-leads', params: { limit: 5 } })
      .then(setLeads)
      .catch(() => setLeads([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="glass-card rounded-[28px] overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.06]">
        <div>
          <div className="flex items-center gap-1.5">
            <Flame className="h-4 w-4 text-orange-500" />
            <h3 className="text-sm font-semibold text-white">Hot Leads</h3>
          </div>
          <p className="text-xs text-white/40 mt-0.5">Top 5 by AI score — ready for outreach</p>
        </div>
        <Link href="/leads" className="flex items-center gap-1 text-xs font-medium text-cyan-400 hover:text-cyan-300 transition-colors">
          View all <ArrowRight className="h-3 w-3" />
        </Link>
      </div>

      {loading ? (
        <div className="divide-y divide-white/[0.05]">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="flex items-center gap-3 px-5 py-3.5">
              <div className="h-9 w-9 rounded-full bg-white/10 animate-pulse" />
              <div className="flex-1 space-y-1.5">
                <div className="h-3 w-32 rounded bg-white/10 animate-pulse" />
                <div className="h-3 w-44 rounded bg-white/10 animate-pulse" />
              </div>
            </div>
          ))}
        </div>
      ) : leads.length === 0 ? (
        <div className="px-5 py-10 text-center">
          <Flame className="mx-auto h-7 w-7 text-white/20 mb-2" />
          <p className="text-sm text-white/40">No scored leads yet</p>
          <p className="text-xs text-white/30 mt-1">Run enrichment to generate AI scores</p>
        </div>
      ) : (
        <div className="divide-y divide-white/[0.05]">
          {leads.map((lead) => (
            <div key={lead.id} className="flex items-center gap-3 px-5 py-3.5 hover:bg-white/[0.03] transition-colors group">
              <div className="h-9 w-9 rounded-full bg-gradient-to-br from-indigo-600 to-violet-600 flex items-center justify-center text-[11px] font-bold text-white flex-shrink-0">
                {lead.name.split(' ').map(n => n[0]).join('')}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-white truncate">{lead.name}</p>
                <p className="text-xs text-white/40 truncate">
                  {[lead.title, lead.company].filter(Boolean).join(' · ')}
                </p>
              </div>
              <span className={`hidden sm:inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold flex-shrink-0 ${tierColors[lead.tier] ?? tierColors.cold}`}>
                {lead.tier.charAt(0).toUpperCase() + lead.tier.slice(1)}
              </span>
              <ScoreRing score={lead.score} />
              <Link
                href={`/leads/${lead.id}`}
                className="opacity-0 group-hover:opacity-100 flex items-center gap-1 rounded-full border border-white/[0.12] bg-white/[0.06] px-2 py-1 text-[11px] font-medium text-white/70 transition-all hover:bg-white/[0.1] flex-shrink-0"
              >
                <ExternalLink className="h-3 w-3" />
                View
              </Link>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
