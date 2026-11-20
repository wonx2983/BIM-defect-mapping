'use client';
import { useEffect, useState } from 'react';
import { useProjectStore } from '@/stores/projectStore';
import { api, authenticatedFetch, responseError } from '@/lib/api';

type AuditEvent = { id: string; entity_id: string; action: string; created_at: string };
export default function ReportsPage() {
  const { projects, fetchProjects } = useProjectStore();
  const [projectId, setProjectId] = useState('');
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [error, setError] = useState('');
  useEffect(() => { void fetchProjects(); }, [fetchProjects]);
  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    api.get<AuditEvent[]>(`/api/v1/reports/${projectId}/audit`).then(data => {
      if (!cancelled) setEvents(data);
    }).catch(e => { if (!cancelled) setError(String(e)); });
    return () => { cancelled = true; };
  }, [projectId]);
  async function download() {
    setError('');
    try {
      const response = await authenticatedFetch(`/api/v1/reports/${projectId}/defects.csv`);
      if (!response.ok) throw new Error(await responseError(response));
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a'); link.href = url; link.download = 'inspection-defects.csv';
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(String(e)); }
  }
  return <div style={{ padding: 24 }}>
    <h1>Inspection reports</h1>
    <p>Export observations and review recorded defect changes. Automated severity is an estimate requiring human confirmation.</p>
    <select className="input" aria-label="Project" value={projectId} onChange={e => setProjectId(e.target.value)}>
      <option value="">Select a project</option>
      {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
    </select>
    <button className="btn btn-primary" disabled={!projectId} onClick={download}>Download CSV</button>
    {error && <p role="alert">{error}</p>}
    <h2>Recent change history</h2>
    <ul>{events.map(e => <li key={e.id}>{new Date(e.created_at).toLocaleString()} — {e.action} — {e.entity_id}</li>)}</ul>
    {projectId && !events.length && <p>No recorded changes yet.</p>}
  </div>;
}
