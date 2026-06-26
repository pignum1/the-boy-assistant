"""SOP Node Executor：工作流各类型节点的执行逻辑

集成 AgentPool：执行前 acquire，执行后 release（含异常时 mark_error）
Supervisor 模式：先调 supervisor 分配 → worker 执行 → supervisor 审核
"""

import logging
import uuid
import time
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.sop_state import TaskState
from app.services.sop_router import SOPRouter
from app.services.team_manager import TeamManager
from app.services.agent_pool import agent_pool
from app.services.session_manager import get_session_manager

logger = logging.getLogger(__name__)


class SOPNodeExecutor:
    """节点执行器：负责执行各类 SOP 节点（agent_action / hitl / validation）"""

    def __init__(self, db: AsyncSession, team_mgr: TeamManager):
        self.db = db
        self.team_mgr = team_mgr
        self.router = SOPRouter()

    async def execute_agent_node(self, state: TaskState, node: dict) -> None:
        """执行 Agent 节点：根据 team mode 选择调度策略"""
        if state.team_mode == "supervisor":
            await self._execute_with_supervisor(state, node)
        else:
            await self._execute_direct(state, node)

    async def _execute_with_supervisor(self, state: TaskState, node: dict) -> None:
        """Supervisor 模式：主管调度 → worker 执行 → 主管审核"""
        from app.services.agent_factory import agent_chat

        role_slot = node.get("role_slot", "")
        team_uuid = uuid.UUID(state.team_id) if state.team_id else None

        # 获取 supervisor agent
        team = await self.team_mgr.get_team(team_uuid)
        supervisor = None
        if team and team.leader_id:
            from app.models.agent import Agent
            supervisor = await self.db.get(Agent, team.leader_id)
        if not supervisor:
            supervisor = await self.team_mgr.get_agent_for_slot(team_uuid, "pm")
        if not supervisor:
            raise ValueError(f"No supervisor agent for team {state.team_id}")

        # 获取 worker agent
        worker = await self.team_mgr.get_agent_for_slot(team_uuid, role_slot)
        if not worker:
            raise ValueError(f"No agent for role_slot '{role_slot}' in team {state.team_id}")

        # ── 阶段 1: Supervisor 调度 ──
        prev_outputs = self._format_artifacts(state.artifacts[-3:])
        task_input = state.input.get("requirements", state.input.get("message", ""))

        dispatch_prompt = (
            f"你是团队主管(supervisor)，负责协调任务分配和质量把控。\n\n"
            f"## 当前节点\n"
            f"- 标签: {node.get('label', '')}\n"
            f"- 角色: {role_slot}\n"
            f"- 执行者: {worker.name}\n\n"
            f"## 任务需求\n{task_input}\n\n"
        )
        if prev_outputs:
            dispatch_prompt += f"## 前序产出\n{prev_outputs}\n\n"
        dispatch_prompt += (
            "请给出执行指导：\n"
            "1. 关键要求和注意事项\n"
            "2. 预期产出格式和内容\n"
            "3. 需要特别注意的质量标准"
        )

        supervisor_id = str(supervisor.id)
        await agent_pool.acquire_with_retry(
            agent_id=supervisor_id, role_slot="pm",
            task_id=state.task_id, max_retries=3, interval=2.0,
        )
        try:
            session_mgr = get_session_manager(self.db)
            session = await session_mgr.get_or_create_session(
                team_id=state.team_id or "",
                agent_id=supervisor_id,
                task_id=state.task_id,
            )

            t0 = time.time()
            dispatch_result = await agent_chat(
                db=self.db, agent=supervisor, message=dispatch_prompt,
                team_id=state.team_id, session_id=session.session_id, mock=False,
            )
            dispatch_elapsed = time.time() - t0
            dispatch_guidance = dispatch_result.get("content", "")

            state.artifacts.append({
                "node": node["id"],
                "phase": "supervisor_dispatch",
                "agent": supervisor.name,
                "role_slot": "supervisor",
                "output": dispatch_guidance,
                "latency": round(dispatch_elapsed, 2),
            })

            try:
                await session_mgr.close_session(session.session_id)
            except Exception:
                pass
        finally:
            await agent_pool.release(supervisor_id)

        # ── 阶段 2: Worker 执行 ──
        worker_id = str(worker.id)
        await agent_pool.acquire_with_retry(
            agent_id=worker_id, role_slot=role_slot,
            task_id=state.task_id, max_retries=3, interval=2.0,
        )
        try:
            session_mgr = get_session_manager(self.db)
            session = await session_mgr.get_or_create_session(
                team_id=state.team_id or "",
                agent_id=worker_id,
                task_id=state.task_id,
            )

            worker_input = (
                f"## 主管指导\n{dispatch_guidance}\n\n"
                f"## 你的任务\n{task_input}"
            )
            if prev_outputs:
                worker_input = f"## 前序产出\n{prev_outputs}\n\n{worker_input}"

            t0 = time.time()
            result = await agent_chat(
                db=self.db, agent=worker, message=worker_input,
                team_id=state.team_id, session_id=session.session_id, mock=False,
            )
            elapsed = time.time() - t0

            output = result.get("content", "")
            routing = result.get("routing", {})

            state.artifacts.append({
                "node": node["id"],
                "phase": "worker_output",
                "agent": worker.name,
                "role_slot": role_slot,
                "output": output,
                "model": routing.get("routed_model", ""),
                "complexity": routing.get("complexity", ""),
                "latency": round(elapsed, 2),
            })

            try:
                await session_mgr.close_session(session.session_id)
            except Exception:
                pass
        except Exception:
            await agent_pool.mark_error(worker_id)
            raise
        finally:
            await agent_pool.release(worker_id)

        # ── 阶段 3: Supervisor 审核 ──
        await agent_pool.acquire_with_retry(
            agent_id=supervisor_id, role_slot="pm",
            task_id=state.task_id, max_retries=3, interval=2.0,
        )
        try:
            session_mgr = get_session_manager(self.db)
            session = await session_mgr.get_or_create_session(
                team_id=state.team_id or "",
                agent_id=supervisor_id,
                task_id=state.task_id,
            )

            review_prompt = (
                f"你是团队主管，请审核以下工作产出。\n\n"
                f"## 原始指导\n{dispatch_guidance[:800]}\n\n"
                f"## 执行者产出（{worker.name}）\n{output[:1500]}\n\n"
                f"请给出审核意见：是否通过？如有问题请指出需要修改的地方。"
            )

            t0 = time.time()
            review_result = await agent_chat(
                db=self.db, agent=supervisor, message=review_prompt,
                team_id=state.team_id, session_id=session.session_id, mock=False,
            )
            review_elapsed = time.time() - t0
            review_content = review_result.get("content", "")

            state.artifacts.append({
                "node": node["id"],
                "phase": "supervisor_review",
                "agent": supervisor.name,
                "role_slot": "supervisor",
                "output": review_content,
                "latency": round(review_elapsed, 2),
            })
            state.messages.append({
                "role": "agent",
                "agent_name": worker.name,
                "content": output[:2000],
                "timestamp": datetime.utcnow().isoformat(),
                "supervisor_review": review_content[:500],
            })

            logger.info(
                f"Supervisor node {node['id']}: dispatch={dispatch_elapsed:.1f}s "
                f"worker={elapsed:.1f}s review={review_elapsed:.1f}s"
            )

            try:
                await session_mgr.close_session(session.session_id)
            except Exception:
                pass
        finally:
            await agent_pool.release(supervisor_id)

    async def _execute_direct(self, state: TaskState, node: dict) -> None:
        """直接调用 worker（swarm/hierarchy 模式，向后兼容）"""
        from app.services.agent_factory import agent_chat

        role_slot = node.get("role_slot", "")
        team_uuid = uuid.UUID(state.team_id) if state.team_id else None

        agent = await self.team_mgr.get_agent_for_slot(team_uuid, role_slot)
        if not agent:
            raise ValueError(f"No agent for role_slot '{role_slot}' in team {state.team_id}")

        agent_id = str(agent.id)

        # 通过 AgentPool acquire（带重试）
        entry = await agent_pool.acquire_with_retry(
            agent_id=agent_id,
            role_slot=role_slot,
            task_id=state.task_id,
            max_retries=3,
            interval=2.0,
        )
        if not entry:
            raise ValueError(
                f"Cannot acquire agent '{agent.name}' for role_slot '{role_slot}'"
            )

        try:
            # 获取或创建 Session（记忆隔离）
            session_mgr = get_session_manager(self.db)
            session = await session_mgr.get_or_create_session(
                team_id=state.team_id or "",
                agent_id=agent_id,
                task_id=state.task_id,
            )

            # 组装输入：任务上下文 + 前序产出
            task_input = state.input.get("requirements", state.input.get("message", ""))

            if state.artifacts:
                prev_outputs = self._format_artifacts(state.artifacts[-3:])
                task_input = f"前置产出:\n{prev_outputs}\n\n当前任务:\n{task_input}"

            t0 = time.time()
            result = await agent_chat(
                db=self.db,
                agent=agent,
                message=task_input,
                team_id=state.team_id,
                session_id=session.session_id,
                mock=False,
            )
            elapsed = time.time() - t0

            output = result.get("content", "")
            routing = result.get("routing", {})

            state.artifacts.append({
                "node": node["id"],
                "agent": agent.name,
                "role_slot": role_slot,
                "output": output,
                "model": routing.get("routed_model", ""),
                "complexity": routing.get("complexity", ""),
                "latency": round(elapsed, 2),
            })
            state.messages.append({
                "role": "agent",
                "agent_name": agent.name,
                "content": output[:2000],
                "timestamp": datetime.utcnow().isoformat(),
            })

            logger.info(f"Agent node {node['id']}: {agent.name} completed in {elapsed:.1f}s")

        except Exception:
            await agent_pool.mark_error(agent_id)
            raise
        finally:
            await agent_pool.release(agent_id)
            try:
                session_mgr = get_session_manager(self.db)
                await session_mgr.close_session(session.session_id)
            except Exception as e:
                logger.warning(f"Session close failed (non-fatal): {e}")

    def _format_artifacts(self, artifacts: list[dict]) -> str:
        """格式化前序产出"""
        if not artifacts:
            return ""
        return "\n".join(
            f"[{a.get('phase', a.get('node'))}] {a.get('output', '')[:500]}"
            for a in artifacts
        )

    def execute_hitl_node(
        self, state: TaskState, node: dict, auto_approve: bool
    ) -> bool:
        """执行 HITL（人工审批）节点。返回 True 表示需要暂停等待人工输入。

        三层审批策略：
        1. 任务级 auto_approve → 直接通过
        2. 节点级 require_human=False → 按配置自动通过
        3. 条件自动审批 → 满足条件时自动通过
        """
        config = node.get("config", {})

        # 第 1 层：任务级自动审批
        if auto_approve:
            state.hitl_result = "approve"
            state.messages.append({
                "role": "system",
                "content": "[HITL] 自动通过（任务级 auto_approve）",
                "timestamp": datetime.utcnow().isoformat(),
            })
            return False

        # 第 2 层：节点级 require_human=False
        if not config.get("require_human", True):
            auto_action = config.get("auto_action", "approve")
            state.hitl_result = auto_action
            state.messages.append({
                "role": "system",
                "content": f"[HITL] 自动{auto_action}（require_human=false）",
                "timestamp": datetime.utcnow().isoformat(),
            })
            return False

        # 第 3 层：条件自动审批
        condition = config.get("condition")
        if condition:
            ctx = {
                "last_confidence": state.last_confidence,
                "hitl_result": state.hitl_result,
                "validations": state.validations,
                **state.input,
            }
            field_val = self.router.resolve_state_field(
                condition.get("field", ""), state
            )
            operator = condition.get("operator", ">=")
            threshold = condition.get("value", 0.8)

            expr = f"{condition['field']} {operator} {threshold}"
            ctx["last_confidence"] = state.last_confidence

            if self.router.condition_router.evaluate(expr, ctx):
                auto_action = condition.get("auto_action", "approve")
                state.hitl_result = auto_action
                state.messages.append({
                    "role": "system",
                    "content": f"[HITL] 条件自动{auto_action}（{expr} 满足）",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                return False

        # 需要人工审批
        state.hitl_data = {
            "node": node["id"],
            "message": node.get("message", "请确认"),
            "timeout": config.get("timeout", 300),
        }
        state.hitl_pending = True
        return True

    def execute_validation_node(self, state: TaskState, node: dict) -> None:
        """执行验证节点（MVP：模拟验证，真实场景需接 lint/test 工具）"""
        checks = node.get("checks", [])
        threshold = node.get("pass_threshold", 80)

        results = []
        for check in checks:
            results.append({
                "check": check,
                "passed": True,
                "score": threshold + 5,
            })

        all_passed = all(r["passed"] for r in results)
        state.validations = {
            "passed": all_passed,
            "results": results,
        }
        state.messages.append({
            "role": "system",
            "content": f"[Validation] checks={checks} passed={all_passed}",
            "timestamp": datetime.utcnow().isoformat(),
        })
