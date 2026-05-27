import os
import json
import sqlite3
import jieba
import re
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com"
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
- 【禁止提取】天气、气温、温度、实时新闻、股价等时效性/实时信息，只提取长期有效的用户事实
只返回 JSON 数组，不要任何解释、不要 markdown 代码块。最多返回 3 条事实，每条事实控制在 50 字以内。

对话：
{dialogue}"""

    response = client.chat.completions.create(
        model="deepseek-v4-pro",
        messages=[
            {"role": "system", "content": "你是信息提取助手，只输出纯 JSON 数组。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=1500,
    )

    content = response.choices[0].message.content.strip()
    # 防 markdown
    content = (
        content.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    )

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
        (
            fact,
            json.dumps(keywords, ensure_ascii=False),
            importance,
            datetime.now(),
            datetime.now(),
        ),
    )
    conn.commit()
    conn.close()


# 停用词：过滤无意义词，提高召回精度
_STOP_WORDS = {
    "的",
    "了",
    "是",
    "我",
    "你",
    "他",
    "她",
    "它",
    "我们",
    "你们",
    "他们",
    "在",
    "有",
    "和",
    "与",
    "或",
    "一个",
    "什么",
    "怎么",
    "为什么",
    "吗",
    "呢",
    "吧",
    "喜欢",
    "记得",
    "知道",
    "告诉",
    "问",
    "说",
    "想",
    "要",
    "会",
    "能",
    "可以",
}


def _extract_keywords(text: str) -> list[str]:
    """jieba分词 + 停用词过滤 + 去重"""
    # jieba精确模式分词
    words = jieba.lcut(text)

    # 过滤：长度>1、不是停用词、不是纯标点/数字
    keywords = []
    for w in words:
        w = w.strip()
        if len(w) > 1 and w not in _STOP_WORDS and not re.match(r"^[\d\W]+$", w):
            keywords.append(w)

    # 额外提取：连续中文字符片段（2-4字），防jieba漏切
    chinese_segments = re.findall(r"[\u4e00-\u9fff]{2,4}", text)
    keywords.extend(chinese_segments)

    # 去重保持顺序
    return list(dict.fromkeys(keywords))


def recall_memories(query: str, top_k: int = 5) -> list[dict]:
    """召回：jieba分词 + 关键词模糊匹配 + 重要性排序"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    keywords = _extract_keywords(query)

    if keywords:
        # 每个关键词在fact和keywords字段里LIKE匹配
        conditions = " OR ".join(["(fact LIKE ? OR keywords LIKE ?)"] * len(keywords))
        params = []
        for kw in keywords:
            params.extend([f"%{kw}%", f"%{kw}%"])
    else:
        # 没有任何有效关键词时，退化为时间排序（返回最近的记忆）
        conditions = "1=1"
        params = []

    c.execute(
        f"""
        SELECT id, fact, keywords, importance, created_at, last_accessed
        FROM memories
        WHERE {conditions}
        ORDER BY importance DESC, last_accessed DESC
        LIMIT ?
    """,
        params + [top_k],
    )

    rows = c.fetchall()
    conn.close()

    return [
        {
            "id": r[0],
            "fact": r[1],
            "keywords": json.loads(r[2]) if r[2] else [],
            "importance": r[3],
            "created_at": r[4],
            "last_accessed": r[5],
        }
        for r in rows
    ]


def update_accessed(memory_id: int):
    """更新最后访问时间（召回后调用）"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "UPDATE memories SET last_accessed = ? WHERE id = ?",
        (datetime.now(), memory_id),
    )
    conn.commit()
    conn.close()


# 启动时自动建表
init_db()
