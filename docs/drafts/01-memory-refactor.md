# 我给 AI 桌宠的记忆系统做了一次重构

<!-- ↓↓↓ 编辑说明：发布前整段删除 ↓↓↓ -->

> **待补充清单（编辑用）**
>
> 1. **开头**：项目上线时长、累计对话轮次量级、当前记忆条数。用来交代"为什么现在才重构"。
> 2. **坑 1**：从 `logs/agent.log` 里挑一条最典型的实例——distance 很差但仍被注入 Prompt（grep 关键字 `[UserMemory]`）。有具体数字这段才有说服力。
> 3. **第三节（重构设计）**：这一节目前是**设计稿**，重构尚未合并到主分支。标题写了"做了一次重构"，如果发布时还没落地，建议改措辞（如"我在重构"，或先只发改前的版本）。
> 4. **第四节（还没做的）**：重构前后对比数据。至少两组——① 召回准确率（跑 `tests/eval/eval_memory.py` 的 before/after）；② 主观体感，比如"连续 10 轮对话里答非所问的次数"。
>
> 全文行号锚点基准为**重构前提交 `3bc471c`**（`main.py` 316 行 / `memory_service.py` 270 行 / `retrievers/user_memory.py` 105 行），已逐条与该提交核对、未越界。本文是"重构记"，§一/§二引的都是**重构前**的代码，故不随重构后的行号变动（`memory-refactor` 分支上 `memory_service.py` 已 516 行）。

<!-- ↑↑↑ 编辑说明：发布前整段删除 ↑↑↑ -->

先说结论：问题从来不是"记不住"，是"记了一堆没用的"。

这个项目叫希格雯桌宠——后端是 Python + FastAPI（入口 `main.py`），前端是一个 WPF 托盘程序（不在这个仓库里）。跑了几个月之后，用户最常反馈的不是"你怎么忘了"，而是"你记的这是啥"。这篇复盘写三件事：现在的记忆是怎么实现的、我踩到的三个坑、以及我正在替换的分层设计。

<!-- 待补充（真实数据）：项目上线时长、累计对话轮次量级、记忆条数。用来交代"为什么现在才重构"。 -->

## 一、现在的记忆是怎么工作的

### 两层存储 + 双写

长期记忆落在两个地方，靠 `store_memory` 一次写完（`memory_service.py:86-124`）：

```python
def store_memory(fact: str, keywords: list, importance: int = 5):
    fact = _normalize_fact(fact)
    conn = sqlite3.connect(DB_PATH)
    ...
    c.execute("""INSERT INTO memories (fact, keywords, importance, created_at, last_accessed)
                 VALUES (?, ?, ?, ?, ?)""", (...))
    memory_id = c.lastrowid          # :111
    ...
    try:                             # :116
        user_memory_rag.add_memory(memory_id=str(memory_id), fact=fact, ...)
    except Exception as e:
        logger.error(f"[UserMemory] 向量写入失败: {e}")   # :123-124
```

SQLite 存结构化字段（建表在 `memory_service.py:26-41`：`fact / keywords / importance / created_at / last_accessed`），ChromaDB 存向量（`retrievers/user_memory.py:16-25`，collection 名 `user_memories`，显式指定 cosine 度量）。

上面那个 `try` 只 log 不补偿——SQLite 写成功、向量写失败的时候，两边的记录数会静默不一致。三个月下来这种漂移有多少，我没统计过，但这是设计缺陷不是巧合。

短期上下文是另一张表，取最近 6 条原文（`test_api.py:39-50`）。

### 写入：让 LLM 抽事实

每轮回复生成完之后跑一次抽取（`main.py:204-208` 调 `extract_facts`）。Prompt 里的三条约束（`memory_service.py:48-52`）是整个系统里最像"有设计"的地方：

```
- keywords: 3-5 个关键词（JSON 数组）
- importance: 重要性 1-10（用户喜好/雷点给 8-10，闲聊给 3-5）
- 【禁止提取】天气、气温、温度、实时新闻、股价等时效性/实时信息，只提取长期有效的用户事实
只返回 JSON 数组……最多返回 3 条事实，每条事实控制在 50 字以内。
```

"最多 3 条、每条 50 字、禁止时效信息"——这是我认为写得最对的一段 prompt。

但写入之前有一次去重，实现是 Python 层的全表扫描（`memory_service.py:94-98`）：

```python
for row in c.execute("SELECT id, fact FROM memories"):      # 一次拉全表
    if _normalize_fact(row[1]) == fact:
        conn.close()
        logger.info(f"[UserMemory] 记忆已存在，跳过写入: {fact[:30]}...")
        return
```

归一化去标点再比较，逻辑本身是对的（防 `"用户喜欢喝奶茶。"` 和 `"用户喜欢喝奶茶"` 存成两条）。代价是**每写一条记忆就扫一遍全表**。几百条时无所谓，上万条时就是每轮对话都在做一次 O(n) 字符串比较。典型的"当时没想过会变大"的决定——不是错，是没设计。

### 召回：两路合并，然后按重要度硬排

`recall_memories`（`memory_service.py:229-254`）是整个系统的核心，也是麻烦的来源：

```python
vec_results = user_memory_rag.recall(query, top_k=3, min_importance=1)  # :236
kw_results = _recall_by_keywords(query, top_k=3)                         # :241

# 合并去重（id 为 key）
...
merged.sort(key=lambda x: x.get("importance", 0), reverse=True)          # :253
return merged[:top_k]
```

向量路取 3 条，关键词路取 3 条，合并去重后**按 importance 降序**，截 top_k（生产传 3，`main.py:173`）。

## 二、三个坑

### 坑 1：相关度在第 253 行被丢掉了

看上面 `:253` 那行。向量检索明明算出了 distance，`user_memory.py:77-79` 也老老实实把它塞进了返回结构里，但**排序用的是 importance，distance 从头到尾没参与决策**。

后果很直观：你问"我晚饭一般吃什么"，一条相似度很高但 importance=4 的"主人爱吃辣"会被 importance=9 的"主人对海鲜过敏"挤掉。系统把"重要的"当成了"相关的"，这是两件事。

再叠一层：`min_importance=1` 会让 `where_clause = None`（`user_memory.py:52-54`）：

```python
where_clause = {"importance": {"$gte": min_importance}} if min_importance > 1 else None
```

等于完全不过滤。所以向量路**无条件**塞 3 条进来，哪怕 distance 很差。

<!-- 待补充（真实日志）：从 logs/agent.log 里挑一条最典型的、distance 很差但仍被注入 Prompt 的实例（关键字 [UserMemory]）。有具体数字这段更有说服力。 -->

### 坑 2：一个 `1=1` 的兜底

关键词路（`memory_service.py:186-226`）是给 jieba 分词兜底的。但停用词表（`memory_service.py:128-163`）里包含这些：

```python
"喜欢", "记得", "知道", "什么", "怎么", "为什么", "想", "要", ...
```

口语提问经常被滤成空列表，然后走到 `memory_service.py:198-200`：

```python
else:
    conditions = "1=1"
    params = []
```

拼出来就是 `WHERE 1=1 ORDER BY importance DESC LIMIT 3`——**静默返回全表最重要的 3 条**。不报错、返回非空、日志里只记条数。你问"我喜欢什么来着"，系统把所有高重要度记忆一股脑塞进 Prompt。

这条路径最脏的地方是它没有受害者申诉渠道：用户只会觉得"这桌宠答非所问"，不会知道是 SQL 兜底干的好事。

### 坑 3：人格漂移 + 一个隐藏的状态机死锁

人格是一张只有一行的表（`personality_state.py:16-24`）：

```sql
CREATE TABLE IF NOT EXISTS personality (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    affinity INTEGER DEFAULT 0,
    emotion TEXT DEFAULT 'normal',
    emotion_momentum INTEGER DEFAULT 0,
    consecutive_positive INTEGER DEFAULT 0, ...
)
```

`CHECK (id = 1)`——全局单例，所有对话共享一个好感度、一个情绪。三个连带问题：

**（1）好感度非对称**（`personality_state.py:127-135`）：正面 `+2`，负面 `-10`。

```python
if sentiment > 0.5:
    self.affinity = min(100, self.affinity + 2); self.positive_count += 1
elif sentiment < -0.5:
    self.affinity = max(-100, self.affinity - 10)   # 负面记忆更深
```

当时的想法是"负面记忆更深"，实际效果是用户骂一句要夸五句才回本——桌宠显得记仇。而且 `_analyze_sentiment`（`personality_state.py:73-103`）每轮都要多调一次 LLM，成本直接翻倍。

**（2）状态机有个卡死的分支**（`personality_state.py:138-150`）：

```python
elif self.affinity < -20:
    self.emotion = "angry"
    self.momentum = max(self.momentum + 1, 3)   # 生气有惯性，至少3轮
elif self.affinity < -10:
    self.emotion = "sad"                         # ← 既不清零也不递减 momentum
else:
    self.momentum = max(0, self.momentum - 1)
    if self.momentum == 0 and self.emotion in ("angry", "sad"):
        self.emotion = "normal"                  # ← 回 normal 的唯一出口
```

`sad` 分支（affinity 落在 -20 ~ -10）**既不清零也不递减 momentum**，而恢复 `normal` 的唯一出口在 `else` 分支里。所以从 `angry` 平复到 `sad` 之后，只要 affinity 没回到 -10 以上，情绪就永远停在 `sad`。路径相关，光看单轮逻辑看不出来——这是我这轮最想记下来的一个 bug。

**（3）流式接口返回的是上一轮的情绪**（`main.py:247-248`）：

```python
if chunk["type"] == "meta":
    # 用旧状态（上一条消息后的值），流结束后再更新
    chunk["emotion"] = personality.emotion
    chunk["affection"] = personality.affinity
```

流式是先发 meta 包、再生成回复、最后才在 `_persist_chat` 里 `personality.update`（`main.py:233-234`）。前端看到的表情永远滞后一轮。

还有个基础事实得摆出来：`ChatRequest.session_id`（`schemas.py:7`）**收下就丢**，全项目只有定义处一次引用。"单用户单会话"不是疏忽，是从存储结构（`CHECK id=1`）到协议层一以贯之的。

## 三、我的重构设计：把"记忆"拆成三层

<!-- 待补充（进度）：这一节目前是设计稿，重构尚未合并到主分支。发布前请按实际进度改措辞；如果已经落地，把对比数据挪到第四节。 -->

现在的问题是所有记忆混在一个池子里，用同一个 `importance` 排序。我打算按"生命周期"分层：

**L1 会话缓冲**：最近 N 轮原文，直接进 Prompt，不退化成 fact。现在是 6 条（`main.py:167`）——稳定但薄，用户在第三轮之后追问"刚才那个"，就断了。

**L2 事实库**：就是现在的 `memories` 表，保留。改三处：

```python
# 现在
merged.sort(key=lambda x: x.get("importance", 0), reverse=True)   # memory_service.py:253
return merged[:top_k]

# 目标
score = w1 * (1 - distance) + w2 * (importance / 10) + w3 * decay(age)
# 并且：低于 relevance 阈值宁可返回空；删掉 1=1 兜底
```

**L3 情景摘要**：把一次会话压成一段摘要（"用户 9 月中旬连续几天提到加班"），而不是散成一堆单句 fact。这是完全缺失的一层，也是"上下文断裂"最直接的解法。

**遗忘**：现在 `user_memory.py:92-93` 定义了 `delete()` 但没有任何调用者。设计两条路并行：

- **时间衰减**：`decay = exp(-λ · days / half_life)`，让老记忆自然降权，而不是硬删
- **冲突覆盖**：写入时对"同一主体的不同取值"打失效标记（"住苏州" → "住南通"），而不是两条都留着等召回时打架

**人格去单例化**：`CHECK (id = 1)` 换成按 `user_id` 分区；补上 `sad` 分支的 momentum 递减；把情绪分析合并进主调用（用结构化输出一次拿情绪 + 回复），省掉每轮那次额外 API。

## 四、为什么不直接上现成的记忆框架

写到这儿肯定有人要问：mem0、Zep、Letta 这些不是现成的吗，为什么要自己写？

我评估过，暂时不换，三条理由：

**它们解决的核心问题我还没遇到。** 这些框架的卖点是自动管理记忆生命周期——去重、合并、语义冲突消解。而我现在的瓶颈在**召回排序**（`memory_service.py:253`）。换框架等于把排序权一起交出去，那我还得重新理解一套黑盒的排序逻辑。我缺的是"看得见的排序公式"，不是"更聪明的合并"。

**依赖成本会失控。** 现在真正跑起来的第三方依赖只有三个：`chromadb`、`jieba`、`openai`。但 `requirements.txt` 里塞了 154 行——`langchain==1.2.15`（:50）、`langgraph==1.1.9`（:53）、`gradio==6.13.0`（:26）、`torch==2.12.0`（:138）、`cuda-toolkit==13.0.2`（:17）、`onnxruntime==1.26.0`（:82），首方代码里一行 import 都没有。已经这么臃肿了，再叠一个记忆框架的抽象层，以后排查问题得先穿过三层封装。

**这是求职作品。** 面试官问"你的记忆系统怎么做的"，我能指着 `recall_memories` 讲清每一行的取舍；如果答案是"我用了 mem0"，这道题就废了。

反过来也成立：哪天要做多用户、多会话，或者记忆量到万级，自己维护这套的边际成本会超过框架——那时候该换就换。现在不换，是因为"自己写"这件事在当前阶段同时满足了学习和展示两个需求。

## 五、还没做的

- 摘要层（L3）没动手，`extract_facts` 现在还是只产单句。
- 时间衰减的 `half_life` 取多少，我没有数据支撑，得靠评测集调。没有评测集就调这个参数，等于瞎猜。
- 人格表加 `user_id` 是破坏性 schema 变更，现有 `chat.db` 需要迁移脚本。
- 双写的补偿逻辑没写——现在向量写失败还是只有一行 log。

<!-- 待补充（真实数据）：重构前后对比。至少给两组：① 召回准确率（跑 tests/eval/eval_memory.py 的 before/after）；② 主观体感，比如"连续 10 轮对话里答非所问的次数"。 -->

写这篇的目的不是"我重构得漂亮"。是想记下来一条：**RAG 的坑基本不在向量库选型上，在"合并排序"和"兜底路径"这些看不出问题的角落。** 上面第 253 行和第 199 行那两处，都是能跑、不报错、看起来还有结果的那种 bug。
