# 希格雯桌宠 — 项目档案（侦察报告）

> 侦察时间：2026-09-23（rev3：响应契约形状统一 + 4 个契约测试入库）｜范围：仓库全部首方代码（排除 `venv/`）
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
- LLM：DeepSeek `deepseek-v4-pro`，走 openai 2.32.0 SDK（main.py:74-110、memory_service.py:57、personality_state.py:81）
- 校验/配置：pydantic 2.13.3（schemas.py）、python-dotenv（.env.example 四键：DEEPSEEK/HEFENG/BOCHA）
- 向量库：chromadb 1.5.9（PersistentClient）+ sentence-transformers 5.5.1 + `BAAI/bge-small-zh-v1.5`（retrievers/anime_kb.py:11-18）
- 结构化存储：SQLite（标准库 sqlite3，无 ORM），单文件 `chat.db`（memory_service.py:23）
- 中文分词：jieba 0.42.1（memory_service.py:169）
- 外部 API：和风天气（tools/weather.py:17-43）、博查搜索（tools/search.py:35）
- 测试：pytest 9.0.3 + fastapi TestClient，**7 个用例**（3 smoke + 4 响应契约），实测 `7 passed`（`HF_HUB_OFFLINE=1`、Python 3.12.3、9.5s；4 个契约用例已用变异测试验证有效性）

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
   - `recall_memories(msg, top_k=3)` — 长期记忆（memory_service.py:229），**同时作为返回值回传给响应层**
   - `_build_rag_context(msg)` — 角色设定（main.py:117-146 → retrievers/anime_kb.py:32）
3. `agent.run_stream`（agent.py:110-151）：
   - 阶段一 `_run_react_planning` 放线程池（agent.py:121-123），最多 3 步（agent.py:15），每步 `_call_llm` 非流式 → 命中 `Action:` 则执行工具（weather/search）并把 `Observation` 追加进 context（agent.py:72）
   - 先 yield `meta` 包（`used_tool`/`thoughts` 由 agent.py:125 产出），main 侧再补 `emotion`/`affection`/**`recalled_memories`**（main.py:245-249；记忆经 `_memory_items`（main.py:149-158）裁成三字段）
   - 阶段二：有 `direct_answer` 就**逐字** yield（agent.py:134-135）；否则用 `clean_system` 重新发起**真 token 流式**调用（agent.py:138-149）
4. `_persist_chat` 注册为 BackgroundTasks（main.py:255），流结束后才执行：存两条消息 → `extract_facts` 提取事实 → 逐条 `store_memory` 双写 → `personality.update(msg)`
5. 异常兜底：`chat_stream` 顶层 try 失败后返回预置的 sad 流（main.py:293-303；降级 meta 同样带 `recalled_memories: []`，三条路径契约一致）

非流式 `POST /chat` 同链路，但所有副作用同步执行（main.py:198-208），并在 main.py:269 复用同一个 `_memory_items` 映射后回传 `MemoryItem` 列表——两条路径不再各写一份形状。

## 4. 记忆系统现状（重点）

**分层：两层，全部落 SQLite + ChromaDB 双写。**

| 层 | 存储 | 生命周期 |
|---|---|---|
| 短期对话历史 | SQLite `messages` 表（test_api.py:18-25），仅取最近 6 条 | 永久堆积，无清理 |
| 长期事实记忆 | SQLite `memories` 表（memory_service.py:30-39）**+** Chroma `user_memories` | 永久，无淘汰 |

- 写入时机：**每条 AI 回复后**（main.py:227-231），由 LLM 抽取（memory_service.py:44-78），约束为：最多 3 条、每条 ≤50 字、显式禁止提取天气/新闻等时效信息（memory_service.py:51-52）、importance 由模型自评（喜好/雷点 8-10，闲聊 3-5）。
- 写入去重：归一化（去尾部标点，memory_service.py:81-83）后**全表逐行比对**（memory_service.py:94-98），命中即跳过；随后 Chroma 双写，失败只 log（memory_service.py:116-124）。
- 检索：**混合召回**（memory_service.py:229-254）——向量语义 `top_k=3` + jieba 关键词 LIKE `top_k=3`，按 id 去重，再按 `importance DESC` 取 3 条注入。关键词侧另有停用词表（memory_service.py:128-163）与"2-4 字中文片段"补充切分（memory_service.py:179）。
- 排序：**没有重排（rerank）**。合并后直接按 importance 排序（memory_service.py:253），向量 distance 仅记录不参与决策（user_memory.py:77-79）。
- 遗忘/压缩：**未找到相关实现**。全仓首方代码 grep `遗忘|衰减|decay|forget|压缩|summar|rerank` 命中 0。`importance` 只用于排序（memory_service.py:253），`user_memory.delete()` 定义后无调用者（user_memory.py:92-93），`min_importance` 恒传 1 等于不过滤（memory_service.py:236），`last_accessed` 唯一写入点 main.py:180、唯一用途是排序权重（memory_service.py:207）——**没有基于时间的衰减或过期删除**。

**实测日志暴露的两个真问题**（logs/agent.log）：
1. `"我是ZZDW"` 召回出「日文名/韩文名/英文名」三条——短查询向量稀释，正是 README:106 想解决的问题，但 `get_all_tags()`（anime_kb.py:63-70）取出的 tag 是「名字/日文名」等词，用户口语几乎不会命中，日志里 tag 命中**始终为"无"**。
2. `"今天上海天气怎样？"` 仍注入 2 条 ZZDW 身份记忆（distance 0.74/0.78），说明无相关性阈值、无 rerank，低分噪声照样进 Prompt。

## 5. 情绪系统现状

- 建模：`personality` 表**强制单行**（`CHECK(id=1)`，personality_state.py:18），四个字段 = affinity(-100~100) / emotion / emotion_momentum / consecutive_positive。进程内再持一份全局单例（main.py:59）。
- 判定：每条用户消息交给 LLM 打情感分 -1~1（personality_state.py:73-103），**额外一次 API 调用**；然后按阈值改好感度——正向 +2、负向 **-10**（非对称，注释写明"负面记忆更深"，personality_state.py:127-131）。
- 情绪映射：affinity>30 且连续 2 次正向 → happy；<-20 → angry 且 momentum 至少 3 轮（怒气惯性）；<-10 → sad；否则 momentum 每轮 -1，归零后回落 normal（personality_state.py:138-150）。
- 影响回复的方式：只通过 `build_system_prompt` 四选一的语气描述注入（personality_state.py:111-118），**没有独立的情绪参数或采样参数调整**。
- **meta 时间基准（当作契约读，不是缺陷）**：`emotion`/`affection` 是**进入本轮之前**的状态——`_persist_chat` 在流结束后才调 `personality.update`（main.py:247-248 注释、main.py:234），所以"客户端看到的情绪滞后一轮"是**既定语义**，不是 bug；而同一 meta 里的 `recalled_memories` 是**本轮**召回的。两者时间基准不同，客户端应把 emotion/affection 理解为"本轮开始前的状态"。若未来要做表情实时联动，需按明确需求另立改动。

## 6. RAG 实现

- 知识库：92 条角色设定（init_anime_kb.py:5-843，id 1-92），8 个 category：identity 18 / appearance 12 / occupation 5 / personality 12 / relationship 13 / backstory 12 / behavior 12 / race 3 / quotes 5，来源标注"萌娘百科/百度百科"。
- 分块策略：**没有自动切分**。是人工把每条属性写成一句独立文档（"希格雯的发色是蓝色。"），粒度靠手写控制，未找到 chunk_size/overlap/splitter 相关实现。
- 向量库：ChromaDB PersistentClient，collection `anime_kb`，embedding = bge-small-zh-v1.5（512 维，实测 chroma.sqlite3 中 `collections.dimension=512`）。
- 召回：`retrieve()` 先纯语义 top3，再用"用户消息里出现的 tag"追加 tag 过滤 top2，合并去重（main.py:122-135）。Chroma `anime_kb` 未设 `hnsw:space`（默认 L2），而 `user_memories` 显式设为 cosine（anime_kb.py:16-18 vs user_memory.py:21-25）——**两个库距离度量不一致**（实测 collection_metadata 表只有 user_memories 一条 cosine 记录）。
- 实测数据规模：根目录 `chroma_db` embeddings=95（92+3 条记忆），`data/chroma_db`=94（92+2），两份库并存。

## 7. 工程决策点（面试用，各注明出处）

1. **手写 ReAct 而不上 LangChain**：基类留 mock，子类覆写 LLM 调用。agent.py:9-17,153-161
2. **规划/生成两阶段分离**：流式只用于最终答案，规划整体走 `asyncio.to_thread` 不阻塞事件循环。agent.py:110-123
3. **生成阶段二次隔离 Prompt**：`clean_system` 明令禁止输出 Thought/Action/Observation 标签，防 ReAct 格式泄漏给用户。agent.py:138-143
4. **两条流式路径不等价**：无工具时 `for char in direct_answer` 是逐字假流式，有工具时才是真 token 流。agent.py:134-135 vs 148
5. **meta 包前置 + 旧状态**：先发情绪再生成，牺牲一轮实时性换取客户端能提前切立绘（语义已在 §5 固化为契约）。main.py:245-249
6. **RAG 双层召回**：语义保广度 + tag 保精度，`dict.fromkeys` 去重保序。main.py:122-135
7. **记忆混合召回**：向量优先、关键词兜底，按 id 而非文本合并。memory_service.py:229-254
8. **去重靠标点归一化**：`_normalize_fact` 解决"…喝奶茶。"≠"…喝奶茶"。memory_service.py:81-98
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
- 无遗忘、无衰减、无压缩、无重排（见 §4），记忆只增不减。
- 合并后按 importance 排序会**丢掉向量相关性顺序**（memory_service.py:253），高重要度无关记忆可挤掉最相关记忆——日志已实证。
- 去重 O(n) 全表扫描（memory_service.py:94-98），量大即瓶颈。
- SQLite 与 Chroma 双写无事务无补偿，失败仅 log（memory_service.py:116-124），可能长期漂移。
- 提取粒度失准：实测把「助手是蓝色头发，不是粉色」当成用户事实存入（logs/agent.log 17:27:30）。

**稳定性/工程级**
- ReAct 空响应无重试：日志实录 `[Step 0] 格式异常…LLM原始输出 (len=0)` 直接终止规划，靠二次总结兜底，白烧一次调用（agent.py:44-55,93-101）。
- `LLMTimeoutException` 形同虚设：main.py:272 捕 `TimeoutError`，而 openai SDK 抛 `APITimeoutError`，504 分支走不到（exceptions.py:13-15）。
- 知识库 tag 机制实际失效（日志中 tag 命中恒为"无"），却每轮全量 `collection.get` 取 metadata（anime_kb.py:63-70）。
- 依赖冗余：langchain/langgraph/gradio/torch/cuda 全家桶塞进 requirements.txt，Dockerfile:11 才用 grep 剔除，本地安装体验极差。
- 版本三处不一致（3.11 / 3.11-slim / venv 3.12.3）；异常文案里还有硬编码中文兜底（main.py:87,110）。

## 9. 修订记录

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
