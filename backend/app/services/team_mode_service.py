"""Team 协作模式配置 service · 三种模式的 CRUD

每种 mode 一个独立的小服务，避免巨型 service。

DDD 边界：归属 Workflow 域（团队协作编排）。
"""

import uuid
from typing import Optional, Sequence

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.team import Team
from app.models.team_member import TeamMember
from app.models.team_mode_configs import (
    TeamSwarmConfig,
    TeamSupervisorConfig,
    TeamSupervisorRelation,
    TeamLanggraphConfig,
    TeamLanggraphNodeBinding,
)


VALID_MODES = {"swarm", "supervisor", "langgraph"}


class TeamModeService:
    """统一管理三种协作模式的配置。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── 通用：设置/切换协作模式 ──

    async def set_mode(self, team_id: uuid.UUID, mode: str) -> Team:
        if mode not in VALID_MODES:
            raise ValueError(f"unknown mode {mode!r}, must be one of {VALID_MODES}")
        team = await self.db.get(Team, team_id)
        if not team:
            raise ValueError("team not found")
        team.collaboration_mode = mode
        # 确保目标 mode 有空配置（在同一事务中完成）
        await self._ensure_config_exists(team_id, mode)
        await self.db.commit()
        await self.db.refresh(team)
        return team

    async def _ensure_config_exists(self, team_id: uuid.UUID, mode: str) -> None:
        if mode == "swarm":
            existing = await self.get_swarm_config(team_id)
            if not existing:
                self.db.add(TeamSwarmConfig(team_id=team_id))
        elif mode == "supervisor":
            existing = await self.get_supervisor_config(team_id)
            if not existing:
                self.db.add(TeamSupervisorConfig(team_id=team_id))
        elif mode == "langgraph":
            existing = await self.get_langgraph_config(team_id)
            if not existing:
                self.db.add(TeamLanggraphConfig(team_id=team_id))
        # 不在此处提交，由调用方统一提交

    # ── Swarm ──

    async def get_swarm_config(self, team_id: uuid.UUID) -> Optional[TeamSwarmConfig]:
        stmt = select(TeamSwarmConfig).where(TeamSwarmConfig.team_id == team_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def upsert_swarm_config(
        self,
        team_id: uuid.UUID,
        max_rounds: int = 10,
        speak_strategy: str = "auto",
        termination_condition: Optional[str] = None,
    ) -> TeamSwarmConfig:
        if speak_strategy not in ("auto", "round_robin", "priority"):
            raise ValueError(f"unknown speak_strategy {speak_strategy!r}")
        cfg = await self.get_swarm_config(team_id)
        if cfg is None:
            cfg = TeamSwarmConfig(team_id=team_id)
            self.db.add(cfg)
        cfg.max_rounds = max_rounds
        cfg.speak_strategy = speak_strategy
        cfg.termination_condition = termination_condition
        await self.db.commit()
        await self.db.refresh(cfg)
        return cfg

    # ── Supervisor ──

    async def get_supervisor_config(self, team_id: uuid.UUID) -> Optional[TeamSupervisorConfig]:
        stmt = select(TeamSupervisorConfig).where(TeamSupervisorConfig.team_id == team_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def set_leader(self, team_id: uuid.UUID, leader_member_id: Optional[uuid.UUID]) -> TeamSupervisorConfig:
        cfg = await self.get_supervisor_config(team_id)
        if cfg is None:
            cfg = TeamSupervisorConfig(team_id=team_id)
            self.db.add(cfg)
        if leader_member_id:
            # 校验 member 属于同团队
            mem = await self.db.get(TeamMember, leader_member_id)
            if not mem or mem.team_id != team_id:
                raise ValueError("leader_member must belong to the same team")
        cfg.leader_member_id = leader_member_id
        await self.db.commit()
        await self.db.refresh(cfg)
        return cfg

    async def get_supervisor_relations(self, team_id: uuid.UUID) -> Sequence[TeamSupervisorRelation]:
        stmt = select(TeamSupervisorRelation).where(TeamSupervisorRelation.team_id == team_id)
        return list((await self.db.execute(stmt)).scalars().all())

    async def set_supervisor_relation(
        self,
        team_id: uuid.UUID,
        member_id: uuid.UUID,
        supervisor_member_id: Optional[uuid.UUID],
    ) -> Optional[TeamSupervisorRelation]:
        """设置/清除某成员的直属上级。supervisor_member_id=None 表示清除。"""
        # 先删旧关系
        await self.db.execute(
            delete(TeamSupervisorRelation).where(
                TeamSupervisorRelation.team_id == team_id,
                TeamSupervisorRelation.member_id == member_id,
            )
        )
        if not supervisor_member_id:
            await self.db.commit()
            return None
        if supervisor_member_id == member_id:
            raise ValueError("cannot report to self")
        # 校验同团队
        mem = await self.db.get(TeamMember, member_id)
        sup = await self.db.get(TeamMember, supervisor_member_id)
        if not mem or mem.team_id != team_id:
            raise ValueError("member not in team")
        if not sup or sup.team_id != team_id:
            raise ValueError("supervisor not in team")
        rel = TeamSupervisorRelation(
            team_id=team_id,
            member_id=member_id,
            supervisor_member_id=supervisor_member_id,
        )
        self.db.add(rel)
        await self.db.commit()
        await self.db.refresh(rel)
        return rel

    async def bulk_set_supervisor_relations(
        self,
        team_id: uuid.UUID,
        relations: list[dict],  # [{member_id, supervisor_member_id}]
    ) -> int:
        """批量设置（先清空，再插入）"""
        await self.db.execute(
            delete(TeamSupervisorRelation).where(TeamSupervisorRelation.team_id == team_id)
        )
        count = 0
        for r in relations:
            mid = r.get("member_id")
            sid = r.get("supervisor_member_id")
            if not mid or not sid:
                continue
            if mid == sid:
                continue
            self.db.add(TeamSupervisorRelation(
                team_id=team_id,
                member_id=uuid.UUID(str(mid)),
                supervisor_member_id=uuid.UUID(str(sid)),
            ))
            count += 1
        await self.db.commit()
        return count

    # ── LangGraph ──

    async def get_langgraph_config(self, team_id: uuid.UUID) -> Optional[TeamLanggraphConfig]:
        stmt = select(TeamLanggraphConfig).where(TeamLanggraphConfig.team_id == team_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def set_workflow(self, team_id: uuid.UUID, workflow_id: Optional[uuid.UUID]) -> TeamLanggraphConfig:
        cfg = await self.get_langgraph_config(team_id)
        if cfg is None:
            cfg = TeamLanggraphConfig(team_id=team_id)
            self.db.add(cfg)
        cfg.workflow_id = workflow_id
        await self.db.commit()
        await self.db.refresh(cfg)
        return cfg

    async def get_node_bindings(self, team_id: uuid.UUID) -> Sequence[TeamLanggraphNodeBinding]:
        cfg = await self.get_langgraph_config(team_id)
        if not cfg:
            return []
        stmt = select(TeamLanggraphNodeBinding).where(TeamLanggraphNodeBinding.config_id == cfg.id)
        return list((await self.db.execute(stmt)).scalars().all())

    async def set_node_binding(
        self,
        team_id: uuid.UUID,
        node_key: str,
        agent_id: uuid.UUID,
    ) -> TeamLanggraphNodeBinding:
        cfg = await self.get_langgraph_config(team_id)
        if not cfg:
            cfg = TeamLanggraphConfig(team_id=team_id)
            self.db.add(cfg)
            await self.db.flush()  # 获取 ID，不提交（与后续操作在同一事务）
            await self.db.refresh(cfg)
        # upsert
        await self.db.execute(
            delete(TeamLanggraphNodeBinding).where(
                TeamLanggraphNodeBinding.config_id == cfg.id,
                TeamLanggraphNodeBinding.node_key == node_key,
            )
        )
        b = TeamLanggraphNodeBinding(config_id=cfg.id, node_key=node_key, agent_id=agent_id)
        self.db.add(b)
        await self.db.commit()
        await self.db.refresh(b)
        return b

    async def bulk_set_node_bindings(
        self,
        team_id: uuid.UUID,
        bindings: list[dict],  # [{node_key, agent_id}]
    ) -> int:
        cfg = await self.get_langgraph_config(team_id)
        if not cfg:
            cfg = TeamLanggraphConfig(team_id=team_id)
            self.db.add(cfg)
            await self.db.flush()  # 获取 ID，不提交（与后续操作在同一事务）
            await self.db.refresh(cfg)
        # clear + bulk insert
        await self.db.execute(
            delete(TeamLanggraphNodeBinding).where(TeamLanggraphNodeBinding.config_id == cfg.id)
        )
        count = 0
        for b in bindings:
            nk = b.get("node_key")
            aid = b.get("agent_id")
            if not nk or not aid:
                continue
            self.db.add(TeamLanggraphNodeBinding(
                config_id=cfg.id, node_key=nk, agent_id=uuid.UUID(str(aid))
            ))
            count += 1
        await self.db.commit()
        return count
