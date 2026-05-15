"""
RAG 模块（亮点 ⑤）
================
世界观知识检索：玩家每回合输入作为 query，从 15 段世界观文档中召回 top-3 注入 prompt。

设计选择（详见 DECISIONS D-020）：
- 不用 ChromaDB / Qdrant 等向量库——15 个文档用内存 numpy 余弦相似度已够
- 嵌入用智谱 embedding-3（2048 维）——本机内存装不下本地 BGE 模型
- 持久化用 pickle 缓存：首次启动调智谱嵌入 15 个文档，后续启动从磁盘读

为什么不用 ChromaDB：
- 减少依赖（最小依赖原则，和 D-006 / D-019 同源）
- 面试讲点："我自己实现了 RAG 的核心（embedding + cosine + top-k）"
  比"我用了 ChromaDB"贵 10 倍——前者证明你懂底层，后者只证明你会查文档
- 15 个文档的 O(N) 搜索 < 1ms，无性能问题

核心 API：
  RAGIndex.add(doc_id, text) - 添加一个文档
  RAGIndex.query(text, top_k=3) -> [(doc_id, text, score)] - 检索相似文档
  RAGIndex.save(path) / RAGIndex.load(path) - pickle 持久化
"""

import os
import pickle
from pathlib import Path
from typing import Callable, List, Tuple

import numpy as np


# 嵌入函数类型：传一批文本，返回一批向量
Embedder = Callable[[List[str]], List[List[float]]]


class ZhipuEmbedder:
    """智谱 embedding-3 嵌入器，2048 维。"""
    def __init__(self, api_key: str, model: str = "embedding-3"):
        from openai import OpenAI
        # 智谱兼容 OpenAI 协议，embedding 端点同 base_url
        self.client = OpenAI(api_key=api_key, base_url="https://open.bigmodel.cn/api/paas/v4/")
        self.model = model

    def __call__(self, texts: List[str]) -> List[List[float]]:
        resp = self.client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in resp.data]


class RAGIndex:
    """
    极简向量索引。
    存储为 (doc_id, text, embedding_np_array) 三元组列表。
    检索用 numpy 余弦相似度 + 排序，O(N) 但 N=15 时 < 1ms。
    """
    def __init__(self, embedder: Embedder):
        self.embedder = embedder
        # 存储：(doc_id, text, normalized_embedding)
        # 注意：embedding 已经归一化，余弦相似度退化为点积
        self.entries: List[Tuple[str, str, np.ndarray]] = []

    def _normalize(self, vec: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(vec)
        if norm == 0:
            return vec
        return vec / norm

    def add(self, doc_id: str, text: str) -> None:
        """添加单个文档（同步调嵌入 API）。"""
        emb = np.array(self.embedder([text])[0], dtype=np.float32)
        self.entries.append((doc_id, text, self._normalize(emb)))

    def add_batch(self, docs: List[Tuple[str, str]]) -> None:
        """批量添加，一次嵌入调用（省 API 钱）。"""
        if not docs:
            return
        texts = [d[1] for d in docs]
        embs = self.embedder(texts)
        for (doc_id, text), emb in zip(docs, embs):
            vec = np.array(emb, dtype=np.float32)
            self.entries.append((doc_id, text, self._normalize(vec)))

    def query(self, text: str, top_k: int = 3) -> List[Tuple[str, str, float]]:
        """
        检索 top-k 相似文档。
        返回：[(doc_id, text, similarity_score), ...]
        score 范围 [-1, 1]，归一化后等价于余弦相似度。
        """
        if not self.entries:
            return []
        q_emb = np.array(self.embedder([text])[0], dtype=np.float32)
        q_norm = self._normalize(q_emb)
        # 余弦相似度 = 归一化后向量的点积
        scores = [(doc_id, doc_text, float(np.dot(emb, q_norm))) for doc_id, doc_text, emb in self.entries]
        scores.sort(key=lambda x: -x[2])
        return scores[:top_k]

    def save(self, path: Path) -> None:
        """pickle 持久化（包含归一化后的 embedding）。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self.entries, f)

    @classmethod
    def load(cls, path: Path, embedder: Embedder) -> "RAGIndex":
        """从 pickle 加载（避免重复调嵌入 API）。"""
        idx = cls(embedder)
        with open(path, "rb") as f:
            idx.entries = pickle.load(f)
        return idx

    def __len__(self) -> int:
        return len(self.entries)


def build_world_lore_index(
    lore_dir: Path,
    cache_path: Path,
    embedder: Embedder,
    force_rebuild: bool = False,
) -> RAGIndex:
    """
    扫描 world_lore/ 目录下所有 .txt，构建向量索引。
    有缓存就读缓存（避免重复嵌入 = 省钱）；缓存版本失效则重建。

    缓存失效判断：缓存 mtime < 任一 .txt mtime —— 即文档更新后自动重建。
    """
    txt_files = sorted(lore_dir.glob("*.txt"))
    if not txt_files:
        # 空目录：返回空索引（不报错，让上层决定）
        return RAGIndex(embedder)

    # 缓存有效性检查
    cache_valid = False
    if cache_path.exists() and not force_rebuild:
        cache_mtime = cache_path.stat().st_mtime
        latest_doc_mtime = max(f.stat().st_mtime for f in txt_files)
        if cache_mtime > latest_doc_mtime:
            cache_valid = True

    if cache_valid:
        try:
            idx = RAGIndex.load(cache_path, embedder)
            print(f"[rag] loaded {len(idx)} docs from cache ({cache_path.name})")
            return idx
        except Exception as e:
            print(f"[rag] cache load failed: {e}, rebuilding")

    # 重建索引
    print(f"[rag] building index from {len(txt_files)} docs in {lore_dir.name}/...")
    idx = RAGIndex(embedder)
    docs = []
    for f in txt_files:
        text = f.read_text(encoding="utf-8")
        # doc_id 用文件名（不含扩展名），便于面试时讲哪段文档命中
        docs.append((f.stem, text))
    idx.add_batch(docs)
    idx.save(cache_path)
    print(f"[rag] built index with {len(idx)} docs, cached to {cache_path}")
    return idx


def format_rag_results_for_prompt(results: List[Tuple[str, str, float]]) -> str:
    """把 RAG 检索结果格式化成 prompt 块。"""
    if not results:
        return ""
    lines = ["【世界观参考资料】（与玩家本回合相关，可作为剧情依据）"]
    for doc_id, text, score in results:
        # 显示 doc_id 让 LLM 知道来源（便于 debug + 防止"凭空发挥"）
        lines.append(f"\n◆ 资料 [{doc_id}] (相似度 {score:.2f}):")
        lines.append(text.strip())
    return "\n".join(lines)
