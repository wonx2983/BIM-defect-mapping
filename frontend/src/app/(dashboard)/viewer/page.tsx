'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useProjectStore } from '@/stores/projectStore';
import {
  getBIMModels, uploadBIMModel, getMappedDefects,
  type BIMModel, type MappedDefectsResponse,
} from '@/lib/api/bim';
import {
  getCameras, createCamera, deleteCamera, runCameraDetection,
  type Camera, type CameraDetectionResult,
} from '@/lib/api/cameras';
import { api } from '@/lib/api';
import {
  Upload, MapPin, Video, Info, Plus, Trash2, Play, Loader,
  Target, X, Eye, Wifi, ChevronDown,
} from 'lucide-react';
import styles from './viewer.module.css';

const SEVERITY_COLORS: Record<string, string> = {
  low: '#2d8a5e',
  medium: '#b8860b',
  high: '#cd6839',
  critical: '#cd3333',
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

type SidePanelTab = 'defects' | 'cameras' | 'properties';

function formatClass(cls: string) {
  return cls.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase());
}

export default function ViewerPage() {
  // Project
  const { projects, fetchProjects } = useProjectStore();
  const [projectId, setProjectId] = useState('');

  // BIM models
  const [bimModels, setBimModels] = useState<BIMModel[]>([]);
  const [selectedModel, setSelectedModel] = useState<BIMModel | null>(null);
  const [viewerReady, setViewerReady] = useState(false);

  // 3D viewer refs
  const containerRef = useRef<HTMLDivElement>(null);
  const componentsRef = useRef<any>(null);
  const worldRef = useRef<any>(null);
  const fragmentsRef = useRef<any>(null);
  const highlighterRef = useRef<any>(null);

  // Side panel
  const [activeTab, setActiveTab] = useState<SidePanelTab>('defects');
  const [defectsData, setDefectsData] = useState<MappedDefectsResponse | null>(null);
  const [cameras, setCameras] = useState<Camera[]>([]);

  // Mapping mode
  const [mappingDefectId, setMappingDefectId] = useState<string | null>(null);
  const [selectedElementGuid, setSelectedElementGuid] = useState<string | null>(null);
  const [selectedElementProps, setSelectedElementProps] = useState<Record<string, string> | null>(null);

  // Camera form
  const [showCameraForm, setShowCameraForm] = useState(false);
  const [cameraForm, setCameraForm] = useState({ name: '', rtsp_url: '', zone_label: '', location: '' });
  const [cameraDetecting, setCameraDetecting] = useState<string | null>(null);
  const [cameraResult, setCameraResult] = useState<CameraDetectionResult | null>(null);

  // Upload
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isUploading, setIsUploading] = useState(false);

  // Loading
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  // Init project list
  useEffect(() => { fetchProjects(); }, [fetchProjects]);
  useEffect(() => {
    if (!projectId && projects.length > 0) setProjectId(projects[0].id);
  }, [projectId, projects]);

  // Load BIM models + defects + cameras when project changes
  useEffect(() => {
    if (!projectId) return;
    setIsLoading(true);
    Promise.all([
      getBIMModels(projectId).catch(() => ({ models: [], total: 0 })),
      getMappedDefects(projectId).catch(() => null),
      getCameras(projectId).catch(() => ({ cameras: [], total: 0 })),
    ]).then(([bimData, defects, cameraData]) => {
      setBimModels(bimData.models);
      if (bimData.models.length > 0 && !selectedModel) {
        setSelectedModel(bimData.models[0]);
      }
      if (defects) setDefectsData(defects);
      setCameras(cameraData.cameras);
    }).finally(() => setIsLoading(false));
  }, [projectId]);

  // ── 3D Viewer Initialization ──────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current || viewerReady) return;

    let disposed = false;

    async function initViewer() {
      try {
        const OBC = await import('@thatopen/components');
        const THREE = await import('three');

        if (disposed || !containerRef.current) return;

        const components = new OBC.Components();
        const worlds = components.get(OBC.Worlds);

        const world = worlds.create();
        world.scene = new OBC.SimpleScene(components);
        world.renderer = new OBC.SimpleRenderer(components, containerRef.current);
        world.camera = new OBC.SimpleCamera(components);

        components.init();
        (world.scene as any).setup?.();

        // Set camera position
        (world.camera as any).controls?.setLookAt(20, 20, 20, 0, 0, 0);

        // Add grid
        const grids = components.get(OBC.Grids);
        grids.create(world);

        componentsRef.current = components;
        worldRef.current = world;

        // Setup fragments manager for IFC loading
        const fragments = components.get(OBC.FragmentsManager);
        if (!fragments.initialized) {
          try {
            fragments.init('/worker.min.mjs');
          } catch (e) {
            console.warn('FragmentsManager init:', e);
          }
        }
        fragmentsRef.current = fragments;

        // Setup raycaster for element picking
        const raycasters = components.get(OBC.Raycasters);
        raycasters.get(world);

        setViewerReady(true);
      } catch (err) {
        console.error('Failed to initialize 3D viewer:', err);
        setError('Failed to initialize 3D viewer. Try refreshing the page.');
      }
    }

    initViewer();

    return () => {
      disposed = true;
      if (componentsRef.current) {
        try { componentsRef.current.dispose(); } catch {}
        componentsRef.current = null;
        worldRef.current = null;
        fragmentsRef.current = null;
        setViewerReady(false);
      }
    };
  }, []);

  // ── Render 3D Pins for Mapped Defects ───────────────────────────
  const updateDefectPins = useCallback(async (defects: Array<{ id: string; severity: string; world_position: { x: number; y: number; z: number } | null }>) => {
    if (!worldRef.current) return;
    try {
      const THREE = await import('three');
      const scene = worldRef.current.scene.three;

      // Remove existing pins
      const existingPins = scene.children.filter((c: any) => c.name?.startsWith('defect_pin_'));
      existingPins.forEach((p: any) => scene.remove(p));

      // Add new pins
      defects.forEach((d) => {
        if (!d.world_position) return;
        const { x, y, z } = d.world_position;
        const geometry = new THREE.SphereGeometry(0.35, 16, 16);
        const color = SEVERITY_COLORS[d.severity] || '#cd3333';
        const material = new THREE.MeshStandardMaterial({
          color: new THREE.Color(color),
          emissive: new THREE.Color(color),
          emissiveIntensity: 0.4,
          roughness: 0.2,
        });
        const pin = new THREE.Mesh(geometry, material);
        pin.position.set(x, y, z);
        pin.name = `defect_pin_${d.id}`;
        scene.add(pin);
      });
    } catch (err) {
      console.error('Failed to render 3D defect pins:', err);
    }
  }, []);

  // ── Load IFC Model ────────────────────────────────────────────────
  const loadIFCModel = useCallback(async (model: BIMModel) => {
    if (!componentsRef.current || !worldRef.current) return;

    setIsLoading(true);
    setError('');
    try {
      const OBC = await import('@thatopen/components');
      const components = componentsRef.current;

      const fragments = components.get(OBC.FragmentsManager);
      if (!fragments.initialized) {
        try {
          fragments.init('/worker.min.mjs');
        } catch (e) {
          console.warn('FragmentsManager init:', e);
        }
      }

      const ifcLoader = components.get(OBC.IfcLoader);
      ifcLoader.settings.autoSetWasm = false;
      ifcLoader.settings.wasm = {
        path: '/',
        absolute: true,
      };
      ifcLoader.settings.customLocateFileHandler = (path: string) => `/${path}`;
      if (ifcLoader.settings.webIfc) {
        ifcLoader.settings.webIfc.locateFile = (path: string) => `/${path}`;
      }
      await ifcLoader.setup();

      // Fetch the IFC file
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE}${model.file_url}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        throw new Error(`Failed to download model file: HTTP ${response.status}`);
      }
      const buffer = await response.arrayBuffer();
      const data = new Uint8Array(buffer);

      const ifcModel = await ifcLoader.load(data);
      worldRef.current.scene.three.add(ifcModel);

      setSelectedModel(model);

      // Render any existing mapped defect pins
      if (defectsData?.mapped) {
        updateDefectPins(defectsData.mapped);
      }
    } catch (err) {
      console.error('Failed to load IFC model:', err);
      setError(err instanceof Error ? err.message : 'Failed to load IFC model.');
    } finally {
      setIsLoading(false);
    }
  }, [defectsData, updateDefectPins]);

  // ── Handle click on 3D canvas (for mapping) ──────────────────────
  const handleCanvasClick = useCallback(async (e: React.MouseEvent) => {
    if (!mappingDefectId || !componentsRef.current || !worldRef.current) return;

    try {
      const OBC = await import('@thatopen/components');
      const raycasters = componentsRef.current.get(OBC.Raycasters);
      const raycaster = raycasters.get(worldRef.current);
      const result = raycaster.castRay();

      if (result && result.object) {
        const point = result.point;
        const worldPosition = { x: point.x, y: point.y, z: point.z };

        // Try to get IFC element GUID from the intersected object
        let elementGuid = `element_${Date.now()}`;
        const fragments = componentsRef.current.get(OBC.FragmentsManager);
        if (result.object.uuid && fragments) {
          elementGuid = result.object.uuid;
        }

        // Update defect with BIM mapping
        await api.put(`/api/v1/defects/${mappingDefectId}`, {
          bim_element_guid: elementGuid,
          world_position: worldPosition,
        });

        // Refresh defects
        if (projectId) {
          const defects = await getMappedDefects(projectId);
          setDefectsData(defects);
          updateDefectPins(defects.mapped);
        }

        setMappingDefectId(null);
        setSelectedElementGuid(elementGuid);
      }
    } catch (err) {
      console.error('Mapping failed:', err);
    }
  }, [mappingDefectId, projectId, updateDefectPins]);

  // ── Upload IFC ────────────────────────────────────────────────────
  const handleUploadIFC = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !projectId) return;

    setIsUploading(true);
    setError('');
    try {
      const model = await uploadBIMModel(projectId, file);
      setBimModels((prev) => [model, ...prev]);
      setSelectedModel(model);
      // Try to load it
      await loadIFCModel(model);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setIsUploading(false);
    }
  };

  // ── Add Camera ────────────────────────────────────────────────────
  const handleAddCamera = async () => {
    if (!cameraForm.name || !cameraForm.rtsp_url || !projectId) return;
    try {
      const camera = await createCamera({
        name: cameraForm.name,
        rtsp_url: cameraForm.rtsp_url,
        project_id: projectId,
        bim_model_id: selectedModel?.id,
        bim_zone_label: cameraForm.zone_label || undefined,
        location_description: cameraForm.location || undefined,
        bim_element_guid: selectedElementGuid || undefined,
        world_position: selectedElementGuid ? { x: 0, y: 0, z: 0 } : undefined,
        auto_detect_enabled: true,
        auto_detect_interval_minutes: 15,
      });
      setCameras((prev) => [camera, ...prev]);
      setShowCameraForm(false);
      setCameraForm({ name: '', rtsp_url: '', zone_label: '', location: '' });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add camera');
    }
  };

  // ── Run Camera Detection ──────────────────────────────────────────
  const handleRunDetection = async (cameraId: string) => {
    setCameraDetecting(cameraId);
    setCameraResult(null);
    try {
      const result = await runCameraDetection(cameraId);
      setCameraResult(result);
      // Refresh defects to show new pins
      if (projectId) {
        const defects = await getMappedDefects(projectId);
        setDefectsData(defects);
        updateDefectPins(defects.mapped);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Detection failed');
    } finally {
      setCameraDetecting(null);
    }
  };

  const panelTabs = [
    { id: 'defects' as SidePanelTab, icon: MapPin, label: 'Defects', count: (defectsData?.mapped_count || 0) + (defectsData?.unmapped_count || 0) },
    { id: 'cameras' as SidePanelTab, icon: Video, label: 'Cameras', count: cameras.length },
    { id: 'properties' as SidePanelTab, icon: Info, label: 'Properties', count: 0 },
  ];

  return (
    <div className={styles.container}>
      {/* Toolbar */}
      <div className={styles.toolbar}>
        <select className="input" value={projectId} onChange={(e) => setProjectId(e.target.value)} style={{ maxWidth: 180 }}>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <div className={styles.toolbarDivider} />
        {selectedModel && (
          <span style={{ fontSize: 12, color: 'hsl(0,0%,50%)' }}>
            📐 {selectedModel.original_filename} ({(selectedModel.file_size_bytes / 1024).toFixed(0)} KB)
          </span>
        )}
        <div style={{ flex: 1 }} />
        <button
          className="btn btn-primary"
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading || !projectId}
          style={{ fontSize: 12, padding: '6px 14px' }}
        >
          {isUploading ? <><Loader size={14} className="spinner" /> Uploading...</> : <><Upload size={14} /> Upload IFC</>}
        </button>
        <input ref={fileInputRef} type="file" accept=".ifc,.ifczip" onChange={handleUploadIFC} style={{ display: 'none' }} />
      </div>

      {/* Mapping mode banner */}
      {mappingDefectId && (
        <div className={styles.mappingBanner}>
          <Target size={16} />
          <span>Click on a building element to map the defect to that location</span>
          <button onClick={() => setMappingDefectId(null)}><X size={12} /> Cancel</button>
        </div>
      )}

      {error && (
        <div className="toast toast-error" style={{ position: 'static', margin: '0 16px' }}>⚠️ {error}</div>
      )}

      {/* Main layout */}
      <div className={styles.main}>
        {/* 3D Canvas */}
        <div className={styles.canvasWrap}>
          <div ref={containerRef} className={styles.canvas} onClick={handleCanvasClick} />
          {!selectedModel && !isLoading && (
            <div className={styles.canvasEmpty}>
              <Upload size={48} strokeWidth={1} />
              <div>Upload an IFC file to view the 3D model</div>
              <button
                className="btn btn-primary"
                onClick={() => fileInputRef.current?.click()}
                disabled={!projectId}
              >
                Upload IFC Model
              </button>
            </div>
          )}
          {isLoading && (
            <div className={styles.canvasEmpty}>
              <Loader size={32} className="spinner" />
              <div>Loading 3D model...</div>
            </div>
          )}
        </div>

        {/* Side Panel */}
        <div className={styles.sidePanel}>
          <div className={styles.panelTabs}>
            {panelTabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  className={`${styles.panelTab} ${activeTab === tab.id ? styles.panelTabActive : ''}`}
                  onClick={() => setActiveTab(tab.id)}
                >
                  <Icon size={14} />
                  {tab.label}
                  {tab.count > 0 && <span className={styles.badge}>{tab.count}</span>}
                </button>
              );
            })}
          </div>

          <div className={styles.panelContent}>
            {/* ── Defects Tab ──────────────────────────────── */}
            {activeTab === 'defects' && (
              <>
                {/* Mapped defects */}
                {defectsData && defectsData.mapped.length > 0 && (
                  <>
                    <div className={styles.sectionHeader}>Mapped to BIM ({defectsData.mapped_count})</div>
                    {defectsData.mapped.map((d) => (
                      <div key={d.id} className={styles.defectItem}>
                        <div className={styles.defectDot} style={{ background: SEVERITY_COLORS[d.severity] }} />
                        <div className={styles.defectInfo}>
                          <div className={styles.defectClass}>{formatClass(d.defect_class)}</div>
                          <div className={styles.defectMeta}>
                            {d.severity} • {(d.confidence * 100).toFixed(0)}% • {d.bim_element_guid?.slice(0, 12)}...
                          </div>
                        </div>
                        <div className={styles.defectActions}>
                          <button className={styles.mapBtn} title="View on model"><Eye size={12} /></button>
                        </div>
                      </div>
                    ))}
                  </>
                )}

                {/* Unmapped defects */}
                {defectsData && defectsData.unmapped.length > 0 && (
                  <>
                    <div className={styles.sectionHeader}>Unmapped ({defectsData.unmapped_count})</div>
                    {defectsData.unmapped.map((d) => (
                      <div key={d.id} className={styles.defectItem}>
                        <div className={styles.defectDot} style={{ background: SEVERITY_COLORS[d.severity] }} />
                        <div className={styles.defectInfo}>
                          <div className={styles.defectClass}>{formatClass(d.defect_class)}</div>
                          <div className={styles.defectMeta}>{d.severity} • {(d.confidence * 100).toFixed(0)}%</div>
                        </div>
                        <div className={styles.defectActions}>
                          <button
                            className={`${styles.mapBtn} ${mappingDefectId === d.id ? styles.mapBtnActive : ''}`}
                            onClick={() => setMappingDefectId(mappingDefectId === d.id ? null : d.id)}
                          >
                            <MapPin size={12} /> Map
                          </button>
                        </div>
                      </div>
                    ))}
                  </>
                )}

                {(!defectsData || (defectsData.mapped.length === 0 && defectsData.unmapped.length === 0)) && (
                  <div style={{ padding: '24px 0', textAlign: 'center', color: 'hsl(0,0%,44%)', fontSize: 13 }}>
                    No defects yet. Detect defects from the Detection or Video page first.
                  </div>
                )}
              </>
            )}

            {/* ── Cameras Tab ─────────────────────────────── */}
            {activeTab === 'cameras' && (
              <>
                <button
                  className="btn btn-primary"
                  onClick={() => setShowCameraForm(!showCameraForm)}
                  style={{ width: '100%', fontSize: 12, marginBottom: 12 }}
                >
                  <Plus size={14} /> Register Camera
                </button>

                {showCameraForm && (
                  <div className={styles.addForm} style={{ marginBottom: 16, padding: 12, background: 'hsl(0,0%,10%)', borderRadius: 8, border: '1px solid hsl(0,0%,18%)' }}>
                    <div className="input-group">
                      <label style={{ fontSize: 11 }}>Camera Name</label>
                      <input className="input" placeholder="e.g. Cam-3F-East" value={cameraForm.name}
                        onChange={(e) => setCameraForm({ ...cameraForm, name: e.target.value })} />
                    </div>
                    <div className="input-group">
                      <label style={{ fontSize: 11 }}>RTSP URL</label>
                      <input className="input" placeholder="rtsp://admin:pass@192.168.1.100:554/stream"
                        value={cameraForm.rtsp_url}
                        onChange={(e) => setCameraForm({ ...cameraForm, rtsp_url: e.target.value })} />
                    </div>
                    <div className="input-group">
                      <label style={{ fontSize: 11 }}>BIM Zone Label</label>
                      <input className="input" placeholder="e.g. 3rd Floor East Wall" value={cameraForm.zone_label}
                        onChange={(e) => setCameraForm({ ...cameraForm, zone_label: e.target.value })} />
                    </div>
                    <div className="input-group">
                      <label style={{ fontSize: 11 }}>Location Description</label>
                      <input className="input" placeholder="Mounted on column C3" value={cameraForm.location}
                        onChange={(e) => setCameraForm({ ...cameraForm, location: e.target.value })} />
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button className="btn btn-primary" onClick={handleAddCamera} style={{ flex: 1, fontSize: 12 }}>
                        Save Camera
                      </button>
                      <button className="btn btn-secondary" onClick={() => setShowCameraForm(false)} style={{ fontSize: 12 }}>
                        Cancel
                      </button>
                    </div>
                  </div>
                )}

                {cameras.map((cam) => (
                  <div key={cam.id} className={styles.cameraItem}>
                    <div className={styles.cameraHeader}>
                      <span className={styles.cameraName}><Wifi size={12} /> {cam.name}</span>
                      <span className={`${styles.cameraStatus} ${cam.is_active ? styles.cameraStatusActive : styles.cameraStatusInactive}`}>
                        {cam.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </div>
                    {cam.bim_zone_label && (
                      <div className={styles.cameraZone}>📍 {cam.bim_zone_label}</div>
                    )}
                    <div className={styles.cameraMeta}>
                      {cam.total_defects_found} defects found
                      {cam.last_detection_at && ` • Last: ${new Date(cam.last_detection_at).toLocaleDateString()}`}
                      {cam.auto_detect_enabled && ` • Auto: every ${cam.auto_detect_interval_minutes}min`}
                    </div>
                    <div className={styles.cameraActions}>
                      <button
                        className={`${styles.cameraBtn} ${styles.cameraBtnPrimary}`}
                        onClick={() => handleRunDetection(cam.id)}
                        disabled={cameraDetecting === cam.id}
                      >
                        {cameraDetecting === cam.id
                          ? <><Loader size={12} className="spinner" /> Detecting...</>
                          : <><Play size={12} /> Run Detection</>
                        }
                      </button>
                      <button
                        className={`${styles.cameraBtn} ${styles.cameraBtnDanger}`}
                        onClick={async () => {
                          await deleteCamera(cam.id);
                          setCameras((prev) => prev.filter((c) => c.id !== cam.id));
                        }}
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                    {cameraResult && cameraResult.camera_id === cam.id && (
                      <div className={styles.detectionResult}>
                        <h4>Detection Results</h4>
                        <div className={styles.resultItem}>
                          <span className={styles.resultLabel}>Frames Analyzed</span>
                          <span className={styles.resultValue}>{cameraResult.frames_analyzed}</span>
                        </div>
                        <div className={styles.resultItem}>
                          <span className={styles.resultLabel}>Total Detections</span>
                          <span className={styles.resultValue}>{cameraResult.total_detections}</span>
                        </div>
                        <div className={styles.resultItem}>
                          <span className={styles.resultLabel}>Unique Defects Saved</span>
                          <span className={styles.resultValue}>{cameraResult.unique_defects_saved}</span>
                        </div>
                        {cameraResult.bim_zone && (
                          <div className={styles.resultItem}>
                            <span className={styles.resultLabel}>BIM Zone</span>
                            <span className={styles.resultValue}>{cameraResult.bim_zone}</span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}

                {cameras.length === 0 && !showCameraForm && (
                  <div style={{ padding: '24px 0', textAlign: 'center', color: 'hsl(0,0%,44%)', fontSize: 13 }}>
                    No cameras registered. Click &quot;Register Camera&quot; to add one.
                  </div>
                )}
              </>
            )}

            {/* ── Properties Tab ──────────────────────────── */}
            {activeTab === 'properties' && (
              <div>
                {selectedElementGuid ? (
                  <>
                    <div className={styles.sectionHeader}>Selected Element</div>
                    <div className={styles.resultItem}>
                      <span className={styles.resultLabel}>GUID</span>
                      <span className={styles.resultValue} style={{ fontSize: 11 }}>{selectedElementGuid}</span>
                    </div>
                  </>
                ) : (
                  <div style={{ padding: '24px 0', textAlign: 'center', color: 'hsl(0,0%,44%)', fontSize: 13 }}>
                    Click on an element in the 3D view to see its properties.
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Bottom bar */}
      <div className={styles.bottomBar}>
        <span>Models: {bimModels.length}</span>
        <span>Mapped: {defectsData?.mapped_count || 0}</span>
        <span>Unmapped: {defectsData?.unmapped_count || 0}</span>
        <span>Cameras: {cameras.length}</span>
        {viewerReady && <span style={{ color: 'hsl(152, 30%, 55%)' }}>● 3D Engine Ready</span>}
      </div>
    </div>
  );
}
