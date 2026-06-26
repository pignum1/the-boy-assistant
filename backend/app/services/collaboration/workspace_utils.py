"""工作空间文件提取工具 — langgraph_engine 和 m6_execute_worker 共享

提供：
- 代码块中的文件路径解析
- 工作空间文件写入
"""

import logging
import os as _os
import re as _re
from typing import Optional

logger = logging.getLogger(__name__)

# 语言扩展名映射
EXT_MAP = {
    'python': '.py', 'py': '.py',
    'javascript': '.js', 'js': '.js',
    'typescript': '.ts', 'ts': '.ts', 'tsx': '.tsx', 'jsx': '.jsx',
    'html': '.html', 'css': '.css', 'scss': '.scss',
    'json': '.json', 'yaml': '.yml', 'yml': '.yml', 'toml': '.toml',
    'sql': '.sql', 'sh': '.sh', 'bash': '.sh', 'shell': '.sh',
    'dockerfile': 'Dockerfile', 'md': '.md', 'markdown': '.md',
    'vue': '.vue', 'svelte': '.svelte',
    'rust': '.rs', 'go': '.go', 'java': '.java', 'kotlin': '.kt',
    'swift': '.swift', 'c': '.c', 'cpp': '.cpp', 'h': '.h',
}

# 路径匹配正则（要求带斜杠的相对路径 + 已知扩展名，排除 .. 路径遍历）
_PATH_RE = _re.compile(
    r'(?!(?:\.\./|\.\.[\\/]))'  # 拒绝 .. 路径遍历
    r'(?:[\w.-]+/)+(?:'
    r'[\w.-]+\.(?:py|js|ts|tsx|jsx|html|css|scss|json|yml|yaml|toml|sql|sh|md|txt|cfg|ini|vue|svelte|'
    r'rs|go|java|kt|swift|c|cpp|h)'
    r'|Dockerfile[\w.-]*'
    r'|Makefile'
    r'|\.env[\w.-]*'
    r'|\.gitignore'
    r'|\.dockerignore'
    r'|\.editorconfig'
    r')'
)

# 已知的特殊文件名（不含标准扩展名）
KNOWN_SPECIAL = frozenset({
    'dockerfile', 'makefile',
    '.env', '.gitignore', '.dockerignore', '.editorconfig',
})


def is_real_code(lang: str, code: str) -> bool:
    """判断代码块是否为真正的代码（排除自然语言文本混入代码块）。"""
    code_stripped = code.strip()
    # 过短不是代码
    if len(code_stripped) < 10:
        return False
    # 纯自然语言行太多不是代码
    lines = code_stripped.split('\n')
    code_lines = 0
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or stripped.startswith('//'):
            continue
        if any(
            kw in stripped
            for kw in ['import ', 'from ', 'def ', 'class ', 'function ', 'const ',
                       'let ', 'var ', 'return ', 'if ', 'for ', 'while ', 'export ',
                       'package ', 'use ', 'fn ', 'pub ', 'func ', '{', '}', ';',
                       'print(', 'console.']
        ):
            code_lines += 1
    return code_lines >= max(1, len(lines) * 0.3)


def extract_files_from_content(
    content: str,
    ws_path: str,
    *,
    source_label: str = "unknown",
) -> list[str]:
    """从 Agent 输出内容中提取代码块并写入工作空间。

    遵循与 m6_execute_worker 相同的严格路径约定：
    只保存代码块第一行明确声明了相对路径的文件。

    Returns:
        写入的文件相对路径列表
    """
    if not ws_path or not content:
        return []

    # 匹配所有代码块：```lang[ path]\n...```
    fence_re = _re.compile(
        r'```(\w+)(?:\s+([^\n]*?))?\n(.*?)```',
        _re.DOTALL,
    )
    written_files: list[str] = []

    for match in fence_re.finditer(content):
        lang = match.group(1).lower()
        fence_rest = (match.group(2) or "").strip()
        code = match.group(3)

        # Lang 有效性检查
        if lang not in EXT_MAP and lang not in ('text', 'plaintext', 'txt', 'bash', 'shell', 'dockerfile'):
            continue

        # 从 fence_rest 提取声明路径
        declared_path: Optional[str] = None
        m = _PATH_RE.search(fence_rest)
        if m:
            declared_path = m.group(0)
        else:
            # 尝试将整个 fence_rest 作为路径
            cand = fence_rest.split()[0] if fence_rest else ""
            mm = _PATH_RE.fullmatch(cand) if cand else None
            if mm:
                declared_path = cand

        if not declared_path and not is_real_code(lang, code):
            continue

        # 确定写入的路径
        file_path: str
        if declared_path:
            file_path = declared_path
        else:
            # 无声明路径：生成一个
            ext = EXT_MAP.get(lang, '.txt')
            file_path = f"output_{len(written_files) + 1}{ext}"

        # 安全检查：路径必须在工作空间内，不能有 ..
        if ".." in file_path:
            logger.warning("[%s] Skipping path with '..': %s", source_label, file_path)
            continue

        full_path = _os.path.join(ws_path, file_path)
        full_path = _os.path.abspath(full_path)
        ws_abs = _os.path.abspath(ws_path)

        if not full_path.startswith(ws_abs):
            logger.warning("[%s] Path outside workspace: %s", source_label, file_path)
            continue

        try:
            _os.makedirs(_os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(code)
            written_files.append(file_path)
            logger.info("[%s] Written: %s (%d chars)", source_label, file_path, len(code))
        except OSError as e:
            logger.error("[%s] Failed to write %s: %s", source_label, file_path, e)

    return written_files
