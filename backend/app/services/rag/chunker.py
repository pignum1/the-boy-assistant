"""语义分块器：按 Markdown 标题/段落边界切分，无结构时按固定大小+overlap"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _estimate_tokens(text: str) -> int:
    """粗略 token 估算"""
    if not text:
        return 0
    cn = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    en = len(text) - cn
    return int(cn * 1.5 + en * 0.25)


async def semantic_chunk(
    text: str,
    max_tokens: int = 512,
    overlap: int = 64,
    file_name: Optional[str] = None,
) -> list[dict]:
    """语义分块

    策略：
    1. 有 Markdown 标题结构 → 按标题切分
    2. 有段落分隔 → 按段落切分
    3. 无结构 → 按 max_tokens + overlap 固定切分
    """
    chunks = []

    # Try markdown heading split
    heading_pattern = re.compile(r'^(#{1,6})\s+.+$', re.MULTILINE)
    headings = list(heading_pattern.finditer(text))

    if len(headings) >= 2:
        chunks = _split_by_headings(text, headings, max_tokens)
    elif '\n\n' in text:
        chunks = _split_by_paragraphs(text, max_tokens, overlap)
    else:
        chunks = _split_by_size(text, max_tokens, overlap)

    # Build result with metadata
    result = []
    for i, chunk in enumerate(chunks):
        tokens = _estimate_tokens(chunk["content"])
        result.append({
            "content": chunk["content"],
            "chunk_index": i,
            "metadata": {
                "file_name": file_name,
                "section": chunk.get("section", ""),
                "start_line": chunk.get("start_line", 0),
                "tokens": tokens,
            },
        })

    logger.info(f"Chunked into {len(result)} pieces (max_tokens={max_tokens}, overlap={overlap})")
    return result


def _split_by_headings(text: str, headings: list, max_tokens: int) -> list[dict]:
    """按 Markdown 标题切分，大章节按 token 再分"""
    chunks = []
    for i, match in enumerate(headings):
        start = match.start()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        section = match.group().strip('#').strip()
        content = text[start:end].strip()

        if _estimate_tokens(content) <= max_tokens:
            chunks.append({"content": content, "section": section, "start_line": start})
        else:
            # Sub-chunk large sections
            sub_chunks = _split_by_size(content, max_tokens, 64)
            for sc in sub_chunks:
                sc["section"] = section
                sc["start_line"] = start
            chunks.extend(sub_chunks)
    return chunks


def _split_by_paragraphs(text: str, max_tokens: int, overlap: int) -> list[dict]:
    """按段落切分"""
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    chunks = []
    current = ""
    for p in paragraphs:
        if _estimate_tokens(current + "\n\n" + p) > max_tokens and current:
            chunks.append({"content": current, "section": "", "start_line": 0})
            # Keep overlap
            words = current.split()
            overlap_text = " ".join(words[-overlap:]) if len(words) > overlap else ""
            current = (overlap_text + "\n\n" + p).strip()
        else:
            current = (current + "\n\n" + p).strip()
    if current:
        chunks.append({"content": current, "section": "", "start_line": 0})
    return chunks


def _split_by_size(text: str, max_tokens: int, overlap: int) -> list[dict]:
    """固定大小切分 + overlap"""
    # Approximate: ~4 chars per token for mixed content
    chars_per_chunk = max_tokens * 3
    overlap_chars = overlap * 3

    if len(text) <= chars_per_chunk:
        return [{"content": text, "section": "", "start_line": 0}]

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chars_per_chunk, len(text))
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append({"content": chunk_text, "section": "", "start_line": start})
        start = end - overlap_chars
        if start >= len(text):
            break
    return chunks
