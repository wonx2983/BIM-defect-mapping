# Automation of Mapping Quality Defects in BIM Environment

A professional-grade, production-ready platform for real-time construction defect detection, severity assessment, and automated BIM mapping — built for real construction professionals, site engineers, and quality managers.

---

## Product Vision

**DefectSync** is a full-stack SaaS tool that enables construction teams to:
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
│  │Neon DB   │  │ Upstash      │  │ Local/Cloud  │  │ ML Model   │ │
│  │(Postgres)│  │ (Redis)      │  │ (Files, IFC, │  │ Registry   │ │
│  │          │  │              │  │  Images)     │  │            │ │
│  └──────────┘  └──────────────┘  └──────────────┘  └────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Features

### ML Defect Detection Pipeline
- YOLOv11 fine-tuning script for 6-class construction defect detection
- Severity classification model — a lightweight ResNet-18/EfficientNet-B0 classifier
- 4-class output: `Low`, `Medium`, `High`, `Critical`

### FastAPI Backend
- Production-grade API server with multi-tenant architecture.
- Full project lifecycle management
- Combines ML severity prediction with rule-based domain logic
- Server-side IFC parsing using `ifcopenshell` (Python)
- Extracts element hierarchy, properties, materials, and spatial structure

### Next.js Frontend
- Premium, dark-mode-first UI with real-time interactivity.
- **Detection Interface**
- **3D BIM Viewer** (built with That Open Engine)
- **Dashboard** with project overview and analytics
- **Reports & Analytics** with PDF/Excel/BCF export
- **Settings & Configuration**

### BIM Integration Layer
- Core 3D viewer component using That Open Engine
- Handles IFC/Fragment loading, camera controls, raycasting
- Custom marker management system for 3D defect mapping

### BCF Integration (BIM Collaboration Format)
- Industry-standard interoperability for sharing defects with other BIM tools (Revit, Navisworks, etc.).

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
*(Fill in your database and service credentials in `.env`. Both the backend and ML services read directly from this single root file.)*

> **Note on Model Weights:** The trained defect detection weights (`backend/ml/models/defect_detector.pt`) are already bundled in the repository, so no separate model download is needed.

---

### Step 3: Backend Setup

#### 🪟 Windows (PowerShell)
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

#### 🍎 macOS / Linux (Terminal / zsh / bash)
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

#### 🪟 Windows & 🍎 macOS / Linux
Open a separate terminal window and run:
```bash
# 1. Navigate to frontend directory
cd frontend

# 2. Install dependencies
npm install

# 3. Start development server
npm run dev
```

---

### Step 5: Access the Application
- **Frontend Web Dashboard**: [http://localhost:3000](http://localhost:3000)
- **Backend API Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Backend Health Check**: [http://localhost:8000/health](http://localhost:8000/health)
