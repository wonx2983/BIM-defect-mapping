'use client';

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
          <span className={styles.searchIcon}>🔎</span>
          <input
            className={styles.searchInput}
            type="text"
            placeholder="Search..."
            aria-label="Search"
          />
          <span className={styles.shortcutHint}>⌘K</span>
        </div>

        <button className={styles.notifBtn} aria-label="Notifications">
          🔔
          <span className={styles.notifDot} />
        </button>
      </div>
    </header>
  );
}
