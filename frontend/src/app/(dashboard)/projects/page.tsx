'use client';

import { useEffect, useState } from 'react';
import { useProjectStore } from '@/stores/projectStore';
import Modal from '@/components/ui/Modal';
import styles from './projects.module.css';

function SeverityBar({ defectCount }: { defectCount: number }) {
  // Without real per-project severity breakdown, show a placeholder bar
  // This will be enhanced when per-project severity stats endpoint is wired
  if (defectCount === 0) return null;
  return (
    <div className={styles.severityBar}>
      <div
        className={styles.severitySegment}
        style={{ width: '100%', background: 'hsl(215, 20%, 25%)' }}
      />
    </div>
  );
}

export default function ProjectsPage() {
  const { projects, total, isLoading, error, fetchProjects, addProject, removeProject } =
    useProjectStore();
  const [showModal, setShowModal] = useState(false);
  const [search, setSearch] = useState('');
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    address: '',
    client_name: '',
  });
  const [formError, setFormError] = useState('');

  useEffect(() => {
    fetchProjects({ search: search || undefined });
  }, [fetchProjects, search]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');
    if (!formData.name.trim()) {
      setFormError('Project name is required');
      return;
    }
    try {
      await addProject({
        name: formData.name,
        description: formData.description || undefined,
        address: formData.address || undefined,
        client_name: formData.client_name || undefined,
      });
      setShowModal(false);
      setFormData({ name: '', description: '', address: '', client_name: '' });
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to create project');
    }
  };

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

      {error && (
        <div className="toast toast-error" style={{ position: 'static', marginBottom: 16 }}>
          ⚠️ {error}
        </div>
      )}

      {isLoading && projects.length === 0 ? (
        <div className={styles.projectsGrid}>
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton skeleton-card" />
          ))}
        </div>
      ) : projects.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">📁</div>
          <h2 className="empty-state-title">No projects yet</h2>
          <p className="empty-state-description">
            Create your first project to start detecting and mapping construction defects.
          </p>
          <button className="btn btn-primary" onClick={() => setShowModal(true)}>
            Create Project
          </button>
        </div>
      ) : (
        <div className={styles.projectsGrid}>
          {projects.map((project) => (
            <div key={project.id} className={styles.projectCard}>
              <div className={styles.projectName}>{project.name}</div>
              <div className={styles.projectAddress}>
                {project.address || 'No address specified'}
              </div>
              <div className={styles.projectMeta}>
                <span className={styles.defectCount}>
                  <strong>{project.defect_count}</strong> defects
                </span>
                <span className={`badge badge-status-${project.status}`}>
                  {project.status}
                </span>
              </div>
              <SeverityBar defectCount={project.defect_count} />
              <div className={styles.projectFooter}>
                <span className={styles.lastUpdated}>
                  Updated {new Date(project.updated_at).toLocaleDateString()}
                </span>
                <span className={styles.defectCount}>
                  {project.bim_model_count} BIM model
                  {project.bim_model_count !== 1 ? 's' : ''}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        title="New Project"
        size="md"
      >
        <form className={styles.formGrid} onSubmit={handleCreate}>
          {formError && (
            <div
              className="toast toast-error"
              style={{ position: 'static', marginBottom: 12, minWidth: 'auto' }}
            >
              {formError}
            </div>
          )}
          <div className="input-group">
            <label>Project Name</label>
            <input
              className="input"
              placeholder="e.g. Highway Bridge Retrofit"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              required
            />
          </div>
          <div className="input-group">
            <label>Description</label>
            <textarea
              className="textarea"
              placeholder="Brief project description..."
              value={formData.description}
              onChange={(e) =>
                setFormData({ ...formData, description: e.target.value })
              }
            />
          </div>
          <div className="input-group">
            <label>Address</label>
            <input
              className="input"
              placeholder="Site address"
              value={formData.address}
              onChange={(e) => setFormData({ ...formData, address: e.target.value })}
            />
          </div>
          <div className="input-group">
            <label>Client Name</label>
            <input
              className="input"
              placeholder="Client or organization"
              value={formData.client_name}
              onChange={(e) =>
                setFormData({ ...formData, client_name: e.target.value })
              }
            />
          </div>
          <div className="modal-footer">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setShowModal(false)}
            >
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={isLoading}>
              {isLoading ? 'Creating...' : 'Create Project'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
