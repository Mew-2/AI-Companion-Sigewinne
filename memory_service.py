import os
import json
import sqlite3
import jieba
from retrievers.user_memory import UserMemoryRAG
import re
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

load_dotenv()

# 全局初始化向量记忆
user_memory_rag = UserMemoryRAG()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com"
)

DB_PATH = "chat.db"


def init_db():
    """创建 memories 表（安全，重复执行不会报错），并把旧库迁移出 owner 列。"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fact TEXT NOT NULL,
            keywords TEXT NOT NULL,
            importance INTEGER DEFAULT 5 CHECK(importance BETWEEN 1 AND 10),
            owner TEXT DEFAULT '主人',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # 迁移：旧库（无 owner 列）补列，历史记忆默认归属"主人"
    cols = {row[1] for row in c.execute("PRAGMA table_info(memories)")}
    if "owner" not in cols:
        c.execute("ALTER TABLE memories ADD COLUMN owner TEXT DEFAULT '主人'")
        logger.info("[UserMemory] 迁移：memories 表新增 owner 列，历史记忆默认 owner=主人")
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


def _normalize_fact(text: str) -> str:
    """去重归一化：去末尾标点符号和空白"""
    return text.rstrip("。！？，,.!?;；:： \t\n")


# 他人关系词：用于区分"关于主人自己的记忆"与"关于他人（同事/朋友/家人）的记忆"
_RELATION_WORDS = (
    "同事|朋友|邻居|室友|同学|老师|医生|领导|老板|上司|"
    "妹妹|弟弟|哥哥|姐姐|表弟|表妹|表哥|表姐|"
    "父母|爸爸|妈妈|父亲|母亲|爷爷|奶奶|外公|外婆|"
    "男友|女友|老公|老婆|丈夫|妻子|儿子|女儿|孩子|亲戚"
)
# "主人的<关系词>" / "主人家的<关系词>" → 该条记忆的主体是他人
_OWNER_OTHER_RE = re.compile(rf"^主人(?:的|家的)\s*(?:{_RELATION_WORDS})")
# 提问主体："我的<关系词>" → 问的是他人；否则默认问主人自己
_QUERY_OTHER_RE = re.compile(rf"我(?:的|家)?\s*(?:{_RELATION_WORDS})")


def _infer_owner(fact: str) -> str:
    """从事实文本推断主体：默认"主人"，形如"主人的同事…"判为"他人"。"""
    return "他人" if _OWNER_OTHER_RE.match(fact.strip()) else "主人"


def _infer_query_owner(query: str) -> str:
    """从提问推断主体：默认"主人"，形如"我同事…"判为"他人"。"""
    return "他人" if _QUERY_OTHER_RE.search(query) else "主人"


def store_memory(fact: str, keywords: list, importance: int = 5, owner: str | None = None):
    """SQLite + ChromaDB 双写。owner 缺省时按事实文本自动推断（主人/他人）。"""
    fact = _normalize_fact(fact)
    if owner is None:
        owner = _infer_owner(fact)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 去重：归一化后去标点比较，防 "用户喜欢喝奶茶。" ≠ "用户喜欢喝奶茶"
    for row in c.execute("SELECT id, fact FROM memories"):
        if _normalize_fact(row[1]) == fact:
            conn.close()
            logger.info(f"[UserMemory] 记忆已存在，跳过写入: {fact[:30]}...")
            return

    c.execute(
        """INSERT INTO memories (fact, keywords, importance, owner, created_at, last_accessed)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            fact,
            json.dumps(keywords, ensure_ascii=False),
            importance,
            owner,
            datetime.now(),
            datetime.now(),
        ),
    )
    memory_id = c.lastrowid
    conn.commit()
    conn.close()

    # 同步写入 ChromaDB 向量库
    try:
        user_memory_rag.add_memory(
            memory_id=str(memory_id),
            fact=fact,
            keywords=keywords,
            importance=importance,
            owner=owner,
        )
    except Exception as e:
        logger.error(f"[UserMemory] 向量写入失败: {e}")


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


def _recall_by_keywords(query: str, top_k: int = 5) -> list[dict]:
    """原 jieba 关键词召回，保留作为 fallback"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    keywords = _extract_keywords(query)

    if keywords:
        conditions = " OR ".join(["(fact LIKE ? OR keywords LIKE ?)"] * len(keywords))
        params = []
        for kw in keywords:
            params.extend([f"%{kw}%", f"%{kw}%"])
    else:
        conditions = "1=1"
        params = []

    c.execute(
        f"""
        SELECT id, fact, keywords, importance, owner, created_at, last_accessed
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
            "owner": r[4] or "主人",
            "created_at": r[5],
            "last_accessed": r[6],
        }
        for r in rows
    ]


def recall_memories(query: str, top_k: int = 5, owner: str | None = None) -> list[dict]:
    """
    混合召回：ChromaDB 语义召回（优先） + jieba 关键词召回（兜底）。
    owner 缺省时按提问推断主体，只保留同一主体的记忆（隔离"同事/朋友"等他人事实）。
    """
    if owner is None:
        owner = _infer_query_owner(query)

    # === 1. 向量语义召回 ===
    vec_results = []
    try:
        vec_results = user_memory_rag.recall(query, top_k=3, min_importance=1)
    except Exception as e:
        logger.error(f"[UserMemory] 召回失败: {e}")

    # === 2. 原 jieba 关键词召回 ===
    kw_results = _recall_by_keywords(query, top_k=3)

    # === 3. 合并去重（id 为 key）===
    seen = set()
    merged = []
    for r in vec_results + kw_results:
        mid = str(r.get("id"))
        if mid and mid not in seen:
            seen.add(mid)
            merged.append(r)

    # === 4. 主体过滤：只保留与提问主体一致的记忆 ===
    merged = [r for r in merged if (r.get("owner") or "主人") == owner]

    # 按 importance 降序，取 top_k
    merged.sort(key=lambda x: x.get("importance", 0), reverse=True)
    return merged[:top_k]


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
