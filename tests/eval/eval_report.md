# 记忆召回评测报告

> 生成时间：2026-09-24 18:41:31｜用例集：`memory_recall_cases.json`（sha256:a0c9dc6d7d89）
> 召回 top_k：3（与 main.py:173 `recall_memories(msg, top_k=3)` 一致）
> 总耗时：34.9s｜token 计量：tiktoken cl100k_base（近似 DeepSeek 分词）
> 召回后端：ChromaDB + `BAAI/bge-small-zh-v1.5`（真实向量检索）

**评测范围**：只覆盖检索层（`store_memory` 写入 + `recall_memories` 召回 + importance 排序截断）。
**不覆盖**：LLM 事实抽取（`extract_facts`）与回复生成——WSL 环境访问不到 DeepSeek API。
**隔离**：脚本 chdir 到临时目录后才 import，生产 `chat.db` / `chroma_db` 未被写入。

## 1. 总览

| 指标 | 值 |
|---|---|
| 用例总数 | 120 |
| 通过 | 97 |
| **总准确率** | **80.8%** |
| 平均召回延迟 | 14.8 ms |
| 中位召回延迟 | 14.6 ms |
| P95 召回延迟 | 17.7 ms |
| 最大召回延迟 | 19.4 ms |
| 平均每用例写入耗时 | 261.1 ms（写入 1137 条） |
| **平均单条记忆写入延迟** | **27.6 ms** |
| 平均召回条数 | 1.18 |
| **平均注入 token** | **21.5**（中位 20.0） |

> token 指召回结果被拼进 System Prompt 的那段文本的 token 数（`main.py:163-166` 的 `memory_text`），
> 召回层自身不调 LLM，因此没有 API token 消耗；这个数字衡量的是**每轮对话被记忆占用的上下文成本**。

## 2. 分类准确率

| 类别 | 用例数 | 通过 | 准确率 |
|---|---|---|---|
| 事实记忆 `fact_recall` | 24 | 24 | 100.0% |
| 多轮上下文依赖 `long_context` | 24 | 24 | 100.0% |
| 情感记忆 `emotion_memory` | 24 | 24 | 100.0% |
| 干扰项 `distractor` | 24 | 24 | 100.0% |
| 遗忘验证 `forgetting` | 24 | 1 | 4.2% |

### 按难度

| 难度 | 用例数 | 通过 | 准确率 |
|---|---|---|---|
| easy | 16 | 16 | 100.0% |
| hard | 52 | 41 | 78.8% |
| medium | 52 | 40 | 76.9% |

## 3. 失败案例明细

### 遗忘验证（23/24 失败）

- **`forget_001`** · medium · 写入 6 条
  - query：`我现在住在哪个城市？`
  - 期望：should_recall=False，match_any=['苏州']，must_not_match=[]
  - 实召：主人以前住在苏州；主人已经搬到南通定居了
  - 判定：hit_any=True，hit_bad=False
- **`forget_002`** · hard · 写入 10 条
  - query：`我现在做什么工作？`
  - 期望：should_recall=False，match_any=['前端']，must_not_match=[]
  - 实召：主人以前是做前端的；主人已经转岗做空管后端开发
  - 判定：hit_any=True，hit_bad=False
- **`forget_003`** · medium · 写入 6 条
  - query：`我养的是什么宠物？`
  - 期望：should_recall=False，match_any=['仓鼠']，must_not_match=[]
  - 实召：主人现在养的是橘猫豆豆；主人以前养的是仓鼠
  - 判定：hit_any=True，hit_bad=False
- **`forget_004`** · hard · 写入 10 条
  - query：`我用的是什么手机？`
  - 期望：should_recall=False，match_any=['苹果']，must_not_match=[]
  - 实召：主人以前用苹果手机；主人已经换成安卓手机了
  - 判定：hit_any=True，hit_bad=False
- **`forget_005`** · medium · 写入 6 条
  - query：`我现在爱喝什么？`
  - 期望：should_recall=False，match_any=['可乐']，must_not_match=[]
  - 实召：主人以前很喜欢喝可乐；主人已经戒了可乐改喝奶茶
  - 判定：hit_any=True，hit_bad=False
- **`forget_007`** · medium · 写入 6 条
  - query：`我过敏的情况是什么样的？`
  - 期望：should_recall=False，match_any=['对虾']，must_not_match=[]
  - 实召：主人现在确诊对海鲜整体都过敏；主人以前是对虾过敏
  - 判定：hit_any=True，hit_bad=False
- **`forget_008`** · hard · 写入 10 条
  - query：`我还在学吉他吗？`
  - 期望：should_recall=False，match_any=['想学']，must_not_match=[]
  - 实召：主人已经放弃学吉他了；主人提到最近想学吉他；主人去年说想学吉他
  - 判定：hit_any=True，hit_bad=False
- **`forget_009`** · medium · 写入 5 条
  - query：`我最近身体怎么样？`
  - 期望：should_recall=False，match_any=['感冒']，must_not_match=[]
  - 实召：主人上个月感冒了，一直咳嗽；主人提到最近想学吉他
  - 判定：hit_any=True，hit_bad=False
- **`forget_010`** · hard · 写入 9 条
  - query：`我最近有出差的安排吗？`
  - 期望：should_recall=False，match_any=['出差']，must_not_match=[]
  - 实召：主人上周说要出差去北京
  - 判定：hit_any=True，hit_bad=False
- **`forget_011`** · medium · 写入 5 条
  - query：`我最近想买什么外设？`
  - 期望：should_recall=False，match_any=['机械键盘']，must_not_match=[]
  - 实召：主人昨天说想买一个机械键盘；主人提到想换一个更好的显示器
  - 判定：hit_any=True，hit_bad=False
- **`forget_012`** · hard · 写入 9 条
  - query：`公司最近有什么变动吗？`
  - 期望：should_recall=False，match_any=['裁员']，must_not_match=[]
  - 实召：主人前天提到公司要裁员；主人今天提到公司楼下新开了一家咖啡店
  - 判定：hit_any=True，hit_bad=False
- **`forget_013`** · medium · 写入 5 条
  - query：`我周末打算做什么？`
  - 期望：should_recall=False，match_any=['爬山']，must_not_match=[]
  - 实召：主人提到周末打算去趟超市囤点东西；主人之前说周末要去爬山
  - 判定：hit_any=True，hit_bad=False
- **`forget_014`** · hard · 写入 10 条
  - query：`我打算养宠物吗？`
  - 期望：should_recall=False，match_any=['想养一只狗']，must_not_match=[]
  - 实召：主人已经决定不养狗了，专心养猫；主人上周说想养一只狗
  - 判定：hit_any=True，hit_bad=False
- **`forget_015`** · medium · 写入 6 条
  - query：`我最近工作上有变动吗？`
  - 期望：should_recall=False，match_any=['换工作']，must_not_match=[]
  - 实召：主人之前说想换工作
  - 判定：hit_any=True，hit_bad=False
- **`forget_016`** · hard · 写入 9 条
  - query：`我昨天中午吃了什么？`
  - 期望：should_recall=False，match_any=['火锅']，must_not_match=[]
  - 实召：主人昨天说午饭吃了火锅
  - 判定：hit_any=True，hit_bad=False
- **`forget_017`** · medium · 写入 6 条
  - query：`我去医院的结果怎么样？`
  - 期望：should_recall=False，match_any=['想去看医生']，must_not_match=[]
  - 实召：主人看完医生了，身体没大问题；主人上周说想去看医生
  - 判定：hit_any=True，hit_bad=False
- **`forget_018`** · hard · 写入 9 条
  - query：`我最近在追什么剧？`
  - 期望：should_recall=False，match_any=['悬疑剧']，must_not_match=[]
  - 实召：主人之前说在追一部悬疑剧；主人说昨晚追剧追到两点
  - 判定：hit_any=True，hit_bad=False
- **`forget_019`** · medium · 写入 5 条
  - query：`我最近有旅游计划吗？`
  - 期望：should_recall=False，match_any=['海南']，must_not_match=[]
  - 实召：主人上个月说要去海南旅游
  - 判定：hit_any=True，hit_bad=False
- **`forget_020`** · hard · 写入 10 条
  - query：`我戒烟这件事进展如何？`
  - 期望：should_recall=False，match_any=['打算戒烟']，must_not_match=[]
  - 实召：主人之前说打算戒烟；主人已经成功戒烟三个月了
  - 判定：hit_any=True，hit_bad=False
- **`forget_021`** · medium · 写入 5 条
  - query：`我的手机出过什么问题吗？`
  - 期望：should_recall=False，match_any=['摔坏']，must_not_match=[]
  - 实召：主人昨天说手机屏幕摔坏了
  - 判定：hit_any=True，hit_bad=False
- **`forget_022`** · hard · 写入 9 条
  - query：`我最近有搬家的打算吗？`
  - 期望：should_recall=False，match_any=['考虑搬家']，must_not_match=[]
  - 实召：主人前天说在考虑搬家
  - 判定：hit_any=True，hit_bad=False
- **`forget_023`** · medium · 写入 5 条
  - query：`我上周末去干什么了？`
  - 期望：should_recall=False，match_any=['婚礼']，must_not_match=[]
  - 实召：主人上周末说要去参加同学婚礼
  - 判定：hit_any=True，hit_bad=False
- **`forget_024`** · hard · 写入 10 条
  - query：`我买显示器的事怎么样了？`
  - 期望：should_recall=False，match_any=['想买个新显示器']，must_not_match=[]
  - 实召：主人已经买好新显示器了；主人之前说想买个新显示器；主人提到想换一个更好的显示器
  - 判定：hit_any=True，hit_bad=False

## 4. 失败模式聚类

| 失败模式 | 条数 |
|---|---|
| 应遗忘却仍被召回（无遗忘机制） | 23 |

## 5. 结论与缺口

- 遗忘验证准确率 4.2%（1/24）。
- 平均每轮注入 22 token 的记忆上下文；
  召回延迟 P95 18ms，相对一次 LLM 调用（秒级）可忽略，**延迟不是瓶颈**。

> 完整失败清单见上；每条用例的判定依据只取决于 `recall_memories` 的返回，
> 不涉及主观打分，任何人重跑本脚本都应得到同样的通过/失败集合（检索层无随机性）。

