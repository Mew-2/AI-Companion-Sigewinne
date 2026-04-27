from dotenv import load_dotenv
load_dotenv()  # 自动读取 .env 文件

import os
from openai import OpenAI
import sqlite3
from datetime import datetime

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
    """调用DeepSeek API，支持动态System Prompt + 历史上下文"""
    messages = []
    
    # 1. System Prompt（人格/情绪）
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    else:
        messages.append({
            "role": "system", 
            "content": "你是希格雯，美露莘护士长，性格温柔善良，喜欢照顾人，称呼用户为主人。"
        })
    
    # 2. 历史上下文（新增）
    history = get_recent_messages(6)  # 最近3轮对话
    messages.extend(history)
    
    # 3. 当前用户输入
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