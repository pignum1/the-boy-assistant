"""Self-Consistency 执行器 — 多采样投票

同一 prompt 跑 N 次（temperature>0），取多数一致结果。
适合需要高可靠性的场景（代码审查、安全分析、分类判断）。

参数:
  sample_count: int = 3  采样次数
"""
import logging
from typing import Any

from app.services.agent_chat import agent_chat
from app.services.trace_context import TraceContext, trace_metadata

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_COUNT = 3

MERGE_PROMPT = """以下是对同一个问题的 {count} 次独立回答。请综合这些回答，给出最终答案。

要求：
1. 如果多次回答一致，直接输出该一致的答案
2. 如果有分歧，分析各自优劣，输出最优方案
3. 不要简单复制某一次回答，要真正综合

## 各次回答
{answers}

## 综合回答
"""


class SelfConsistencyExecutor:
    """Self-Consistency 执行器。

    用法:
        executor = SelfConsistencyExecutor()
        result = await executor.execute(prompt=prompt, agent=agent, db=db, config={"sample_count": 3})
    """

    async def execute(
        self,
        prompt: str,
        agent,
        db,
        session_id: str = "",
        team_id: str = "",
        config: dict | None = None,
    ) -> dict[str, Any]:
        """执行 Self-Consistency 采样 + 综合。

        Returns:
            {content, iterations, reasoning}
        """
        sample_count = (config or {}).get("sample_count", DEFAULT_SAMPLE_COUNT)
        sample_count = max(2, min(sample_count, 7))  # 限制 2-7

        logger.info(f"[SelfConsistency] sampling {sample_count} times")

        samples: list[str] = []
        with TraceContext.span(name=trace_metadata.phase_span_name("self_consistency", "sampling"), metadata=trace_metadata.phase_span_meta(mode="self_consistency", phase_name="sampling", phase_index=1, total_phases=2)):
            for i in range(sample_count):
                result = await agent_chat(
                    db=db, agent=agent, message=prompt,
                    return_reasoning=False, save_memory=False,
                    session_id=session_id, team_id=team_id,
                )
                content = (result.get("content") or "").strip()
                if content:
                    samples.append(content)
                logger.info(f"[SelfConsistency] sample {i+1}/{sample_count}: {len(content)} chars")

        if not samples:
            return {
                "content": "",
                "iterations": sample_count,
                "reasoning": {"samples": []},
            }

        # 如果只有一份有效采样，直接返回
        if len(samples) == 1:
            return {
                "content": samples[0],
                "iterations": sample_count,
                "reasoning": {"samples": samples, "merged": False},
            }

        # 多份采样 → LLM 综合
        with TraceContext.span(name=trace_metadata.phase_span_name("self_consistency", "merge"), metadata=trace_metadata.phase_span_meta(mode="self_consistency", phase_name="merge", phase_index=2, total_phases=2)):
            answers_text = "\n\n---\n\n".join(
                f"### 回答 {i+1}\n{s}" for i, s in enumerate(samples)
            )
            merge_message = MERGE_PROMPT.format(count=len(samples), answers=answers_text)

            merge_result = await agent_chat(
                db=db, agent=agent, message=merge_message,
                return_reasoning=False, save_memory=False,
                session_id=session_id, team_id=team_id,
            )

        return {
            "content": (merge_result.get("content") or samples[0]).strip(),
            "iterations": sample_count + 1,
            "reasoning": {"samples": samples, "merged": True},
        }
