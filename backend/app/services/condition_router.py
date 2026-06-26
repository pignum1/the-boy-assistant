"""Condition Router：条件表达式评估 + 分支路由"""

import logging
import re
import operator
from typing import Any, Optional

# 向后兼容：LoopController 已移至 loop_controller.py
from app.services.loop_controller import LoopController

logger = logging.getLogger(__name__)

# 支持的比较运算符
OPERATORS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
    "contains": lambda a, b: b in str(a),
    "not_contains": lambda a, b: b not in str(a),
    "is_empty": lambda a, _: not a,
    "is_not_empty": lambda a, _: bool(a),
    "matches": lambda a, b: bool(re.search(b, str(a))),
}


class ConditionRouter:
    """条件路由器：根据上下文变量进行条件分支判断"""

    def evaluate(self, expression: str, context: dict) -> bool:
        """评估单个条件表达式

        表达式格式:
        - "variable == value"
        - "variable > 5"
        - "variable contains 'keyword'"
        - "variable is_empty"
        - "variable matches 'regex_pattern'"

        Args:
            expression: 条件表达式字符串
            context: 上下文变量字典

        Returns:
            评估结果 (True/False)
        """
        expr = expression.strip()

        # 处理 is_empty / is_not_empty（单操作数）
        for op_name in ["is_not_empty", "is_empty"]:
            if expr.endswith(f" {op_name}"):
                var_name = expr[: -(len(op_name) + 1)].strip()
                value = self._resolve_variable(var_name, context)
                return OPERATORS[op_name](value, None)

        # 处理双操作数表达式
        # 按运算符长度降序匹配，避免部分匹配
        sorted_ops = sorted(
            [op for op in OPERATORS if op not in ("is_empty", "is_not_empty")],
            key=len,
            reverse=True,
        )

        for op_name in sorted_ops:
            if f" {op_name} " in expr:
                parts = expr.split(f" {op_name} ", 1)
                left = self._resolve_variable(parts[0].strip(), context)
                right = self._parse_value(parts[1].strip())
                try:
                    result = OPERATORS[op_name](left, right)
                    logger.debug(f"Condition: {expr} -> {result} (left={left}, right={right})")
                    return result
                except (TypeError, ValueError) as e:
                    logger.warning(f"Condition eval failed: {expr} -> {e}")
                    return False

        # 无法解析的表达式
        logger.warning(f"Cannot parse condition: {expr}")
        return False

    def evaluate_all(self, conditions: list[str], context: dict, logic: str = "and") -> bool:
        """评估多个条件

        Args:
            conditions: 条件列表
            context: 上下文变量
            logic: "and" 或 "or"
        """
        if not conditions:
            return True

        results = [self.evaluate(c, context) for c in conditions]

        if logic == "or":
            return any(results)
        return all(results)

    def route(
        self,
        branches: list[dict],
        context: dict,
        default: Optional[str] = None,
    ) -> Optional[str]:
        """根据条件分支路由到目标

        Args:
            branches: [{"condition": "var == value", "target": "step_name"}, ...]
            context: 上下文变量
            default: 默认目标

        Returns:
            匹配的 target，或 default
        """
        for branch in branches:
            condition = branch.get("condition", "")
            target = branch.get("target", "")

            if not condition or self.evaluate(condition, context):
                logger.info(f"ConditionRouter: matched -> {target}")
                return target

        return default

    def _resolve_variable(self, name: str, context: dict) -> Any:
        """解析变量值，支持嵌套路径 (e.g., 'response.status')"""
        if not name:
            return None

        # 移除引号
        clean = name.strip("'\"")

        # 尝试直接取值
        if clean in context:
            return context[clean]

        # 尝试嵌套路径
        parts = clean.split(".")
        value = context
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None
            if value is None:
                return None

        return value

    def _parse_value(self, value_str: str) -> Any:
        """解析值字面量"""
        s = value_str.strip()

        # 字符串（引号包裹）
        if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
            return s[1:-1]

        # 布尔
        if s.lower() == "true":
            return True
        if s.lower() == "false":
            return False

        # None
        if s.lower() in ("none", "null"):
            return None

        # 数字
        try:
            if "." in s:
                return float(s)
            return int(s)
        except ValueError:
            pass

        # 列表 (逗号分隔)
        if "," in s:
            return [item.strip().strip("'\"") for item in s.split(",")]

        return s
