'use client';

import { useEffect, useState } from 'react';
import { User, Mail, Users, Sparkles, Key, Plus, Eye, EyeOff, AlertCircle, Trash2, Activity, Upload, Zap, Play, Pause, RotateCcw, UserPlus, RefreshCw, Loader2, FlaskConical } from 'lucide-react';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/stores/auth-store';
import type { User as AuthUser } from '@/stores/auth-store';

const TABS = [
  { id: 'account', label: 'Account', icon: User },
  { id: 'email', label: 'Email Accounts', icon: Mail },
  { id: 'team', label: 'Team', icon: Users },
  { id: 'ai', label: 'AI Config', icon: Sparkles },
  { id: 'api', label: 'API Keys', icon: Key },
  { id: 'testmode', label: 'Test Mode', icon: FlaskConical },
  { id: 'activity', label: 'Activity Log', icon: Activity },
];


function InputField({ label, id, type = 'text', defaultValue = '', placeholder = '' }: { label: string; id: string; type?: string; defaultValue?: string; placeholder?: string }) {
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium text-white/50 mb-1.5">{label}</label>
      <input
        id={id}
        type={type}
        defaultValue={defaultValue}
        placeholder={placeholder}
        className="w-full rounded-xl border border-white/[0.1] bg-white/[0.05] px-3 py-2 text-sm text-white placeholder:text-white/20 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 transition"
      />
    </div>
  );
}

function SectionHeader({ title, description, action }: { title: string; description?: string; action?: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between mb-5">
      <div>
        <h3 className="text-sm font-semibold text-white">{title}</h3>
        {description && <p className="text-xs text-white/40 mt-0.5">{description}</p>}
      </div>
      {action}
    </div>
  );
}

function AccountTab() {
  const { user, setUser } = useAuthStore();

  const [firstName, setFirstName] = useState(user?.first_name ?? '');
  const [lastName, setLastName] = useState(user?.last_name ?? '');
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileMsg, setProfileMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [pwSaving, setPwSaving] = useState(false);
  const [pwMsg, setPwMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const initials = ((firstName[0] ?? '') + (lastName[0] ?? '')).toUpperCase() || user?.email?.[0]?.toUpperCase() || 'U';

  async function saveProfile() {
    setProfileSaving(true);
    setProfileMsg(null);
    try {
      const updated = await api<AuthUser>({ method: 'PATCH', url: '/auth/me', data: { first_name: firstName.trim(), last_name: lastName.trim() } });
      setUser({ ...user!, first_name: updated.first_name, last_name: updated.last_name });
      setProfileMsg({ ok: true, text: 'Profile updated successfully.' });
    } catch {
      setProfileMsg({ ok: false, text: 'Failed to update profile. Please try again.' });
    } finally {
      setProfileSaving(false);
    }
  }

  async function updatePassword() {
    if (!currentPw || !newPw || !confirmPw) {
      setPwMsg({ ok: false, text: 'All password fields are required.' });
      return;
    }
    if (newPw !== confirmPw) {
      setPwMsg({ ok: false, text: 'New passwords do not match.' });
      return;
    }
    if (newPw.length < 8) {
      setPwMsg({ ok: false, text: 'New password must be at least 8 characters.' });
      return;
    }
    setPwSaving(true);
    setPwMsg(null);
    try {
      await api({ method: 'POST', url: '/auth/change-password', data: { current_password: currentPw, new_password: newPw } });
      setCurrentPw('');
      setNewPw('');
      setConfirmPw('');
      setPwMsg({ ok: true, text: 'Password updated successfully.' });
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      setPwMsg({ ok: false, text: typeof detail === 'string' ? detail : 'Failed to update password.' });
    } finally {
      setPwSaving(false);
    }
  }

  const inputCls = 'w-full rounded-xl border border-white/[0.1] bg-white/[0.05] px-3 py-2 text-sm text-white placeholder:text-white/20 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 transition';

  return (
    <div className="space-y-6">
      <div className="glass-card rounded-[24px] p-5">
        <SectionHeader title="Profile" description="Update your personal information" />
        <div className="flex items-start gap-5 mb-5">
          <div className="h-14 w-14 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center text-lg font-bold text-white flex-shrink-0">{initials}</div>
          <div>
            <button className="rounded-xl border border-white/[0.12] px-3 py-1.5 text-xs font-medium text-white/60 hover:bg-white/[0.06] transition-colors">Change photo</button>
            <p className="text-xs text-white/30 mt-1.5">JPG, PNG under 2MB</p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-medium text-white/50 mb-1.5">First name</label>
            <input className={inputCls} value={firstName} onChange={e => setFirstName(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs font-medium text-white/50 mb-1.5">Last name</label>
            <input className={inputCls} value={lastName} onChange={e => setLastName(e.target.value)} />
          </div>
          <div className="col-span-2">
            <label className="block text-xs font-medium text-white/50 mb-1.5">Email address</label>
            <input className="w-full rounded-xl border border-white/[0.07] bg-white/[0.03] px-3 py-2 text-sm text-white/40 cursor-not-allowed" value={user?.email ?? ''} readOnly />
          </div>
        </div>
        {profileMsg && (
          <p className={cn('mt-3 text-xs font-medium', profileMsg.ok ? 'text-emerald-400' : 'text-rose-400')}>{profileMsg.text}</p>
        )}
        <div className="mt-4 flex justify-end">
          <button onClick={saveProfile} disabled={profileSaving} className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-4 py-2 text-xs font-medium text-white hover:opacity-90 transition shadow-lg shadow-indigo-900/40 disabled:opacity-50">
            {profileSaving && <Loader2 className="h-3 w-3 animate-spin" />}
            {profileSaving ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      </div>

      <div className="glass-card rounded-[24px] p-5">
        <SectionHeader title="Password" description="Update your login password" />
        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-white/50 mb-1.5">Current password</label>
            <input type="password" className={inputCls} placeholder="Enter current password" value={currentPw} onChange={e => setCurrentPw(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs font-medium text-white/50 mb-1.5">New password</label>
            <input type="password" className={inputCls} placeholder="Min 8 characters" value={newPw} onChange={e => setNewPw(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs font-medium text-white/50 mb-1.5">Confirm new password</label>
            <input type="password" className={inputCls} placeholder="Confirm password" value={confirmPw} onChange={e => setConfirmPw(e.target.value)} />
          </div>
        </div>
        {pwMsg && (
          <p className={cn('mt-3 text-xs font-medium', pwMsg.ok ? 'text-emerald-400' : 'text-rose-400')}>{pwMsg.text}</p>
        )}
        <div className="mt-4 flex justify-end">
          <button onClick={updatePassword} disabled={pwSaving} className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-4 py-2 text-xs font-medium text-white hover:opacity-90 transition shadow-lg shadow-indigo-900/40 disabled:opacity-50">
            {pwSaving && <Loader2 className="h-3 w-3 animate-spin" />}
            {pwSaving ? 'Updating…' : 'Update password'}
          </button>
        </div>
      </div>

      <div className="glass-card rounded-[24px] border-red-500/20 p-5">
        <SectionHeader title="Danger zone" description="Irreversible actions — proceed with caution" />
        <button className="rounded-xl border border-red-500/30 px-3 py-1.5 text-xs font-medium text-red-400 hover:bg-red-500/10 transition-colors">Delete account</button>
      </div>
    </div>
  );
}

type SenderAccount = {
  id: string;
  email: string;
  display_name: string;
  provider: string;
  daily_limit: number;
  sent_today: number;
  is_active: boolean;
  health_score: number;
  imap_host: string | null;
  imap_user: string | null;
  has_imap: boolean;
};

function EmailTab() {
  const [accounts, setAccounts] = useState<SenderAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [addEmail, setAddEmail] = useState('');
  const [addName, setAddName] = useState('');
  const [addProvider, setAddProvider] = useState('gmail');
  const [addLimit, setAddLimit] = useState('150');
  const [addImapHost, setAddImapHost] = useState('');
  const [addImapUser, setAddImapUser] = useState('');
  const [addImapPassword, setAddImapPassword] = useState('');
  const [addSaving, setAddSaving] = useState(false);
  const [addError, setAddError] = useState('');

  const [editImapId, setEditImapId] = useState<string | null>(null);
  const [editImapHost, setEditImapHost] = useState('');
  const [editImapUser, setEditImapUser] = useState('');
  const [editImapPassword, setEditImapPassword] = useState('');
  const [editImapSaving, setEditImapSaving] = useState(false);
  const [editImapError, setEditImapError] = useState('');

  async function load() {
    setLoading(true);
    try {
      const data = await api<SenderAccount[]>({ method: 'GET', url: '/admin/sender-accounts' });
      setAccounts(Array.isArray(data) ? data : []);
    } catch { setAccounts([]); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  async function handleAdd() {
    setAddSaving(true); setAddError('');
    try {
      await api({ method: 'POST', url: '/admin/sender-accounts', data: {
        email: addEmail, display_name: addName, provider: addProvider, daily_limit: parseInt(addLimit),
        imap_host: addImapHost || null,
        imap_user: addImapUser || addEmail || null,
        imap_password: addImapPassword || null,
      }});
      setShowAdd(false);
      setAddEmail(''); setAddName(''); setAddProvider('gmail'); setAddLimit('150');
      setAddImapHost(''); setAddImapUser(''); setAddImapPassword('');
      await load();
    } catch (err: unknown) {
      const detail = (err as any)?.response?.data?.detail;
      setAddError(typeof detail === 'string' ? detail : 'Failed to add account.');
    } finally { setAddSaving(false); }
  }

  async function toggleActive(acct: SenderAccount) {
    await api({ method: 'PATCH', url: `/admin/sender-accounts/${acct.id}`, data: { is_active: !acct.is_active } });
    setAccounts(a => a.map(x => x.id === acct.id ? { ...x, is_active: !x.is_active } : x));
  }

  async function handleDelete(id: string) {
    await api({ method: 'DELETE', url: `/admin/sender-accounts/${id}` });
    setAccounts(a => a.filter(x => x.id !== id));
  }

  function openEditImap(acct: SenderAccount) {
    setEditImapId(acct.id);
    setEditImapHost(acct.imap_host || '');
    setEditImapUser(acct.imap_user || acct.email);
    setEditImapPassword('');
    setEditImapError('');
  }

  async function handleSaveImap(acct: SenderAccount) {
    setEditImapSaving(true); setEditImapError('');
    try {
      const payload: Record<string, string | null> = {
        imap_host: editImapHost || null,
        imap_user: editImapUser || null,
      };
      if (editImapPassword) payload.imap_password = editImapPassword;
      await api({ method: 'PATCH', url: `/admin/sender-accounts/${acct.id}`, data: payload });
      setEditImapId(null);
      await load();
    } catch (err: unknown) {
      const detail = (err as any)?.response?.data?.detail;
      setEditImapError(typeof detail === 'string' ? detail : 'Failed to save IMAP credentials.');
    } finally { setEditImapSaving(false); }
  }

  const inputCls = 'w-full rounded-xl border border-white/[0.1] bg-white/[0.05] px-3 py-2 text-sm text-white placeholder:text-white/20 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition';

  return (
    <div className="space-y-5">
      <div className="glass-card rounded-[24px] p-5">
        <SectionHeader
          title="Connected accounts"
          description="Manage sending inboxes for outreach campaigns"
          action={
            <button onClick={() => setShowAdd(v => !v)} className="flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 transition shadow-lg shadow-indigo-900/30">
              <Plus className="h-3.5 w-3.5" /> Connect inbox
            </button>
          }
        />

        {showAdd && (
          <div className="mb-4 rounded-xl border border-indigo-500/30 bg-indigo-500/10 p-4 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-white/50 mb-1">Email</label>
                <input className={inputCls} placeholder="sender@yourco.com" value={addEmail} onChange={e => setAddEmail(e.target.value)} />
              </div>
              <div>
                <label className="block text-xs font-medium text-white/50 mb-1">Display name</label>
                <input className={inputCls} placeholder="Outreach Bot 1" value={addName} onChange={e => setAddName(e.target.value)} />
              </div>
              <div>
                <label className="block text-xs font-medium text-white/50 mb-1">Provider</label>
                <select className={inputCls} value={addProvider} onChange={e => setAddProvider(e.target.value)}>
                  <option value="gmail">Gmail</option>
                  <option value="sendgrid">SendGrid</option>
                  <option value="ses">AWS SES</option>
                  <option value="smtp">SMTP</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-white/50 mb-1">Daily limit</label>
                <input type="number" className={inputCls} value={addLimit} onChange={e => setAddLimit(e.target.value)} />
              </div>
            </div>
            {/* IMAP section */}
            <div className="border-t border-white/[0.07] pt-3">
              <p className="text-xs font-semibold text-white/50 mb-2">IMAP credentials <span className="font-normal text-white/30">(for reply polling — optional but recommended)</span></p>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-medium text-white/40 mb-1">IMAP host</label>
                  <input className={inputCls} placeholder="imap.gmail.com" value={addImapHost} onChange={e => setAddImapHost(e.target.value)} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-white/40 mb-1">IMAP username</label>
                  <input className={inputCls} placeholder="same as email" value={addImapUser} onChange={e => setAddImapUser(e.target.value)} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-white/40 mb-1">App password</label>
                  <input type="password" className={inputCls} placeholder="••••••••••••••••" value={addImapPassword} onChange={e => setAddImapPassword(e.target.value)} />
                </div>
              </div>
            </div>
            {addError && <p className="text-xs text-rose-400">{addError}</p>}
            <div className="flex gap-2">
              <button onClick={handleAdd} disabled={addSaving || !addEmail || !addName} className="flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50 transition">
                {addSaving && <Loader2 className="h-3 w-3 animate-spin" />} Add
              </button>
              <button onClick={() => setShowAdd(false)} className="rounded-xl border border-white/[0.1] px-3 py-1.5 text-xs font-medium text-white/50 hover:bg-white/[0.05] transition">Cancel</button>
            </div>
          </div>
        )}

        {loading ? (
          <div className="flex justify-center py-10"><Loader2 className="h-5 w-5 animate-spin text-white/30" /></div>
        ) : accounts.length === 0 ? (
          <p className="py-8 text-center text-sm text-white/30">No sender accounts yet. Connect an inbox to start sending.</p>
        ) : (
          <div className="space-y-3">
            {accounts.map(acct => (
              <div key={acct.id} className="rounded-xl border border-white/[0.08] bg-white/[0.03] overflow-hidden">
                <div className="flex items-center gap-4 px-4 py-3 hover:bg-white/[0.02] transition-colors">
                  <div className="h-9 w-9 rounded-full bg-gradient-to-br from-emerald-500 to-cyan-500 flex items-center justify-center text-xs font-bold text-white flex-shrink-0">
                    {acct.provider === 'gmail' ? 'G' : acct.provider === 'sendgrid' ? 'SG' : acct.provider === 'ses' ? 'AWS' : 'SM'}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <p className="text-sm font-medium text-white">{acct.display_name}</p>
                      <span className={cn('rounded-full px-1.5 py-0.5 text-[10px] font-semibold', acct.is_active ? 'bg-emerald-500/20 text-emerald-400' : 'bg-white/10 text-white/40')}>
                        {acct.is_active ? 'Active' : 'Paused'}
                      </span>
                    </div>
                    <p className="text-xs text-white/40">
                      {acct.email} · {acct.provider} · {acct.sent_today}/{acct.daily_limit} today
                      {acct.has_imap
                        ? <span className="ml-2 text-emerald-400">● IMAP connected</span>
                        : <span className="ml-2 text-amber-400/70">○ No IMAP</span>
                      }
                    </p>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <div className="flex items-center justify-end gap-1">
                      <div className="h-1.5 w-16 rounded-full bg-white/[0.08]">
                        <div className={cn('h-1.5 rounded-full', acct.health_score >= 90 ? 'bg-emerald-500' : acct.health_score >= 70 ? 'bg-amber-500' : 'bg-red-500')} style={{ width: `${acct.health_score}%` }} />
                      </div>
                      <span className="text-[10px] text-white/30">{acct.health_score}%</span>
                    </div>
                  </div>
                  <button
                    onClick={() => editImapId === acct.id ? setEditImapId(null) : openEditImap(acct)}
                    className={cn('rounded-xl border p-1.5 transition-colors ml-1', editImapId === acct.id ? 'border-indigo-500/50 bg-indigo-500/20 text-indigo-400' : 'border-white/[0.1] text-white/30 hover:bg-white/[0.06] hover:text-indigo-400')}
                    title="Edit IMAP credentials"
                  >
                    <Key className="h-3.5 w-3.5" />
                  </button>
                  <button onClick={() => toggleActive(acct)} className="rounded-xl border border-white/[0.1] p-1.5 text-white/30 hover:bg-white/[0.06] hover:text-white/70 transition-colors" title={acct.is_active ? 'Pause' : 'Resume'}>
                    {acct.is_active ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
                  </button>
                  <button onClick={() => handleDelete(acct.id)} className="rounded-xl border border-white/[0.1] p-1.5 text-white/30 hover:bg-white/[0.06] hover:text-red-400 transition-colors">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>

                {editImapId === acct.id && (
                  <div className="border-t border-white/[0.07] bg-indigo-500/5 px-4 py-3 space-y-3">
                    <p className="text-xs font-semibold text-white/50">IMAP credentials <span className="font-normal text-white/30">— used for reply polling</span></p>
                    <div className="grid grid-cols-3 gap-3">
                      <div>
                        <label className="block text-xs font-medium text-white/40 mb-1">IMAP host</label>
                        <input className={inputCls} placeholder="imap.gmail.com" value={editImapHost} onChange={e => setEditImapHost(e.target.value)} />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-white/40 mb-1">IMAP username</label>
                        <input className={inputCls} placeholder="same as email" value={editImapUser} onChange={e => setEditImapUser(e.target.value)} />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-white/40 mb-1">App password</label>
                        <input type="password" className={inputCls} placeholder="leave blank to keep existing" value={editImapPassword} onChange={e => setEditImapPassword(e.target.value)} />
                      </div>
                    </div>
                    {editImapError && <p className="text-xs text-rose-400">{editImapError}</p>}
                    <div className="flex gap-2">
                      <button onClick={() => handleSaveImap(acct)} disabled={editImapSaving} className="flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50 transition">
                        {editImapSaving && <Loader2 className="h-3 w-3 animate-spin" />} Save
                      </button>
                      <button onClick={() => setEditImapId(null)} className="rounded-xl border border-white/[0.1] px-3 py-1.5 text-xs font-medium text-white/50 hover:bg-white/[0.05] transition">Cancel</button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

type TeamMember = {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  role: string;
  last_login_at: string | null;
};

function TeamTab() {
  const { user: currentUser } = useAuthStore();
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [roleChanging, setRoleChanging] = useState<string | null>(null);

  const [showInvite, setShowInvite] = useState(false);
  const [inviteFirstName, setInviteFirstName] = useState('');
  const [inviteLastName, setInviteLastName] = useState('');
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('member');
  const [invitePassword, setInvitePassword] = useState('');
  const [inviting, setInviting] = useState(false);
  const [inviteMsg, setInviteMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function load() {
    setLoading(true);
    try {
      const data = await api<TeamMember[]>({ method: 'GET', url: '/admin/users' });
      setMembers(Array.isArray(data) ? data : []);
    } catch { setMembers([]); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  async function handleInvite() {
    setInviting(true); setInviteMsg(null);
    try {
      await api({ method: 'POST', url: '/admin/users', data: {
        first_name: inviteFirstName.trim(),
        last_name: inviteLastName.trim(),
        email: inviteEmail.trim(),
        role: inviteRole,
        temp_password: invitePassword,
      }});
      setInviteMsg({ ok: true, text: `${inviteFirstName} added. Share their temporary password with them.` });
      setInviteFirstName(''); setInviteLastName(''); setInviteEmail(''); setInvitePassword(''); setInviteRole('member');
      setShowInvite(false);
      await load();
    } catch (err: unknown) {
      const detail = (err as any)?.response?.data?.detail;
      setInviteMsg({ ok: false, text: typeof detail === 'string' ? detail : 'Failed to add member.' });
    } finally { setInviting(false); }
  }

  async function changeRole(memberId: string, role: string) {
    setRoleChanging(memberId);
    try {
      await api({ method: 'PATCH', url: `/admin/users/${memberId}/role`, data: { role } });
      setMembers(m => m.map(x => x.id === memberId ? { ...x, role } : x));
    } catch {} finally { setRoleChanging(null); }
  }

  async function removeUser(memberId: string) {
    await api({ method: 'DELETE', url: `/admin/users/${memberId}` });
    setMembers(m => m.filter(x => x.id !== memberId));
  }

  function lastActive(iso: string | null) {
    if (!iso) return 'Never';
    const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  }

  return (
    <div className="glass-card rounded-[24px] p-5">
      <SectionHeader
        title="Team members"
        description="Manage access and roles for your workspace"
        action={
          <button onClick={() => { setShowInvite(v => !v); setInviteMsg(null); }} className="flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 transition shadow-lg shadow-indigo-900/30">
            <Plus className="h-3.5 w-3.5" /> Add member
          </button>
        }
      />

      {inviteMsg && (
        <p className={cn('mb-4 text-xs font-medium', inviteMsg.ok ? 'text-emerald-400' : 'text-rose-400')}>{inviteMsg.text}</p>
      )}

      {showInvite && (() => {
        const inputCls = 'w-full rounded-xl border border-white/[0.1] bg-white/[0.05] px-3 py-2 text-sm text-white placeholder:text-white/20 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition';
        return (
          <div className="mb-4 rounded-xl border border-indigo-500/30 bg-indigo-500/10 p-4 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-white/50 mb-1">First name</label>
                <input className={inputCls} placeholder="Shehdeep" value={inviteFirstName} onChange={e => setInviteFirstName(e.target.value)} />
              </div>
              <div>
                <label className="block text-xs font-medium text-white/50 mb-1">Last name</label>
                <input className={inputCls} placeholder="Chanda" value={inviteLastName} onChange={e => setInviteLastName(e.target.value)} />
              </div>
              <div>
                <label className="block text-xs font-medium text-white/50 mb-1">Email</label>
                <input type="email" className={inputCls} placeholder="member@company.com" value={inviteEmail} onChange={e => setInviteEmail(e.target.value)} />
              </div>
              <div>
                <label className="block text-xs font-medium text-white/50 mb-1">Role</label>
                <select className={inputCls} value={inviteRole} onChange={e => setInviteRole(e.target.value)}>
                  <option value="admin">Admin</option>
                  <option value="member">Member</option>
                  <option value="viewer">Viewer</option>
                </select>
              </div>
              <div className="col-span-2">
                <label className="block text-xs font-medium text-white/50 mb-1">Temporary password</label>
                <input type="password" className={inputCls} placeholder="Min 8 characters" value={invitePassword} onChange={e => setInvitePassword(e.target.value)} />
              </div>
            </div>
            <div className="flex gap-2">
              <button onClick={handleInvite} disabled={inviting || !inviteFirstName || !inviteLastName || !inviteEmail || invitePassword.length < 8}
                className="flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50 transition">
                {inviting && <Loader2 className="h-3 w-3 animate-spin" />} Add member
              </button>
              <button onClick={() => setShowInvite(false)} className="rounded-xl border border-white/[0.1] px-3 py-1.5 text-xs text-white/50 hover:bg-white/[0.05] transition">Cancel</button>
            </div>
          </div>
        );
      })()}

      {loading ? (
        <div className="flex justify-center py-10"><Loader2 className="h-5 w-5 animate-spin text-white/30" /></div>
      ) : (
        <div className="space-y-2">
          {members.map(member => {
            const initials = (member.first_name[0] ?? '') + (member.last_name[0] ?? '');
            const isSelf = member.id === currentUser?.id;
            return (
              <div key={member.id} className="flex items-center gap-3 rounded-xl border border-white/[0.07] px-4 py-3 hover:bg-white/[0.03] transition-colors">
                <div className="h-8 w-8 rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center text-xs font-bold text-white flex-shrink-0">
                  {initials.toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-white">{member.first_name} {member.last_name} {isSelf && <span className="text-[10px] text-white/30">(you)</span>}</p>
                  <p className="text-xs text-white/40">{member.email}</p>
                </div>
                <span className="text-xs text-white/30 flex-shrink-0">{lastActive(member.last_login_at)}</span>
                <div className="relative flex-shrink-0">
                  <select
                    className="rounded-xl border border-white/[0.1] bg-white/[0.05] px-2 py-1 text-xs text-white/70 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-40"
                    value={member.role}
                    disabled={isSelf || roleChanging === member.id}
                    onChange={e => changeRole(member.id, e.target.value)}
                  >
                    <option value="owner">Owner</option>
                    <option value="admin">Admin</option>
                    <option value="member">Member</option>
                    <option value="viewer">Viewer</option>
                  </select>
                  {roleChanging === member.id && <Loader2 className="absolute right-2 top-1/2 -translate-y-1/2 h-3 w-3 animate-spin text-white/50" />}
                </div>
                {!isSelf && (
                  <button onClick={() => removeUser(member.id)} className="rounded-xl border border-white/[0.1] p-1.5 text-white/30 hover:text-red-400 transition-colors">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

const AI_MODELS = [
  { id: 'claude-sonnet', label: 'Claude Sonnet 4.5', desc: 'Best balance of quality and speed', recommended: true },
  { id: 'claude-opus', label: 'Claude Opus 4.6', desc: 'Highest quality, slower, higher cost', recommended: false },
  { id: 'gpt-4o', label: 'GPT-4o', desc: 'OpenAI flagship model', recommended: false },
];

const TONES = ['Professional & Concise', 'Warm & Conversational', 'Authoritative & Bold', 'Formal'];

function AITab() {
  const [model, setModel] = useState('claude-sonnet');
  const [tone, setTone] = useState('Professional & Concise');
  const [emailLength, setEmailLength] = useState(160);
  const [anthropicKey, setAnthropicKey] = useState('');
  const [openaiKey, setOpenaiKey] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    api<{ ai_config: { model: string; tone: string; email_length: number } }>({
      method: 'GET', url: '/admin/tenant',
    }).then(data => {
      setModel(data.ai_config.model);
      setTone(data.ai_config.tone);
      setEmailLength(data.ai_config.email_length);
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  async function save() {
    setSaving(true); setMsg(null);
    try {
      const payload: Record<string, unknown> = { model, tone, email_length: emailLength };
      if (anthropicKey) payload.anthropic_api_key = anthropicKey;
      if (openaiKey) payload.openai_api_key = openaiKey;
      await api({ method: 'PATCH', url: '/admin/tenant/ai-config', data: payload });
      setAnthropicKey(''); setOpenaiKey('');
      setMsg({ ok: true, text: 'AI settings saved.' });
    } catch {
      setMsg({ ok: false, text: 'Failed to save.' });
    } finally { setSaving(false); }
  }

  const inputCls = 'w-full rounded-xl border border-white/[0.1] bg-white/[0.05] px-3 py-2 text-sm text-white placeholder:text-white/20 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition';

  if (loading) return <div className="flex justify-center py-16"><Loader2 className="h-5 w-5 animate-spin text-white/30" /></div>;

  return (
    <div className="space-y-5">
      <div className="glass-card rounded-[24px] p-5">
        <SectionHeader title="Primary model" description="The LLM used for email generation and analysis" />
        <div className="space-y-3">
          {AI_MODELS.map(m => (
            <label key={m.id} className={cn('flex items-start gap-3 rounded-xl border p-3.5 cursor-pointer transition-colors', model === m.id ? 'border-indigo-500/40 bg-indigo-500/10' : 'border-white/[0.08] hover:bg-white/[0.04]')}>
              <input type="radio" name="model" checked={model === m.id} onChange={() => setModel(m.id)} className="mt-0.5 accent-indigo-500" />
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium text-white">{m.label}</p>
                  {m.recommended && <span className="rounded-full bg-indigo-500/20 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-400">Recommended</span>}
                </div>
                <p className="text-xs text-white/40 mt-0.5">{m.desc}</p>
              </div>
            </label>
          ))}
        </div>
      </div>

      <div className="glass-card rounded-[24px] p-5">
        <SectionHeader title="AI behaviour" description="Control how the AI writes and analyzes" />
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-white/50 mb-1.5">Email tone</label>
            <select className={inputCls} value={tone} onChange={e => setTone(e.target.value)}>
              {TONES.map(t => <option key={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <div className="flex justify-between mb-1.5">
              <label className="text-xs font-medium text-white/50">Email length</label>
              <span className="text-xs text-white/40">~{emailLength} words</span>
            </div>
            <input type="range" min="50" max="400" value={emailLength} onChange={e => setEmailLength(Number(e.target.value))} className="w-full accent-indigo-500" />
            <div className="flex justify-between text-[10px] text-white/25 mt-0.5"><span>50w</span><span>400w</span></div>
          </div>
          <div>
            <label className="block text-xs font-medium text-white/50 mb-1.5">Anthropic API key <span className="text-white/25">(leave blank to keep existing)</span></label>
            <input type="password" className={inputCls} placeholder="sk-ant-api03-••••••••" value={anthropicKey} onChange={e => setAnthropicKey(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs font-medium text-white/50 mb-1.5">OpenAI API key <span className="text-white/25">(leave blank to keep existing)</span></label>
            <input type="password" className={inputCls} placeholder="sk-••••••••" value={openaiKey} onChange={e => setOpenaiKey(e.target.value)} />
          </div>
        </div>
        {msg && <p className={cn('mt-3 text-xs font-medium', msg.ok ? 'text-emerald-400' : 'text-rose-400')}>{msg.text}</p>}
        <div className="mt-4 flex justify-end">
          <button onClick={save} disabled={saving} className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-4 py-2 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50 transition shadow-lg shadow-indigo-900/40">
            {saving && <Loader2 className="h-3 w-3 animate-spin" />} Save AI settings
          </button>
        </div>
      </div>
    </div>
  );
}

type ApiKeyItem = {
  id: string;
  name: string;
  key_prefix: string;
  last_used_at: string | null;
  created_at: string;
  // only present right after creation:
  key?: string;
};

function APITab() {
  const [keys, setKeys] = useState<ApiKeyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [newKeyName, setNewKeyName] = useState('');
  const [creating, setCreating] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [revealedKey, setRevealedKey] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const data = await api<ApiKeyItem[]>({ method: 'GET', url: '/admin/api-keys' });
      setKeys(Array.isArray(data) ? data : []);
    } catch { setKeys([]); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  async function createKey() {
    if (!newKeyName.trim()) return;
    setCreating(true);
    try {
      const created = await api<ApiKeyItem>({ method: 'POST', url: '/admin/api-keys', data: { name: newKeyName.trim() } });
      setKeys(k => [...k, created]);
      setRevealedKey(created.id); // auto-reveal newly created key
      setNewKeyName('');
      setShowCreate(false);
    } catch {} finally { setCreating(false); }
  }

  async function revokeKey(id: string) {
    await api({ method: 'DELETE', url: `/admin/api-keys/${id}` });
    setKeys(k => k.filter(x => x.id !== id));
  }

  function formatDate(iso: string | null) {
    if (!iso) return 'Never';
    return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  }

  const inputCls = 'w-full rounded-xl border border-white/[0.1] bg-white/[0.05] px-3 py-2 text-sm text-white placeholder:text-white/20 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition';

  return (
    <div className="glass-card rounded-[24px] p-5">
      <SectionHeader
        title="API keys"
        description="Use these keys to access the OutreachAI API"
        action={
          <button onClick={() => setShowCreate(v => !v)} className="flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 transition shadow-lg shadow-indigo-900/30">
            <Plus className="h-3.5 w-3.5" /> New key
          </button>
        }
      />

      {showCreate && (
        <div className="mb-4 flex gap-2">
          <input className={inputCls} placeholder="Key name (e.g. Production)" value={newKeyName} onChange={e => setNewKeyName(e.target.value)} onKeyDown={e => e.key === 'Enter' && createKey()} />
          <button onClick={createKey} disabled={creating || !newKeyName.trim()} className="flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-3 py-2 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50 whitespace-nowrap transition">
            {creating && <Loader2 className="h-3 w-3 animate-spin" />} Create
          </button>
          <button onClick={() => setShowCreate(false)} className="rounded-xl border border-white/[0.1] px-3 py-2 text-xs text-white/50 hover:bg-white/[0.05] transition">Cancel</button>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-10"><Loader2 className="h-5 w-5 animate-spin text-white/30" /></div>
      ) : keys.length === 0 ? (
        <p className="py-8 text-center text-sm text-white/30">No API keys yet.</p>
      ) : (
        <div className="space-y-3">
          {keys.map(k => {
            const isRevealed = revealedKey === k.id && !!k.key;
            return (
              <div key={k.id} className="rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-3">
                <div className="flex items-center justify-between mb-1.5">
                  <p className="text-sm font-medium text-white">{k.name}</p>
                  <button onClick={() => revokeKey(k.id)} className="rounded-xl border border-white/[0.1] p-1.5 text-white/30 hover:text-red-400 transition-colors">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
                <div className="flex items-center gap-2">
                  <code className="flex-1 rounded-lg border border-white/[0.07] bg-white/[0.04] px-2 py-1 text-xs font-mono text-white/60 truncate">
                    {isRevealed ? k.key : `${k.key_prefix}••••••••••••••••••••`}
                  </code>
                  {k.key && (
                    <button onClick={() => setRevealedKey(isRevealed ? null : k.id)} className="text-white/30 hover:text-white/60 transition-colors flex-shrink-0">
                      {isRevealed ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                    </button>
                  )}
                </div>
                <p className="text-[11px] text-white/25 mt-1.5">Created {formatDate(k.created_at)} · Last used {formatDate(k.last_used_at)}</p>
              </div>
            );
          })}
        </div>
      )}

      <div className="mt-4 rounded-xl border border-amber-500/20 bg-amber-500/10 px-4 py-3">
        <div className="flex items-start gap-2">
          <AlertCircle className="h-4 w-4 text-amber-400 mt-0.5 flex-shrink-0" />
          <p className="text-xs text-amber-300/80">API keys are shown only at creation. Store them securely — they cannot be recovered.</p>
        </div>
      </div>
    </div>
  );
}

// ── Test Mode Tab ─────────────────────────────────────────────────────────────

type TestEmail = { id: string; email: string; label: string; enabled: boolean };
type TestModeConfig = { enabled: boolean; emails: TestEmail[] };

function TestModeTab() {
  const [config, setConfig] = useState<TestModeConfig>({ enabled: false, emails: [] });
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState(false);

  const [showAdd, setShowAdd] = useState(false);
  const [addEmail, setAddEmail] = useState('');
  const [addLabel, setAddLabel] = useState('');
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState('');

  async function load() {
    setLoading(true);
    try {
      const data = await api<TestModeConfig>({ method: 'GET', url: '/admin/test-mode' });
      setConfig(data ?? { enabled: false, emails: [] });
    } catch { setConfig({ enabled: false, emails: [] }); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  async function toggleGlobal() {
    setToggling(true);
    try {
      await api({ method: 'PATCH', url: '/admin/test-mode/toggle', data: { enabled: !config.enabled } });
      setConfig(c => ({ ...c, enabled: !c.enabled }));
    } catch {} finally { setToggling(false); }
  }

  async function toggleEmail(id: string, enabled: boolean) {
    await api({ method: 'PATCH', url: `/admin/test-mode/emails/${id}`, data: { enabled } });
    setConfig(c => ({ ...c, emails: c.emails.map(e => e.id === id ? { ...e, enabled } : e) }));
  }

  async function deleteEmail(id: string) {
    await api({ method: 'DELETE', url: `/admin/test-mode/emails/${id}` });
    setConfig(c => ({ ...c, emails: c.emails.filter(e => e.id !== id) }));
  }

  async function addTestEmail() {
    setAdding(true); setAddError('');
    try {
      const created = await api<TestEmail>({ method: 'POST', url: '/admin/test-mode/emails', data: { email: addEmail.trim(), label: addLabel.trim() } });
      setConfig(c => ({ ...c, emails: [...c.emails, created] }));
      setAddEmail(''); setAddLabel(''); setShowAdd(false);
    } catch (err: unknown) {
      const detail = (err as any)?.response?.data?.detail;
      setAddError(typeof detail === 'string' ? detail : 'Failed to add email.');
    } finally { setAdding(false); }
  }

  const [flushing, setFlushing] = useState(false);
  const [flushConfirm, setFlushConfirm] = useState(false);
  const [flushResult, setFlushResult] = useState<{ deleted: Record<string, number> } | null>(null);

  async function flushTestData() {
    setFlushing(true); setFlushResult(null);
    try {
      const result = await api<{ deleted: Record<string, number> }>({ method: 'POST', url: '/admin/test-mode/flush' });
      setFlushResult(result);
      setFlushConfirm(false);
    } catch {} finally { setFlushing(false); }
  }

  const enabledEmails = config.emails.filter(e => e.enabled);
  const inputCls = 'w-full rounded-xl border border-white/[0.1] bg-white/[0.05] px-3 py-2 text-sm text-white placeholder:text-white/20 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition';

  if (loading) return <div className="flex justify-center py-16"><Loader2 className="h-5 w-5 animate-spin text-white/30" /></div>;

  return (
    <div className="space-y-5">
      {/* ── Global toggle ── */}
      <div className="glass-card rounded-[24px] p-5">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-white flex items-center gap-2">
              <FlaskConical className="h-4 w-4 text-amber-400" />
              Test Mode
              {config.enabled && (
                <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold text-amber-400 border border-amber-500/20">ACTIVE</span>
              )}
            </h3>
            <p className="text-xs text-white/40 mt-1">
              When enabled, campaigns send to your configured test inboxes instead of real lead emails.
              Replies from test inboxes are routed back to the correct leads.
            </p>
          </div>
          <button
            onClick={toggleGlobal}
            disabled={toggling}
            className={cn(
              'relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none disabled:opacity-50',
              config.enabled ? 'bg-amber-500' : 'bg-white/10'
            )}
          >
            <span className={cn(
              'inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200',
              config.enabled ? 'translate-x-5' : 'translate-x-0'
            )} />
          </button>
        </div>

        {config.enabled && (
          <div className="mt-4 rounded-xl border border-amber-500/20 bg-amber-500/10 px-4 py-3">
            <p className="text-xs text-amber-300/80">
              <span className="font-semibold">Test mode is ON.</span> All new campaign emails will be sent to{' '}
              {enabledEmails.length === 0
                ? 'no test emails (enable at least one below)'
                : enabledEmails.length === 1
                  ? enabledEmails[0].email
                  : `${enabledEmails.length} enabled test inboxes in round-robin`}.
              {' '}Real lead emails are never contacted.
            </p>
          </div>
        )}
      </div>

      {/* ── Test email addresses ── */}
      <div className="glass-card rounded-[24px] p-5">
        <SectionHeader
          title="Test inboxes"
          description="Emails enabled here receive outreach on behalf of real leads. Replies route back automatically."
          action={
            <button onClick={() => { setShowAdd(v => !v); setAddError(''); }} className="flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 transition shadow-lg shadow-indigo-900/30">
              <Plus className="h-3.5 w-3.5" /> Add email
            </button>
          }
        />

        {showAdd && (
          <div className="mb-4 rounded-xl border border-indigo-500/30 bg-indigo-500/10 p-4 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-white/50 mb-1">Email address</label>
                <input type="email" className={inputCls} placeholder="you@gmail.com" value={addEmail} onChange={e => setAddEmail(e.target.value)} />
              </div>
              <div>
                <label className="block text-xs font-medium text-white/50 mb-1">Label (optional)</label>
                <input className={inputCls} placeholder="My Gmail" value={addLabel} onChange={e => setAddLabel(e.target.value)} />
              </div>
            </div>
            {addError && <p className="text-xs text-rose-400">{addError}</p>}
            <div className="flex gap-2">
              <button onClick={addTestEmail} disabled={adding || !addEmail.trim()} className="flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50 transition">
                {adding && <Loader2 className="h-3 w-3 animate-spin" />} Add
              </button>
              <button onClick={() => setShowAdd(false)} className="rounded-xl border border-white/[0.1] px-3 py-1.5 text-xs text-white/50 hover:bg-white/[0.05] transition">Cancel</button>
            </div>
          </div>
        )}

        {config.emails.length === 0 ? (
          <p className="py-8 text-center text-sm text-white/30">No test inboxes added yet.</p>
        ) : (
          <div className="space-y-2">
            {config.emails.map(e => (
              <div key={e.id} className={cn(
                'flex items-center gap-3 rounded-xl border px-4 py-3 transition-colors',
                e.enabled ? 'border-amber-500/20 bg-amber-500/5' : 'border-white/[0.07] bg-white/[0.02] opacity-60'
              )}>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-white truncate">{e.email}</p>
                  {e.label && <p className="text-xs text-white/40">{e.label}</p>}
                </div>
                <span className={cn(
                  'rounded-full px-2 py-0.5 text-[10px] font-semibold flex-shrink-0',
                  e.enabled ? 'bg-amber-500/20 text-amber-400' : 'bg-white/10 text-white/30'
                )}>
                  {e.enabled ? 'Enabled' : 'Disabled'}
                </span>
                {/* toggle */}
                <button
                  onClick={() => toggleEmail(e.id, !e.enabled)}
                  className={cn(
                    'relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200',
                    e.enabled ? 'bg-amber-500' : 'bg-white/10'
                  )}
                >
                  <span className={cn(
                    'inline-block h-4 w-4 transform rounded-full bg-white shadow transition duration-200',
                    e.enabled ? 'translate-x-4' : 'translate-x-0'
                  )} />
                </button>
                <button onClick={() => deleteEmail(e.id)} className="rounded-xl border border-white/[0.1] p-1.5 text-white/30 hover:text-red-400 transition-colors">
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── How it works ── */}
      <div className="glass-card rounded-[24px] p-5">
        <h3 className="text-sm font-semibold text-white mb-3">How it works</h3>
        <div className="space-y-3">
          {[
            { step: '1', text: 'Add your personal email addresses as test inboxes above and enable them.' },
            { step: '2', text: 'Enable Test Mode with the toggle. All new campaign sends are redirected.' },
            { step: '3', text: 'Leads are mapped to enabled test emails in round-robin (e.g. 3 leads + 2 emails → lead 1 & 3 go to inbox A, lead 2 goes to inbox B).' },
            { step: '4', text: 'You receive the outreach emails in your test inboxes exactly as a real lead would.' },
            { step: '5', text: 'Reply from any test inbox. The system detects the reply, matches it back to the real lead via subject line, and it appears in the Replies page as if the actual lead replied.' },
          ].map(({ step, text }) => (
            <div key={step} className="flex items-start gap-3">
              <span className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-indigo-500/20 text-[10px] font-bold text-indigo-400">{step}</span>
              <p className="text-xs text-white/50 leading-5">{text}</p>
            </div>
          ))}
        </div>
      </div>

      {/* ── Flush test data ── */}
      <div className="glass-card rounded-[24px] border-red-500/20 p-5">
        <SectionHeader
          title="Flush test data"
          description="Remove all messages, replies, email events, and follow-ups generated during test runs. Campaign leads are reset to pending so you can re-run."
        />

        {flushResult && (
          <div className="mb-4 rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-3">
            <p className="text-xs font-semibold text-emerald-400 mb-1">Flushed successfully</p>
            <div className="flex flex-wrap gap-3">
              {Object.entries(flushResult.deleted).map(([key, count]) => (
                <span key={key} className="text-xs text-white/50">
                  <span className="font-medium text-white/80">{count}</span> {key.replace(/_/g, ' ')}
                </span>
              ))}
            </div>
          </div>
        )}

        {!flushConfirm ? (
          <button
            onClick={() => { setFlushConfirm(true); setFlushResult(null); }}
            className="rounded-xl border border-red-500/30 px-4 py-2 text-xs font-medium text-red-400 hover:bg-red-500/10 transition-colors"
          >
            Flush test data
          </button>
        ) : (
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 space-y-3">
            <p className="text-sm font-semibold text-white">Are you sure?</p>
            <p className="text-xs text-white/50">
              This will permanently delete all messages, replies, and events sent during test runs,
              and reset all campaign leads with a test override back to pending.
              This cannot be undone.
            </p>
            <div className="flex gap-2">
              <button
                onClick={flushTestData}
                disabled={flushing}
                className="flex items-center gap-1.5 rounded-xl bg-red-600 px-4 py-2 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50 transition"
              >
                {flushing && <Loader2 className="h-3 w-3 animate-spin" />}
                {flushing ? 'Flushing…' : 'Yes, flush it'}
              </button>
              <button
                onClick={() => setFlushConfirm(false)}
                className="rounded-xl border border-white/[0.1] px-4 py-2 text-xs text-white/50 hover:bg-white/[0.05] transition"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

type ActivityEntry = {
  id: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  user_agent: string | null;
  user_email: string;
  created_at: string;
};

const ACTION_META: Record<string, { label: string; icon: React.ElementType; color: string }> = {
  'user.login':          { label: 'Signed in',               icon: User,      color: 'bg-indigo-500/20 text-indigo-400' },
  'leads.import':        { label: 'Imported leads sheet',    icon: Upload,    color: 'bg-cyan-500/20 text-cyan-400' },
  'leads.enrich':        { label: 'Triggered enrichment',    icon: Zap,       color: 'bg-amber-500/20 text-amber-400' },
  'campaign.create':     { label: 'Created campaign',        icon: UserPlus,  color: 'bg-violet-500/20 text-violet-400' },
  'campaign.launch':     { label: 'Launched campaign',       icon: Play,      color: 'bg-emerald-500/20 text-emerald-400' },
  'campaign.pause':      { label: 'Paused campaign',         icon: Pause,     color: 'bg-orange-500/20 text-orange-400' },
  'campaign.resume':     { label: 'Resumed campaign',        icon: RotateCcw, color: 'bg-teal-500/20 text-teal-400' },
  'campaign.add_leads':  { label: 'Added leads to campaign', icon: UserPlus,  color: 'bg-blue-500/20 text-blue-400' },
};

function formatTs(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const diff = Math.floor((Date.now() - d.getTime()) / 1000);
  if (diff < 60) return 'Just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function detailLine(entry: ActivityEntry): string {
  const d = entry.details;
  if (entry.action === 'user.login') {
    const ip = entry.ip_address ?? (d?.ip as string) ?? '';
    return ip ? `from ${ip}` : '';
  }
  if (!d) return '';
  if (entry.action === 'leads.import') return `${d.file_name ?? ''}${d.rows_imported != null ? ` · ${d.rows_imported} rows` : ''}`;
  if (entry.action === 'leads.enrich') return `${d.lead_count ?? ''} leads`;
  if (entry.action === 'campaign.add_leads') return `${d.leads_added ?? ''} leads added`;
  if (d.name) return String(d.name);
  return '';
}

function ActivityTab() {
  const [entries, setEntries] = useState<ActivityEntry[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const res = await api<ActivityEntry[]>({ method: 'GET', url: '/admin/activity', params: { limit: 100 } });
      setEntries(Array.isArray(res) ? res : (res as any)?.data ?? []);
    } catch {
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  return (
    <div className="glass-card rounded-[24px] p-5">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h3 className="text-sm font-semibold text-white">Activity log</h3>
          <p className="text-xs text-white/40 mt-0.5">All actions performed by users in this workspace</p>
        </div>
        <button onClick={load} className="flex items-center gap-1.5 rounded-xl border border-white/[0.1] px-3 py-1.5 text-xs font-medium text-white/60 hover:bg-white/[0.05] transition-colors">
          <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} /> Refresh
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16 text-white/30">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      ) : entries.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-white/20">
          <Activity className="h-8 w-8 mb-3 opacity-40" />
          <p className="text-sm">No activity recorded yet</p>
          <p className="text-xs mt-1">Actions like imports, enrichments, and campaign launches will appear here</p>
        </div>
      ) : (
        <div className="space-y-2">
          {entries.map((entry) => {
            const meta = ACTION_META[entry.action] ?? { label: entry.action, icon: Activity, color: 'bg-white/10 text-white/50' };
            const Icon = meta.icon;
            const detail = detailLine(entry);
            const emailPrefix = entry.user_email.split('@')[0].replace(/[._-]/g, ' ').toUpperCase();
            return (
              <div key={entry.id} className="flex items-start gap-3 rounded-xl border border-white/[0.06] px-4 py-3 hover:bg-white/[0.03] transition-colors">
                <div className={cn('mt-0.5 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full', meta.color)}>
                  <Icon className="h-3.5 w-3.5" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-white">{meta.label}</p>
                  {detail && <p className="text-xs text-white/40 mt-0.5 truncate">{detail}</p>}
                </div>
                <div className="text-right flex-shrink-0">
                  <p className="text-xs font-semibold text-white/60">{emailPrefix}</p>
                  <p className="text-[11px] text-white/25 mt-0.5">{formatTs(entry.created_at)}</p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState('account');

  const renderTab = () => {
    switch (activeTab) {
      case 'account': return <AccountTab />;
      case 'email': return <EmailTab />;
      case 'team': return <TeamTab />;
      case 'ai': return <AITab />;
      case 'api': return <APITab />;
      case 'testmode': return <TestModeTab />;
      case 'activity': return <ActivityTab />;
      default: return null;
    }
  };

  return (
    <div className="space-y-5">
      <section
        className="relative overflow-hidden rounded-2xl p-6 lg:p-7"
        style={{
          background: 'linear-gradient(135deg, #0d2540 0%, #09131f 55%, #1c4d73 100%)',
          boxShadow: '0 8px 32px rgba(13,37,64,0.18)',
        }}
      >
        <div className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full bg-white/3" />
        <p className="text-[10px] font-bold uppercase tracking-widest mb-2" style={{ color: 'rgba(255,255,255,0.35)' }}>Workspace controls</p>
        <h1 className="text-[1.65rem] font-extrabold tracking-tight text-white leading-tight sm:text-[2rem]">Keep the operating system, not just the profile, in good shape.</h1>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed" style={{ color: 'rgba(255,255,255,0.50)' }}>Manage senders, AI defaults, permissions, and keys from a single control surface built for operators instead of forms piled on forms.</p>
      </section>

      <div className="flex flex-col gap-6 lg:flex-row">
        <div className="w-full flex-shrink-0 lg:w-56">
          <nav className="glass-card space-y-1 rounded-[28px] p-3">
            {TABS.map(tab => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    'flex w-full items-center gap-2.5 rounded-[20px] px-3 py-3 text-left text-sm transition-colors',
                    activeTab === tab.id
                      ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-900/40'
                      : 'text-white/50 hover:bg-white/[0.05] hover:text-white'
                  )}
                >
                  <Icon className="h-4 w-4 flex-shrink-0" />
                  {tab.label}
                </button>
              );
            })}
          </nav>
        </div>

        <div className="min-w-0 flex-1">{renderTab()}</div>
      </div>
    </div>
  );
}
