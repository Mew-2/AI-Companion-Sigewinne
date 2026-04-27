from fastapi import FastAPI
from test_api import chat, save_message, init_db as init_chat_db
from memory_service import extract_facts, store_memory
from personality_state import PersonalityState

app = FastAPI()

# 初始化聊天记录表
init_chat_db()

# 全局人格实例（单用户场景）
personality = PersonalityState()

@app.get("/chat")
def get_chat(msg: str):
    # 1. 人格驱动System Prompt（情绪+好感度）
    system_prompt = personality.build_system_prompt()
    
    # 2. LLM对话，注入人格
    reply = chat(msg, system_prompt=system_prompt)
    
    # 3. 更新人格状态（分析情绪→好感度→惯性）
    personality.update(msg)
    
    # 4. 保存完整聊天记录（原始数据，以后做对话RAG用）
    save_message("user", msg)
    save_message("assistant", reply)
    
    # 5. 提取结构化记忆（事实+情绪）
    dialogue = f"用户：{msg}\n助手：{reply}"
    facts = extract_facts(dialogue)
    for f in facts:
        store_memory(f["fact"], f.get("keywords", []), f.get("importance", 5))
    
    return {"reply": reply}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)