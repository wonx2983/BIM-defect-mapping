'use client';

import { useState } from 'react';
import Modal from '@/components/ui/Modal';
import styles from './projects.module.css';

const MOCK_PROJECTS = [
  {
    id: '1', name: 'Highway Bridge Retrofit', address: 'NH-48, Sector 14, Gurgaon',
    status: 'active', defect_count: 23, bim_model_count: 2,
    severity: { low: 8, medium: 9, high: 4, critical: 2 },
    updated_at: '2026-08-09T10:30:00Z',
  },
  {
    id: '2', name: 'Metro Station Phase 2', address: 'Huda City Centre, Delhi NCR',
    status: 'active', defect_count: 15, bim_model_count: 1,
    severity: { low: 6, medium: 5, high: 3, critical: 1 },
    updated_at: '2026-08-08T14:00:00Z',
  },
  {
    id: '3', name: 'Residential Tower C', address: 'Noida Expressway, Sector 150',
    status: 'active', defect_count: 8, bim_model_count: 3,
    severity: { low: 4, medium: 2, high: 2, critical: 0 },
    updated_at: '2026-08-07T09:15:00Z',
  },
  {
    id: '4', name: 'Warehouse Complex', address: 'Industrial Area, Manesar',
    status: 'completed', defect_count: 31, bim_model_count: 1,
    severity: { low: 12, medium: 10, high: 7, critical: 2 },
    updated_at: '2026-07-25T16:45:00Z',
  },
];

function SeverityBar({ severity }: { severity: Record<string, number> }) {
  const total = Object.values(severity).reduce((s, v) => s + v, 0) || 1;
  return (
    <div className={styles.severityBar}>
      <div className={styles.severitySegment} style={{ width: `${(severity.low / total) * 100}%`, background: 'hsl(142, 71%, 45%)' }} />
      <div className={styles.severitySegment} style={{ width: `${(severity.medium / total) * 100}%`, background: 'hsl(45, 93%, 47%)' }} />
      <div className={styles.severitySegment} style={{ width: `${(severity.high / total) * 100}%`, background: 'hsl(25, 95%, 53%)' }} />
      <div className={styles.severitySegment} style={{ width: `${(severity.critical / total) * 100}%`, background: 'hsl(0, 84%, 60%)' }} />
    </div>
  );
}

export default function ProjectsPage() {
  const [showModal, setShowModal] = useState(false);
  const [search, setSearch] = useState('');

  const filtered = MOCK_PROJECTS.filter((p) =>
    p.name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div>
      <div className={styles.header}>
        <input
          className={`input ${styles.searchBar}`}
          type="text"
          placeholder="Search projects..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <button className="btn btn-primary" onClick={() => setShowModal(true)}>
          + New Project
        </button>
      </div>

      <div className={styles.projectsGrid}>
        {filtered.map((project) => (
          <div key={project.id} className={styles.projectCard}>
            <div className={styles.projectName}>{project.name}</div>
            <div className={styles.projectAddress}>{project.address}</div>
            <div className={styles.projectMeta}>
              <span className={styles.defectCount}>
                <strong>{project.defect_count}</strong> defects
              </span>
              <span className={`badge badge-status-${project.status}`}>
                {project.status}
              </span>
            </div>
            <SeverityBar severity={project.severity} />
            <div className={styles.projectFooter}>
              <span className={styles.lastUpdated}>
                Updated {new Date(project.updated_at).toLocaleDateString()}
              </span>
              <span className={styles.defectCount}>
                {project.bim_model_count} BIM model{project.bim_model_count !== 1 ? 's' : ''}
              </span>
            </div>
          </div>
        ))}
      </div>

      <Modal isOpen={showModal} onClose={() => setShowModal(false)} title="New Project" size="md">
        <form className={styles.formGrid} onSubmit={(e) => { e.preventDefault(); setShowModal(false); }}>
          <div className="input-group">
            <label>Project Name</label>
            <input className="input" placeholder="e.g. Highway Bridge Retrofit" required />
          </div>
          <div className="input-group">
            <label>Description</label>
            <textarea className="textarea" placeholder="Brief project description..." />
          </div>
          <div className="input-group">
            <label>Address</label>
            <input className="input" placeholder="Site address" />
          </div>
          <div className="input-group">
            <label>Client Name</label>
            <input className="input" placeholder="Client or organization" />
          </div>
          <div className="modal-footer">
            <button type="button" className="btn btn-secondary" onClick={() => setShowModal(false)}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary">
              Create Project
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
