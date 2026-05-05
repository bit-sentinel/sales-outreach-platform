'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api-client';

interface PipelineData {
  new: number;
  enriching: number;
  enriched: number;
  scored: number;
  campaign_active: number;
  replied: number;
  converted: number;
  disqualified: number;
}

export function LeadPipeline() {
  const [data, setData] = useState<PipelineData | null>(null);

  useEffect(() => {
    api<PipelineData>({ method: 'GET', url: '/analytics/lead-pipeline' })
      .then(setData)
      .catch(() => null);
  }, []);

  const stages = data
    ? [
        { stage: 'New',         count: data.new,            color: '#94a3b8' },
        { stage: 'Enriched',    count: data.enriched,       color: '#60a5fa' },
        { stage: 'Scored',      count: data.scored,         color: '#f59e0b' },
        { stage: 'In Campaign', count: data.campaign_active, color: '#a78bfa' },
        { stage: 'Replied',     count: data.replied,        color: '#34d399' },
        { stage: 'Converted',   count: data.converted,      color: '#10b981' },
      ]
    : [];

  const total = stages[0]?.count || 1;

  return (
    <div className="glass-card rounded-[28px] p-5 flex flex-col" style={{ minHeight: '300px' }}>
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-white">Lead Funnel</h3>
        <p className="text-xs text-white/40 mt-0.5">
          {data ? `${stages[0].count.toLocaleString()} leads entering pipeline` : 'Loading…'}
        </p>
      </div>

      {!data ? (
        <div className="flex-1 flex flex-col justify-between gap-2.5">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="animate-pulse h-5 rounded-md bg-white/10" />
          ))}
        </div>
      ) : (
        <div className="flex-1 flex flex-col justify-between gap-2.5">
          {stages.map((s, i) => {
            const pct = (s.count / total) * 100;
            const convRate = i > 0 ? ((s.count / stages[i - 1].count) * 100).toFixed(0) : null;
            return (
              <div key={s.stage}>
                <div className="flex items-center justify-between text-xs mb-1.5">
                  <div className="flex items-center gap-1.5">
                    <div className="h-2.5 w-2.5 rounded-sm flex-shrink-0" style={{ backgroundColor: s.color }} />
                    <span className="font-medium text-white/80">{s.stage}</span>
                    {convRate && stages[i - 1].count > 0 && (
                      <span className="text-white/30">→ {convRate}%</span>
                    )}
                  </div>
                  <span className="font-semibold text-white/60 tabular-nums">{s.count.toLocaleString()}</span>
                </div>
                <div className="h-5 rounded-md bg-white/[0.04] overflow-hidden">
                  <div
                    className="h-full rounded-md transition-all duration-700"
                    style={{ width: `${pct}%`, backgroundColor: s.color, opacity: 0.8 }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="mt-4 pt-4 border-t border-white/[0.06] flex items-center justify-between">
        <span className="text-xs text-white/40">New → Converted</span>
        <span className="text-xs font-bold text-emerald-400">
          {data && stages[0].count > 0
            ? `${((stages[5].count / stages[0].count) * 100).toFixed(1)}% overall conversion`
            : '—'}
        </span>
      </div>
    </div>
  );
}
