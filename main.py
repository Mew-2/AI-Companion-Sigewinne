from fastapi import FastAPI
from test_api import (
    save_message,
    init_db as init_chat_db,
    client as llm_client,
    get_recent_messages,
)
from memory_service import extract_facts, store_memory, recall_memories, update_accessed
from personality_state import PersonalityState

from schemas import ChatRequest, ChatResponse
from exceptions import setup_exception_handlers, LLMTimeoutException, CompanionException

from agent import ReActAgent
from tools.weather import get_weather
from tools.search import web_search
import logging

# 根日志器
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)  # 全局放行 DEBUG，由 Handler 各自过滤

# 过滤第三方库噪音：httpx/httpcore/openai 的 DEBUG 不记录
for noisy in ["httpcore", "httpx", "openai", "asyncio", "jieba"]:
    logging.getLogger(noisy).setLevel(logging.WARNING)

# 控制台：只显示 INFO 及以上，精简格式
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)

# 文件：记录 DEBUG 及以上，完整内容写入 agent.log（自动追加，不覆盖）
file_handler = logging.FileHandler("logs/agent.log", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(file_handler)

app = FastAPI(title="AI Companion API", version="1.1.0")
setup_exception_handlers(app)

# 初始化聊天记录表
init_chat_db()

# 全局人格实例
personality = PersonalityState()


# 继承 ReActAgent，接入真实 LLM（不走 test_api.chat，避免重复记录历史）
class CompanionAgent(ReActAgent):
    def _call_llm(self, system_content: str, user_content: str) -> str:
        try:
            response = llm_client.chat.completions.create(
                model="deepseek-v4-pro",
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.7,
                max_tokens=800,
            )
            return response.choices[0].message.content
        except Exception:
            return "Final Answer: 哎呀，希格雯的通讯魔法被干扰了...主人稍后再试好吗？"


# 初始化 Agent：注册可用工具
agent = CompanionAgent(tools={"weather": get_weather, "search": web_search})


def _handle_chat(msg: str) -> dict:
    """
    完整链路：短期历史 + 人格 + 长期记忆 → ReAct 循环 → 更新人格 → 保存对话 → 提取记忆
    """
    # 1. 人格驱动 System Prompt
    system_prompt = personality.build_system_prompt()

    # 2. 短期对话历史注入（新增）
    history = get_recent_messages(6)
    if history:
        history_text = "\n".join([f"{h['role']}: {h['content']}" for h in history])
        system_prompt += f"\n\n最近的对话：\n{history_text}"

    # 3. 长期记忆召回（注入 ReAct 上下文）
    memories = recall_memories(msg, top_k=3)
    if memories:
        memory_text = "你记得关于主人的事情：\n" + "\n".join(
            [f"- {m['fact']}" for m in memories]
        )
        system_prompt += f"\n\n{memory_text}"
        # 更新访问时间（新增）
        for m in memories:
            update_accessed(m["id"])

    # 4. Agent ReAct 循环
    result = agent.run(msg, system_prompt)
    reply = result["reply"]

    # 5. 更新人格状态
    personality.update(msg)

    # 6. 保存完整聊天记录
    save_message("user", msg)
    save_message("assistant", reply)

    # 7. 提取结构化记忆
    dialogue = f"用户：{msg}\n助手：{reply}"
    facts = extract_facts(dialogue)
    for f in facts:
        store_memory(f["fact"], f.get("keywords", []), f.get("importance", 5))

    return {
        "reply": reply,
        "emotion": personality.emotion,
        "affection": personality.affinity,
    }


@app.post("/chat", response_model=ChatResponse)
async def chat_post(request: ChatRequest):
    """标准 POST 接口"""
    try:
        result = _handle_chat(request.msg)
        return ChatResponse(
            reply=result["reply"],
            emotion=result["emotion"],
            affection=result["affection"],
        )
    except TimeoutError:
        raise LLMTimeoutException()
    except Exception as e:
        raise CompanionException(str(e))


@app.get("/chat")
async def chat_get(msg: str):
    """兼容旧版 GET /chat?msg=xxx"""
    return await chat_post(ChatRequest(msg=msg))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
