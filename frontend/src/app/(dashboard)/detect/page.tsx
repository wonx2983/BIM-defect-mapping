export default function DetectPage() {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">🔍</div>
      <h2 className="empty-state-title">Defect Detection</h2>
      <p className="empty-state-description">
        Upload construction site images to automatically detect and classify structural defects
        using AI-powered analysis. Coming in Phase 2.
      </p>
      <button className="btn btn-primary" disabled>
        Upload Images
      </button>
    </div>
  );
}
