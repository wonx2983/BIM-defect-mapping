"""Dashboard statistics endpoint — real-time aggregated stats for the logged-in user's organization.

Endpoints:
    GET /api/v1/dashboard/stats  — Aggregated project/defect/severity stats
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import case, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.defect import Defect, DefectStatus, SeverityLevel
from app.models.project import Project
from app.models.user import User

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])


@router.get("/stats")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Return real-time dashboard statistics for the user's organization.

    All counts are scoped to the organization that the authenticated user belongs to.
    """
    org_id = user.organization_id

    # ── 1. Total Projects ────────────────────────────────────────────
    total_projects = await db.scalar(
        select(func.count(Project.id)).where(Project.organization_id == org_id)
    ) or 0

    # ── 2. Active Defects (not resolved/verified) ────────────────────
    resolved_statuses = {DefectStatus.RESOLVED, DefectStatus.VERIFIED}
    org_project_ids = select(Project.id).where(Project.organization_id == org_id)

    active_defects = await db.scalar(
        select(func.count(Defect.id)).where(
            Defect.project_id.in_(org_project_ids),
            Defect.status.notin_(resolved_statuses),
        )
    ) or 0

    # ── 3. Critical Alerts (severity=critical, status=detected/confirmed) ─
    critical_alerts = await db.scalar(
        select(func.count(Defect.id)).where(
            Defect.project_id.in_(org_project_ids),
            Defect.severity == SeverityLevel.CRITICAL,
            Defect.status.in_({DefectStatus.DETECTED, DefectStatus.CONFIRMED}),
        )
    ) or 0

    # ── 4. Total Inspections (unique inspection_ids) ─────────────────
    total_inspections = await db.scalar(
        select(func.count(func.distinct(Defect.inspection_id))).where(
            Defect.project_id.in_(org_project_ids),
            Defect.inspection_id.isnot(None),
        )
    ) or 0

    # ── 5. Severity Distribution (for pie chart) ─────────────────────
    severity_rows = (
        await db.execute(
            select(Defect.severity, func.count(Defect.id))
            .where(Defect.project_id.in_(org_project_ids))
            .group_by(Defect.severity)
        )
    ).all()
    severity_distribution = {
        "low": 0,
        "medium": 0,
        "high": 0,
        "critical": 0,
    }
    for row in severity_rows:
        severity_distribution[row[0].value] = row[1]

    # ── 6. Defects Over Time (last 6 months, grouped by month) ───────
    six_months_ago = datetime.now(timezone.utc) - timedelta(days=180)
    trend_rows = (
        await db.execute(
            select(
                extract("year", Defect.created_at).label("year"),
                extract("month", Defect.created_at).label("month"),
                func.count(Defect.id).label("count"),
            )
            .where(
                Defect.project_id.in_(org_project_ids),
                Defect.created_at >= six_months_ago,
            )
            .group_by("year", "month")
            .order_by("year", "month")
        )
    ).all()

    month_names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    trend_data = [
        {"month": month_names[int(row.month)], "year": int(row.year), "defects": row.count}
        for row in trend_rows
    ]

    # ── 7. Recent Activity (last 10 defects created) ─────────────────
    recent_rows = (
        await db.execute(
            select(Defect)
            .where(Defect.project_id.in_(org_project_ids))
            .order_by(Defect.created_at.desc())
            .limit(10)
        )
    ).scalars().all()

    recent_activity = []
    for defect in recent_rows:
        ago = _time_ago(defect.created_at)
        recent_activity.append({
            "text": f"{defect.severity.value.capitalize()} {defect.defect_class.value.replace('_', ' ')} detected",
            "time": ago,
            "severity": defect.severity.value,
            "defect_id": str(defect.id),
        })

    # ── 8. Defect Class Distribution (for class breakdown) ───────────
    class_rows = (
        await db.execute(
            select(Defect.defect_class, func.count(Defect.id))
            .where(Defect.project_id.in_(org_project_ids))
            .group_by(Defect.defect_class)
        )
    ).all()
    class_distribution = {row[0].value: row[1] for row in class_rows}

    # ── 9. Resolved this week ────────────────────────────────────────
    one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    resolved_this_week = await db.scalar(
        select(func.count(Defect.id)).where(
            Defect.project_id.in_(org_project_ids),
            Defect.status.in_(resolved_statuses),
            Defect.updated_at >= one_week_ago,
        )
    ) or 0

    return {
        "stats": {
            "total_projects": total_projects,
            "active_defects": active_defects,
            "critical_alerts": critical_alerts,
            "total_inspections": total_inspections,
            "resolved_this_week": resolved_this_week,
        },
        "severity_distribution": severity_distribution,
        "trend_data": trend_data,
        "recent_activity": recent_activity,
        "class_distribution": class_distribution,
    }


def _time_ago(dt: datetime) -> str:
    """Human-readable time-ago string."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    delta = now - dt
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "Just now"
    elif seconds < 3600:
        mins = seconds // 60
        return f"{mins} min{'s' if mins != 1 else ''} ago"
    elif seconds < 86400:
        hours = seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif seconds < 604800:
        days = seconds // 86400
        return f"{days} day{'s' if days != 1 else ''} ago"
    else:
        return dt.strftime("%b %d, %Y")
