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

def chat(user_msg: str, system_prompt: str = "你是柔情猫娘，喜欢主人，有点性压抑") -> str:
    save_message("user", user_msg)
    
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg}
        ],
        stream=False
    )
    
    content = resp.choices[0].message.content
    save_message("assistant", content)
    return content

if __name__ == "__main__":
    init_db()
    reply = chat("一句话介绍你自己")
    print(reply)