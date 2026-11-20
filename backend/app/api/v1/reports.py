"""Project-scoped inspection exports and immutable change history."""
import csv
import io
import uuid
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select
from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.defect import Defect
from app.models.audit import AuditEvent
from app.services.access import project_access

router = APIRouter(prefix="/api/v1/reports", tags=["Reports"])


def csv_cell(value):
    text = "" if value is None else str(getattr(value, "value", value))
    # Prevent formula execution when exported notes are opened in spreadsheets.
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else text


@router.get("/{project_id}/defects.csv")
async def export_defects(project_id: uuid.UUID, db=Depends(get_db), user=Depends(get_current_active_user)):
    await project_access(project_id, user, db)
    rows = (await db.scalars(select(Defect).where(Defect.project_id == project_id).order_by(Defect.created_at))).all()
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    fields = ["id", "defect_class", "severity", "confidence", "status", "bim_model_id",
              "bim_element_guid", "world_position", "source_image_url", "notes", "created_at"]
    writer.writerow(fields)
    writer.writerows([[csv_cell(getattr(row, key)) for key in fields] for row in rows])
    return Response(output.getvalue().encode("utf-8-sig"), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="inspection-defects.csv"',
                             "Cache-Control": "no-store"})


@router.get("/{project_id}/audit")
async def audit_history(project_id: uuid.UUID, limit: int = Query(100, ge=1, le=500),
                        db=Depends(get_db), user=Depends(get_current_active_user)):
    await project_access(project_id, user, db)
    events = (await db.scalars(select(AuditEvent).where(AuditEvent.project_id == project_id)
                              .order_by(AuditEvent.created_at.desc()).limit(limit))).all()
    return [{"id": str(e.id), "actor_id": str(e.actor_id) if e.actor_id else None,
             "entity_id": e.entity_id, "action": e.action, "changes": e.changes,
             "created_at": e.created_at} for e in events]
