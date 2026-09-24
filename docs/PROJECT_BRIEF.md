# 希格雯桌宠 — 项目档案（侦察报告）

> 侦察时间：2026-09-24（rev4：记忆系统重构——主体过滤 / 相关性阈值与融合重排 / 遗忘机制；人格 sad 死锁修复）｜分支 `memory-refactor`（HEAD `e990162`，基线 `3bc471c`）｜范围：仓库全部首方代码（排除 `venv/`）
> 所有结论均标注 `文件:行号`。无实现依据的一律标注"未找到相关实现"。修订内容见 §9。

## 0. 先纠正三处与 README 不符的事实

| README 说法 | 实测事实 | 证据 |
|---|---|---|
| 前端 .NET 10 WPF + Prism + MVVM | **本仓库没有任何 WPF 代码**，无 `.cs/.csproj/.xaml` | README.md:99；`*.csproj` 全仓搜索命中 0 |
| Python 3.11 | 本地 venv 实为 3.12.3 | README.md:94 vs venv/pyvenv.cfg:3 |
| "不依赖 LangChain" | 确实没 import，但 `requirements.txt` 装了 langchain 1.2.15 / langgraph 1.1.9 / gradio 6.13.0 / torch 2.12.0 | README.md:104；requirements.txt:26,50-56 |

**结论：本仓库 = 纯 Python FastAPI 后端**，客户端是独立工程，不在作品集仓库里。

## 1. 技术栈清单

- 语言：Python（Docker 目标 3.11，实跑 3.12.3）
- Web：FastAPI 0.136.0 + Starlette 1.0.0 + uvicorn 0.45.0（main.py:52,316）
- LLM：DeepSeek `deepseek-v4-pro`，走 openai 2.32.0 SDK（main.py:74-110、memory_service.py:72-80、personality_state.py:81）
- 校验/配置：pydantic 2.13.3（schemas.py）、python-dotenv（.env.example 四键：DEEPSEEK/HEFENG/BOCHA）
- 向量库：chromadb 1.5.9（PersistentClient）+ sentence-transformers 5.5.1 + `BAAI/bge-small-zh-v1.5`（retrievers/anime_kb.py:11-18）
- 结构化存储：SQLite（标准库 sqlite3，无 ORM），单文件 `chat.db`（memory_service.py:24）
- 中文分词：jieba 0.42.1（memory_service.py:5,282）
- 外部 API：和风天气（tools/weather.py:17-43）、博查搜索（tools/search.py:35）
- 测试：pytest 9.0.3 + fastapi TestClient，**19 个用例**（3 smoke + 4 响应契约 + 5 主体过滤 + 4 遗忘 + 3 人格），实测 `19 passed in 11.93s`（`HF_HUB_OFFLINE=1`、Python 3.12.3；4 个契约用例已用变异测试验证有效性）

## 2. 模块地图

| 路径 | 职责（一句话） |
|---|---|
| main.py | FastAPI 入口：三接口 + 上下文组装 + 后台持久化 + 人格/RAG 全局单例 |
| agent.py | 手写 ReAct 循环，规划/生成两阶段，含工具调用与三级参数容错解析 |
| memory_service.py | 长期记忆：事实抽取、去重写入、向量+关键词混合召回 |
| personality_state.py | 情绪状态机：LLM 打情绪分、好感度增减、按情绪拼 System Prompt |
| retrievers/anime_kb.py | 角色设定 RAG（ChromaDB collection `anime_kb`），支持 tag 过滤 |
| retrievers/user_memory.py | 用户记忆向量库（collection `user_memories`，cosine） |
| test_api.py | **被 main.py 当作存储层复用**：messages 建表/写入/取最近 N 条 |
| schemas.py | Pydantic 请求/响应模型 |
| exceptions.py | 业务异常基类 + 三类全局异常处理器 |
| tools/weather.py、tools/search.py | 两个 Agent 工具，均为"失败返回文案不抛异常" |
| init_anime_kb.py | 92 条角色设定文档的硬编码数据源 |
| entrypoint.sh | 首启检测并初始化三表 + 知识库，再拉起 uvicorn |
| reset_db.py、dev_test.py | 开发脚本：一键删库重建 / 情绪状态机对比实验 |
| tests/test_chat.py | 3 个 smoke 用例（正常请求 + 参数校验） |
| tests/test_response_contract.py | 响应契约测试：锁定 `used_tool` / `recalled_memories` 的出口形状，全 mock、无副作用 |

## 3. 数据流：从用户输入到 AI 回复

以流式接口 `POST /chat/stream`（main.py:284-303）为主链路：

1. 请求校验 → `ChatRequest`（schemas.py:5-7，`session_id` 收下即丢）
2. `_handle_chat_stream` 调 `_build_chat_context`（main.py:162-187）组装 System Prompt 并返回 `(system_prompt, memories)` 二元组，Prompt 四段拼接：
   - `personality.build_system_prompt()` — 情绪+好感度+语气指令（personality_state.py:105-120）
   - `get_recent_messages(6)` — 最近 3 轮原文（test_api.py:39-50 → SQLite `messages`）
   - `recall_memories(msg, top_k=3)` — 长期记忆（memory_service.py:374），**同时作为返回值回传给响应层**
   - `_build_rag_context(msg)` — 角色设定（main.py:117-146 → retrievers/anime_kb.py:32）
3. `agent.run_stream`（agent.py:110-151）：
   - 阶段一 `_run_react_planning` 放线程池（agent.py:121-123），最多 3 步（agent.py:15），每步 `_call_llm` 非流式 → 命中 `Action:` 则执行工具（weather/search）并把 `Observation` 追加进 context（agent.py:72）
   - 先 yield `meta` 包（`used_tool`/`thoughts` 由 agent.py:125 产出），main 侧再补 `emotion`/`affection`/**`recalled_memories`**（main.py:245-249；记忆经 `_memory_items`（main.py:149-158）裁成三字段）
   - 阶段二：有 `direct_answer` 就**逐字** yield（agent.py:134-135）；否则用 `clean_system` 重新发起**真 token 流式**调用（agent.py:138-149）
4. `_persist_chat` 注册为 BackgroundTasks（main.py:255），流结束后才执行：存两条消息 → `extract_facts` 提取事实 → 逐条 `store_memory` 双写 → `personality.update(msg)`
5. 异常兜底：`chat_stream` 顶层 try 失败后返回预置的 sad 流（main.py:293-303；降级 meta 同样带 `recalled_memories: []`，三条路径契约一致）

非流式 `POST /chat` 同链路，但所有副作用同步执行（main.py:198-208），并在 main.py:269 复用同一个 `_memory_items` 映射后回传 `MemoryItem` 列表——两条路径不再各写一份形状。

## 4. 记忆系统现状（重点）

**分层：两层。长期层以 SQLite 为权威源，Chroma 是派生的向量索引。**

| 层 | 存储 | 生命周期 |
|---|---|---|
| 短期对话历史 | SQLite `messages` 表（test_api.py:18-25），仅取最近 6 条（test_api.py:39-50） | 永久堆积，无清理 |
| 长期事实记忆 | SQLite `memories` 表（memory_service.py:31-43）**+** Chroma `user_memories`（user_memory.py:21-25） | 有软删除与时间衰减（见下） |

`memories` 表 rev4 新增三列：`owner`（主人/他人）、`status`（active/expired/superseded）、`access_count`（memory_service.py:37-39）；旧库用 `PRAGMA table_info` + `ALTER TABLE` 幂等补列（memory_service.py:44-55）。

**写入（memory_service.py:178-237）**

- 时机：**每条 AI 回复后**（流式 main.py:227-231 / 非流式 main.py:206-208），由 LLM 抽取（`extract_facts`，memory_service.py:59-93）。约束写在 prompt 里：最多 3 条、每条 ≤50 字、显式禁止天气/新闻等时效信息、importance 由模型自评（memory_service.py:61-70）。
- 去重：`_normalize_fact` 去尾部标点（memory_service.py:96-98）后**全表逐行比对**（memory_service.py:194-198），命中即跳过。
- **主体标记（rev4 新增）**：`_infer_owner` / `_infer_query_owner` 按文本词形推断主体——形如"主人的同事…"或"我同事…"判为 `他人`，否则 `主人`（关系词表与正则 memory_service.py:101-111，推断函数 :114-121）。
- **时效软删除（rev4 新增）**：命中 `_STALE_MARKERS`（以前/之前/曾经/去年/上个月/上周/昨天/前天…，memory_service.py:125-128）的事实，写入 SQLite 但 `status='expired'`，且**不进向量库**（memory_service.py:136-138,188,218-222）——软删除，留痕可查。
- **冲突覆盖（rev4 新增）**：新事实命中 `_CURRENT_MARKERS`（已经/现在/换成/搬到/转岗/戒了/决定不…，memory_service.py:130-133）且与同主体旧记忆 keywords 相交时，旧记忆置 `status='superseded'` 并调 `user_memory.delete()` 撤出向量库（memory_service.py:145-175,237）。**这是 `delete()` 的第一个真实调用者。**
- Chroma 双写失败只 log 不补偿（memory_service.py:225-234）。

**检索（`recall_memories`，memory_service.py:374-443）——rev4 已重写为七步**

1. 主体推断：`_infer_query_owner(query)`（memory_service.py:383-384）。
2. 向量路：候选池 `RECALL_CANDIDATE_K=15`，`user_memory.recall(max_distance=RECALL_MAX_DISTANCE=0.8)` 做**绝对阈值**过滤（memory_service.py:388-394；user_memory.py:92-104）——超阈值的直接丢弃，这是 rev3 缺失的第一道闸。
3. 关键词路（兜底）：jieba 分词 + 停用词表（memory_service.py:240-276）+ 2-4 字中文片段补充（memory_service.py:291-293）；**无有效关键词时显式返回空**，旧的 `1=1` 兜底已删除（memory_service.py:306-310）；SQL 加 `AND status='active'`（memory_service.py:321）。
4. 按 id 去重合并，向量结果先入（memory_service.py:401-408）。
5. **主体过滤**：只保留 `owner` 与提问主体一致的记忆（memory_service.py:410-411）。
6. **遗忘过滤**：`_recency_factor = exp(-λ·天数) × (1+ln(1+access_count))`，低于 `RECALL_MIN_RECENCY=0.05` 丢弃（memory_service.py:356-371,417-423）。λ=0.05/天 → 约 **60 天**未访问即永久出列（exp(-0.05×60)≈0.0498 < 0.05）。
7. **融合重排 + 相对阈值**：`score = 0.9·(1−distance) + 0.1·(importance/10)`，无 distance 的关键词路给 `0.4·importance/10` 的弱分，再乘遗忘因子；排序后**只保留与最佳分差在 `RECALL_SCORE_MARGIN=0.08` 内的**，取 top_k（memory_service.py:425-443）。

- **排序口径：distance 为主（权重 0.9）、importance 为辅（0.1）**，distance 第一次真正参与决策；全部阈值与权重集中在 memory_service.py:346-353。注意 `min_importance` 仍恒传 1，等于不过滤（memory_service.py:392）。
- 召回后对**进入 Prompt 的每条**记忆调 `update_accessed`，刷新 `last_accessed` 并累加 `access_count`（main.py:179-180；memory_service.py:446-455）。
- 遗忘是**三条路并行**：时效软删除（写入即失效）、冲突覆盖（新事实取代旧事实）、时间衰减×访问频率（召回时过滤）。单靠时间衰减在本项目评测条件下恒等无效（120 条用例同刻写入，`exp(-λ·Δt)≡1`），真正能区分"过期"的信号是文本里的时效标记——这是"评测约束倒逼设计"的实例。

**实测**

- 检索层评测（tests/eval/eval_report.md，120 条用例，real 后端）：总准确率 **98.3%**（118/120）；分类 accuracy——fact / long_context / emotion / distractor 均 **100%**、forgetting **91.7%**；平均召回条数 1.17、平均注入 21.8 token、召回延迟 P95 20.0ms。重构前基线 60.8%（干扰项仅 4.2%、遗忘 0%）。
- 遗留的真实问题之一：**抽取粒度失准仍在**——`助手是蓝色头发，不是粉色`（"关于助手"的伪事实）在 logs/agent.log:43 被写入，且在 rev4 之后仍被召回注入（logs/agent.log:800,842，distance 0.5988）。`owner` 推断救不了它：该条不以"主人的<关系词>"开头，被默认为 `主人`。
- 遗留问题之二：**短查询向量稀释**依旧——`记好了，我是ZZDW` 召回「日文名/韩文名」（data/logs/agent.log:1-6）。tag 旁路命中率极低：logs/agent.log 中带 tag 判定的日志共 **67 条**，非"无"命中仅 **12 条（17.9%）**，其中 **11 次是单字 tag `女`**（:84,:154,:255,:468,:579,:690,:802,:915,:1030,:1163,:1301），另 1 次 `美露莘`（:65）。

## 5. 情绪系统现状

- 建模：`personality` 表**强制单行**（`CHECK(id=1)`，personality_state.py:18），四个字段 = affinity(-100~100) / emotion / emotion_momentum / consecutive_positive。进程内再持一份全局单例（main.py:59）。
- 判定：每条用户消息交给 LLM 打情感分 -1~1（personality_state.py:73-103），**额外一次 API 调用**；然后按阈值改好感度——正向 +2、负向 **-10**（非对称，注释写明"负面记忆更深"，personality_state.py:127-131）。
- 情绪映射：affinity>30 且连续 2 次正向 → happy（momentum 清零）；<-20 → angry 且 momentum 至少 3 轮（怒气惯性）；<-10 → sad；否则 momentum 每轮 -1，归零后从 angry/sad 回落 normal（personality_state.py:138-159）。
- **sad 死锁已修复（rev4）**：旧实现 sad 分支既不清零也不递减 momentum，而回落 normal 的唯一出口在 `else` 分支——"angry → 好感度回到 (−20,−10) 区间 → sad"之后，momentum 永远停在 3，**情绪永久卡 sad**。现在 sad 首次进入给 2 轮惯性、之后每轮递减，减到 0 回落 normal（personality_state.py:144-154，注释里写明了这次修复的动因）。回归测试 `tests/test_personality.py::test_sad_momentum_decrements_to_normal` 构造死锁现场（affinity=−15、momentum=3）断言 6 轮内必然出现 normal。
- **残留**：sad 归零回 normal 后，若 affinity 仍落在 −20~−10，下一轮会再次进入 sad → 表现为 sad↔normal 间歇而非平滑恢复；要根治得引入显式状态机转移表，而不是继续堆 `elif`。
- 影响回复的方式：只通过 `build_system_prompt` 四选一的语气描述注入（personality_state.py:111-118），**没有独立的情绪参数或采样参数调整**。
- **meta 时间基准（当作契约读，不是缺陷）**：`emotion`/`affection` 是**进入本轮之前**的状态——`_persist_chat` 在流结束后才调 `personality.update`（main.py:247-248 注释、main.py:234），所以"客户端看到的情绪滞后一轮"是**既定语义**，不是 bug；而同一 meta 里的 `recalled_memories` 是**本轮**召回的。两者时间基准不同，客户端应把 emotion/affection 理解为"本轮开始前的状态"。若未来要做表情实时联动，需按明确需求另立改动。

## 6. RAG 实现

- 知识库：92 条角色设定（init_anime_kb.py:5-843，id 1-92），8 个 category：identity 18 / appearance 12 / occupation 5 / personality 12 / relationship 13 / backstory 12 / behavior 12 / race 3 / quotes 5，来源标注"萌娘百科/百度百科"。
- 分块策略：**没有自动切分**。是人工把每条属性写成一句独立文档（"希格雯的发色是蓝色。"），粒度靠手写控制，未找到 chunk_size/overlap/splitter 相关实现。
- 向量库：ChromaDB PersistentClient，collection `anime_kb`，embedding = bge-small-zh-v1.5（512 维，实测 chroma.sqlite3 中 `collections.dimension=512`）。
- 召回：`retrieve()` 先纯语义 top3，再用"用户消息里出现的 tag"追加 tag 过滤 top2，合并去重（main.py:122-135）。Chroma `anime_kb` 未设 `hnsw:space`（默认 L2），而 `user_memories` 显式设为 cosine（anime_kb.py:16-18 vs user_memory.py:21-25）——**两个库距离度量不一致**（实测 collection_metadata 表只有 user_memories 一条 cosine 记录）。
- 实测数据规模：根目录 `chroma_db` embeddings=96（92+4 条记忆），`data/chroma_db`=94（92+2），两份库并存。

## 7. 工程决策点（面试用，各注明出处）

1. **手写 ReAct 而不上 LangChain**：基类留 mock，子类覆写 LLM 调用。agent.py:9-17,153-161
2. **规划/生成两阶段分离**：流式只用于最终答案，规划整体走 `asyncio.to_thread` 不阻塞事件循环。agent.py:110-123
3. **生成阶段二次隔离 Prompt**：`clean_system` 明令禁止输出 Thought/Action/Observation 标签，防 ReAct 格式泄漏给用户。agent.py:138-143
4. **两条流式路径不等价**：无工具时 `for char in direct_answer` 是逐字假流式，有工具时才是真 token 流。agent.py:134-135 vs 148
5. **meta 包前置 + 旧状态**：先发情绪再生成，牺牲一轮实时性换取客户端能提前切立绘（语义已在 §5 固化为契约）。main.py:245-249
6. **RAG 双层召回**：语义保广度 + tag 保精度，`dict.fromkeys` 去重保序。main.py:122-135
7. **记忆混合召回**：向量优先、关键词兜底，按 id 而非文本合并。memory_service.py:374-443
8. **去重靠标点归一化**：`_normalize_fact` 解决"…喝奶茶。"≠"…喝奶茶"。memory_service.py:96-98
9. **情绪交给 LLM 判断**而非词典/规则，接受额外延迟换语义泛化。personality_state.py:73-103
10. **好事感度非对称**（+2/-10）与**怒气惯性 3 轮**——用数值设计模拟"记仇"。personality_state.py:127-131,141-143

（可补充：单行表存全局状态 personality_state.py:12-29；存储层复用测试脚本 main.py:10-15；**响应契约以实际数据结构为准**——`MemoryItem.keywords` 由 `Optional[str]` 纠正为 `Optional[List[str]]`，并把"定义了却从不回传"的 `recalled_memories`/`used_tool` 补齐为真实回传，schemas.py:12、main.py:187,210-216,249,269；**对外形状只保留一个构造点**——非流式、流式、降级流三条路径全部走 `_memory_items`（main.py:149-158），从结构上杜绝"两处各写一份再各漂各的"；`used_tool` 固定取**首个**被调用的工具，agent.py:65-66。）

## 8. 技术债清单

**架构级**
- 存储层寄生在 `test_api.py`，main.py:10-15 从测试文件导入生产逻辑——命名与职责严重错位。
- `session_id` 收下即丢（schemas.py:7，全仓仅此一处），系统实为**单用户单会话**。
- 单进程 uvicorn（main.py:313-316）+ 进程内人格单例（main.py:59），无法横向扩展。
- ~~同一字段两种传输形状~~ **rev3 已修复**：三条路径（非流式 main.py:269、流式 main.py:249、降级流 main.py:294-301）共用 `_memory_items`（main.py:149-158），出口统一为 fact/keywords/importance 三字段，内部字段不再泄漏。**残余风险**：测试只锁固定形状，未来给 `MemoryItem` 加字段时仍可能出现两端不同步。
- ~~新增字段零回归测试~~ **rev3 已补齐**：`tests/test_response_contract.py` 4 个用例锁定 `used_tool` 与 `recalled_memories` 形状（走工具 / 不走工具 / 流式 meta / 降级流），并经变异测试验证——退回任一修复点即变红。

**记忆/检索级**

*rev4 已解决（保留记录，供面试对比）*

- ~~无遗忘、无衰减、无压缩、无重排~~ → 已实现：时效软删除 + 冲突覆盖 + 时间衰减×访问频率 + distance 融合重排（见 §4）。
- ~~合并后按 importance 硬排丢掉向量相关性序~~ → 已改为 `0.9·(1−distance)+0.1·importance`（memory_service.py:425-434）。
- ~~关键词路 `1=1` 兜底静默返回全表最重要的 3 条~~ → 已改为显式返回空并记日志（memory_service.py:306-310）。

*仍然存在*

- **访问频率加成对语义路实际失效**：`freq = 1+ln(1+access_count)`（memory_service.py:370）读的是 SQLite 列，但向量路返回的 dict **不含 `access_count`/`last_accessed`**（user_memory.py:78-90 只给 id/fact/keywords/importance/owner/created_at/distance），而合并时向量优先（memory_service.py:404）——凡被向量路命中的记忆，频率恒为 1.0，衰减基准退化成 `created_at`（memory_service.py:362）。"热点记忆抗遗忘"只在纯关键词命中时成立。
- **时间戳解析失败会静默不衰减**：`_recency_factor` 用 `datetime.fromisoformat(str(ts))`，`ValueError/TypeError` 一律按 0 天处理（memory_service.py:364-368）→ 时间格式一旦变化，该批记录变成"永不遗忘"，且**不报错、无日志**。
- **时效标记是关键词启发式，会误伤**：`_is_expired_fact` 只做子串匹配（memory_service.py:136-138）。"我以前是军人，所以很自律""之前学的那点东西还有用"这类**长期有效**的自我描述会被直接判过期、写入即不入库——而软删除没有召回路径，**误判的代价是信息永久丢失**（仅在 SQLite 留痕）。
- **冲突覆盖按 keywords 集合相交判定，过宽**：只要新旧记忆共享**任意一个** keyword 就覆盖（memory_service.py:165-166）。keywords 由 LLM 生成且常含宽泛词（"饮料""居住""工作"），一条新的"现状"事实可能连带撤掉若干条其实仍有价值的旧记忆。
- **`owner` 推断依赖固定词形，抽取侧不保证**：`_OWNER_OTHER_RE` 要求事实以 `主人(的|家的)+关系词` 开头（memory_service.py:109），但 `extract_facts` 的 prompt 从不要求这个前缀（memory_service.py:61-70）。LLM 写成"同事小李喜欢美式咖啡"就会被判成 `主人`，他人事实照样混进主人召回；关系词表也不含"闺蜜/发小"等口语词（memory_service.py:102-107）。现有单测只覆盖带前缀的写法（tests/test_memory_owner.py:6-27，全部 5 个用例都只覆盖带前缀的写法）。
- **用 recall 换 precision**：`RECALL_SCORE_MARGIN=0.08` 的相对阈值 + `top_k=3` 把平均召回条数压到 **1.17**（tests/eval/eval_report.md:25）。低噪声、低覆盖是明确取舍，但 0.8 / 0.08 / 0.9 / 0.1 全是经验值、无数据支撑，记忆规模上去后必须重调。
- 去重仍是 **O(n) 全表扫描**（memory_service.py:194-198），量大即瓶颈；且 check-then-act 非原子（无唯一索引兜底），并发下仍可能重复写入。
- SQLite 与 Chroma 双写无事务无补偿，失败仅 log（memory_service.py:225-234）；rev4 的冲突覆盖同样是"改 status + 删向量"两步非事务（memory_service.py:166-170），中途失败会造成两边不一致。
- 提取粒度失准：实测把「助手是蓝色头发，不是粉色」当成用户事实存入（logs/agent.log:43 写入），且该伪事实在 rev4 后仍被召回注入（logs/agent.log:800,842，distance 0.5988）。

**稳定性/工程级**
- ReAct 空响应无重试：日志实录 `[Step 0] 格式异常…LLM原始输出 (len=0)` 直接终止规划，靠二次总结兜底，白烧一次调用（agent.py:44-55,93-101）。
- `LLMTimeoutException` 形同虚设：main.py:272 捕 `TimeoutError`，而 openai SDK 抛 `APITimeoutError`，504 分支走不到（exceptions.py:13-15）。
- 知识库 tag 旁路收益极低却代价固定：每轮全量 `collection.get` 取 metadata（anime_kb.py:63-70），而 logs/agent.log 中带 tag 判定的日志共 **67 条**，非"无"命中只有 **12 条（17.9%）**，且其中 11 条命中的是单字 tag `女`（脏命中，根因见 main.py:125 的裸子串匹配）。
- 依赖冗余：langchain/langgraph/gradio/torch/cuda 全家桶塞进 requirements.txt，Dockerfile:11 才用 grep 剔除，本地安装体验极差。
- 版本三处不一致（3.11 / 3.11-slim / venv 3.12.3）；异常文案里还有硬编码中文兜底（main.py:87,110）。

## 9. 修订记录

**rev4（2026-09-24）— 记忆系统重构 + 人格 sad 死锁修复**（分支 `memory-refactor`，基线 `3bc471c`）

代码侧改动（均已在源码中逐条核对，非转述）：

1. `a7678a7` 记忆主体标记 `owner` + 召回按提问主体过滤；
2. `86ae443` distance 相关性绝对阈值 + 融合重排，删除关键词路 `1=1` 兜底；
3. `970c93b` 遗忘机制：时效标记软删除 + 冲突覆盖 + 时间衰减×访问频率；
4. `5372253` 人格 sad 分支 momentum 递减，修复情绪死锁（新增单测）。

**本报告同步范围：§4（全部重写）、§5（情绪映射与死锁）、§8 记忆/检索级（重写）**，另更新封面版本标记与本记录。

**行号位移（rev3 → rev4）**

| 文件 | rev3 | rev4 | 说明 |
|---|---|---|---|
| main.py | 316 | 316 | **未变**——本次重构没碰入口层，§3/§7 的 main.py 锚点全部仍然有效 |
| agent.py | 273 | 273 | 未变 |
| memory_service.py | 270 | **459** | 新增 owner/status/access_count、时效与冲突覆盖、七步召回；旧锚点全部失效 |
| personality_state.py | 157 | **166** | sad 分支展开 +9 行 |
| retrievers/user_memory.py | 105 | **128** | 新增 `max_distance` 阈值与 `owner` 元数据 |

重算方法：`git diff` 的 `equal` 段可压缩成 `(位移, 旧区间)` 表，再逐条映射被引用行号；工具见用户级 skill `doc-anchor-guard/scripts/remap_anchors.py`（`--file <file> --rev <旧提交> --lines <旧行号>`）。

**rev4 补扫（2026-09-24，同分支）— §1/§3/§6/§7 锚点同步**

rev4 首轮只改了 §4/§5/§8，遗留的 rev3 行号在本轮清掉（逐条回源码核对，rev3 基准 `3bc471c`）：

- §1：`memory_service.py:23`（DB_PATH）→ `:24`；`:57`（LLM 调用，原在 `extract_facts` 内）→ `:72-80`；`:169`（jieba 分词）→ `:5,282`；测试用例数由 7 更新为 **19**（实测 `19 passed in 11.93s`）。
- §3：`memory_service.py:229`（`recall_memories` 定义行）→ `:374`。
- §6：根目录 `chroma_db` embeddings 由 95 更正为 **96**（92 条设定 + 4 条记忆）；`data/chroma_db` 仍为 94。
- §7：第 7 条 `memory_service.py:229-254` → `:374-443`（`recall_memories` 全函数）；第 8 条 `:81-98` → `:96-98`（`_normalize_fact`）。

**同批同步**：`docs/interview_qa.md` 的 Q5（整段按 rev4 重写——旧答案仍在讲已被删除的 `merged.sort(key=importance, reverse=True)`，与 Q7 自相矛盾）与 Q2/Q3/Q6/Q8/Q23/Q39 的过时行号；`tests/eval/eval_report.md` 的 3 处旧措辞（`:8` 排序口径、`:28` `memory_text` 行号、`:68` 遗忘失败聚类标签）。

**仍待同步（超出本轮点名范围）**：`docs/interview_qa.md` 封面第 7 行与 Q15/Q40 仍引用 rev3 的「`logs/agent.log` 573 行」「tag 命中 2 次」。实测该日志为 **1432 行**（append-only，跑测试或真实对话都会继续增长，此处与 §4 的统计同为一个快照值），带 tag 判定的 **67 条**中非「无」**12 条（17.9%）**（其中 11 条为单字 tag `女`）——与 §4 的数字已对不上，需单独一轮修正；另 `tests/eval/eval_memory.py:312` 的注释仍写 `main.py:163-166`，实为 `:175-177`。

**验收缺口（如实记录）**

- rev4 的 98.3% **只覆盖检索层**（`store_memory` + `recall_memories`），**不覆盖** `extract_facts` 抽取质量与真实 LLM 回复——WSL 环境访问不到 DeepSeek API，`eval_report.md:9` 自己也写明了。
- 遗忘类 91.7% 的 2 条失败已定位为**判定子串假阳性**（`forget_005` 新事实本身含"可乐"、`forget_008` 召回了含"想学"的闲聊），**两条旧事实其实都已被正确过期**，非机制失效；但 `eval_report.md:68` 的失败聚类标签"（无遗忘机制）"是重构前的旧措辞，尚未改。
- 19 个 pytest 用例全为 mock 级；全仓仍**无 CI**、**无真实 LLM 端到端测试**。

**rev3（2026-09-23）— 响应契约形状统一 + 契约测试入库**

按评审意见执行的三条，逐条落实：
1. **流式形状统一**（改代码）：新增 `_memory_items`（main.py:149-158）作为**唯一构造点**，非流式（main.py:269）、流式 meta（main.py:249）、降级流 meta（main.py:294-301）三处共用，出口恒为 fact/keywords/importance 三字段；顺带补上降级流原先缺失的 `recalled_memories` 键。
2. **补契约测试**（不碰业务逻辑）：新增 `tests/test_response_contract.py`，4 个用例——走工具断言 `used_tool == "weather"`、不走工具断言 `used_tool is None` + 召回形状、流式 meta 与非流式同形状、降级流 meta 带键。全 mock、无副作用。
3. **meta 语义文档化**（不改代码）：§5 把"emotion/affection 是进入本轮前的状态"从"时序瑕疵"改写为**契约**，明确它不是缺陷。

**测试证据**：`HF_HUB_OFFLINE=1 venv/bin/python -m pytest tests -q` → `7 passed in 9.52s`（3 smoke + 4 契约）。
**测试有效性证据（变异测试）**：把三处修复逐条退回，对应用例精确变红——流式 meta 退回裸 dict → `test_stream_meta_shape_matches_post` 失败；非流式 `used_tool` 不填充 → `test_post_chat_reports_used_tool` 失败；降级流去掉 `recalled_memories` 键 → `test_stream_fallback_meta_keeps_key` 失败。变异后已验证 main.py 完整复原。

**行号位移（rev2 → rev3，已逐条更新）**：旧 1-148 不变（`_memory_items` 插在旧 146 后，占新 149-160）；旧 149-256 → +12；旧 257-264（8 行手写 `MemoryItem` 映射）→ 压缩为新 269 一行；旧 265-289 → +5；旧 289（1 行降级 meta）→ 展开为新 294-301；旧 290-304 → +12。文件 304 → 316 行（+12 −7 +7）。schemas.py 未变。

**rev2（2026-09-23）— 同步 `used_tool` / `recalled_memories` 契约修复**（下列行号为 **rev2 时点**，已被 rev3 位移覆盖）

改动点（经逐一核对源码确认）：
- schemas.py:12 `MemoryItem.keywords`：`Optional[str]` → `Optional[List[str]]`（原类型与 `recall_memories` 实际返回的 list 不符）
- main.py:19 导入 `MemoryItem`；main.py:150-151,175 `_build_chat_context` 返回类型 `str` → `tuple[str, list]`
- main.py:179 与 226 两处调用点同步解包
- main.py:202-203 `_handle_chat` 回传 `recalled_memories` / `used_tool`
- main.py:237 流式 meta 补 `recalled_memories`
- main.py:257-265 `ChatResponse` 映射 `MemoryItem`

**行号位移（rev2 时点）**：文件由 292 行增至 304 行，位移为**分段常量**——旧 1-201 不变 / 旧 202-234 全部 +2 / 旧 235-253 全部 +3 / 旧 254-292 全部 +12。schemas.py 行数未变，仅 L12 类型变更。

**已作废的 rev1 结论**：原写"`recalled_memories`/`used_tool` 定义了但 main.py 从不填充，永远是默认空值"——**已修复，本报告已删除该条**。

**验收缺口（如实记录）**：
- rev2 修复方与自己都只在 mock 下验证；rev3 的 4 个契约用例同样是 **mock 级**——它们证明"字段被正确搬运和裁剪"，**不证明"真实 LLM 会正确触发工具"**。
- **真实 LLM 端到端仍未验证**（真实回复下 `used_tool` 与召回记忆是否正确），需在 Docker 内按 §3 链路复测。
- 跑 `tests/` 需 `HF_HUB_OFFLINE=1`，否则 sentence-transformers 会去 HuggingFace 拉模型元数据。
