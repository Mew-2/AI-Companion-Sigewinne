from fastapi import FastAPI
from test_api import chat, save_message, init_db as init_chat_db
from memory_service import extract_facts, store_memory
from personality_state import PersonalityState

from schemas import ChatRequest, ChatResponse
from exceptions import setup_exception_handlers, LLMTimeoutException, CompanionException

app = FastAPI(title="AI Companion API", version="1.0.0")
setup_exception_handlers(app)

# 初始化聊天记录表
init_chat_db()

# 全局人格实例（单用户场景）
personality = PersonalityState()


def _handle_chat(msg: str) -> dict:
    """核心聊天逻辑，保持原有业务不变"""
    # 1. 人格驱动System Prompt（情绪+好感度）
    system_prompt = personality.build_system_prompt()
    
    # 2. LLM对话，注入人格
    reply = chat(msg, system_prompt=system_prompt)
    
    # 3. 更新人格状态（分析情绪→好感度→惯性）
    personality.update(msg)
    
    # 4. 保存完整聊天记录
    save_message("user", msg)
    save_message("assistant", reply)
    
    # 5. 提取结构化记忆（事实+情绪）
    dialogue = f"用户：{msg}\n助手：{reply}"
    facts = extract_facts(dialogue)
    for f in facts:
        store_memory(f["fact"], f.get("keywords", []), f.get("importance", 5))
    
    return {"reply": reply, "emotion": personality.emotion, "affection": personality.affinity}


@app.post("/chat", response_model=ChatResponse)
async def chat_post(request: ChatRequest):
    """标准 POST 接口，Pydantic 入参出参"""
    try:
        result = _handle_chat(request.msg)
        return ChatResponse(
            reply=result["reply"],
            emotion=result["emotion"],
            affection=result["affection"]
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