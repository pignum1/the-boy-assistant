"""ReAct Agent 执行器 — Think-Act-Observe 循环

实现 ReAct (Reasoning + Acting) 模式，让 Agent 在单次任务中
可以迭代思考、调用工具、验证结果，直到完成或达到上限。

设计原则：
- 每次循环：Think → Act → Observe → 判断是否完成
- Thought 和 Action 在一次 LLM 调用中完成
- 工具结果和验证输出追加到 history，下轮自动注入
- 最大循环次数可配置，超限后强制汇总输出
"""

import json
import logging
import os
import re
from typing import Any

from app.services.agent_chat import agent_chat
from app.services.trace_context import TraceContext, trace_metadata

logger = logging.getLogger(__name__)

# ── 文件提取正则 ──

# 常见源码/配置文件扩展名
_FILE_EXT_RE = re.compile(
    r'[\w\-./\\]+\.(?:py|js|ts|tsx|jsx|json|yaml|yml|toml|md|txt|html|css|scss|'
    r'sql|sh|bash|cfg|ini|env|example|go|rs|java|rb|php|vue|svelte)\b',
    re.IGNORECASE,
)
# 代码块 ```lang\n...\n```
_FENCE_RE = re.compile(r'```([^\n`]*)\n(.*?)\n\s*```', re.DOTALL)
# "文件: xxx" / "创建文件 xxx" 等关键词前缀
_FILE_KW_RE = re.compile(
    r'(?:文件|创建文件|新建文件|写入|保存到|路径|file)\s*[:：]?\s*(.+)',
    re.IGNORECASE,
)

# ── ReAct System Prompt ──

REACT_SYSTEM_PROMPT = """你是一个具备迭代执行能力的 AI Agent。

## 执行模式
你采用 Think → Act → Observe 循环模式工作：
1. **Think**: 分析当前状态，决定下一步做什么
2. **Act**: 执行具体的动作（生成代码、调用工具、输出结果）
3. **Observe**: 查看执行结果，判断是否完成

## 输出格式
每轮你必须输出以下格式：

```
THOUGHT: <你的分析：当前进展如何？还需要做什么？为什么？>
ACTION: <你要执行的具体动作>
```

当任务完成时，输出：
```
THOUGHT: <总结分析，说明为什么任务已完成>
FINAL_ANSWER: <最终产出的完整内容>
```

## 规则
- 每轮必须同时输出 THOUGHT 和 ACTION
- 不要重复之前已经完成的工作
- 如果连续 2 轮没有实质进展，直接输出 FINAL_ANSWER
- 代码必须完整可运行，不要用省略号或注释占位

## 创建文件（重要）
当你需要在 ACTION 中创建/写入文件时，**必须**用如下格式标注文件名，紧跟代码块，
系统会据此把代码真正写入工作区：

```
ACTION: 创建项目文件。
文件: app/main.py
```python
from fastapi import FastAPI
app = FastAPI()
```

文件: requirements.txt
```text
fastapi
uvicorn
```
```

每个文件一个 `文件: <相对路径>` 行 + 一个代码块。路径用相对路径（如 `app/models.py`）。
"""

# ── Review and fix prompt template ──

CODE_REVIEW_PROMPT = """请审查以下代码，找出问题并修正。

## 代码
{code}

## 审查要求
1. 检查语法错误、逻辑错误
2. 检查是否满足需求
3. 检查是否有安全漏洞
4. 如果发现错误，输出修正后的完整代码
5. 如果代码正确，输出 "CODE_OK"

## 修正后的代码（或 CODE_OK）
"""


class ReActExecutor:
    """ReAct 执行器。

    用法:
        executor = ReActExecutor()
        result = await executor.execute(
            prompt=prompt, agent=agent, db=db,
            config={"max_iterations": 5, "enable_self_review": True},
        )
    """

    def __init__(self):
        pass

    async def execute(
        self,
        prompt: str,
        agent,
        db,
        session_id: str = "",
        team_id: str = "",
        config: dict | None = None,
    ) -> dict[str, Any]:
        # 从 config 读取参数，兜底默认值
        max_iterations = (config or {}).get("max_iterations", 5)
        enable_self_review = (config or {}).get("enable_self_review", True)
        """执行 ReAct 循环。

        Returns:
            {
                "content": str,         # 最终输出
                "iterations": int,      # 循环次数
                "history": list[str],   # 完整思考链
            }
        """
        system_prompt = REACT_SYSTEM_PROMPT
        history = [f"## 任务\n{prompt}"]
        final_answer = None
        all_tool_calls: list[dict] = []
        written_paths: set[str] = set()

        for i in range(max_iterations):
            logger.info(f"[ReAct] Iteration {i+1}/{max_iterations}")

            # 构建当前轮的 prompt
            history_text = "\n\n".join(history)
            full_prompt = f"{system_prompt}\n\n## 对话历史\n{history_text}\n\n请输出 THOUGHT 和 ACTION。"

            with TraceContext.span(name=trace_metadata.iter_span_name("react", i+1), metadata=trace_metadata.iter_span_meta(exec_mode="react", iteration=i+1, max_iterations=max_iterations)):
                result = await agent_chat(
                    db=db, agent=agent, message=full_prompt,
                    return_reasoning=False, save_memory=False,
                    session_id=session_id, team_id=team_id,
                )
            response = result.get("content", "").strip()

            # 解析 THOUGHT 和 ACTION/FINAL_ANSWER
            thought = self._extract_tag(response, "THOUGHT")
            action = self._extract_tag(response, "ACTION")
            final = self._extract_tag(response, "FINAL_ANSWER")

            if thought:
                history.append(f"## Round {i+1}\nTHOUGHT: {thought}")

            # ── 从本轮输出中提取文件并写入工作区 ──
            # 扫描完整 response（FINAL/ACTION 是其子集），最大化捕获 LLM 产出的文件，
            # 无论它是否严格遵循 `文件: <路径>` 格式
            files = self._extract_files(response)
            if files:
                tcs = await self._write_files_to_workspace(
                    files, session_id, written_paths,
                )
                if tcs:
                    all_tool_calls.extend(tcs)
                    names = ", ".join(tc["params"]["path"] for tc in tcs)
                    history.append(f"OBSERVATION: 已写入 {len(tcs)} 个文件: {names}")

            if final:
                final_answer = final
                break
            if action:
                history.append(f"ACTION: {action[:2000]}")
                # 执行结果反馈
                if enable_self_review and i < max_iterations - 1:
                    # 检查是否需要代码审查
                    observation = self._generate_observation(action, prompt)
                    if observation:
                        history.append(f"OBSERVATION: {observation}")

        # 如果没有 FINAL_ANSWER，用最后一轮输出作为结果
        if not final_answer:
            logger.warning(f"[ReAct] Max iterations reached, summarizing")
            final_answer = self._extract_best_output(history)

        # 多轮迭代可能重复写入同一文件（后写覆盖先写，磁盘内容已是最新）；
        # 对外返回的 tool_calls 按路径去重，避免产物面板出现重复条目。
        seen: set[str] = set()
        unique_tool_calls: list[dict] = []
        for tc in all_tool_calls:
            p = tc.get("params", {}).get("path", "")
            if p and p not in seen:
                seen.add(p)
                unique_tool_calls.append(tc)

        logger.info(
            f"[ReAct] done iterations={i+1} files_written={len(unique_tool_calls)}"
        )
        return {
            "content": final_answer,
            "iterations": i + 1,
            "history": history,
            "reasoning": {"tool_calls": unique_tool_calls},
        }

    def _extract_tag(self, text: str, tag: str) -> str:
        """从文本中提取标签内容。"""
        patterns = [
            rf"{tag}:\s*(.+?)(?=\n(?:THOUGHT|ACTION|FINAL_ANSWER|OBSERVATION):|$)",
            rf"{tag}\s*[:：]\s*(.+?)(?=\n(?:THOUGHT|ACTION|FINAL_ANSWER|OBSERVATION)|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""

    def _extract_files(self, text: str) -> list[tuple[str, str]]:
        """从 LLM 输出中提取 (相对路径, 内容) 文件对。

        识别代码块前 1~4 行内的文件名（`文件: xxx` 关键词，或裸路径行）。
        """
        files: list[tuple[str, str]] = []
        for m in _FENCE_RE.finditer(text):
            code = m.group(2)
            preface = text[max(0, m.start() - 240): m.start()]
            preface_lines = [ln.strip() for ln in preface.split("\n")][-4:]
            path = None
            for line in reversed(preface_lines):
                line = line.strip("*#`> ").strip()
                if not line:
                    continue
                kw = _FILE_KW_RE.match(line)
                cand = kw.group(1).strip().strip("`*").strip() if kw else line
                fm = _FILE_EXT_RE.search(cand)
                if fm:
                    path = fm.group(0).strip()
                    break
            if path:
                files.append((path, code))
        return files

    async def _write_files_to_workspace(
        self,
        files: list[tuple[str, str]],
        session_id: str,
        written: set[str],
    ) -> list[dict]:
        """把提取到的文件写入 session 工作区，返回 tool_calls 记录。"""
        if not files or not session_id:
            return []
        try:
            from app.services.workspace.manager import workspace_manager

            ws = workspace_manager.get_or_create(session_id)
            ws_path = getattr(ws, "path", None)
            if not ws_path:
                return []
        except Exception as e:
            logger.warning(f"[ReAct] workspace unavailable: {e}")
            return []

        tool_calls: list[dict] = []
        for path, content in files:
            # 规范化路径，防止越权跳出工作区
            clean = path.replace("\\", "/").lstrip("/")
            if clean.startswith("..") or not clean:
                continue
            full = os.path.join(ws_path, clean)
            try:
                os.makedirs(os.path.dirname(full) or ws_path, exist_ok=True)
                with open(full, "w", encoding="utf-8") as f:
                    f.write(content)
                written.add(clean)
                tool_calls.append(
                    {"tool": "file-ops", "success": True, "params": {"path": clean}}
                )
            except Exception as e:
                logger.warning(f"[ReAct] write {clean} failed: {e}")
        return tool_calls

    def _generate_observation(self, action: str, task: str) -> str:
        """为 Action 生成简单的观察反馈。"""
        action_lower = action.lower()

        feedbacks = []

        # 检查代码完整性
        if "```" in action:
            # 检查是否有未闭合的代码块
            code_blocks = action.count("```")
            if code_blocks % 2 != 0:
                feedbacks.append("代码块未正确闭合（``` 不成对）")

        # 检查是否有省略号（不完整的代码）
        if "..." in action and "..." not in task:
            if not action.strip().endswith("..."):
                feedbacks.append("输出包含省略号(...)，代码可能不完整")

        # 检查是否有明显的占位符
        placeholders = ["todo", "TODO", "fixme", "FIXME", "xxx", "your_key_here"]
        for ph in placeholders:
            if ph in action:
                feedbacks.append(f"输出包含占位符 '{ph}'，需要替换为实际内容")

        if feedbacks:
            return " | ".join(feedbacks)
        return ""

    def _extract_best_output(self, history: list[str]) -> str:
        """从历史中提取最完整的输出。"""
        # 找最后一个 ACTION 作为最佳输出
        for h in reversed(history):
            if h.startswith("ACTION:"):
                return h[7:].strip()
        # 回退：用最后一个非 THOUGHT 的内容
        for h in reversed(history):
            if not h.startswith("THOUGHT:") and not h.startswith("OBSERVATION:"):
                return h
        return history[-1] if history else ""
