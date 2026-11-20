import uuid
from datetime import datetime, timezone
from app.models.inspection import Inspection, InspectionStatus


def record_inspection(db, project_id, user_id, title):
    inspection = Inspection(id=uuid.uuid4(), project_id=uuid.UUID(str(project_id)),
        inspector_id=user_id, title=title, inspection_date=datetime.now(timezone.utc).date(),
        status=InspectionStatus.COMPLETED)
    db.add(inspection)
    return inspection.id
