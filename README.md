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
│  │PostgreSQL│  │ Redis        │  │ S3/MinIO     │  │ ML Model   │ │
│  │ (+ RLS)  │  │ (Cache +     │  │ (Files, IFC, │  │ Registry   │ │
│  │          │  │  Task Queue) │  │  Images)     │  │            │ │
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

## Getting Started

### Prerequisites
- Docker & Docker Compose
- Python 3.11+ (for local ML training)
- Node.js 18+ (for local frontend dev)

### Installation

1. Clone the repository
```bash
git clone https://github.com/wonx2983/BIM-defect-mapping.git
cd BIM-defect-mapping
```

2. Start the services using Docker Compose
```bash
docker-compose up -d
```

3. Access the application
- Frontend: `http://localhost:3000`
- Backend API Docs: `http://localhost:8000/docs`
