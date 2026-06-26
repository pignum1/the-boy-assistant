"""Workflow Events API：工作流执行事件推送

通过 WebSocket 推送工作流执行进度
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# 活跃的 WebSocket 连接
active_connections: dict[uuid.UUID, list[WebSocket]] = {}

# 事件回调（由外部设置）
event_callbacks: list[callable] = []


def register_event_callback(callback: callable):
    """注册事件回调函数"""
    event_callbacks.append(callback)


async def broadcast_workflow_event(event_type: str, data: dict):
    """广播工作流事件到所有订阅者（回调 + WebSocket）。"""
    # 1) 调用所有注册的回调
    for callback in event_callbacks:
        try:
            await callback(event_type, data)
        except Exception as e:
            logger.error(f"Event callback failed: {e}")

    # 2) 发送到 WebSocket 订阅者
    instance_id = data.get("instance_id")
    if instance_id:
        await _send_to_instance_subscribers(uuid.UUID(str(instance_id)), {
            "type": f"workflow.{event_type}",
            "data": data,
        })


def _send_to_instance_subscribers(instance_id: uuid.UUID, message: dict):
    """发送消息到特定实例的订阅者。自动清理断开的连接。"""
    if instance_id not in active_connections:
        return
    dead: list[WebSocket] = []
    for ws in active_connections[instance_id]:
        try:
            import asyncio
            asyncio.create_task(ws.send_json(message))
        except Exception as e:
            logger.warning(f"Removing dead WebSocket for instance {instance_id}: {e}")
            dead.append(ws)
    for ws in dead:
        try:
            active_connections[instance_id].remove(ws)
        except ValueError:
            pass
    if not active_connections[instance_id]:
        del active_connections[instance_id]


@router.websocket("/ws/instances/{instance_id}")
async def subscribe_to_instance(
    instance_id: uuid.UUID,
    websocket: WebSocket,
):
    """订阅工作流实例的执行事件

    连接后，客户端会实时收到该实例的执行事件。
    """
    await websocket.accept()

    # 添加连接
    if instance_id not in active_connections:
        active_connections[instance_id] = []
    active_connections[instance_id].append(websocket)

    logger.info(f"WebSocket connected for instance {instance_id}")

    try:
        # 发送连接成功消息
        await websocket.send_json({
            "type": "workflow.connected",
            "data": {
                "instance_id": str(instance_id),
                "message": "Connected to workflow instance",
            }
        })

        # 保持连接，接收客户端消息
        while True:
            data = await websocket.receive_json()

            # 处理客户端消息（如 HITL 响应）
            if data.get("type") == "workflow.hitl.response":
                await _handle_hitl_response(
                    instance_id=instance_id,
                    response=data.get("data", {}),
                )

    except WebSocketDisconnect:
        # 移除连接
        if instance_id in active_connections:
            active_connections[instance_id].remove(websocket)
            if not active_connections[instance_id]:
                del active_connections[instance_id]
        logger.info(f"WebSocket disconnected for instance {instance_id}")


async def _handle_hitl_response(instance_id: uuid.UUID, response: dict):
    """处理 HITL 人工响应"""
    from app.core.database import async_session
    from app.models.workflow_instance import WorkflowInstance
    from sqlalchemy import select

    async with async_session() as db:
        instance = await db.get(WorkflowInstance, instance_id)
        if not instance:
            logger.warning(f"Instance {instance_id} not found")
            return

        if not instance.hitl_pending:
            logger.warning(f"Instance {instance_id} is not waiting for HITL")
            return

        # 处理响应
        action = response.get("action")  # approve/reject/input

        if action == "approve":
            # 继续
            instance.hitl_pending = False
            instance.hitl_node_id = None
            instance.hitl_timeout_at = None

            # 更新状态
            instance.state.update({
                "hitl_result": "approved",
                "hitl_comment": response.get("comment"),
            })

            await db.commit()

            # 通知继续执行
            from app.services.workflow_engine import WorkflowEngine
            engine = WorkflowEngine(db, event_callback=broadcast_workflow_event)
            await engine.resume_instance(instance_id)

            await _send_to_instance_subscribers(instance_id, {
                "type": "workflow.hitl.approved",
                "data": {"instance_id": str(instance_id)},
            })

        elif action == "reject":
            # 拒绝/返回
            instance.hitl_pending = False
            instance.hitl_node_id = None
            instance.hitl_timeout_at = None

            instance.state.update({
                "hitl_result": "rejected",
                "hitl_comment": response.get("comment"),
            })

            await db.commit()

            # 根据配置处理（可能返回上一个节点）
            await _send_to_instance_subscribers(instance_id, {
                "type": "workflow.hitl.rejected",
                "data": {"instance_id": str(instance_id)},
            })

        elif action == "input":
            # 提供输入
            instance.hitl_pending = False
            instance.hitl_node_id = None
            instance.hitl_timeout_at = None

            user_input = response.get("input")
            instance.state.update({
                "hitl_result": "input",
                "hitl_input": user_input,
            })

            await db.commit()

            # 使用用户输入继续执行
            from app.services.workflow_engine import WorkflowEngine
            engine = WorkflowEngine(db, event_callback=broadcast_workflow_event)
            await engine.resume_instance(instance_id)

            await _send_to_instance_subscribers(instance_id, {
                "type": "workflow.hitl.input_received",
                "data": {"instance_id": str(instance_id)},
            })


@router.get("/instances/{instance_id}/events")
async def get_instance_events(
    instance_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取工作流实例的事件历史"""
    from app.models.workflow_instance import NodeExecution
    from sqlalchemy import select

    result = await db.execute(
        select(NodeExecution)
        .where(NodeExecution.instance_id == instance_id)
        .order_by(NodeExecution.started_at)
    )
    executions = result.scalars().all()

    events = []
    for execution in executions:
        events.append({
            "id": str(execution.id),
            "node_id": str(execution.node_id),
            "node_type": execution.node_type,
            "node_label": execution.node_label,
            "status": execution.status,
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
            "output": execution.output,
            "error": execution.error_message,
            "agent_name": execution.agent_name,
        })

    return {"events": events}
