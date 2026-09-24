# 记忆召回评测报告

> 生成时间：2026-09-23 19:21:27｜用例集：`memory_recall_cases.json`（sha256:a0c9dc6d7d89）
> 召回 top_k：3（与 main.py:173 `recall_memories(msg, top_k=3)` 一致）
> 总耗时：56.4s｜token 计量：字符数（未安装 tiktoken，按 1 字符≈1 token 粗估）
> 召回后端：**stub 替身（字符 bigram 重叠）**

> ⚠️ **本次为流水线自检运行，不是真实评测结果。**
> stub 后端不加载 embedding 模型、不做向量检索，只用字符 bigram 重叠当替身，
> 唯一目的是验证脚本流程（读用例 -> 隔离建库 -> 写入 -> 召回 -> 判定 -> 统计 -> 出报告）可跑通，
> 从而把「脚本自身的 bug」与「运行环境缺依赖」区分开。下面的数字**不得用于任何结论**。
>
> 真实结果请在项目 venv 内运行：`HF_HUB_OFFLINE=1 venv/bin/python tests/eval/eval_memory.py`

**评测范围**：只覆盖检索层（`store_memory` 写入 + `recall_memories` 召回 + importance 排序截断）。
**不覆盖**：LLM 事实抽取（`extract_facts`）与回复生成——WSL 环境访问不到 DeepSeek API。
**隔离**：脚本 chdir 到临时目录后才 import，生产 `chat.db` / `chroma_db` 未被写入。

## 1. 总览

| 指标 | 值 |
|---|---|
| 用例总数 | 120 |
| 通过 | 63 |
| **总准确率** | **52.5%** |
| 平均召回延迟 | 2.8 ms |
| 中位召回延迟 | 2.9 ms |
| P95 召回延迟 | 3.4 ms |
| 最大召回延迟 | 3.8 ms |
| 平均每用例写入耗时 | 424.5 ms（写入 1137 条） |
| **平均单条记忆写入延迟** | **44.8 ms** |
| 平均召回条数 | 1.12 |
| **平均注入 token** | **17.2**（中位 17.0） |

> token 指召回结果被拼进 System Prompt 的那段文本的 token 数（`main.py:163-166` 的 `memory_text`），
> 召回层自身不调 LLM，因此没有 API token 消耗；这个数字衡量的是**每轮对话被记忆占用的上下文成本**。

## 2. 分类准确率

| 类别 | 用例数 | 通过 | 准确率 |
|---|---|---|---|
| 事实记忆 `fact_recall` | 24 | 21 | 87.5% |
| 多轮上下文依赖 `long_context` | 24 | 21 | 87.5% |
| 情感记忆 `emotion_memory` | 24 | 9 | 37.5% |
| 干扰项 `distractor` | 24 | 6 | 25.0% |
| 遗忘验证 `forgetting` | 24 | 6 | 25.0% |

### 按难度

| 难度 | 用例数 | 通过 | 准确率 |
|---|---|---|---|
| easy | 16 | 10 | 62.5% |
| hard | 52 | 29 | 55.8% |
| medium | 52 | 24 | 46.2% |

## 3. 失败案例明细

### 事实记忆（3/24 失败）

- **`fact_003`** · easy · 写入 1 条
  - query：`我平时玩什么游戏呀？`
  - 期望：should_recall=True，match_any=['原神']，must_not_match=[]
  - 实召：（空）
  - 判定：hit_any=False，hit_bad=False
- **`fact_018`** · hard · 写入 8 条
  - query：`我一般几点睡觉？`
  - 期望：should_recall=True，match_any=['凌晨']，must_not_match=[]
  - 实召：（空）
  - 判定：hit_any=False，hit_bad=False
- **`fact_023`** · hard · 写入 8 条
  - query：`我有兄弟姐妹吗？`
  - 期望：should_recall=True，match_any=['妹妹']，must_not_match=[]
  - 实召：（空）
  - 判定：hit_any=False，hit_bad=False

### 多轮上下文依赖（3/24 失败）

- **`longctx_003`** · medium · 写入 21 条
  - query：`我平时玩什么游戏呀？`
  - 期望：should_recall=True，match_any=['原神']，must_not_match=[]
  - 实召：（空）
  - 判定：hit_any=False，hit_bad=False
- **`longctx_018`** · hard · 写入 26 条
  - query：`我一般几点睡觉？`
  - 期望：should_recall=True，match_any=['凌晨']，must_not_match=[]
  - 实召：（空）
  - 判定：hit_any=False，hit_bad=False
- **`longctx_023`** · medium · 写入 21 条
  - query：`我有兄弟姐妹吗？`
  - 期望：should_recall=True，match_any=['妹妹']，must_not_match=[]
  - 实召：（空）
  - 判定：hit_any=False，hit_bad=False

### 情感记忆（15/24 失败）

- **`emotion_001`** · easy · 写入 1 条
  - query：`我最近工作上还顺利吗？`
  - 期望：should_recall=True，match_any=['生气']，must_not_match=[]
  - 实召：（空）
  - 判定：hit_any=False，hit_bad=False
- **`emotion_002`** · medium · 写入 4 条
  - query：`我最近状态怎么样？`
  - 期望：should_recall=True，match_any=['焦虑']，must_not_match=[]
  - 实召：主人提到最近天气转凉了
  - 判定：hit_any=False，hit_bad=False
- **`emotion_003`** · hard · 写入 7 条
  - query：`我最近心情不太好吧？`
  - 期望：should_recall=True，match_any=['难过']，must_not_match=[]
  - 实召：主人说最近地铁在施工，通勤要绕路
  - 判定：hit_any=False，hit_bad=False
- **`emotion_004`** · easy · 写入 1 条
  - query：`我最近有什么值得高兴的事吗？`
  - 期望：should_recall=True，match_any=['开心']，must_not_match=[]
  - 实召：（空）
  - 判定：hit_any=False，hit_bad=False
- **`emotion_007`** · easy · 写入 1 条
  - query：`有人催我交东西的时候我会怎样？`
  - 期望：should_recall=True，match_any=['烦躁']，must_not_match=[]
  - 实召：（空）
  - 判定：hit_any=False，hit_bad=False
- **`emotion_008`** · medium · 写入 4 条
  - query：`我去医院会害怕什么？`
  - 期望：should_recall=True，match_any=['打针']，must_not_match=[]
  - 实召：（空）
  - 判定：hit_any=False，hit_bad=False
- **`emotion_009`** · hard · 写入 7 条
  - query：`我最近的睡眠情况如何？`
  - 期望：should_recall=True，match_any=['失眠']，must_not_match=[]
  - 实召：主人提到最近在学做番茄炒蛋；主人说电脑风扇最近声音很大；主人提到最近想学吉他
  - 判定：hit_any=False，hit_bad=False
- **`emotion_010`** · easy · 写入 1 条
  - query：`我家的猫最近怎么样？`
  - 期望：should_recall=True，match_any=['走丢']，must_not_match=[]
  - 实召：（空）
  - 判定：hit_any=False，hit_bad=False
  - …… 其余 7 条同类失败略

### 干扰项（18/24 失败）

- **`distract_001`** · medium · 写入 6 条
  - query：`我最喜欢喝的是什么饮料？`
  - 期望：should_recall=True，match_any=['奶茶']，must_not_match=['咖啡']
  - 实召：主人喜欢喝奶茶，尤其是珍珠奶茶；主人的同事小李喜欢喝美式咖啡；主人提到午饭吃的是楼下的黄焖鸡
  - 判定：hit_any=True，hit_bad=True
- **`distract_003`** · medium · 写入 6 条
  - query：`我固定做什么运动？`
  - 期望：should_recall=True，match_any=['羽毛球']，must_not_match=['篮球']
  - 实召：（空）
  - 判定：hit_any=False，hit_bad=False
- **`distract_004`** · hard · 写入 10 条
  - query：`我最喜欢哪个歌手？`
  - 期望：should_recall=True，match_any=['周杰伦']，must_not_match=['林俊杰']
  - 实召：主人最喜欢周杰伦的歌；主人的朋友很喜欢林俊杰的歌
  - 判定：hit_any=True，hit_bad=True
- **`distract_005`** · medium · 写入 6 条
  - query：`我平时玩哪个游戏？`
  - 期望：should_recall=True，match_any=['原神']，must_not_match=['崩坏']
  - 实召：（空）
  - 判定：hit_any=False，hit_bad=False
- **`distract_008`** · hard · 写入 10 条
  - query：`我最爱看哪个类型的电影？`
  - 期望：should_recall=True，match_any=['科幻']，must_not_match=['悬疑']
  - 实召：主人喜欢看科幻电影；主人的同事喜欢看悬疑电影
  - 判定：hit_any=True，hit_bad=True
- **`distract_009`** · medium · 写入 6 条
  - query：`过敏的是什么东西？`
  - 期望：should_recall=True，match_any=['过敏']，must_not_match=['芒果']
  - 实召：主人对海鲜过敏，尤其不能吃虾；主人的妹妹对芒果过敏
  - 判定：hit_any=True，hit_bad=True
- **`distract_010`** · hard · 写入 10 条
  - query：`我自己用的是什么手机？`
  - 期望：should_recall=True，match_any=['安卓']，must_not_match=['苹果']
  - 实召：主人用的是安卓手机；主人的妹妹用的是苹果手机
  - 判定：hit_any=True，hit_bad=True
- **`distract_011`** · medium · 写入 6 条
  - query：`我每天怎么去上班？`
  - 期望：should_recall=True，match_any=['开车']，must_not_match=['地铁']
  - 实召：主人的同事每天坐地铁上班；主人自己开车上班
  - 判定：hit_any=True，hit_bad=True
  - …… 其余 10 条同类失败略

### 遗忘验证（18/24 失败）

- **`forget_001`** · medium · 写入 6 条
  - query：`我现在住在哪个城市？`
  - 期望：should_recall=False，match_any=['苏州']，must_not_match=[]
  - 实召：主人以前住在苏州
  - 判定：hit_any=True，hit_bad=False
- **`forget_003`** · medium · 写入 6 条
  - query：`我养的是什么宠物？`
  - 期望：should_recall=False，match_any=['仓鼠']，must_not_match=[]
  - 实召：主人以前养的是仓鼠；主人现在养的是橘猫豆豆
  - 判定：hit_any=True，hit_bad=False
- **`forget_004`** · hard · 写入 10 条
  - query：`我用的是什么手机？`
  - 期望：should_recall=False，match_any=['苹果']，must_not_match=[]
  - 实召：主人以前用苹果手机；主人已经换成安卓手机了
  - 判定：hit_any=True，hit_bad=False
- **`forget_007`** · medium · 写入 6 条
  - query：`我过敏的情况是什么样的？`
  - 期望：should_recall=False，match_any=['对虾']，must_not_match=[]
  - 实召：主人以前是对虾过敏；主人现在确诊对海鲜整体都过敏
  - 判定：hit_any=True，hit_bad=False
- **`forget_008`** · hard · 写入 10 条
  - query：`我还在学吉他吗？`
  - 期望：should_recall=False，match_any=['想学']，must_not_match=[]
  - 实召：主人去年说想学吉他；主人已经放弃学吉他了；主人提到最近想学吉他
  - 判定：hit_any=True，hit_bad=False
- **`forget_010`** · hard · 写入 9 条
  - query：`我最近有出差的安排吗？`
  - 期望：should_recall=False，match_any=['出差']，must_not_match=[]
  - 实召：主人上周说要出差去北京；主人说最近在补一部很老的老剧
  - 判定：hit_any=True，hit_bad=False
- **`forget_011`** · medium · 写入 5 条
  - query：`我最近想买什么外设？`
  - 期望：should_recall=False，match_any=['机械键盘']，must_not_match=[]
  - 实召：主人昨天说想买一个机械键盘；主人说最近在补一部很老的老剧
  - 判定：hit_any=True，hit_bad=False
- **`forget_012`** · hard · 写入 9 条
  - query：`公司最近有什么变动吗？`
  - 期望：should_recall=False，match_any=['裁员']，must_not_match=[]
  - 实召：主人前天提到公司要裁员；主人说最近在控制饮食，少吃主食；主人今天提到公司楼下新开了一家咖啡店
  - 判定：hit_any=True，hit_bad=False
  - …… 其余 10 条同类失败略

## 4. 失败模式聚类

| 失败模式 | 条数 |
|---|---|
| 目标记忆未进 top_k（被挤出/排序丢失相关性） | 27 |
| 应遗忘却仍被召回（无遗忘机制） | 18 |
| 干扰项混入（应排除的记忆进了 top_k） | 12 |

## 5. 结论与缺口

- 遗忘验证准确率 25.0%（6/24）。
- **干扰项 25.0%**：相似但无关的记忆混入 top_k。
  根因是 `recall_memories` 取满 top_k 且**无相关性阈值**（`memory_service.py:236` 传 `min_importance=1`，
  `user_memory.py:52-54` 因此不构造 where 过滤），distance 只记录不参与决策（`user_memory.py:77-79`）。
- 平均每轮注入 17 token 的记忆上下文；
  召回延迟 P95 3ms，相对一次 LLM 调用（秒级）可忽略，**延迟不是瓶颈**。

> 完整失败清单见上；每条用例的判定依据只取决于 `recall_memories` 的返回，
> 不涉及主观打分，任何人重跑本脚本都应得到同样的通过/失败集合（检索层无随机性）。

