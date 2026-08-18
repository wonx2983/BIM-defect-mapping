'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useProjectStore } from '@/stores/projectStore';
import { Upload, Video, Wifi, Camera, Play, Square, Download, AlertTriangle, Loader } from 'lucide-react';
import styles from './video.module.css';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

type TabId = 'upload' | 'rtsp' | 'webcam';

interface VideoResult {
  result_id: string;
  total_frames: number;
  processed_frames: number;
  total_detections: number;
  unique_defects: number;
  duration_seconds: number;
  processing_time_seconds: number;
  severity_summary: Record<string, number>;
  class_summary: Record<string, number>;
  annotated_video_url?: string;
  download_url?: string;
  saved_defect_count: number;
  frame_detections: Array<{
    frame_index: number;
    timestamp_ms: number;
    detection_count: number;
    detections: Array<{
      defect_class: string;
      confidence: number;
      severity: string;
    }>;
  }>;
}

const SEVERITY_COLORS: Record<string, string> = {
  low: '#2d8a5e',
  medium: '#b8860b',
  high: '#cd6839',
  critical: '#cd3333',
};

function formatClass(cls: string): string {
  return cls.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase());
}

export default function VideoDetectionPage() {
  const [activeTab, setActiveTab] = useState<TabId>('upload');
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<VideoResult | null>(null);
  const [progress, setProgress] = useState('');

  // Upload state
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [videoPreviewUrl, setVideoPreviewUrl] = useState<string | null>(null);
  const [frameSkip, setFrameSkip] = useState(10);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // RTSP state
  const [rtspUrl, setRtspUrl] = useState('');
  const [rtspFrameSkip, setRtspFrameSkip] = useState(15);
  const [rtspMaxFrames, setRtspMaxFrames] = useState(100);

  // Webcam state
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [webcamActive, setWebcamActive] = useState(false);
  const [webcamResults, setWebcamResults] = useState<Array<{ class: string; severity: string; confidence: number }>>([]);
  const webcamIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Project selection
  const { projects, fetchProjects } = useProjectStore();
  const [projectId, setProjectId] = useState('');

  useEffect(() => { fetchProjects(); }, [fetchProjects]);
  useEffect(() => {
    if (!projectId && projects.length > 0) setProjectId(projects[0].id);
  }, [projectId, projects]);

  // Cleanup
  useEffect(() => {
    return () => {
      if (videoPreviewUrl) URL.revokeObjectURL(videoPreviewUrl);
      if (webcamIntervalRef.current) clearInterval(webcamIntervalRef.current);
    };
  }, [videoPreviewUrl]);

  const handleVideoSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setVideoFile(file);
      setVideoPreviewUrl(URL.createObjectURL(file));
      setResult(null);
      setError('');
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith('video/')) {
      setVideoFile(file);
      setVideoPreviewUrl(URL.createObjectURL(file));
      setResult(null);
      setError('');
    }
  }, []);

  // ── Upload Processing ─────────────────────────────────────────────
  const processUploadedVideo = async () => {
    if (!videoFile || !projectId) return;
    setIsProcessing(true);
    setError('');
    setProgress('Uploading video and processing frames...');
    setResult(null);

    try {
      const formData = new FormData();
      formData.append('file', videoFile);
      formData.append('project_id', projectId);
      formData.append('frame_skip', String(frameSkip));
      formData.append('auto_save', 'true');

      const token = localStorage.getItem('access_token');
      const res = await fetch(`${API_BASE}/api/v1/video/upload`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Processing failed' }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const data: VideoResult = await res.json();
      setResult(data);
      setProgress('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Video processing failed');
      setProgress('');
    } finally {
      setIsProcessing(false);
    }
  };

  // ── RTSP Processing ───────────────────────────────────────────────
  const processRtspStream = async () => {
    if (!rtspUrl || !projectId) return;
    setIsProcessing(true);
    setError('');
    setProgress('Connecting to RTSP stream...');
    setResult(null);

    try {
      const formData = new FormData();
      formData.append('rtsp_url', rtspUrl);
      formData.append('project_id', projectId);
      formData.append('frame_skip', String(rtspFrameSkip));
      formData.append('max_frames', String(rtspMaxFrames));

      const token = localStorage.getItem('access_token');
      const res = await fetch(`${API_BASE}/api/v1/video/stream/analyze`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Stream processing failed' }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      setResult(data);
      setProgress('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'RTSP stream processing failed');
      setProgress('');
    } finally {
      setIsProcessing(false);
    }
  };

  // ── Webcam ────────────────────────────────────────────────────────
  const startWebcam = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.play();
      }
      setWebcamActive(true);
      setWebcamResults([]);

      // Send frames every 2 seconds
      webcamIntervalRef.current = setInterval(async () => {
        if (!videoRef.current || !canvasRef.current) return;
        const canvas = canvasRef.current;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        canvas.width = 640;
        canvas.height = 480;
        ctx.drawImage(videoRef.current, 0, 0, 640, 480);

        canvas.toBlob(async (blob) => {
          if (!blob || !projectId) return;
          const formData = new FormData();
          formData.append('file', blob, 'webcam_frame.jpg');
          formData.append('project_id', projectId);
          formData.append('auto_save', 'false');

          try {
            const token = localStorage.getItem('access_token');
            const res = await fetch(`${API_BASE}/api/v1/detect/image`, {
              method: 'POST',
              headers: { Authorization: `Bearer ${token}` },
              body: formData,
            });
            if (res.ok) {
              const data = await res.json();
              setWebcamResults(
                (data.detections || []).map((d: { defect_class: string; severity: string; confidence: number }) => ({
                  class: d.defect_class,
                  severity: d.severity,
                  confidence: d.confidence,
                }))
              );
            }
          } catch { /* ignore frame errors */ }
        }, 'image/jpeg', 0.8);
      }, 2000);
    } catch (err) {
      setError('Failed to access webcam. Please grant camera permissions.');
    }
  };

  const stopWebcam = () => {
    if (webcamIntervalRef.current) {
      clearInterval(webcamIntervalRef.current);
      webcamIntervalRef.current = null;
    }
    if (videoRef.current?.srcObject) {
      (videoRef.current.srcObject as MediaStream).getTracks().forEach((t) => t.stop());
      videoRef.current.srcObject = null;
    }
    setWebcamActive(false);
    setWebcamResults([]);
  };

  const tabs = [
    { id: 'upload' as TabId, icon: Upload, label: 'Upload Video' },
    { id: 'rtsp' as TabId, icon: Wifi, label: 'RTSP / CCTV Stream' },
    { id: 'webcam' as TabId, icon: Camera, label: 'Live Webcam' },
  ];

  return (
    <div className={styles.container}>
      {/* Tab Bar */}
      <div className={styles.tabBar}>
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              className={`${styles.tab} ${activeTab === tab.id ? styles.tabActive : ''}`}
              onClick={() => { setActiveTab(tab.id); setError(''); setResult(null); }}
            >
              <Icon size={16} />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Project Selector */}
      <div className={styles.projectBar}>
        <label>Project:</label>
        <select
          className="input"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
          style={{ maxWidth: 300 }}
        >
          {projects.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </div>

      {error && (
        <div className="toast toast-error" style={{ position: 'static', marginBottom: 16 }}>
          <AlertTriangle size={14} /> {error}
        </div>
      )}

      {/* ── Tab: Upload Video ──────────────────────────────────────── */}
      {activeTab === 'upload' && (
        <div className={styles.content}>
          <div
            className={`${styles.dropZone} ${videoFile ? styles.dropZoneHasFile : ''}`}
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            {videoFile ? (
              <div className={styles.fileInfo}>
                <Video size={32} />
                <div className={styles.fileName}>{videoFile.name}</div>
                <div className={styles.fileMeta}>
                  {(videoFile.size / (1024 * 1024)).toFixed(1)} MB
                </div>
              </div>
            ) : (
              <>
                <Upload size={40} strokeWidth={1} style={{ opacity: 0.4 }} />
                <div className={styles.dropText}>Drop a video file here or click to browse</div>
                <div className={styles.dropHint}>MP4, AVI, MOV, MKV • Max 500MB</div>
              </>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept="video/*"
              onChange={handleVideoSelect}
              style={{ display: 'none' }}
            />
          </div>

          <div className={styles.controls}>
            <div className="input-group" style={{ flex: 1 }}>
              <label>Frame Sampling Rate</label>
              <select className="input" value={frameSkip} onChange={(e) => setFrameSkip(Number(e.target.value))}>
                <option value={5}>Every 5th frame (thorough, slower)</option>
                <option value={10}>Every 10th frame (balanced)</option>
                <option value={15}>Every 15th frame (fast)</option>
                <option value={30}>Every 30th frame (very fast)</option>
              </select>
            </div>
            <button
              className="btn btn-primary"
              disabled={!videoFile || !projectId || isProcessing}
              onClick={processUploadedVideo}
              style={{ height: 42, minWidth: 160 }}
            >
              {isProcessing ? (
                <><Loader size={16} className="spinner" /> Processing...</>
              ) : (
                <><Play size={16} /> Analyze Video</>
              )}
            </button>
          </div>

          {progress && (
            <div className={styles.progressBar}>
              <Loader size={14} className="spinner" /> {progress}
            </div>
          )}

          {videoPreviewUrl && !result && (
            <div className={styles.previewSection}>
              <video src={videoPreviewUrl} controls className={styles.videoPreview} />
            </div>
          )}
        </div>
      )}

      {/* ── Tab: RTSP / CCTV ──────────────────────────────────────── */}
      {activeTab === 'rtsp' && (
        <div className={styles.content}>
          <div className={styles.rtspForm}>
            <div className="input-group" style={{ flex: 2 }}>
              <label>RTSP Stream URL</label>
              <input
                className="input"
                placeholder="rtsp://username:password@camera-ip:554/stream"
                value={rtspUrl}
                onChange={(e) => setRtspUrl(e.target.value)}
              />
            </div>
            <div className="input-group" style={{ flex: 1 }}>
              <label>Frame Sampling</label>
              <select className="input" value={rtspFrameSkip} onChange={(e) => setRtspFrameSkip(Number(e.target.value))}>
                <option value={5}>Every 5th frame</option>
                <option value={10}>Every 10th frame</option>
                <option value={15}>Every 15th frame</option>
                <option value={30}>Every 30th frame</option>
              </select>
            </div>
            <div className="input-group" style={{ flex: 1 }}>
              <label>Max Frames</label>
              <select className="input" value={rtspMaxFrames} onChange={(e) => setRtspMaxFrames(Number(e.target.value))}>
                <option value={50}>50 frames</option>
                <option value={100}>100 frames</option>
                <option value={200}>200 frames</option>
                <option value={500}>500 frames</option>
              </select>
            </div>
          </div>
          <button
            className="btn btn-primary"
            disabled={!rtspUrl || !projectId || isProcessing}
            onClick={processRtspStream}
            style={{ marginTop: 16 }}
          >
            {isProcessing ? (
              <><Loader size={16} className="spinner" /> Analyzing Stream...</>
            ) : (
              <><Wifi size={16} /> Connect & Analyze</>
            )}
          </button>
          {progress && (
            <div className={styles.progressBar}>
              <Loader size={14} className="spinner" /> {progress}
            </div>
          )}
          <div className={styles.rtspGuide}>
            <h4>How to connect your CCTV camera:</h4>
            <ol>
              <li>Find your IP camera&apos;s local IP address (e.g., 192.168.1.100)</li>
              <li>The default RTSP port is <strong>554</strong></li>
              <li>Common URL formats:
                <ul>
                  <li><code>rtsp://admin:password@192.168.1.100:554/stream1</code> (Hikvision)</li>
                  <li><code>rtsp://admin:password@192.168.1.100:554/cam/realmonitor?channel=1</code> (Dahua)</li>
                  <li><code>rtsp://192.168.1.100:554/live/ch00_0</code> (Generic ONVIF)</li>
                </ul>
              </li>
              <li>Ensure the camera and this server are on the same network</li>
            </ol>
          </div>
        </div>
      )}

      {/* ── Tab: Webcam ───────────────────────────────────────────── */}
      {activeTab === 'webcam' && (
        <div className={styles.content}>
          <div className={styles.webcamSection}>
            <div className={styles.webcamContainer}>
              <video ref={videoRef} className={styles.webcamVideo} playsInline muted />
              <canvas ref={canvasRef} style={{ display: 'none' }} />
              {!webcamActive && (
                <div className={styles.webcamOverlay}>
                  <Camera size={48} strokeWidth={1} style={{ opacity: 0.4 }} />
                  <div>Click Start to activate your webcam</div>
                </div>
              )}
            </div>
            <div className={styles.webcamControls}>
              {!webcamActive ? (
                <button className="btn btn-primary" onClick={startWebcam} disabled={!projectId}>
                  <Play size={16} /> Start Live Detection
                </button>
              ) : (
                <button className="btn btn-secondary" onClick={stopWebcam} style={{ background: '#cd3333', borderColor: '#cd3333' }}>
                  <Square size={16} /> Stop
                </button>
              )}
            </div>
            {webcamActive && webcamResults.length > 0 && (
              <div className={styles.webcamDetections}>
                <h4>Live Detections:</h4>
                {webcamResults.map((r, i) => (
                  <div key={i} className={styles.liveDetection}>
                    <span className={styles.liveClass}>{formatClass(r.class)}</span>
                    <span className={styles.liveSeverity} style={{ color: SEVERITY_COLORS[r.severity] }}>
                      {r.severity}
                    </span>
                    <span className={styles.liveConf}>{(r.confidence * 100).toFixed(0)}%</span>
                  </div>
                ))}
              </div>
            )}
            {webcamActive && webcamResults.length === 0 && (
              <div className={styles.webcamDetections}>
                <div style={{ color: 'hsl(0,0%,44%)', fontSize: 13, padding: '12px 0' }}>
                  Scanning for defects... Point camera at concrete surfaces.
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Results Panel ─────────────────────────────────────────── */}
      {result && (
        <div className={styles.resultsPanel}>
          <h3 className={styles.resultsTitle}>Analysis Results</h3>

          <div className={styles.statsGrid}>
            <div className={styles.statCard}>
              <div className={styles.statValue}>{result.unique_defects}</div>
              <div className={styles.statLabel}>Unique Defects</div>
            </div>
            <div className={styles.statCard}>
              <div className={styles.statValue}>{result.total_detections}</div>
              <div className={styles.statLabel}>Total Detections</div>
            </div>
            <div className={styles.statCard}>
              <div className={styles.statValue}>{result.processed_frames}</div>
              <div className={styles.statLabel}>Frames Analyzed</div>
            </div>
            <div className={styles.statCard}>
              <div className={styles.statValue}>{result.processing_time_seconds?.toFixed(1)}s</div>
              <div className={styles.statLabel}>Processing Time</div>
            </div>
          </div>

          {/* Severity Breakdown */}
          <div className={styles.breakdownRow}>
            <div className={styles.breakdownCard}>
              <h4>Severity Breakdown</h4>
              {Object.entries(result.severity_summary).filter(([, v]) => v > 0).length === 0 ? (
                <div style={{ color: 'hsl(0,0%,44%)', fontSize: 13 }}>No defects found</div>
              ) : (
                Object.entries(result.severity_summary)
                  .filter(([, v]) => v > 0)
                  .map(([sev, count]) => (
                    <div key={sev} className={styles.breakdownItem}>
                      <div className={styles.breakdownDot} style={{ background: SEVERITY_COLORS[sev] }} />
                      <span className={styles.breakdownLabel}>{sev}</span>
                      <span className={styles.breakdownCount}>{count}</span>
                    </div>
                  ))
              )}
            </div>
            <div className={styles.breakdownCard}>
              <h4>Defect Classes</h4>
              {Object.entries(result.class_summary).length === 0 ? (
                <div style={{ color: 'hsl(0,0%,44%)', fontSize: 13 }}>No defects found</div>
              ) : (
                Object.entries(result.class_summary).map(([cls, count]) => (
                  <div key={cls} className={styles.breakdownItem}>
                    <span className={styles.breakdownLabel}>{formatClass(cls)}</span>
                    <span className={styles.breakdownCount}>{count}</span>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Saved defects info */}
          {result.saved_defect_count > 0 && (
            <div className={styles.savedInfo}>
              ✅ {result.saved_defect_count} unique defect{result.saved_defect_count !== 1 ? 's' : ''} saved to project
            </div>
          )}

          {/* Download annotated video */}
          {result.download_url && (
            <a
              href={`${API_BASE}${result.download_url}?authorization=Bearer+${localStorage.getItem('access_token')}`}
              className="btn btn-primary"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 8, marginTop: 12 }}
              download
            >
              <Download size={16} /> Download Annotated Video
            </a>
          )}
        </div>
      )}
    </div>
  );
}
