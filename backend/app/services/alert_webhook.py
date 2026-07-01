"""告警 Webhook — 关键事件通知（Slack / Discord / 自定义 Webhook）

根据系统架构 v5.0 — 告警场景：
- ESCALATION: 任务升级到人工（M6 escalate → M7 critical）
- FATAL_ERROR: 多次重试仍失败
- SECURITY: Prompt injection 检测
- HITL_TIMEOUT: 人工确认超时
- MODEL_FALLBACK: 模型降级

用法:
    from app.services.alert_webhook import alert

    await alert("escalation", "任务依赖缺失", {"team_id": "team-1", "task": "t1"})
    await alert("security", "检测到 prompt injection", {"user_msg": "..."})

配置（.env）:
    ALERT_WEBHOOK_SLACK=https://hooks.slack.com/services/...
    ALERT_WEBHOOK_DISCORD=https://discord.com/api/webhooks/...
    ALERT_WEBHOOK_CUSTOM=https://your-webhook.example.com/alerts
    ALERT_LEVEL=warning  # debug | info | warning | error | critical
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# Alert 类型
# ═══════════════════════════════════════════

AlertType = str
ALERT_TYPES: dict[str, dict[str, str]] = {
    "escalation": {
        "emoji": "🚨",
        "label": "任务升级",
        "level": "error",
    },
    "fatal_error": {
        "emoji": "💥",
        "label": "致命错误",
        "level": "critical",
    },
    "security": {
        "emoji": "🔒",
        "label": "安全告警",
        "level": "warning",
    },
    "hitl_timeout": {
        "emoji": "⏰",
        "label": "HITL 超时",
        "level": "warning",
    },
    "model_fallback": {
        "emoji": "⚠️",
        "label": "模型降级",
        "level": "warning",
    },
    "review_failed": {
        "emoji": "❌",
        "label": "验证失败",
        "level": "error",
    },
    "rate_limit": {
        "emoji": "⏳",
        "label": "速率限制",
        "level": "warning",
    },
}


# ═══════════════════════════════════════════
# Webhook 发送器
# ═══════════════════════════════════════════

class AlertDispatcher:
    """多通道告警分发器。

    - Slack: Incoming Webhook (Block Kit 格式)
    - Discord: Webhook (Embed 格式)
    - Custom: 通用 JSON payload
    """

    def __init__(self):
        self._webhooks: dict[str, str] = {}
        self._min_level: str = "warning"
        self._level_order = {"debug": 0, "info": 1, "warning": 2, "error": 3, "critical": 4}

    def configure(
        self,
        slack_url: str = "",
        discord_url: str = "",
        custom_url: str = "",
        min_level: str = "warning",
    ) -> None:
        """配置 Webhook URL 和最低告警级别。"""
        if slack_url:
            self._webhooks["slack"] = slack_url
        if discord_url:
            self._webhooks["discord"] = discord_url
        if custom_url:
            self._webhooks["custom"] = custom_url
        self._min_level = min_level

    async def send(
        self,
        alert_type: AlertType,
        title: str,
        details: Optional[dict[str, Any]] = None,
        trace_id: str = "",
    ) -> None:
        """发送告警到所有配置的通道。

        Args:
            alert_type: 告警类型（见 ALERT_TYPES）
            title: 告警标题
            details: 附加信息
            trace_id: 关联的 LangFuse trace ID
        """
        alert_info = ALERT_TYPES.get(alert_type, {})
        level = alert_info.get("level", "warning")

        # 级别过滤
        if self._level_order.get(level, 0) < self._level_order.get(self._min_level, 0):
            return

        emoji = alert_info.get("emoji", "📢")
        label = alert_info.get("label", alert_type)

        for channel, url in self._webhooks.items():
            try:
                if channel == "slack":
                    await self._send_slack(url, emoji, label, title, details, trace_id, level)
                elif channel == "discord":
                    await self._send_discord(url, emoji, label, title, details, trace_id, level)
                else:
                    await self._send_custom(url, alert_type, title, details, trace_id, level)
            except Exception as e:
                logger.warning(f"Alert webhook failed [{channel}]: {e}")

    async def _send_slack(
        self,
        url: str,
        emoji: str,
        label: str,
        title: str,
        details: Optional[dict],
        trace_id: str,
        level: str,
    ) -> None:
        """发送到 Slack（Block Kit 格式）。"""
        color = {"warning": "#ffa500", "error": "#ff0000", "critical": "#8b0000"}.get(
            level, "#808080"
        )

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{emoji} {label}"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Title:*\n{title}"},
                    {"type": "mrkdwn", "text": f"*Time:*\n{datetime.now().isoformat()}"},
                ],
            },
        ]

        if details:
            detail_text = "\n".join(
                f"• {k}: {str(v)[:200]}" for k, v in details.items()
            )
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"```{detail_text}```"},
            })

        if trace_id:
            blocks.append({
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"Trace: `{trace_id[:20]}...`"}
                ],
            })

        payload = {
            "attachments": [
                {
                    "color": color,
                    "blocks": blocks,
                }
            ]
        }

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code >= 400:
                logger.warning(f"Slack webhook failed: HTTP {resp.status_code} {resp.text[:200]}")

    async def _send_discord(
        self,
        url: str,
        emoji: str,
        label: str,
        title: str,
        details: Optional[dict],
        trace_id: str,
        level: str,
    ) -> None:
        """发送到 Discord（Embed 格式）。"""
        color = {"warning": 0xFFA500, "error": 0xFF0000, "critical": 0x8B0000}.get(
            level, 0x808080
        )

        embed = {
            "title": f"{emoji} {label}: {title}",
            "color": color,
            "timestamp": datetime.now().isoformat(),
            "fields": [],
        }

        if details:
            for k, v in details.items():
                embed["fields"].append({
                    "name": k,
                    "value": str(v)[:1024],
                    "inline": True,
                })

        if trace_id:
            embed["footer"] = {"text": f"Trace: {trace_id}"}

        payload = {"embeds": [embed]}

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code >= 400:
                logger.warning(f"Discord webhook failed: HTTP {resp.status_code} {resp.text[:200]}")

    async def _send_custom(
        self,
        url: str,
        alert_type: str,
        title: str,
        details: Optional[dict],
        trace_id: str,
        level: str,
    ) -> None:
        """发送到自定义 Webhook（通用 JSON）。"""
        payload = {
            "type": alert_type,
            "level": level,
            "title": title,
            "details": details or {},
            "trace_id": trace_id,
            "timestamp": datetime.now().isoformat(),
        }

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code >= 400:
                logger.warning(f"Custom webhook failed: HTTP {resp.status_code} {resp.text[:200]}")


# ── Module-level singleton ──

_dispatcher: Optional[AlertDispatcher] = None


def get_alert_dispatcher() -> AlertDispatcher:
    """获取 AlertDispatcher 单例。"""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = AlertDispatcher()
    return _dispatcher


async def alert(
    alert_type: AlertType,
    title: str,
    details: Optional[dict[str, Any]] = None,
    trace_id: str = "",
) -> None:
    """便捷函数：发送告警。

    用法:
        await alert("escalation", "任务因严重偏离升级", {"team_id": "t1"})
        await alert("security", "检测到 prompt injection", {"user_msg": "..."})
    """
    dispatcher = get_alert_dispatcher()
    await dispatcher.send(alert_type, title, details, trace_id)


# ═══════════════════════════════════════════
# 启动时自动配置（从 config 读取 webhook URL）
# ═══════════════════════════════════════════

def init_alerts_from_config() -> None:
    """从应用配置初始化告警通道。

    在 app startup 事件中调用。
    """
    try:
        from app.core.config import get_settings
        settings = get_settings()

        slack = getattr(settings, "ALERT_WEBHOOK_SLACK", "") or ""
        discord = getattr(settings, "ALERT_WEBHOOK_DISCORD", "") or ""
        custom = getattr(settings, "ALERT_WEBHOOK_CUSTOM", "") or ""
        min_level = getattr(settings, "ALERT_LEVEL", "warning") or "warning"

        if slack or discord or custom:
            dispatcher = get_alert_dispatcher()
            dispatcher.configure(
                slack_url=slack,
                discord_url=discord,
                custom_url=custom,
                min_level=min_level,
            )
            channels = []
            if slack:
                channels.append("Slack")
            if discord:
                channels.append("Discord")
            if custom:
                channels.append("Custom")
            logger.info(f"Alert webhooks configured: {', '.join(channels)} (min_level={min_level})")
        else:
            logger.info("No alert webhooks configured (set ALERT_WEBHOOK_SLACK/DISCORD/CUSTOM in .env)")

    except Exception as e:
        logger.warning(f"Failed to init alert webhooks: {e}")
