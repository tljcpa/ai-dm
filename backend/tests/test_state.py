"""
游戏状态测试
============
覆盖：
- default_state() 初始合理
- apply_diff 的边界处理（HP/MP/金币钳制、物品增删 silently-ignore）
- turn_count 自增
- state 序列化/反序列化对称（JSON roundtrip）
"""
from state import GameState, StateDiff, apply_diff, default_state


def test_default_state_sensible():
    """新存档的初始状态合理"""
    s = default_state()
    assert s.player.hp == 100 and s.player.max_hp == 100
    assert s.player.mp == 20 and s.player.max_mp == 20
    assert s.player.level == 1
    assert s.turn_count == 0
    assert s.scene.location == "村庄广场"
    assert "旅店老板" in s.scene.present_npcs
    assert s.long_term_summary == ""


def test_apply_diff_hp_clamp_low():
    """HP 钳制在 0（不能为负）—— 即使 LLM 想搞死玩家也不会真死到 -100"""
    s = default_state()
    new_s = apply_diff(s, StateDiff(hp_delta=-200))
    assert new_s.player.hp == 0


def test_apply_diff_hp_clamp_high():
    """HP 钳制在 max_hp（治疗不超上限）"""
    s = default_state()
    s.player.hp = 50
    new_s = apply_diff(s, StateDiff(hp_delta=200))
    assert new_s.player.hp == 100


def test_apply_diff_gold_no_negative():
    """金币不能为负（即使 LLM 让玩家欠债也不会负）"""
    s = default_state()
    new_s = apply_diff(s, StateDiff(gold_delta=-999))
    assert new_s.player.gold == 0


def test_apply_diff_inventory_add():
    """物品增加"""
    s = default_state()
    new_s = apply_diff(s, StateDiff(add_items=["剑", "盾"]))
    assert "剑" in new_s.player.inventory
    assert "盾" in new_s.player.inventory


def test_apply_diff_inventory_remove_existing():
    """删除存在的物品"""
    s = default_state()
    s.player.inventory = ["剑", "盾"]
    new_s = apply_diff(s, StateDiff(remove_items=["剑"]))
    assert "剑" not in new_s.player.inventory
    assert "盾" in new_s.player.inventory


def test_apply_diff_inventory_remove_nonexistent_silent():
    """删除不存在的物品应静默忽略，不抛异常（D-007 防幻觉设计）"""
    s = default_state()
    new_s = apply_diff(s, StateDiff(remove_items=["不存在的物品"]))
    # 没异常即通过
    assert new_s.player.inventory == s.player.inventory


def test_apply_diff_location_switch():
    """新场景切换"""
    s = default_state()
    new_s = apply_diff(s, StateDiff(
        new_location="沉睡巨龙旅店",
        new_scene_description="温暖的火光摇曳",
        new_present_npcs=["旅店老板"],
    ))
    assert new_s.scene.location == "沉睡巨龙旅店"
    assert new_s.scene.present_npcs == ["旅店老板"]


def test_apply_diff_turn_count_increment():
    """每次 apply_diff 回合数 +1"""
    s = default_state()
    new_s = apply_diff(s, StateDiff())
    assert new_s.turn_count == s.turn_count + 1


def test_state_json_roundtrip():
    """state 序列化 → JSON → 反序列化对称（GameSession 持久化的核心）"""
    s = default_state()
    s.player.inventory = ["神秘银币", "麦酒"]
    s.story_flags = {"met_innkeeper": True}
    json_str = s.model_dump_json()
    restored = GameState.model_validate_json(json_str)
    assert restored.player.inventory == s.player.inventory
    assert restored.story_flags == s.story_flags
    assert restored.scene.location == s.scene.location
