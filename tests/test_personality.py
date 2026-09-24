"""人格状态机单测：sad 分支惯性递减，修复"卡死在 sad"的死锁。隔离到 tmp DB，mock 情绪打分。"""

import pytest

import personality_state as ps


@pytest.fixture
def p(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "DB_PATH", str(tmp_path / "chat.db"))
    return ps.PersonalityState()


def test_sad_momentum_decrements_to_normal(p):
    # 构造死锁现场：affinity 落在 (-20, -10) 的 sad 区，momentum 停在 3（旧实现永不递减）
    p.affinity = -15
    p.emotion = "sad"
    p.momentum = 3
    p._analyze_sentiment = lambda msg: 0.0  # 中性，affinity 不变

    emotions = []
    for _ in range(6):
        p.update("x")
        emotions.append(p.emotion)
    assert "normal" in emotions, f"sad 死锁未修复: {emotions}"


def test_angry_has_inertia(p):
    p.affinity = -25
    p._analyze_sentiment = lambda msg: 0.0
    p.update("x")
    assert p.emotion == "angry"
    assert p.momentum >= 3


def test_happy_requires_consecutive_positive(p):
    p._analyze_sentiment = lambda msg: 1.0
    for _ in range(16):
        p.update("x")
    assert p.emotion == "happy"
    assert p.affinity > 30
