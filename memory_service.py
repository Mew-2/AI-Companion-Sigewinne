import os
import json
import sqlite3
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

DB_PATH = "chat.db"


def init_db():
    """创建 memories 表（安全，重复执行不会报错）"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fact TEXT NOT NULL,
            keywords TEXT NOT NULL,
            importance INTEGER DEFAULT 5 CHECK(importance BETWEEN 1 AND 10),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def extract_facts(dialogue: str) -> list[dict]:
    """调 DeepSeek 从对话中提取事实"""
    prompt = f"""请从以下对话中提取关键事实，返回 JSON 数组。
要求：
- fact: 事实描述（简洁，一句话）
- keywords: 3-5 个关键词（JSON 数组）
- importance: 重要性 1-10（用户喜好/雷点给 8-10，闲聊给 3-5）
只返回 JSON 数组，不要任何解释、不要 markdown 代码块。

对话：
{dialogue}"""

    response = client.chat.completions.create(
        model="deepseek-v4-pro",
        messages=[
            {"role": "system", "content": "你是信息提取助手，只输出纯 JSON 数组。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=800
    )

    content = response.choices[0].message.content.strip()
    # 防 markdown
    content = content.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        facts = json.loads(content)
        return facts if isinstance(facts, list) else [facts]
    except json.JSONDecodeError:
        print("[extract_facts] JSON解析失败，原始内容：", content)
        return []


def store_memory(fact: str, keywords: list, importance: int = 5):
    """存记忆"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """INSERT INTO memories (fact, keywords, importance, created_at, last_accessed)
           VALUES (?, ?, ?, ?, ?)""",
        (fact, json.dumps(keywords, ensure_ascii=False), importance, datetime.now(), datetime.now())
    )
    conn.commit()
    conn.close()


def recall_memories(query: str, top_k: int = 5) -> list[dict]:
    """召回：关键词模糊匹配 + 重要性排序"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    words = [w for w in query.split() if len(w) > 1]
    if words:
        conditions = " OR ".join(["(fact LIKE ? OR keywords LIKE ?)"] * len(words))
        params = []
        for w in words:
            params.extend([f"%{w}%", f"%{w}%"])
    else:
        conditions = "1=1"
        params = []

    c.execute(f"""
        SELECT id, fact, keywords, importance, created_at, last_accessed
        FROM memories
        WHERE {conditions}
        ORDER BY importance DESC, last_accessed DESC
        LIMIT ?
    """, params + [top_k])

    rows = c.fetchall()
    conn.close()

    return [
        {
            "id": r[0], "fact": r[1],
            "keywords": json.loads(r[2]) if r[2] else [],
            "importance": r[3], "created_at": r[4], "last_accessed": r[5]
        }
        for r in rows
    ]


def update_accessed(memory_id: int):
    """更新最后访问时间（召回后调用）"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE memories SET last_accessed = ? WHERE id = ?",
              (datetime.now(), memory_id))
    conn.commit()
    conn.close()


# 启动时自动建表
init_db()