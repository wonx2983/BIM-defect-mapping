"""Exercise upload validation and persistence through the actual API."""
import os
from pathlib import Path

import pytest


@pytest.mark.skipif(not os.environ.get("IFC_UPLOAD_TEST_FILE"), reason="Requires a local IFC fixture")
async def test_real_ifc_upload(context):
    path = Path(os.environ["IFC_UPLOAD_TEST_FILE"])
    with path.open("rb") as source:
        response = await context.client.post(
            "/api/v1/bim/upload",
            data={"project_id": str(context.projects[0].id)},
            files={"file": (path.name, source, "application/octet-stream")},
        )
    assert response.status_code == 200, response.text
    model = response.json()
    assert model["file_size_bytes"] == path.stat().st_size
    assert model["element_count"] > 0
    assert model["processing_status"] == "ready"
    listing = await context.client.get(f"/api/v1/bim/{context.projects[0].id}/models")
    assert any(item["id"] == model["id"] for item in listing.json()["models"])
