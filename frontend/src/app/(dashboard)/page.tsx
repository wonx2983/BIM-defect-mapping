'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { PieChart, Pie, Cell, ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import { FolderKanban, ScanSearch, AlertTriangle, ClipboardList, ArrowUpRight, Box, Upload, Video } from 'lucide-react';
import { getDashboardStats, type DashboardStats } from '@/lib/api/dashboard';
import styles from './dashboard.module.css';

const SEVERITY_COLORS: Record<string, string> = {
  low: 'hsl(152, 30%, 45%)',
  medium: 'hsl(40, 45%, 48%)',
  high: 'hsl(25, 50%, 48%)',
  critical: 'hsl(0, 45%, 50%)',
};

export default function DashboardPage() {
  const [data, setData] = useState<DashboardStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let mounted = true;
    getDashboardStats()
      .then((stats) => { if (mounted) setData(stats); })
      .catch((err) => { if (mounted) setError(err.message || 'Failed to load dashboard'); })
      .finally(() => { if (mounted) setIsLoading(false); });
    return () => { mounted = false; };
  }, []);

  if (isLoading) {
    return (
      <div className={styles.grid}>
        <div className={styles.statsRow}>
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="skeleton skeleton-card" style={{ height: 110 }} />
          ))}
        </div>
        <div className={styles.chartsRow}>
          <div className="skeleton skeleton-card" style={{ height: 340 }} />
          <div className="skeleton skeleton-card" style={{ height: 340 }} />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">⚠️</div>
        <h2 className="empty-state-title">Failed to load dashboard</h2>
        <p className="empty-state-description">{error}</p>
      </div>
    );
  }

  const stats = data!;
  const severityData = Object.entries(stats.severity_distribution)
    .map(([name, value]) => ({
      name: name.charAt(0).toUpperCase() + name.slice(1),
      value,
      color: SEVERITY_COLORS[name] || 'hsl(0, 0%, 30%)',
    }))
    .filter((d) => d.value > 0);

  const totalDefects = severityData.reduce((sum, d) => sum + d.value, 0);

  const statCards = [
    {
      icon: FolderKanban,
      label: 'Total Projects',
      value: String(stats.stats.total_projects),
      trend: stats.stats.total_projects === 0 ? 'Create your first project' : `${stats.stats.total_projects} active`,
      positive: true,
    },
    {
      icon: ScanSearch,
      label: 'Active Defects',
      value: String(stats.stats.active_defects),
      trend: stats.stats.resolved_this_week > 0
        ? `${stats.stats.resolved_this_week} resolved this week`
        : 'No defects resolved this week',
      positive: stats.stats.resolved_this_week > 0,
    },
    {
      icon: AlertTriangle,
      label: 'Critical Alerts',
      value: String(stats.stats.critical_alerts),
      trend: stats.stats.critical_alerts > 0 ? 'Requires attention' : 'All clear',
      positive: stats.stats.critical_alerts === 0,
    },
    {
      icon: ClipboardList,
      label: 'Inspections',
      value: String(stats.stats.total_inspections),
      trend: stats.stats.total_inspections === 0
        ? 'Run your first inspection'
        : `${stats.stats.total_inspections} completed`,
      positive: true,
    },
  ];

  const hasNoData = totalDefects === 0 && stats.stats.total_projects === 0;

  return (
    <div className={styles.grid}>
      {/* Stats Row */}
      <div className={styles.statsRow}>
        {statCards.map((stat) => {
          const Icon = stat.icon;
          return (
            <div key={stat.label} className={styles.statCard}>
              <div className={styles.statHeader}>
                <Icon size={16} strokeWidth={1.5} className={styles.statIconSvg} />
                <span className={styles.statLabel}>{stat.label}</span>
              </div>
              <div className={`${styles.statValue} ${!stat.positive && stat.label === 'Critical Alerts' && stats.stats.critical_alerts > 0 ? styles.statPulse : ''}`}>
                {stat.value}
              </div>
              <div className={`${styles.statTrend} ${!stat.positive ? styles.negative : ''}`}>
                {stat.trend}
              </div>
            </div>
          );
        })}
      </div>

      {/* Charts Row */}
      <div className={styles.chartsRow}>
        <div className={styles.chartCard}>
          <h3 className={styles.chartTitle}>Severity Distribution</h3>
          {totalDefects === 0 ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 250, color: 'hsl(0, 0%, 44%)', fontSize: '13px' }}>
              No defects detected yet — run an inspection to see data here
            </div>
          ) : (
            <>
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie
                    data={severityData}
                    cx="50%"
                    cy="50%"
                    innerRadius={65}
                    outerRadius={95}
                    paddingAngle={3}
                    dataKey="value"
                    strokeWidth={0}
                  >
                    {severityData.map((entry, index) => (
                      <Cell key={index} fill={entry.color} />
                    ))}
                  </Pie>
                  <text x="50%" y="48%" textAnchor="middle" fill="hsl(0, 0%, 93%)" fontSize="24" fontWeight="600">
                    {totalDefects}
                  </text>
                  <text x="50%" y="60%" textAnchor="middle" fill="hsl(0, 0%, 44%)" fontSize="11">
                    Total Defects
                  </text>
                </PieChart>
              </ResponsiveContainer>
              <div style={{ display: 'flex', justifyContent: 'center', gap: '16px', marginTop: '8px' }}>
                {severityData.map((d) => (
                  <div key={d.name} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px' }}>
                    <div style={{ width: 6, height: 6, borderRadius: '50%', background: d.color }} />
                    <span style={{ color: 'hsl(0, 0%, 44%)' }}>{d.name}: {d.value}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        <div className={styles.chartCard}>
          <h3 className={styles.chartTitle}>Defects Over Time</h3>
          {stats.trend_data.length === 0 ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 280, color: 'hsl(0, 0%, 44%)', fontSize: '13px' }}>
              Trend data will appear as you detect defects over time
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={stats.trend_data}>
                <defs>
                  <linearGradient id="colorDefects" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="hsl(0, 0%, 44%)" stopOpacity={0.15} />
                    <stop offset="100%" stopColor="hsl(0, 0%, 44%)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(0, 0%, 15%)" />
                <XAxis dataKey="month" stroke="hsl(0, 0%, 30%)" fontSize={11} tickLine={false} />
                <YAxis stroke="hsl(0, 0%, 30%)" fontSize={11} tickLine={false} />
                <Tooltip
                  contentStyle={{
                    background: 'hsl(0, 0%, 9%)',
                    border: '1px solid hsl(0, 0%, 15%)',
                    borderRadius: '8px',
                    color: 'hsl(0, 0%, 93%)',
                    fontSize: '12px',
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="defects"
                  stroke="hsl(0, 0%, 50%)"
                  strokeWidth={1.5}
                  fill="url(#colorDefects)"
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Quick Actions */}
      <div className={styles.actionsRow}>
        <Link href="/detect" className={styles.actionCard}>
          <ScanSearch size={24} strokeWidth={1.5} className={styles.actionIconSvg} />
          <div className={styles.actionLabel}>New Inspection</div>
          <div className={styles.actionDesc}>Upload images and detect defects</div>
          <ArrowUpRight size={14} className={styles.actionArrow} />
        </Link>
        <Link href="/video" className={styles.actionCard}>
          <Video size={24} strokeWidth={1.5} className={styles.actionIconSvg} />
          <div className={styles.actionLabel}>Video Detection</div>
          <div className={styles.actionDesc}>Analyze video feeds and CCTV streams</div>
          <ArrowUpRight size={14} className={styles.actionArrow} />
        </Link>
        <Link href="/viewer" className={styles.actionCard}>
          <Box size={24} strokeWidth={1.5} className={styles.actionIconSvg} />
          <div className={styles.actionLabel}>Open BIM Viewer</div>
          <div className={styles.actionDesc}>View 3D model with defect markers</div>
          <ArrowUpRight size={14} className={styles.actionArrow} />
        </Link>
      </div>

      {/* Recent Activity */}
      <div className={styles.activityCard}>
        <h3 className={styles.chartTitle}>Recent Activity</h3>
        {stats.recent_activity.length === 0 ? (
          <div style={{ padding: '24px 0', textAlign: 'center', color: 'hsl(0, 0%, 44%)', fontSize: '13px' }}>
            No activity yet — detect defects to see your activity feed here
          </div>
        ) : (
          stats.recent_activity.map((item, i) => (
            <div key={i} className={styles.activityItem}>
              <div className={`${styles.activityDot} ${styles[`dot_${item.severity}`]}`} />
              <span className={styles.activityText}>{item.text}</span>
              <span className={styles.activityTime}>{item.time}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
