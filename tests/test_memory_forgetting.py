"""遗忘机制单测：时效标记软删除、冲突覆盖、召回排除过期。隔离到 tmp DB + 假向量库。"""

import sqlite3

import pytest

import memory_service as ms


class _FakeRag:
    def __init__(self):
        self.docs = {}

    def add_memory(self, memory_id, fact, keywords, importance=5, source="dialogue", owner="主人"):
        self.docs[str(memory_id)] = fact

    def delete(self, memory_id):
        self.docs.pop(str(memory_id), None)

    def recall(self, query, top_k=5, min_importance=1, max_distance=None):
        return []

    def clear(self):
        self.docs.clear()


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(ms, "DB_PATH", str(tmp_path / "chat.db"))
    fake = _FakeRag()
    monkeypatch.setattr(ms, "user_memory_rag", fake)
    ms.init_db()
    return fake


def _status_map():
    conn = sqlite3.connect(ms.DB_PATH)
    rows = dict(conn.execute("SELECT fact, status FROM memories").fetchall())
    conn.close()
    return rows


def test_stale_marker_expires_on_write(isolated):
    ms.store_memory("主人以前住在苏州", ["苏州", "居住"], 5)
    # 软删除：SQLite 留痕，但不进向量库
    assert isolated.docs == {}
    assert _status_map()["主人以前住在苏州"] == "expired"


def test_active_fact_indexed(isolated):
    ms.store_memory("主人目前住在江苏南通", ["南通", "江苏"], 8)
    assert len(isolated.docs) == 1
    assert _status_map()["主人目前住在江苏南通"] == "active"


def test_conflict_supersede(isolated):
    ms.store_memory("主人喜欢喝可乐", ["可乐", "饮料"], 6)
    ms.store_memory("主人已经戒了可乐改喝奶茶", ["奶茶", "戒", "饮料"], 8)
    status = _status_map()
    assert status["主人喜欢喝可乐"] == "superseded"
    assert status["主人已经戒了可乐改喝奶茶"] == "active"


def test_recall_excludes_expired(isolated):
    ms.store_memory("主人以前住在苏州", ["苏州", "居住"], 5)
    ms.store_memory("主人目前住在江苏南通", ["南通", "江苏", "居住"], 8)
    out = ms.recall_memories("主人以前住在苏州还是南通？", top_k=3)
    facts = [m["fact"] for m in out]
    assert all("苏州" not in f for f in facts)
