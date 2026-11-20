# Automation of Mapping Quality Defects in BIM Environment (DefectSync)

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
