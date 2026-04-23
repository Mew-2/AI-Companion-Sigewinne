from fastapi import FastAPI
from test_api import chat  # 复用昨天的函数

app = FastAPI()

@app.get("/chat")
def get_chat(msg: str):
    reply = chat(msg)
    return {"reply": reply}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)