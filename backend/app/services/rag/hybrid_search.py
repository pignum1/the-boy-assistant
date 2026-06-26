"""混合检索：Dense 向量检索 + Sparse 关键词检索，RRF 融合"""

import asyncio
import logging
import uuid
from typing import Optional

from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_base import KnowledgeBase
from app.services.rag.embedder import Embedder

logger = logging.getLogger(__name__)


async def _get_raw_conn(db: AsyncSession):
    """获取 asyncpg 原生连接"""
    raw = await db.connection()
    pg = raw.get_raw_connection()
    if hasattr(pg, '_connection'):
        pg = pg._connection
    return pg


class HybridSearcher:
    """Dense + Sparse 混合检索器"""

    def __init__(self, db: AsyncSession, embedder: Optional[Embedder] = None):
        self.db = db
        self.embedder = embedder or Embedder()

    async def search_dense(
        self,
        query: str,
        top_k: int = 10,
        kb_ids: Optional[list[uuid.UUID]] = None,
    ) -> list[dict]:
        """向量相似度检索"""
        query_embedding = await self.embedder.embed_query(query)
        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        if kb_ids:
            kb_list = ",".join(f"'{kid}'" for kid in kb_ids)
            sql = text(f"""
                SELECT kc.id, kc.content, kc.metadata, kc.knowledge_base_id,
                       1 - (kc.embedding <=> '{embedding_str}'::vector) AS score
                FROM knowledge_chunks kc
                WHERE kc.knowledge_base_id IN ({kb_list})
                ORDER BY kc.embedding <=> '{embedding_str}'::vector
                LIMIT :limit
            """)
        else:
            sql = text(f"""
                SELECT kc.id, kc.content, kc.metadata, kc.knowledge_base_id,
                       1 - (kc.embedding <=> '{embedding_str}'::vector) AS score
                FROM knowledge_chunks kc
                ORDER BY kc.embedding <=> '{embedding_str}'::vector
                LIMIT :limit
            """)

        result = await self.db.execute(sql, {"limit": top_k})
        rows = result.fetchall()

        logger.info(f"Dense search: query='{query[:50]}' returned {len(rows)} results")
        return [
            {
                "id": str(r[0]),
                "content": r[1],
                "metadata": r[2],
                "knowledge_base_id": str(r[3]),
                "score": float(r[4]),
                "source": "dense",
            }
            for r in rows
        ]

    async def search_sparse(
        self,
        query: str,
        top_k: int = 10,
        kb_ids: Optional[list[uuid.UUID]] = None,
    ) -> list[dict]:
        """全文检索 (tsvector + ts_rank)"""
        if kb_ids:
            kb_list = [str(kid) for kid in kb_ids]
            sql = text("""
                SELECT kc.id, kc.content, kc.metadata, kc.knowledge_base_id,
                       ts_rank(kc.tsv, plainto_tsquery('simple', :query)) AS score
                FROM knowledge_chunks kc
                WHERE kc.tsv @@ plainto_tsquery('simple', :query)
                AND kc.knowledge_base_id = ANY(CAST(:kb_ids AS uuid[]))
                ORDER BY score DESC LIMIT :limit
            """)
            result = await self.db.execute(sql, {"query": query, "kb_ids": kb_list, "limit": top_k})
        else:
            sql = text("""
                SELECT kc.id, kc.content, kc.metadata, kc.knowledge_base_id,
                       ts_rank(kc.tsv, plainto_tsquery('simple', :query)) AS score
                FROM knowledge_chunks kc
                WHERE kc.tsv @@ plainto_tsquery('simple', :query)
                ORDER BY score DESC LIMIT :limit
            """)
            result = await self.db.execute(sql, {"query": query, "limit": top_k})

        rows = result.fetchall()
        logger.info(f"Sparse search: query='{query[:50]}' returned {len(rows)} results")
        return [
            {
                "id": str(r[0]),
                "content": r[1],
                "metadata": r[2],
                "knowledge_base_id": str(r[3]),
                "score": float(r[4]),
                "source": "sparse",
            }
            for r in rows
        ]

    async def hybrid_search(
        self,
        query: str,
        top_k: int = 10,
        kb_ids: Optional[list[uuid.UUID]] = None,
        fusion_method: str = "RRF",
        k: int = 60,
    ) -> list[dict]:
        """混合检索：Dense + Sparse 并行，RRF 融合"""
        dense_results, sparse_results = await asyncio.gather(
            self.search_dense(query, top_k=top_k * 2, kb_ids=kb_ids),
            self.search_sparse(query, top_k=top_k * 2, kb_ids=kb_ids),
        )

        if fusion_method == "RRF":
            fused = self._rrf_fusion(dense_results, sparse_results, k=k)
        else:
            fused = self._simple_merge(dense_results, sparse_results)

        result = fused[:top_k]
        logger.info(f"Hybrid search: {len(dense_results)} dense + {len(sparse_results)} sparse → {len(result)} fused")
        return result

    async def search_with_priority(
        self,
        query: str,
        agent_id: Optional[uuid.UUID] = None,
        team_id: Optional[uuid.UUID] = None,
        top_k: int = 10,
    ) -> list[dict]:
        """层级检索：Agent 专属 > 团队公共 > 全局"""
        async def _get_kb_ids(kb_type: str, **filters) -> list[uuid.UUID]:
            conditions = [KnowledgeBase.type == kb_type]
            for key, val in filters.items():
                if val is not None:
                    conditions.append(getattr(KnowledgeBase, key) == val)
            stmt = select(KnowledgeBase.id).where(*conditions)
            result = await self.db.execute(stmt)
            return [row[0] for row in result.fetchall()]

        agent_kbs = await _get_kb_ids("agent", agent_id=agent_id) if agent_id else []
        team_kbs = await _get_kb_ids("team", team_id=team_id) if team_id else []
        global_kbs = await _get_kb_ids("global")

        all_results = []

        for layer_name, kb_ids_layer, max_results in [
            ("agent", agent_kbs, top_k),
            ("team", team_kbs, max(0, top_k - len(all_results))),
            ("global", global_kbs, max(0, top_k - len(all_results))),
        ]:
            if not kb_ids_layer or max_results <= 0:
                continue
            results = await self.hybrid_search(query, top_k=max_results, kb_ids=kb_ids_layer)
            for r in results:
                r["source_level"] = layer_name
            all_results.extend(results)

        logger.info(
            f"Priority search: agent_kbs={len(agent_kbs)} team_kbs={len(team_kbs)} "
            f"global_kbs={len(global_kbs)} → {len(all_results)} results"
        )
        return all_results[:top_k]

    @staticmethod
    def _rrf_fusion(dense: list[dict], sparse: list[dict], k: int = 60) -> list[dict]:
        """Reciprocal Rank Fusion"""
        scores: dict[str, dict] = {}
        for rank, item in enumerate(dense):
            doc_id = item["id"]
            scores[doc_id] = {**item, "rrf_score": 1.0 / (k + rank + 1)}
        for rank, item in enumerate(sparse):
            doc_id = item["id"]
            if doc_id in scores:
                scores[doc_id]["rrf_score"] += 1.0 / (k + rank + 1)
                scores[doc_id]["source"] = "hybrid"
            else:
                scores[doc_id] = {**item, "rrf_score": 1.0 / (k + rank + 1)}
        return sorted(scores.values(), key=lambda x: x["rrf_score"], reverse=True)

    @staticmethod
    def _simple_merge(dense: list[dict], sparse: list[dict]) -> list[dict]:
        seen = {}
        for item in dense + sparse:
            doc_id = item["id"]
            if doc_id not in seen:
                seen[doc_id] = {**item, "merge_score": item["score"]}
            else:
                seen[doc_id]["merge_score"] += item["score"]
                seen[doc_id]["source"] = "hybrid"
        return sorted(seen.values(), key=lambda x: x["merge_score"], reverse=True)
