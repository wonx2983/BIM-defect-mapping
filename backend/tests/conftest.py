"""Isolated test DB. Never use the application's configured remote database."""
import os
from sqlalchemy.engine import make_url

_test_url = make_url(os.environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:"))
if _test_url.get_backend_name() == "sqlite" and _test_url.database == ":memory:":
    # App imports still initialise an asyncpg engine; tests inject their SQLite session.
    _app_test_url = make_url("postgresql+asyncpg://audit_test@127.0.0.1:55432/defectsync_test")
elif (_test_url.get_backend_name() == "postgresql"
      and _test_url.host in {"localhost", "127.0.0.1", "::1"}
      and _test_url.database == "defectsync_test"):
    _app_test_url = _test_url
else:
    raise RuntimeError("Tests require in-memory SQLite or a disposable local defectsync_test database")
os.environ["DATABASE_URL"] = _app_test_url.set(drivername="postgresql+asyncpg").render_as_string(hide_password=False)
os.environ["DATABASE_URL_SYNC"] = _app_test_url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)
os.environ["APP_ENV"] = "test"
os.environ["JWT_SECRET_KEY"] = "test-only-secret-not-for-deployment-123456789"
os.environ["CAMERA_ALLOWED_HOSTS"] = "camera.example"
os.environ["SCHEDULER_ENABLED"] = "false"

import uuid
from types import SimpleNamespace
import pytest
import httpx
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.base import Base
from app.db.session import get_db
from app.models import Organization, User, Project, BIMModel, Camera
from app.models.user import UserRole
from app.models.bim_model import ProcessingStatus
from app.main import app
from app.core.security import create_access_token
from app.core.config import get_settings


@pytest.fixture
async def context(tmp_path, monkeypatch):
    engine = create_async_engine(_test_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(get_settings(), "LOCAL_UPLOAD_DIR", str(tmp_path / "uploads"))
    async with factory() as db:
        orgs = [Organization(id=uuid.uuid4(), name=f"Org {i}") for i in range(2)]
        db.add_all(orgs)
        await db.flush()
        users = [User(id=uuid.uuid4(), organization_id=o.id, email=f"user{i}@example.com",
                      hashed_password="unused", full_name="Test", role=UserRole.ADMIN) for i, o in enumerate(orgs)]
        db.add_all(users)
        await db.flush()
        projects = [Project(id=uuid.uuid4(), name=f"Project {i}", organization_id=o.id,
                            created_by_id=u.id) for i, (o, u) in enumerate(zip(orgs, users))]
        db.add_all(projects)
        await db.flush()
        models = [BIMModel(id=uuid.uuid4(), project_id=p.id, original_filename="test.ifc",
                           file_url="/uploads/test.ifc", file_size_bytes=10,
                           processing_status=ProcessingStatus.READY, uploaded_by_id=u.id)
                  for p, u in zip(projects, users)]
        db.add_all(models)
        await db.flush()
        cameras = [Camera(id=uuid.uuid4(), project_id=p.id, name="Camera",
                          rtsp_url="rtsp://camera.example/live", created_by_id=u.id,
                          bim_model_id=m.id) for p, u, m in zip(projects, users, models)]
        db.add_all(cameras)
        await db.commit()
        async def override_db():
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise
        app.dependency_overrides[get_db] = override_db
        headers = {"Authorization": "Bearer " + create_access_token({"sub": str(users[0].id)})}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers) as client:
            yield SimpleNamespace(db=db, client=client, users=users, projects=projects,
                                  models=models, cameras=cameras, tmp=tmp_path)
        app.dependency_overrides.clear()
    await engine.dispose()
