'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useAuthStore } from '@/stores/authStore';
import styles from './Sidebar.module.css';

const NAV_ITEMS = [
  { icon: '📊', label: 'Dashboard', path: '/' },
  { icon: '📁', label: 'Projects', path: '/projects' },
  { icon: '🔍', label: 'Detection', path: '/detect' },
  { icon: '🏗️', label: 'BIM Viewer', path: '/viewer' },
  { icon: '📄', label: 'Reports', path: '/reports' },
  { icon: '⚙️', label: 'Settings', path: '/settings' },
];

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuthStore();

  const handleLogout = () => {
    logout();
    router.push('/login');
  };

  const initials = user?.full_name
    ?.split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2) || 'U';

  return (
    <aside className={`${styles.sidebar} ${collapsed ? styles.collapsed : ''}`}>
      <button
        className={styles.toggleBtn}
        onClick={() => setCollapsed(!collapsed)}
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        {collapsed ? '→' : '←'}
      </button>

      <div className={styles.logo}>
        <div className={styles.logoIcon}>DS</div>
        <span className={styles.logoText}>DefectSync</span>
      </div>

      <nav className={styles.nav}>
        {NAV_ITEMS.map((item) => {
          const isActive =
            item.path === '/'
              ? pathname === '/'
              : pathname.startsWith(item.path);
          return (
            <Link
              key={item.path}
              href={item.path}
              className={`${styles.navItem} ${isActive ? styles.active : ''}`}
            >
              <span className={styles.navIcon}>{item.icon}</span>
              <span className={styles.navLabel}>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className={styles.userSection}>
        <div className={styles.avatar}>{initials}</div>
        <div className={styles.userInfo}>
          <div className={styles.userName}>{user?.full_name || 'User'}</div>
          <div className={styles.userRole}>{user?.role || 'inspector'}</div>
        </div>
        <button className={styles.logoutBtn} onClick={handleLogout} title="Logout">
          ⏻
        </button>
      </div>
    </aside>
  );
}
