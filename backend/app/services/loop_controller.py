"""Loop Controller：循环退避控制，防止工作流无限循环"""


class LoopController:
    """循环控制：防止无限循环，带指数退避策略"""

    def __init__(self, max_iterations: int = 5, backoff_base: float = 1.0):
        self.max_iterations = max_iterations
        self.backoff_base = backoff_base
        self._iteration_counts: dict[str, int] = {}

    def can_continue(self, loop_id: str) -> bool:
        """检查是否可以继续循环"""
        count = self._iteration_counts.get(loop_id, 0)
        return count < self.max_iterations

    def increment(self, loop_id: str) -> int:
        """增加循环计数"""
        self._iteration_counts[loop_id] = self._iteration_counts.get(loop_id, 0) + 1
        return self._iteration_counts[loop_id]

    def get_backoff_seconds(self, loop_id: str) -> float:
        """获取退避等待时间（指数退避）"""
        count = self._iteration_counts.get(loop_id, 0)
        return self.backoff_base * (2 ** (count - 1))

    def reset(self, loop_id: str) -> None:
        """重置循环计数"""
        self._iteration_counts.pop(loop_id, None)

    def get_status(self, loop_id: str) -> dict:
        """获取循环状态"""
        count = self._iteration_counts.get(loop_id, 0)
        return {
            "loop_id": loop_id,
            "iterations": count,
            "max_iterations": self.max_iterations,
            "can_continue": count < self.max_iterations,
        }
