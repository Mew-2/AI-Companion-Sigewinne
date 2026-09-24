import os
import json
import math
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
    """创建 memories 表（安全，重复执行不会报错），并把旧库迁移出 owner/status/access_count 列。"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fact TEXT NOT NULL,
            keywords TEXT NOT NULL,
            importance INTEGER DEFAULT 5 CHECK(importance BETWEEN 1 AND 10),
            owner TEXT DEFAULT '主人',
            status TEXT DEFAULT 'active',
            access_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # 迁移：旧库补列
    cols = {row[1] for row in c.execute("PRAGMA table_info(memories)")}
    if "owner" not in cols:
        c.execute("ALTER TABLE memories ADD COLUMN owner TEXT DEFAULT '主人'")
        logger.info("[UserMemory] 迁移：memories 表新增 owner 列，历史记忆默认 owner=主人")
    if "status" not in cols:
        c.execute("ALTER TABLE memories ADD COLUMN status TEXT DEFAULT 'active'")
        logger.info("[UserMemory] 迁移：memories 表新增 status 列，历史记忆默认 status=active")
    if "access_count" not in cols:
        c.execute("ALTER TABLE memories ADD COLUMN access_count INTEGER DEFAULT 0")
        logger.info("[UserMemory] 迁移：memories 表新增 access_count 列")
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
# 自然表述：事实直接以关系词开头（可跟姓名/称呼），如"同事小李喜欢美式咖啡""妹妹对芒果过敏"
_OWNER_OTHER_BARE_RE = re.compile(rf"^(?:{_RELATION_WORDS})")
# 提问主体："我的<关系词>" → 问的是他人；否则默认问主人自己
_QUERY_OTHER_RE = re.compile(rf"我(?:的|家)?\s*(?:{_RELATION_WORDS})")


def _infer_owner(fact: str) -> str:
    """从事实文本推断主体：默认"主人"。

    命中以下任一即判为"他人"：
    - 显式归属："主人的同事…" / "主人家的妹妹…"
    - 自然表述：事实直接以关系词开头（可带姓名），如"同事小李喜欢美式咖啡"。
      注意"主人有个妹妹…""主人被同事抢了功劳"以"主人"开头，仍归主人。
    """
    f = fact.strip()
    if _OWNER_OTHER_RE.match(f) or _OWNER_OTHER_BARE_RE.match(f):
        return "他人"
    return "主人"


def _infer_query_owner(query: str) -> str:
    """从提问推断主体：默认"主人"，形如"我同事…"判为"他人"。"""
    return "他人" if _QUERY_OTHER_RE.search(query) else "主人"


# 时效标记：命中即视为"已过期/情景性"记忆，写入即失效（软删除，不参与召回）
_STALE_MARKERS = (
    "以前", "之前", "曾经", "去年", "上个月", "上周", "上周末",
    "昨天", "前天", "过去", "当年", "那时候",
)
# 现状/变更标记：命中表示"当前有效的新事实"，可与同主题旧记忆冲突覆盖
_CURRENT_MARKERS = (
    "已经", "现在", "如今", "目前", "成功", "换成", "搬到",
    "转岗", "戒了", "买好", "决定不", "改成",
)


def _is_expired_fact(fact: str) -> bool:
    """含过去时效标记的事实 = 已被覆盖/已过去的情景，标记为过期。"""
    return any(m in fact for m in _STALE_MARKERS)


def _has_current_marker(fact: str) -> bool:
    return any(m in fact for m in _CURRENT_MARKERS)


def _supersede_conflicts(new_id: int, fact: str, keywords: list, owner: str) -> int:
    """冲突覆盖：新事实带"现状"标记且与同主体旧记忆共享关键词时，
    旧记忆置为 superseded 并撤出向量库（软删除）。"""
    if not _has_current_marker(fact):
        return 0
    new_kw = set(keywords or [])
    if not new_kw:
        return 0
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    superseded = 0
    rows = c.execute(
        "SELECT id, keywords FROM memories WHERE status='active' AND owner=? AND id<>?",
        (owner, new_id),
    ).fetchall()
    for rid, rkw in rows:
        try:
            old_kw = set(json.loads(rkw) if rkw else [])
        except Exception:
            old_kw = set()
        if new_kw & old_kw:
            c.execute("UPDATE memories SET status='superseded' WHERE id=?", (rid,))
            try:
                user_memory_rag.delete(str(rid))
            except Exception as e:
                logger.error(f"[UserMemory] 冲突覆盖删除向量失败 id={rid}: {e}")
            logger.info(f"[UserMemory] 冲突覆盖：旧记忆 id={rid} 被新记忆 id={new_id} 取代")
            superseded += 1
    conn.commit()
    conn.close()
    return superseded


def store_memory(fact: str, keywords: list, importance: int = 5, owner: str | None = None):
    """SQLite + ChromaDB 双写。

    - owner 缺省时按事实文本自动推断（主人/他人）。
    - 命中时效标记（以前/上周/昨天…）的事实写入即标记 expired（软删除，不入向量库）。
    - 带"现状"标记且与同主体旧记忆共享关键词时，旧记忆被冲突覆盖（superseded）。
    """
    fact = _normalize_fact(fact)
    if owner is None:
        owner = _infer_owner(fact)
    status = "expired" if _is_expired_fact(fact) else "active"

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 去重：归一化后去标点比较，防 "用户喜欢喝奶茶。" ≠ "用户喜欢喝奶茶"
    for row in c.execute("SELECT id, fact FROM memories"):
        if _normalize_fact(row[1]) == fact:
            conn.close()
            logger.info(f"[UserMemory] 记忆已存在，跳过写入: {fact[:30]}...")
            return

    c.execute(
        """INSERT INTO memories
           (fact, keywords, importance, owner, status, access_count, created_at, last_accessed)
           VALUES (?, ?, ?, ?, ?, 0, ?, ?)""",
        (
            fact,
            json.dumps(keywords, ensure_ascii=False),
            importance,
            owner,
            status,
            datetime.now(),
            datetime.now(),
        ),
    )
    memory_id = c.lastrowid
    conn.commit()
    conn.close()

    if status == "expired":
        logger.info(
            f"[UserMemory] 时效标记命中，写入即失效（软删除，不入向量库）: {fact[:30]}..."
        )
        return

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

    # 冲突覆盖：新现状事实取代同主题旧事实
    _supersede_conflicts(memory_id, fact, keywords, owner)


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

    if not keywords:
        # 消灭 1=1 兜底：无有效关键词时不再"返回全表最重要的 N 条"，显式返回空
        logger.info(f"[UserMemory] 关键词路无有效词，显式返回空: {query[:20]}...")
        conn.close()
        return []

    conditions = " OR ".join(["(fact LIKE ? OR keywords LIKE ?)"] * len(keywords))
    params = []
    for kw in keywords:
        params.extend([f"%{kw}%", f"%{kw}%"])

    c.execute(
        f"""
        SELECT id, fact, keywords, importance, owner, access_count, created_at, last_accessed
        FROM memories
        WHERE ({conditions}) AND status='active'
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
            "access_count": r[5] or 0,
            "created_at": r[6],
            "last_accessed": r[7],
        }
        for r in rows
    ]


# 召回参数（重构：相关性阈值 + 融合重排 + 遗忘）
RECALL_CANDIDATE_K = 15      # 候选池大小（供过滤/重排）
RECALL_MAX_DISTANCE = 0.8    # 绝对阈值：cosine 距离超过即丢弃
RECALL_SCORE_MARGIN = 0.08   # 相对阈值：只保留与最佳结果分数差在 margin 内的记忆
RECALL_W_DISTANCE = 0.9      # 融合打分权重：distance 为主
RECALL_W_IMPORTANCE = 0.1    # importance 为辅
RECALL_DECAY_LAMBDA = 0.05   # 时间衰减：每天按 e^-0.05 降权
RECALL_MIN_RECENCY = 0.05    # 衰减因子低于此值视为过期，不再召回


def _recency_factor(m: dict) -> float:
    """遗忘因子 = 时间衰减 × 访问频率加成。

    - 越久未访问，decay 越小（exp(-λ·天数)）。
    - 被访问次数越多，freq 越大（1+ln(1+access_count)）——热点记忆不易被遗忘。
    """
    ts = m.get("last_accessed") or m.get("created_at")
    days = 0.0
    if ts:
        try:
            days = max(0.0, (datetime.now() - datetime.fromisoformat(str(ts))).total_seconds() / 86400)
        except (ValueError, TypeError):
            days = 0.0
    decay = math.exp(-RECALL_DECAY_LAMBDA * days)
    freq = 1.0 + math.log1p(int(m.get("access_count") or 0))
    return decay * freq


def _enrich_from_sqlite(memories: list[dict]) -> None:
    """用 SQLite（权威源）就地回填 access_count/last_accessed/owner/status。

    向量路返回的 dict 不含权威的 access_count/last_accessed（user_memory.recall 只有
    Chroma 里的旧快照或占位值），而合并时向量侧优先（`vec_results + kw_results`）——
    若不回填，凡被语义命中的记忆访问频率恒为 1.0、遗忘基准退化成 created_at。
    这里统一以 SQLite 为准，保证生产路径（recall_memories）拿到真实访问统计。
    """
    ids = []
    for m in memories:
        try:
            ids.append(int(m.get("id")))
        except (TypeError, ValueError):
            continue
    if not ids:
        return

    placeholders = ",".join("?" * len(ids))
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            f"SELECT id, access_count, last_accessed, owner, status "
            f"FROM memories WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
        conn.close()
    except sqlite3.Error as e:
        logger.error(f"[UserMemory] 回填访问统计失败: {e}")
        return

    by_id = {r[0]: r for r in rows}
    for m in memories:
        try:
            row = by_id.get(int(m.get("id")))
        except (TypeError, ValueError):
            row = None
        if row:
            m["access_count"] = row[1] or 0
            m["last_accessed"] = row[2]
            m["owner"] = row[3] or m.get("owner") or "主人"
            m["status"] = row[4] or "active"


def recall_memories(query: str, top_k: int = 5, owner: str | None = None) -> list[dict]:
    """
    混合召回：ChromaDB 语义召回（优先） + jieba 关键词召回（兜底）。

    - owner 缺省时按提问推断主体，只保留同一主体的记忆（隔离他人事实）。
    - 相关性阈值：distance 超阈值丢弃（user_memory.recall 内），再做"相对阈值"——
      只保留与最佳结果同档的记忆，宁缺毋滥；无候选时显式返回空并记日志。
    - 融合打分：distance 为主、importance 为辅（关键词路无 distance 给弱分）。
    """
    if owner is None:
        owner = _infer_query_owner(query)

    # === 1. 向量语义召回（取较大候选池，供后续过滤/重排）===
    vec_results = []
    try:
        vec_results = user_memory_rag.recall(
            query,
            top_k=RECALL_CANDIDATE_K,
            min_importance=1,
            max_distance=RECALL_MAX_DISTANCE,
        )
    except Exception as e:
        logger.error(f"[UserMemory] 召回失败: {e}")

    # === 2. jieba 关键词召回（兜底）===
    kw_results = _recall_by_keywords(query, top_k=RECALL_CANDIDATE_K)

    # === 3. 合并去重（id 为 key）===
    seen = set()
    merged = []
    for r in vec_results + kw_results:
        mid = str(r.get("id"))
        if mid and mid not in seen:
            seen.add(mid)
            merged.append(r)

    # === 3.5 回填权威字段：修正向量路缺失的 access_count/last_accessed/owner/status ===
    _enrich_from_sqlite(merged)

    # === 4. 主体过滤：只保留与提问主体一致的记忆 ===
    merged = [r for r in merged if (r.get("owner") or "主人") == owner]

    if not merged:
        logger.info("[UserMemory] 无候选记忆（语义路与关键词路均为空）")
        return []

    # === 5. 遗忘：时间衰减 × 访问频率，衰减过度的记忆视为过期 ===
    for m in merged:
        m["_recency"] = _recency_factor(m)
    merged = [m for m in merged if m["_recency"] >= RECALL_MIN_RECENCY]
    if not merged:
        logger.info("[UserMemory] 候选记忆均已衰减过期，显式返回空")
        return []

    # === 6. 融合打分：distance 为主、importance 为辅，再乘遗忘因子 ===
    def _score(m: dict) -> float:
        imp = m.get("importance", 0) / 10.0
        d = m.get("distance")
        base = 0.4 * imp if d is None else RECALL_W_DISTANCE * (1.0 - d) + RECALL_W_IMPORTANCE * imp
        return base * m["_recency"]

    for m in merged:
        m["_score"] = _score(m)
    merged.sort(key=lambda x: x["_score"], reverse=True)

    # === 7. 相对相关性阈值：只保留与最佳结果同档的记忆 ===
    best = merged[0]["_score"]
    kept = [m for m in merged if m["_score"] >= best - RECALL_SCORE_MARGIN]
    if not kept:
        logger.info("[UserMemory] 阈值过滤后无相关记忆，显式返回空")
        return []

    return kept[:top_k]


def update_accessed(memory_id: int):
    """更新最后访问时间并累加访问次数（召回后调用，供遗忘频率因子使用）"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "UPDATE memories SET last_accessed = ?, access_count = COALESCE(access_count, 0) + 1 WHERE id = ?",
        (datetime.now(), memory_id),
    )
    conn.commit()
    conn.close()


# 启动时自动建表
init_db()
