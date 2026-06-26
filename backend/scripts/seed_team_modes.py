"""PR-A · 团队模式 seed 脚本

任务：
1. 删除产品开发团队以外的所有团队
2. 给产品开发团队设 supervisor 模式
3. 找到 PM 设为 leader
4. seed 委派关系：PM→架构师/UI；架构师→前端/后端/测试/部署

执行：
  cd backend && PYTHONPATH=. python scripts/seed_team_modes.py
"""

import asyncio
import uuid
from sqlalchemy import select, delete

from app.core.database import async_session
from app.models.team import Team
from app.models.team_member import TeamMember
from app.services.team_mode_service import TeamModeService


PROD_TEAM_ID = uuid.UUID("62f0110c-addd-4989-973d-826f45212053")  # 产品开发团队


async def main():
    async with async_session() as db:
        # 1) 删除其他团队（先清理引用：sops + sessions + team_members + 其它子表会 CASCADE）
        from app.models.sop import SOP
        from app.models.session import Session as SessionModel
        all_teams = (await db.execute(select(Team))).scalars().all()
        to_delete = [t for t in all_teams if t.id != PROD_TEAM_ID]
        print(f"[seed] found {len(all_teams)} teams, keeping 产品开发团队, deleting {len(to_delete)} others")
        # 先删 tasks 引用的 sops，再删 sops，再删 sessions/teams
        from app.models.task import Task
        from sqlalchemy import text
        for t in to_delete:
            # tasks → sops（删 task 引用了 t 的 sops 的）
            sops_ids = (await db.execute(select(SOP.id).where(SOP.team_id == t.id))).scalars().all()
            if sops_ids:
                await db.execute(delete(Task).where(Task.sop_id.in_(sops_ids)))
            await db.execute(delete(SOP).where(SOP.team_id == t.id))
            await db.execute(delete(SessionModel).where(SessionModel.team_id == t.id))
            try:
                await db.execute(delete(Team).where(Team.id == t.id))
                await db.commit()
            except Exception as e:
                print(f"[seed] skip {t.name}: {e}")
                await db.rollback()

        # 2) 设置产品开发团队为 supervisor 模式
        svc = TeamModeService(db)
        try:
            team = await svc.set_mode(PROD_TEAM_ID, "supervisor")
        except ValueError:
            print("[seed] 产品开发团队 not found, abort")
            return
        print(f"[seed] team={team.name} mode set to {team.collaboration_mode}")

        # 3) 查找 PM 成员
        members = (await db.execute(
            select(TeamMember).where(TeamMember.team_id == PROD_TEAM_ID)
        )).scalars().all()
        by_role: dict[str, TeamMember] = {}
        for m in members:
            rn = (m.role_name or "").lower()
            if "pm" in rn or "产品" in rn:
                by_role["pm"] = m
            elif "architect" in rn or "架构" in rn:
                by_role["architect"] = m
            elif "ui" in rn or "设计" in rn:
                by_role["ui"] = m
            elif "frontend" in rn or "前端" in rn:
                by_role["frontend"] = m
            elif "backend" in rn or "后端" in rn:
                by_role["backend"] = m
            elif "test" in rn or "qa" in rn or "测试" in rn:
                by_role["tester"] = m
            elif "devops" in rn or "运维" in rn or "部署" in rn:
                by_role["devops"] = m

        print(f"[seed] roles found: {list(by_role.keys())}")
        if "pm" not in by_role:
            print("[seed] no PM found, abort relation seeding")
            return

        # 4) Set leader = PM
        await svc.set_leader(PROD_TEAM_ID, by_role["pm"].id)
        print(f"[seed] leader = PM ({by_role['pm'].agent_id})")

        # 5) Seed supervisor relations
        relations = []
        # PM 下属
        for r in ("architect", "ui"):
            if r in by_role:
                relations.append({
                    "member_id": str(by_role[r].id),
                    "supervisor_member_id": str(by_role["pm"].id),
                })
        # 架构师下属
        if "architect" in by_role:
            for r in ("frontend", "backend", "tester", "devops"):
                if r in by_role:
                    relations.append({
                        "member_id": str(by_role[r].id),
                        "supervisor_member_id": str(by_role["architect"].id),
                    })
        count = await svc.bulk_set_supervisor_relations(PROD_TEAM_ID, relations)
        print(f"[seed] {count} supervisor relations created")

        # 6) Verify
        rels = await svc.get_supervisor_relations(PROD_TEAM_ID)
        print(f"[seed] verification: {len(rels)} relations in DB")
        for r in rels:
            sup = await db.get(TeamMember, r.supervisor_member_id)
            sub = await db.get(TeamMember, r.member_id)
            print(f"  · {sub.role_name} → reports to → {sup.role_name}")


if __name__ == "__main__":
    asyncio.run(main())
