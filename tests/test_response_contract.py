"""响应契约测试：锁定 `/chat` 与 `/chat/stream` 对外暴露的 `used_tool` / `recalled_memories` 形状。

为什么单独一个文件：2026-09-23 的 bug 根因是"字段定义了却从不回传，且没有任何断言把契约钉住"。
本文件是评测体系 v1 的第一层——单元级契约测试：全 mock、可重复、不烧 LLM 额度、不依赖库内数据。
只覆盖"出口字段存在且形状正确"，不覆盖检索质量（那是端到端评测的事）。

运行：HF_HUB_OFFLINE=1 venv/bin/python -m pytest tests/test_response_contract.py -q
"""

import json
from contextlib import ExitStack, contextmanager
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

import main
from main import app

client = TestClient(app)

# 召回层真实返回的裸 dict 形状（memory_service.recall_memories），含 id/distance 等内部字段。
# 用它喂进链路，断言出口把这些内部字段裁掉了。
_RAW_RECALL = [
    {
        "id": 7,
        "fact": "主人喜欢喝奶茶",
        "keywords": ["奶茶"],
        "importance": 9,
        "created_at": "2026-09-01 10:00:00",
        "last_accessed": "2026-09-23 09:00:00",
        "distance": 0.31,
    }
]

# 对外契约：只有这三个字段，多一个都算泄漏内部实现。
_CONTRACT_KEYS = {"fact", "keywords", "importance"}


def _llm_response(content: str):
    m = MagicMock()
    m.choices = [MagicMock()]
    m.choices[0].message.content = content
    return m


def _mock_planner(*args, **kwargs):
    """规划/生成阶段的 LLM：问天气先给 Action，看到 Observation 再给 Final Answer。"""
    messages = kwargs.get("messages") or []
    content = messages[-1].get("content", "") if messages else ""
    if "Observation" in content:
        return _llm_response("Final Answer: 上海今天晴，25°C 哦主人~")
    if "天气" in content:
        return _llm_response(
            "Thought: 用户问天气，需要调用天气工具\nAction: weather(city='上海')"
        )
    return _llm_response("Final Answer: 主人好呀~")


def _mock_memory_llm(*args, **kwargs):
    """memory_service / personality_state 共用的 LLM：事实抽取 + 情绪打分。"""
    messages = kwargs.get("messages") or []
    content = messages[-1].get("content", "") if messages else ""
    if "事实" in content or "提取" in content:
        return _llm_response(
            '[{"fact": "用户喜欢测试", "keywords": ["测试"], "importance": 5}]'
        )
    return _llm_response('{"sentiment": 0.5}')


def _fake_weather(city: str) -> str:
    """替身工具：禁止契约测试打真实和风天气 API。"""
    return f"{city}今天晴，25°C"


def _fake_search(query: str) -> str:
    return "stub"


@contextmanager
def _patched(recall_result=None):
    """全 mock 环境：无网络、无副作用（不写 chat.db / Chroma / 人格状态），召回结果可控。"""
    with ExitStack() as stack:
        stack.enter_context(
            patch("main.agent.tools", new={"weather": _fake_weather, "search": _fake_search})
        )
        stack.enter_context(patch("main.update_accessed", new=lambda *a, **k: None))
        stack.enter_context(patch("main.save_message", new=lambda *a, **k: None))
        stack.enter_context(patch("main.store_memory", new=lambda *a, **k: None))
        stack.enter_context(
            patch.object(main.personality, "update", new=lambda *a, **k: None)
        )
        stack.enter_context(
            patch("test_api.client.chat.completions.create", side_effect=_mock_planner)
        )
        stack.enter_context(
            patch(
                "memory_service.client.chat.completions.create",
                side_effect=_mock_memory_llm,
            )
        )
        stack.enter_context(
            patch("main.recall_memories", new=lambda *a, **k: list(recall_result or []))
        )
        yield


def test_post_chat_reports_used_tool():
    """走工具时，非流式响应必须回传 used_tool。"""
    with _patched():
        resp = client.post("/chat", json={"msg": "上海今天天气怎么样？"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["used_tool"] == "weather"
    assert data["reply"] == "上海今天晴，25°C 哦主人~"


def test_post_chat_recalled_memories_shape():
    """不用工具时 used_tool 为 None；召回记忆必须裁成三字段契约形状。"""
    with _patched(recall_result=_RAW_RECALL):
        resp = client.post("/chat", json={"msg": "你还记得我喜欢什么吗？"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["used_tool"] is None
    assert len(data["recalled_memories"]) == 1

    item = data["recalled_memories"][0]
    assert set(item.keys()) == _CONTRACT_KEYS
    assert item["fact"] == "主人喜欢喝奶茶"
    assert item["keywords"] == ["奶茶"]
    assert item["importance"] == 9


def test_stream_meta_shape_matches_post():
    """流式 meta 的 recalled_memories 必须与非流式同形状（不泄漏 id/distance）。"""
    with _patched(recall_result=_RAW_RECALL):
        resp = client.post("/chat/stream", json={"msg": "你好"})

    assert resp.status_code == 200
    chunks = [json.loads(line) for line in resp.text.splitlines() if line.strip()]
    meta = next(c for c in chunks if c.get("type") == "meta")

    assert "recalled_memories" in meta, "meta 包必须始终带 recalled_memories 键"
    assert len(meta["recalled_memories"]) == 1
    assert set(meta["recalled_memories"][0].keys()) == _CONTRACT_KEYS
    assert meta["recalled_memories"][0]["fact"] == "主人喜欢喝奶茶"


def test_stream_fallback_meta_keeps_key():
    """降级流（顶层异常兜底）的 meta 也必须带 recalled_memories 键，客户端不必写缺键分支。"""
    with _patched():
        with patch("main._handle_chat_stream", side_effect=RuntimeError("boom")):
            resp = client.post("/chat/stream", json={"msg": "你好"})

    assert resp.status_code == 200
    chunks = [json.loads(line) for line in resp.text.splitlines() if line.strip()]
    meta = next(c for c in chunks if c.get("type") == "meta")

    assert meta["recalled_memories"] == []
    assert any(c.get("type") == "text" for c in chunks)
