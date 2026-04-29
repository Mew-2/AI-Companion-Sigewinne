from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _mock_chat_create(*args, **kwargs):
    """Mock test_api 的 LLM 调用"""
    m = MagicMock()
    m.choices = [MagicMock()]
    m.choices[0].message.content = "希格雯测试回复"
    return m


def _mock_memory_create(*args, **kwargs):
    """Mock memory_service 的 LLM 调用（extract_facts + sentiment）"""
    m = MagicMock()
    messages = kwargs.get('messages', [])
    if messages:
        content = messages[-1].get('content', '')
        if '事实' in content or '提取' in content:
            m.choices = [MagicMock()]
            m.choices[0].message.content = '[{"fact": "用户喜欢测试", "keywords": ["测试"], "importance": 5}]'
        elif '情绪' in content or 'sentiment' in content:
            m.choices = [MagicMock()]
            m.choices[0].message.content = '{"sentiment": 0.5}'
        else:
            m.choices = [MagicMock()]
            m.choices[0].message.content = "默认"
    return m


@patch('test_api.client.chat.completions.create', side_effect=_mock_chat_create)
@patch('memory_service.client.chat.completions.create', side_effect=_mock_memory_create)
def test_chat_get_success(mock_mem, mock_chat):
    """GET /chat 正常请求"""
    response = client.get("/chat?msg=我喜欢粉毛女仆")
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert data["reply"] == "希格雯测试回复"


@patch('test_api.client.chat.completions.create', side_effect=_mock_chat_create)
@patch('memory_service.client.chat.completions.create', side_effect=_mock_memory_create)
def test_chat_post_success(mock_mem, mock_chat):
    """POST /chat 正常请求"""
    response = client.post("/chat", json={"msg": "测试消息"})
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert data["reply"] == "希格雯测试回复"


def test_chat_post_validation_error():
    """POST 空消息应该 422"""
    response = client.post("/chat", json={"msg": ""})
    assert response.status_code == 422