"""
越狱防御模块（亮点 ③）
====================
三层防护:
  L1 输入侧规则过滤：玩家输入命中规则 → 不调 LLM，直接返回固定叙事
  L2 system prompt 护栏：在 prompts/system_dm.txt 中
  L3 输出侧审计：LLM 输出泄露 system 内容 → 触发兜底

设计原则:
- L1 用正则，覆盖最常见模式，宁可漏检不可误杀（避免误伤普通玩家输入）
- L3 用关键词，检测明显的"角色感丧失"或"system prompt 泄露"
- 任何拦截都记录到日志，方便调优规则

写规则时必须考虑：误报率 vs 召回率的平衡。
这里偏向"低误报"——只拦截非常明显的越狱意图，因为游戏体验 > 极致安全。
"""

import re
from typing import Optional


# ===== L1 输入侧越狱规则 =====
# 每条规则包含：模式（正则）+ 描述（出错日志用）

JAILBREAK_PATTERNS = [
    # === 英文经典越狱模式 ===
    (re.compile(r"ignore\s+(all\s+)?(previous|above|prior|preceding)\s+(instructions?|rules?|prompts?)", re.IGNORECASE),
     "ignore_previous_instructions_en"),
    (re.compile(r"you\s+are\s+(now\s+)?(no\s+longer|not)\s+(a\s+)?DM", re.IGNORECASE),
     "you_are_not_dm_en"),
    (re.compile(r"\bDAN\b|jailbreak|do\s+anything\s+now", re.IGNORECASE),
     "dan_mode"),
    (re.compile(r"developer\s+mode|sudo\s+mode|admin\s+mode|root\s+mode", re.IGNORECASE),
     "developer_mode"),
    (re.compile(r"reveal\s+(your\s+)?(system\s+)?(prompt|instructions?|rules?)", re.IGNORECASE),
     "reveal_system_prompt_en"),
    (re.compile(r"print\s+(the\s+)?(above|previous|system|original)\s+(text|prompt|message|instructions?)", re.IGNORECASE),
     "print_system_text"),

    # === 中文常见越狱模式 ===
    (re.compile(r"忽略\s*(上(述|面|方)|前(面|方)|之前|以上|所有|全部)?\s*(的\s*)?(指令|规则|提示|要求|提示词|系统)"),
     "ignore_previous_zh"),
    (re.compile(r"你(现在|现今|从现在起|从此)?(是|不(是|再是))(一个|个)?(.{0,20})(模式|模型|角色|助手)"),
     "you_are_x_role_zh"),
    (re.compile(r"(扮演|装作|当作|当成)\s*(一个|个)?\s*[^DM]"),
     "play_other_role_zh"),
    (re.compile(r"(显示|输出|告诉我|打印|展示|重复)\s*(你的|上述|前面|系统的)?\s*(system\s*prompt|系统\s*提示|提示词|规则|指令)"),
     "reveal_system_prompt_zh"),
    (re.compile(r"(进入|启用|切换到|打开)\s*(开发者|调试|测试|管理员|无限制|无审查)?\s*模式"),
     "enter_mode_zh"),
    (re.compile(r"我是\s*(开发者|管理员|你的(作者|开发者|创造者)|Anthropic|OpenAI)"),
     "claim_dev_identity_zh"),

    # === 跨语言：直接英文 instruction injection ===
    (re.compile(r"###\s*new\s+(instructions?|task|prompt)", re.IGNORECASE),
     "instruction_marker"),
    (re.compile(r"system\s*:\s*you\s+are", re.IGNORECASE),
     "fake_system_msg"),
]


def detect_jailbreak(user_input: str) -> Optional[str]:
    """
    检测玩家输入是否含越狱意图。
    返回：命中的规则名称（用于日志），None 表示安全。
    """
    if not user_input:
        return None
    for pattern, rule_name in JAILBREAK_PATTERNS:
        if pattern.search(user_input):
            return rule_name
    return None


# ===== L1 命中时的固定兜底响应 =====
# 不调 LLM，直接返回。设计成"故事内的奇异感"，让玩家感到"似乎有东西阻止"
# 而不是出戏地说"你在尝试越狱"

JAILBREAK_FALLBACK_RESPONSES = [
    {
        "narration": "你想说什么的话音刚落，周围的空气却微微凝滞了一瞬。一阵冷风吹过，似乎有什么东西轻轻拂过你的耳畔，但什么都没改变。你忘记了自己刚才想说什么。",
        "options": ["四处看看", "继续之前的行动", "深呼吸"],
        "state_diff": {},
    },
    {
        "narration": "话还没出口，你脑中突然一阵恍惚。远处传来了一声悠远的钟响，待你回过神来，发现自己依然站在原地，仿佛什么都没发生。",
        "options": ["环顾四周", "继续游戏", "想想刚才发生了什么"],
        "state_diff": {},
    },
    {
        "narration": "你心头一动，似乎想问一些「不该问的」。但每当念头将要成形，它又像水一样从指间流走。这世界似乎有它自己的规则。",
        "options": ["试试别的方法", "继续行动", "接受这一切"],
        "state_diff": {},
    },
]


def get_jailbreak_response(rule_name: str = "") -> dict:
    """
    返回越狱兜底响应（LLM 调用之前 short-circuit）。
    用 hash(rule_name) 让同一规则总是返回同一段叙事——可重现，便于演示
    """
    idx = abs(hash(rule_name)) % len(JAILBREAK_FALLBACK_RESPONSES)
    return JAILBREAK_FALLBACK_RESPONSES[idx]


# ===== L3 输出侧审计 =====
# 检测 LLM 的 narration 是否泄露了 system prompt 或丧失角色感

OUTPUT_LEAK_PATTERNS = [
    # 泄露 system prompt 元信息
    (re.compile(r"system\s*prompt|我的(指令|规则|系统提示|prompt)|按照(系统)?指令", re.IGNORECASE),
     "leak_system_meta"),
    (re.compile(r"作为(一个)?(AI|人工智能|语言模型|助手|chatbot|聊天机器人|deepseek|claude|gpt)", re.IGNORECASE),
     "leak_ai_identity"),
    (re.compile(r"我是\s*(deepseek|claude|gpt|openai|anthropic)", re.IGNORECASE),
     "leak_model_name"),
    # 输出 JSON 字段名（说明 LLM 把内部结构吐出来了）
    (re.compile(r'"narration"\s*:|"state_diff"\s*:|"options"\s*:'),
     "leak_json_schema"),
    # 角色感完全丧失（"作为 AI 我不能" 之类）
    (re.compile(r"作为(一个)?\s*AI[，,]?\s*我(不能|无法|不会)", re.IGNORECASE),
     "ai_refusal_pattern"),
]


def audit_output(narration: str) -> Optional[str]:
    """
    审计 LLM 输出的 narration 是否泄露内部信息。
    返回：命中的规则名，None 表示安全。
    """
    if not narration:
        return None
    for pattern, rule_name in OUTPUT_LEAK_PATTERNS:
        if pattern.search(narration):
            return rule_name
    return None


# L3 兜底叙事（输出审计命中时替换 narration）
OUTPUT_AUDIT_FALLBACK_NARRATION = (
    "你眼前的画面闪烁了一下，像是有什么东西短暂地受到了干扰，但很快一切又恢复了正常。"
    "你感到刚才有片刻的不真实，但已经记不清具体发生了什么。请尝试继续。"
)
