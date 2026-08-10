export default function ViewerPage() {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">🏗️</div>
      <h2 className="empty-state-title">BIM Viewer</h2>
      <p className="empty-state-description">
        View 3D BIM models with defect markers, element picking, and spatial mapping.
        Upload IFC files to get started. Coming in Phase 3.
      </p>
      <button className="btn btn-primary" disabled>
        Upload IFC Model
      </button>
    </div>
  );
}
