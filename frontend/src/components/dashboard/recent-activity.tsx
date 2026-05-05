'use client';

import { useEffect, useState } from 'react';
import { Mail, UserPlus, Zap, MessageSquare, TrendingUp, CheckCircle2 } from 'lucide-react';
import { api } from '@/lib/api-client';

interface ActivityItem {
  id: string;
  type: string;
  title: string;
  description: string | null;
  time: string;
}

const typeConfig: Record<string, { icon: React.ElementType; iconBg: string; iconColor: string; dot: string }> = {
  import:      { icon: UserPlus,      iconBg: 'bg-violet-500/20', iconColor: 'text-violet-400', dot: 'bg-violet-500' },
  enrichment:  { icon: Zap,           iconBg: 'bg-amber-500/20',  iconColor: 'text-amber-400',  dot: 'bg-amber-500' },
  scoring:     { icon: TrendingUp,    iconBg: 'bg-orange-500/20', iconColor: 'text-orange-400', dot: 'bg-orange-500' },
  email:       { icon: Mail,          iconBg: 'bg-cyan-500/20',   iconColor: 'text-cyan-400',   dot: 'bg-cyan-500' },
  email_sent:  { icon: Mail,          iconBg: 'bg-cyan-500/20',   iconColor: 'text-cyan-400',   dot: 'bg-cyan-500' },
  reply:       { icon: MessageSquare, iconBg: 'bg-emerald-500/20',iconColor: 'text-emerald-400',dot: 'bg-emerald-500' },
  conversion:  { icon: CheckCircle2,  iconBg: 'bg-emerald-500/20',iconColor: 'text-emerald-400',dot: 'bg-emerald-500' },
};

const fallback = typeConfig.import;

export function RecentActivity() {
  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<ActivityItem[]>({ method: 'GET', url: '/analytics/recent-activity', params: { limit: 8 } })
      .then(setActivities)
      .catch(() => setActivities([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="glass-card rounded-[28px] overflow-hidden">
      <div className="px-5 py-4 border-b border-white/[0.06]">
        <h3 className="text-sm font-semibold text-white">Recent Activity</h3>
        <p className="text-xs text-white/40 mt-0.5">Live feed of platform events</p>
      </div>

      <div className="px-5 py-3">
        {loading ? (
          [...Array(5)].map((_, i) => (
            <div key={i} className="flex items-start gap-3 pb-4">
              <div className="mt-1 h-7 w-7 rounded-lg bg-white/10 animate-pulse flex-shrink-0" />
              <div className="flex-1 space-y-1.5 pt-1">
                <div className="h-3 w-3/4 rounded bg-white/10 animate-pulse" />
                <div className="h-2.5 w-1/4 rounded bg-white/10 animate-pulse" />
              </div>
            </div>
          ))
        ) : activities.length === 0 ? (
          <p className="py-6 text-center text-sm text-white/40">No activity yet</p>
        ) : (
          activities.map((activity, idx) => {
            const cfg = typeConfig[activity.type] ?? fallback;
            const Icon = cfg.icon;
            return (
              <div key={activity.id} className="flex items-start gap-3 relative">
                {idx < activities.length - 1 && (
                  <div className="absolute left-[15px] top-8 bottom-0 w-px bg-white/[0.06] z-0" />
                )}
                <div className={`relative z-10 mt-1 flex-shrink-0 rounded-lg p-1.5 ${cfg.iconBg}`}>
                  <Icon className={`h-3.5 w-3.5 ${cfg.iconColor}`} />
                </div>
                <div className="flex-1 min-w-0 pb-4">
                  <p className="text-xs text-white/80 leading-snug pr-2">{activity.title}</p>
                  {activity.description && (
                    <p className="text-[11px] text-white/40 mt-0.5 line-clamp-1">{activity.description}</p>
                  )}
                  <div className="flex items-center gap-1.5 mt-1">
                    <span className={`h-1.5 w-1.5 rounded-full flex-shrink-0 ${cfg.dot}`} />
                    <span className="text-[11px] text-white/30">{activity.time}</span>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

