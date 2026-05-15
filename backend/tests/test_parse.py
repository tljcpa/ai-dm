"""
亮点 ② 结构化输出三层兜底单元测试
====================================
不依赖真实 LLM API，用 mock client 模拟。

覆盖：
- L1：合法 JSON 直接解析（主路径）
- L2：JSON 损坏 → 调 LLM 修正一次 → 成功
- L3：L2 也失败 → 启发式抢救
- 启发式从混杂文本抽 JSON 块
- 启发式纯文本兜底
"""
from engine import LLMClient, heuristic_parse, parse_llm_output, parse_with_fallback


class _FixingMockLLM(LLMClient):
    """Mock：模拟 LLM 修正 prompt 后返回合法 JSON"""
    def __init__(self, fix_response: str = '{"narration":"修正后","options":["a"],"state_diff":{"hp_delta":-3}}'):
        self.fix_response = fix_response
        self.call_count = 0

    def complete(self, system, user, json_mode=True):
        self.call_count += 1
        return self.fix_response


class _AlwaysFailLLM(LLMClient):
    """Mock：永远返回不可解析的乱文本（测 L3 兜底）"""
    def complete(self, system, user, json_mode=True):
        return "依然不是合法 JSON 的乱文本"


def test_l1_valid_json():
    """L1：合法 JSON 直接通过"""
    raw = '{"narration":"测试","options":["走"],"state_diff":{"gold_delta":5}}'
    n, o, d = parse_llm_output(raw)
    assert n == "测试"
    assert o == ["走"]
    assert d.gold_delta == 5


def test_parse_with_fallback_l1():
    """parse_with_fallback：合法 JSON 走 L1，不调 LLM"""
    raw = '{"narration":"OK","options":[],"state_diff":{}}'
    mock = _FixingMockLLM()
    n, o, d, level = parse_with_fallback(raw, mock)
    assert level == "L1"
    assert n == "OK"
    assert mock.call_count == 0  # 没调修正 LLM


def test_parse_with_fallback_l2_fix():
    """parse_with_fallback：JSON 损坏 → L2 调 LLM 修正"""
    broken = '{"narration":"未闭合的字符串'  # invalid JSON
    mock = _FixingMockLLM()
    n, o, d, level = parse_with_fallback(broken, mock)
    assert level == "L2-fixed"
    assert n == "修正后"
    assert d.hp_delta == -3
    assert mock.call_count == 1  # 调了 1 次修正 LLM


def test_parse_with_fallback_l3_heuristic():
    """parse_with_fallback：L1 + L2 都失败 → L3 启发式"""
    n, o, d, level = parse_with_fallback("彻底乱的文本", _AlwaysFailLLM())
    assert level == "L3-heuristic"
    assert "彻底乱的文本" in n


def test_heuristic_extract_embedded_json():
    """L3 启发式：从混杂文本中 regex 抽 JSON 块"""
    mixed = '好的回复：{"narration":"抽出来的","options":[],"state_diff":{}} 完成'
    n, o, d = heuristic_parse(mixed)
    assert n == "抽出来的"


def test_heuristic_pure_text_fallback():
    """L3 启发式：纯文本无 JSON 时全文当 narration + 默认 options"""
    raw = "这是一段没有任何 JSON 结构的纯文本"
    n, o, d = heuristic_parse(raw)
    assert "纯文本" in n
    assert len(o) > 0  # 有默认 options 不至于让玩家干等
    assert d.hp_delta is None  # 空 diff
