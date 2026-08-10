# Automation of Mapping Quality Defects in BIM Environment

A professional-grade, production-ready platform for real-time construction defect detection, severity assessment, and automated BIM mapping — built for real construction professionals, site engineers, and quality managers.

---

## Product Vision

**DefectSync** (working title) is a full-stack SaaS tool that enables construction teams to:
1. **Capture** — Upload site images/video or connect a live camera feed
2. **Detect** — AI identifies multi-class structural defects in real-time (cracks, spalling, exposed rebar, corrosion, water seepage, honeycombing)
3. **Grade** — Each defect is automatically scored on a 4-tier severity scale (Low → Medium → High → Critical) with dimensional analysis
4. **Map** — Defects are pinned onto the project's 3D BIM/IFC model with full spatial context
5. **Manage** — Track defect lifecycle from detection → assignment → remediation → verification, with full audit trails

---

## System Architecture (High-Level)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Next.js 15)                        │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │ Dashboard │  │ Defect       │  │ 3D BIM       │  │ Reports &  │ │
│  │ & Auth    │  │ Detection UI │  │ Viewer       │  │ Analytics  │ │
│  │           │  │ (Upload/     │  │ (IFC Viewer  │  │            │ │
│  │           │  │  Camera)     │  │  + Defect    │  │            │ │
│  │           │  │              │  │  Markers)    │  │            │ │
│  └──────────┘  └──────────────┘  └──────────────┘  └────────────┘ │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ REST + WebSocket
┌──────────────────────────┴──────────────────────────────────────────┐
│                     BACKEND (Python / FastAPI)                       │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │ Auth &   │  │ ML Inference │  │ BIM/IFC      │  │ Project &  │ │
│  │ Tenant   │  │ Service      │  │ Processing   │  │ Defect     │ │
│  │ Manager  │  │ (YOLO +      │  │ Service      │  │ CRUD       │ │
│  │          │  │  Severity)   │  │              │  │            │ │
│  └──────────┘  └──────────────┘  └──────────────┘  └────────────┘ │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │ Celery   │  │ BCF Export   │  │ Report Gen   │                  │
│  │ Workers  │  │ Service      │  │ (PDF/Excel)  │                  │
│  └──────────┘  └──────────────┘  └──────────────┘                  │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────────────┐
│                        DATA / INFRA LAYER                           │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │PostgreSQL│  │ Redis        │  │ S3/MinIO     │  │ ML Model   │ │
│  │ (+ RLS)  │  │ (Cache +     │  │ (Files, IFC, │  │ Registry   │ │
│  │          │  │  Task Queue) │  │  Images)     │  │            │ │
│  └──────────┘  └──────────────┘  └──────────────┘  └────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

---

## User Review Required

> [!IMPORTANT]
> **Technology choices that need your sign-off:**
> 1. **Frontend Framework**: Next.js 15 (App Router, TypeScript) — industry standard for this kind of dashboard-heavy SaaS
> 2. **Backend Framework**: Python FastAPI — ideal for ML inference integration (same ecosystem as PyTorch/Ultralytics) and async API performance
> 3. **BIM Viewer**: **That Open Engine** (`@thatopen/components`, formerly IFC.js) — open-source, web-native, supports IFC loading, fragment optimization, and custom markers. Alternative: xeokit SDK (more enterprise, AGPL licensed)
> 4. **ML Model**: YOLOv11 (Ultralytics) for object detection + custom severity classification head
> 5. **Database**: PostgreSQL with Row-Level Security for multi-tenancy

> [!WARNING]
> **Training data**: We will start with public datasets from Roboflow Universe (concrete defects, spalling, rebar) and SDNET2018. For production accuracy, the platform includes a **custom annotation pipeline** so clients can upload and label their own site-specific data and retrain models. This is essential because construction defects vary significantly across materials, climates, and building types.

> [!CAUTION]
> **IFC File Handling**: IFC files can be extremely large (500MB+). The architecture uses a **server-side conversion pipeline** that converts raw `.ifc` to optimized `.frag` (Fragments) format before serving to the browser. Users never interact with raw IFC in the frontend — this prevents browser crashes and ensures smooth 60fps rendering.

---

## Open Questions

> [!IMPORTANT]
> **Q1: Deployment target** — Are you planning to self-host this (Docker/on-prem) or deploy to cloud (AWS/GCP/Azure)? This affects the infrastructure code we write. For now, I'll design for **Docker Compose** (local dev) with cloud-readiness.

> [!IMPORTANT]
> **Q2: Authentication provider** — Build custom auth (JWT-based) or integrate a managed provider (Clerk, Auth0, Supabase Auth)? Custom gives full control; managed providers save weeks of development. I recommend **custom JWT auth** for this project so everything is self-contained.

> [!IMPORTANT]
> **Q3: Video processing** — For video feeds, should we support real-time webcam/RTSP streams (requires WebSocket + frame-by-frame inference), or is batch video upload + processing sufficient for v1? Real-time adds significant complexity. I recommend **batch upload for v1** with real-time as a v2 feature.

> [!IMPORTANT]
> **Q4: Defect classes** — I'm proposing these 6 initial defect classes based on industry standards. Should we add/remove any?
> 1. **Cracks** (structural, hairline, pattern cracking)
> 2. **Spalling** (surface deterioration, delamination)
> 3. **Exposed Rebar** (reinforcement exposure)
> 4. **Corrosion** (rust staining, steel deterioration)
> 5. **Water Seepage** (moisture ingress, efflorescence)
> 6. **Honeycombing** (voids in concrete)

---

## Proposed Changes

### Component 1: Project Foundation & Configuration

Sets up the monorepo, tooling, linting, CI/CD configuration, and shared types.

#### [NEW] Root Configuration Files

| File | Purpose |
|------|---------|
| `package.json` | Monorepo root with workspace config |
| `docker-compose.yml` | Full-stack local dev environment (Postgres, Redis, MinIO, Backend, Frontend) |
| `docker-compose.prod.yml` | Production-optimized compose |
| `.env.example` | Environment variable template |
| `Makefile` | Developer workflow shortcuts (`make dev`, `make test`, `make migrate`) |
| `README.md` | Professional README with setup, architecture diagrams, screenshots |

#### [NEW] Directory Structure

```
BTP/
├── frontend/                    # Next.js 15 application
│   ├── src/
│   │   ├── app/                 # App Router pages
│   │   │   ├── (auth)/          # Login, Register, Forgot Password
│   │   │   ├── (dashboard)/     # Authenticated layout
│   │   │   │   ├── projects/    # Project management
│   │   │   │   ├── detect/      # Defect detection interface
│   │   │   │   ├── viewer/      # 3D BIM viewer
│   │   │   │   ├── reports/     # Analytics & report generation
│   │   │   │   └── settings/    # User, org, model config
│   │   │   └── layout.tsx
│   │   ├── components/
│   │   │   ├── ui/              # Design system primitives
│   │   │   ├── bim/             # BIM viewer components
│   │   │   ├── detection/       # ML detection components
│   │   │   ├── defects/         # Defect cards, lists, modals
│   │   │   └── charts/          # Analytics visualizations
│   │   ├── lib/                 # Utilities, API client, hooks
│   │   ├── stores/              # Zustand state management
│   │   └── styles/              # Global CSS, design tokens
│   ├── public/
│   │   └── wasm/                # web-ifc WASM binaries
│   └── next.config.ts
│
├── backend/                     # Python FastAPI application
│   ├── app/
│   │   ├── api/
│   │   │   ├── v1/
│   │   │   │   ├── auth.py      # Authentication endpoints
│   │   │   │   ├── projects.py  # Project CRUD
│   │   │   │   ├── defects.py   # Defect management
│   │   │   │   ├── detection.py # ML inference endpoints
│   │   │   │   ├── bim.py       # IFC upload & processing
│   │   │   │   ├── reports.py   # Report generation
│   │   │   │   └── bcf.py       # BCF export/import
│   │   │   └── deps.py          # Shared dependencies
│   │   ├── core/
│   │   │   ├── config.py        # Settings & env management
│   │   │   ├── security.py      # JWT, password hashing
│   │   │   └── exceptions.py    # Custom exception handlers
│   │   ├── models/              # SQLAlchemy ORM models
│   │   │   ├── user.py
│   │   │   ├── project.py
│   │   │   ├── defect.py
│   │   │   ├── bim_model.py
│   │   │   └── inspection.py
│   │   ├── schemas/             # Pydantic request/response schemas
│   │   ├── services/
│   │   │   ├── ml_service.py    # YOLO inference + severity
│   │   │   ├── bim_service.py   # IFC parsing, element extraction
│   │   │   ├── severity_engine.py  # Multi-factor severity scoring
│   │   │   └── report_service.py   # PDF/Excel generation
│   │   ├── tasks/               # Celery async tasks
│   │   │   ├── ifc_processing.py   # Background IFC → Fragment conversion
│   │   │   └── batch_detection.py  # Batch image/video processing
│   │   └── db/
│   │       ├── session.py       # Database session management
│   │       └── migrations/      # Alembic migrations
│   ├── ml/
│   │   ├── models/              # Trained model weights (.pt files)
│   │   ├── training/
│   │   │   ├── train_detector.py    # YOLOv11 training script
│   │   │   ├── train_severity.py    # Severity classifier training
│   │   │   └── data.yaml            # Dataset configuration
│   │   └── inference/
│   │       ├── detector.py          # Detection pipeline
│   │       ├── severity_classifier.py  # Severity grading
│   │       └── postprocessor.py     # NMS, filtering, aggregation
│   ├── requirements.txt
│   └── Dockerfile
│
├── shared/                      # Shared types & constants
│   └── defect_classes.json      # Defect taxonomy
│
└── docs/                        # Documentation
    ├── api/                     # Auto-generated API docs
    ├── architecture/            # Architecture diagrams
    └── user-guide/              # End-user documentation
```

---

### Component 2: ML Defect Detection Pipeline

The core intelligence layer — multi-class defect detection with severity grading.

#### [NEW] `backend/ml/training/train_detector.py`
- YOLOv11 fine-tuning script for 6-class construction defect detection
- Supports `yolo11n` (fast/edge), `yolo11m` (balanced), `yolo11l` (max accuracy)
- Data augmentation pipeline: rotation, brightness/contrast jitter, Gaussian noise, perspective transforms, random crop, mosaic
- Exports trained model to ONNX for cross-platform inference
- W&B / MLflow integration for experiment tracking

#### [NEW] `backend/ml/training/train_severity.py`
- **Severity classification model** — a lightweight ResNet-18/EfficientNet-B0 classifier
- Takes the cropped defect region from the YOLO detector as input
- 4-class output: `Low`, `Medium`, `High`, `Critical`
- Severity is determined by a **multi-factor scoring algorithm**:

| Factor | Weight | Description |
|--------|--------|-------------|
| Defect type | 25% | Exposed rebar inherently more severe than hairline crack |
| Area ratio | 25% | Defect area relative to element surface area |
| Dimension analysis | 20% | Crack width, spalling depth (from bounding box geometry) |
| Location context | 15% | Proximity to load-bearing elements (from BIM metadata) |
| Count density | 15% | Number of defects in a localized region |

#### [NEW] `backend/ml/inference/detector.py`
- Unified inference pipeline: `Image → YOLO Detection → Crop → Severity Classification → Results`
- Supports batch inference (multiple images)
- Returns structured JSON with bounding boxes, class labels, confidence scores, severity grades
- GPU acceleration (CUDA) with CPU fallback
- Model hot-reloading for zero-downtime updates

#### [NEW] `backend/ml/inference/postprocessor.py`
- Non-Maximum Suppression (NMS) with configurable IoU threshold
- Confidence thresholding (configurable per class)
- Defect clustering — groups nearby defects for density analysis
- Annotation rendering — draws bounding boxes and labels on images for visualization

---

### Component 3: FastAPI Backend

Production-grade API server with multi-tenant architecture.

#### [NEW] `backend/app/api/v1/detection.py`
Key endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/detect/image` | Upload image → run inference → return defects |
| `POST` | `/api/v1/detect/batch` | Upload multiple images → async batch processing |
| `POST` | `/api/v1/detect/video` | Upload video → extract frames → batch inference |
| `GET` | `/api/v1/detect/status/{task_id}` | Check async processing status |
| `GET` | `/api/v1/detect/results/{task_id}` | Get completed results |
| `PUT` | `/api/v1/detect/config` | Update detection thresholds per project |

#### [NEW] `backend/app/api/v1/bim.py`
Key endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/bim/upload` | Upload IFC file → queue conversion → return model ID |
| `GET` | `/api/v1/bim/models/{id}` | Get model metadata + fragment download URL |
| `GET` | `/api/v1/bim/models/{id}/elements` | List all IFC elements with metadata |
| `POST` | `/api/v1/bim/models/{id}/defects` | Map defect to BIM element (spatial link) |
| `GET` | `/api/v1/bim/models/{id}/defects` | Get all defects mapped to this model |
| `POST` | `/api/v1/bim/models/{id}/bcf/export` | Export defects as BCF 2.1 file |
| `POST` | `/api/v1/bim/models/{id}/bcf/import` | Import BCF issues into defect tracker |

#### [NEW] `backend/app/api/v1/projects.py`
- Full project lifecycle management
- Each project has: name, address, client info, IFC models, inspections, defect history
- Role-based access: `Owner`, `Manager`, `Inspector`, `Viewer`
- Project templates for common building types

#### [NEW] `backend/app/services/severity_engine.py`
- Combines ML severity prediction with rule-based domain logic
- **User-configurable severity thresholds** per project (different standards for bridges vs residential)
- Generates structured severity reports with remediation recommendations
- Priority scoring that factors in: severity × affected area × structural criticality

#### [NEW] `backend/app/services/bim_service.py`
- Server-side IFC parsing using `ifcopenshell` (Python)
- Extracts element hierarchy, properties, materials, and spatial structure
- Converts IFC → Fragments (`.frag`) using `web-ifc` WASM (via subprocess or Node service)
- Spatial indexing of BIM elements for nearest-element matching when mapping defects

#### [NEW] `backend/app/models/defect.py`
Core defect data model:
```
Defect
├── id (UUID)
├── project_id (FK)
├── inspection_id (FK)
├── bim_element_guid (nullable — linked after mapping)
├── defect_class (enum: crack, spalling, rebar, corrosion, seepage, honeycomb)
├── severity (enum: low, medium, high, critical)
├── severity_score (float 0-1)
├── confidence (float 0-1)
├── bbox (JSON: {x, y, w, h})
├── source_image_url (S3 path)
├── annotated_image_url (S3 path)
├── world_position (JSON: {x, y, z} — 3D coords on BIM model)
├── dimensions (JSON: {width_mm, height_mm, area_mm2})
├── status (enum: detected, confirmed, assigned, in_progress, resolved, verified)
├── assigned_to (FK → User, nullable)
├── notes (text)
├── remediation_recommendation (text — AI-generated)
├── created_at, updated_at
└── created_by (FK → User)
```

---

### Component 4: Next.js Frontend

Premium, dark-mode-first UI with real-time interactivity.

#### Design System

| Token | Value | Purpose |
|-------|-------|---------|
| Primary | `hsl(210, 100%, 56%)` | Actions, links, active states |
| Critical | `hsl(0, 84%, 60%)` | Critical severity, destructive actions |
| High | `hsl(25, 95%, 53%)` | High severity warnings |
| Medium | `hsl(45, 93%, 47%)` | Medium severity cautions |
| Low | `hsl(142, 71%, 45%)` | Low severity, success states |
| Surface | `hsl(222, 47%, 11%)` | Card backgrounds (dark mode) |
| Background | `hsl(224, 71%, 4%)` | Page background (dark mode) |
| Font | Inter (Google Fonts) | Clean, professional typography |
| Border Radius | `12px` | Modern rounded corners |
| Glassmorphism | `backdrop-filter: blur(16px)` | Premium panel effects |

#### [NEW] Detection Interface (`frontend/src/app/(dashboard)/detect/page.tsx`)
- **Drag-and-drop upload zone** with animated border, file validation (JPEG, PNG, MP4)
- **Real-time inference progress** — WebSocket connection shows detection happening live
- **Results gallery** — grid of analyzed images with annotated bounding boxes overlay
- **Defect detail panel** — click any detection to see:
  - Zoomed crop of the defect region
  - Class label + confidence percentage
  - Severity badge (color-coded: green/yellow/orange/red)
  - Dimensional estimates
  - AI-generated remediation suggestion
  - "Map to BIM" button → opens viewer with element selection
- **Batch mode** — upload entire inspection folders, process async, get notification when done
- **Detection settings** — adjustable confidence thresholds, model selection (speed vs accuracy)

#### [NEW] 3D BIM Viewer (`frontend/src/app/(dashboard)/viewer/page.tsx`)
- **Full 3D IFC viewer** built with That Open Engine (`@thatopen/components`)
- **Model tree sidebar** — hierarchical view of building stories → spaces → elements
- **Defect markers** — 3D sprite markers placed on the model:
  - Color-coded by severity (green/yellow/orange/pulsing red for critical)
  - Click to expand defect details panel
  - Filter by severity, defect type, status, date range
- **Defect mapping workflow**:
  1. User selects a detected defect from the sidebar
  2. User clicks on a BIM element in the 3D view (raycasting picks the element)
  3. System records the `IFC GlobalId` + click position as the defect's spatial location
  4. Marker appears on the model with defect details
- **Section planes** — slice through the model to inspect internal defects
- **Measurement tools** — distance and area measurement on the 3D model
- **BCF viewpoint capture** — save camera position + visible defects as shareable BCF viewpoints
- **Heatmap overlay** — density heatmap showing concentration of defects across building zones

#### [NEW] Dashboard (`frontend/src/app/(dashboard)/page.tsx`)
- **Project overview cards** with defect counts, severity distribution, and progress rings
- **Recent activity feed** — latest detections, status changes, assignments
- **Severity distribution chart** — animated doughnut chart (Recharts)
- **Defect trend line** — defects over time, filterable by project/type
- **Critical alerts banner** — pulsing notification for newly detected critical defects
- **Quick actions** — "New Inspection", "Upload Images", "Open Viewer"

#### [NEW] Reports & Analytics (`frontend/src/app/(dashboard)/reports/page.tsx`)
- **Pre-built report templates**: Inspection Summary, Defect Register, Severity Analysis, Progress Report
- **Customizable filters**: date range, building zone, defect class, severity, status
- **Export formats**: PDF (professional layout with company branding), Excel (raw data), BCF (BIM-native)
- **Comparative analytics**: before/after remediation, cross-project benchmarking
- **Printable inspection checklists** auto-generated from BIM element data

#### [NEW] Settings & Configuration (`frontend/src/app/(dashboard)/settings/page.tsx`)
- **Organization settings** — company name, logo (for branded reports), team members
- **Project configuration** — severity thresholds, defect classes, notification rules
- **Model management** — upload/retrain custom detection models with user's own labeled data
- **API key management** — for third-party integrations
- **Notification preferences** — email/in-app alerts for critical defects

---

### Component 5: BIM Integration Layer

The bridge between detected defects and the 3D building model.

#### [NEW] `frontend/src/components/bim/IFCViewer.tsx`
- Core 3D viewer component using That Open Engine
- Handles IFC/Fragment loading, camera controls, raycasting
- Custom marker management system:
  - `DefectMarker3D`: Positioned at world coordinates, scales with zoom
  - `MarkerCluster`: Groups nearby markers at far zoom levels
  - `MarkerTooltip`: HTML overlay showing defect summary on hover
- Performance optimizations:
  - Fragment-based loading (pre-processed on server)
  - Level-of-detail rendering
  - Frustum culling for markers
  - Web Worker for heavy parsing operations

#### [NEW] `frontend/src/components/bim/ElementPicker.tsx`
- Interactive BIM element selection
- On click: highlights element, shows properties panel (IFC metadata: material, dimensions, story)
- "Link Defect" mode: maps the selected defect to the picked element
- Element search: find elements by name, type, or GlobalId

#### [NEW] `frontend/src/components/bim/DefectOverlayPanel.tsx`
- Side panel that appears when a defect marker is clicked in the 3D view
- Shows: original image, annotated crop, severity badge, status, assignee, timeline
- Quick actions: change status, reassign, add notes, export BCF viewpoint

#### [NEW] `backend/app/services/spatial_mapper.py`
- **Automatic element suggestion**: When a user provides approximate coordinates (e.g., "3rd floor, north wall"), the system queries the BIM model's spatial structure to suggest matching IFC elements
- **Nearest-element matching**: Given a 3D click position, finds the closest IFC element using bounding box intersection
- **Zone-based grouping**: Aggregates defects by building story, space, or zone for reporting

---

### Component 6: BCF Integration (BIM Collaboration Format)

Industry-standard interoperability for sharing defects with other BIM tools (Revit, Navisworks, etc.).

#### [NEW] `backend/app/api/v1/bcf.py`
- **BCF 2.1 export**: Converts defects → BCF topics with viewpoints, comments, and markup
- **BCF import**: Reads BCF files from external tools, creates defect records
- Each BCF topic includes:
  - Camera viewpoint (position, direction, up vector)
  - Selected/visible components
  - Defect image as snapshot
  - Severity and status as extensions
- Compatible with: Revit, Navisworks, Solibri, BIMcollab, Trimble Connect

---

### Component 7: Data Pipeline & Storage

#### [NEW] `docker-compose.yml`
Services:
- `postgres:16` — primary database with RLS policies
- `redis:7` — caching + Celery task broker
- `minio` — S3-compatible object storage (images, IFC files, fragments, reports)
- `backend` — FastAPI application
- `celery-worker` — background task processing (IFC conversion, batch inference)
- `celery-beat` — scheduled tasks (stale defect alerts, report generation)
- `frontend` — Next.js dev server

#### [NEW] Database Migrations (Alembic)
Core tables:
- `organizations` — tenant isolation
- `users` — auth, roles, org membership
- `projects` — construction projects
- `bim_models` — uploaded IFC files + processing status
- `inspections` — inspection sessions (date, inspector, zone)
- `defects` — detected defects with full metadata
- `defect_bim_links` — spatial mapping between defects and IFC elements
- `bcf_viewpoints` — saved BCF camera states
- `audit_log` — immutable change history for compliance

---

## Verification Plan

### Automated Tests

```bash
# Backend unit tests (pytest)
cd backend && pytest tests/ -v --cov=app --cov-report=html

# ML pipeline tests
cd backend && pytest ml/tests/ -v

# Frontend component tests (Vitest + React Testing Library)
cd frontend && npm run test

# E2E tests (Playwright)
cd frontend && npx playwright test

# API integration tests
cd backend && pytest tests/integration/ -v

# Full stack smoke test
docker-compose up -d && make test-e2e
```

### Manual Verification
- Upload a sample IFC file (e.g., a Revit sample building) and verify it renders correctly in the 3D viewer
- Upload 10+ construction defect images and verify detection accuracy, severity grading, and annotation rendering
- Map 5+ defects to BIM elements and verify markers appear at correct positions in the 3D model
- Export a BCF file and import it into a BCF-compatible tool (e.g., BIMcollab) to verify interoperability
- Generate a PDF report and verify it includes all defect data, images, and BIM context
- Test the full workflow: Create project → Upload IFC → Run inspection → Detect defects → Map to BIM → Generate report

### Performance Benchmarks
- IFC viewer: renders 50MB+ model at 60fps in Chrome
- Detection inference: < 200ms per image on GPU, < 2s on CPU
- API response times: < 100ms for CRUD, < 500ms for inference endpoints
- Batch processing: 100 images in < 60 seconds (GPU)

---

## Implementation Phases

### Phase 1 — Foundation (Week 1-2)
- Monorepo setup, Docker infrastructure, database schema
- Auth system (JWT-based), user/org management
- Design system & layout components
- Basic project CRUD

### Phase 2 — ML Pipeline (Week 3-4)
- Dataset preparation (Roboflow + augmentation)
- YOLOv11 training for 6-class detection
- Severity classification model training
- FastAPI inference endpoints
- Detection UI (upload, results, annotations)

### Phase 3 — BIM Integration (Week 5-6)
- IFC upload + server-side Fragment conversion
- 3D viewer component with That Open Engine
- Defect marker system (3D sprites, clustering, filtering)
- Element picking + defect-to-BIM mapping workflow
- BCF export/import

### Phase 4 — Polish & Production (Week 7-8)
- Dashboard with analytics charts
- Report generation (PDF, Excel, BCF)
- Defect lifecycle management (assignment, status tracking)
- Settings & configuration UI
- Performance optimization, accessibility, testing
- Documentation & deployment guides

---

## Key Differentiators (Why This Isn't a Student Project)

| Feature | Student Project | DefectSync |
|---------|----------------|------------|
| Auth | Hardcoded login | JWT + RBAC + multi-tenancy |
| Detection | Single-class binary | 6-class + severity grading |
| BIM | Screenshot overlay | Full 3D IFC viewer with spatial mapping |
| Data | Demo images | User uploads their own data + custom model retraining |
| Reports | Console output | Branded PDF/Excel + BCF export |
| Deployment | `python app.py` | Docker Compose + CI/CD |
| UX | Basic HTML | Premium dark-mode SaaS dashboard |
| Scale | Single user | Multi-org, multi-project, concurrent users |
| Interop | None | BCF 2.1, IFC, REST API |
