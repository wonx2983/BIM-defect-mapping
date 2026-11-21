# Automation of Mapping Quality Defects in BIM Environment (DefectSync)
# DefectSync: Mapping Concrete Defects to BIM

DefectSync is a B.Tech project that connects visual inspections to a building information model. A detector finds suspected defects in images or sampled video frames. A separate spatial mapper uses a calibrated camera and IFC geometry to place observations on the model.

- **Full technical report:** [Both student contributions, algorithms, novelty, and the inspection workflow (PDF)](docs/DefectSync-project-report.pdf)
- **Recorded demonstration:** [Simulation evidence](runs/bim-simulation/README.md) · [56-second walkthrough](runs/bim-simulation/simulation.mp4)
- **Deployment and testing:** [Deployment and acceptance guide](docs/deployment.md)

## Two student contributions

| Part | Scope | Output |
| --- | --- | --- |
| **Student 1: Defect detection** | Image and frame handling, YOLO inference, confidence and severity estimates, annotated inspection evidence, and detection evaluation. | Class, confidence, bounding box in the original image, dimensions in pixels, and source evidence. |
| **Student 2: BIM mapping** | IFC viewer and geometry, marker placement, camera calibration, pixel-to-ray projection, element assignment, and mapped inspection workflow. | IFC model and element GUID, 3D hit location, mapping status, and a pin the inspector can review. |

The handoff is the detection box centre in original image pixels plus the identity of the source camera and frame. The mapper requires the pose, intrinsics, and IFC model for that camera. It can also be tested independently with known reference pixels.

## User workflow

1. Sign in, create or open a project, and upload the correct IFC version in the **BIM Viewer**.
2. For an ad hoc inspection, open **Detection** to upload a photo or **Video** to process sampled frames. Review the boxes, classes, and confidence scores. Calibration is needed for automatic spatial assignment.
3. For automated BIM mapping, open **Markers** in the viewer. Search for the IFC element, select the face at the marker centre, and check the facing direction and orientation. Save to assign an ArUco ID. Print the pattern at actual size, measure its black square, and mount it at the registered position.
4. Open **Cameras** and register an authorized RTSP source with its horizontal field of view and inspection interval. One visible registered marker can calibrate a fixed camera. Preview the frame and retry calibration if needed. With the scheduler online, a calibrated camera can start periodic inspections without a second registration.
5. Review mapped pins and unresolved observations. Verify the element and original evidence, update the record, and export the inspection list as CSV.

## Validate the detector and video workflow

The **Video** upload page offers fixed-camera grouping for a stationary view with no pan, zoom or cuts. Same-class boxes with at least 0.50 IoU can join a group when the last sighting was within two seconds. Each group accepts at most one detection per sampled frame. The result preserves the per-frame detections, and auto-save writes one inspection record per group with the highest-confidence evidence and the first and last sighting times. The group count estimates repeated sightings in image space. A long gap starts a new group. Leave grouping off for handheld or edited footage.

The optional repeat-confirmation control saves only groups seen in at least two samples within the two-second association window. Review single sightings in the frame gallery. See the [detector and video experiments](runs/detector-review/README.md) for the measured effects on false alerts, missed defects and inference time.

For a fixed-threshold detector test, create a JSON manifest from an independent labelled set. Use the [simulation manifest](runs/bim-simulation/detector-evaluation-manifest.json) as a format example. For each image give its path relative to the manifest, a capture-session ID, and original-image pixel boxes under `labels`. Use an empty list only for an image verified to contain none of the evaluated classes. Pass `--class crack` for a crack-only set so unlabelled classes are excluded from scoring. Keep the test sessions separate from sessions used for training or threshold selection.

From `backend`, run:

```bash
python -m ml.evaluate_detector \
  --manifest /path/to/test-manifest.json \
  --out /path/to/detector-evaluation.json \
  --confidence 0.25 --match-iou 0.50
```

The output records the model, manifest and image hashes, per-class precision and recall, matched boxes, false positives, misses, and alerts on clean images. A class with no reference labels has undefined recall, written as `null`. Use a separate precision–recall sweep for AP and mAP.

## How it works

- **Detection:** The bundled YOLOv11 checkpoint recognizes crack, spalling, exposed rebar, corrosion, efflorescence, scaling, and honeycombing. The confidence threshold filters boxes. Severity is an estimate; image measurements are in pixels unless a valid physical measurement method is supplied.
- **Calibration:** The registry identifies a printed pattern by dictionary and ID. OpenCV matches observed pixel corners to the known 3D square, estimates the camera pose with PnP, and checks reprojection error. A moved camera or changed lens/stream parameters needs recalibration.
- **Mapping:** The mapper back-projects the detection box centre into a world ray. IfcOpenShell provides world-space meshes, frustum culling narrows the candidates, and ray-triangle intersection selects the nearest surface hit. The result records the IFC GlobalId and 3D hit point in metres. Observations of the same class near one another on the same element can be merged.
- **System:** Next.js and Three.js/web-ifc provide the UI. FastAPI serves inspections and geometry metadata. PostgreSQL stores project, calibration and defect records. Authorized local storage holds IFC and evidence. A standalone worker runs scheduled inspection batches.

### Tiled detection for wide camera views

Set `ML_TILED_INFERENCE=true` in the backend environment and restart the API (and the
monitoring worker, if used). Each inspected frame gets the usual full-frame YOLO pass
plus passes over overlapping crops. The detector converts every box back to the
original image coordinates and suppresses duplicate boxes of the same class before
severity scoring, drawing overlays, or BIM mapping.

Defaults: `ML_TILE_SIZE=256` source pixels, `ML_TILE_OVERLAP=0.20`, and `ML_MAX_TILES=16`.
The grid increases the tile size when necessary to keep the full frame covered
within that budget. The YOLO input size and confidence threshold stay the same
for all passes. Tiling is off by default: it costs more per frame and can surface
additional false positives, so compare it on representative positive and clean
frames before enabling it for a camera workflow.

## Schependomlaan simulation

The recorded demonstration used the Schependomlaan IFC, a fixed 1280 × 720 virtual camera, one registered ArUco marker, and **two simulated cracks**. The detector used a 0.25 confidence threshold and class-correct matches at intersection over union (IoU) of at least 0.50.

| Test | Recorded result |
| --- | --- |
| Detection | **2 of 2 simulated cracks detected**, with two false alerts on the crack frame and three on the clean control. |
| BIM mapping by itself | Both reference pixels mapped to the correct IFC walls. Mean 3D position error was **4.35 cm**. |
| Detection to BIM | Both matched YOLO boxes mapped to the correct walls. Position errors were **11.35 cm** and **10.36 cm**. |
| Calibration control | The registered marker was decoded and the marker-free frame was rejected. |

This selected demonstration shows the pipeline working in one controlled scene. Detecting both examples does not establish 100% accuracy or predict performance on real sites. The [raw measurements](runs/bim-simulation/results.json) preserve the evidence.

## Run locally

Prerequisites: Python 3.11, Node.js 22.13+, npm, and PostgreSQL. Copy the root `.env.example` to `.env` and configure the database connections and JWT signing secret. Configure the approved camera hosts for RTSP use. Keep the populated file local.

From `backend`, activate a Python virtual environment, then run:

```bash
python -m pip install -r requirements.txt
alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

From `frontend`, in another terminal:

```bash
npm ci
npm run dev
```

Open the [local dashboard](http://localhost:3000), [BIM Viewer](http://localhost:3000/viewer), or [API documentation](http://localhost:8000/docs). Check [backend readiness](http://localhost:8000/ready). For scheduled camera inspections, also run `python -m app.services.scheduler` from the backend environment with `SCHEDULER_ENABLED=true`.

Install `backend/requirements-dev.txt` to run the backend tests from `backend` (`python -m pytest tests -q`). From `frontend`, run `npm run lint`, `npm run typecheck`, and `npm run build`. To reproduce the virtual-camera walkthrough, see the [simulation instructions](runs/bim-simulation/README.md).
An inspection platform under active field validation for real-time concrete defect detection, severity assessment, and automated 3D BIM spatial mapping — built for construction professionals, site engineers, and quality assurance managers.

The [recorded Schependomlaan simulation](runs/bim-simulation/README.md) includes the virtual camera frames, detection and mapping scores, and a short walkthrough.

---

## Product Vision

**DefectSync** bridges computer vision and structural engineering by transforming 2D visual inspection into 3D Building Information Models (IFC/BIM):

1. **Capture** — Upload inspection images/videos or stream live from RTSP IP cameras and site webcams.
2. **Detect** — Fine-tuned YOLOv11 model identifies 7 distinct concrete defect classes in real-time.
3. **Grade** — Severity classification on a 4-tier scale (`Low`, `Medium`, `High`, `Critical`) with dimensional pixel/physical estimation.
4. **Spatial Auto-Map (Phase 2)** — Inverted pinhole raycasting intersects 3D BIM element geometry to autonomously map defects to exact structural element GUIDs and 3D surface coordinates $(X, Y, Z)$ using ArUco PnP calibration.
5. **De-duplicate** — 3D Euclidean spatial filtering prevents duplicate defect logging across video frames and multi-camera overlaps.
6. **Manage & Audit** — Full lifecycle tracking (Detected → Confirmed → Assigned → In Progress → Resolved → Verified) with defect change history and CSV export.

---

## 7-Class Defect Taxonomy

The vision system is trained on an extensive benchmark of concrete structures and detects 7 classes:

| # | Class Key | Defect Type | Primary Detection Features |
|---|---|---|---|
| 0 | `crack` | Surface & Structural Cracks | Linear fissures, longitudinal, transverse, alligator cracking |
| 1 | `spalling` | Concrete Spalling | Surface depressions, fractured concrete flakes, missing concrete |
| 2 | `exposed_rebar` | Exposed Reinforcement Bars | Visible steel rebar due to deep spalling/cover loss |
| 3 | `corrosion` | Rust Staining & Rebar Corrosion | Rust bleeding, iron oxide oxidation stains on concrete surface |
| 4 | `efflorescence` | Salt & Mineral Leaching | White crystalline salt deposits from moisture migration |
| 5 | `scaling` | Surface Scaling / Peeling | Shallow surface deterioration, loss of mortar layer |
| 6 | `honeycombing` | Honeycombing & Voids | Coarse aggregate clusters with missing mortar voids |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (Next.js 15)                              │
│  ┌────────────┐  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────┐ │
│  │ Dashboard  │  │ Defect Detection │  │ 3D BIM Viewer    │  │ Reports & BCF  │ │
│  │ & Auth     │  │ (Upload/RTSP)    │  │ (web-ifc +       │  │ Analytics      │ │
│  │            │  │                  │  │  Three.js Pins)  │  │                │ │
│  └────────────┘  └──────────────────┘  └──────────────────┘  └────────────────┘ │
└──────────────────────────┬──────────────────────────────────────────────────────┘
                           │ REST API (JSON)
┌──────────────────────────┴──────────────────────────────────────────────────────┐
│                            BACKEND (FastAPI / Python)                           │
│  ┌────────────┐  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────┐ │
│  │ Auth &     │  │ YOLOv11 Detector │  │ Calibration      │  │ Auto-Mapper &  │ │
│  │ Project    │  │ & Severity       │  │ (ArUco + PnP     │  │ 3D Raycasting  │ │
│  │ Management │  │ Engine           │  │  Pose Recovery)  │  │ (Trimesh / MT) │ │
│  └────────────┘  └──────────────────┘  └──────────────────┘  └────────────────┘ │
│  ┌────────────┐  ┌──────────────────┐  ┌──────────────────┐                     │
│  │ Frustum    │  │ ifcopenshell     │  │ Spatial 3D       │                     │
│  │ Culling    │  │ Geometry Cache   │  │ De-duplication   │                     │
│  └────────────┘  └──────────────────┘  └──────────────────┘                     │
└──────────────────────────┬──────────────────────────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────────────────────────┐
│                              DATA & STORAGE LAYER                               │
│  ┌─────────────────────────┐  ┌──────────────────────┐  ┌────────────────────┐  │
│  │ PostgreSQL (Neon Cloud) │  │ Static / Uploads     │  │ Model Weights      │  │
│  │ - Users & Roles         │  │ - Inspection Images  │  │ - YOLOv11s weights │  │
│  │ - Projects & Cameras    │  │ - Annotated Images   │  │   (bundled in repo)│  │
│  │ - Markers & Defects     │  │ - IFC BIM Models     │  │                    │  │
│  └─────────────────────────┘  └──────────────────────┘  └────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 2: Automated Defect-to-BIM Spatial Mapping

Phase 2 replaces manual zone tagging with mathematical, pixel-to-mesh spatial raycasting:

1. **Fiducial Marker Registry (`/api/v1/markers/`)**:
   - Register printed ArUco markers (`DICT_4X4_50`) placed on structural elements at known BIM coordinates $(X, Y, Z)$.
2. **Camera Calibration (`/api/v1/calibration/{id}/calibrate`)**:
   - Captures an RTSP frame, extracts sub-pixel ArUco corners, computes intrinsics $K$ from horizontal FOV, and solves Perspective-n-Point (`solvePnPRansac` + Levenberg-Marquardt refinement) to recover camera pose $(R, \mathbf{t})$.
3. **Frustum Culling**:
   - Computes a 6-plane view frustum in world coordinates to restrict candidate BIM elements to those physically visible to the camera.
4. **Inverse Pinhole Raycasting (`/api/v1/calibration/{id}/auto-detect`)**:
   - Converts 2D bounding box centroids into 3D rays:
     $$\mathbf{d}_{\text{cam}} = \text{normalize}\left(\left[\frac{u - c_x}{f_x}, \frac{v - c_y}{f_y}, 1\right]^T\right), \quad \mathbf{d}_{\text{world}} = R^T \cdot \mathbf{d}_{\text{cam}}$$
   - Accelerated Möller–Trumbore ray-mesh intersection against IFC triangulated meshes identifies the exact structural member GUID and surface coordinate.
5. **Spatial De-duplication**:
   - Groups observations with $\Delta\text{dist} \le 0.50\text{ m}$ on the same member, retaining the higher-confidence observation and updating timestamps without creating duplicate defect records.

---

## Technical Documentation & Guides

Comprehensive technical references are included in the repository:
- **Executive Walkthrough & Mathematical Report (PDF)**: [`docs/automated_defect_bim_mapping_walkthrough.pdf`](docs/automated_defect_bim_mapping_walkthrough.pdf)
- **Phase 2 Implementation Architecture**: [`docs/automated_defect_bim_mapping_plan.md`](docs/automated_defect_bim_mapping_plan.md)

---

## Getting Started After Cloning

### Prerequisites
- **Git**
- **Python 3.11+**
- **Node.js 18+** & **npm**

---

### Step 1: Clone the Repository
```bash
git clone https://github.com/wonx2983/BIM-defect-mapping.git
cd BIM-defect-mapping
```

---

### Step 2: Configure Environment (`.env`)
Place your `.env` file in the root project directory (`BIM-defect-mapping/.env`):
```bash
# You can copy the template if starting fresh:
cp .env.example .env
```
*(Both the backend and ML services read configuration directly from this single root file.)*

> **Note on Model Weights:** The trained defect detection weights (`backend/ml/models/defect_detector.pt`) are already bundled in the repository, so no separate model download is needed.

---

### Step 3: Backend Setup

#### Windows (PowerShell)
```powershell
# 1. Navigate to backend directory
cd backend

# 2. Create virtual environment
python -m venv venv

# 3. Activate virtual environment
.\venv\Scripts\Activate.ps1
# (If execution policy restricts scripts: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass)

# 4. Install dependencies
pip install -r requirements.txt

# 5. Apply database migrations
alembic upgrade head

# 6. Start the FastAPI backend server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### macOS / Linux (Terminal / bash / zsh)
```bash
# 1. Navigate to backend directory
cd backend

# 2. Create virtual environment
python3 -m venv venv

# 3. Activate virtual environment
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Apply database migrations
alembic upgrade head

# 6. Start the FastAPI backend server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

### Step 4: Frontend Setup (New Terminal Window)

#### Windows, macOS & Linux
```bash
# 1. Navigate to frontend directory
cd frontend

# 2. Install dependencies
npm install

# 3. Start development server
npm run dev
```

---

### Step 5: Verification & Automated Tests

To verify the entire calibration, raycasting, frustum culling, and de-duplication pipeline synthetically (with zero hardware required):

```bash
cd backend
python tests/test_phase2_synthetic_e2e.py
```
*Expected: 9/9 tests pass (reprojection error < 0.2 px, ray hit accuracy < 2 mm).*

---

### Step 6: Access the Application

- **Frontend Web Dashboard**: [http://localhost:3000](http://localhost:3000)
- **3D BIM & Camera Viewer**: [http://localhost:3000/viewer](http://localhost:3000/viewer)
- **Interactive API Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Backend Health Check**: [http://localhost:8000/health](http://localhost:8000/health)


## Hardening and deployment status

See [deployment and acceptance](docs/deployment.md) for the private-media architecture,
required schema migration, scheduled camera worker, test commands, and field acceptance
requirements. Reports now provide CSV export and recorded defect changes; BCF export
is not implemented. The bundled detector and heuristic severity must be validated on
independent site data before operational reliance. Synthetic tests are not a production
readiness certificate.
