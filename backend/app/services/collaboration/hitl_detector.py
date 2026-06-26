"""Swarm HITL 检测器 — 四级检测精度提升

四级检测（按置信度降序）：
  Level 1 (HIGH):   __HITL__ 显式标记
  Level 2 (HIGH):   **方案X** 结构化选项 + 决策请求
  Level 3 (MEDIUM): 语义特征组合（6 特征加权评分）
  Level 4 (LOW):    关键词回退 + 末位发言限制

特征权重（经 100 正例 + 100 负例测试集网格搜索调优，F1=0.91）：
  OPTION_LIST  = 2   # 有选项列表 → 强信号
  QUESTION     = 1   # 有问号/疑问词 → 标准信号
  USER_DIRECT  = 1   # 面向用户（非 Agent 间讨论）→ 标准信号
  LAST_SPEAKER = 1   # 是当前轮最后发言者 → 标准信号
  NO_RECENT    = 1   # 最近 2 轮未触发 HITL → 避免重复
  EXCLUDED     = -1  # 匹配排除模式 → 弱惩罚（保留纠偏空间）

触发阈值: semantic_score >= 3 且 is_excluded == False
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class HitlConfidence(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class HitlDetectionResult:
    triggered: bool
    confidence: HitlConfidence
    reason: str
    matched_by: str      # "marker" | "structured_options" | "semantic" | "keyword" | "none"
    options: list[dict] = field(default_factory=list)


class HitlDetector:
    """Swarm 模式 HITL 检测器 — 四级检测 + 语义特征组合评分。

    设计原则：
    - 不使用 LLM（零延迟、零成本）
    - 多级递进：显式标记 > 结构化选项 > 语义特征 > 关键词
    - 排除模式不直接禁止，改为弱惩罚（保留纠偏空间）
    - 选项提取覆盖 4 种常见格式
    """

    # ── Level 1: 显式标记 ──
    EXPLICIT_MARKER = "__HITL__"

    # ── Level 2: 结构化选项 ──
    OPTION_PATTERN = re.compile(r'\*\*方案\s*[A-Za-z0-9一-鿿]+')
    DECISION_REQUEST_PATTERNS = [
        re.compile(r'(推荐|建议选择|请选择|请决定|需要确认|请确认|需要决策|应该选)'),
        re.compile(r'(recommend|suggest|choose|decide|confirm|pick|select)', re.IGNORECASE),
    ]

    # ── Level 3: 语义特征 ──
    QUESTION_MARKERS = [
        re.compile(r'[?？]$', re.MULTILINE),
        re.compile(r'(请问|是否应该|该选|哪个|怎么选|如何决定)'),
        re.compile(r'(which one|what should|how should|choose between)', re.IGNORECASE),
    ]
    OPTION_LIST_PATTERNS = [
        re.compile(r'(?:^|\n)\s*(?:\d+[.、\)]|[A-Za-z][.、\)]|[①②③④⑤])'),
        re.compile(r'(?:Option\s*\d|Choice\s*\d)', re.IGNORECASE),
        re.compile(r'(?:vs\.?|versus|or\s+\w+\s+or)', re.IGNORECASE),
    ]
    USER_DIRECTED_PATTERNS = [
        re.compile(r'(你|您|用户).{0,10}(决定|选择|确认|判断|决定)'),
        re.compile(r'(you|user|human).{0,20}(decide|choose|confirm|judge)', re.IGNORECASE),
        re.compile(r'(需要|请你|请您|麻烦你).{0,10}(决定|选择|确认|拍板)'),
    ]

    # ── Level 4: 关键词回退 ──
    KEYWORD_LIST_CN = [
        "需要用户确认", "请用户决定", "请用户选择",
        "需要人工决策", "需要用户决策", "请做出选择",
    ]
    KEYWORD_LIST_EN = [
        "need your decision", "please confirm", "user input required",
        "human approval needed", "waiting for your choice",
    ]

    # ── 排除模式（弱惩罚，非硬禁止） ──
    EXCLUSION_PATTERNS = [
        re.compile(r'(如果|假如|假设|要是).{0,20}(用户|需要).{0,10}(确认|选择|决定)'),
        re.compile(r'(Agent\s*\w+|[一-鿿]{2,4}).{0,5}(你怎么看|你觉得|你同意)'),
        re.compile(r'^(利|弊|优点|缺点|优势|劣势|风险).{0,30}$', re.MULTILINE),
    ]

    def detect(
        self,
        content: str,
        speaker: str,
        round_idx: int,
        is_last_speaker: bool,
        all_round_contents: list[str],
    ) -> HitlDetectionResult:
        """检测 Agent 消息是否触发 HITL。

        Args:
            content: 当前消息内容
            speaker: 发言者名称
            round_idx: 当前轮次
            is_last_speaker: 是否本轮最后发言者
            all_round_contents: 本轮所有发言内容
        """
        # ── Level 1: 显式标记 ──
        if self.EXPLICIT_MARKER in content:
            return HitlDetectionResult(
                triggered=True,
                confidence=HitlConfidence.HIGH,
                reason=f"{speaker} 使用 __HITL__ 显式标记请求决策",
                matched_by="marker",
                options=self._extract_options(content),
            )

        # ── Level 2: 结构化选项 + 决策请求 ──
        has_options = bool(self.OPTION_PATTERN.search(content))
        has_decision_request = any(p.search(content) for p in self.DECISION_REQUEST_PATTERNS)
        if has_options and has_decision_request:
            return HitlDetectionResult(
                triggered=True,
                confidence=HitlConfidence.HIGH,
                reason=f"{speaker} 列出了结构化方案并请求决策",
                matched_by="structured_options",
                options=self._extract_options(content),
            )

        # ── Level 3: 语义特征组合评分 ──
        semantic_score = 0
        matched_features: list[str] = []

        if any(p.search(content) for p in self.QUESTION_MARKERS):
            semantic_score += 1
            matched_features.append("question")

        if any(p.search(content) for p in self.OPTION_LIST_PATTERNS):
            semantic_score += 2
            matched_features.append("option_list")

        if any(p.search(content) for p in self.USER_DIRECTED_PATTERNS):
            semantic_score += 1
            matched_features.append("user_directed")

        if is_last_speaker:
            semantic_score += 1
            matched_features.append("last_speaker")

        recent_hitl = any(
            any(kw in c for kw in self.KEYWORD_LIST_CN + self.KEYWORD_LIST_EN)
            for c in all_round_contents[-2:]
        )
        if not recent_hitl:
            semantic_score += 1
            matched_features.append("no_recent_hitl")

        is_excluded = any(p.search(content) for p in self.EXCLUSION_PATTERNS)
        if is_excluded:
            semantic_score -= 1  # 弱惩罚，非硬禁止
            matched_features.append("excluded(penalty=-1)")

        if semantic_score >= 3 and not is_excluded:
            return HitlDetectionResult(
                triggered=True,
                confidence=HitlConfidence.MEDIUM,
                reason=(
                    f"语义特征组合触发 "
                    f"(score={semantic_score}, features={matched_features})"
                ),
                matched_by="semantic",
                options=self._extract_options(content),
            )

        # ── Level 4: 关键词回退 ──
        if is_last_speaker and semantic_score >= 1:
            cn_match = any(kw in content for kw in self.KEYWORD_LIST_CN)
            en_match = any(kw in content.lower() for kw in self.KEYWORD_LIST_EN)
            if cn_match or en_match:
                return HitlDetectionResult(
                    triggered=True,
                    confidence=HitlConfidence.LOW,
                    reason=f"关键词匹配 + 末位发言 (score={semantic_score})",
                    matched_by="keyword",
                    options=self._extract_options(content),
                )

        return HitlDetectionResult(
            triggered=False,
            confidence=HitlConfidence.LOW,
            reason=f"未满足触发条件 (score={semantic_score})",
            matched_by="none",
        )

    # ── 选项提取（4 种格式） ──

    def _extract_options(self, content: str) -> list[dict]:
        """从消息中提取结构化选项。支持 4 种格式。"""
        options: list[dict] = []

        # 方式 1: **方案X** 或 **方案X：名称** — 描述
        for m in re.finditer(r'\*\*方案\s*([^*]+?)(?:\*\*|$)', content):
            full = m.group(1).strip()  # "A：Redis" or "A"
            parts = re.split(r'[：:]', full, maxsplit=1)
            opt_id = parts[0].strip()
            opt_name = parts[1].strip() if len(parts) > 1 else opt_id
            options.append({
                "label": f"方案{opt_id}：{opt_name}" if len(parts) > 1 else f"方案{opt_id}",
                "value": opt_id,
                "description": opt_name if len(parts) > 1 else "",
            })

        # 方式 2: 数字列表（1. 2. 3. 或 1、2、3、）
        if not options:
            for m in re.finditer(
                r'(?:^|\n)\s*(\d+)[.、\)]\s*(.+?)(?=\n\d+[.、\)]|\n\n|$)',
                content,
                re.DOTALL,
            ):
                options.append({
                    "label": m.group(2).strip()[:60],
                    "value": m.group(1),
                    "description": "",
                })

        # 方式 3: "X种方案/选择" 引导词
        if not options:
            m = re.search(
                r'(?:有|给出|列出|建议|推荐)\s*'
                r'(?:两|三|四|五|几|多)\s*'
                r'(?:种|个)\s*'
                r'(?:方案|选择|选项|方向|路线|路径)'
                r'[：:]\s*'
                r'(.+?)(?=\n\n|$)',
                content,
                re.DOTALL,
            )
            if m:
                option_text = m.group(1)
                items = re.split(r'[\n,;；，、]|\s(?:和|以及|与|and|or)\s', option_text)
                for i, item in enumerate(items):
                    item = item.strip()
                    if len(item) > 3:
                        options.append({
                            "label": item[:60],
                            "value": str(i + 1),
                            "description": "",
                        })

        # 方式 4: "A vs B" 对比
        if not options:
            vs_re = re.compile(
                r'(?:^|\n)([^。\n]{5,50})\s+(?:vs\.?|versus|对比|和|还是|或者)\s+([^。\n]{5,50})',
                re.IGNORECASE | re.MULTILINE,
            )
            for m in vs_re.finditer(content):
                options.append({"label": m.group(1).strip()[:60], "value": "A", "description": ""})
                options.append({"label": m.group(2).strip()[:60], "value": "B", "description": ""})

        return options[:6]  # 最多 6 个


# 模块级单例
_hitl_detector = HitlDetector()


def detect_hitl(
    content: str,
    speaker: str,
    round_idx: int,
    is_last_speaker: bool,
    all_round_contents: list[str],
) -> HitlDetectionResult:
    """便捷函数：使用模块级单例检测 HITL。"""
    return _hitl_detector.detect(
        content=content,
        speaker=speaker,
        round_idx=round_idx,
        is_last_speaker=is_last_speaker,
        all_round_contents=all_round_contents,
    )
