"""DefectSync — FastAPI Application Entry Point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.api.v1.auth import router as auth_router
from app.api.v1.projects import router as projects_router

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
