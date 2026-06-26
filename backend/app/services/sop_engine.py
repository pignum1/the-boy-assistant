"""SOP Engine：基于状态机的工作流引擎（不依赖 LangGraph，独立实现）

职责：编排框架，驱动节点执行和路由决策，不包含具体节点逻辑。
依赖：sop_state / sop_router / sop_node_executor

向后兼容：从子模块重新导出 TaskState, SOPRouter, SOPNodeExecutor
"""

import logging
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.models.sop import SOP
from app.services.sop_state import TaskState
from app.services.sop_router import SOPRouter
from app.services.sop_node_executor import SOPNodeExecutor
from app.services.team_manager import TeamManager
from app.services.agent_pool import agent_pool
from app.services.blackboard import blackboard, EventType
from app.services.observer import trace_manager

# 向后兼容：外部 import sop_engine.TaskState 仍然有效
__all__ = ["SOPEngine", "TaskState", "SOPRouter", "SOPNodeExecutor"]

logger = logging.getLogger(__name__)


class SOPEngine:
    """SOP 工作流引擎：负责任务生命周期（启动 → 运行 → 暂停 → 恢复）"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.team_mgr = TeamManager(db)
        self.router = SOPRouter()
        self.node_executor = SOPNodeExecutor(db, self.team_mgr)

    async def start_task(
        self,
        sop_id: uuid.UUID,
        team_id: uuid.UUID,
        task_input: dict,
        auto_approve_hitl: bool = False,
        session_id: uuid.UUID = None,
    ) -> Task:
        """创建并启动 SOP 任务

        session_id: 可选，将任务关联到已有的会话（从 discussion 模式创建任务时传入）
        """
        sop = await self.db.get(SOP, sop_id)
        if not sop:
            raise ValueError(f"SOP {sop_id} not found")

        # 创建 Task 记录
        task = Task(
            team_id=team_id,
            sop_id=sop_id,
            status="running",
            input=task_input,
            session_id=session_id,
        )
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)

        # 注册团队 Agent 到池中（幂等，已注册的会跳过）
        try:
            await agent_pool.register_team_agents(self.db, team_id)
        except Exception as e:
            logger.warning(f"AgentPool registration failed (non-fatal): {e}")

        # 初始化运行时状态
        nodes = sop.nodes or []
        edges = sop.edges or []

        state = TaskState(
            task_id=str(task.id),
            sop_id=str(sop_id),
            team_id=str(team_id),
        )
        state.input = task_input
        state._node_index = {n["id"]: n for n in nodes}
        state._edge_map = self.router.build_edge_map(edges)
        state.current_node = nodes[0]["id"] if nodes else ""

        # 读取团队编排模式
        team = await self.team_mgr.get_team(team_id)
        if team:
            state.team_mode = team.collaboration_mode

        # 持久化状态（包含图的拓扑信息）
        state_dict = state.to_dict()
        state_dict["_nodes"] = nodes
        state_dict["_edges"] = edges
        state_dict["_auto_approve_hitl"] = auto_approve_hitl

        task.state = state_dict
        await self.db.commit()

        logger.info(f"SOP task started: {task.id}, SOP={sop.name}, node={state.current_node}")
        return task

    async def run_until_paused(self, task_id: uuid.UUID) -> Task:
        """运行任务直到 HITL 暂停或完成"""
        task = await self.db.get(Task, task_id)
        if not task or not task.state:
            raise ValueError(f"Task {task_id} not found or no state")

        # 恢复状态
        state = TaskState.from_dict(task.state)
        nodes = task.state.get("_nodes", [])
        edges = task.state.get("_edges", [])
        node_index = {n["id"]: n for n in nodes}
        edge_map = self.router.build_edge_map(edges)
        auto_approve = task.state.get("_auto_approve_hitl", False)

        state._node_index = node_index
        state._edge_map = edge_map

        # Observer: 创建 trace + root span
        trace_id = trace_manager.start_trace(str(task_id))
        root_span = trace_manager.start_span(trace_id, "sop_workflow")

        max_steps = 50
        step = 0

        while state.status == "running" and step < max_steps:
            step += 1

            if state.current_node not in node_index:
                state.status = "failed"
                state.errors.append(f"Unknown node: {state.current_node}")
                break

            node = node_index[state.current_node]
            node_type = node.get("type", "")
            node_label = node.get("label", state.current_node)

            logger.info(f"SOP step {step}: node={state.current_node} type={node_type}")

            # 发布节点开始事件
            await blackboard.pub(
                EventType.NODE_UPDATE,
                {
                    "task_id": state.task_id,
                    "node_id": state.current_node,
                    "label": node_label,
                    "status": "running",
                    "node_type": node_type,
                },
                team_id=state.team_id,
            )

            try:
                # Observer: 每个节点一个 span
                node_span = trace_manager.start_span(
                    trace_id, f"node_{state.current_node}", parent_span_id=root_span,
                    attributes={"node_type": node_type, "node_id": state.current_node},
                )

                if node_type == "agent_action":
                    await self.node_executor.execute_agent_node(state, node)
                    # 节点完成
                    await blackboard.pub(
                        EventType.NODE_UPDATE,
                        {
                            "task_id": state.task_id,
                            "node_id": state.current_node,
                            "label": node_label,
                            "status": "completed",
                            "node_type": node_type,
                        },
                        team_id=state.team_id,
                    )
                elif node_type == "hitl":
                    # 恢复时已有结果则跳过重新执行
                    if state.hitl_result and not state.hitl_pending:
                        logger.info(
                            f"HITL node {state.current_node}: skip (result={state.hitl_result})"
                        )
                        # 节点完成（跳过）
                        await blackboard.pub(
                            EventType.NODE_UPDATE,
                            {
                                "task_id": state.task_id,
                                "node_id": state.current_node,
                                "label": node_label,
                                "status": "completed",
                                "node_type": node_type,
                            },
                            team_id=state.team_id,
                        )
                    else:
                        should_pause = self.node_executor.execute_hitl_node(
                            state, node, auto_approve
                        )
                        if should_pause:
                            state.hitl_pending = True
                            state.status = "paused"
                            # 发布 HITL 等待事件
                            await blackboard.pub(
                                EventType.HITL_NOTIFICATION,
                                {"task_id": state.task_id, "node": state.current_node, "hitl_data": state.hitl_data},
                                team_id=state.team_id,
                            )
                            # 发布节点暂停事件
                            await blackboard.pub(
                                EventType.NODE_UPDATE,
                                {
                                    "task_id": state.task_id,
                                    "node_id": state.current_node,
                                    "label": node_label,
                                    "status": "waiting_approval",
                                    "node_type": node_type,
                                },
                                team_id=state.team_id,
                            )
                            break
                elif node_type == "validation":
                    self.node_executor.execute_validation_node(state, node)
                    # 节点完成
                    await blackboard.pub(
                        EventType.NODE_UPDATE,
                        {
                            "task_id": state.task_id,
                            "node_id": state.current_node,
                            "label": node_label,
                            "status": "completed",
                            "node_type": node_type,
                        },
                        team_id=state.team_id,
                    )
                elif node_type == "end":
                    state.status = "completed"
                    # 节点完成
                    await blackboard.pub(
                        EventType.NODE_UPDATE,
                        {
                            "task_id": state.task_id,
                            "node_id": state.current_node,
                            "label": node_label,
                            "status": "completed",
                            "node_type": node_type,
                        },
                        team_id=state.team_id,
                    )
                    # 发布任务完成事件
                    await blackboard.pub(
                        EventType.TASK_UPDATE,
                        {"task_id": state.task_id, "status": "completed", "artifacts": len(state.artifacts)},
                        team_id=state.team_id,
                    )
                    break
                elif node_type == "start":
                    pass
                else:
                    state.status = "failed"
                    state.errors.append(f"Unknown node type: {node_type}")
                    trace_manager.end_span(node_span, {"status": "failed"})
                    break

                # Observer: 节点完成
                trace_manager.end_span(node_span, {"status": state.status})
            except Exception as e:
                logger.error(f"Node {state.current_node} failed: {e}")
                state.status = "failed"
                state.errors.append(f"Node {state.current_node}: {str(e)}")
                # 发布节点失败事件
                await blackboard.pub(
                    EventType.NODE_UPDATE,
                    {
                        "task_id": state.task_id,
                        "node_id": state.current_node,
                        "label": node_label,
                        "status": "failed",
                        "node_type": node_type,
                        "error": str(e),
                    },
                    team_id=state.team_id,
                )
                # 发布任务失败事件
                await blackboard.pub(
                    EventType.TASK_UPDATE,
                    {"task_id": state.task_id, "status": "failed", "node": state.current_node, "error": str(e)},
                    team_id=state.team_id,
                )
                break

            # 路由到下一个节点
            if state.status == "running":
                next_node = self.router.route_next(state, state.current_node, edge_map)
                if next_node:
                    state.current_node = next_node
                else:
                    state.status = "completed"
                    break

        # Observer: 结束 trace
        trace_manager.end_span(root_span, {"status": state.status, "steps": step})
        trace_manager.end_trace(trace_id)

        # 持久化最终状态
        await self._persist_and_commit(task, state, nodes, edges, auto_approve)
        return task

    async def resume_task(
        self, task_id: uuid.UUID, action: str, comment: str = ""
    ) -> Task:
        """从 HITL 暂停恢复"""
        task = await self.db.get(Task, task_id)
        if not task or not task.state:
            raise ValueError(f"Task {task_id} not found")

        state = TaskState.from_dict(task.state)
        if not state.hitl_pending:
            raise ValueError("Task is not waiting for HITL input")

        state.hitl_result = action
        state.hitl_pending = False
        state.status = "running"
        state.messages.append({
            "role": "human",
            "content": f"[HITL] {action}: {comment}",
            "timestamp": datetime.utcnow().isoformat(),
        })

        # 更新状态后继续运行
        state_dict = state.to_dict()
        state_dict["_nodes"] = task.state.get("_nodes", [])
        state_dict["_edges"] = task.state.get("_edges", [])
        state_dict["_auto_approve_hitl"] = task.state.get("_auto_approve_hitl", False)
        task.state = state_dict
        task.status = "running"
        await self.db.commit()

        return await self.run_until_paused(task_id)

    async def _persist_and_commit(
        self,
        task: Task,
        state: TaskState,
        nodes: list[dict],
        edges: list[dict],
        auto_approve: bool,
    ) -> None:
        """持久化运行时状态并提交到数据库"""
        state_dict = state.to_dict()
        state_dict["_nodes"] = nodes
        state_dict["_edges"] = edges
        state_dict["_auto_approve_hitl"] = auto_approve

        task.state = state_dict
        task.status = state.status
        if state.artifacts:
            task.artifacts = {a.get("node", "unknown"): a for a in state.artifacts}
        await self.db.commit()
        await self.db.refresh(task)
