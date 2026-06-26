"""SOP State：任务运行时状态数据类"""


class TaskState:
    """SOP 任务运行时状态，负责状态的序列化/反序列化"""

    def __init__(self, task_id: str, sop_id: str, team_id: str):
        self.task_id = task_id
        self.sop_id = sop_id
        self.team_id = team_id
        self.current_node: str = ""
        self.status: str = "running"  # running/paused/completed/failed
        self.input: dict = {}
        self.artifacts: list[dict] = []
        self.messages: list[dict] = []
        self.retry_count: int = 0
        self.hitl_pending: bool = False
        self.hitl_data: dict = {}
        self.hitl_result: str = ""
        self.validations: dict = {"passed": False, "results": []}
        self.errors: list[str] = []
        self.last_confidence: float = 0.0
        self.team_mode: str = ""  # supervisor/swarm/hierarchy
        # 运行时索引（不序列化）
        self._node_index: dict = {}
        self._edge_map: dict = {}

    def to_dict(self) -> dict:
        """序列化为可存储的字典（排除运行时索引）"""
        return {
            "task_id": self.task_id,
            "sop_id": self.sop_id,
            "team_id": self.team_id,
            "current_node": self.current_node,
            "status": self.status,
            "input": self.input,
            "artifacts": self.artifacts,
            "messages": self.messages,
            "retry_count": self.retry_count,
            "hitl_pending": self.hitl_pending,
            "hitl_data": self.hitl_data,
            "hitl_result": self.hitl_result,
            "validations": self.validations,
            "errors": self.errors,
            "last_confidence": self.last_confidence,
            "team_mode": self.team_mode,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaskState":
        """从字典反序列化"""
        state = cls(
            task_id=data.get("task_id", ""),
            sop_id=data.get("sop_id", ""),
            team_id=data.get("team_id", ""),
        )
        state.current_node = data.get("current_node", "")
        state.status = data.get("status", "pending")
        state.input = data.get("input", {})
        state.artifacts = data.get("artifacts", [])
        state.messages = data.get("messages", [])
        state.retry_count = data.get("retry_count", 0)
        state.hitl_pending = data.get("hitl_pending", False)
        state.hitl_data = data.get("hitl_data", {})
        state.hitl_result = data.get("hitl_result", "")
        state.validations = data.get("validations", {"passed": False, "results": []})
        state.errors = data.get("errors", [])
        state.last_confidence = data.get("last_confidence", 0.0)
        state.team_mode = data.get("team_mode", "")
        return state
