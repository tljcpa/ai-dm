"""
游戏状态结构
============
- 用 Pydantic 2.x 定义游戏内业务对象（不是数据库表）
- GameState 是单一根，所有玩家相关变化都通过它
- 提供 default_state() 初始化新存档
- 序列化用 model_dump_json / model_validate_json，存进 GameSession.game_state_json

设计思路：
- "状态"和"叙事"分开：state 是结构化数据（玩家HP、物品、场景flag），叙事是文本流
- LLM 每回合返回结构化的 state_diff，由代码 apply，避免幻觉污染状态
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class PlayerStats(BaseModel):
    """玩家属性。最简版本，可扩展。"""
    hp: int = 100
    max_hp: int = 100
    mp: int = 20
    max_mp: int = 20
    level: int = 1
    gold: int = 10
    inventory: List[str] = Field(default_factory=list)


class Scene(BaseModel):
    """当前所处场景。"""
    location: str = "村庄广场"
    description: str = "你站在一个安静的小村庄广场上，午后的阳光透过老榕树洒下。"
    # 当前场景中存在的 NPC（只是名字列表，详细信息由角色卡管理）
    present_npcs: List[str] = Field(default_factory=list)


class GameState(BaseModel):
    """
    游戏的完整状态根。
    设计原则：所有"会随时间变化的事实"都进这里，prompt 注入时整个序列化送给 LLM。
    """
    player: PlayerStats = Field(default_factory=PlayerStats)
    scene: Scene = Field(default_factory=Scene)
    # 剧情 flags：用 dict 而非固定字段，灵活记录任意剧情进度
    # 例：{"met_blacksmith": True, "found_secret_door": False}
    story_flags: Dict[str, bool] = Field(default_factory=dict)
    # 玩家的回合数
    turn_count: int = 0
    # 长期记忆摘要（Day 2 NPC 一致性亮点会用到）
    long_term_summary: str = ""
    # 最近 N 轮对话历史（短期窗口，Day 2 限制为 5-10 条）
    recent_history: List[Dict[str, str]] = Field(default_factory=list)


def default_state() -> GameState:
    """新存档的初始状态。"""
    return GameState(
        player=PlayerStats(),
        scene=Scene(
            location="村庄广场",
            description="你是一名新到此地的冒险者。村庄广场上人来人往，远处的山脉若隐若现。",
            present_npcs=["旅店老板", "卖菜的老妇"],
        ),
        story_flags={},
        turn_count=0,
        long_term_summary="",
        recent_history=[],
    )


class StateDiff(BaseModel):
    """
    LLM 单回合返回的状态变更（结构化输出的一部分）。
    所有字段都是可选——LLM 只填它认为需要变的部分。
    """
    hp_delta: Optional[int] = None
    mp_delta: Optional[int] = None
    gold_delta: Optional[int] = None
    add_items: List[str] = Field(default_factory=list)
    remove_items: List[str] = Field(default_factory=list)
    new_location: Optional[str] = None
    new_scene_description: Optional[str] = None
    new_present_npcs: Optional[List[str]] = None
    set_flags: Dict[str, bool] = Field(default_factory=dict)


def apply_diff(state: GameState, diff: StateDiff) -> GameState:
    """
    把 LLM 返回的 state_diff 应用到当前 state，返回新 state。
    所有改动都由代码做，LLM 只声明"想变什么"——这是防幻觉的关键。
    """
    # Pydantic 2.x: model_copy(deep=True) 拿到深拷贝
    new_state = state.model_copy(deep=True)

    if diff.hp_delta is not None:
        new_state.player.hp = max(0, min(new_state.player.max_hp, new_state.player.hp + diff.hp_delta))
    if diff.mp_delta is not None:
        new_state.player.mp = max(0, min(new_state.player.max_mp, new_state.player.mp + diff.mp_delta))
    if diff.gold_delta is not None:
        new_state.player.gold = max(0, new_state.player.gold + diff.gold_delta)

    for item in diff.add_items:
        new_state.player.inventory.append(item)
    for item in diff.remove_items:
        if item in new_state.player.inventory:
            new_state.player.inventory.remove(item)

    if diff.new_location is not None:
        new_state.scene.location = diff.new_location
    if diff.new_scene_description is not None:
        new_state.scene.description = diff.new_scene_description
    if diff.new_present_npcs is not None:
        new_state.scene.present_npcs = diff.new_present_npcs

    for flag_key, flag_val in diff.set_flags.items():
        new_state.story_flags[flag_key] = flag_val

    new_state.turn_count += 1
    return new_state
