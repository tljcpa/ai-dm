"""
提示词管理
==========
- 所有 prompt 实物存在 prompts/*.txt 文件，便于版本控制、diff、面试时翻给面试官看
- NPC 角色卡存在 prompts/npc_cards/*.json，prompt 注入时按 present_npcs 加载对应卡片
- 世界观文档在 world_lore/*.txt，RAG 检索后注入（亮点 ⑤）
- 本模块负责加载、缓存、注入 state 拼装最终 prompt

亮点 ① NPC 一致性三层注入：
  L1 角色卡（静态）：load_npc_card() + format_npc_card_for_prompt()
  L2 长期摘要（动态）：在 engine.py 的 summarize_history() 生成，注入到 state.long_term_summary
  L3 短期对话窗口（滑动）：state.recent_history

亮点 ⑤ 世界观 RAG：
  set_rag_index() 由 main.py startup 注入；build_dm_prompt 自动检索 top-3 注入
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

from state import GameState

# 由 main.py startup 注入；None 表示 RAG 未启用
_rag_index: Optional["RAGIndex"] = None  # noqa: F821 (避免在模块导入时强制 import rag)


def set_rag_index(idx) -> None:
    """注入 RAG 索引（亮点 ⑤）。idx 应为 rag.RAGIndex 实例或 None。"""
    global _rag_index
    _rag_index = idx


PROMPTS_DIR = Path(__file__).parent / "prompts"
NPC_CARDS_DIR = PROMPTS_DIR / "npc_cards"


@lru_cache(maxsize=32)
def load_prompt(name: str) -> str:
    """
    从 prompts/ 加载 prompt 实物。
    @lru_cache 让生产环境只读一次文件——开发期改完 prompt 需要重启服务才生效，这是接受的代价。
    """
    path = PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=128)
def _load_card_by_filename(filename: str) -> dict:
    """按文件名直接加载卡片（不经过 alias 匹配）。"""
    path = NPC_CARDS_DIR / filename
    return json.loads(path.read_text(encoding="utf-8"))


def load_npc_card(name: str) -> Optional[dict]:
    """
    加载 NPC 角色卡。
    匹配规则：
      1. 先按 `{name}.json` 文件直接找
      2. 否则遍历所有卡片，看 name 或 aliases 是否匹配
      3. 找不到返回 None（LLM 会自由扮演这个未知 NPC）
    """
    if not NPC_CARDS_DIR.exists():
        return None
    # 1) 直接文件名匹配
    direct_path = NPC_CARDS_DIR / f"{name}.json"
    if direct_path.exists():
        return _load_card_by_filename(f"{name}.json")
    # 2) 遍历找 alias
    for card_path in NPC_CARDS_DIR.glob("*.json"):
        card = _load_card_by_filename(card_path.name)
        if name == card.get("name") or name in card.get("aliases", []):
            return card
    return None


def format_npc_card_for_prompt(card: dict) -> str:
    """把 NPC 卡片格式化成 prompt 文本块。"""
    lines = [f"◆ {card['name']}"]
    if card.get("aliases"):
        lines.append(f"  别名: {', '.join(card['aliases'])}")
    lines.append(f"  人格: {card['persona']}")
    lines.append(f"  说话风格: {card['speech_style']}")
    if card.get("knowledge_bounds"):
        lines.append("  知识边界:")
        for item in card["knowledge_bounds"]:
            lines.append(f"    · {item}")
    lines.append(f"  与玩家关系: {card['relationship_to_player']}")
    if card.get("secret"):
        lines.append(f"  不主动透露的过去: {card['secret']}")
    if card.get("dont_do"):
        lines.append("  绝对不要这么演:")
        for item in card["dont_do"]:
            lines.append(f"    · {item}")
    return "\n".join(lines)


def build_dm_prompt(state: GameState, user_input: str) -> Tuple[str, str]:
    """
    构造给 LLM 的 (system_prompt, user_message) 二元组。

    设计：
    - system_prompt 来自 prompts/system_dm.txt（角色、规则、输出格式）
    - user_message 包含：
        state 紧凑表示
        + L1 NPC 卡片（亮点 ①）
        + RAG 世界观检索（亮点 ⑤，用本回合输入做 query 召回 top-3）
        + L2 长期摘要（亮点 ①）
        + L3 短期对话（亮点 ①）
        + 玩家本次输入
    - state 写在 user 侧（每回合变化）：保持 system_prompt 静态便于 prompt cache

    亮点 ① + ⑤ 在这里拼装。
    """
    system_prompt = load_prompt("system_dm")

    # 紧凑序列化当前 state（避免冗余字段消耗 token）
    state_block = (
        f"【当前游戏状态】\n"
        f"- 回合数: {state.turn_count}\n"
        f"- 玩家: HP {state.player.hp}/{state.player.max_hp}, "
        f"MP {state.player.mp}/{state.player.max_mp}, "
        f"金币 {state.player.gold}, 等级 {state.player.level}\n"
        f"- 物品: {state.player.inventory if state.player.inventory else '（空）'}\n"
        f"- 当前位置: {state.scene.location}\n"
        f"- 场景描述: {state.scene.description}\n"
        f"- 在场 NPC: {state.scene.present_npcs if state.scene.present_npcs else '（无）'}\n"
        f"- 剧情标记: {state.story_flags if state.story_flags else '（无）'}\n"
    )

    # ===== L1 NPC 角色卡注入 =====
    # 给在场每个有卡片的 NPC 注入完整资料，让 LLM 严格按卡片演
    npc_blocks = []
    for npc_name in state.scene.present_npcs:
        card = load_npc_card(npc_name)
        if card:
            npc_blocks.append(format_npc_card_for_prompt(card))
    if npc_blocks:
        state_block += "\n【在场 NPC 详细资料】（严格按这些资料扮演，不要让 NPC 越界）\n"
        state_block += "\n\n".join(npc_blocks) + "\n"

    # ===== 亮点 ⑤ RAG 世界观检索注入 =====
    # 用本回合玩家输入做 query，从 world_lore/*.txt 召回 top-3 相关文档
    # 若 RAG 未启用（_rag_index is None）则跳过——优雅降级
    if _rag_index is not None and user_input.strip():
        try:
            from rag import format_rag_results_for_prompt
            results = _rag_index.query(user_input, top_k=3)
            if results:
                rag_block = format_rag_results_for_prompt(results)
                state_block += "\n" + rag_block + "\n"
        except Exception as e:
            # RAG 失败不影响主回合（如智谱 API 短暂故障）
            print(f"[rag] query failed: {type(e).__name__}: {e}")

    # ===== L2 长期记忆摘要注入 =====
    if state.long_term_summary:
        state_block += f"\n【长期剧情摘要】（已经发生过的关键事件，不要遗忘）\n{state.long_term_summary}\n"

    # ===== L3 短期对话窗口注入 =====
    if state.recent_history:
        history_lines = []
        for turn in state.recent_history[-8:]:  # 最近 8 轮（再多会过长）
            history_lines.append(f"  玩家: {turn.get('user', '')}")
            dm_text = turn.get("dm", "")
            history_lines.append(f"  DM: {dm_text[:150]}{'...' if len(dm_text) > 150 else ''}")
        state_block += "\n【最近对话】\n" + "\n".join(history_lines) + "\n"

    user_message = f"{state_block}\n【玩家本回合的行动】\n{user_input}\n\n请严格按 JSON 格式回复。"

    return system_prompt, user_message


# ===== L2 长期记忆摘要的 prompt =====

SUMMARIZE_SYSTEM_PROMPT = """你是一个游戏剧情摘要员。任务：把游戏对话历史浓缩成简洁的关键事件记录。

要求：
1. 用第三人称写（"玩家"而不是"你"）
2. 只记录关键事实：玩家做的重要选择、获得/失去的物品、人物关系变化、剧情线索
3. 不要修辞、不要文学化、不要复述对话内容
4. 中文，3-5 句话，每句不超过 30 字
5. 直接输出摘要文本，不要任何前缀（不要"摘要:"之类）"""


def build_summary_prompt(state: GameState) -> Tuple[str, str]:
    """构造摘要任务的 (system, user) prompt。"""
    history_lines = []
    for turn in state.recent_history:
        history_lines.append(f"玩家说: {turn.get('user', '')}")
        history_lines.append(f"DM 回复: {turn.get('dm', '')}")
    history_text = "\n".join(history_lines)

    previous_summary = state.long_term_summary or "（暂无）"
    user_message = (
        f"【已有的长期摘要】\n{previous_summary}\n\n"
        f"【最近发生的对话历史】\n{history_text}\n\n"
        f"请把上面已有摘要 + 最近对话 综合后，重写成新的简洁摘要。"
    )
    return SUMMARIZE_SYSTEM_PROMPT, user_message
