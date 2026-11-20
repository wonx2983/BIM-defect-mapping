import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from sqlalchemy import select

from app.models import Camera
from app.models.monitoring_worker import MonitoringWorker
from ml.calibration.marker_detector import detect_markers


def marker_body(context, **overrides):
    return {"project_id": str(context.projects[0].id), "bim_model_id": str(context.models[0].id),
            "world_x": 1, "world_y": 2, "world_z": 3, "physical_size_m": .2, **overrides}


@pytest.mark.parametrize('dictionary,cells', [('DICT_4X4_50', 6), ('DICT_6X6_250', 8)])
async def test_marker_allocation_print_and_cross_org_access(context, dictionary, cells):
    first = await context.client.post('/api/v1/markers', json=marker_body(context, aruco_dict_type=dictionary))
    second = await context.client.post('/api/v1/markers', json=marker_body(context, aruco_dict_type=dictionary))
    assert first.status_code == second.status_code == 201
    assert first.json()['marker_dict_id'] == 0
    assert second.json()['marker_dict_id'] == 1
    printed = await context.client.get(f"/api/v1/markers/{second.json()['id']}/print")
    assert printed.status_code == 200
    svg = ET.fromstring(printed.text)
    assert float(svg.attrib['width'].removesuffix('mm')) == pytest.approx(200 * (cells + 2) / cells)
    canvas = np.full(((cells + 2) * 50, (cells + 2) * 50), 255, np.uint8)
    for rect in svg.findall('.//{http://www.w3.org/2000/svg}g/{http://www.w3.org/2000/svg}rect'):
        x, y = int(rect.attrib['x']), int(rect.attrib['y'])
        canvas[y * 50:(y + 1) * 50, x * 50:(x + 1) * 50] = 0
    assert [marker.marker_id for marker in detect_markers(cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR), dictionary)] == [1]
    from app.core.security import create_access_token
    headers = {'Authorization': 'Bearer ' + create_access_token({'sub': str(context.users[1].id)})}
    assert (await context.client.get(f"/api/v1/markers/{second.json()['id']}/print", headers=headers)).status_code in {403, 404}


async def test_marker_dictionary_range_and_duplicates(context):
    body = marker_body(context, marker_dict_id=49)
    assert (await context.client.post('/api/v1/markers', json={**body, 'marker_dict_id': 50})).status_code == 422
    assert (await context.client.post('/api/v1/markers', json={**body, 'aruco_dict_type': 'invalid'})).status_code == 422
    assert (await context.client.post('/api/v1/markers', json=body)).status_code == 201
    assert (await context.client.post('/api/v1/markers', json=body)).status_code == 422


async def test_monitoring_requires_worker_and_successful_calibration(context, monkeypatch):
    camera = context.cameras[0]
    other_id = context.cameras[1].id
    camera.fov_horizontal_deg = 90
    await context.db.commit()
    url = f'/api/v1/cameras/{camera.id}/start-monitoring'
    assert (await context.client.post(url)).status_code == 503
    context.db.add(MonitoringWorker(id='test-worker', last_seen=datetime.now(timezone.utc)))
    await context.db.commit()
    assert (await context.client.get('/api/v1/cameras/monitoring/status')).json()['available']

    async def failed(*args):
        return SimpleNamespace(success=False, message='No marker visible')
    monkeypatch.setattr('app.api.v1.calibration.calibrate_camera', failed)
    assert (await context.client.post(url)).status_code == 422
    await context.db.refresh(camera)
    assert not camera.auto_detect_enabled

    async def calibrated(*args):
        camera.calibration_status = 'calibrated'
        return SimpleNamespace(success=True)
    monkeypatch.setattr('app.api.v1.calibration.calibrate_camera', calibrated)
    response = await context.client.post(url)
    assert response.status_code == 200, response.text
    assert response.json()['auto_detect_enabled']
    assert camera.last_attempt_at is None
    other = await context.client.post(f'/api/v1/cameras/{other_id}/start-monitoring')
    assert other.status_code == 404


async def test_worker_claims_distinct_cameras_and_releases_after_processing(context, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services import scheduler
    from app.models.camera import CameraStatus
    factory = async_sessionmaker(context.db.bind, expire_on_commit=False)
    monkeypatch.setattr(scheduler, 'async_session_factory', factory)
    expected = {camera.id for camera in context.cameras}
    for camera in context.cameras:
        camera.auto_detect_enabled = True
        camera.calibration_status = 'calibrated'
    await context.db.commit()
    first = await scheduler.claim_due_camera()
    second = await scheduler.claim_due_camera()
    assert {first, second} == expected
    assert await scheduler.claim_due_camera() is None
    calls = []
    async def inspect(camera_id, frames, db, user, *, persist_unmapped):
        assert not persist_unmapped
        calls.append(camera_id)
        camera = await db.get(Camera, camera_id)
        camera.status = CameraStatus.ACTIVE
    monkeypatch.setattr(scheduler, 'run_auto_mapped_detection', inspect)
    await scheduler.process_claim(first)
    await scheduler.process_claim(second)
    assert set(calls) == expected
    async with factory() as db:
        for camera in (await db.scalars(select(Camera))).all():
            assert camera.claimed_until is None
            assert camera.last_attempt_at is not None
    assert await scheduler.claim_due_camera() is None
