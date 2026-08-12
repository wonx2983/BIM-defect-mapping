'use client';

import Link from 'next/link';
import { PieChart, Pie, Cell, ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import { FolderKanban, ScanSearch, AlertTriangle, ClipboardList, ArrowUpRight, Box, Upload } from 'lucide-react';
import styles from './dashboard.module.css';

const SEVERITY_DATA = [
  { name: 'Low', value: 18, color: 'hsl(152, 30%, 45%)' },
  { name: 'Medium', value: 15, color: 'hsl(40, 45%, 48%)' },
  { name: 'High', value: 11, color: 'hsl(25, 50%, 48%)' },
  { name: 'Critical', value: 3, color: 'hsl(0, 45%, 50%)' },
];

const TREND_DATA = [
  { month: 'Feb', defects: 12 },
  { month: 'Mar', defects: 19 },
  { month: 'Apr', defects: 15 },
  { month: 'May', defects: 28 },
  { month: 'Jun', defects: 35 },
  { month: 'Jul', defects: 42 },
  { month: 'Aug', defects: 47 },
];

const ACTIVITIES = [
  { text: 'Critical crack detected in Building A — 3rd Floor', time: '2 min ago', severity: 'critical' },
  { text: 'Defect #42 resolved by John Doe', time: '15 min ago', severity: 'resolved' },
  { text: 'New inspection started: North Wing Survey', time: '1 hour ago', severity: 'info' },
  { text: 'BIM model updated: Tower B Foundation', time: '3 hours ago', severity: 'info' },
  { text: 'Report generated: Weekly Summary', time: '5 hours ago', severity: 'info' },
];

const STAT_CARDS = [
  { icon: FolderKanban, label: 'Total Projects', value: '12', trend: '+3 this month', positive: true },
  { icon: ScanSearch, label: 'Active Defects', value: '47', trend: '-5 resolved this week', positive: true },
  { icon: AlertTriangle, label: 'Critical Alerts', value: '3', trend: 'Requires attention', positive: false },
  { icon: ClipboardList, label: 'Inspections', value: '28', trend: '+8 this month', positive: true },
];

export default function DashboardPage() {
  const total = SEVERITY_DATA.reduce((sum, d) => sum + d.value, 0);

  return (
    <div className={styles.grid}>
      {/* Stats Row */}
      <div className={styles.statsRow}>
        {STAT_CARDS.map((stat) => {
          const Icon = stat.icon;
          return (
            <div key={stat.label} className={styles.statCard}>
              <div className={styles.statHeader}>
                <Icon size={16} strokeWidth={1.5} className={styles.statIconSvg} />
                <span className={styles.statLabel}>{stat.label}</span>
              </div>
              <div className={`${styles.statValue} ${!stat.positive && stat.label === 'Critical Alerts' ? styles.statPulse : ''}`}>
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
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie
                data={SEVERITY_DATA}
                cx="50%"
                cy="50%"
                innerRadius={65}
                outerRadius={95}
                paddingAngle={3}
                dataKey="value"
                strokeWidth={0}
              >
                {SEVERITY_DATA.map((entry, index) => (
                  <Cell key={index} fill={entry.color} />
                ))}
              </Pie>
              <text x="50%" y="48%" textAnchor="middle" fill="hsl(0, 0%, 93%)" fontSize="24" fontWeight="600">
                {total}
              </text>
              <text x="50%" y="60%" textAnchor="middle" fill="hsl(0, 0%, 44%)" fontSize="11">
                Total Defects
              </text>
            </PieChart>
          </ResponsiveContainer>
          <div style={{ display: 'flex', justifyContent: 'center', gap: '16px', marginTop: '8px' }}>
            {SEVERITY_DATA.map((d) => (
              <div key={d.name} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px' }}>
                <div style={{ width: 6, height: 6, borderRadius: '50%', background: d.color }} />
                <span style={{ color: 'hsl(0, 0%, 44%)' }}>{d.name}: {d.value}</span>
              </div>
            ))}
          </div>
        </div>

        <div className={styles.chartCard}>
          <h3 className={styles.chartTitle}>Defects Over Time</h3>
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={TREND_DATA}>
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
        <Link href="/detect" className={styles.actionCard}>
          <Upload size={24} strokeWidth={1.5} className={styles.actionIconSvg} />
          <div className={styles.actionLabel}>Upload Images</div>
          <div className={styles.actionDesc}>Batch process site photographs</div>
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
        {ACTIVITIES.map((item, i) => (
          <div key={i} className={styles.activityItem}>
            <div className={`${styles.activityDot} ${styles[`dot_${item.severity}`]}`} />
            <span className={styles.activityText}>{item.text}</span>
            <span className={styles.activityTime}>{item.time}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
