from dotenv import load_dotenv
load_dotenv()

import os
import sqlite3
from datetime import datetime
from openai import OpenAI
from memory_service import recall_memories  # 新增：记忆召回

client = OpenAI(
    api_key=os.environ.get('DEEPSEEK_API_KEY'),
    base_url="https://api.deepseek.com"
)

def init_db():
    conn = sqlite3.connect("chat.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT,
            content TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_message(role: str, content: str):
    conn = sqlite3.connect("chat.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO messages (role, content, created_at) VALUES (?, ?, ?)",
        (role, content, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def get_recent_messages(limit: int = 6):
    """读取最近N条聊天记录作为上下文（3轮对话=6条）"""
    conn = sqlite3.connect("chat.db")
    c = conn.cursor()
    c.execute(
        "SELECT role, content FROM messages ORDER BY created_at DESC LIMIT ?",
        (limit,)
    )
    rows = c.fetchall()
    conn.close()
    # 反转回正序（旧→新）
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

def chat(msg: str, system_prompt: str = None) -> str:
    """调用DeepSeek API，支持动态System Prompt + 历史上下文 + 长期记忆召回"""
    messages = []
    
    # 1. System Prompt（人格/情绪）
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    else:
        messages.append({
            "role": "system", 
            "content": "你是希格雯，美露莘护士长，性格温柔善良，喜欢照顾人，称呼用户为主人。"
        })
    
    # 2. 长期记忆召回（新增）——根据当前用户输入召回相关事实
    memories = recall_memories(msg, top_k=3)
    if memories:
        memory_text = "你记得关于主人的事情：\n" + "\n".join(
            [f"- {m['fact']}" for m in memories]
        )
        messages.append({"role": "system", "content": memory_text})
    
    # 3. 短期对话历史（保证上下文连贯）
    history = get_recent_messages(6)
    messages.extend(history)
    
    # 4. 当前用户输入
    messages.append({"role": "user", "content": msg})
    
    response = client.chat.completions.create(
        model="deepseek-v4-pro",
        messages=messages,
        temperature=0.7,
        max_tokens=800
    )
    
    return response.choices[0].message.content

if __name__ == "__main__":
    init_db()
    reply = chat("一句话介绍你自己")
    print(reply)