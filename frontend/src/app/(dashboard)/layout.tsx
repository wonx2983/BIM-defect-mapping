'use client';

import { useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import Sidebar from '@/components/ui/Sidebar';
import Topbar from '@/components/ui/Topbar';
import { useAuthStore } from '@/stores/authStore';

const PAGE_TITLES: Record<string, string> = {
  '/': 'Dashboard',
  '/projects': 'Projects',
  '/detect': 'Defect Detection',
  '/viewer': 'BIM Viewer',
  '/reports': 'Reports & Analytics',
  '/settings': 'Settings',
};

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { isAuthenticated, loadUser } = useAuthStore();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const token = localStorage.getItem('access_token');
    if (!token) {
      router.push('/login');
    } else {
      loadUser();
    }
  }, [router, loadUser]);

  if (!mounted) return null;

  const title =
    PAGE_TITLES[pathname] ||
    Object.entries(PAGE_TITLES).find(([k]) => k !== '/' && pathname.startsWith(k))?.[1] ||
    'DefectSync';

  return (
    <div>
      <Sidebar />
      <Topbar title={title} />
      <main
        style={{
          marginLeft: 'var(--sidebar-width)',
          marginTop: 'var(--topbar-height)',
          padding: 'var(--space-xl)',
          minHeight: 'calc(100vh - var(--topbar-height))',
          transition: 'margin-left 300ms cubic-bezier(0.4, 0, 0.2, 1)',
        }}
      >
        {children}
      </main>
    </div>
  );
}
