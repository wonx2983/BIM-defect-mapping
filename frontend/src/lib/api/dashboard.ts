import { api } from '@/lib/api';

export interface DashboardStats {
  stats: {
    total_projects: number;
    active_defects: number;
    critical_alerts: number;
    total_inspections: number;
    resolved_this_week: number;
  };
  severity_distribution: {
    low: number;
    medium: number;
    high: number;
    critical: number;
  };
  trend_data: Array<{
    month: string;
    year: number;
    defects: number;
  }>;
  recent_activity: Array<{
    text: string;
    time: string;
    severity: string;
    defect_id: string;
  }>;
  class_distribution: Record<string, number>;
}

export async function getDashboardStats(): Promise<DashboardStats> {
  return api.get<DashboardStats>('/api/v1/dashboard/stats');
}
