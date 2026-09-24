# 希格雯桌宠 — 面试深挖题库（50 题）

> 定位：以"资深 AI 应用工程师面试官"视角，针对本仓库真实实现出题。
> 锚点基准：**rev4**（2026-09-24，记忆系统重构 + 人格死锁修复）。`main.py` = 316 行、`memory_service.py` = 459 行、`agent.py` = 273 行、`personality_state.py` = 166 行、`schemas.py` = 21 行、`retrievers/user_memory.py` = 128 行、`retrievers/anime_kb.py` = 70 行、`init_anime_kb.py` = 845 行（92 条文档）。
> 代码改动后行号会漂，重算方法见 `PROJECT_BRIEF.md` §9。
> 🔥 = 压力题，共 **10** 个（索引见文末）。压力题的共同特征：**答"有"就露馅，正确答法通常是先纠正题目前提**。
> 所有"实测"均可在 `logs/agent.log`（573 行）与 `chroma_db/`、`chat.db` 里复核。
> **rev4 变更摘要**：记忆召回从"importance 硬排"改为"distance 融合重排 + 相关性阈值 + 主体过滤 + 遗忘机制"，评测总准确率 60.8% → 98.3%（五分类：事实/长上下文/情感/干扰项均 100%，遗忘 91.7%）；修复 `personality_state.py` 的 sad 死锁。受影响题目已逐条改写：Q2、Q4、Q7、Q10、Q11、Q20、Q29、Q50。

| 分组 | 题号 | 压力题 |
|---|---|---|
| A 记忆系统 | Q1–Q12 | Q4、Q7、Q11 |
| B RAG | Q13–Q22 | Q16、Q20 |
| C 情绪建模 | Q23–Q30 | Q25、Q28 |
| D 工程取舍 | Q31–Q42 | Q35、Q40 |
| E 部署运维 | Q43–Q50 | Q47 |

---

## A. 记忆系统（Q1–Q12）

### Q1｜短期记忆为什么要单独落 `messages` 表？取 6 条、按什么排序？
**锚点**：`test_api.py:39-50`、`main.py:167`
- **考察意图**：能否区分"工作记忆"与"长期记忆"，并说清参数来源而非背概念。
- **答题要点**：
  - `get_recent_messages(limit=6)` 的 docstring 直接写明"3 轮对话=6 条"（`test_api.py:40`），是**消息条数**不是轮数；`ORDER BY created_at DESC LIMIT ?` 取最新 6 条后 `reversed()` 还原成"旧→新"（`test_api.py:44-50`）。
  - `created_at` 是 `datetime.now().isoformat()` 文本（`test_api.py:34`），排序靠**字符串比较**——isoformat 恰好可字典序排序，所以能工作，但这是"格式红利"不是设计保证。
  - 注入方式是把 6 条拼成一段文本塞进 System Prompt（`main.py:168-170`），**不是** messages 数组的 role 交替——模型只能看到"user: xxx / assistant: xxx"的纯文本。这是可质疑点：真实对话轮次结构被抹平，也没有窗口截断策略（第 7 轮之后历史硬切，不带摘要）。
  - `messages` 表无 `session_id`、无清理、永久堆积（`schemas.py:7` 的 `session_id` 收下即丢）。

### Q2｜长期记忆为什么要 SQLite + Chroma 双写？两边各存什么？
**锚点**：`memory_service.py:178-277`、`retrievers/user_memory.py:27-49`
- **考察意图**：向量库与关系库的职责边界，以及双写一致性的代价意识。
- **答题要点**：
  - SQLite `memories` 是**权威源**：`fact/keywords/importance/owner/status/access_count/created_at/last_accessed`（`memory_service.py:30-46`），带去重、去排序、供关键词 LIKE 检索。`owner`（主人/他人）、`status`（active/superseded/expired）、`access_count` 是 rev4 记忆重构新增的列，旧库通过 `PRAGMA table_info` + `ALTER TABLE` 幂等迁移补列。
  - Chroma `user_memories` 是**派生的向量索引**：只存 `documents=[fact]` + metadata（含 `owner`，`user_memory.py:37-50`），用于语义召回。
  - 顺序是"先 SQLite 拿 `lastrowid`（`:232`）→ 再用 `str(memory_id)` 写 Chroma"，id 是两边的唯一关联键。这也解释了召回侧为什么要 `str(r.get("id"))` 统一类型：向量路 id 是 str、关键词路是 int。
  - 代价：Chroma 写失败只 `logger.error` 不补偿，两边可能长期漂移；没有事务、没有对账任务。rev4 的"冲突覆盖/时效软删除"会**同时**改 SQLite `status` 并 `user_memory.delete()` 撤出向量，但仍是两步非事务操作。

### Q3｜写入去重为什么用"全表逐行比对"？这样写有什么问题？
**锚点**：`memory_service.py:81-83, 94-98`
- **考察意图**：是否看得见 O(n) 与原子性。
- **答题要点**：
  - `_normalize_fact` 只剥末尾标点（`rstrip("。！？，,.!?;；:： \t\n")`），解决"喝奶茶。"≠"喝奶茶"，但归一化规则是**应用层**的，无法用 `UNIQUE(fact)` 约束表达。
  - 于是退化成 `SELECT id, fact FROM memories` 全表扫描 + Python 侧逐行比较（`:94-98`）——每写一条 O(n)（实测 `chat.db` 里仅 4 条记忆，量级压力未暴露）。
  - 更硬的缺陷：**check-then-act 非原子**。并发两次相同写入都可能通过检查再各插一行（无唯一索引兜底）。正解是加 `normalized_fact` 列 + `UNIQUE` 索引，或 `INSERT ... ON CONFLICT DO NOTHING`，把归一化下沉到写入路径。

### Q4｜🔥 压力题｜`_recall_by_keywords` 里的 `1=1` 兜底是什么？什么时候走到？后果多严重？
**锚点**：`memory_service.py:299-320`（rev4 已修复）
- **考察意图**：能不能发现/讲清这条"看起来有召回、实际无相关性"的隐蔽路径——它曾是本系统最脏的一段代码。
- **答题要点**：
  - **先纠正前提（若被问"现在还有没有"）**：rev4 记忆重构已删除该兜底。旧实现：query 分词 → 过滤停用词/长度/纯符号 → **若 `keywords` 为空，则 `conditions = "1=1"`**，f-string 拼进 SQL 后成为 `WHERE 1=1 ORDER BY importance DESC, last_accessed DESC LIMIT 3`，**返回整表"最重要+最近访问"的 3 条**，与 query 完全无关。
  - 触发门槛极低：停用词表把"喜欢/记得/知道/告诉/什么/怎么/为什么/我/你/吗/呢"全滤掉，"你记得我喜欢什么吗？"这类**口语短问句**几乎必然被滤空 → 静默返回高权重随机记忆。危险在于它**不报错、不返回空、日志看不出异常**，现象上完全像"召回到了有用的东西"。
  - **当前实现**：`if not keywords: return []` 并打 `[UserMemory] 关键词路无有效词，显式返回空` 日志；召回主链 `recall_memories` 在两路都为空时显式返回 `[]` 并记 `无候选记忆`。关键词路 SQL 同时加了 `AND status='active'`。
  - 可延伸：关键词路仍按 `ORDER BY importance` 排序（未做独立相关性重排），但它现在是**兜底**且结果会并入 `recall_memories` 的融合重排，所以"importance 当相关性"的残留问题只影响兜底路。

### Q5｜向量路和关键词路为什么用 id 去重而不是文本去重？哪一路优先？
**锚点**：`memory_service.py:243-250`
- **考察意图**：对"同一实体两路命中"的理解。
- **答题要点**：
  - 同一条记忆天然会被两路同时召回（Chroma 的 id 就是 SQLite 主键的字符串形式），文本可能有细微差异（Chroma 侧存归一化后的 fact），所以必须靠 **id 判等**；`str()` 转换是为了抹平"向量路 str / 关键词路 int"的类型差（`:247`）。
  - 顺序 `for r in vec_results + kw_results`（`:246`）→ 向量结果先入 `merged`，`seen` 只是防重，所以"向量优先"体现为**合并顺序**。
  - **但要说清这个优先只在去重阶段有效**：紧接着 `merged.sort(key=importance, reverse=True)`（`:253`）把顺序彻底重排，向量的相关性序被抹掉。所以"向量优先、关键词兜底"这个描述**只在两条路都拿到候选时才成立**，最终谁进 top3 由 importance 决定。

### Q6｜为什么要跑两路召回？各自补了什么短板？
**锚点**：`memory_service.py:229-241`、`logs/agent.log:47`
- **考察意图**：检索架构的设计动机。
- **答题要点**：
  - 语义路（`user_memory_rag.recall`，`:236`）解决同义表达："我平时喝什么饮料"→"主人喜欢喝奶茶"。
  - 关键词路（`_recall_by_keywords`，`:241`）解决专名/精确词——bge-small-zh 是 512 维小模型，对极短 query 和生僻专名召回弱（日志实证：`"我是ZZDW"` 召回出"日文名/韩文名/英文名"三条，语义路被短查询稀释）。
  - 成本：每轮一次 embedding 编码（CPU 上 ms~百 ms 级）+ 一次全表 `LIKE` 扫描 ×N 个关键词（`:194-200` 把每个词展开成两个 LIKE 条件）。
  - 可质疑点：两路都只取 top3、合并最多 6 条再截 3（`:236,241,254`），**候选池太小**，没有给重排留空间。

### Q7｜🔥 压力题｜合并后按 `importance` 硬排，为什么这是本系统最核心的检索缺陷？
**锚点**：`memory_service.py:374-444`（rev4 已修复）
- **考察意图**：能否指出"采集了相关性指标却不用它做决策"这一典型失误。
- **答题要点**：
  - **先纠正前提（若被问"现在还是不是"）**：rev4 已改为 distance 为主的融合重排。旧实现是 `merged.sort(key=importance, reverse=True)` 后 `[:top_k]`——`importance` 是写入时 LLM 自评的重要性，与"这条记忆和本轮问题有多相关"完全无关；一条 `importance=9` 的无关记忆会挤掉 `importance=6` 的真正命中项。而 `user_memory.recall` 明明把 `distances` 取出来了，却从不参与任何决策。
  - **当前实现**（`recall_memories`）：
    1. 向量路取候选池 `RECALL_CANDIDATE_K=15`，`user_memory.recall(max_distance=RECALL_MAX_DISTANCE=0.8)` 先做**绝对阈值**过滤，超阈值直接丢；
    2. 合并去重后按 `score = 0.9·(1-distance) + 0.1·(importance/10)` 融合打分（distance 为主、importance 仅做 tie-break），再乘遗忘因子 `_recency_factor`；
    3. 做**相对阈值**——只保留与最佳结果分差在 `RECALL_SCORE_MARGIN=0.08` 内的记忆，宁缺毋滥；
    4. 无候选或全被过滤时**显式返回空**并记日志。
  - 效果（`tests/eval/eval_report.md`）：干扰项类 4.2% → 100%，总准确率 60.8% → 98.3%。
  - 可质疑点（诚实说）：相对阈值 + 单候选倾向会让"平均召回条数"下降，是**用 recall 换 precision**；权重与阈值是经验值，缺数据支撑，记忆规模上去后要重调；`importance` 仍以 0.1 的权重参与，并非完全移除。

### Q8｜`store_memory` 里 SQLite 与 Chroma 的写入顺序能反过来吗？
**锚点**：`memory_service.py:90-124`
- **考察意图**：一致性设计的推理能力。
- **答题要点**：
  - 不能轻易反。当前顺序的前提是"SQLite 自增主键作为两库关联键"：先 `INSERT` 拿 `lastrowid`（`:111`），才能用它当 Chroma 的 `ids`（`:118`）。
  - 反过来做，要么自己生成 UUID 与 SQLite 主键脱钩（召回时 `update_accessed(m["id"])` 就得用 UUID 反查，`main.py:180`→`memory_service.py:257-266` 全链路要改），要么在 Chroma 失败时回滚 SQLite（当前无事务）。
  - 现顺序的残留风险：SQLite 成功、Chroma 失败 → 记忆**只能被关键词路召回**，语义路永远看不到；无对账、无重试。可提出的方案：把双写做成"先写 SQLite 并标记 `indexed=0`，后台任务补索引"（变同步双写为最终一致）。

### Q9｜记忆注入的那句强指令有什么设计意图？有什么风险？
**锚点**：`main.py:175-178`
- **考察意图**：Prompt 工程手法的收益与副作用。
- **答题要点**：
  - 原文：`【以下是你必须记住的关于主人的事实，回答用户关于自身的问题时必须优先使用】`。意图有二：压制模型"我不知道/我不记得"的默认行为；把用户事实的优先级提到角色设定之上（避免被 RAG 的设定段覆盖）。
  - 风险：**无条件注入**——`if memories:` 只判空不判相关性（`main.py:174`），只要 `recall_memories` 返回非空（哪怕 3 条全是噪声，见 Q4/Q7），模型就被要求"必须优先使用"。
  - 没有"本轮无可用记忆"的显式信号，也没有让模型自评"这些记忆跟问题有关吗"的机会。改进：给每条记忆附 `distance`/重要性，让模型自行取舍；或干脆把指令弱化成"以下是一些可能相关的背景"。

### Q10｜召回后 `update_accessed` 到底起什么作用？它在排序里有隐性影响吗？
**锚点**：`main.py:179-180`、`memory_service.py:446-456, 356-372`
- **考察意图**：是否愿意追一个小字段的真实影响力，而不是当它"没用"。
- **答题要点**：
  - 写入：每轮对**进入 Prompt 的每条记忆**逐条 `update_accessed`（`main.py:180`），无批量、无节流，N 条记忆就是 N 次 SQLite 连接开关。rev4 起它**同时累加 `access_count`**：`UPDATE memories SET last_accessed=?, access_count=COALESCE(access_count,0)+1`。
  - 隐性影响一：关键词路 SQL 仍是 `ORDER BY importance DESC, last_accessed DESC`——同分候选里"刚被访问过的优先"。
  - 隐性影响二（rev4 新增）：遗忘因子 `_recency_factor = exp(-λ·天数) × (1+ln(1+access_count))`——`last_accessed` 决定**时间衰减**、`access_count` 提供**访问频率加成**。也就是说，它现在真的会驱动"遗忘/降权"：久未访问的记忆衰减，高频访问的记忆更抗遗忘。
  - 需要指出的副作用：频率加成会强化**马太效应**（越被取用越容易被取用），当前没有对 `access_count` 的上限约束，长期可能让少数记忆垄断召回。
  - 对比 rev3：那时 `last_accessed` 只写不参与淘汰，净效果仅是"同分时热点优先"；rev4 才第一次把它接进遗忘决策。

### Q11｜🔥 压力题｜遗忘机制里的衰减函数为什么这么选？
**锚点**：`memory_service.py:96-176, 356-372, 374-444`（rev4 已实现遗忘）
- **考察意图**：**这道题曾是前提错误题**（rev3 及以前无遗忘机制）。rev4 已实现遗忘，考的是能否讲清"为什么不能只靠时间衰减、必须引入时效标记"。
- **答题要点**：
  - **先说明旧前提已变**：rev3 无任何遗忘/衰减/覆盖；`user_memory.delete()` 定义后无调用者、`min_importance` 恒传 1 等于不过滤、`importance` 只用于排序——这些旧证据已成历史。
  - **当前实现（三条路并行）**：
    1. **时效标记软删除（主力）**：写入时 `_is_expired_fact` 命中过去时效词（`以前/之前/曾经/去年/上个月/上周/上周末/昨天/前天/过去`…）的事实，直接写 `status='expired'` 且**不进向量库**（软删除，SQLite 留痕）。覆盖"旧值已过去/已失效"。
    2. **冲突覆盖**：新事实带"现状"标记（`已经/现在/换成/搬到/转岗/戒了/买好/决定不`…）且与同主体旧记忆共享关键词时，旧记忆置 `status='superseded'` 并调 `user_memory.delete()` 撤出向量库——`delete()` 终于有了调用者。
    3. **时间衰减 × 访问频率**：`_recency_factor = exp(-λ·days) × (1+ln(1+access_count))`（λ=0.05/天），低于 `RECALL_MIN_RECENCY` 视为过期；召回时排除 `status!='active'`。
  - **关键设计判断（加分点）**：为什么不能只靠时间衰减？因为**评测集的 120 条用例在同一瞬间写入**，`exp(-λ·Δt)=1` 对所有记忆成立，纯时间衰减在评测里**恒等无效**。真正能区分"过期事实"的信号是**文本里的时效标记**——这是"评测约束倒逼设计"的真实案例。
  - 效果：遗忘类 0% → 91.7%（24 条里 22 条通过；剩 2 条是判定子串假阳性，见 Q20）。
  - 诚实缺口：时效标记是**启发式**，可能误伤（如"我以前是军人，所以很自律"会被判过期）；没有把 TTL/λ 配置化；`status` 更新与 Chroma 删除仍是两步非事务操作。

### Q12｜同一轮里，人格、历史、记忆三份上下文的时间基准一致吗？meta 包内部呢？
**锚点**：`main.py:167, 173, 198, 247-248, 212-213`
- **考察意图**：时序语义的敏感度——这是分布式/流式系统里最容易错的地方。
- **答题要点**：
  - **上下文侧是一致的**：`_build_chat_context` 在生成前一次性组装（`main.py:162-187`），历史取"上一轮结束前存下的 6 条"（`save_message` 发生在之后，见 `main.py:201-202` / 流式的 `:224-225`），记忆是本轮新查的，人格是进入本轮前的状态——三者语义都能解释为"本轮开始时的世界快照"，**没有矛盾**。
  - **meta 包内部不一致**：同一个 meta 里 `emotion`/`affection` 是**本轮更新前**的值（`main.py:246-248` 注释明说用旧状态、流结束后才 `personality.update`，`:234`），而 `recalled_memories` 是**本轮**召回的（`:249`）。两个时间基准混在一个对象里（已在 `PROJECT_BRIEF.md` §5 固化为契约）。
  - **额外发现（文档里还没记的一条）**：`/chat` 与 `/chat/stream` 对**同一组字段**的时间基准不同——非流式在 `_handle_chat` 内同步调 `personality.update(msg)`（`:198`）后再取 `personality.emotion/affinity` 返回（`:212-213`），所以给的是**本轮更新后**的值；流式给的是**本轮更新前**的值。客户端若同时用两个接口（比如先用 `/chat` 调试再用 `/chat/stream` 上线），会看到"情绪跳变时机不同"的诡异现象。建议：统一成"meta 描述进入本轮前的状态"并在两侧都遵守，或给字段改名（`emotion_before`）。

---

## B. RAG（Q13–Q22）

### Q13｜知识库为什么是 92 条单属性短句，而不是长文档 + 自动切分？
**锚点**：`init_anime_kb.py:5-845`
- **考察意图**：分块策略的选择依据。
- **答题要点**：
  - 结构：`docs = [{id, content, metadata{category, source, tags}}]`，每条 content 是一句独立属性（如 `init_anime_kb.py:172` = `"希格雯的发色是蓝色。"`、`:262` = `"希格雯有呆毛。"`），845 行硬编码，共 92 条。
  - **没有自动切分**：全仓无 splitter / chunk_size / overlap 相关实现。粒度靠**人工写句子**控制。
  - 收益：① 每条语义单一 → embedding 不被长文稀释；② 天然适合"一问一属性"的召回；③ metadata 的 category/tags 可以精确过滤。
  - 代价：① 知识规模靠手写，不可扩展到长文档（要知道"她的老师是谁"需要人工拆成一条）；② 跨条推理丢失（模型拿到 3 条孤立句子，缺上下文连接）；③ 无法表达"同一实体多属性聚合"（"介绍一下你自己"需要命中多条）。
  - 可以作为主动亮点讲：**用"数据形态"替代"分块工程"**，在 92 条这个量级是合理的省事选择，量级上去后必须换 RAG 分块 + 重排。

### Q14｜`AnimeRAG.retrieve` 只返回文档文本，这样写丢了什么？
**锚点**：`retrievers/anime_kb.py:49-54`
- **考察意图**：检索器接口设计能力。
- **答题要点**：
  - `return results["documents"][0]` —— 把 Chroma 返回的 `ids` / `distances` / `metadatas` **全部丢掉**，调用侧只拿到 `list[str]`。
  - 丢了四样能力：① 相关性阈值过滤（没有 distance 就无法"低于阈值不注入"）；② 重排（无分可排）；③ 观测（日志只能打印命中条数，`main.py:132-135` 无法打印相似度）；④ 溯源（source 字段拿不到，无法做引用标注）。
  - **同项目内接口能力不一致**：`user_memory.recall` 至少把 `distance` 带出来了（`user_memory.py:70-81`），`AnimeRAG.retrieve` 没有——两个检索器应该统一返回 `list[dict]`。这是"设计基线不统一"的直接体现，改动成本低、收益明确。

### Q15｜tag 召回是怎么实现的？为什么日志里绝大多数是"无"？
**锚点**：`main.py:122-135`、`retrievers/anime_kb.py:63-70`
- **考察意图**：能否既讲机制、又把"命中率极低"讲精确（不许说"从不命中"这种绝对化表述）。
- **答题要点**：
  - 机制：`hit_tags = [t for t in anime_rag.get_all_tags() if t in msg]`（`main.py:125`）——取知识库**全部 tag**（`get_all_tags` 每轮 `collection.get(include=["metadatas"])` 全量拉 92 条文档元数据再聚合，`anime_kb.py:63-70`），做**子串匹配**；命中的 tag 各追加一次 `retrieve(msg, top_k=2, tag=t)`（`main.py:127-128`），最后 `dict.fromkeys(rag_docs + extra_docs)` 去重保序（`:131`）。
  - 为什么命中率低：tag 词表是**知识库自述词**——"名字/外文名/日文名/生日/身份/作品/原神"（`init_anime_kb.py:13-58` 等）。用户真实提问是"你叫啥""你生日几号""你是谁做的"，几乎不会逐字出现这些 tag。**词表与用户语言之间没有映射层。**
  - **精确表述（别说"从不命中"）**：`logs/agent.log` 573 行中 tag 命中出现过 2 次——第 65 行 `tag命中 ['美露莘']`、第 84 行 `tag命中 ['女']`，其余全部为"无"。所以是"命中率极低，且命中的是偶然词"，不是"机制完全没跑"。
  - 顺带的成本问题：`get_all_tags()` 每轮全量拉 metadata（O(知识库规模)），换来的收益是"极低概率命中"——**性价比为负**，应该缓存 tag 集合或在建库时物化。

### Q16｜🔥 压力题｜tag 用 `t in msg` 子串匹配，会踩什么真实坑？举本项目的例子。
**锚点**：`main.py:125`、`anime_kb.py:44`、`init_anime_kb.py:49`、`logs/agent.log:84`
- **考察意图**：能否从"看起来没问题的两行代码"里找出脏命中——这类噪声往往被当成正常召回，极难定位。
- **答题要点**：
  - 知识库里存在**单字 tag**：`"tags": ["性别", "女"]`（`init_anime_kb.py:49`）。于是**任何含"女"字的用户消息**都会触发 tag 过滤：`hit_tags = ['女']` → `retrieve(msg, top_k=2, tag="女")` → 走 `where_clause["tags"] = {"$contains": "女"}`（`anime_kb.py:44`）→ **强制只在"性别=女"的文档里搜**。
  - 后果：把与 query 无关的性别文档强行塞进 Prompt，同时还**压缩了真正相关文档的名额**（`top_k=2` 只在那一个 tag 子集里取）。"女仆""圣女""少女"这类词全部会误触发。
  - 这是有**日志实录**的：`logs/agent.log:84` 记 `[RAG] 语义命中 3 条, tag命中 ['女'], tag补充 1 条, 最终注入 4 条`。
  - 修法：① tag 白名单化，只允许长度 ≥2 的多字 tag（`名字`、`美露莘`）；② 改成词边界/正则匹配而非裸 `in`；③ 更彻底：用分类器或 LLM 抽 slot 后再查 metadata，或干脆**删掉这条召回路径**（收益本就极低，见 Q15）；④ 给 `retrieve` 加 `where` 组合校验，禁止单字 tag。
  - 加分点：这题的解法不是"修匹配"，而是**先问"这条路径值不值得留"**——一个命中率极低、误命中成本不低的补充召回，最理性的处置是砍掉，把精力放在真正缺的重排上（Q7）。

### Q17｜`dict.fromkeys` 合并去重有什么隐含约定？
**锚点**：`main.py:131`
- **考察意图**：小技巧背后的语义假设。
- **答题要点**：
  - `list(dict.fromkeys(rag_docs + extra_docs))` 用 dict 键去重且保插入序（Python 3.7+ 语言保证）。语义是"**先语义后 tag，且保序 = 语义优先**"——与 Q5 里向量/关键词的合并思路一致。
  - 隐含风险：合并结果**没有总量上限**。命中 N 个 tag 就是 `3 + 2N` 条（`:122,128`），每条一到两句 → 命中 5 个 tag 就有 13 条设定文本进 System Prompt，Token 无界增长、上下文被角色设定挤爆（挤掉历史与记忆的注意力）。
  - 建议：`all_docs[:MAX_DOCS]` 硬上限 + 按 score 排序后再截断（前提是 `retrieve` 得先返回 score，见 Q14）。

### Q18｜无命中时 `_build_rag_context` 返回空串、上层用 `if rag_text:` 判断，这个写法好在哪？
**锚点**：`main.py:137-139, 183-185`
- **考察意图**：能否识别"空值不产生副作用"的一致性约定。
- **答题要点**：
  - 好处：避免拼接出 `【角色设定资料】\n` 这种**只有标题没有内容**的 prompt 段落。空标题会诱使模型编造内容（"根据角色设定资料……"），是真实的 prompt 污染源。
  - 同一约定在记忆注入处也成立：`if memories:` 才拼 `memory_text`（`main.py:174-178`），人格与历史同理（`:168`、`build_system_prompt` 恒有内容）。
  - 可以补充的质疑：**没有给模型"本轮无设定资料"的显式信号**，模型无法区分"没有相关资料"和"资料为空"。更稳的写法是注入一句显式占位（"（本轮无相关角色设定资料，请基于已知常识回答，不要编造设定）"），把"空"变成可被模型消费的语义。这是"沉默的空" vs "显式的空"的取舍，值得主动展开。

### Q19｜`anime_kb` 和 `user_memories` 的距离度量不一致，会造成什么？
**锚点**：`anime_kb.py:16-18` vs `user_memory.py:21-25`；实测 `chroma_db/chroma.sqlite3`
- **考察意图**：向量库配置细节 + 是否真的动手验证过。
- **答题要点**：
  - `user_memories` 显式声明 `metadata={"hnsw:space": "cosine"}`（`user_memory.py:24`）；`anime_kb` 建 collection 时**没传 metadata**（`anime_kb.py:16-18`）→ 走 Chroma 默认 **L2**。
  - 实测证据（只读快照 `chroma_db/chroma.sqlite3`）：`collections` 表两行（`user_memories`、`anime_kb`），但 `collection_metadata` 表**只有 1 行**，属于 `user_memories`（`hnsw:space = cosine`）。→ anime_kb 确实是无配置的默认度量。
  - 影响：两个库吐出的 `distance` **量纲不同**（L2 是欧氏距离、cosine 距离是 1−相似度），不可比、不能套同一个阈值。当前"看起来没事"**只因为两边都没用 distance**（见 Q7/Q14）——一旦引入统一阈值或跨库重排，必须先统一 metric，否则会得到一个静默错误的过滤线。
  - 修法是建成时指定（`metadata={"hnsw:space":"cosine"}`），已有 collection 需要重建（Chroma 不支持改 space）。
  - 顺带：仓库里并存两份库（`chroma_db/` 96 条 embedding vs `data/chroma_db/` 94 条），说明"相对路径 + 启动目录不同"已经真实产生过数据分叉（见 Q48）。

### Q20｜🔥 压力题｜RAG 的检索准确率是多少？怎么测的？
**锚点**：`tests/eval/eval_report.md`、`tests/eval/eval_memory.py`、`logs/agent.log`
- **考察意图**：经典"你有没有量化过效果"压力题。考的是**分层诚实的表达能力**，不是有没有数字。
- **答题要点**：
  - **第一步：分开回答"RAG"和"记忆召回"，别混为一谈。**
    - **角色设定 RAG（anime_kb）：没有任何量化评测。** 全仓无 RAG 评测脚本、无标注集、无 hit rate / MRR。已有的只是**运行日志观测**：`[RAG] 语义命中 N 条, tag命中 [...], 最终注入 N 条`——这是"能看见"，不是"测过"。
    - **用户记忆召回：已有真实评测结果。** 用例集 `tests/eval/memory_recall_cases.json`（120 条 = 5 类 × 24）+ 脚本 `tests/eval/eval_memory.py`（输出总/分类准确率、延迟分位、token，写 `eval_report.md`）。
  - **第二步：给出真实数字与 before/after。** `tests/eval/eval_report.md` 现为 **real 后端（ChromaDB + bge-small-zh-v1.5）真实结果**（旧 stub 版已废弃，其 52.5% 不可引用）。rev4 记忆重构前后：

    | 类别 | 重构前 | 重构后 |
    |---|---|---|
    | 事实记忆 fact_recall | 100.0% | 100.0% |
    | 多轮上下文 long_context | 100.0% | 100.0% |
    | 情感记忆 emotion_memory | 100.0% | 100.0% |
    | 干扰项 distractor | 4.2% | 100.0% |
    | 遗忘验证 forgetting | 0.0% | 91.7% |
    | **总准确率** | **60.8%** | **98.3%** |

  - **第三步：给出复现命令与三层评测路线。** 真实结果一条命令：`HF_HUB_OFFLINE=1 venv/bin/python tests/eval/eval_memory.py`（加 `--trace` 会写逐用例明细到 `logs/eval_recall_trace_<时间>.log`）。评测体系分三层：① 单元契约测试（`tests/test_response_contract.py`）；② 检索层评测（已跑，120 条）；③ LLM 端到端评测（缺 API 额度与环境，**未开始**）。
  - **第四步（加分）：主动说清剩余 2 条遗忘失败的真相。** 不是机制没生效，而是**判定是子串匹配的假阳性**：`forget_005` 的新事实"已经戒了可乐改喝奶茶"本身含"可乐"、`forget_008` 召回了闲聊"最近想学吉他"含"想学"，于是命中 `match_any` 被判失败——两条的**旧事实其实都已被正确过期**。这是"判定太粗"的已知局限，改进方向是否定词/主语感知的判定（会牺牲可重复性，需谨慎）。
  - **反面示范（会当场露馅）**：编一个"准确率 85%"，或者把已废弃的 stub 52.5% 说成真实结果，或者说"我们只用了 Chroma 官方评测"（本项目没有）。

### Q21｜metadata 里的 `source` 字段有实际作用吗？
**锚点**：`init_anime_kb.py:12`、`anime_kb.py:40-47`
- **考察意图**：区分"数据里的字段"与"被使用的字段"。
- **答题要点**：
  - `source`（"萌娘百科"/"百度百科"）**在代码里从未被读取**——`retrieve` 的 where 只用 `category` 和 `tags`（`anime_kb.py:40-47`），`get_all_tags` 只读 `tags`（`:63-70`）。它是纯人工溯源字段。
  - 所以当前**没有引用/溯源链路**（citation）：回复里不会告诉用户"这条设定来自萌娘百科"，也没有"答案依据"。要做的话需要 `retrieve` 先返回 metadata（Q14），再在 Prompt 里带上来源并要求模型标注，或走 response 字段回传。
  - 面试可主动说：这是"数据准备到位、链路还没接"的典型，改造成本低（接口先扩成 dict 返回即可）。

### Q22｜`retrieve` 支持 `category` 过滤，为什么调用侧从不用它？
**锚点**：`anime_kb.py:32-47` vs `main.py:122-128`
- **考察意图**：能否发现"留了扩展位但没接线"的死参数。
- **答题要点**：
  - `AnimeRAG.retrieve(query, top_k, category=None, tag=None)` 两个过滤维度都实现了（`anime_kb.py:40-44`），但 `_build_rag_context` 只传 `tag`（`main.py:128`），**`category` 参数在首方代码里 0 次被赋值使用**（可 grep `category=` 验证：`main.py` 内无命中）。
  - 后果：8 个 category（identity / appearance / occupation / personality / relationship / backstory / behavior / race / quotes，共 92 条）的**分类价值完全没被利用**。问外貌时本该只搜 `appearance`，现在靠向量在全库瞎撞。
  - 这是最容易拿分的改造点：**用一次轻量意图分类（或关键词规则）把 category 填上，检索精度立刻提升**，接口不用动。面试时把它讲成"已知的、明确的下一步优化"，比硬吹现状好。

---

## C. 情绪建模（Q23–Q30）

### Q23｜情绪判定为什么额外调一次 LLM 而不是用词典/规则？
**锚点**：`personality_state.py:73-103`
- **考察意图**：LLM-as-judge 的收益与成本意识。
- **答题要点**：
  - 用 LLM 的理由：泛化。"滚，别烦我"和"你能不能别来烦我"、"今天真开心"和"还行吧"——词典覆盖率差、反讽几乎无解。返回 `{"sentiment": float}` 是稳定的结构化输出（temp=0.3、max_tokens=100，`:87-88`）。
  - 成本：**每条用户消息 +1 次 API 调用**（叠加 ReAct 规划最多 3 次 + 生成 1 次 + 事实抽取 1 次 → 单轮最坏 6 次调用），延迟 +秒级，且这是**串行阻塞**在回复链路里的（非流式更明显）。
  - 容错很弱：解析失败静默返回 `0.0`（`:99-103`）→ 被当成中性，情绪不动。也就是"API 抖动"会表现成"角色突然变得情绪迟钝"，无日志告警（只有 `logger.info` 记最终状态，`:152-154`）。
  - 更优方案值得说：用小模型/本地分类头替代（成本降一个数量级）；或复用同一次生成调用让模型顺带输出 sentiment（把两次调用合成一次）；或规则兜底 + LLM 只处理置信度低的样本。

### Q24｜好感度为什么是 +2 / −10 的非对称设计？
**锚点**：`personality_state.py:126-131, 138-150`
- **考察意图**：能否把数值参数解释成人设表达，并指出其副作用。
- **答题要点**：
  - 代码注释直接写了动机：`# 负面记忆更深`（`:131`）。量化看：从 0 到 happy 阈值 30 需要 **16 次**连续正向（+2/次，且还要求 `positive_count>=2`）；从 0 到 angry 阈值 −20 只需 **2 次**负向（−10/次）。
  - 配合怒气惯性 `momentum = max(momentum+1, 3)`（`:143`）→ 形成"容易生气、要好起来很久"的人设。这是**用数值模拟性格**，属于产品设计而非工程实现，面试时应该讲成"用可调参数表达人设"，而不是"随便定的数"。
  - 副作用必须主动说：**没有回归机制**。affinity 一旦被推到 −100（10 次负向），只能靠用户持续正向慢慢爬（+2/次 → 50 次才回 0），且没有时间维度（见 Q25）。
  - 参数可调性差：阈值 30 / −20 / −10 与步长 2 / 10 全是硬编码字面量（`:128,131,138,141,144`），没有配置化。

### Q25｜🔥 压力题｜好感度的"衰减"是怎么实现的？隔一周再聊天，情绪会变吗？
**锚点**：`personality_state.py:16-24, 38-50, 122-150`、`README.md:116`
- **考察意图**：**前提错误题**（README 自称"动态衰减"）。考敢不敢指出"文档声明与实现不符"。
- **答题要点**：
  - **先纠正前提：没有时间衰减。** 证据：
    1. `personality` 表只有 `affinity / emotion / emotion_momentum / consecutive_positive / updated_at`（`:16-24`），`updated_at` 只在 `_save()` 里被写（`:59,67`），**从不参与任何计算**。
    2. `_load()`（`:38-50`）是纯读取，没有任何基于 `updated_at` 的推演（没有 `Δt` 项、没有 `exp(-λt)`）。
    3. `momentum`（`:141-150`）是**轮次计数**，不是时间——它只在被调用 `update()` 时 +1/−1。**不调用就不变。**
  - **所以正确答案是**：断线一周后再发一条消息，`_load()` 拿到的还是 `affinity=-30, emotion=angry, momentum=3`，`updated_at` 被刷新成现在 —— 角色"记仇"跨周不变。只有 `updated_at` 变了。
  - **要指出的文档问题**：`README.md:116` 写"人格状态机：情绪/好感度动态衰减，影响回复语气"——"影响回复语气"成立，"动态衰减"**不成立**。准确说法是"有轮次惯性，无时间衰减"。面试时主动纠正自己 README 的过度声明，比被追问划算得多。
  - 顺带给方案：在 `_load()` 里按 `now - updated_at` 做回归（如每小时向 0 回收 1 点，或按天数折半），或者存一条"情绪事件时间线"而非单行快照。

### Q26｜情绪具体是怎么影响回复的？
**锚点**：`personality_state.py:105-120`
- **考察意图**：能否讲清"影响"的**窄**，不夸大。
- **答题要点**：
  - 唯一通道：`build_system_prompt()` 输出两行——`你是希格雯，当前情绪：{emotion}，对主人好感度：{affinity}。` + 四选一的一句语气指令（happy：活泼带颜文字 / sad：低落简短 / angry：冷淡带刺 / normal：温柔陪伴，`:107-118`）。
  - **没有做的**：不调 temperature / top_p / max_tokens；不给 few-shot 示例；不约束回复长度；不影响立绘选择（立绘由客户端读 meta 包自行决定，`main.py:247-248`）。
  - 也就是说情绪对生成的影响**只有一句自然语言指令**，强度完全依赖模型自觉。可改进：情绪 → 采样参数（angry 降温度、happy 升温度）、情绪 → 长度上限、情绪 → 示例对。这是"轻量够用"与"可量化控制"的取舍点。

### Q27｜为什么用"单行表 CHECK(id=1)"存人格状态？代价是什么？
**锚点**：`personality_state.py:17-29, 52-71`、`main.py:59`
- **考察意图**：状态存储方案的自觉性。
- **答题要点**：
  - `id INTEGER PRIMARY KEY CHECK(id=1)` + `INSERT OR IGNORE INTO personality (id) VALUES (1)`（`:18,27`）——用 schema 约束把"全局唯一角色状态"这个业务前提**写进表结构**，是很干净的表达。配合启动时 `PersonalityState()` 进程内单例（`main.py:59`）。
  - 代价：
    1. **单角色 / 单用户**，无法多角色并发（要让两个用户各有各的好感度，表结构就要改）。
    2. 进程内单例 + 启动时读一次 + 每轮整行覆盖（`:56-71`，无版本号、无乐观锁）→ **多 worker 会状态分叉**（详见 Q28）。
    3. 每轮一次 `UPDATE` 开新连接（`:54-71`），和记忆写入一样是"打开-写-关"模式，无连接池。
  - 加分：可以直接指出"如果重做，我会存 `(character_id, user_id)` 复合主键 + 事件表（append-only），当前值由事件推导"——这才是可扩展的形态。

### Q28｜🔥 压力题｜如果给 uvicorn 加 `--workers 2`，或者 Docker 起两个实例，会发生什么？
**锚点**：`main.py:59, 64, 67, 114, 316`、`personality_state.py:52-71`
- **考察意图**：全局可变状态 + 无锁 + 单进程假设的连锁后果。这是"作品集会崩在哪"的典型问题。
- **答题要点**：
  - 事实基础：服务里有一堆**模块级单例**——`personality`（`main.py:59`）、`anime_rag`（`:64`）、`async_llm_client`（`:67`）、`agent`（`:114`）、以及 `memory_service.user_memory_rag`（`memory_service.py:17`）。uvicorn 是单进程启动（`main.py:316` 的 `uvicorn.run(app, ...)`，**没有 workers 参数**），所以现在没问题。
  - 一旦多 worker / 多实例：
    1. **人格状态分叉（最严重）**：每个 worker 各持一份内存状态（`PersonalityState._load()` 只在 `__init__` 时读一次，`:36`），`update()` 改内存后整行覆盖写（`:56-71`）——**没有版本号、没有乐观锁、没有合并**。两个 worker 交替处理时，`A` 写的 affinity 会被 `B` 用陈旧内存值覆盖 → 丢更新、情绪跳变。
    2. **Chroma 并发写**：PersistentClient 走本地 SQLite，多进程写会锁竞争（实测：只读快照都遇到过 `database is locked`）。`store_memory` 只在写 Chroma 处 try/except（`memory_service.py:116-124`），失败静默 → **记忆静默丢失**。
    3. 记忆去重 check-then-act 非原子（Q3）→ 重复记忆概率上升。
  - 修法（按性价比排序）：① 人格状态改成**每次读 DB 并加行版本号**（`UPDATE ... WHERE version = ?`），冲突重试；② 记忆写入改为"SQLite 权威 + 后台补向量索引"，把跨进程状态收敛到单一数据库；③ 真要横向扩展就把 Chroma 换 Server 模式 / 换托管向量库；④ 在那之前**老实用 1 个 worker**，并在 README/部署文档里写明这个限制。

### Q29｜`momentum`（怒气惯性）的衰减逻辑有个边界 bug，在哪？
**锚点**：`personality_state.py:138-162`（rev4 已修复）
- **考察意图**：读分支语句的细致度（尤其是 `elif` 链的"跳过 else"效果）。
- **答题要点**：
  - **旧 bug（rev3 及以前）**：分支是 `if affinity>30 and positive_count>=2 → happy, momentum=0` / `elif affinity<-20 → angry, momentum=max(m+1,3)` / `elif affinity<-10 → sad`（**不动 momentum**）/ `else → momentum=max(0,m-1)`，且只有 `momentum==0 且当前是 angry|sad` 才回落 `normal`。于是从 angry 掉进 **sad 分支（affinity 落在 (−20, −10)）时，momentum 既不清零也不递减**，而回落 `normal` 的唯一出口在 `else` 分支里——"angry(3) → 好感度回到 −15 → sad"后 `momentum` 永远停在 3，**情绪永久卡在 sad**，直到 affinity 升过 −10。路径相关，光看单轮逻辑看不出来。
  - **rev4 修复**：`sad` 分支现在有惯性——首次进入 sad 时 `momentum = max(momentum, 2)`，之后每轮 `momentum -= 1`，减到 0 即回落 `normal`。即使 affinity 一直停留在 (−20, −10)，情绪也会在有限轮内自动恢复，死锁消除。
  - 已加单测 `tests/test_personality.py::test_sad_momentum_decrements_to_normal` 锁定该行为。
  - 残留可改进点：sad 到 0 回 normal 后，若 affinity 仍在负区，下一轮会再次进入 sad（表现为 sad↔normal 间歇，而非永久卡死）——要更平滑需引入"情绪事件时间线"或显式状态机转移表，而不是继续堆 if/elif。

### Q30｜为什么要两个计数器（`consecutive_positive` 和 `emotion_momentum`）？
**锚点**：`personality_state.py:127-135, 138-150`
- **考察意图**：状态字段的最小性/冗余判断。
- **答题要点**：
  - 方向相反：`consecutive_positive` 只在 `sentiment>0.5` 时 +1、负向清零、**中性不动**（`:127-135`）→ 衡量"连续被善待的程度"，只服务 happy 判定；`momentum` 服务 angry/sad 的"还要气几轮"（`:141-150`）。
  - 一个值得说出来的**宽松设计**：中性消息不清零 `positive_count`（`:133-135` 是 `pass`）→ "夸一次 → 聊两句别的 → 再夸一次"会被判成连续两次正向，直接触发 happy。是有意放水（避免闲聊打断人设）还是疏忽，可以讲成"刻意让正向更宽容，与负向的 −10 形成对照"。
  - 冗余点：`momentum` 在 happy 时被清零（`:140`），在 `else` 里递减——它的状态转移完全依附 `emotion`，理论上有重复表达；但因为 Q29 的 bug，确实需要显式存。干净做法是两个计数器合并进显式状态机。

---

## D. 工程取舍（Q31–Q42）

### Q31｜为什么手写 ReAct 而不用 LangChain / LangGraph？
**锚点**：`agent.py:9-17, 153-161`、`main.py:73-110`、`requirements.txt:50-57`
- **考察意图**：选型论证能力 + 是否知道自己的依赖清单。
- **答题要点**：
  - 支持手写的理由：① 循环逻辑只有 60 行（`agent.py:19-74`），可控可读；② 基类留 mock、子类覆写 LLM（`:153-161` vs `main.py:74-110`）→ **LLM 层可替换、可测试**，这是很好的分层；③ 不引入框架的隐藏 prompt 拼装和版本升级风险。
  - 手写的代价（要如实说）：需要自己写三级参数解析容错（`:239-263`）、自己处理格式异常（`:43-55`）、没有重试/没有结构化输出（function calling）、没有 trace/回放。这些恰恰是 LangGraph 的强项。
  - **必须主动澄清的一点**：`requirements.txt:50-57` 装着 `langchain 1.2.15 / langchain-core / langchain-openai / langgraph 1.1.9 / langsmith`，而首方代码 **0 处 import**（`README.md:112` 自称"不依赖 LangChain"）。所以这不是"选型取舍"，而是**依赖清单没清理**——Dockerfile 甚至要用 grep 剔除（Q44）。面试时主动说"这是遗留的依赖债，代码确实不依赖"，比被 grep 抓出来体面得多。

### Q32｜为什么把"规划"和"生成"拆成两个阶段？
**锚点**：`agent.py:110-123, 132-149`
- **考察意图**：流式系统里"格式正确 vs 首字延迟"的取舍推理。
- **答题要点**：
  - 根本约束：ReAct 的中间输出（`Thought:` / `Action:`）**不能给用户看**。但流式要求边生成边发。两者冲突 → 作者选择"**规划阶段全部非流式跑完（最多 3 步，`agent.py:15`），最后一步才流式**"。
  - 工程细节到位的地方：规划是同步阻塞的，所以放进 `asyncio.to_thread`（`:121-123`）避免卡住 FastAPI 事件循环——**这是很多手写 Agent 会漏的一步**，值得讲。
  - 代价：首字延迟 = 最坏 3 次非流式 LLM 往返 + 1 次生成。用户感知是"发出去几秒钟没反应，然后突然开始打字"。缓解手段（尚未做）：先发一个 `type: thinking` 事件、或把规划也做成流式但服务端拦截标签后只转发最终答案。
  - 可延伸的产品视角：桌宠场景下"停顿几秒"其实可接受（拟人感），但要给**视觉反馈**，否则用户以为卡了。

### Q33｜`clean_system` 二次隔离 Prompt 是在补什么漏？
**锚点**：`agent.py:138-143` vs `:176-210`
- **考察意图**：能否识别"prompt 复用导致的格式泄漏"这个通病。
- **答题要点**：
  - 现象：同一个 `system_prompt` 在规划阶段被塞满了 ReAct 格式示范（`agent.py:176-210`，含 `Thought:`/`Action:`/`Final Answer:` 范例）。上下文里全是这些标签，模型生成最终回复时**倾向于继续输出标签**，或说出"我查了一下天气"暴露工具调用过程。
  - 修补：生成阶段另起一个 `clean_system`，明令"禁止输出 Thought/Action/Observation/Final Answer 标签""禁止暴露查询过程""只说中文"（`:140-143`）。
  - 更干净的架构：**规划和生成用两套 prompt 构造器**，而不是"完整 prompt + 后置禁令"。现在的做法等于"先教它格式，再吼它别用格式"，属于补丁而非设计。这条很适合当作"如果再重构一次我会怎么改"的答案。

### Q34｜两条流式路径为什么不等价？会有可感知差异吗？
**锚点**：`agent.py:132-135` vs `:138-148`、`main.py:89-110`
- **考察意图**：流式实现细节的辨识度。
- **答题要点**：
  - 无工具路径（`direct_answer`）：`for char in direct_answer: yield {"type":"text","content":char}`（`:134-135`）——**整段文本早已生成完毕**，只是在服务端逐字符包装发送，是"假流式"。
  - 有工具路径：`async for token in self._call_llm_stream(...)`（`:148`）→ 真 token 流（`main.py:89-110` 的 `AsyncOpenAI` + `stream=True`）。
  - 可感知差异：① 首字延迟——假流式要等整段生成完（长回复可能好几秒白屏），真流式首 token 几百 ms 就出；② 节奏——逐字符 vs 逐 token，客户端打字机速度曲线不同；③ 一个技术细节：逐 `char` 遍历的是 Python code point，emoji 的 ZWJ 组合序列（如某些颜文字/表情）会被拆开发送，客户端可能渲染出半个字；真 token 流没这个问题。
  - 修法很简单：无工具时也走 `_call_llm_stream`（把 `direct_answer` 不当作终态，而是作为"已确定的意图"再流式生成一次会浪费一次调用——所以更合理的是：无工具时**跳过规划阶段**，直接流式生成）。这是个很好的架构级优化点。

### Q35｜🔥 压力题｜如果"写库/抽取/更新人格"这步失败，用户会看到什么？数据会怎样？
**锚点**：`main.py:190-216`（非流式）vs `:219-234, 255`（流式）
- **考察意图**：副作用与响应链路的耦合分析——把"看起来一样的两条路径"拆成两种故障行为。
- **答题要点**：
  - **非流式 `/chat`：用户会丢掉已经生成好的回复。** `_handle_chat` 把 `personality.update(msg)`（`:198`）、`save_message`（`:201-202`）、`extract_facts`（`:206`）、`store_memory`（`:207-208`）**全部同步执行**，而 `chat_post` 的 `try` 把 `_handle_chat` 整个包住（`:263-275`）→ 任何一步抛异常都变成 500。注意 `extract_facts` 和 `_analyze_sentiment` 内部的 `client.chat.completions.create` **没有 try**（`memory_service.py:57-65`、`personality_state.py:81-89`）→ **DeepSeek 抖一次，整个请求 500，回复白生成**。这是最反直觉的耦合。
  - **流式 `/chat/stream`：用户不受影响，但后续步骤会被静默跳过。** `_persist_chat` 由 `background_tasks.add_task` 注册（`:255`），在响应流结束后执行，异常不影响已发送的流（**设计上更正确**）。但 `_persist_chat`（`:219-234`）**没有 try/except** → `save_message` 失败则消息不存、`extract_facts` 失败则人格永不更新（`:234` 被跳过），只有 Starlette 的默认日志留痕。
  - 顺序脆弱点：非流式是 `save_message → extract_facts → store_memory → personality.update`（`:198-208`），**人格更新在最后**；流式是 `存消息 → 抽取 → 存记忆 → 更新人格`（`:224-234`）——两者顺序还不一样（非流式先更新人格再存消息），行为差异没有文档说明。
  - **另一个容易忽略的细节**：`background_tasks.add_task(_persist_chat, msg, full_reply_parts)` 传的是**可变列表的引用**（`:241,255`），闭包在流结束时读它的最终内容 —— 这是它能工作的原因，也意味着一旦有人改成"先 copy 再传"就会存下空回复。这种隐式契约值得写注释。
  - 修法与答辩口径：① 副作用全部移出响应关键路径（流式已经对了，非流式应该改成 BackgroundTasks）；② `_persist_chat` 内部逐步 try + 结构化日志（哪一步失败、丢了多少数据）；③ 用户侧不因持久化失败而拿不到回复。

### Q36｜为什么有两个（实际是三个）OpenAI 客户端？硬编码了哪些东西？
**锚点**：`main.py:8, 13, 67-69`、`memory_service.py:19-21`、`test_api.py:10-13`
- **考察意图**：配置收敛与重复度意识。
- **答题要点**：
  - 事实：全仓构造了 **3 个客户端实例**——`test_api.client`（同步，`test_api.py:10-13`）、`memory_service.client`（同步，`memory_service.py:19-21`）、`main.async_llm_client`（异步，`main.py:67-69`）。`main.py:13` 只是把 `test_api.client` 重命名导入成 `llm_client`，不是新建。`personality_state.py:7` 直接复用 `memory_service.client`，所以"一次 patch 就能 mock 掉情绪+事实两处 LLM"（这正是 `tests/test_response_contract.py:95-100` 的做法）。
  - 为什么必须有一个异步的：流式要用 `async for chunk in response`（`main.py:104`），同步 `OpenAI` 不支持；所以 `AsyncOpenAI` 不可省。
  - 重复度问题：`model="deepseek-v4-pro"` 写死 **5 处**（`main.py:77,95`；`memory_service.py:58`；`personality_state.py:82`）、`temperature` 4 处（`0.7/0.7/0.3/0.3`）、`max_tokens` 4 处（`800/800/1500/100`）。改模型要改 5 个地方，且没有配置项。
  - 一个真实的启动风险：三个客户端都是**模块导入时构造**（`main.py:67`、`memory_service.py:19`、`test_api.py:10`），而 `main.py:10-15` 导入 `test_api`、`test_api.py:8` 又导入 `memory_service` → 导入 `main` 就会连锁构造。若 `DEEPSEEK_API_KEY` 缺失且环境里没有 `OPENAI_API_KEY`，openai SDK 在**构造时**就抛 `OpenAIError` → **服务根本起不来**（不是运行时 401）。这种"缺配置"应该给一条明确的启动期报错信息，而不是 SDK 的通用异常栈。
  - 正解：抽 `llm.py` 暴露 `SYNC_CLIENT` / `ASYNC_CLIENT` + `MODEL` / `TIMEOUT` 常量，全部从环境变量读。

### Q37｜工具为什么"失败也要返回文案"？这个选择的副作用是什么？
**锚点**：`tools/weather.py:15-46`、`tools/search.py:34-60`、`agent.py:63-72`
- **考察意图**：故障处理策略的边界感——识别"降级"和"欺骗"的区别。
- **答题要点**：
  - 设计动机：工具返回值会以 `Observation: {observation}` 拼回 context（`agent.py:72`）交给 LLM 生成最终回复，异常会打断 ReAct 循环并把 500 抛给用户。返回 `"上海天气查询失败（timeout）"` 让模型能用希格雯的口吻包装（"通讯魔法被干扰了"），体验上更连贯。
  - **两个真实副作用**：
    1. **失败被静默降级成正常文本**，没有失败率分母。`tools/weather.py` **全文没有 logging**，`web_search` 的 `except` 也只 return（`search.py:55-60`）→ 外部 API 挂一周，从日志里看不出来（这也是 Q50 "只有分子没有分母"的具体体现）。
    2. **最危险的一条：和风 Key 未配置时返回"天气不错"**（`weather.py:12-13`：`return f"{city}今天天气不错（Key未配置）"`）。这是**假数据**，模型会把它当真实观测写进回复，用户看到"上海今天天气不错"而实际上是配置缺失。博查那边同样兜底成"搜索服务 API Key 未配置"（`search.py:20-21`），措辞更诚实一些。
  - 建议：区分"可降级"（外部超时 → 返回不可用文案 + warning 日志）与"配置错误"（应为启动期校验并 fail fast，或返回显式错误让模型说"我这功能没打开"）；全部补 logger + 计数。
  - 一个细节加分：`weather.py` 用 `HEFENG_HOST` 从环境变量读专属 Host（`:8`），默认值 `"你的APIHost"` 是中文占位符 → 未配置时请求会发到 `https://你的APIHost/...` 这种非法域名，被 except 兜成"查询失败"，也是"缺配置不 fail fast"的同一个毛病。

### Q38｜`_parse_action` 的三级容错值得保留吗？
**锚点**：`agent.py:228-266`
- **考察意图**：对"LLM 输出不可靠"的工程应对水平。
- **答题要点**：
  - 三级兜底：① `key='value'` / `key="value"` 正则（`:242`）；② 无引号 `key=value`（`:246`）；③ 整体当一个参数，并用 `inspect.signature` **从工具签名推断参数名**（`:249-260`）。第三级是最有想法的一步——不硬编码 `city`/`query`，而是问函数自己。
  - 问题：① 无引号分支 `([^,\s]+)` 会把 `weather(city=上海 浦东)` 截成 `上海`，静默丢参；② 第三级依赖形参顺序，`get_weather(city)` 只有一个参数才幸运成立；③ **没有解析失败的度量**——`_parse_action` 无法解析时只 `logger.warning`（`:232`），没有计数，无法回答"LLM 的 Action 格式合规率是多少"。
  - 更稳的方向：改用 function calling / JSON schema（DeepSeek 支持），把"解析"从正则变成模型约束——这是这个模块最值得升级的地方。

### Q39｜事实抽取的 prompt 里为什么要显式"禁止提取天气/新闻/股价"？
**锚点**：`memory_service.py:46-55, 57-65`
- **考察意图**：数据治理意识，以及"用 prompt 做治理"的边界。
- **答题要点**：
  - 动机：长期事实记忆与时效信息必须分开。不写这条约束，模型会把"今天上海 25 度""股市涨了"当用户事实存进永久库，一周后污染回复。rev4 虽已加入遗忘机制（时效标记软删除，见 Q11），但**天气/实时信息未必带"以前/上周"这类时效词**，仍必须靠这条 prompt 约束在写入侧拦掉——两层防护，不能只靠遗忘。
  - 其他约束也在同一个 prompt 里：最多 3 条、每条 ≤50 字（`:52`）、importance 由模型自评（喜好/雷点 8-10、闲聊 3-5，`:50`）、要求纯 JSON 且防 markdown 包裹（`:69-71` 三重 `removeprefix/removesuffix`）。
  - 局限：**全靠模型自觉**。没有 schema 校验（只判 `isinstance(facts, list)`，`:73-78`；解析失败直接返回 `[]`，静默丢一轮）、没有字段级校验（缺 `fact` 键会在 `main.py:208` 的 `f["fact"]` 处抛 KeyError → 非流式直接 500，见 Q35）、没有写入前的规则过滤。
  - **实测反例（很有说服力的素材）**：`logs/agent.log:47` 记录召回到 `fact=助手是蓝色头发，不是粉色` —— **"助手是自己"的属性被当成"关于用户的事实"存了下来**。说明 prompt 约束不足以控制抽取粒度，这也是 `tests/eval` 里 `extract_facts` 未被覆盖（Q20）的真正风险点。
  - 建议：加 `fact_type` 字段（preference / life_event / role_attribute / ephemeral）+ 写入前规则过滤（含"助手/希格雯/我"主语的可疑条目拦截）+ 结构化输出校验。

### Q40｜🔥 压力题｜README 的四条声明，哪些有代码支撑？
**锚点**：`README.md:107, 112, 114, 116`
- **考察意图**：作品集自查能力。面试官最爱做"文档 vs 代码"对账，主动说完比被逐条拆穿好。
- **答题要点**：
  | README 声明 | 结论 | 证据 |
  |---|---|---|
  | "不依赖 LangChain"（`:112`） | **代码成立，工程不成立** | 首方 0 import；但 `requirements.txt:50-57` 装着 langchain/langgraph/langsmith，`Dockerfile:11` 要用 grep 剔除 |
  | "混合 RAG…解决向量稀释问题"（`:114`） | **部分成立，措辞过度** | tag 补充召回确实存在（`main.py:125-128`）；但 tag 是知识库自述词 + 子串匹配，573 行日志里只命中 2 次（Q15/Q16），"解决"言过其实 |
  | "人格状态机：情绪/好感度动态衰减"（`:116`） | **不成立** | 无时间衰减、无回归、无 TTL（Q25）；只有轮次惯性 momentum |
  | "前端 .NET 10 WPF + Prism + MVVM"（`:107`） | **不在本仓库** | 全仓 `*.csproj` / `*.cs` / `*.xaml` 命中 0；README:13-15 已说明是另一个仓库（MyAIPet） |
  | "双层记忆系统"（`:113`） | **成立** | SQLite `messages` + `memories`/Chroma（`test_api.py:18-25`、`memory_service.py:30-39`） |
  | "NDJSON 流式，meta 前置"（`:108`） | **成立** | `main.py:243-252`；注意 meta 的时序语义见 Q12 |
  - 答辩口径：**"README 里有两处过度声明（衰减、解决向量稀释），我在自己的项目档案里已经逐条标注了事实与证据"** —— 这种自我审计能力本身就是强信号。最好顺手把 README 改准（改文案成本为零、收益明显）。

### Q41｜"字段定义了却从不填充"这个 bug 为什么能活那么久？
**锚点**：`schemas.py:20-21`、`main.py:214-215, 249, 269`、`tests/test_response_contract.py`
- **考察意图**：识别"默认值掩盖缺失"这类静默缺陷。
- **答题要点**：
  - 结构原因：`ChatResponse.recalled_memories: List[MemoryItem] = []` 和 `used_tool: Optional[str] = None`（`schemas.py:20-21`）都**有默认值**。pydantic 校验通过、OpenAPI 文档漂亮、客户端拿到 `[]` / `null` 也"合法" → **没有任何东西会失败**，所以没人发现。
  - 传播原因：契约没有断言。`tests/test_chat.py` 3 个用例只断言 `reply` 存在（`:42-43`），从不碰这两个字段。
  - 修复方式：把三处出口收敛到**唯一构造点** `_memory_items`（`main.py:149-158`），非流式（`:269`）、流式 meta（`:249`）、降级流（`:294-301`）共用 → 从结构上杜绝"两处各写一份再各漂各的"。
  - 加固方式：新增 `tests/test_response_contract.py` 4 个用例锁形状，并用**变异测试**验证有效性（把每处修复逐一退回，确认对应用例精确变红；`main.py` 复原后校验一致）—— 见 `PROJECT_BRIEF.md` §9。这一步回答了"你的测试是不是摆设"。
  - 可延伸的原则：对响应契约字段宁可用 `Field(...)` 必填（缺失即 500）也不要给默认值；`response_model` 只保证类型，不保证"有值"。

### Q42｜为什么同时存在 `/chat`、`GET /chat`、`/chat/stream` 三个入口？
**锚点**：`main.py:260-310`、`schemas.py:5-7`
- **考察意图**：接口演进与兼容策略的判断。
- **答题要点**：
  - 现状：`POST /chat` 标注"兼容旧版"（`:262`）同步返回；`GET /chat?msg=` **直接内部委托** `await chat_post(ChatRequest(msg=msg))`（`:278-281`）—— 一处逻辑三个入口，复用做得干净（GET 是真的调 POST 的处理函数，不是复制代码）。
  - 问题：① 两条数据路径的**副作用时机不同**（同步 vs BackgroundTasks，见 Q35），行为并不等价，却共享同一个响应模型的概念；② 非流式路径下用户要等"生成 + 存消息 + 抽取事实 + 更新人格"全部跑完才拿到回复（最坏 6 次 LLM 调用全在关键路径上），延迟远高于流式；③ `session_id` 收下即丢（`schemas.py:7`）。
  - 建议：保留 `/chat` 作为"兼容层"但把它内部改成走同一条链路（同样 BackgroundTasks，或直接内部调用流式再聚合），**让行为等价**；长期把 `/chat/stream` 作为唯一主链路。

---

## E. 部署运维（Q43–Q50）

### Q43｜`entrypoint.sh` 的"首启检测"可靠吗？
**锚点**：`entrypoint.sh:6-18`、`docker-compose.yml:9-11`
- **考察意图**：初始化/幂等设计的鲁棒性。
- **答题要点**：
  - 逻辑：`if [ -z "$(ls -A chroma_db 2>/dev/null)" ]` → 空则建三表 + `import init_anime_kb` 灌 92 条（`:6-17`），最后 `exec python main.py`（`:20`，用 `exec` 让 uvicorn 接管 PID 1 便于信号传递，是正确写法）。
  - 用 `chroma_db` 目录当**所有初始化完成的哨兵**——但它实际只代表 Chroma 建好了。compose 把三个路径**分别挂载**（`./data/chroma_db`、`./data/chat.db`、`./data/logs`，`:9-11`），所以完全可能出现"chroma 有数据但 `chat.db` 被删/未挂"的情况 → 哨兵非空 → **跳过 SQLite 建表** → 运行时才在 `save_message` 处炸（`test_api.py:19` 的 `CREATE TABLE IF NOT EXISTS` 只在 `init_db()` 被调用时才生效）。
  - `import init_anime_kb`（`:15`）依赖**导入即执行的模块级副作用**，没有"已存在则跳过"保护。若哨兵判断失误导致重跑，会第二次 `collection.add` 同 92 个 id → Chroma 行为取决于版本（报错或覆盖），没有明确的幂等保证。更稳的写法是 `if AnimeRAG().collection.count() == 0: import init_anime_kb`。
  - shell 细节：`chroma_db` 不存在时 `ls` 返回非零，但它是 `if` 的条件（`set -e` 对 if 条件不生效），所以凑巧走到初始化分支——行为是对的，但依赖 shell 语义细节，建议显式写成 `[ ! -d chroma_db ] || [ -z "$(ls -A chroma_db)" ]`。
  - 实证这个初始化路径确实容易错位：仓库里同时存在 `chroma_db/`（96 条 embedding）和 `data/chroma_db/`（94 条）两份库（只读快照实测），说明"启动目录决定数据落点"已经真实发生过（根因是相对路径，见 Q48）。

### Q44｜Dockerfile 为什么先单独装 torch 再 grep 掉 requirements？
**锚点**：`Dockerfile:8-12`、`requirements.txt:15-17, 66-80, 138, 141`
- **考察意图**：是否理解"构建期修补依赖清单"的代价。
- **答题要点**：
  - 原因：`requirements.txt` 里 `torch==2.12.0`（`:138`）+ `triton`（`:141`）+ `nvidia-*` 一整套 CUDA 包（`:66-80`）+ `cuda-toolkit/cuda-bindings/cuda-pathfinder`（`:15-17`）—— 全装进镜像要拉几 GB 且 CPU 推理用不上。
  - 做法：先 `pip install torch --index-url https://download.pytorch.org/whl/cpu`（`Dockerfile:8`）装 CPU 版，再 `grep -viE '^(torch|nvidia-|triton|cuda-)'` 过滤生成 `req-docker.txt`（`:11`），用清华源装其余（`:12`）。
  - 代价：① Dockerfile 与 requirements.txt **隐式耦合**——以后有人加一个以 `cuda-` 开头但其实必需的包会被静默剔除；② 本地开发体验极差：README:95 让用户直接 `pip install -r requirements.txt` → 会装 GPU 全家桶（几 GB），这是新人上手的第一道墙；③ 镜像分层里 torch 单独一层（好事，缓存友好）但 grep 那层每次改 requirements 都失效。
  - 正解：拆成 `requirements-base.txt` / `requirements-gpu.txt`（或用 extras），Dockerfile 与本地都读 base；顺带清掉 `langchain/langgraph/gradio/langsmith/kubernetes/pandas` 等未使用依赖（`requirements.txt:26,49-57,94`）——`gradio` 6.13.0 里还带了 `pydub/pillow`，全是死重量。

### Q45｜`uvicorn.run(app, host="0.0.0.0", port=8000)` 这个启动方式有什么问题？
**锚点**：`main.py:313-316`、`Dockerfile:17`、`docker-compose.yml:5-6, 12`
- **考察意图**：生产化程度的判断。
- **答题要点**：
  - 能工作：`0.0.0.0` 是容器内必需的（否则宿主映射无效）；`EXPOSE 8000`（`Dockerfile:17`）+ compose 端口映射（`:5-6`）与之一致。
  - 缺的东西：① **无 workers**（默认单进程）→ CPU 密集操作（embedding 编码、jieba 分词、`_run_react_planning` 虽然在 `to_thread` 但受 GIL 限制）会互相拖慢；② **无健康检查**（compose 里没有 `healthcheck`），`restart: unless-stopped`（`:12`）只能救"进程死了"，救不了"进程活着但 LLM Key 失效/Chroma 打不开"；③ 无访问日志开关、无请求 ID、无优雅关闭处理（uvicorn 默认会处理 SIGTERM，但 in-flight 的 BackgroundTasks 不保证跑完 → **流式响应的持久化可能丢**，这条与 Q35 呼应）；④ 无 `--proxy-headers` 配置，若前面有 nginx 转发，客户端 IP/协议头不可信。
  - 日志：全局 `logger.setLevel(DEBUG)` + `FileHandler("logs/agent.log")`（`main.py:28-50`）无轮转（`RotatingFileHandler`）→ 长期运行无限增长，且是相对路径挂在 `./data/logs`（`:11`）。

### Q46｜仓库里为什么找不到 WPF 客户端？这对"求职作品"意味着什么？
**锚点**：`README.md:13-15, 107`；全仓 `*.csproj` / `*.cs` / `*.xaml` 命中 0
- **考察意图**：作品集完整度自查 + 边界表达能力。
- **答题要点**：
  - 事实：README 明确说明分前后端两个仓库，前端是 [MyAIPet](https://github.com/Mew-2/MyAIPet)（README:15）；所以本仓库无 C# 代码是**设计如此**，不是遗漏。真正的缺口是：**作品集仓库里没有任何客户端侧证据**（无截图、无解析代码片段）。
  - 面试官会立刻追问的三件事，要先准备好答案：① 客户端怎么消费 NDJSON（事件类型只有 `meta` / `text` / `done` 三种，`main.py:125,135,151`）；② 收到 meta 后如何驱动立绘与情绪（契约见 Q12）；③ 断流兜底（`main.py:293-310` 会先发一个 `emotion=sad` 的 meta 再发错误文案）客户端必须能处理"meta 正常但 text 是错误提示"。
  - 建议动作（成本低、收益高）：把客户端关键解析代码或几张截图放进 README，或在本仓库加一个 `docs/client-contract.md` 说明协议。**协议文档本身就是后端作品集最有说服力的东西之一。**

### Q47｜🔥 压力题｜这个服务怎么暴露到公网？有鉴权、限流、CORS、Key 管理吗？
**锚点**：`main.py:260-310`（无中间件）、`schemas.py:6`、`.env.example`、`.gitignore`、`.dockerignore`
- **考察意图**：安全意识与"生产可用性"的诚实评估。这是本仓最大的一块运维债，含糊其辞会立刻掉分。
- **答题要点**：
  - **鉴权：无。** 三个接口全部匿名可调（`main.py:260-310`），没有 `Depends` 校验、没有 API Key、没有 `add_middleware`（可 grep：全仓 `CORSMiddleware|add_middleware|Depends` 命中 0）。
  - **限流：无。** 单次请求会触发 **1~6 次 DeepSeek 调用**（规划 ≤3 + 生成 1 + 情绪 1 + 抽取 1，`agent.py:15`、`main.py:198,206`、`personality_state.py:124`）。一个循环脚本就能烧光额度。输入侧只有 `msg` 的 `min_length=1, max_length=2000`（`schemas.py:6`），**没有频率/并发/每日配额限制**。
  - **CORS：未配置。** WPF 桌面客户端不受同源策略约束，所以没暴露问题；但任何网页 demo 都会被拦。
  - **Key 管理：可用但不完善。** 三个 Key 从环境变量读（`.env.example` 四键：DEEPSEEK / HEFENG_KEY / HEFENG_HOST / BOCHA），compose 用 `env_file: .env`（`docker-compose.yml:7`），`.env` 未被跟踪（`.gitignore:8`）——这部分做得对。可挑的点：Key 在模块导入时被读取并构造客户端（`main.py:67`、`memory_service.py:19`），**缺失即启动失败**（Q36）；没有任何启动期校验给出友好提示。
  - **结论口径**：**"当前定位是单机/局域网自用，不能直接对外。最小改造顺序是：鉴权中间件 → 按用户令牌桶限流 + 每日配额 → LLM 调用级 timeout → 请求 ID + 日志轮转。"** 把顺序说清楚，比说"我们上线时会加安全" 强得多。
  - 补充一个细节（体现你真的翻过仓库）：`.gitignore:14` 和 `.dockerignore` 末尾都是 `.workbuddy/`，规则与实际目录一致（早期版本曾写成不带点的 `workbuddy/` 而失效，当前已正确）；而 `.dockerignore` 排除了 `chroma_db` / `chat.db` / `data/`，所以镜像内不带数据，全靠 compose 的挂载点提供 —— 这与 Q43 的哨兵判断强耦合。

### Q48｜数据落在哪？为什么仓库里会有两份向量库？有备份吗？
**锚点**：`memory_service.py:23`、`retrievers/user_memory.py:16`、`docker-compose.yml:8-11`、`reset_db.py`
- **考察意图**：路径假设与数据安全意识。
- **答题要点**：
  - 落点：**相对路径**。`DB_PATH = "chat.db"`（`memory_service.py:23`）、`UserMemoryRAG(db_path="./chroma_db")`（`user_memory.py:16`）、`AnimeRAG(db_path="./chroma_db")`（`anime_kb.py:11`）、日志 `logs/agent.log`（`main.py:45`）——全部相对**当前工作目录**。Docker 里靠 `WORKDIR /app`（`Dockerfile:6`）与 entrypoint 的 `cd /app`（`entrypoint.sh:3`）兜住。
  - **两份库的成因**：从仓库根目录跑 → 生成 `./chroma_db`；从别处跑（或用 `data/` 挂载）→ 生成 `./data/chroma_db`。实测两份并存：`chroma_db/` 96 条 embedding、`data/chroma_db/` 94 条（只读快照），差 2 条就是各自历史上跑过不同的对话。**这是相对路径假设被打破的实证**——同一份"记忆"在磁盘上分叉了，且没有任何机制察觉。
  - 备份：**没有**。没有任何 dump/快照/导出脚本；唯一的"数据管理工具"是 `reset_db.py`，而它是**删库脚本**（`reset_db.py:31-33` 删 `chroma_db`、`chat.db`、`logs/agent.log`，无确认、无备份）。
  - 一致性另外要注意：SQLite 与 Chroma **本来就是两个数据源**，双写无事务（Q2），所以"备份"必须两边同时做并保证时点接近，否则恢复后出现"记忆在 SQLite 但向量库里没有"。
  - 建议：路径改绝对化（从环境变量读 `DATA_DIR`），启动时校验并打日志；加 `scripts/backup.sh`（`sqlite3 chat.db ".backup"` + tar chroma 目录）与定时任务；给 `reset_db.py` 加 `--yes` 确认与自动备份。

### Q49｜超时和错误处理链路完整吗？
**锚点**：`main.py:74-87, 89-110, 272-275`、`exceptions.py:13-15, 23-43`、`tools/weather.py:20,38`、`tools/search.py:35`
- **考察意图**：分层容错的完整度盘点——特别是"写了处理但走不到"的死代码。
- **答题要点**：
  - 三层的真实状态：
    1. **工具层：有超时。** 和风 GEO/实况各 `timeout=5`（`weather.py:20,38`），博查 `timeout=10`（`search.py:35`），且超时/异常都降级成文案（Q37）。
    2. **LLM 层：没有超时参数。** 五个调用点（`main.py:76-84, 94-103`；`memory_service.py:57-65`；`personality_state.py:81-89`）都**只传 model/messages/temperature/max_tokens**，没有 `timeout=` → 完全依赖 SDK 默认（默认 600s 级），一次卡住能把 `/chat` 请求挂死。
    3. **HTTP 层：兜底能返回，但语义失真。**
  - **死代码（很值得主动指出）**：`chat_post` 里 `except TimeoutError: raise LLMTimeoutException()`（`main.py:272-273`）→ `LLMTimeoutException` 是 504（`exceptions.py:13-15`）。但：① openai SDK 超时抛的是 `APITimeoutError`（继承自 `APIError`），**不是内置 `TimeoutError`**；② 就算抛的是，非流式的 LLM 调用发生在 `agent._call_llm` 里，而它自带 `except Exception → 返回兜底文案`（`main.py:86-87`）把异常吞掉了；`_call_llm_stream` 同理（`:108-110`）。→ **504 分支实际上不可能被触发**，`LLMTimeoutException` 和 `MemoryFetchException`（`exceptions.py:18-20`，全仓无引用）都是死异常。面试时主动说"我核查过这条分支走不到"是加分项。
  - 兜底的副作用：`@app.exception_handler(Exception)`（`exceptions.py:38-43`）把所有未捕获异常统一成 `{"error":"服务器内部错误"}` 500 —— 对外安全，对内信息量为零（真实原因只在日志里，且没有异常 ID 关联请求）。
  - 修法：所有 LLM 调用加 `timeout=`；把 `except Exception` 从 `_call_llm` 里拿掉（或至少分类处理并抛出可识别的异常类型）；把 `APITimeoutError` / `APIConnectionError` 显式映射到 504/502；异常响应里带 `request_id`。

### Q50｜测试与可观测性的现状、缺口？
**锚点**：`tests/`、`main.py:28-50`、`logs/agent.log`
- **考察意图**：工程成熟度自评——"你现在能证明什么、证明不了什么"。
- **答题要点**：
  - **测试现状**：共 **19 个用例**，分五组——`tests/test_chat.py` 3 个（GET/POST 正常 + 空消息 422）、`tests/test_response_contract.py` 4 个（走工具/不走工具/流式 meta 形状/降级流带键）、`tests/test_memory_owner.py` 5 个（主体推断 + 按主体过滤召回）、`tests/test_memory_forgetting.py` 4 个（时效软删除 / 冲突覆盖 / 召回排除过期，隔离到 tmp DB + 假向量库）、`tests/test_personality.py` 3 个（sad 死锁回归 / 怒气惯性 / happy 阈值）。全部 mock 或无外部副作用（不写生产库、不打外部 API、不烧额度）。运行必须带 `HF_HUB_OFFLINE=1`（否则 sentence-transformers 去 HuggingFace 拉模型元数据）。
  - **测试有效性的证据**：对契约用例做过**变异测试**——把三处修复逐条退回，确认对应用例精确变红（`PROJECT_BRIEF.md` §9）；rev4 新增的记忆/人格用例均为"先构造缺陷态、再断言修复"的可回归测试。
  - **缺口（照实说）**：① **没有 CI**（全仓无 `.github/` / `.gitlab-ci.yml`，测试全靠人手跑）；② **没有真实 LLM 端到端测试**，19 个用例都是 mock 级——它们证明"字段搬运/检索排序/状态机转移正确"，**不证明"真实 LLM 会正确触发工具或抽对事实"**；③ 无覆盖率统计与门槛；④ `extract_facts` / `_analyze_sentiment` 的**解析健壮性**（markdown 包裹、非法 JSON、字段缺失）仍没有一条测试。
  - **可观测性现状**：只有 logging —— 控制台 INFO（`main.py:36-41`）+ `logs/agent.log` DEBUG（`:45-50`），`httpcore/httpx/openai` 噪音被压到 WARNING（`:32-33`，这个细节做得好）。业务关键事件确实有打点：`[RAG] 语义命中/tag命中/注入片段`、`[ReAct] Thoughts/Actions/Tool`、`[UserMemory] 召回 + distance`、`[人格] 情绪/好感度/动量`。**本项目所有"实测证据"都来自 grep 这个日志文件**——说明日志设计是有效的。
  - **最关键的缺口一句话**：**只有分子，没有分母。** 现在能 grep 出"某次格式异常""某次召回了 2 条"，但拿不到"总请求数""命中率""工具调用失败率""格式异常率"——因为没有 metrics、没有计数聚合。补法很轻：把上述日志事件做成计数器（Prometheus counter 或定期聚合写日志），就能在不改架构的前提下拿到所有关键比率。

---

## 🔥 压力题索引（10 个）

| # | 题号 | 一句话靶子 | 正确答法的关键动作 |
|---|---|---|---|
| 1 | **Q4** | `1=1` 兜底会把"无关键词"的 query 变成"返回全表最重要的 3 条" | **rev4 已删除该兜底**；讲清旧路径的隐蔽性 + 当前 `if not keywords: return []` |
| 2 | **Q7** | 合并后按 importance 硬排，把相关性序（distance）丢掉 | **rev4 已改为 distance 融合重排 + 双重阈值**；讲清旧缺陷与现方案，附 before/after |
| 3 | **Q11** | "遗忘机制的衰减函数为什么这么选" | **rev4 已实现遗忘**（时效标记软删除 + 冲突覆盖 + 衰减×频率）；点明"评测同时间戳→纯时间衰减无效、必须用时效标记" |
| 4 | **Q16** | `t in msg` 子串匹配 tag，会踩什么坑 | 举知识库单字 tag `"女"` 的实例 + 日志实录 |
| 5 | **Q20** | "检索准确率多少、怎么测的" | 分三层回答：契约测试已闭环 / 检索层已跑（60.8%→98.3%）/ 端到端未开始；**绝不引用已废弃的 stub 52.5%** |
| 6 | **Q25** | "好感度的衰减" | **纠正前提：无时间衰减**，momentum 是轮次不是时间；指出 README 过度声明 |
| 7 | **Q28** | 加 `--workers 2` 会怎样 | 全局单例 + 无锁整行覆盖 → 状态分叉；Chroma 多进程锁竞争 |
| 8 | **Q35** | 持久化/抽取失败时用户看到什么 | 非流式 500 丢回复（回复已生成）vs 流式静默跳过后续步骤 |
| 9 | **Q40** | README 声明逐条对账 | 主动列出两处过度声明（衰减、解决向量稀释）+ 一处仓库边界（前端不在本仓） |
| 10 | **Q47** | 怎么暴露到公网、有没有鉴权限流 | **照实说全无**，给最小改造顺序；说清"单机自用，不能直接对外" |

**压力题的通用答题结构**：先给结论（有/没有/部分成立）→ 贴证据（文件:行号 + 可复现的检索命令或日志行）→ 说明代价与风险 → 给可落地的改进方案。**最关键的是敢在前提错误时纠正前提**——面试官出这类题，看的往往不是"你会不会修"，而是"你会不会不懂装懂"。
