# 记忆召回评测报告

> 生成时间：2026-09-24 19:06:23｜用例集：`memory_recall_cases.json`（sha256:a0c9dc6d7d89）
> 召回 top_k：3（与 main.py:173 `recall_memories(msg, top_k=3)` 一致）
> 总耗时：34.4s｜token 计量：tiktoken cl100k_base（近似 DeepSeek 分词）
> 召回后端：ChromaDB + `BAAI/bge-small-zh-v1.5`（真实向量检索）

**评测范围**：只覆盖检索层（`store_memory` 写入 + `recall_memories` 召回 + importance 排序截断）。
**不覆盖**：LLM 事实抽取（`extract_facts`）与回复生成——WSL 环境访问不到 DeepSeek API。
**隔离**：脚本 chdir 到临时目录后才 import，生产 `chat.db` / `chroma_db` 未被写入。

## 1. 总览

| 指标 | 值 |
|---|---|
| 用例总数 | 120 |
| 通过 | 118 |
| **总准确率** | **98.3%** |
| 平均召回延迟 | 15.6 ms |
| 中位召回延迟 | 14.4 ms |
| P95 召回延迟 | 20.0 ms |
| 最大召回延迟 | 49.3 ms |
| 平均每用例写入耗时 | 255.0 ms（写入 1137 条） |
| **平均单条记忆写入延迟** | **26.9 ms** |
| 平均召回条数 | 1.17 |
| **平均注入 token** | **21.8**（中位 19.0） |

> token 指召回结果被拼进 System Prompt 的那段文本的 token 数（`main.py:163-166` 的 `memory_text`），
> 召回层自身不调 LLM，因此没有 API token 消耗；这个数字衡量的是**每轮对话被记忆占用的上下文成本**。

## 2. 分类准确率

| 类别 | 用例数 | 通过 | 准确率 |
|---|---|---|---|
| 事实记忆 `fact_recall` | 24 | 24 | 100.0% |
| 多轮上下文依赖 `long_context` | 24 | 24 | 100.0% |
| 情感记忆 `emotion_memory` | 24 | 24 | 100.0% |
| 干扰项 `distractor` | 24 | 24 | 100.0% |
| 遗忘验证 `forgetting` | 24 | 22 | 91.7% |

### 按难度

| 难度 | 用例数 | 通过 | 准确率 |
|---|---|---|---|
| easy | 16 | 16 | 100.0% |
| hard | 52 | 51 | 98.1% |
| medium | 52 | 51 | 98.1% |

## 3. 失败案例明细

### 遗忘验证（2/24 失败）

- **`forget_005`** · medium · 写入 6 条
  - query：`我现在爱喝什么？`
  - 期望：should_recall=False，match_any=['可乐']，must_not_match=[]
  - 实召：主人已经戒了可乐改喝奶茶
  - 判定：hit_any=True，hit_bad=False
- **`forget_008`** · hard · 写入 10 条
  - query：`我还在学吉他吗？`
  - 期望：should_recall=False，match_any=['想学']，must_not_match=[]
  - 实召：主人已经放弃学吉他了；主人提到最近想学吉他
  - 判定：hit_any=True，hit_bad=False

## 4. 失败模式聚类

| 失败模式 | 条数 |
|---|---|
| 应遗忘却仍被召回（无遗忘机制） | 2 |

## 5. 结论与缺口

- 遗忘验证准确率 91.7%（22/24）。
- 平均每轮注入 22 token 的记忆上下文；
  召回延迟 P95 20ms，相对一次 LLM 调用（秒级）可忽略，**延迟不是瓶颈**。

> 完整失败清单见上；每条用例的判定依据只取决于 `recall_memories` 的返回，
> 不涉及主观打分，任何人重跑本脚本都应得到同样的通过/失败集合（检索层无随机性）。

