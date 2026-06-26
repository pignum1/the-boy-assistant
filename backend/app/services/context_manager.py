import json
import logging
import uuid
import asyncio
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.services.memory_manager import MemoryManager

logger = logging.getLogger(__name__)

# Token 预算分配比例
BUDGET_RATIOS = {
    "system": 0.10,
    "task": 0.10,
    "memory": 0.40,
    "rag": 0.30,
    "output": 0.10,
}


def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数"""
    if not text:
        return 0
    cn_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    en_chars = len(text) - cn_chars
    return int(cn_chars * 2.5 + en_chars * 0.33)


class ContextManager:
    """上下文管理器：自动注入 Memory + RAG + Token 预算裁剪"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.memory_manager = MemoryManager(db)

    async def build_prompt_context(
        self,
        agent: Agent,
        system_prompt: str,
        user_message: str,
        history: Optional[list[dict]] = None,
        team_id: Optional[str] = None,
        max_tokens: int = 8000,
    ) -> tuple[list[dict], dict]:
        """构建完整的 Prompt 上下文：Memory + RAG 联合注入

        Returns:
            (messages, stats) - 组装后的消息列表 + 统计信息
        """
        budgets = {k: int(max_tokens * v) for k, v in BUDGET_RATIOS.items()}

        agent_uuid = agent.id if isinstance(agent.id, uuid.UUID) else uuid.UUID(str(agent.id))
        team_uuid = uuid.UUID(team_id) if team_id else None

        # Parallel load Memory + RAG
        (memory_parts, memory_stats), (rag_parts, rag_stats) = await asyncio.gather(
            self._load_memories(agent_uuid, team_uuid, budgets["memory"]),
            self._load_rag(user_message, agent_uuid, team_uuid, budgets["rag"]),
        )

        # Build system prompt with injected context
        full_system = system_prompt

        if memory_parts:
            full_system += "\n## 相关记忆\n" + "".join(memory_parts)
            full_system += "\n\n请参考以上记忆来回答用户的问题。"

        if rag_parts:
            full_system += "\n## 知识库检索结果\n" + "".join(rag_parts)
            full_system += "\n\n请参考以上知识库内容来辅助回答。"

        messages = [{"role": "system", "content": full_system}]

        # History
        if history:
            for msg in history:
                messages.append(msg)

        # User message
        messages.append({"role": "user", "content": user_message})

        stats = {
            "memory": memory_stats,
            "rag": rag_stats,
            "system_tokens": _estimate_tokens(full_system),
            "budgets": budgets,
        }

        logger.info(
            f"Context built: Memory(L1={memory_stats['L1']} L2={memory_stats['L2']} "
            f"L3={memory_stats['L3']} L4={memory_stats['L4']} tokens={memory_stats['total_tokens']}) "
            f"RAG(chunks={rag_stats['chunks']} tokens={rag_stats['total_tokens']})"
        )

        return messages, stats

    async def _load_memories(
        self, agent_uuid: uuid.UUID, team_uuid: Optional[uuid.UUID], budget: int
    ) -> tuple[list[str], dict]:
        """加载四层记忆，按预算裁剪"""
        memory_view = await self.memory_manager.get_agent_view(agent_uuid, team_uuid)

        memory_parts = []
        stats = {"L1": 0, "L2": 0, "L3": 0, "L4": 0, "total_tokens": 0}

        layer_map = [
            ("L1", memory_view["L1_system"], "【系统级记忆】"),
            ("L2", memory_view["L2_team"], "【团队级记忆】"),
            ("L3", memory_view["L3_agent_global"], "【Agent 全局记忆】"),
            ("L4", memory_view["L4_context"], "【上下文记忆】"),
        ]

        for layer_key, memories, label in layer_map:
            if not memories:
                continue
            remaining = budget - stats["total_tokens"]
            if remaining <= 0:
                break

            section = f"\n{label}\n"
            for m in memories:
                entry = f"- [{m.type}] {m.content}\n"
                entry_tokens = _estimate_tokens(entry)
                if stats["total_tokens"] + entry_tokens > budget:
                    break
                section += entry
                stats[layer_key] += 1
                stats["total_tokens"] += entry_tokens

            if stats[layer_key] > 0:
                memory_parts.append(section)

        return memory_parts, stats

    async def _load_rag(
        self,
        query: str,
        agent_uuid: uuid.UUID,
        team_uuid: Optional[uuid.UUID],
        budget: int,
    ) -> tuple[list[str], dict]:
        """从知识库检索相关内容"""
        stats = {"chunks": 0, "total_tokens": 0, "query": query}

        try:
            from app.services.rag.knowledge_service import KnowledgeService
            svc = KnowledgeService(self.db)
            results = await svc.search(
                query=query, top_k=5, method="hybrid",
                agent_id=agent_uuid, team_id=team_uuid,
            )
        except Exception as e:
            logger.warning(f"RAG search failed: {e}")
            return [], stats

        if not results:
            return [], stats

        rag_parts = []
        for r in results:
            content = r.get("content", "")
            source = r.get("source_level", r.get("source", "unknown"))
            entry = f"- [知识库/{source}] {content[:300]}\n"
            entry_tokens = _estimate_tokens(entry)
            if stats["total_tokens"] + entry_tokens > budget:
                break
            rag_parts.append(entry)
            stats["chunks"] += 1
            stats["total_tokens"] += entry_tokens

        return rag_parts, stats
