"""Reranker：对检索结果进行精排"""

import logging
from typing import Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class Reranker:
    """Cross-Encoder Reranker

    使用 SiliconFlow / Jina / Cohere 兼容的 Rerank API。
    若服务不可用，优雅降级返回原始排序。
    """

    def __init__(self):
        settings = get_settings()
        self.api_url = getattr(settings, "RERANKER_URL", "")
        self.api_key = getattr(settings, "RERANKER_API_KEY", "")
        self.model = getattr(settings, "RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")

    async def rerank(
        self,
        query: str,
        candidates: list[dict],
        top_k: int = 5,
    ) -> list[dict]:
        """对候选结果重排序

        Args:
            query: 查询文本
            candidates: 检索结果列表，每个包含 "content" 字段
            top_k: 返回 top_k 结果

        Returns:
            重排序后的列表（包含 rerank_score）
        """
        if not candidates:
            return []

        # Try external reranker API
        if self.api_url:
            try:
                return await self._call_reranker_api(query, candidates, top_k)
            except Exception as e:
                logger.warning(f"Reranker API failed: {e}, using fallback")

        # Fallback: simple keyword overlap scoring
        return self._fallback_rerank(query, candidates, top_k)

    async def _call_reranker_api(
        self, query: str, candidates: list[dict], top_k: int
    ) -> list[dict]:
        """调用 Reranker HTTP API"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        documents = [c["content"] for c in candidates]
        payload = {
            "model": self.model,
            "query": query,
            "documents": documents,
            "top_k": top_k,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self.api_url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("results", []):
            idx = item["index"]
            score = item["relevance_score"]
            candidate = {**candidates[idx]}
            candidate["rerank_score"] = score
            candidate["source"] = "reranked"
            results.append(candidate)

        results.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        logger.info(f"Reranked {len(candidates)} → {len(results)} results via API")
        return results[:top_k]

    @staticmethod
    def _fallback_rerank(
        query: str, candidates: list[dict], top_k: int
    ) -> list[dict]:
        """Fallback: 基于关键词重叠的简单重排序"""
        query_words = set(query.lower().split())
        scored = []
        for c in candidates:
            content_words = set(c["content"].lower().split())
            overlap = len(query_words & content_words)
            total = len(query_words) or 1
            c["rerank_score"] = overlap / total
            scored.append(c)

        scored.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        logger.info(f"Fallback rerank: {len(scored)} candidates → top {top_k}")
        return scored[:top_k]
