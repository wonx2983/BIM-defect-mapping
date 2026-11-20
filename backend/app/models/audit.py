"""Append-only inspection change history, written with the business transaction."""
import uuid
from datetime import datetime
from sqlalchemy import DateTime, String, ForeignKey, JSON, func, event, inspect
from sqlalchemy.orm import Mapped, mapped_column, Session
from app.db.session import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    entity_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(32))
    changes: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


@event.listens_for(Session, "before_flush")
def record_defect_changes(session, flush_context, instances):
    from app.models.defect import Defect
    fields = ("status", "severity", "severity_score", "confidence", "notes", "assigned_to_id",
              "bim_model_id", "bim_element_guid", "world_position")
    def plain(value):
        if isinstance(value, uuid.UUID):
            return str(value)
        return getattr(value, "value", value)
    for obj in list(session.new) + list(session.dirty) + list(session.deleted):
        if not isinstance(obj, Defect):
            continue
        action = "created" if obj in session.new else "deleted" if obj in session.deleted else "updated"
        changes = {}
        for field in fields:
            history = inspect(obj).attrs[field].history
            if history.has_changes() or action != "updated":
                changes[field] = {"before": plain(history.deleted[0]) if history.deleted else None,
                                  "after": plain(getattr(obj, field))}
        if not changes:
            continue
        obj.id = obj.id or uuid.uuid4()
        session.add(AuditEvent(project_id=obj.project_id,
            actor_id=session.info.get("actor_id", obj.created_by_id), entity_id=str(obj.id),
            action=action, changes=changes))
