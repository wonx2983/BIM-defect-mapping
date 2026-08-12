'use client';

import { Search, Bell } from 'lucide-react';
import styles from './Topbar.module.css';

interface TopbarProps {
  title: string;
}

export default function Topbar({ title }: TopbarProps) {
  return (
    <header className={styles.topbar}>
      <h1 className={styles.title}>{title}</h1>

      <div className={styles.actions}>
        <div className={styles.searchBox}>
          <Search size={14} strokeWidth={1.5} className={styles.searchIcon} />
          <input
            className={styles.searchInput}
            type="text"
            placeholder="Search..."
            aria-label="Search"
          />
          <kbd className={styles.shortcutHint}>⌘K</kbd>
        </div>

        <button className={styles.notifBtn} aria-label="Notifications">
          <Bell size={18} strokeWidth={1.5} />
        </button>
      </div>
    </header>
  );
}
