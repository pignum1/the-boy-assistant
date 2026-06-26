"""SOP Presets：预置 SOP 工作流模板定义 + 种子数据

v2.0: 7 角色完整产品开发流程
"""

import logging
import uuid

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sop import SOP
from app.services.sop_service import SOPService

logger = logging.getLogger(__name__)

# ── 预置 SOP 模板 ────────────────────────────────────────

DEV_FULL_SOP_YAML = """
name: "完整产品开发流程"
description: "7 角色全流水线：需求 → 设计 → 架构 → 开发 → 测试 → 部署"
version: "2.0"
nodes:
  # ── Phase 1: 需求 ──
  - id: n1
    type: agent_action
    role_slot: pm
    label: "需求分析"
    config: { maxRetries: 2 }
  - id: n2
    type: hitl
    label: "需求评审"
    message: "请确认 PRD 和用户故事"
    config: { require_human: true, timeout: 600 }

  # ── Phase 2: 设计 ──
  - id: n3
    type: agent_action
    role_slot: ui_designer
    label: "原型设计"
    config: { maxRetries: 2 }
  - id: n4
    type: hitl
    label: "设计评审"
    message: "请确认 UI 原型和设计稿"
    config: { require_human: true, timeout: 600 }

  # ── Phase 3: 架构 ──
  - id: n5
    type: agent_action
    role_slot: architect
    label: "架构设计"
    config: { maxRetries: 2 }
  - id: n6
    type: hitl
    label: "技术评审"
    message: "请确认架构方案和数据库设计"
    config: { require_human: true, timeout: 600 }

  # ── Phase 4: 开发（前后端并行） ──
  - id: n7
    type: agent_action
    role_slot: backend_dev
    label: "后端实现"
    config: { maxRetries: 3 }
  - id: n8
    type: agent_action
    role_slot: frontend_dev
    label: "前端实现"
    config: { maxRetries: 3 }
  - id: n9
    type: validation
    label: "代码审查"
    checks: ["lint", "unit_test", "build"]
    pass_threshold: 80

  # ── Phase 5: 测试 ──
  - id: n10
    type: agent_action
    role_slot: tester
    label: "功能测试"
    config: { maxRetries: 2 }
  - id: n11
    type: hitl
    label: "上线审批"
    message: "测试通过，确认上线？"
    config: { require_human: true, timeout: 300 }

  # ── Phase 6: 部署 ──
  - id: n12
    type: agent_action
    role_slot: devops
    label: "部署上线"
    config: { maxRetries: 2 }
  - id: n13
    type: validation
    label: "线上健康检查"
    checks: ["health_check", "smoke_test"]
    pass_threshold: 100

  - id: n_end
    type: end

edges:
  # ── 正向流程 (forward) ──
  - from: n1
    to: n2
  - from: n2
    to: n3
    condition: "hitl_result == 'approve'"
    edgeType: "forward"
    label: "通过"
  - from: n3
    to: n4
  - from: n4
    to: n5
    condition: "hitl_result == 'approve'"
    edgeType: "forward"
    label: "通过"
  - from: n5
    to: n6
  - from: n6
    to: n7
    condition: "hitl_result == 'approve'"
    edgeType: "forward"
    label: "通过"
  - from: n6
    to: n8
    condition: "hitl_result == 'approve'"
    edgeType: "forward"
    label: "通过"
  - from: n7
    to: n9
  - from: n8
    to: n9
  - from: n9
    to: n10
    condition: "validations.passed"
    edgeType: "forward"
    label: "通过"
  - from: n10
    to: n11
  - from: n11
    to: n12
    condition: "hitl_result == 'approve'"
    edgeType: "forward"
    label: "通过"
  - from: n12
    to: n13
  - from: n13
    to: n_end
    condition: "validations.passed"
    edgeType: "forward"
    label: "通过"

  # ── 打回 (reject) ──
  - from: n2
    to: n1
    condition: "hitl_result == 'reject'"
    edgeType: "reject"
    label: "打回"
  - from: n4
    to: n3
    condition: "hitl_result == 'reject'"
    edgeType: "reject"
    label: "打回"
  - from: n6
    to: n5
    condition: "hitl_result == 'reject'"
    edgeType: "reject"
    label: "打回"
  - from: n9
    to: n7
    condition: "not validations.passed"
    edgeType: "reject"
    label: "后端失败"
  - from: n9
    to: n8
    condition: "not validations.passed"
    edgeType: "reject"
    label: "前端失败"
  - from: n13
    to: n12
    condition: "not validations.passed"
    edgeType: "reject"
    label: "回滚"

  # ── 升级 (escalate) ──
  # 所有升级统一回到需求分析(n1)重启流程
  - from: n4
    to: n1
    condition: "escalate"
    edgeType: "escalate"
    label: "升级到产品"
  - from: n6
    to: n1
    condition: "escalate"
    edgeType: "escalate"
    label: "需求不满足"
  - from: n9
    to: n1
    condition: "escalate"
    edgeType: "escalate"
    label: "需求不满足"
  - from: n10
    to: n1
    condition: "escalate"
    edgeType: "escalate"
    label: "严重缺陷升级"
"""

DEV_HOTFIX_SOP_YAML = """
name: "热修复流程"
description: "快速修复 → 验证 → 部署（4 角色：后端 + 测试 + 运维 + 人工审批）"
version: "2.0"
nodes:
  - id: hf1
    type: agent_action
    role_slot: backend_dev
    label: "修复实现"
    config: { maxRetries: 2 }
  - id: hf2
    type: validation
    label: "代码检查"
    checks: ["lint", "unit_test"]
    pass_threshold: 60
  - id: hf3
    type: agent_action
    role_slot: tester
    label: "回归测试"
    config: { maxRetries: 1 }
  - id: hf4
    type: hitl
    label: "上线确认"
    message: "热修复已通过测试，确认紧急上线？"
    config: { require_human: true, timeout: 120 }
  - id: hf5
    type: agent_action
    role_slot: devops
    label: "紧急部署"
    config: { maxRetries: 2 }
  - id: hf6
    type: validation
    label: "线上验证"
    checks: ["health_check", "smoke_test"]
    pass_threshold: 100
  - id: hf_end
    type: end

edges:
  - from: hf1
    to: hf2
  - from: hf2
    to: hf3
    condition: "validations.passed"
    edgeType: "forward"
    label: "通过"
  - from: hf3
    to: hf4
  - from: hf4
    to: hf5
    condition: "hitl_result == 'approve'"
    edgeType: "forward"
    label: "通过"
  - from: hf5
    to: hf6
  - from: hf6
    to: hf_end
    condition: "validations.passed"
    edgeType: "forward"
    label: "通过"
  # 打回
  - from: hf2
    to: hf1
    condition: "not validations.passed"
    edgeType: "reject"
    label: "失败"
  - from: hf6
    to: hf5
    condition: "not validations.passed"
    edgeType: "reject"
    label: "回滚"
"""

DEV_DESIGN_SOP_YAML = """
name: "产品设计流程"
description: "产品经理 + UI 设计师协作：需求 → 原型 → 评审"
version: "2.0"
nodes:
  - id: d1
    type: agent_action
    role_slot: pm
    label: "需求分析"
    config: { maxRetries: 2 }
  - id: d2
    type: agent_action
    role_slot: ui_designer
    label: "原型设计"
    config: { maxRetries: 2 }
  - id: d3
    type: hitl
    label: "设计评审"
    message: "请确认原型和设计稿"
    config: { require_human: true, timeout: 600 }
  - id: d4
    type: agent_action
    role_slot: architect
    label: "技术可行性评估"
    config: { maxRetries: 1 }
  - id: d5
    type: hitl
    label: "最终确认"
    message: "产品方案确认？"
    config: { require_human: true, timeout: 300 }
  - id: d_end
    type: end

edges:
  - from: d1
    to: d2
  - from: d2
    to: d3
  - from: d3
    to: d4
    condition: "hitl_result == 'approve'"
    edgeType: "forward"
    label: "通过"
  - from: d4
    to: d5
  - from: d5
    to: d_end
    condition: "hitl_result == 'approve'"
    edgeType: "forward"
    label: "通过"
  # 打回
  - from: d3
    to: d2
    condition: "hitl_result == 'reject'"
    edgeType: "reject"
    label: "打回"
  - from: d5
    to: d1
    condition: "hitl_result == 'reject'"
    edgeType: "reject"
    label: "打回"
  # 升级
  - from: d4
    to: d2
    condition: "escalate"
    edgeType: "escalate"
    label: "技术不可行"
"""


async def seed_preset_sops(db: AsyncSession, team_id: uuid.UUID) -> None:
    """将预置 SOP 模板种子到数据库"""
    svc = SOPService(db)

    for yaml_str in [DEV_FULL_SOP_YAML]:
        data = yaml.safe_load(yaml_str)
        name = data.get("name", "")

        existing = await db.execute(select(SOP).where(SOP.name == name))
        if existing.scalar_one_or_none() is None:
            await svc.import_from_yaml(team_id, yaml_str)
            logger.info(f"Preset SOP seeded: {name}")
