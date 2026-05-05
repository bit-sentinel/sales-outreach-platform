'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { BarChart3, Eye, EyeOff, Loader2, ShieldCheck, Sparkles } from 'lucide-react';
import { useAuthStore } from '@/stores/auth-store';
import { apiClient } from '@/lib/api-client';

export default function LoginPage() {
  const router = useRouter();
  const { setUser } = useAuthStore();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      // JSON body expected by FastAPI
      const tokenRes = await apiClient.post('/auth/login', {
        email,
        password,
      });

      const { access_token, refresh_token } = tokenRes.data?.data ?? tokenRes.data;
      if (typeof window !== 'undefined') {
        localStorage.setItem('access_token', access_token);
        if (refresh_token) localStorage.setItem('refresh_token', refresh_token);
      }

      // Fetch current user
      const userRes = await apiClient.get('/auth/me');
      setUser(userRes.data?.data ?? userRes.data);

      router.push('/dashboard');
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      const msg = Array.isArray(detail)
        ? (detail[0] as { msg?: string })?.msg ?? 'Invalid email or password.'
        : typeof detail === 'string'
          ? detail
          : 'Invalid email or password. Please try again.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen overflow-hidden px-5 py-6 lg:px-8 lg:py-8" style={{ background: '#070b14' }}>
      <div className="pointer-events-none absolute inset-0" style={{ background: 'radial-gradient(circle at 20% 20%, rgba(99,102,241,0.15) 0%, transparent 40%), radial-gradient(circle at 80% 80%, rgba(6,182,212,0.08) 0%, transparent 40%)' }} />
      <div className="relative mx-auto grid min-h-[calc(100vh-3rem)] max-w-[1460px] overflow-hidden rounded-[36px] border border-white/[0.07] shadow-2xl backdrop-blur-xl lg:grid-cols-[1.1fr_0.9fr]" style={{ background: 'rgba(255,255,255,0.02)' }}>
        {/* Left brand panel */}
        <div className="hidden p-12 text-white lg:flex lg:flex-col lg:justify-between" style={{ background: 'linear-gradient(135deg, #0d1525 0%, #111827 50%, #1a1040 100%)' }}>
          <div>
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-600 to-violet-600">
                <Sparkles className="h-5 w-5 text-white" />
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-[0.22em] text-white/40">Outreach OS</p>
                <p className="text-xl font-extrabold tracking-[-0.04em]">OutreachAI</p>
              </div>
            </div>

            <h1 className="mt-12 max-w-xl text-[3.2rem] font-extrabold leading-[1.02] tracking-[-0.06em]">A sales outreach workspace that actually feels operational.</h1>
            <p className="mt-5 max-w-lg text-base leading-7 text-white/50">Run enrichment, campaign orchestration, and reply triage from one polished system instead of stitching together tabs and spreadsheets.</p>
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            {[
              { value: 'AI-written', label: 'Personalised per lead using live research', icon: Sparkles },
              { value: 'Multi-step', label: 'Sequences with automated follow-ups', icon: BarChart3 },
              { value: 'Reply-aware', label: 'Stops sequence the moment a lead responds', icon: ShieldCheck },
            ].map((item) => (
              <div key={item.label} className="rounded-[24px] border border-white/[0.08] bg-white/[0.04] p-4 backdrop-blur-sm">
                <item.icon className="h-4 w-4 text-white/40" />
                <p className="mt-4 text-2xl font-bold tracking-[-0.04em]">{item.value}</p>
                <p className="mt-1 text-sm text-white/40">{item.label}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Right form panel */}
        <div className="flex items-center justify-center p-6 sm:p-10">
          <div className="w-full max-w-md rounded-[30px] border border-white/[0.1] p-6 sm:p-8" style={{ background: 'rgba(255,255,255,0.04)', backdropFilter: 'blur(20px)' }}>
            <div className="mb-8 lg:hidden">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-600 to-violet-600 text-white">
                  <Sparkles className="h-4 w-4" />
                </div>
                <div>
                  <p className="app-label">Outreach OS</p>
                  <p className="text-lg font-extrabold tracking-[-0.04em] text-white">OutreachAI</p>
                </div>
              </div>
            </div>

            <div className="mb-7">
              <p className="app-label">Sign in</p>
              <h2 className="mt-2 text-[2rem] font-extrabold tracking-[-0.05em] text-white">Welcome back.</h2>
              <p className="mt-2 text-sm leading-6 text-white/50">Access your workspace, review AI signals, and keep outbound moving without context switching.</p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label htmlFor="email" className="mb-1.5 block text-xs font-semibold uppercase tracking-[0.16em] text-white/40">
                  Email address
                </label>
                <input
                  id="email"
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  className="w-full rounded-[18px] border border-white/[0.1] bg-white/[0.06] px-4 py-3 text-sm text-white placeholder:text-white/25 focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                />
              </div>

              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <label htmlFor="password" className="block text-xs font-semibold uppercase tracking-[0.16em] text-white/40">
                    Password
                  </label>
                  <a href="#" className="text-xs font-semibold text-indigo-400 hover:text-indigo-300">
                    Forgot password?
                  </a>
                </div>
                <div className="relative">
                  <input
                    id="password"
                    type={showPw ? 'text' : 'password'}
                    required
                    autoComplete="current-password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    placeholder="Enter your password"
                    className="w-full rounded-[18px] border border-white/[0.1] bg-white/[0.06] px-4 py-3 pr-11 text-sm text-white placeholder:text-white/25 focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPw(!showPw)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-white/30 transition-colors hover:text-white/60"
                    tabIndex={-1}
                  >
                    {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              {error && (
                <div className="rounded-[18px] border border-rose-500/30 bg-rose-500/10 px-4 py-3">
                  <p className="text-sm text-rose-400">{error}</p>
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="mt-2 flex w-full items-center justify-center gap-2 rounded-[18px] bg-gradient-to-r from-indigo-600 to-violet-600 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-900/50 transition-transform hover:-translate-y-0.5 disabled:opacity-60"
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {loading ? 'Signing in...' : 'Enter workspace'}
              </button>
            </form>

            <p className="mt-6 text-center text-xs text-white/30">
              Need access? <a href="mailto:cto@launchhouse.events" className="font-semibold text-indigo-400 hover:text-indigo-300">Contact your admin</a>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
