import { Suspense } from 'react';
import Link from 'next/link';
import { ArrowUpRight, Zap } from 'lucide-react';
import { DashboardKPIs } from '@/components/dashboard/kpis';
import { LeadPipeline } from '@/components/dashboard/lead-pipeline';
import { RecentActivity } from '@/components/dashboard/recent-activity';
import { HotLeads } from '@/components/dashboard/hot-leads';
import { EmailPerformanceChart } from '@/components/dashboard/email-performance-chart';
import { DashboardBriefing } from '@/components/dashboard/briefing';

function SkeletonCard({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-2xl bg-slate-100 ${className}`} />;
}

export default function DashboardPage() {
  return (
    <div className="space-y-5">

      {/* ── Hero banner ─────────────────────────────────── */}
      <section
        className="relative overflow-hidden rounded-2xl p-6 lg:p-7"
        style={{
          background: 'linear-gradient(135deg, #0d2540 0%, #09131f 55%, #1c4d73 100%)',
          boxShadow: '0 8px 32px rgba(13,37,64,0.18)',
        }}
      >
        {/* Background orbs */}
        <div className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-white/3" />
        <div className="pointer-events-none absolute -bottom-12 left-1/2 h-48 w-48 rounded-full bg-blue-400/5" />

        <div className="relative flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-2xl">
            <span
              className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[10px] font-bold mb-3"
              style={{ background: 'rgba(255,255,255,0.1)', color: 'rgba(255,255,255,0.65)' }}
            >
              <Zap className="h-3 w-3" />
              Revenue command center
            </span>
            <h1 className="text-[1.85rem] font-extrabold tracking-tight text-white leading-tight sm:text-[2.2rem]">
              Operate your outreach engine<br className="hidden sm:block" /> from one clean control plane.
            </h1>
            <p className="mt-3 text-sm leading-relaxed" style={{ color: 'rgba(255,255,255,0.55)' }}>
              Track sending velocity, reply readiness, enrichment throughput, and campaign quality without bouncing between tabs.
            </p>
            <p className="mt-3 text-[11px] font-medium" style={{ color: 'rgba(255,255,255,0.35)' }}>
              {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 shrink-0 xl:max-w-[560px] w-full lg:max-w-[480px]">
            <Suspense fallback={<div className="animate-pulse rounded-2xl bg-white/8 xl:col-span-2 h-[108px]" />}>
              <DashboardBriefing />
            </Suspense>

            <div
              className="rounded-2xl p-4 flex flex-col justify-between"
              style={{ background: 'rgba(255,255,255,0.07)', border: '1px solid rgba(255,255,255,0.08)' }}
            >
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest" style={{ color: 'rgba(255,255,255,0.35)' }}>
                  Next action
                </p>
                <p className="mt-2 text-sm font-semibold text-white leading-snug">Enrich &amp; score your pipeline</p>
                <p className="mt-1.5 text-[11px] leading-relaxed" style={{ color: 'rgba(255,255,255,0.45)' }}>
                  Run enrichment on pending leads then launch a campaign targeting top-scored accounts.
                </p>
              </div>
              <Link
                href="/leads"
                className="mt-3 inline-flex items-center gap-1 text-xs font-semibold transition-colors"
                style={{ color: '#60a5fa' }}
              >
                Open leads <ArrowUpRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* ── KPI Cards ───────────────────────────────────── */}
      <Suspense fallback={
        <div className="grid gap-4 lg:grid-cols-4">
          {[...Array(4)].map((_, i) => <SkeletonCard key={i} className="h-[148px]" />)}
        </div>
      }>
        <DashboardKPIs />
      </Suspense>

      {/* ── Charts row ──────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <Suspense fallback={<SkeletonCard className="h-[300px]" />}>
            <EmailPerformanceChart />
          </Suspense>
        </div>
        <div className="lg:col-span-2">
          <Suspense fallback={<SkeletonCard className="h-[300px]" />}>
            <LeadPipeline />
          </Suspense>
        </div>
      </div>

      {/* ── Hot leads + Activity ─────────────────────────── */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <Suspense fallback={<SkeletonCard className="h-80" />}>
            <HotLeads />
          </Suspense>
        </div>
        <div className="lg:col-span-2">
          <Suspense fallback={<SkeletonCard className="h-80" />}>
            <RecentActivity />
          </Suspense>
        </div>
      </div>
    </div>
  );
}

