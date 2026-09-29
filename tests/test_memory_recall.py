"""召回回归单测：向量路命中的记忆，其访问频率必须在生产路径（recall_memories）生效。

缺陷①：user_memory.recall 返回的 dict 缺 access_count/last_accessed，而合并时向量侧
优先，导致语义命中记忆的频率恒为 1.0。本测试用真实 UserMemoryRAG（隔离 tmp chroma）+
隔离 SQLite，验证 recall_memories 会从 SQLite 回填权威访问统计。
"""

import sqlite3

import memory_service as ms
from retrievers.user_memory import UserMemoryRAG


def test_vector_path_access_count_reflected(tmp_path, monkeypatch):
    rag = UserMemoryRAG(db_path=str(tmp_path / "chroma"))
    monkeypatch.setattr(ms, "DB_PATH", str(tmp_path / "chat.db"))
    monkeypatch.setattr(ms, "user_memory_rag", rag)
    ms.init_db()

    ms.store_memory("主人喜欢喝奶茶", ["奶茶", "珍珠"], 9)
    conn = sqlite3.connect(ms.DB_PATH)
    mid = conn.execute("SELECT id FROM memories").fetchone()[0]
    conn.execute("UPDATE memories SET access_count=5 WHERE id=?", (mid,))
    conn.commit()
    conn.close()

    # 向量路 dict 必须补齐 access_count/last_accessed 字段
    vec = rag.recall("主人喜欢喝奶茶", top_k=1)
    assert vec and "access_count" in vec[0] and "last_accessed" in vec[0]

    # 生产路径：语义命中的记忆必须带上 SQLite 的权威访问次数，且频率加成生效
    out = ms.recall_memories("主人喜欢喝奶茶", top_k=3)
    hit = [m for m in out if m["fact"] == "主人喜欢喝奶茶"]
    assert hit, out
    assert hit[0]["access_count"] == 5
    assert hit[0]["_recency"] > 1.0
