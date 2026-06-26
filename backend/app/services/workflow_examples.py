"""工作流案例库：供 LLM 参考 Few-Shot Examples

这些案例会被发送给 LLM 作为工作流生成的参考。

设计原则：
1. 覆盖常见协作模式
2. 每个案例包含：场景描述、需求分析、工作流定义、预期效果
3. LLM 可以参考这些案例的结构生成新的工作流
"""

WORKFLOW_EXAMPLES = [
    {
        "id": "ex_001",
        "name": "代码审查工作流",
        "scenario": "开发人员提交代码后，需要自动进行代码审查",
        "requirement_analysis": {
            "task_type": "质量验证",
            "participants": ["开发人员", "审查员", "主管"],
            "complexity": "medium",
            "need_human": True,
        },
        "workflow_template": {
            "nodes": [
                {
                    "id": "start",
                    "type": "Start",
                    "label": "开始",
                    "position": {"x": 100, "y": 100}
                },
                {
                    "id": "static_check",
                    "type": "Agent",
                    "label": "静态检查",
                    "config": {
                        "agent_role": "code_quality",
                        "tools": ["linter", "type_checker"],
                        "prompt": "运行静态代码分析，检查代码质量问题"
                    },
                    "position": {"x": 100, "y": 200}
                },
                {
                    "id": "review_router",
                    "type": "Router",
                    "label": "审查路由",
                    "config": {
                        "strategy": "round_robin",
                        "candidates": ["reviewer_a", "reviewer_b"],
                        "fallback": "tech_lead"
                    },
                    "position": {"x": 100, "y": 300}
                },
                {
                    "id": "human_review",
                    "type": "HITL",
                    "label": "人工审查",
                    "config": {
                        "action_type": "approve_reject",
                        "timeout": 86400
                    },
                    "position": {"x": 100, "y": 400}
                },
                {
                    "id": "end",
                    "type": "End",
                    "label": "结束",
                    "position": {"x": 100, "y": 500}
                }
            ],
            "edges": [
                {"source": "start", "target": "static_check", "type": "Forward"},
                {"source": "static_check", "target": "review_router", "type": "Forward"},
                {"source": "review_router", "target": "human_review", "type": "Forward"},
                {"source": "human_review", "target": "end", "type": "Forward"},
                {"source": "human_review", "target": "static_check", "type": "Reject"}
            ]
        },
        "expected_outcome": "代码自动检查 → 分配审查员 → 人工审核 → 通过/驳回"
    },
    {
        "id": "ex_002",
        "name": "客户问题处理工作流",
        "scenario": "客户提交问题，需要分类、处理、回复",
        "requirement_analysis": {
            "task_type": "客户服务",
            "participants": ["客服", "技术支持", "主管"],
            "complexity": "low",
            "need_human": False,
        },
        "workflow_template": {
            "nodes": [
                {
                    "id": "start",
                    "type": "Start",
                    "label": "开始",
                    "position": {"x": 100, "y": 100}
                },
                {
                    "id": "classify",
                    "type": "Agent",
                    "label": "问题分类",
                    "config": {
                        "agent_role": "classifier",
                        "prompt": "分析客户问题，分类为：技术问题/产品咨询/投诉/其他"
                    },
                    "position": {"x": 100, "y": 200}
                },
                {
                    "id": "route_by_type",
                    "type": "Condition",
                    "label": "按类型路由",
                    "config": {
                        "expression": "{{classification}}",
                        "branches": {
                            "技术问题": "tech_support",
                            "产品咨询": "sales",
                            "投诉": "manager"
                        }
                    },
                    "position": {"x": 100, "y": 300}
                },
                {
                    "id": "tech_support",
                    "type": "Agent",
                    "label": "技术支持",
                    "config": {"agent_role": "tech_support"},
                    "position": {"x": 50, "y": 400}
                },
                {
                    "id": "sales",
                    "type": "Agent",
                    "label": "销售",
                    "config": {"agent_role": "sales"},
                    "position": {"x": 150, "y": 400}
                },
                {
                    "id": "manager",
                    "type": "Agent",
                    "label": "主管处理",
                    "config": {"agent_role": "manager"},
                    "position": {"x": 250, "y": 400}
                },
                {
                    "id": "end",
                    "type": "End",
                    "label": "结束",
                    "position": {"x": 100, "y": 500}
                }
            ],
            "edges": [
                {"source": "start", "target": "classify", "type": "Forward"},
                {"source": "classify", "target": "route_by_type", "type": "Forward"},
                {"source": "route_by_type", "target": "tech_support", "type": "Forward", "condition": {"type": "技术问题"}},
                {"source": "route_by_type", "target": "sales", "type": "Forward", "condition": {"type": "产品咨询"}},
                {"source": "route_by_type", "target": "manager", "type": "Forward", "condition": {"type": "投诉"}},
                {"source": "tech_support", "target": "end", "type": "Forward"},
                {"source": "sales", "target": "end", "type": "Forward"},
                {"source": "manager", "target": "end", "type": "Forward"}
            ]
        },
        "expected_outcome": "问题分类 → 按类型分配给对应角色 → 处理 → 结束"
    },
    {
        "id": "ex_003",
        "name": "产品功能设计工作流",
        "scenario": "设计一个新功能，需要多角色协作",
        "requirement_analysis": {
            "task_type": "产品设计",
            "participants": ["产品经理", "设计师", "技术负责人"],
            "complexity": "high",
            "need_human": True,
        },
        "workflow_template": {
            "nodes": [
                {"id": "start", "type": "Start", "label": "开始", "position": {"x": 100, "y": 100}},
                {
                    "id": "parallel_analysis",
                    "type": "Parallel",
                    "label": "并行分析",
                    "config": {
                        "branches": [
                            [{"type": "Agent", "label": "需求分析", "config": {"role": "pm"}}],
                            [{"type": "Agent", "label": "技术评估", "config": {"role": "tech_lead"}}],
                            [{"type": "Agent", "label": "UI/UX设计", "config": {"role": "designer"}}]
                        ],
                        "merge_strategy": "all",
                        "timeout": 1800
                    },
                    "position": {"x": 100, "y": 200}
                },
                {
                    "id": "merge_results",
                    "type": "Agent",
                    "label": "合并方案",
                    "config": {
                        "role": "pm",
                        "prompt": "综合需求、技术、设计三方的分析结果，形成完整方案"
                    },
                    "position": {"x": 100, "y": 300}
                },
                {
                    "id": "validate",
                    "type": "Validation",
                    "label": "方案验证",
                    "config": {
                        "validator": "LLM",
                        "criteria": ["完整性", "可行性", "一致性"],
                        "on_fail": "reject"
                    },
                    "position": {"x": 100, "y": 400}
                },
                {
                    "id": "human_approve",
                    "type": "HITL",
                    "label": "人工审批",
                    "config": {"action_type": "approve_modify", "timeout": 86400},
                    "position": {"x": 100, "y": 500}
                },
                {"id": "end", "type": "End", "label": "结束", "position": {"x": 100, "y": 600}}
            ],
            "edges": [
                {"source": "start", "target": "parallel_analysis", "type": "Forward"},
                {"source": "parallel_analysis", "target": "merge_results", "type": "Forward"},
                {"source": "merge_results", "target": "validate", "type": "Forward"},
                {"source": "validate", "target": "human_approve", "type": "Forward"},
                {"source": "validate", "target": "merge_results", "type": "Reject"},
                {"source": "human_approve", "target": "end", "type": "Forward"},
                {"source": "human_approve", "target": "merge_results", "type": "Reject"}
            ]
        },
        "expected_outcome": "三方并行分析 → 合并方案 → 验证 → 人工审批 → 完成"
    },
    {
        "id": "ex_004",
        "name": "数据分析报告工作流",
        "scenario": "定期生成数据分析报告",
        "requirement_analysis": {
            "task_type": "数据分析",
            "participants": ["数据分析师"],
            "complexity": "low",
            "need_human": False,
        },
        "workflow_template": {
            "nodes": [
                {"id": "start", "type": "Start", "label": "开始", "position": {"x": 100, "y": 100}},
                {
                    "id": "fetch_data",
                    "type": "Agent",
                    "label": "获取数据",
                    "config": {
                        "role": "data_analyst",
                        "tools": ["sql_query", "api_fetch"]
                    },
                    "position": {"x": 100, "y": 200}
                },
                {
                    "id": "analyze",
                    "type": "Agent",
                    "label": "分析数据",
                    "config": {
                        "role": "data_analyst",
                        "prompt": "分析数据趋势、异常点、关键指标"
                    },
                    "position": {"x": 100, "y": 300}
                },
                {
                    "id": "generate_report",
                    "type": "Agent",
                    "label": "生成报告",
                    "config": {
                        "role": "data_analyst",
                        "prompt": "生成可读的数据分析报告，包含图表建议"
                    },
                    "position": {"x": 100, "y": 400}
                },
                {
                    "id": "validate_quality",
                    "type": "Validation",
                    "label": "质量检查",
                    "config": {
                        "validator": "Rule",
                        "criteria": ["数据完整性", "结论合理性"]
                    },
                    "position": {"x": 100, "y": 500}
                },
                {"id": "end", "type": "End", "label": "结束", "position": {"x": 100, "y": 600}}
            ],
            "edges": [
                {"source": "start", "target": "fetch_data", "type": "Forward"},
                {"source": "fetch_data", "target": "analyze", "type": "Forward"},
                {"source": "analyze", "target": "generate_report", "type": "Forward"},
                {"source": "generate_report", "target": "validate_quality", "type": "Forward"},
                {"source": "validate_quality", "target": "end", "type": "Forward"},
                {"source": "validate_quality", "target": "analyze", "type": "Reject"}
            ]
        },
        "expected_outcome": "获取数据 → 分析 → 生成报告 → 质量检查 → 完成"
    },
    {
        "id": "ex_005",
        "name": "紧急事件响应工作流",
        "scenario": "系统告警，需要快速定位和修复",
        "requirement_analysis": {
            "task_type": "故障处理",
            "participants": ["SRE", "开发人员", "值班主管"],
            "complexity": "medium",
            "need_human": True,
        },
        "workflow_template": {
            "nodes": [
                {"id": "start", "type": "Start", "label": "告警触发", "position": {"x": 100, "y": 100}},
                {
                    "id": "assess_severity",
                    "type": "Agent",
                    "label": "评估严重程度",
                    "config": {
                        "role": "sre",
                        "prompt": "分析告警信息，评估严重程度：P0/P1/P2"
                    },
                    "position": {"x": 100, "y": 200}
                },
                {
                    "id": "route_by_severity",
                    "type": "Router",
                    "label": "按级别路由",
                    "config": {
                        "strategy": "priority",
                        "routes": {
                            "P0": ["oncall_sre", "tech_lead"],
                            "P1": ["oncall_sre"],
                            "P2": ["normal_dev"]
                        }
                    },
                    "position": {"x": 100, "y": 300}
                },
                {
                    "id": "fix_issue",
                    "type": "Agent",
                    "label": "修复问题",
                    "config": {
                        "role": "developer",
                        "tools": ["log_analysis", "restart_service", "rollback"]
                    },
                    "position": {"x": 100, "y": 400}
                },
                {
                    "id": "verify_fix",
                    "type": "Validation",
                    "label": "验证修复",
                    "config": {
                        "validator": "Agent",
                        "validator_role": "sre",
                        "criteria": ["服务恢复", "指标正常"]
                    },
                    "position": {"x": 100, "y": 500}
                },
                {
                    "id": "timeout_handler",
                    "type": "Agent",
                    "label": "超时处理",
                    "config": {"role": "manager"},
                    "position": {"x": 300, "y": 400}
                },
                {"id": "end", "type": "End", "label": "结束", "position": {"x": 100, "y": 600}}
            ],
            "edges": [
                {"source": "start", "target": "assess_severity", "type": "Forward"},
                {"source": "assess_severity", "target": "route_by_severity", "type": "Forward"},
                {"source": "route_by_severity", "target": "fix_issue", "type": "Forward"},
                {"source": "fix_issue", "target": "verify_fix", "type": "Forward"},
                {"source": "verify_fix", "target": "end", "type": "Forward"},
                {"source": "verify_fix", "target": "fix_issue", "type": "Reject"},
                {"source": "fix_issue", "target": "timeout_handler", "type": "Timeout"}
            ]
        },
        "expected_outcome": "评估告警 → 按级别分配 → 快速修复 → 验证 → 超时升级"
    },
]


# 节点类型参考
NODE_TYPE_REFERENCE = {
    "Start": {
        "description": "工作流入口节点",
        "config": {},
        "examples": ["开始", "启动", "触发"]
    },
    "End": {
        "description": "工作流出口节点",
        "config": {},
        "examples": ["结束", "完成", "终止"]
    },
    "Agent": {
        "description": "执行单个 Agent 处理任务",
        "config": {
            "agent_role": "Agent 的角色名称",
            "tools": ["工具列表"],
            "prompt": "任务提示词",
            "model_config": {"model": "模型选择"}
        },
        "examples": ["代码审查", "数据分析", "文档生成"]
    },
    "Router": {
        "description": "根据策略选择下一个执行节点",
        "config": {
            "strategy": "路由策略：round_robin/priority/semantic/workload",
            "candidates": ["候选 Agent 列表"],
            "fallback": "降级 Agent"
        },
        "examples": ["任务分配", "成员路由", "负载均衡"]
    },
    "Parallel": {
        "description": "并行执行多个分支",
        "config": {
            "branches": [[{"type": "Agent", "config": {...}}]],
            "merge_strategy": "all/first/majority",
            "timeout": "超时时间(秒)"
        },
        "examples": ["并行分析", "多方评审", "并发处理"]
    },
    "Condition": {
        "description": "根据条件判断执行路径",
        "config": {
            "expression": "条件表达式",
            "branches": {"条件值": "目标节点"}
        },
        "examples": ["按类型路由", "条件分支", "状态判断"]
    },
    "HITL": {
        "description": "人工介入节点",
        "config": {
            "action_type": "approve/input/modify",
            "timeout": "超时时间(秒)",
            "escalation_target": "超时后升级的节点"
        },
        "examples": ["人工审批", "用户确认", "专家决策"]
    },
    "Validation": {
        "description": "验证节点输出",
        "config": {
            "validator": "LLM/Agent/Rule",
            "criteria": ["验证标准"],
            "on_fail": "reject/retry/escalate"
        },
        "examples": ["质量检查", "结果验证", "合规审查"]
    }
}


# 边类型参考
EDGE_TYPE_REFERENCE = {
    "Forward": {
        "description": "正常流转到下一个节点"
    },
    "Reject": {
        "description": "验证失败等场景，返回上一个节点或指定节点"
    },
    "Escalate": {
        "description": "无法处理时升级到上级节点"
    },
    "Timeout": {
        "description": "节点执行超时后的流转路径"
    },
    "Fallback": {
        "description": "主流程失败后的降级处理路径"
    }
}


def get_example_by_scenario(scenario: str) -> dict | None:
    """根据场景获取参考案例"""
    for ex in WORKFLOW_EXAMPLES:
        if scenario.lower() in ex["scenario"].lower():
            return ex
    return None


def get_relevant_examples(requirement: str) -> list[dict]:
    """根据需求关键词获取相关案例"""
    keywords = requirement.lower().split()
    relevant = []
    for ex in WORKFLOW_EXAMPLES:
        ex_text = f"{ex['scenario']} {ex['name']} {' '.join(ex.get('tags', []))}".lower()
        if any(kw in ex_text for kw in keywords):
            relevant.append(ex)
    return relevant[:3]  # 返回最相关的3个案例
