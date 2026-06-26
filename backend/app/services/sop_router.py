"""SOP Router：工作流边映射 + 条件路由决策"""

from typing import Optional

from app.services.condition_router import ConditionRouter
from app.services.sop_state import TaskState


class SOPRouter:
    """工作流路由器：根据边条件和状态决定下一跳节点"""

    def __init__(self):
        self.condition_router = ConditionRouter()

    @staticmethod
    def build_edge_map(edges: list[dict]) -> dict:
        """构建 from_node -> [{to, condition}] 的邻接表"""
        edge_map: dict[str, list[dict]] = {}
        for edge in edges:
            from_node = edge.get("from", "")
            edge_map.setdefault(from_node, []).append(edge)
        return edge_map

    def route_next(
        self, state: TaskState, current: str, edge_map: dict
    ) -> Optional[str]:
        """根据当前节点和条件，决定下一跳

        优先匹配条件边，无条件边作为 fallback。
        支持 "not X" 反转条件和裸字段真值检查。
        """
        edges = edge_map.get(current, [])
        if not edges:
            return None

        unconditional = [e for e in edges if "condition" not in e]
        conditional = [e for e in edges if "condition" in e]

        if not conditional:
            return unconditional[0]["to"] if unconditional else None

        # 构建条件评估上下文
        ctx = {
            "hitl_result": state.hitl_result,
            "validations": state.validations,
            "retry_count": state.retry_count,
            "last_confidence": state.last_confidence,
            **state.input,
        }

        for edge in conditional:
            condition = edge["condition"]

            # "not X" 反转条件
            if condition.startswith("not "):
                field = condition[4:].strip()
                val = self.resolve_state_field(field, state)
                if not val:
                    return edge["to"]
            else:
                # 标准条件评估
                if self.condition_router.evaluate(condition, ctx):
                    return edge["to"]
                # 裸字段真值检查（无运算符时）
                val = self.resolve_state_field(condition, state)
                if val:
                    return edge["to"]

        # Fallback 到无条件边
        return unconditional[0]["to"] if unconditional else None

    @staticmethod
    def resolve_state_field(field: str, state: TaskState):
        """从 TaskState 解析字段路径（如 validations.passed）"""
        mapping = {
            "hitl_result": state.hitl_result,
            "retry_count": state.retry_count,
            "last_confidence": state.last_confidence,
            "validations.passed": state.validations.get("passed", False),
        }
        return mapping.get(field)
