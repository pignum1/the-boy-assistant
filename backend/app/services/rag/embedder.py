"""Embedding 生成器：调用 DeepSeek / OpenAI 兼容的 Embedding API"""

import logging
from typing import Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# bge-m3 on SiliconFlow (free) or DeepSeek-compatible endpoints
DEFAULT_EMBEDDING_CONFIG = {
    "siliconflow": {
        "api_base": "https://api.siliconflow.cn/v1",
        "model": "BAAI/bge-m3",
        "dimensions": 1024,
    },
    "deepseek": {
        "api_base": "https://api.deepseek.com",
        "model": "deepseek-chat",  # DeepSeek doesn't have embedding, fallback
        "dimensions": 1024,
    },
}


class Embedder:
    """调用 Embedding API 生成向量"""

    def __init__(self, provider: str = "siliconflow", api_key: Optional[str] = None):
        settings = get_settings()
        config = DEFAULT_EMBEDDING_CONFIG.get(provider, DEFAULT_EMBEDDING_CONFIG["siliconflow"])
        self.api_base = config["api_base"]
        self.model = config["model"]
        self.dimensions = config["dimensions"]
        self.api_key = api_key or getattr(settings, "SILICONFLOW_API_KEY", "") or ""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量文本 embedding"""
        if not texts:
            return []

        # Try SiliconFlow / OpenAI-compatible embedding endpoint
        try:
            return await self._call_embedding_api(texts)
        except Exception as e:
            logger.warning(f"Embedding API failed: {e}, falling back to local hash")
            return [self._fallback_embedding(t) for t in texts]

    async def embed_query(self, query: str) -> list[float]:
        """单条 query embedding"""
        results = await self.embed_texts([query])
        return results[0] if results else self._fallback_embedding(query)

    async def _call_embedding_api(self, texts: list[str]) -> list[list[float]]:
        """调用 OpenAI 兼容的 Embedding API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": texts,
            "encoding_format": "float",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.api_base}/embeddings",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        embeddings = []
        for item in sorted(data["data"], key=lambda x: x["index"]):
            embeddings.append(item["embedding"])

        logger.info(f"Embedded {len(texts)} texts via {self.model}, dim={len(embeddings[0])}")
        return embeddings

    @staticmethod
    def _fallback_embedding(text: str, dim: int = 1024) -> list[float]:
        """Fallback: simple hash-based pseudo-embedding for when API is unavailable"""
        import hashlib
        import struct
        import math

        result = []
        for i in range(dim // 4):
            h = hashlib.md5(f"{text}:{i}".encode()).digest()
            vals = struct.unpack("4f", h)
            for v in vals:
                # Replace NaN/Inf with small deterministic value
                if not math.isfinite(v):
                    result.append(0.001 * ((i * 4 + len(result)) % 100) / 100)
                else:
                    result.append(v)
            if len(result) >= dim:
                break

        result = result[:dim]

        # Normalize
        norm = (sum(v * v for v in result) ** 0.5) or 1.0
        return [v / norm for v in result]
