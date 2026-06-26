"""事件持久化 — 将事件写入 observer_events 表"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select as _sel, func as _func, text

from app.services.observer.events import Event, EventType

logger = logging.getLogger(__name__)


async def ensure_table(db) -> None:
    """确保 observer_events 表存在（首次启动自动创建）。"""
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS observer_events (
            id UUID PRIMARY KEY,
            type VARCHAR(50) NOT NULL,
            source VARCHAR(50) DEFAULT '',
            session_id UUID,
            team_id UUID,
            agent_id UUID,
            agent_name VARCHAR(100),
            task_id UUID,
            payload JSONB DEFAULT '{}',
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_observer_events_type
        ON observer_events(type)
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_observer_events_timestamp
        ON observer_events(timestamp)
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_observer_events_session
        ON observer_events(session_id)
    """))
    await db.commit()


async def persist(db, event: Event) -> None:
    """持久化单个事件到 observer_events 表。"""
    try:
        await db.execute(
            text("""
                INSERT INTO observer_events (id, type, source, session_id, team_id,
                    agent_id, agent_name, task_id, payload, timestamp)
                VALUES (:id, :type, :source, :session_id, :team_id,
                    :agent_id, :agent_name, :task_id, :payload, :timestamp)
            """),
            {
                "id": uuid.UUID(event.id),
                "type": event.type.value,
                "source": event.source,
                "session_id": _safe_uuid(event.session_id) if event.session_id else None,
                "team_id": _safe_uuid(event.team_id) if event.team_id else None,
                "agent_id": _safe_uuid(event.agent_id) if event.agent_id else None,
                "agent_name": event.agent_name,
                "task_id": _safe_uuid(event.task_id) if event.task_id else None,
                "payload": json.dumps(event.payload),
                "timestamp": datetime.fromisoformat(event.timestamp) if isinstance(event.timestamp, str) else event.timestamp,
            },
        )
        await db.commit()
    except Exception as e:
        logger.warning(f"Failed to persist event {event.type.value}: {e}")


async def query(
    db,
    *,
    event_type: Optional[str] = None,
    session_id: Optional[str] = None,
    since: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """查询事件列表。"""
    conditions = []
    params: dict = {"limit": limit, "offset": offset}

    if event_type:
        conditions.append("type = :event_type")
        params["event_type"] = event_type
    if session_id:
        conditions.append("session_id = :session_id")
        params["session_id"] = uuid.UUID(session_id)
    if since:
        conditions.append("timestamp >= :since")
        params["since"] = since

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"""
        SELECT id, type, source, session_id, team_id, agent_id, agent_name,
               task_id, payload, timestamp
        FROM observer_events
        {where}
        ORDER BY timestamp DESC
        LIMIT :limit OFFSET :offset
    """

    result = await db.execute(text(sql), params)
    rows = result.fetchall()
    return [_row_to_dict(r) for r in rows]


async def summary(db, *, since: Optional[str] = None) -> dict:
    """按类型分组统计事件数量。"""
    params: dict = {}
    where = ""
    if since:
        where = "WHERE timestamp >= :since"
        params["since"] = since

    sql = f"""
        SELECT type, COUNT(*) as cnt
        FROM observer_events
        {where}
        GROUP BY type
        ORDER BY cnt DESC
    """
    result = await db.execute(text(sql), params)
    rows = result.fetchall()
    return {r[0]: r[1] for r in rows}


def _safe_uuid(val: str):
    try:
        return uuid.UUID(val)
    except (ValueError, AttributeError):
        return None


def _row_to_dict(row) -> dict:
    return {
        "id": str(row[0]),
        "type": row[1],
        "source": row[2],
        "session_id": str(row[3]) if row[3] else None,
        "team_id": str(row[4]) if row[4] else None,
        "agent_id": str(row[5]) if row[5] else None,
        "agent_name": row[6],
        "task_id": str(row[7]) if row[7] else None,
        "payload": row[8] or {},
        "timestamp": row[9].isoformat() if row[9] else None,
    }
