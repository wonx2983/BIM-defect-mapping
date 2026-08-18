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

  // ── 3D Viewer Initialization (Three.js + web-ifc direct) ────────
  useEffect(() => {
    if (!containerRef.current || viewerReady) return;

    let disposed = false;

    async function initViewer() {
      try {
        const THREE = await import('three');
        const { OrbitControls } = await import('three/examples/jsm/controls/OrbitControls.js');

        if (disposed || !containerRef.current) return;

        const container = containerRef.current;

        // Create scene
        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0xf0f0f0);

        // Lighting
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
        scene.add(ambientLight);
        const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
        dirLight.position.set(50, 100, 50);
        dirLight.castShadow = true;
        scene.add(dirLight);
        const hemiLight = new THREE.HemisphereLight(0xffffff, 0x8d8d8d, 0.5);
        scene.add(hemiLight);

        // Camera
        const camera = new THREE.PerspectiveCamera(
          45, container.clientWidth / container.clientHeight, 0.1, 10000
        );
        camera.position.set(30, 30, 30);

        // Renderer
        const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        renderer.setSize(container.clientWidth, container.clientHeight);
        renderer.setPixelRatio(window.devicePixelRatio);
        renderer.shadowMap.enabled = true;
        container.appendChild(renderer.domElement);

        // Controls
        const controls = new OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.05;
        controls.target.set(0, 0, 0);
        controls.update();

        // Grid
        const gridHelper = new THREE.GridHelper(100, 50, 0xcccccc, 0xe0e0e0);
        scene.add(gridHelper);

        // Raycaster for picking
        const raycaster = new THREE.Raycaster();
        const mouse = new THREE.Vector2();

        // Animation loop
        function animate() {
          if (disposed) return;
          requestAnimationFrame(animate);
          controls.update();
          renderer.render(scene, camera);
        }
        animate();

        // Resize handler
        const handleResize = () => {
          if (!container) return;
          camera.aspect = container.clientWidth / container.clientHeight;
          camera.updateProjectionMatrix();
          renderer.setSize(container.clientWidth, container.clientHeight);
        };
        window.addEventListener('resize', handleResize);
        const resizeObserver = new ResizeObserver(handleResize);
        resizeObserver.observe(container);

        // Store refs
        componentsRef.current = { scene, camera, renderer, controls, raycaster, mouse, THREE };
        worldRef.current = { scene: { three: scene }, camera, renderer };

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
        try {
          componentsRef.current.renderer?.dispose();
          componentsRef.current.controls?.dispose();
          const canvas = componentsRef.current.renderer?.domElement;
          if (canvas?.parentElement) canvas.parentElement.removeChild(canvas);
        } catch {}
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

  // ── Load IFC Model (direct web-ifc + Three.js) ────────────────────
  const loadIFCModel = useCallback(async (model: BIMModel) => {
    if (!componentsRef.current || !worldRef.current) return;

    setIsLoading(true);
    setError('');
    try {
      const THREE = await import('three');
      const WebIFC = await import('web-ifc');

      const { scene, camera, controls } = componentsRef.current;

      // Initialize web-ifc API
      const ifcApi = new WebIFC.IfcAPI();
      ifcApi.SetWasmPath(window.location.origin + '/', true);
      await ifcApi.Init();

      // Fetch the IFC file from backend
      const token = localStorage.getItem('access_token');
      const response = await fetch(`${API_BASE}${model.file_url}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) {
        throw new Error(`Failed to download model: HTTP ${response.status}`);
      }
      const buffer = await response.arrayBuffer();
      const data = new Uint8Array(buffer);

      // Open IFC model
      const modelID = ifcApi.OpenModel(data);

      // Remove previous model meshes
      const toRemove = scene.children.filter((c: any) => c.name === 'ifc_model');
      toRemove.forEach((m: any) => scene.remove(m));

      // Extract all geometry from the IFC model
      const modelGroup = new THREE.Group();
      modelGroup.name = 'ifc_model';

      // Get all mesh geometries
      ifcApi.StreamAllMeshes(modelID, (mesh: any) => {
        const placedGeometries = mesh.geometries;
        for (let i = 0; i < placedGeometries.size(); i++) {
          const placedGeometry = placedGeometries.get(i);
          const ifcGeometry = ifcApi.GetGeometry(modelID, placedGeometry.geometryExpressID);

          const verts = ifcApi.GetVertexArray(
            ifcGeometry.GetVertexData(),
            ifcGeometry.GetVertexDataSize()
          );
          const indices = ifcApi.GetIndexArray(
            ifcGeometry.GetIndexData(),
            ifcGeometry.GetIndexDataSize()
          );

          if (verts.length === 0 || indices.length === 0) {
            ifcGeometry.delete();
            continue;
          }

          // Build Three.js geometry from raw vertex/index data
          const geometry = new THREE.BufferGeometry();

          // web-ifc vertex data: [x, y, z, nx, ny, nz] per vertex
          const posArray = new Float32Array(verts.length / 2);
          const norArray = new Float32Array(verts.length / 2);
          for (let v = 0; v < verts.length; v += 6) {
            const idx = v / 2;
            posArray[idx] = verts[v];
            posArray[idx + 1] = verts[v + 1];
            posArray[idx + 2] = verts[v + 2];
            norArray[idx] = verts[v + 3];
            norArray[idx + 1] = verts[v + 4];
            norArray[idx + 2] = verts[v + 5];
          }

          geometry.setAttribute('position', new THREE.BufferAttribute(posArray, 3));
          geometry.setAttribute('normal', new THREE.BufferAttribute(norArray, 3));
          geometry.setIndex(Array.from(indices));

          // Apply IFC color
          const color = placedGeometry.color;
          const material = new THREE.MeshPhongMaterial({
            color: new THREE.Color(color.x, color.y, color.z),
            opacity: color.w,
            transparent: color.w < 1.0,
            side: THREE.DoubleSide,
            depthWrite: color.w >= 1.0,
          });

          const mesh3D = new THREE.Mesh(geometry, material);

          // Apply transformation matrix
          const matrix = new THREE.Matrix4();
          const flatMatrix = placedGeometry.flatTransformation;
          matrix.fromArray(flatMatrix);
          mesh3D.applyMatrix4(matrix);

          mesh3D.name = `ifc_element_${mesh.expressID}`;
          mesh3D.userData.expressID = mesh.expressID;
          modelGroup.add(mesh3D);

          ifcGeometry.delete();
        }
      });

      scene.add(modelGroup);

      // Fit camera to model
      const box = new THREE.Box3().setFromObject(modelGroup);
      if (!box.isEmpty()) {
        const center = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z);
        const dist = maxDim * 1.5;

        camera.position.set(center.x + dist, center.y + dist * 0.7, center.z + dist);
        controls.target.copy(center);
        controls.update();
      }

      // Cleanup web-ifc model (keep API for future queries)
      fragmentsRef.current = { ifcApi, modelID };

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

  // ── Raycast helper (shared by hover + click) ─────────────────────
  const raycastIFC = useCallback((e: React.MouseEvent) => {
    if (!componentsRef.current) return null;
    const { raycaster, mouse, scene, camera } = componentsRef.current;
    const canvas = componentsRef.current.renderer?.domElement;
    if (!canvas) return null;

    const rect = canvas.getBoundingClientRect();
    mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

    raycaster.setFromCamera(mouse, camera);

    const ifcModel = scene.children.find((c: any) => c.name === 'ifc_model');
    if (!ifcModel) return null;

    const intersects = raycaster.intersectObjects(ifcModel.children, true);
    return intersects.length > 0 ? intersects[0] : null;
  }, []);

  // ── Get IFC element properties from web-ifc ──────────────────────
  const getElementProperties = useCallback((expressID: number): Record<string, string> => {
    if (!fragmentsRef.current?.ifcApi || fragmentsRef.current.modelID === undefined) return {};
    const { ifcApi, modelID } = fragmentsRef.current;
    const props: Record<string, string> = { 'Express ID': String(expressID) };

    try {
      const line = ifcApi.GetLine(modelID, expressID);
      if (line) {
        if (line.GlobalId?.value) props['Global ID'] = line.GlobalId.value;
        if (line.Name?.value) props['Name'] = line.Name.value;
        if (line.Description?.value) props['Description'] = line.Description.value;
        if (line.ObjectType?.value) props['Object Type'] = line.ObjectType.value;
        if (line.Tag?.value) props['Tag'] = line.Tag.value;
        // Get the IFC type name
        const type = ifcApi.GetLineType(modelID, expressID);
        if (type) props['IFC Type'] = String(type);
      }
    } catch {
      // Some elements may not have property sets
    }

    return props;
  }, []);

  // ── Hover highlight ──────────────────────────────────────────────
  const prevHighlightRef = useRef<{ mesh: any; originalMaterial: any } | null>(null);

  const handleCanvasHover = useCallback((e: React.MouseEvent) => {
    if (!componentsRef.current) return;
    const { THREE } = componentsRef.current;

    // Restore previous highlight
    if (prevHighlightRef.current) {
      prevHighlightRef.current.mesh.material = prevHighlightRef.current.originalMaterial;
      prevHighlightRef.current = null;
    }

    const hit = raycastIFC(e);
    if (hit && hit.object) {
      const mesh = hit.object;
      const originalMaterial = mesh.material;

      // Create highlight material (keep original color but add emissive glow)
      const highlightMat = originalMaterial.clone();
      highlightMat.emissive = new THREE.Color(0x4488ff);
      highlightMat.emissiveIntensity = 0.3;
      mesh.material = highlightMat;

      prevHighlightRef.current = { mesh, originalMaterial };

      // Change cursor
      componentsRef.current.renderer.domElement.style.cursor = 'pointer';
    } else {
      if (componentsRef.current.renderer?.domElement) {
        componentsRef.current.renderer.domElement.style.cursor = mappingDefectId ? 'crosshair' : 'grab';
      }
    }
  }, [raycastIFC, mappingDefectId]);

  // ── Handle click on 3D canvas ────────────────────────────────────
  const [mappingSuccess, setMappingSuccess] = useState('');

  const handleCanvasClick = useCallback(async (e: React.MouseEvent) => {
    if (!componentsRef.current || !worldRef.current) return;

    const hit = raycastIFC(e);
    if (!hit || !hit.object) return;

    const point = hit.point;
    const worldPosition = { x: point.x, y: point.y, z: point.z };
    const expressID = hit.object.userData?.expressID;

    // Get element GUID from web-ifc properties
    let elementGuid = expressID ? `ifc_${expressID}` : `element_${Date.now()}`;
    let elementProps: Record<string, string> = {};
    
    if (expressID) {
      elementProps = getElementProperties(expressID);
      if (elementProps['Global ID']) {
        elementGuid = elementProps['Global ID'];
      }
    }

    // Update selected element (always, for properties panel)
    setSelectedElementGuid(elementGuid);
    setSelectedElementProps(elementProps);
    setActiveTab('properties');

    // If in mapping mode, also map the defect
    if (mappingDefectId) {
      try {
        const token = localStorage.getItem('access_token');
        const putRes = await fetch(`${API_BASE}/api/v1/defects/${mappingDefectId}`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            bim_element_guid: elementGuid,
            world_position: worldPosition,
          }),
        });

        if (!putRes.ok) {
          const errBody = await putRes.json().catch(() => ({ detail: `HTTP ${putRes.status}` }));
          throw new Error(errBody.detail || `Failed with status ${putRes.status}`);
        }

        // Show success
        const defectName = defectsData?.unmapped.find(d => d.id === mappingDefectId)?.defect_class || 'Defect';
        setMappingSuccess(`✅ ${formatClass(defectName)} mapped to ${elementProps['Name'] || elementGuid.slice(0, 16)}`);
        setTimeout(() => setMappingSuccess(''), 4000);

        // Refresh defects
        if (projectId) {
          const defects = await getMappedDefects(projectId);
          setDefectsData(defects);
          updateDefectPins(defects.mapped);
        }

        setMappingDefectId(null);
      } catch (err) {
        console.error('Mapping failed:', err);
        setError(err instanceof Error ? err.message : 'Failed to map defect. Please try again.');
      }
    }

    // Highlight selected element (persistent blue outline)
    const { THREE, scene } = componentsRef.current;
    // Remove old selection outlines
    const oldOutlines = scene.children.filter((c: any) => c.name === 'selection_outline');
    oldOutlines.forEach((o: any) => scene.remove(o));
    // Add selection outline  
    if (hit.object.geometry) {
      const outlineMat = new THREE.MeshBasicMaterial({
        color: 0x4488ff,
        side: THREE.BackSide,
        transparent: true,
        opacity: 0.25,
      });
      const outline = new THREE.Mesh(hit.object.geometry.clone(), outlineMat);
      outline.position.copy(hit.object.position);
      outline.rotation.copy(hit.object.rotation);
      outline.scale.copy(hit.object.scale).multiplyScalar(1.03);
      outline.matrix.copy(hit.object.matrix);
      outline.matrixAutoUpdate = false;
      outline.name = 'selection_outline';
      scene.add(outline);
    }
  }, [raycastIFC, mappingDefectId, projectId, defectsData, getElementProperties, updateDefectPins]);

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
          <span>🎯 <strong>Mapping Mode:</strong> Hover over elements to preview, then click to map the defect</span>
          <button onClick={() => setMappingDefectId(null)}><X size={12} /> Cancel</button>
        </div>
      )}

      {/* Success toast */}
      {mappingSuccess && (
        <div className="toast toast-success" style={{ position: 'static', margin: '0 16px' }}>{mappingSuccess}</div>
      )}

      {error && (
        <div className="toast toast-error" style={{ position: 'static', margin: '0 16px' }}>⚠️ {error}
          <button onClick={() => setError('')} style={{ marginLeft: 8, background: 'none', border: 'none', color: 'inherit', cursor: 'pointer' }}>✕</button>
        </div>
      )}

      {/* Main layout */}
      <div className={styles.main}>
        {/* 3D Canvas */}
        <div className={styles.canvasWrap}>
          <div
            ref={containerRef}
            className={styles.canvas}
            onClick={handleCanvasClick}
            onMouseMove={handleCanvasHover}
            style={{ cursor: mappingDefectId ? 'crosshair' : 'grab' }}
          />
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
                    <div className={styles.sectionHeader}>
                      Selected Element
                      <button
                        onClick={() => { setSelectedElementGuid(null); setSelectedElementProps(null); }}
                        style={{ float: 'right', background: 'none', border: 'none', color: 'hsl(0,0%,50%)', cursor: 'pointer', fontSize: 11 }}
                      >
                        Clear
                      </button>
                    </div>
                    {selectedElementProps && Object.entries(selectedElementProps).map(([key, val]) => (
                      <div key={key} className={styles.resultItem}>
                        <span className={styles.resultLabel}>{key}</span>
                        <span className={styles.resultValue} style={{ fontSize: 11, wordBreak: 'break-all' }}>{val}</span>
                      </div>
                    ))}
                    {!selectedElementProps && (
                      <div className={styles.resultItem}>
                        <span className={styles.resultLabel}>Element ID</span>
                        <span className={styles.resultValue} style={{ fontSize: 11 }}>{selectedElementGuid}</span>
                      </div>
                    )}
                    <div style={{ padding: '12px 0', borderTop: '1px solid hsl(0,0%,18%)', marginTop: 8 }}>
                      <div style={{ fontSize: 11, color: 'hsl(0,0%,50%)', marginBottom: 8 }}>
                        💡 To map a defect to this element, go to the Defects tab and click &quot;Map&quot; on an unmapped defect.
                      </div>
                    </div>
                  </>
                ) : (
                  <div style={{ padding: '24px 0', textAlign: 'center', color: 'hsl(0,0%,44%)', fontSize: 13 }}>
                    <div style={{ marginBottom: 8 }}>🖱️</div>
                    Click on any element in the 3D model to inspect its properties.
                    <div style={{ fontSize: 11, marginTop: 8, color: 'hsl(0,0%,36%)' }}>
                      Hover over elements to see them highlighted in blue.
                    </div>
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
