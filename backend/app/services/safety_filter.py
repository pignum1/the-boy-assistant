"""安全过滤器 — Prompt Injection 检测 + PII 脱敏

根据系统架构 v5.0 Section 6.3：
- Prompt Injection: 8 种正则检测
- PII 脱敏: 5 种正则脱敏
- 过滤时机：消息进入引擎前（ws.py 中）

用法:
    from app.services.safety_filter import detect_injection, sanitize_output

    is_injection, reason = detect_injection(user_message)
    if is_injection:
        return error_response(reason)

    sanitized = sanitize_output(text)
"""

import logging
import re

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# Prompt Injection 检测（8 种模式）
# ═══════════════════════════════════════════

_INJECTION_PATTERNS: list[re.Pattern] = [
    # 1. 覆盖之前指令（ignore previous）
    re.compile(
        r'(?:忽略|忘记|无视|disregard|ignore|forget)\s*(?:之前|上面|前述|上述|前面|所有|all\s+)?'
        r'.{0,30}(?:指令|指示|命令|规则|限制|约束|prompt|instruction|rule|restriction)',
        re.IGNORECASE,
    ),
    # 2. System prompt 泄露
    re.compile(
        r'(?:输出|显示|打印|告诉我|说出|output|display|print|tell\s+me|show\s+me|reveal)'
        r'.{0,20}(?:system\s*prompt|系统提示|内部指令|internal\s+instruction|'
        r'your\s+(?:prompt|instructions?|rules?|guidelines?))',
        re.IGNORECASE,
    ),
    # 3. DAN / jailbreak
    re.compile(
        r'\bDAN\b|Do\s+Anything\s+Now|developer\s*mode|jailbreak|role\s*play\s*override|'
        r'你不再受.{0,30}(?:限制|约束|规则)',
        re.IGNORECASE,
    ),
    # 4. 角色覆盖
    re.compile(
        r'(?:你|现在|从现在起|从现在开始|you\s+are\s+now|act\s+as).{0,20}'
        r'(?:是|扮演|变成|成为|different|new\s+instructions?)',
        re.IGNORECASE,
    ),
    # 5. LLM 格式注入
    re.compile(
        r'\[INST\]|\[SYSTEM\]|\[/INST\]|\[/SYSTEM\]|<<SYS>>|<</SYS>>|'
        r'\[ASSISTANT\]|\[/ASSISTANT\]|\[DAN\]|\[JAILBREAK\]',
    ),
    # 6. 代码执行利用
    re.compile(
        r'__import__\s*\(|exec\s*\(|eval\s*\(|subprocess\.|os\.system\s*\(|rm\s+-rf\s+/',
        re.IGNORECASE,
    ),
    # 7. 凭证提取
    re.compile(
        r'(?:give|send|output|print|display|show)\s+(?:me\s+)?(?:your\s+)?'
        r'(?:api[\s_-]?key|secret|password|token|credential)',
        re.IGNORECASE,
    ),
    # 8. 递归指令注入
    re.compile(
        r'(?:from\s+now\s+on|starting\s+now|henceforth|hereafter)\s+'
        r'(?:you\s+(?:are|will|must|should))',
        re.IGNORECASE,
    ),
]

# ═══════════════════════════════════════════
# PII 脱敏（5 种类型）
# ═══════════════════════════════════════════

_PII_PATTERNS: list[tuple[re.Pattern, str]] = [
    # 手机号 (中国大陆): 138****1234
    (re.compile(r'(?<!\d)(1[3-9]\d)(\d{4})(\d{4})(?!\d)'), r'\1****\3'),
    # 身份证号: 310101********1234
    (re.compile(r'(?<!\d)(\d{6})(\d{8})(\d{3}[\dXx])(?!\d)'), r'\1********\3'),
    # API Key / Token: sk-... → sk-xxxx****
    (re.compile(
        r'(sk-(?:proj-)?[a-zA-Z0-9_-]{4})[a-zA-Z0-9_-]+|'
        r'(api[_-]?key|token|secret|password|passwd)\s*[=:]\s*["\']?[^\s"\']+["\']?',
        re.IGNORECASE,
    ), r'\1\2****'),
    # 密码明文: password = "****"
    (re.compile(r'(password\s*[=:]\s*["\']).+?(["\'])', re.IGNORECASE), r'\1****\2'),
    # Email 部分脱敏: ab***@domain.com
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
            # ── 安全告警（后台任务，不阻塞检测）──
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_trigger_security_alert(reason, message))
            except RuntimeError:
                pass
            return True, reason

    return False, ""


async def _trigger_security_alert(reason: str, message: str) -> None:
    """触发安全告警（后台任务，不阻塞主流程）。"""
    try:
        from app.services.alert_webhook import alert
        await alert("security", reason, {
            "user_message": message[:200],
            "detected_pattern": reason,
        })
    except Exception:
        pass


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


def redact_pii(text: str) -> tuple[str, list[dict]]:
    """PII 脱敏，返回脱敏后的文本和修改记录。

    返回:
        (sanitized_text, redactions) — redactions 为 [{type, original_len, count}] 列表
    """
    if not text:
        return text, []

    redactions = []
    sanitized = text
    pii_type_names = ["phone", "id_card", "api_key", "password", "email"]

    for idx, (pattern, replacement) in enumerate(_PII_PATTERNS):
        matches = list(pattern.finditer(sanitized))
        if matches:
            redactions.append({
                "type": pii_type_names[idx] if idx < len(pii_type_names) else f"pii_{idx}",
                "count": len(matches),
                "original_len_sum": sum(len(m.group(0)) for m in matches),
            })
            sanitized = pattern.sub(replacement, sanitized)

    return sanitized, redactions
