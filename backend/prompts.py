"""
提示词管理
==========
- 所有 prompt 实物存在 prompts/*.txt 文件，便于版本控制、diff、面试时翻给面试官看
- 本模块负责加载、缓存、注入 state 拼装最终 prompt
- Day 2 会扩展：NPC 角色卡注入、长期摘要注入、越狱防御层
"""

from functools import lru_cache
from pathlib import Path

from state import GameState


PROMPTS_DIR = Path(__file__).parent / "prompts"


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


def build_dm_prompt(state: GameState, user_input: str) -> tuple[str, str]:
    """
    构造给 LLM 的 (system_prompt, user_message) 二元组。

    设计：
    - system_prompt 来自 prompts/system_dm.txt（角色、规则、输出格式）
    - user_message 包含：当前 state 的紧凑表示 + 玩家本次输入
    - 把 state 拼到 user_message 而不是 system_prompt 中：
      因为 state 每回合都变，写在 user 侧避免污染 system（也利于 prompt cache）

    Day 2 会在这里插入：
      - NPC 角色卡注入（present_npcs 中每个 NPC 的角色卡）
      - 长期记忆摘要（state.long_term_summary）
      - 短期对话历史（state.recent_history）
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

    if state.long_term_summary:
        state_block += f"\n【长期记忆摘要】\n{state.long_term_summary}\n"

    if state.recent_history:
        history_lines = []
        for turn in state.recent_history[-5:]:
            history_lines.append(f"  玩家: {turn.get('user', '')}")
            history_lines.append(f"  你的回复: {turn.get('dm', '')[:120]}...")
        state_block += f"\n【最近对话】\n" + "\n".join(history_lines) + "\n"

    user_message = f"{state_block}\n【玩家本回合的行动】\n{user_input}\n\n请按 JSON 格式回复。"

    return system_prompt, user_message
