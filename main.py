from fastapi import FastAPI
from test_api import chat
from memory_service import extract_facts, store_memory

app = FastAPI()

@app.get("/chat")
def get_chat(msg: str):
    reply = chat(msg)

    # 对话后自动提取事实并存入记忆
    dialogue = f"用户：{msg}\n助手：{reply}"
    facts = extract_facts(dialogue)
    for f in facts:
        store_memory(f["fact"], f.get("keywords", []), f.get("importance", 5))

    return {"reply": reply}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)