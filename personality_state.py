import sqlite3
import json
from datetime import datetime
from memory_service import client  # 复用已有的DeepSeek客户端

DB_PATH = "chat.db"

def init_personality_db():
    """建 personality 表，只存一行（当前状态）"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS personality (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            affinity INTEGER DEFAULT 0,
            emotion TEXT DEFAULT 'normal',
            emotion_momentum INTEGER DEFAULT 0,
            consecutive_positive INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # 初始化插入一行（如果还没有）
    c.execute("INSERT OR IGNORE INTO personality (id) VALUES (1)")
    conn.commit()
    conn.close()

class PersonalityState:
    def __init__(self):
        init_personality_db()
        # 从SQLite加载状态到self
        self.affinity, self.emotion, self.momentum, self.positive_count = self._load()
    
    def _load(self):
        """从数据库加载状态"""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            SELECT affinity, emotion, emotion_momentum, consecutive_positive 
            FROM personality WHERE id=1
        """)
        row = c.fetchone()
        conn.close()
        if row:
            return row[0], row[1], row[2], row[3]
        return 0, "normal", 0, 0
    
    def _save(self):
        """把self当前状态写回SQLite"""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
                  UPDATE personality
                  SET affinity=?,emotion=?,emotion_momentum=?,consecutive_positive=?,updated_at=?
                  WHERE id=1
                  """,(self.affinity,self.emotion,self.momentum,self.positive_count,datetime.now()))
        conn.commit()
        conn.close()

    def _analyze_sentiment(self, user_msg: str) -> float:
        """调DeepSeek分析用户情绪倾向，返回-1.0到1.0"""
        prompt = f"""分析以下用户消息的情绪倾向，只返回纯JSON：{{"sentiment": 0.5}}
范围：-1.0（极度负面）到 1.0（极度正面）。
只输出JSON，不要任何解释。

消息：{user_msg}"""

        response = client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[
                {"role": "system", "content": "你是情绪分析助手，只输出JSON。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=100
        )

        content = response.choices[0].message.content.strip()
        content = content.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

        try:
            data = json.loads(content)
            return float(data.get("sentiment", 0))
        except (json.JSONDecodeError, ValueError):
            return 0.0
    
    def build_system_prompt(self) -> str:
        """根据当前情绪拼System Prompt"""
        lines = [
            f"你是希格雯，当前情绪：{self.emotion}，对主人好感度：{self.affinity}。",
        ]

        if self.emotion == "happy":
            lines.append("语气活泼，带颜文字，主动关心主人~")
        elif self.emotion == "sad":
            lines.append("语气低落，简短回复，偶尔撒娇求关注...")
        elif self.emotion == "angry":
            lines.append("语气冷淡，带刺，需要主人哄才会好转。")
        else:  # normal
            lines.append("语气温柔，像平常一样陪伴主人。")

        return "\n".join(lines)
    
    def update(self, user_msg: str):
        """核心：分析情绪→更新好感度→确定情绪→存库"""
        sentiment = self._analyze_sentiment(user_msg)

        # 1. 更新好感度（负面偏差：下降比上升快）
        if sentiment > 0.5:
            self.affinity = min(100, self.affinity + 2)
            self.positive_count += 1
        elif sentiment < -0.5:
            self.affinity = max(-100, self.affinity - 10)  # 负面记忆更深
            self.positive_count = 0
        else:
            # 中性，连续正面计数不变
            pass

        # 2. 情绪阈值 + 惯性判断
        if self.affinity > 30 and self.positive_count >= 2:
            self.emotion = "happy"
            self.momentum = 0
        elif self.affinity < -20:
            self.emotion = "angry"
            self.momentum = max(self.momentum + 1, 3)  # 生气有惯性，至少3轮
        elif self.affinity < -10:
            self.emotion = "sad"
        else:
            # 慢慢平复
            self.momentum = max(0, self.momentum - 1)
            if self.momentum == 0 and self.emotion in ("angry", "sad"):
                self.emotion = "normal"

        # 3. 持久化
        self._save()