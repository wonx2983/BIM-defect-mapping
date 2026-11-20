"""Run only against a disposable local PostgreSQL database.

python tests/verify_migrations.py
Creates its own database and validates upgrades with existing camera rows.
"""
import os
import uuid
from pathlib import Path
import psycopg
from psycopg import sql
from alembic.config import Config
from alembic import command


def main():
    name = "defectsync_upgrade_" + uuid.uuid4().hex[:10]
    admin = "host=127.0.0.1 port=55432 user=audit_test dbname=postgres"
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = f"postgresql+psycopg://audit_test@127.0.0.1:55432/{name}"
    os.environ["DATABASE_URL_SYNC"] = url
    os.environ["DATABASE_URL"] = url.replace("+psycopg", "+asyncpg")
    os.environ["APP_ENV"] = "test"
    from app.core.config import get_settings
    get_settings.cache_clear()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "ca62692399c7")
    with psycopg.connect(f"host=127.0.0.1 port=55432 user=audit_test dbname={name}") as conn:
        columns = {table: [r[0] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name=%s AND is_nullable='NO' AND column_default IS NULL", (table,))]
            for table in ("organizations", "users", "projects", "cameras")}
        org, user, project, camera = [uuid.uuid4() for _ in range(4)]
        common = {"organizations": {"id": org, "name": "Upgrade test"},
                  "users": {"id": user, "organization_id": org, "email": "migration@example.com", "hashed_password": "unused", "full_name": "Migration", "role": "ADMIN", "is_active": True},
                  "projects": {"id": project, "organization_id": org, "created_by_id": user, "name": "Upgrade", "status": "ACTIVE"},
                  "cameras": {"id": camera, "project_id": project, "created_by_id": user, "name": "Existing camera", "rtsp_url": "rtsp://camera.example/live", "status": "ACTIVE", "is_active": True, "frame_skip": 15, "auto_detect_enabled": False, "auto_detect_interval_minutes": 15, "total_defects_found": 0}}
        for table, fields in columns.items():
            values = common[table]
            conn.execute(sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                sql.Identifier(table), sql.SQL(",").join(map(sql.Identifier, fields)),
                sql.SQL(",").join(sql.Placeholder() for _ in fields)), [values[f] for f in fields])
    command.upgrade(config, "head")
    with psycopg.connect(f"host=127.0.0.1 port=55432 user=audit_test dbname={name}") as conn:
        assert conn.execute("SELECT calibration_status FROM cameras WHERE id=%s", (camera,)).fetchone()[0] == "uncalibrated"
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "20261120_marker_identity"
    print("PASS: populated pre-calibration database upgraded successfully")
    # Drop only the unique database created by this test, never a configured DB.
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


if __name__ == "__main__":
    main()
