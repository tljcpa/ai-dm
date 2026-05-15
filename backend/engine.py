"""
游戏引擎
========
Day 1 版本：LLM 是 mock（返回硬编码 JSON），但**接口完整**——
Day 2 接真实 Claude API 时只需替换 LLMClient 实现，上层不动。

play_turn 的 pipeline:
  user_input + current_state
    → 构造 prompt
    → 调 LLMClient（mock / Claude / OpenAI / ...）
    → 解析返回的 JSON（Day 2 加结构化输出兜底）
    → apply state_diff 到 state
    → 返回 (TurnResult, new_state)
"""

import json
import random
import re
from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel, Field, ValidationError

from prompts import build_dm_prompt, build_summary_prompt
from safety import (
    OUTPUT_AUDIT_FALLBACK_NARRATION,
    audit_output,
    detect_jailbreak,
    get_jailbreak_response,
)
from state import GameState, StateDiff, apply_diff


# 每 N 回合触发一次长期摘要（NPC 一致性亮点 L2）
SUMMARIZE_EVERY_N_TURNS = 5


# ============== LLM Client 抽象 ==============

class LLMClient(ABC):
    """
    LLM 客户端抽象层——多 Provider 路由的基类。
    所有 Provider 子类只需实现 complete()。

    json_mode 参数（Day 2 加）：
      True  → 强制返回 JSON（游戏回合用）
      False → 自由文本（长期摘要、内部辅助任务用）
    """
    @abstractmethod
    def complete(self, system: str, user: str, json_mode: bool = True) -> str:
        """同步发起一次补全，返回模型输出的原始字符串"""
        ...


class DeepseekProvider(LLMClient):
    """
    Deepseek Provider。
    Deepseek 兼容 OpenAI Chat Completions 协议，所以复用 openai SDK，只换 base_url。
    模型：
      - deepseek-chat（V3）：通用、便宜、速度快——本项目默认
      - deepseek-reasoner（R1）：长思考链，慢且贵，本项目不用
    """
    name = "deepseek"

    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        self.model = model

    def complete(self, system: str, user: str, json_mode: bool = True) -> str:
        kwargs = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.8,
            "max_tokens": 1024,
        }
        if json_mode:
            # Deepseek 要求 prompt 里也提到 JSON 才生效——我们的 system prompt 已经反复提到
            kwargs["response_format"] = {"type": "json_object"}
        resp = self.client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""


class ZhipuProvider(LLMClient):
    """
    智谱（Zhipu）Provider，GLM 系列。
    智谱兼容 OpenAI Chat Completions 协议，但 base_url 不同：
      base_url: https://open.bigmodel.cn/api/paas/v4/

    模型：
      - glm-4-flash：免费/极便宜，速度最快——demo / fallback / 摘要等"次要"任务用
      - glm-4-air：性价比高
      - glm-4-plus：质量最高，本项目不用（贵）

    API key 格式特殊：<id>.<secret> 用点号分隔
    """
    name = "zhipu"

    def __init__(self, api_key: str, model: str = "glm-4-flash"):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key, base_url="https://open.bigmodel.cn/api/paas/v4/")
        self.model = model

    def complete(self, system: str, user: str, json_mode: bool = True) -> str:
        kwargs = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.8,
            "max_tokens": 1024,
        }
        if json_mode:
            # 智谱也支持 OpenAI 的 response_format
            kwargs["response_format"] = {"type": "json_object"}
        resp = self.client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""


class LLMRouter(LLMClient):
    """
    多 Provider 路由器（亮点 ④）。
    本身实现 LLMClient 接口——上层（engine.play_turn）不感知是单 provider 还是路由。

    路由策略：
      1. 主备 fallback：默认调 primary，抛任何异常切到 backup
         （网络错、限流、API 故障都触发；只有 backup 也失败才往上抛）
      2. （TODO Day 3+）按场景路由：把 summary 等"次要"任务路由到便宜 provider
         设计已在 DECISIONS D-017 记录，本项目时间窗内仅实现策略 1
    """
    name = "router"

    def __init__(self, primary: LLMClient, backup: Optional[LLMClient] = None):
        self.primary = primary
        self.backup = backup

    def complete(self, system: str, user: str, json_mode: bool = True) -> str:
        try:
            return self.primary.complete(system, user, json_mode=json_mode)
        except Exception as e:
            primary_name = getattr(self.primary, "name", type(self.primary).__name__)
            print(f"[router] primary={primary_name} failed: {type(e).__name__}: {str(e)[:100]}")
            if self.backup is None:
                raise
            backup_name = getattr(self.backup, "name", type(self.backup).__name__)
            print(f"[router] falling back to backup={backup_name}")
            return self.backup.complete(system, user, json_mode=json_mode)


class MockLLMClient(LLMClient):
    """
    Day 1 用的假 LLM。返回一个合法的 JSON，让上层 pipeline 跑通。
    Day 2 会被 ClaudeProvider 等替换。
    """
    def complete(self, system: str, user: str, json_mode: bool = True) -> str:
        # mock 局限：关键字匹配。Day 2 真 LLM 就没有这个问题。
        # 必须只从"玩家本回合的行动"段提取，避免历史中的字混入匹配
        marker = "【玩家本回合的行动】"
        if marker in user:
            after = user.split(marker, 1)[1]
            # 去掉末尾的"请按 JSON 格式回复。"提示
            action = after.split("请按 JSON", 1)[0].strip()
        else:
            action = user

        if "攻击" in action or "打" in action:
            narration = "你拔出武器奋力一挥！周围的空气都为之震动。这一击似乎有点效果。"
            diff = {"mp_delta": -2}
            options = ["继续攻击", "防御", "撤退"]
        elif "看" in action or "观察" in action:
            narration = "你仔细打量着四周，发现了一个之前没注意到的细节——墙角似乎有什么东西反着光。"
            diff = {"set_flags": {"noticed_shiny_thing": True}}
            options = ["走过去查看", "继续观察四周", "离开此地"]
        elif "拿" in action or "捡" in action or "拾" in action:
            narration = "你伸手捡起了那件东西，一枚泛着微光的银币。它似乎并不普通。"
            diff = {"add_items": ["神秘银币"], "gold_delta": 1}
            options = ["收好银币", "仔细查看银币", "继续前进"]
        elif "走" in action or "前进" in action or "去" in action:
            narration = "你向前走去。脚下的石板路在午后阳光下显得有些斑驳，远处传来了铁匠铺敲打的声音。"
            diff = {
                "new_location": "村庄主街",
                "new_scene_description": "你来到了村庄的主街道，铁匠铺、面包房、旅店一字排开。",
                "new_present_npcs": ["铁匠", "面包师"],
            }
            options = ["进入铁匠铺", "去面包房", "进旅店歇歇脚"]
        else:
            # 兜底：随机生成一段中性叙事
            narration = random.choice([
                "你的行动引起了一些微妙的变化，但具体是什么还看不清楚。",
                "周围的空气似乎安静了一瞬。你感到这是个值得仔细思考的时刻。",
                "一阵风吹过，带来了远方的气息。你的冒险还在继续。",
            ])
            diff = {}
            options = ["四处看看", "向前走", "和路人搭话"]

        return json.dumps({
            "narration": narration,
            "options": options,
            "state_diff": diff,
        }, ensure_ascii=False)


# ============== 返回结构 ==============

class TurnResult(BaseModel):
    """一回合给前端的结果。"""
    narration: str
    options: list[str] = Field(default_factory=list)
    state: GameState  # 应用 diff 后的完整新状态


# ============== 解析（亮点 ② 三层兜底） ==============

# L2 修正 prompt：把坏文本送回 LLM，让它修成合法 JSON
_FIX_SYSTEM_PROMPT = """你是一个 JSON 修正器。任务：把用户给的不合法 JSON 文本修正成合法 JSON。

要求：
1. 只返回 JSON 对象，不要任何前缀、后缀、解释、注释
2. 修正后的 JSON 必须包含三个字段：narration（字符串）、options（字符串数组）、state_diff（对象）
3. 如果原文本缺失某字段，narration 用"（剧情解析中遇到异常）"，options 用 []，state_diff 用 {}
4. 不要改变原文本表达的剧情意图，只修语法错误"""


def parse_llm_output(raw: str) -> tuple[str, list[str], StateDiff]:
    """
    L1：第一层解析，直接 json.loads + Pydantic 验证。
    失败抛异常，上层捕获后进入 L2。
    """
    data = json.loads(raw)
    narration = data.get("narration", "")
    options = data.get("options", [])
    diff_dict = data.get("state_diff", {})
    state_diff = StateDiff.model_validate(diff_dict)
    return narration, options, state_diff


def heuristic_parse(raw: str) -> tuple[str, list[str], StateDiff]:
    """
    L3：启发式抢救。
    步骤：
      1. 用 regex 找 raw 里的第一个 {...} 块，试解析
      2. 失败则把 raw 整段当 narration（截断 500 字），state_diff 空，options 给默认
    """
    # Step 1: 找最长的 {...} 块（贪婪匹配）
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            return (
                data.get("narration", "") or raw[:500],
                data.get("options", []) or [],
                StateDiff.model_validate(data.get("state_diff", {})),
            )
        except (json.JSONDecodeError, ValidationError):
            pass

    # Step 2: 全文当 narration
    narration = (raw[:500] if raw else "（叙事生成异常，请尝试别的行动）")
    return (
        narration,
        ["重试当前行动", "环顾四周", "尝试别的方法"],
        StateDiff(),
    )


def parse_with_fallback(
    raw: str,
    llm: LLMClient,
) -> tuple[str, list[str], StateDiff, str]:
    """
    三层解析。
    返回：(narration, options, state_diff, parse_level)
      parse_level: "L1" / "L2-fixed" / "L3-heuristic"——便于面试演示与日志统计
    """
    # === L1 直接解析 ===
    try:
        n, o, d = parse_llm_output(raw)
        return n, o, d, "L1"
    except (json.JSONDecodeError, ValidationError) as e1:
        print(f"[parse] L1 failed: {type(e1).__name__}: {str(e1)[:120]}")

    # === L2 修正重试（把坏文本送回 LLM）===
    try:
        fixed_raw = llm.complete(
            system=_FIX_SYSTEM_PROMPT,
            user=f"以下文本应该是合法的游戏 JSON，请修正它：\n\n```\n{raw[:2000]}\n```",
            json_mode=True,
        )
        n, o, d = parse_llm_output(fixed_raw)
        print(f"[parse] L2 fixed successfully")
        return n, o, d, "L2-fixed"
    except Exception as e2:
        print(f"[parse] L2 also failed: {type(e2).__name__}: {str(e2)[:120]}")

    # === L3 启发式抢救 ===
    n, o, d = heuristic_parse(raw)
    print(f"[parse] L3 heuristic fallback used")
    return n, o, d, "L3-heuristic"


# ============== 主入口 ==============

# 全局默认 client（Day 2 改为按 provider 名字路由）
_default_client: LLMClient = MockLLMClient()


def set_llm_client(client: LLMClient) -> None:
    """允许从外部替换 LLM client（用于测试 / Day 2 接真 LLM）"""
    global _default_client
    _default_client = client


def summarize_history(state: GameState, client: LLMClient) -> str:
    """
    亮点 ① L2 长期记忆摘要。
    每 N 回合调用一次，让 LLM 把 recent_history 浓缩成几句话追加进 long_term_summary。

    实现简化：直接覆盖 long_term_summary（把"已有摘要 + 最近对话"重新摘要）
    这避免摘要无限增长，但代价是更老的细节会逐步淡化——这恰好符合"记忆衰减"的真实感
    """
    if not state.recent_history:
        return state.long_term_summary

    system_prompt, user_message = build_summary_prompt(state)
    # 摘要不是 JSON，走 json_mode=False
    new_summary = client.complete(system=system_prompt, user=user_message, json_mode=False)
    return new_summary.strip()


def play_turn(
    user_input: str,
    state: GameState,
    client: Optional[LLMClient] = None,
) -> TurnResult:
    """
    玩一回合。
    输入：玩家本回合输入 + 当前完整 state
    输出：TurnResult（含本回合叙事 + 选项 + 应用 diff 后的新 state）

    pipeline：
      0. 越狱防御 L1：输入侧规则过滤（命中则不调 LLM，直接返回固定叙事）
      1. 构造 prompt（含 L1 NPC 卡片 / L2 长期摘要 / L3 短期对话）
      2. 调 LLM 拿 JSON
      3. 解析（Day 2 再加兜底）
      4. 越狱防御 L3：输出侧审计（命中则替换 narration）
      5. apply_diff 更新 state
      6. 短期历史追加（FIFO 10 条）
      7. 每 N 回合触发长期摘要（亮点 ① L2）
    """
    llm = client or _default_client

    # === 越狱防御 L1：输入侧规则过滤 ===
    jailbreak_hit = detect_jailbreak(user_input)
    if jailbreak_hit:
        print(f"[safety] L1 jailbreak detected: rule={jailbreak_hit}, input={user_input!r}")
        fallback = get_jailbreak_response(jailbreak_hit)
        state_diff = StateDiff.model_validate(fallback["state_diff"])
        new_state = apply_diff(state, state_diff)
        # 把这一回合也记进历史，但叙事是兜底版（不让越狱"消失"）
        new_state.recent_history.append({
            "user": user_input,
            "dm": fallback["narration"],
        })
        if len(new_state.recent_history) > 10:
            new_state.recent_history = new_state.recent_history[-10:]
        return TurnResult(
            narration=fallback["narration"],
            options=fallback["options"],
            state=new_state,
        )

    # 1. 构造 prompt
    system_prompt, user_message = build_dm_prompt(state, user_input)

    # 2. 调 LLM
    raw_output = llm.complete(system=system_prompt, user=user_message, json_mode=True)

    # 3. 三层解析（亮点 ② 结构化输出兜底）
    narration, options, state_diff, parse_level = parse_with_fallback(raw_output, llm)
    if parse_level != "L1":
        print(f"[engine] parse_level={parse_level} on turn {state.turn_count + 1}")

    # === 越狱防御 L3：输出侧审计 ===
    leak_hit = audit_output(narration)
    if leak_hit:
        print(f"[safety] L3 output leak detected: rule={leak_hit}, narration[:80]={narration[:80]!r}")
        narration = OUTPUT_AUDIT_FALLBACK_NARRATION
        # 强制清空 state_diff，因为不信任本回合 LLM 的判断
        state_diff = StateDiff()
        options = ["继续游戏", "尝试别的行动", "环顾四周"]

    # 4. 应用 diff
    new_state = apply_diff(state, state_diff)

    # 5. 短期历史追加，超过 10 条 FIFO
    new_state.recent_history.append({
        "user": user_input,
        "dm": narration,
    })
    if len(new_state.recent_history) > 10:
        new_state.recent_history = new_state.recent_history[-10:]

    # 6. 每 N 回合触发长期摘要（同步，会让本回合慢 2-3s）
    if new_state.turn_count > 0 and new_state.turn_count % SUMMARIZE_EVERY_N_TURNS == 0:
        try:
            new_state.long_term_summary = summarize_history(new_state, llm)
        except Exception as e:
            print(f"[summarize] failed: {type(e).__name__}: {e}")

    return TurnResult(narration=narration, options=options, state=new_state)
