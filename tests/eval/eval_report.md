# 记忆召回评测报告

> 生成时间：2026-09-24 16:31:34｜用例集：`memory_recall_cases.json`（sha256:a0c9dc6d7d89）
> 召回 top_k：3（与 main.py:173 `recall_memories(msg, top_k=3)` 一致）
> 总耗时：39.6s｜token 计量：tiktoken cl100k_base（近似 DeepSeek 分词）
> 召回后端：ChromaDB + `BAAI/bge-small-zh-v1.5`（真实向量检索）

**评测范围**：只覆盖检索层（`store_memory` 写入 + `recall_memories` 召回 + importance 排序截断）。
**不覆盖**：LLM 事实抽取（`extract_facts`）与回复生成——WSL 环境访问不到 DeepSeek API。
**隔离**：脚本 chdir 到临时目录后才 import，生产 `chat.db` / `chroma_db` 未被写入。

## 1. 总览

| 指标 | 值 |
|---|---|
| 用例总数 | 120 |
| 通过 | 73 |
| **总准确率** | **60.8%** |
| 平均召回延迟 | 16.1 ms |
| 中位召回延迟 | 15.5 ms |
| P95 召回延迟 | 20.7 ms |
| 最大召回延迟 | 33.4 ms |
| 平均每用例写入耗时 | 297.4 ms（写入 1137 条） |
| **平均单条记忆写入延迟** | **31.4 ms** |
| 平均召回条数 | 2.73 |
| **平均注入 token** | **50.7**（中位 53.5） |

> token 指召回结果被拼进 System Prompt 的那段文本的 token 数（`main.py:163-166` 的 `memory_text`），
> 召回层自身不调 LLM，因此没有 API token 消耗；这个数字衡量的是**每轮对话被记忆占用的上下文成本**。

## 2. 分类准确率

| 类别 | 用例数 | 通过 | 准确率 |
|---|---|---|---|
| 事实记忆 `fact_recall` | 24 | 24 | 100.0% |
| 多轮上下文依赖 `long_context` | 24 | 24 | 100.0% |
| 情感记忆 `emotion_memory` | 24 | 24 | 100.0% |
| 干扰项 `distractor` | 24 | 1 | 4.2% |
| 遗忘验证 `forgetting` | 24 | 0 | 0.0% |

### 按难度

| 难度 | 用例数 | 通过 | 准确率 |
|---|---|---|---|
| easy | 16 | 16 | 100.0% |
| hard | 52 | 28 | 53.8% |
| medium | 52 | 29 | 55.8% |

## 3. 失败案例明细

### 干扰项（23/24 失败）

- **`distract_001`** · medium · 写入 6 条
  - query：`我最喜欢喝的是什么饮料？`
  - 期望：should_recall=True，match_any=['奶茶']，must_not_match=['咖啡']
  - 实召：主人喜欢喝奶茶，尤其是珍珠奶茶；主人的同事小李喜欢喝美式咖啡；主人提到午饭吃的是楼下的黄焖鸡
  - 判定：hit_any=True，hit_bad=True
- **`distract_002`** · hard · 写入 10 条
  - query：`我自己养的是什么宠物？`
  - 期望：should_recall=True，match_any=['橘猫']，must_not_match=['狗']
  - 实召：主人家里养了一只橘猫叫豆豆；主人的邻居家养了一条金毛狗；主人提到同事拿了一箱橘子分给大家
  - 判定：hit_any=True，hit_bad=True
- **`distract_003`** · medium · 写入 6 条
  - query：`我固定做什么运动？`
  - 期望：should_recall=True，match_any=['羽毛球']，must_not_match=['篮球']
  - 实召：主人每周三晚上去打羽毛球；主人的同事每周五去打篮球；主人提到最近在整理以前的旧照片
  - 判定：hit_any=True，hit_bad=True
- **`distract_004`** · hard · 写入 10 条
  - query：`我最喜欢哪个歌手？`
  - 期望：should_recall=True，match_any=['周杰伦']，must_not_match=['林俊杰']
  - 实召：主人最喜欢周杰伦的歌；主人的朋友很喜欢林俊杰的歌；主人提到最近在学做番茄炒蛋
  - 判定：hit_any=True，hit_bad=True
- **`distract_005`** · medium · 写入 6 条
  - query：`我平时玩哪个游戏？`
  - 期望：should_recall=True，match_any=['原神']，must_not_match=['崩坏']
  - 实召：主人喜欢玩原神；主人的室友在玩崩坏三；主人提到最近在学做番茄炒蛋
  - 判定：hit_any=True，hit_bad=True
- **`distract_006`** · hard · 写入 10 条
  - query：`我最喜欢的颜色是哪一个？`
  - 期望：should_recall=True，match_any=['深蓝色']，must_not_match=['墨绿色']
  - 实召：主人最喜欢的颜色是深蓝色；主人说过墨绿色也不错；主人提到最近想学吉他
  - 判定：hit_any=True，hit_bad=True
- **`distract_007`** · medium · 写入 6 条
  - query：`我最喜欢哪个季节？`
  - 期望：should_recall=True，match_any=['秋天']，must_not_match=['春天']
  - 实召：主人最喜欢秋天；主人说过春天也挺舒服；主人提到最近想学吉他
  - 判定：hit_any=True，hit_bad=True
- **`distract_008`** · hard · 写入 10 条
  - query：`我最爱看哪个类型的电影？`
  - 期望：should_recall=True，match_any=['科幻']，must_not_match=['悬疑']
  - 实召：主人喜欢看科幻电影；主人的同事喜欢看悬疑电影；主人说最近在补一部很老的老剧
  - 判定：hit_any=True，hit_bad=True
  - …… 其余 15 条同类失败略

### 遗忘验证（24/24 失败）

- **`forget_001`** · medium · 写入 6 条
  - query：`我现在住在哪个城市？`
  - 期望：should_recall=False，match_any=['苏州']，must_not_match=[]
  - 实召：主人已经搬到南通定居了；主人以前住在苏州；主人说最近地铁在施工，通勤要绕路
  - 判定：hit_any=True，hit_bad=False
- **`forget_002`** · hard · 写入 10 条
  - query：`我现在做什么工作？`
  - 期望：should_recall=False，match_any=['前端']，must_not_match=[]
  - 实召：主人已经转岗做空管后端开发；主人以前是做前端的；主人说最近地铁在施工，通勤要绕路
  - 判定：hit_any=True，hit_bad=False
- **`forget_003`** · medium · 写入 6 条
  - query：`我养的是什么宠物？`
  - 期望：should_recall=False，match_any=['仓鼠']，must_not_match=[]
  - 实召：主人现在养的是橘猫豆豆；主人以前养的是仓鼠；主人提到同事拿了一箱橘子分给大家
  - 判定：hit_any=True，hit_bad=False
- **`forget_004`** · hard · 写入 10 条
  - query：`我用的是什么手机？`
  - 期望：should_recall=False，match_any=['苹果']，must_not_match=[]
  - 实召：主人已经换成安卓手机了；主人以前用苹果手机；主人提到最近在整理以前的旧照片
  - 判定：hit_any=True，hit_bad=False
- **`forget_005`** · medium · 写入 6 条
  - query：`我现在爱喝什么？`
  - 期望：should_recall=False，match_any=['可乐']，must_not_match=[]
  - 实召：主人已经戒了可乐改喝奶茶；主人以前很喜欢喝可乐；主人说今天点的外卖等了四十分钟
  - 判定：hit_any=True，hit_bad=False
- **`forget_006`** · hard · 写入 10 条
  - query：`我现在的居住情况怎么样？`
  - 期望：should_recall=False，match_any=['宿舍']，must_not_match=[]
  - 实召：主人现在自己在外面租房住；主人以前住在公司宿舍；主人提到楼下健身房正在搞促销
  - 判定：hit_any=True，hit_bad=False
- **`forget_007`** · medium · 写入 6 条
  - query：`我过敏的情况是什么样的？`
  - 期望：should_recall=False，match_any=['对虾']，must_not_match=[]
  - 实召：主人现在确诊对海鲜整体都过敏；主人以前是对虾过敏；主人说电脑风扇最近声音很大
  - 判定：hit_any=True，hit_bad=False
- **`forget_008`** · hard · 写入 10 条
  - query：`我还在学吉他吗？`
  - 期望：should_recall=False，match_any=['想学']，must_not_match=[]
  - 实召：主人已经放弃学吉他了；主人提到最近想学吉他；主人去年说想学吉他
  - 判定：hit_any=True，hit_bad=False
  - …… 其余 16 条同类失败略

## 4. 失败模式聚类

| 失败模式 | 条数 |
|---|---|
| 应遗忘却仍被召回（无遗忘机制） | 24 |
| 干扰项混入（应排除的记忆进了 top_k） | 23 |

## 5. 结论与缺口

- **遗忘验证 0.0% 全灭——符合实现现状，不是测试写错。**
  项目没有任何遗忘/衰减/覆盖机制：`user_memory.delete()`（`user_memory.py:92-93`）定义后无调用者，
  `min_importance` 恒传 1（`memory_service.py:236`）等于不过滤，`importance` 只用于排序（`:253`）。
  本类断言的是「已过期/已被更正的信息不应被想起来」——这是产品缺口，不是回归。
- **干扰项 4.2%**：相似但无关的记忆混入 top_k。
  根因是 `recall_memories` 取满 top_k 且**无相关性阈值**（`memory_service.py:236` 传 `min_importance=1`，
  `user_memory.py:52-54` 因此不构造 where 过滤），distance 只记录不参与决策（`user_memory.py:77-79`）。
- 平均每轮注入 51 token 的记忆上下文；
  召回延迟 P95 21ms，相对一次 LLM 调用（秒级）可忽略，**延迟不是瓶颈**。

> 完整失败清单见上；每条用例的判定依据只取决于 `recall_memories` 的返回，
> 不涉及主观打分，任何人重跑本脚本都应得到同样的通过/失败集合（检索层无随机性）。

