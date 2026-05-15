"""
RAG 召回率评估（亮点 ⑤）
=========================
需要真实智谱 embedding API key 才能跑。
CI 没设 ZHIPU_API_KEY 环境变量时自动跳过——pytest.ini 的 requires_api 标记 + skipif。

本地手动跑（带数据）：
  cd backend && source venv/bin/activate
  pytest tests/test_rag_eval.py -v -s

输出示例：
  Top-1 召回率: 9/10 = 90%

10 个 ground truth 设计原则：
- query 模拟玩家的自然语言（不是关键字）
- expected_doc_id_substring 是文档主题词
- 覆盖多种类型：地理 / 历史 / 人物 / 经济 / 魔法
"""
import os
from pathlib import Path

import pytest


GROUND_TRUTH = [
    # (玩家自然语言, 期望召回的文档名子串)
    ("我想去北边的矿洞里看看",                  "mine_noises"),
    ("矿洞最近怎么了，有没有怪声音",            "mine_noises"),
    ("我问卖菜老妇关于她的家人",                "missing_adventurer"),
    ("我向铁匠询问传说中的剑",                  "hero_blade"),
    ("绝霜剑是什么东西",                        "hero_blade"),
    ("这村子里供奉的是什么神",                  "three_gods"),
    ("我想学魔法",                              "magic_basics"),
    ("黑森林深处住着什么",                      "dark_forest"),
    ("一晚旅店住宿大概多少钱",                  "currency"),
    ("龙之战是怎么回事",                        "dragon_war"),
]


@pytest.mark.requires_api
@pytest.mark.skipif(
    not os.getenv("ZHIPU_API_KEY"),
    reason="需要 ZHIPU_API_KEY 环境变量（CI 默认跳过）",
)
def test_rag_top1_recall_rate():
    """
    Top-1 召回率 >= 80%。

    实测基线：90%（9/10）。
    < 80% 说明嵌入质量或文档分块出了问题，需要排查。
    """
    from rag import ZhipuEmbedder, build_world_lore_index

    embedder = ZhipuEmbedder(api_key=os.environ["ZHIPU_API_KEY"])
    backend_dir = Path(__file__).parent.parent
    idx = build_world_lore_index(
        backend_dir / "world_lore",
        backend_dir / "data" / "rag_index.pkl",
        embedder,
    )

    hits = 0
    misses = []
    for query, expected_substr in GROUND_TRUTH:
        results = idx.query(query, top_k=1)
        top_doc = results[0][0] if results else "(no_result)"
        score = results[0][2] if results else 0.0
        if expected_substr in top_doc:
            hits += 1
            print(f"  HIT  [{score:.2f}] q={query!r} → {top_doc}")
        else:
            misses.append((query, expected_substr, top_doc, score))
            print(f"  MISS [{score:.2f}] q={query!r} expected={expected_substr!r} got={top_doc}")

    recall = hits / len(GROUND_TRUTH)
    print(f"\nTop-1 召回率: {hits}/{len(GROUND_TRUTH)} = {recall*100:.0f}%")
    if misses:
        print("漏召回明细：")
        for q, exp, got, sc in misses:
            print(f"  '{q}' 期望 {exp} 实际 {got} ({sc:.2f})")

    assert recall >= 0.8, f"召回率 {recall*100:.0f}% 低于 80% 阈值（实测基线 90%）"
