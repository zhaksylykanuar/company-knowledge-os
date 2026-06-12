"""Data availability: the formal state behind every widget number.

Rule of the product: not a single drawn number. Before rendering a
series the UI checks this table and shows an honest state instead:
no_data / collecting / insufficient / ready / stale.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.agent_models import DataAvailability, MetricSnapshot
from app.db.graph_models import EntityRecord
from app.services.entity_resolution import ENTITY_TYPE_PROJECT
from app.services.metric_collector import GLOBAL_SCOPE

STATUS_NO_DATA = "no_data"
STATUS_COLLECTING = "collecting"
STATUS_INSUFFICIENT = "insufficient"
STATUS_READY = "ready"
STATUS_STALE = "stale"

DEFAULT_REQUIRED_POINTS = 5
STALE_AFTER_DAYS = 3

# Series the platform expects to exist once sources are connected.
PROJECT_METRICS = ("jira.open", "jira.stale", "jira.overdue", "jira.done")
GLOBAL_METRICS = (
    "knowledge.tasks",
    "knowledge.risks",
    "knowledge.decisions",
    "activity.events",
)


def _message(
    status: str, points: int, required: int, last_point: str | None, age_days: int
) -> str:
    if status == STATUS_NO_DATA:
        return "Нет данных — источник ещё не подключён или агенты не запускались"
    if status == STATUS_COLLECTING:
        return f"Копим данные: точка {points} из {required}"
    if status == STATUS_INSUFFICIENT:
        return f"Недостаточно истории для тренда: {points} из {required}"
    if status == STATUS_STALE:
        return f"Данные устарели: последняя точка {age_days} дн назад ({last_point})"
    return f"Готово: {points} точек, последняя {last_point}"


async def _upsert_availability(
    session: AsyncSession,
    *,
    metric_key: str,
    scope: str,
    points: int,
    last_point: str | None,
    now: datetime,
    required: int = DEFAULT_REQUIRED_POINTS,
) -> None:
    age_days = 0
    if last_point:
        try:
            age_days = (now.date() - date.fromisoformat(last_point)).days
        except ValueError:
            age_days = 0

    if points == 0:
        status = STATUS_NO_DATA
    elif last_point and age_days > STALE_AFTER_DAYS:
        status = STATUS_STALE
    elif points < required:
        status = STATUS_COLLECTING
    else:
        status = STATUS_READY

    message = _message(status, points, required, last_point, age_days)

    row = await session.scalar(
        select(DataAvailability)
        .where(DataAvailability.metric_key == metric_key)
        .where(DataAvailability.scope == scope)
    )
    if row is None:
        session.add(
            DataAvailability(
                metric_key=metric_key,
                scope=scope,
                status=status,
                points_count=points,
                required_points=required,
                last_point_at=last_point,
                message=message,
            )
        )
    else:
        row.status = status
        row.points_count = points
        row.required_points = required
        row.last_point_at = last_point
        row.message = message
    await session.flush()


async def refresh_data_availability(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    """Recompute availability for every expected and observed series."""

    safe_now = now or datetime.now(timezone.utc)

    observed: dict[tuple[str, str], tuple[int, str | None]] = {}
    rows = (
        await session.execute(
            select(
                MetricSnapshot.metric_key,
                MetricSnapshot.scope,
                func.count(),
                func.max(MetricSnapshot.captured_on),
            ).group_by(MetricSnapshot.metric_key, MetricSnapshot.scope)
        )
    ).all()
    for metric_key, scope, points, last_point in rows:
        observed[(str(metric_key), str(scope))] = (
            int(points),
            str(last_point) if last_point else None,
        )

    expected: set[tuple[str, str]] = {
        (metric_key, GLOBAL_SCOPE) for metric_key in GLOBAL_METRICS
    }
    projects = (
        await session.execute(
            select(EntityRecord.entity_id).where(
                EntityRecord.entity_type == ENTITY_TYPE_PROJECT
            )
        )
    ).all()
    for (project_id,) in projects:
        for metric_key in PROJECT_METRICS:
            expected.add((metric_key, str(project_id)))

    statuses = {"rows": 0}
    for metric_key, scope in sorted(expected | set(observed)):
        points, last_point = observed.get((metric_key, scope), (0, None))
        await _upsert_availability(
            session,
            metric_key=metric_key,
            scope=scope,
            points=points,
            last_point=last_point,
            now=safe_now,
        )
        statuses["rows"] += 1
    return statuses


async def get_availability(
    session: AsyncSession,
    *,
    scope: str | None = None,
) -> list[dict]:
    query = select(DataAvailability).order_by(
        DataAvailability.scope, DataAvailability.metric_key
    )
    if scope is not None:
        query = query.where(DataAvailability.scope == scope)
    rows = (await session.execute(query)).scalars()
    return [
        {
            "metric_key": row.metric_key,
            "scope": row.scope,
            "status": row.status,
            "points_count": row.points_count,
            "required_points": row.required_points,
            "last_point_at": row.last_point_at,
            "message": row.message,
        }
        for row in rows
    ]
