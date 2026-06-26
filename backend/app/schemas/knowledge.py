from typing import Optional
from pydantic import BaseModel


class KnowledgeSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    method: str = "hybrid"
    rerank: bool = False
    agent_id: Optional[str] = None
    team_id: Optional[str] = None
