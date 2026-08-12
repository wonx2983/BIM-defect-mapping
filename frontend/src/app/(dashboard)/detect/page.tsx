'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useDetectionStore } from '@/stores/detectionStore';
import { useProjectStore } from '@/stores/projectStore';
import { Upload, X, Check, Loader, ImageIcon, ScanSearch, ArrowRight } from 'lucide-react';
import styles from './detect.module.css';

const SEVERITY_STYLES: Record<string, string> = {
  low: styles.severityLow,
  medium: styles.severityMedium,
  high: styles.severityHigh,
  critical: styles.severityCritical,
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

function formatClass(cls: string): string {
  return cls.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase());
}

export default function DetectPage() {
  const {
    files, selectedFileIndex, selectedDetectionIndex, isProcessing,
    projectId, error, setProjectId, addFiles, removeFile, clearFiles,
    selectFile, selectDetection, processAll,
  } = useDetectionStore();

  const { projects, fetchProjects } = useProjectStore();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  useEffect(() => { fetchProjects(); }, [fetchProjects]);
  useEffect(() => {
    if (!projectId && projects.length > 0) setProjectId(projects[0].id);
  }, [projectId, projects, setProjectId]);

  const handleDragOver = useCallback((e: React.DragEvent) => { e.preventDefault(); setIsDragging(true); }, []);
  const handleDragLeave = useCallback(() => setIsDragging(false), []);
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setIsDragging(false);
    const droppedFiles = Array.from(e.dataTransfer.files).filter((f) => f.type.startsWith('image/'));
    if (droppedFiles.length > 0) addFiles(droppedFiles);
  }, [addFiles]);
  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) { addFiles(Array.from(e.target.files)); e.target.value = ''; }
  }, [addFiles]);

  const selectedFile = selectedFileIndex !== null ? files[selectedFileIndex] : null;
  const selectedResult = selectedFile?.result ?? null;

  const displayImage = selectedFile
    ? selectedResult?.annotated_image_url
      ? `${API_BASE}${selectedResult.annotated_image_url}`
      : selectedFile.preview
    : null;

  return (
    <div className={files.length === 0 ? '' : styles.detectLayout}>
      <div className={styles.mainArea}>
        {files.length === 0 ? (
          <div
            className={`${styles.uploadZone} ${isDragging ? styles.uploadZoneDragging : ''}`}
            onDragOver={handleDragOver} onDragLeave={handleDragLeave}
            onDrop={handleDrop} onClick={() => fileInputRef.current?.click()}
          >
            <Upload size={32} strokeWidth={1.5} className={styles.uploadIconSvg} />
            <div className={styles.uploadTitle}>Drop construction site images here</div>
            <div className={styles.uploadSubtext}>or click to browse. Upload multiple images for batch processing.</div>
            <button className="btn btn-primary" onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}>
              Select Images
            </button>
            <div className={styles.uploadFormats}>JPG, PNG, BMP, WebP — up to 20MB each</div>
            <input ref={fileInputRef} type="file" accept="image/*" multiple className={styles.hiddenInput} onChange={handleFileSelect} />
          </div>
        ) : (
          <>
            <div className={styles.toolbar}>
              <div className={styles.toolbarLeft}>
                <select className={`select ${styles.projectSelect}`} value={projectId || ''} onChange={(e) => setProjectId(e.target.value)}>
                  <option value="" disabled>Select Project</option>
                  {projects.map((p) => (<option key={p.id} value={p.id}>{p.name}</option>))}
                </select>
                <span className={styles.fileCount}>
                  {files.length} image{files.length !== 1 ? 's' : ''}
                  {files.filter((f) => f.status === 'done').length > 0 && ` · ${files.filter((f) => f.status === 'done').length} processed`}
                </span>
              </div>
              <div className={styles.toolbarRight}>
                <button className="btn btn-secondary btn-sm" onClick={() => fileInputRef.current?.click()}>Add More</button>
                <button className="btn btn-primary" onClick={processAll} disabled={isProcessing || !projectId}>
                  {isProcessing ? (<><span className="spinner" /> Processing...</>) : (<>Detect All <ArrowRight size={14} /></>)}
                </button>
                <button className="btn btn-ghost btn-sm" onClick={clearFiles}>Clear</button>
              </div>
              <input ref={fileInputRef} type="file" accept="image/*" multiple className={styles.hiddenInput} onChange={handleFileSelect} />
            </div>

            {error && <div className="toast toast-error" style={{ position: 'static' }}>{error}</div>}

            <div className={styles.previewContainer}>
              {displayImage ? (
                <img src={displayImage} alt="Detection preview" className={styles.previewImage} />
              ) : (
                <div className={styles.emptyResults}>
                  <ImageIcon size={28} strokeWidth={1.5} className={styles.emptyIconSvg} />
                  <div className={styles.emptyTitle}>Select an image</div>
                  <div className={styles.emptyText}>Click a thumbnail below to preview</div>
                </div>
              )}
              {selectedFile?.status === 'processing' && (
                <div className={styles.processingOverlay}>
                  <span className="spinner spinner-lg" />
                  <span className={styles.processingText}>Analyzing image for defects...</span>
                </div>
              )}
            </div>

            <div className={styles.thumbnailStrip}>
              {files.map((f, i) => (
                <div key={i} className={`${styles.thumbnail} ${selectedFileIndex === i ? styles.thumbnailActive : ''}`} onClick={() => selectFile(i)}>
                  <img src={f.preview} alt={f.file.name} className={styles.thumbnailImg} />
                  <div className={`${styles.thumbnailBadge} ${
                    f.status === 'done' ? styles.thumbnailDone
                    : f.status === 'processing' ? styles.thumbnailProcessing
                    : f.status === 'error' ? styles.thumbnailError
                    : styles.thumbnailPending
                  }`}>
                    {f.status === 'done' ? <Check size={10} /> : f.status === 'processing' ? <Loader size={10} /> : f.status === 'error' ? <X size={10} /> : null}
                  </div>
                  <button className={styles.thumbnailRemove} onClick={(e) => { e.stopPropagation(); removeFile(i); }}>
                    <X size={10} />
                  </button>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {files.length > 0 && (
        <div className={styles.resultsPanel}>
          <div className={styles.resultsPanelHeader}>
            <span className={styles.resultsPanelTitle}>
              {selectedResult ? `${selectedResult.detection_count} Defect${selectedResult.detection_count !== 1 ? 's' : ''} Found` : 'Detection Results'}
            </span>
            {selectedResult && <span className={styles.resultsMeta}>{selectedResult.inference_time_ms.toFixed(0)}ms</span>}
          </div>

          {selectedResult && selectedResult.detection_count > 0 && (
            <div className={styles.severitySummary}>
              {Object.entries(selectedResult.severity_summary).filter(([, count]) => count > 0).map(([sev, count]) => (
                <span key={sev} className={`${styles.severityChip} ${SEVERITY_STYLES[sev]}`}>{count} {sev}</span>
              ))}
            </div>
          )}

          <div className={styles.resultsBody}>
            {!selectedResult ? (
              <div className={styles.emptyResults}>
                <ScanSearch size={24} strokeWidth={1.5} className={styles.emptyIconSvg} />
                <div className={styles.emptyTitle}>No results yet</div>
                <div className={styles.emptyText}>Select an image and click &quot;Detect All&quot; to analyze for construction defects.</div>
              </div>
            ) : selectedResult.detection_count === 0 ? (
              <div className={styles.emptyResults}>
                <Check size={24} strokeWidth={1.5} className={styles.emptyIconSvg} />
                <div className={styles.emptyTitle}>No defects detected</div>
                <div className={styles.emptyText}>This image appears clear. Try adjusting the confidence threshold if you suspect missed detections.</div>
              </div>
            ) : (
              selectedResult.detections.map((det, i) => (
                <div key={i} className={`${styles.detectionCard} ${selectedDetectionIndex === i ? styles.detectionCardActive : ''}`} onClick={() => selectDetection(i)}>
                  <div className={styles.detectionCardHeader}>
                    <span className={styles.detectionClass}>{formatClass(det.defect_class)}</span>
                    <span className={styles.detectionConfidence}>{(det.confidence * 100).toFixed(1)}%</span>
                  </div>
                  <div className={styles.detectionCardMeta}>
                    <span className={`badge ${det.severity === 'critical' ? 'badge-severity-critical' : det.severity === 'high' ? 'badge-severity-high' : det.severity === 'medium' ? 'badge-severity-medium' : 'badge-severity-low'}`}>
                      {det.severity}
                    </span>
                    <span className={styles.detectionDimensions}>{det.dimensions.width_px}x{det.dimensions.height_px}px</span>
                    <span className={styles.detectionDimensions}>Score: {(det.severity_score * 100).toFixed(0)}%</span>
                  </div>
                </div>
              ))
            )}
          </div>

          {selectedResult && (
            <div className={styles.inferenceStats}>
              <span>Model: {selectedResult.model_name}</span>
              <span>{selectedResult.image_width}x{selectedResult.image_height}px</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
