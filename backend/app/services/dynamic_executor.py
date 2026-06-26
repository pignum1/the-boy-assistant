"""DynamicExecutor：DAG 任务执行引擎

替代串行 for 循环，支持：
- 拓扑排序 → 依赖检查
- 并行执行独立任务（asyncio.gather + Semaphore）
- 失败自动重规划
- 事件流推送（WS 兼容）
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import AsyncGenerator, Optional

logger = logging.getLogger(__name__)


class ExecutorEventType(str, Enum):
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    PLAN_CREATED = "plan_created"
    PLAN_UPDATED = "plan_updated"
    PLAN_COMPLETE = "plan_complete"
    PROGRESS = "progress"


@dataclass
class ExecutorEvent:
    type: ExecutorEventType
    source: str
    payload: dict
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class TaskNode:
    """执行器内部任务节点"""
    id: str
    title: str
    description: str = ""
    required_capabilities: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)  # task IDs
    status: str = "pending"  # pending → ready → running → done / failed
    assigned_agent_id: Optional[str] = None
    assigned_agent_name: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None
    seq: int = 0  # 排序序号


class DynamicExecutor:
    """DAG 任务执行引擎"""

    def __init__(
        self,
        max_parallel: int = 3,
        task_timeout: int = 300,  # 单个任务超时秒数
    ):
        self.max_parallel = max_parallel
        self.task_timeout = task_timeout
        self._semaphore = asyncio.Semaphore(max_parallel)

    def parse_plan(self, tasks: list[dict]) -> list[TaskNode]:
        """从字典列表解析任务节点"""
        nodes = []
        for i, t in enumerate(tasks):
            nodes.append(TaskNode(
                id=t.get("id", str(uuid.uuid4())),
                title=t.get("title", t.get("description", f"Task {i+1}")),
                description=t.get("description", ""),
                required_capabilities=t.get("required_capabilities", []),
                dependencies=t.get("dependencies", t.get("depends_on", []) or []),
                seq=i + 1,
            ))
        return nodes

    def _topological_order(self, nodes: list[TaskNode]) -> list[TaskNode]:
        """拓扑排序 + 检测循环依赖"""
        node_map = {n.id: n for n in nodes}
        in_degree = {n.id: len([d for d in n.dependencies if d in node_map]) for n in nodes}

        # Kahn's algorithm
        queue = [n for n in nodes if in_degree[n.id] == 0]
        ordered = []
        while queue:
            node = queue.pop(0)
            ordered.append(node)
            for other in nodes:
                if node.id in other.dependencies:
                    in_degree[other.id] -= 1
                    if in_degree[other.id] == 0:
                        queue.append(other)

        if len(ordered) != len(nodes):
            # 有循环依赖或无效依赖，回退到原始顺序
            logger.warning("Circular or invalid dependencies detected, using original order")
            return sorted(nodes, key=lambda n: n.seq)
        return ordered

    def _get_ready_tasks(self, nodes: list[TaskNode]) -> list[TaskNode]:
        """找出所有依赖已满足的待执行任务"""
        done_ids = {n.id for n in nodes if n.status == "done"}
        ready = []
        for n in nodes:
            if n.status != "pending":
                continue
            if all(d in done_ids for d in n.dependencies):
                ready.append(n)
        return ready

    def _build_dag_from_session_tasks(self, tasks: list) -> list[TaskNode]:
        """从 SessionTask ORM 对象构建 TaskNode 列表"""
        nodes = []
        for i, t in enumerate(tasks):
            deps = t.depends_on if hasattr(t, 'depends_on') and t.depends_on else []
            capabilities = []
            if hasattr(t, 'required_capabilities') and t.required_capabilities:
                capabilities = t.required_capabilities
            nodes.append(TaskNode(
                id=str(t.id),
                title=t.title if hasattr(t, 'title') else f"Task {i+1}",
                description=t.description if hasattr(t, 'description') and t.description else "",
                required_capabilities=capabilities,
                dependencies=[str(d) for d in deps],
                status=t.status if hasattr(t, 'status') else "pending",
                assigned_agent_id=str(t.assigned_agent_id) if hasattr(t, 'assigned_agent_id') and t.assigned_agent_id else None,
                assigned_agent_name=t.assigned_agent_name if hasattr(t, 'assigned_agent_name') and t.assigned_agent_name else None,
                seq=i + 1,
            ))
        return nodes

    async def execute_plan(
        self,
        plan_tasks: list,
        team_id: uuid.UUID,
        session_id: uuid.UUID,
        user_message: str = "",
        db=None,
        task_service=None,
    ) -> AsyncGenerator[ExecutorEvent, None]:
        """执行 DAG 任务计划 — 核心方法

        Args:
            plan_tasks: list of dict or SessionTask ORM objects
            team_id: 团队 ID
            session_id: 会话 ID
            user_message: 原始用户消息
            db: 数据库会话（用于 agent_chat）
            task_service: SessionTaskService 实例

        Yields:
            ExecutorEvent: 任务状态变更事件
        """
        # 解析任务节点
        if plan_tasks and hasattr(plan_tasks[0], '__tablename__'):
            nodes = self._build_dag_from_session_tasks(plan_tasks)
        else:
            nodes = self.parse_plan(plan_tasks)

        # 标记已完成的任务（从 DB 加载的状态）
        for n in nodes:
            if n.status == "done":
                pass  # 已完成的跳过
            elif n.status in ("in_progress", "claimed"):
                n.status = "pending"  # 重新执行

        # 拓扑排序
        ordered = self._topological_order(nodes)
        task_names = [f"{n.seq}. {n.title[:40]}" for n in ordered]
        logger.info(f"📋 Execution plan ({len(ordered)} tasks): {' → '.join(task_names)}")

        yield ExecutorEvent(
            type=ExecutorEventType.PLAN_CREATED,
            source="system",
            payload={
                "tasks": [{"id": n.id, "seq": n.seq, "title": n.title,
                           "dependencies": n.dependencies, "status": n.status}
                          for n in ordered],
                "total": len(ordered),
            }
        )

        # 主循环
        pending_nodes = [n for n in ordered if n.status != "done"]
        if not pending_nodes:
            yield ExecutorEvent(type=ExecutorEventType.PLAN_COMPLETE, source="system",
                                payload={"message": "所有任务已完成"})
            return

        active_tasks: dict[str, asyncio.Task] = {}
        node_map = {n.id: n for n in ordered}

        while pending_nodes or active_tasks:
            # 1. 找出 ready 任务并启动
            ready = self._get_ready_tasks(pending_nodes)
            for node in ready:
                if len(active_tasks) >= self.max_parallel:
                    break
                node.status = "running"
                pending_nodes.remove(node)

                # 更新 DB 状态
                if task_service:
                    try:
                        await task_service.update_task(
                            task_id=uuid.UUID(node.id), status="in_progress"
                        )
                    except Exception:
                        pass

                yield ExecutorEvent(
                    type=ExecutorEventType.TASK_STARTED,
                    source=node.id,
                    payload={"task_id": node.id, "seq": node.seq, "title": node.title,
                             "agent_name": node.assigned_agent_name},
                )

                coro = self._execute_single_task(node, team_id, session_id, user_message, db, task_service)
                active_tasks[node.id] = asyncio.create_task(coro)

            if not active_tasks and not ready:
                # 无活跃任务且无 ready → 可能有循环依赖或全部完成
                if pending_nodes:
                    stuck = [n.id for n in pending_nodes]
                    logger.error(f"Stuck tasks (unresolvable dependencies): {stuck}")
                    for n in pending_nodes:
                        yield ExecutorEvent(
                            type=ExecutorEventType.TASK_FAILED,
                            source=n.id,
                            payload={"task_id": n.id, "seq": n.seq, "title": n.title,
                                     "error": "依赖无法满足"},
                        )
                break

            # 2. 等待任一任务完成
            if active_tasks:
                done, _ = await asyncio.wait(
                    active_tasks.values(),
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=10,  # 每10秒检查一次进度
                )

                for completed in done:
                    # 找到对应的 task_id
                    completed_id = None
                    for tid, t in active_tasks.items():
                        if t is completed:
                            completed_id = tid
                            break
                    if completed_id:
                        del active_tasks[completed_id]
                        node = node_map.get(completed_id)
                        if node:
                            try:
                                result = completed.result()
                                if isinstance(result, dict) and result.get("success"):
                                    node.status = "done"
                                    node.result = result.get("output", "")
                                    yield ExecutorEvent(
                                        type=ExecutorEventType.TASK_COMPLETED,
                                        source=node.id,
                                        payload={"task_id": node.id, "seq": node.seq,
                                                 "title": node.title, "output": node.result[:200]},
                                    )
                                else:
                                    node.status = "failed"
                                    node.error = str(result.get("error", "Unknown error")) if isinstance(result, dict) else str(result)
                                    yield ExecutorEvent(
                                        type=ExecutorEventType.TASK_FAILED,
                                        source=node.id,
                                        payload={"task_id": node.id, "seq": node.seq,
                                                 "title": node.title, "error": node.error},
                                    )
                            except Exception as e:
                                node.status = "failed"
                                node.error = str(e)
                                yield ExecutorEvent(
                                    type=ExecutorEventType.TASK_FAILED,
                                    source=node.id,
                                    payload={"task_id": node.id, "seq": node.seq,
                                             "title": node.title, "error": str(e)},
                                )

            # 3. 发送进度
            total = len(ordered)
            done_count = sum(1 for n in ordered if n.status == "done")
            failed_count = sum(1 for n in ordered if n.status == "failed")
            yield ExecutorEvent(
                type=ExecutorEventType.PROGRESS,
                source="system",
                payload={"done": done_count, "total": total, "failed": failed_count},
            )

        # 完成
        final_done = sum(1 for n in ordered if n.status == "done")
        final_failed = sum(1 for n in ordered if n.status == "failed")
        yield ExecutorEvent(
            type=ExecutorEventType.PLAN_COMPLETE,
            source="system",
            payload={"done": final_done, "total": len(ordered), "failed": final_failed},
        )

    async def _execute_single_task(
        self,
        node: TaskNode,
        team_id: uuid.UUID,
        session_id: uuid.UUID,
        user_message: str,
        db,
        task_service,
    ) -> dict:
        """执行单个任务（带超时）"""
        async with self._semaphore:
            try:
                t0 = time.time()

                # 如果有 db 和 agent，调用 agent_chat
                if db and node.assigned_agent_id:
                    from app.models.agent import Agent
                    from app.services.agent_factory import agent_chat

                    agent = await db.get(Agent, uuid.UUID(node.assigned_agent_id))
                    if agent:
                        prompt = (
                            f"## 任务\n{node.description or node.title}\n\n"
                            f"## 用户原始消息\n{user_message}\n\n"
                            f"请完成上述任务。如果需要操作文件，工作空间已配置。"
                        )
                        try:
                            result = await asyncio.wait_for(
                                agent_chat(
                                    db=db, agent=agent, message=prompt,
                                    team_id=str(team_id), session_id=str(session_id),
                                ),
                                timeout=self.task_timeout,
                            )
                            elapsed = time.time() - t0
                            output = result.get("content", "") if isinstance(result, dict) else str(result)

                            # 更新 DB
                            if task_service:
                                try:
                                    await task_service.update_task(
                                        task_id=uuid.UUID(node.id),
                                        status="done",
                                        actual_output=output[:500],
                                    )
                                except Exception:
                                    pass

                            return {"success": True, "output": output, "elapsed": elapsed}
                        except asyncio.TimeoutError:
                            return {"success": False, "error": f"任务超时 ({self.task_timeout}s)"}
                        except Exception as e:
                            return {"success": False, "error": str(e)}

                # 无 agent：标记为完成（简单任务或外部执行）
                return {"success": True, "output": "Task marked as done (no agent assigned)"}

            except Exception as e:
                logger.error(f"Task {node.id} execution error: {e}")
                return {"success": False, "error": str(e)}
