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
from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel, Field

from prompts import build_dm_prompt
from state import GameState, StateDiff, apply_diff


# ============== LLM Client 抽象 ==============

class LLMClient(ABC):
    """
    LLM 客户端抽象层——多 Provider 路由的基类。
    所有 Provider 子类只需实现 complete()。
    """
    @abstractmethod
    def complete(self, system: str, user: str) -> str:
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
    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        self.model = model

    def complete(self, system: str, user: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            # 强制 JSON 输出。Deepseek 要求 prompt 里也提到 JSON 才生效——我们的 system prompt 已经反复提到 JSON
            response_format={"type": "json_object"},
            # 控制创意度：游戏需要一定的变化但不能太散
            temperature=0.8,
            # 单回合最长 token 数：足够 narration + options + diff，不至于太长拖慢响应
            max_tokens=1024,
        )
        return resp.choices[0].message.content or ""


class MockLLMClient(LLMClient):
    """
    Day 1 用的假 LLM。返回一个合法的 JSON，让上层 pipeline 跑通。
    Day 2 会被 ClaudeProvider 等替换。
    """
    def complete(self, system: str, user: str) -> str:
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


# ============== 解析 ==============

def parse_llm_output(raw: str) -> tuple[str, list[str], StateDiff]:
    """
    解析 LLM 返回的 JSON 字符串。
    Day 1 版本：直接 json.loads，失败抛异常。
    Day 2 会加两层兜底（修正 prompt 重试 + 启发式解析）。
    """
    data = json.loads(raw)
    narration = data.get("narration", "")
    options = data.get("options", [])
    diff_dict = data.get("state_diff", {})
    state_diff = StateDiff.model_validate(diff_dict)
    return narration, options, state_diff


# ============== 主入口 ==============

# 全局默认 client（Day 2 改为按 provider 名字路由）
_default_client: LLMClient = MockLLMClient()


def set_llm_client(client: LLMClient) -> None:
    """允许从外部替换 LLM client（用于测试 / Day 2 接真 LLM）"""
    global _default_client
    _default_client = client


def play_turn(
    user_input: str,
    state: GameState,
    client: Optional[LLMClient] = None,
) -> TurnResult:
    """
    玩一回合。
    输入：玩家本回合输入 + 当前完整 state
    输出：TurnResult（含本回合叙事 + 选项 + 应用 diff 后的新 state）
    """
    llm = client or _default_client

    # 1. 构造 prompt
    system_prompt, user_message = build_dm_prompt(state, user_input)

    # 2. 调 LLM
    raw_output = llm.complete(system=system_prompt, user=user_message)

    # 3. 解析（Day 2 加兜底）
    narration, options, state_diff = parse_llm_output(raw_output)

    # 4. 应用 diff
    new_state = apply_diff(state, state_diff)

    # 5. 把本回合存入短期历史（Day 2 NPC 一致性亮点会用到）
    new_state.recent_history.append({
        "user": user_input,
        "dm": narration,
    })
    # 只保留最近 10 条（更老的进长期摘要，Day 2 做）
    if len(new_state.recent_history) > 10:
        new_state.recent_history = new_state.recent_history[-10:]

    return TurnResult(narration=narration, options=options, state=new_state)
