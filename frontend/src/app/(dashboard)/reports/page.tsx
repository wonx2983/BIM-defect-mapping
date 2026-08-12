import { FileBarChart } from 'lucide-react';

export default function ReportsPage() {
  return (
    <div className="empty-state">
      <div className="empty-state-icon"><FileBarChart size={32} strokeWidth={1.5} /></div>
      <h2 className="empty-state-title">Reports &amp; Analytics</h2>
      <p className="empty-state-description">
        Generate professional inspection reports, severity analyses, and exportable
        BCF files for BIM collaboration. Coming in Phase 4.
      </p>
      <button className="btn btn-primary" disabled>
        Generate Report
      </button>
    </div>
  );
}
