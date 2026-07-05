"""回归测试：用户消息末尾的纳秒去重标记不应展示给用户。

背景：ws.py 在保存用户消息时会附加 f"[{time.time_ns()}]" 作为持久化去重 key
（使每轮用户消息内容唯一，避免 get_session_messages 按内容去重时把重复/配对
消息合并）。该标记仅供去重使用，读取展示时必须剥离，否则刷新页面后用户消息
会显示成 'hi[1782742820960483000]'。
"""

from app.services.session_service import _strip_dialog_tag


def test_strips_nanosecond_tag_after_ascii():
    assert _strip_dialog_tag("hi[1782742820960483000]") == "hi"


def test_strips_nanosecond_tag_after_chinese():
    assert _strip_dialog_tag("帮我设计一个简单的博客系统[1782892302613548000]") == "帮我设计一个简单的博客系统"


def test_preserves_short_bracketed_numbers():
    # 用户真实输入的短编号不应被误删（阈值 18 位）
    assert _strip_dialog_tag("see issue [123]") == "see issue [123]"
    assert _strip_dialog_tag("订单号[1234567890]") == "订单号[1234567890]"  # 10 位


def test_preserves_non_trailing_brackets():
    # 仅剥离“末尾”的标记，行中的长数字串不动
    assert _strip_dialog_tag("值是[123456789012345678]注意") == "值是[123456789012345678]注意"


def test_preserves_plain_and_empty():
    assert _strip_dialog_tag("普通文本") == "普通文本"
    assert _strip_dialog_tag("") == ""
    assert _strip_dialog_tag(None) == ""
