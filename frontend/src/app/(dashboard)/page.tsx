'use client';

import Link from 'next/link';
import { PieChart, Pie, Cell, ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import styles from './dashboard.module.css';

const SEVERITY_DATA = [
  { name: 'Low', value: 18, color: 'hsl(142, 71%, 45%)' },
  { name: 'Medium', value: 15, color: 'hsl(45, 93%, 47%)' },
  { name: 'High', value: 11, color: 'hsl(25, 95%, 53%)' },
  { name: 'Critical', value: 3, color: 'hsl(0, 84%, 60%)' },
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
  { text: 'Critical crack detected in Building A - 3rd Floor', time: '2 min ago', color: 'hsl(0, 84%, 60%)' },
  { text: 'Defect #42 resolved by John Doe', time: '15 min ago', color: 'hsl(142, 71%, 45%)' },
  { text: 'New inspection started: North Wing Survey', time: '1 hour ago', color: 'hsl(210, 100%, 56%)' },
  { text: 'BIM model updated: Tower B Foundation', time: '3 hours ago', color: 'hsl(280, 67%, 55%)' },
  { text: 'Report generated: Weekly Summary', time: '5 hours ago', color: 'hsl(45, 93%, 47%)' },
];

export default function DashboardPage() {
  const total = SEVERITY_DATA.reduce((sum, d) => sum + d.value, 0);

  return (
    <div className={styles.grid}>
      {/* Stats Row */}
      <div className={styles.statsRow}>
        <div className={styles.statCard}>
          <div className={styles.statHeader}>
            <span className={styles.statIcon}>📁</span>
            <span className={styles.statLabel}>Total Projects</span>
          </div>
          <div className={styles.statValue}>12</div>
          <div className={styles.statTrend}>+3 this month</div>
        </div>

        <div className={styles.statCard}>
          <div className={styles.statHeader}>
            <span className={styles.statIcon}>🔍</span>
            <span className={styles.statLabel}>Active Defects</span>
          </div>
          <div className={styles.statValue}>47</div>
          <div className={styles.statTrend}>-5 resolved this week</div>
        </div>

        <div className={styles.statCard}>
          <div className={styles.statHeader}>
            <span className={styles.statIcon}>🚨</span>
            <span className={styles.statLabel}>Critical Alerts</span>
          </div>
          <div className={`${styles.statValue} ${styles.statPulse}`}>3</div>
          <div className={`${styles.statTrend} ${styles.negative}`}>Requires attention</div>
        </div>

        <div className={styles.statCard}>
          <div className={styles.statHeader}>
            <span className={styles.statIcon}>📋</span>
            <span className={styles.statLabel}>Inspections</span>
          </div>
          <div className={styles.statValue}>28</div>
          <div className={styles.statTrend}>+8 this month</div>
        </div>
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
                paddingAngle={4}
                dataKey="value"
                strokeWidth={0}
              >
                {SEVERITY_DATA.map((entry, index) => (
                  <Cell key={index} fill={entry.color} />
                ))}
              </Pie>
              <text x="50%" y="48%" textAnchor="middle" fill="hsl(210, 40%, 98%)" fontSize="28" fontWeight="700">
                {total}
              </text>
              <text x="50%" y="60%" textAnchor="middle" fill="hsl(215, 20%, 65%)" fontSize="12">
                Total Defects
              </text>
            </PieChart>
          </ResponsiveContainer>
          <div style={{ display: 'flex', justifyContent: 'center', gap: '16px', marginTop: '8px' }}>
            {SEVERITY_DATA.map((d) => (
              <div key={d.name} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
                <div style={{ width: 8, height: 8, borderRadius: '50%', background: d.color }} />
                <span style={{ color: 'hsl(215, 20%, 65%)' }}>{d.name}: {d.value}</span>
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
                  <stop offset="0%" stopColor="hsl(210, 100%, 56%)" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="hsl(210, 100%, 56%)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(217, 33%, 17%)" />
              <XAxis dataKey="month" stroke="hsl(215, 20%, 45%)" fontSize={12} tickLine={false} />
              <YAxis stroke="hsl(215, 20%, 45%)" fontSize={12} tickLine={false} />
              <Tooltip
                contentStyle={{
                  background: 'hsl(222, 47%, 11%)',
                  border: '1px solid hsl(217, 33%, 17%)',
                  borderRadius: '10px',
                  color: 'hsl(210, 40%, 98%)',
                  fontSize: '13px',
                }}
              />
              <Area
                type="monotone"
                dataKey="defects"
                stroke="hsl(210, 100%, 56%)"
                strokeWidth={2}
                fill="url(#colorDefects)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Quick Actions */}
      <div className={styles.actionsRow}>
        <Link href="/detect" className={styles.actionCard}>
          <div className={styles.actionIcon}>🔍</div>
          <div className={styles.actionLabel}>New Inspection</div>
          <div className={styles.actionDesc}>Upload images and detect defects</div>
        </Link>
        <Link href="/detect" className={styles.actionCard}>
          <div className={styles.actionIcon}>📷</div>
          <div className={styles.actionLabel}>Upload Images</div>
          <div className={styles.actionDesc}>Batch process site photographs</div>
        </Link>
        <Link href="/viewer" className={styles.actionCard}>
          <div className={styles.actionIcon}>🏗️</div>
          <div className={styles.actionLabel}>Open BIM Viewer</div>
          <div className={styles.actionDesc}>View 3D model with defect markers</div>
        </Link>
      </div>

      {/* Recent Activity */}
      <div className={styles.activityCard}>
        <h3 className={styles.chartTitle}>Recent Activity</h3>
        {ACTIVITIES.map((item, i) => (
          <div key={i} className={styles.activityItem}>
            <div className={styles.activityDot} style={{ background: item.color }} />
            <span className={styles.activityText}>{item.text}</span>
            <span className={styles.activityTime}>{item.time}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
