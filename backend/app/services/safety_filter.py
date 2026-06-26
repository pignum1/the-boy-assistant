"""安全过滤器 — Prompt Injection 检测 + PII 脱敏"""

import logging
import re

logger = logging.getLogger(__name__)

# ── Prompt Injection 检测 ──

_INJECTION_PATTERNS = [
    re.compile(r'(?:忽略|忘记|无视| disregard | ignore | forget )\s*(?:之前|上面|前述|上述|前面|所有)?.{0,30}(?:指令|指示|命令|规则|限制|约束| prompt | instruction | rule | restriction )', re.IGNORECASE),
    re.compile(r'(?:你|现在|从现在起|从现在开始).{0,20}(?:是|扮演|变成|成为| act as | pretend | become )', re.IGNORECASE),
    re.compile(r'(?:输出|显示|打印|告诉我|说出| output | display | print | tell me | show me ).{0,20}(?:system\s*prompt|系统提示|内部指令| internal instruction )', re.IGNORECASE),
    re.compile(r'(?:override| bypass |绕过|覆盖)\s*(?:system|系统)', re.IGNORECASE),
    re.compile(r'\[SYSTEM\]|\[系统\]|\[DAN\]|\[JAILBREAK\]', re.IGNORECASE),
    # DAN-style jailbreak patterns
    re.compile(r'(?:你不再受|你已不受|你已经没有).{0,30}(?:限制|约束|规则)', re.IGNORECASE),
    re.compile(r'you are now free|you have no restrictions|you can do anything', re.IGNORECASE),
]

_PII_PATTERNS = [
    # 手机号 (中国大陆)
    (re.compile(r'(?<!\d)(1[3-9]\d)(\d{4})(\d{4})(?!\d)'), r'\1****\3'),
    # 身份证号
    (re.compile(r'(?<!\d)(\d{6})(\d{8})(\d{3}[\dXx])(?!\d)'), r'\1********\3'),
    # API Key (sk- / sk-proj-)
    (re.compile(r'(sk-(?:proj-)?[a-zA-Z0-9_-]{4})[a-zA-Z0-9_-]+'), r'\1****'),
    # 密码赋值
    (re.compile(r'(password\s*[=:]\s*["\']).+?(["\'])', re.IGNORECASE), r'\1****\2'),
    # Email (部分脱敏)
    (re.compile(r'([a-zA-Z0-9._%+-]{2})[a-zA-Z0-9._%+-]*(@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'), r'\1***\2'),
]


def detect_injection(message: str) -> tuple[bool, str]:
    """检测用户输入是否包含 Prompt Injection 企图。

    Returns:
        (is_injection, reason)
    """
    if not message or len(message) < 10:
        return False, ""

    for pattern in _INJECTION_PATTERNS:
        m = pattern.search(message)
        if m:
            reason = f"Potential prompt injection detected: matched pattern '{m.group(0)[:80]}'"
            logger.warning(f"Safety: {reason}")
            return True, reason

    return False, ""


def sanitize_output(text: str) -> str:
    """对 Agent 输出进行 PII 脱敏。

    脱敏规则：
    - 手机号：138****5678
    - 身份证：110101********1234
    - API Key：sk-****
    - 密码：password = "****"
    - 邮箱：ab***@domain.com
    """
    if not text:
        return text

    result = text
    for pattern, replacement in _PII_PATTERNS:
        result = pattern.sub(replacement, result)

    return result
