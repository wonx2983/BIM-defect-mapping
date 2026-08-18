"""DefectSync — FastAPI Application Entry Point."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.api.v1.auth import router as auth_router
from app.api.v1.projects import router as projects_router
from app.api.v1.detection import router as detection_router
from app.api.v1.defects import router as defects_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.video import router as video_router
from app.api.v1.bim import router as bim_router
from app.api.v1.cameras import router as cameras_router

settings = get_settings()

app = FastAPI(
    title="DefectSync API",
    description="Construction defect detection, severity assessment, and BIM mapping platform.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
register_exception_handlers(app)

# Routers
app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(detection_router)
app.include_router(defects_router)
app.include_router(dashboard_router)
app.include_router(video_router)
app.include_router(bim_router)
app.include_router(cameras_router)

# Serve uploaded files as static assets (local storage mode)
if settings.is_local_storage:
    uploads_dir = Path(__file__).resolve().parents[1] / settings.LOCAL_UPLOAD_DIR
    uploads_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")


@app.get("/health", tags=["System"])
async def health_check():
    """System health check endpoint."""
    return {"status": "healthy", "service": "DefectSync API", "version": "0.1.0"}


@app.get("/", tags=["System"])
async def root():
    """API root — service info."""
    return {
        "name": settings.APP_NAME,
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }
