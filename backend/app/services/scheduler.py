"""Standalone scheduled-camera worker: python -m app.services.scheduler.

Claims are persisted before capture, so multiple workers cannot claim the same
camera concurrently. The lease exceeds the bounded stream processing deadline.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, text
from app.core.config import get_settings
from app.db.session import async_session_factory
from app.models.camera import Camera, CameraStatus
from app.models.user import User, UserRole
from app.api.v1.calibration import run_auto_mapped_detection

logger = logging.getLogger(__name__)


def _utc(value: datetime) -> datetime:
    # SQLite test databases return naive values for timestamps stored in UTC.
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


async def claim_due_camera():
    now = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        cameras = (await db.scalars(select(Camera).where(
            Camera.auto_detect_enabled.is_(True), Camera.is_active.is_(True),
            Camera.calibration_status == "calibrated").with_for_update(skip_locked=True))).all()
        for camera in cameras:
            if camera.claimed_until and _utc(camera.claimed_until) > now:
                continue
            if camera.last_attempt_at and now - _utc(camera.last_attempt_at) < timedelta(minutes=camera.auto_detect_interval_minutes):
                continue
            camera.last_attempt_at = now
            camera.claimed_until = now + timedelta(minutes=15)
            camera_id = camera.id
            await db.commit()
            return camera_id
        await db.rollback()
    return None


async def process_claim(camera_id):
    async with async_session_factory() as db:
        camera = await db.get(Camera, camera_id)
        if camera is None:
            return
        try:
            user = await db.get(User, camera.created_by_id)
            if user is None or not user.is_active or user.role == UserRole.VIEWER:
                camera.auto_detect_enabled = False
                await db.commit()
                raise RuntimeError("Camera owner is unavailable or read-only")
            db.info["actor_id"] = user.id
            await run_auto_mapped_detection(camera_id, 30, db, user, persist_unmapped=False)
        except Exception:
            await db.rollback()
            camera = await db.get(Camera, camera_id)
            if camera:
                camera.status = CameraStatus.ERROR
            logger.warning("Scheduled camera %s failed; will retry after its configured interval", camera_id)
        finally:
            if camera:
                camera.claimed_until = None
            await db.commit()


async def main():
    if not get_settings().SCHEDULER_ENABLED:
        raise SystemExit("Set SCHEDULER_ENABLED=true to run the camera worker")
    worker_id = str(uuid.uuid4())
    async def heartbeat():
        while True:
            try:
                async with async_session_factory() as db:
                    await db.execute(text("INSERT INTO monitoring_workers (id, last_seen) VALUES (:id, now()) "
                                          "ON CONFLICT (id) DO UPDATE SET last_seen = now()"), {"id": worker_id})
                    await db.execute(text("DELETE FROM monitoring_workers WHERE last_seen < now() - interval '1 day'"))
                    await db.commit()
            except Exception:
                logger.exception("Monitoring heartbeat failed")
            await asyncio.sleep(10)
    heartbeat_task = asyncio.create_task(heartbeat())
    try:
        while True:
            try:
                camera_id = await claim_due_camera()
                if camera_id:
                    await process_claim(camera_id)
                else:
                    await asyncio.sleep(2)
            except Exception:
                logger.exception("Monitoring worker will retry after a service error")
                await asyncio.sleep(10)
    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
        async with async_session_factory() as db:
            await db.execute(text("DELETE FROM monitoring_workers WHERE id = :id"), {"id": worker_id})
            await db.commit()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
