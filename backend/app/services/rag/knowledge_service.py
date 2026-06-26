"""知识库服务：文档上传、分块、Embedding 存储、检索编排"""

import json
import logging
import uuid
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_base import KnowledgeBase
from app.models.knowledge_chunk import KnowledgeChunk
from app.services.rag.chunker import semantic_chunk
from app.services.rag.embedder import Embedder
from app.services.rag.hybrid_search import HybridSearcher
from app.services.rag.reranker import Reranker

logger = logging.getLogger(__name__)


class KnowledgeService:
    """知识库管理服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.embedder = Embedder()
        self.searcher = HybridSearcher(db, self.embedder)
        self.reranker = Reranker()

    async def upload_document(
        self,
        content: str,
        file_name: str,
        kb_type: str = "global",
        team_id: Optional[uuid.UUID] = None,
        agent_id: Optional[uuid.UUID] = None,
        skill_id: Optional[uuid.UUID] = None,
    ) -> KnowledgeBase:
        """上传文档：分块 → Embedding → 存储"""
        # 1. Create knowledge base
        kb = KnowledgeBase(
            name=file_name,
            type=kb_type,
            team_id=team_id,
            agent_id=agent_id,
            skill_id=skill_id,
            file_name=file_name,
            chunk_count=0,
        )
        self.db.add(kb)
        await self.db.flush()

        # 2. Chunk
        chunks = await semantic_chunk(content, max_tokens=512, overlap=64, file_name=file_name)
        logger.info(f"Document '{file_name}' split into {len(chunks)} chunks")

        # 3. Embed all chunks in batches
        texts = [c["content"] for c in chunks]
        batch_size = 20
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            embeddings = await self.embedder.embed_texts(batch)
            all_embeddings.extend(embeddings)

        # 4. Store chunks with embeddings using f-string SQL (asyncpg compatible)
        for i, chunk_data in enumerate(chunks):
            chunk_id = uuid.uuid4()
            meta_escaped = json.dumps(chunk_data["metadata"]).replace("'", "''")
            content_escaped = chunk_data["content"].replace("'", "''")

            if i < len(all_embeddings) and all_embeddings[i]:
                emb_str = "[" + ",".join(str(v) for v in all_embeddings[i]) + "]"
                sql = text(
                    f"INSERT INTO knowledge_chunks "
                    f"(id, knowledge_base_id, content, chunk_index, metadata, embedding, created_at) "
                    f"VALUES ('{chunk_id}', '{kb.id}', '{content_escaped}', {chunk_data['chunk_index']}, "
                    f"'{meta_escaped}'::jsonb, '{emb_str}'::vector, now())"
                )
            else:
                sql = text(
                    f"INSERT INTO knowledge_chunks "
                    f"(id, knowledge_base_id, content, chunk_index, metadata, created_at) "
                    f"VALUES ('{chunk_id}', '{kb.id}', '{content_escaped}', {chunk_data['chunk_index']}, "
                    f"'{meta_escaped}'::jsonb, now())"
                )
            await self.db.execute(sql)

        kb.chunk_count = len(chunks)
        await self.db.commit()
        await self.db.refresh(kb)

        logger.info(f"Uploaded '{file_name}': {len(chunks)} chunks, kb_id={kb.id}")
        return kb

    async def search(
        self,
        query: str,
        top_k: int = 10,
        method: str = "hybrid",
        rerank: bool = False,
        agent_id: Optional[uuid.UUID] = None,
        team_id: Optional[uuid.UUID] = None,
    ) -> list[dict]:
        """检索知识库"""
        if agent_id or team_id:
            # Priority search with hierarchy
            results = await self.searcher.search_with_priority(
                query=query, agent_id=agent_id, team_id=team_id, top_k=top_k * 2
            )
        elif method == "hybrid":
            results = await self.searcher.hybrid_search(query, top_k=top_k * 2)
        elif method == "dense":
            results = await self.searcher.search_dense(query, top_k=top_k * 2)
        else:
            results = await self.searcher.search_sparse(query, top_k=top_k * 2)

        # Rerank if requested
        if rerank and results:
            results = await self.reranker.rerank(query, results, top_k=top_k)

        return results[:top_k]

    async def list_knowledge_bases(
        self,
        kb_type: Optional[str] = None,
        team_id: Optional[uuid.UUID] = None,
        agent_id: Optional[uuid.UUID] = None,
    ) -> list[KnowledgeBase]:
        """列出知识库"""
        conditions = []
        if kb_type:
            conditions.append(KnowledgeBase.type == kb_type)
        if team_id:
            conditions.append(KnowledgeBase.team_id == team_id)
        if agent_id:
            conditions.append(KnowledgeBase.agent_id == agent_id)

        stmt = select(KnowledgeBase)
        if conditions:
            stmt = stmt.where(*conditions)
        stmt = stmt.order_by(KnowledgeBase.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def delete_knowledge_base(self, kb_id: uuid.UUID) -> bool:
        """删除知识库及其所有 chunks"""
        kb = await self.db.get(KnowledgeBase, kb_id)
        if not kb:
            return False
        await self.db.delete(kb)
        await self.db.commit()
        logger.info(f"Deleted knowledge base {kb_id}")
        return True
