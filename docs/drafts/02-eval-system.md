# 个人 AI 项目怎么搭评测体系

<!-- ↓↓↓ 编辑说明：发布前整段删除 ↓↓↓ -->

> **待补充清单（编辑用）**
>
> 1. **开头**：项目规模——代码行数、累计对话量、迭代次数。用来交代"为什么这个体量的项目也值得搭评测"。
> 2. **第七节（还没做到的）**：**这是最重要的一处**。现在 `tests/eval/eval_report.md` 是 stub 自检版，顶部有"数字不得用于结论"的警示。真实数据需要在项目 venv 内跑：
>    `cd /home/zzdw/ai-gallery && HF_HUB_OFFLINE=1 venv/bin/python tests/eval/eval_memory.py`
>    跑完把报告里的总准确率、分类准确率、失败模式聚类表贴进正文，第 2/4/5 节都能用上。
>    注意：`emotion_memory` 和 `forgetting` 两类预期会很低，跑之前先想好怎么解释——这是文章最有价值的部分，不是丢人的部分。
> 3. **第三节（判定）**：如果后来加了更细的判定（否定词处理 / LLM 裁判），替换这一节。
>
> 全文行号锚点基准为**重构前提交 `3bc471c`**（`memory_service.py` 270 行 / `retrievers/user_memory.py` 105 行），已逐条与该提交核对、未越界。重构后该文件已 516 行，本文引的仍是重构前口径。

<!-- ↑↑↑ 编辑说明：发布前整段删除 ↑↑↑ -->

一个人做的 AI 项目，最难的不是加功能，是"改完之后我怎么知道它没变差"。

我给桌宠后端（`main.py` 起的 FastAPI 服务）搭评测的时候踩了一圈。这篇写三件事：测试集怎么设计、指标怎么选、"记忆好不好"到底怎么量化。

<!-- 待补充（真实数据）：项目规模——代码行数、累计对话量、迭代次数。用来交代"为什么这个体量的项目也值得搭评测"。 -->

## 一、先划清楚要测哪一层

最开始我是想做端到端评测的：给一句用户输入，看 AI 回复对不对。做不了，两个硬约束：

1. 事实抽取要调 DeepSeek（`memory_service.py:57`），我的评测环境访问不到 API。
2. 120 条用例走端到端会放大成上千次调用，个人项目烧不起。

所以评测锁在**检索层**：`store_memory` 写入 → `recall_memories` 召回 → importance 排序截断（`memory_service.py:229-254`）。用例直接给已结构化的 fact，等价于 `extract_facts` 的输出。

这个取舍的代价必须说清楚：**抽取质量测不到**。LLM 会不会漏掉关键信息、会不会把闲聊也当事实存进去，这一层完全没覆盖。但"召回准不准"的定义恰好落在这一层，而且它可重复、能真跑、不烧额度。

## 二、测试集的结构

120 条，五类各 24 条（`tests/eval/memory_recall_cases.json`）。单条长这样：

```json
{
  "id": "fact_001",
  "category": "fact_recall",
  "setup_turns": [
    {"fact": "主人喜欢喝奶茶，尤其是珍珠奶茶",
     "keywords": ["奶茶", "珍珠", "饮料"],
     "importance": 9}
  ],
  "query": "我最喜欢喝什么饮料来着？",
  "expected": {"should_recall": true, "match_any": ["奶茶"], "must_not_match": []},
  "difficulty": "easy"
}
```

三个关键设计点：

**`setup_turns` 是"先写入再提问"，不是"先聊天再提问"。** 每条用例自带它需要的记忆土壤，而不是复用真实历史。好处是隔离——用例之间不互相污染，跑完清库即可。坏处是它无法验证"真实对话中抽出来的 fact 长什么样"，这正好是上面说的未覆盖层。

**`expected` 拆成三个字段**，不是一个布尔值：

- `should_recall` —— 这条信息**该不该**被想起来的语义标签，只用于报告归类
- `match_any` —— 召回结果里至少命中一个才算对
- `must_not_match` —— 一个都不许出现

`must_not_match` 是专为干扰项设计的。比如"我最喜欢喝什么饮料"，setup 里同时写"主人喜欢珍珠奶茶"和"主人的同事小李喜欢美式咖啡"，召回里出现"咖啡"就判失败。

**五类场景各自对应什么**：

| 类别 | 测的是什么 | 设计要点 |
|---|---|---|
| `fact_recall` | 单条事实能否召回 | 基线，importance 取 8-9 |
| `long_context` | 20+ 条闲聊后目标还在不在 top_k | 用低 importance 闲聊做噪声 |
| `emotion_memory` | 带情绪色彩的事实能否召回 | fact 里嵌情绪词 |
| `distractor` | 相似但无关的记忆会不会混进来 | 必须配 `must_not_match` |
| `forgetting` | 该失效的信息会不会被想起来 | setup 里埋"旧值 + 新值" |

难度分三档（easy 16 / medium 52 / hard 52），按 setup 条数和对干扰的敏感度定。

这里有个必须自己承认的问题：**`emotion_memory` 类名不副实**。项目里没有独立的情感通道——人格表的好感度（`personality_state.py:16-24`）完全不参与召回，情绪只能通过 fact 文本被召回。这 24 条测的仍然是文本召回，只是 fact 里带了情绪词。类名不改，下次看报告的人会被误导。

## 三、判定：不用 LLM 当裁判

这点我做得比较坚决。判定函数是纯字符串匹配（`eval_memory.py:146-173`）：

```python
def judge(recalled: list[dict], expected: dict) -> dict:
    facts = [m.get("fact", "") for m in recalled]
    hit_any = any(tok in fact for fact in facts for tok in expected.get("match_any") or [])
    hit_bad = any(tok in fact for fact in facts for tok in expected.get("must_not_match") or [])
    if expected.get("should_recall", True):
        passed = hit_any and not hit_bad
    else:
        passed = not hit_any and not hit_bad
```

为什么不用 LLM 打分：个人项目最怕的就是"数字每周不一样"。字符串匹配意味着**任何人重跑都应该拿到同样的通过/失败集合**——检索层本身没有随机性，判定也不引入随机性。

代价同样明显：匹配是粗的。"主人不喜欢奶茶"照样命中 `match_any: ["奶茶"]`，判成通过。这是假阳性，是这套评测目前最大的有效性漏洞。

<!-- 待补充（真实数据/决策）：如果后来加了更细的判定（否定词处理、或用 LLM 当裁判但固定 seed），把这一节替换掉。 -->

## 四、指标：单一准确率没用

`summarize()`（`eval_memory.py:218-261`）输出的指标分三组，缺一不可。

**效果组**
- 总准确率 = passed / total
- **分类准确率**——这组比总数重要得多
- 按难度分组准确率

为什么要分类看：一个 85% 的总准确率，可能藏着"某一类 0%"。只看总数你只会觉得"还行"，分类看才知道哪条路是断的。

**成本组**
- 平均注入 token：召回结果拼进 System Prompt 那段文本的 token 数（对应 `main.py:175-177` 的 `memory_text`）。检索层自己不调 LLM，所以这个数衡量的是**每轮对话被记忆占用的上下文开销**。
- 平均召回条数

**性能组**
- 召回延迟 mean / median / p95 / max（`eval_memory.py:210-215` 手写 p95，不引依赖）
- 平均**单条**写入延迟

最后这条我踩过坑：一开始我把"每个用例写入全部 setup 的总耗时"标成了"平均单条写入延迟"，数字大了二十倍。现在拆成两个独立指标（`eval_memory.py:307-308`）：一个是每用例 setup 总耗时，一个是 `seed_ms_total / seeded_total` 得到的单条延迟。

**三组缺一不可**：只报准确率，你不知道为了这点准确率付出了多少上下文；只报延迟，你不知道效果是不是靠"把记忆全塞进去"堆出来的。

## 五、怎么量化"记忆好不好"

我的答案是**不要用一个数**。拆成四个能动手改的问题：

1. **存得下吗**——写入是否成功、有没有静默丢失。（`store_memory` 的 Chroma 写入失败只 log 不补偿，`memory_service.py:123-124`）
2. **想得起来吗**——召回率代理指标：`match_any` 命中率
3. **会不会乱想**——精确率代理指标：`must_not_match` 有没有被触发。这个通常没人测，但桌宠场景里"记错人"比"想不起来"更致命
4. **代价多大**——token + 延迟

再往下是**失败模式聚类**（`eval_memory.py:362-382`）。失败不是均匀分布的，聚成几类才有指导意义：

```python
if r["hit_bad"]:
    modes["干扰项混入（应排除的记忆进了 top_k）"] += 1
elif not r["expected"]["should_recall"] and r["hit_any"]:
    modes["应遗忘却仍被召回（无遗忘机制）"] += 1
elif r["expected"]["should_recall"] and not r["hit_any"]:
    modes["目标记忆未进 top_k（被挤出/排序丢失相关性）"] += 1
```

这三类的修法完全不同：干扰项混入要加相关性阈值；应遗忘却召回要加失效机制；目标进不了 top_k 要改排序公式（现在的排序只看 importance，`memory_service.py:253`）。**聚类的作用就是把"准确率若干"翻译成"接下来该动哪个函数"。**

## 六、一个便宜的工程技巧：让脚本能自证

我的评测环境装不上 `sentence-transformers`，加载不了向量模型。跑了半天报错，你根本分不清是"脚本有 bug"还是"环境缺依赖"——这个不确定性比报错本身更耗人。

解法是给脚本加一个替身后端（`eval_memory.py:104-143`）：

```python
class _StubRag:
    """评测流水线自检用的替身向量库：不加载 embedding 模型、不做向量检索。"""
    def recall(self, query: str, top_k: int = 5, min_importance: int = 1) -> list[dict]:
        q = _bigrams(query)
        scored = [(len(q & _bigrams(fact)), mid, fact) for mid, fact in self._docs.items() ...]
        ...  # 用字符 bigram 重叠当相似度替身
```

`--backend stub`（`eval_memory.py:433-435`）跑一遍：流水线通、报告出得来，说明脚本没问题，问题在环境。这个替身产出的数字在报告头部被写死标注**不得用于任何结论**（`eval_memory.py:282-289`）——因为自检版和真实结果长得一模一样，不标就会被自己骗。

顺带一个隔离技巧，比 monkeypatch 干净：脚本先 `chdir` 到临时目录**再** import（`eval_memory.py:52-60`）。因为 `memory_service.py:23` 的 `DB_PATH = "chat.db"` 和 `user_memory.py:16` 的 `./chroma_db` 都是相对路径，chdir 之后自动落到临时目录，生产库不会被写入一个字节。

## 七、还没做到的

<!-- 待补充（真实数据）：真实向量检索下的完整报告。当前 tests/eval/eval_report.md 是 stub 自检版，顶部有警示，数字不可引用。 -->

- **真实数据还没跑**。开发环境跑不了向量模型，`eval_report.md` 目前是流水线自检版。需要项目 venv 内执行：`HF_HUB_OFFLINE=1 venv/bin/python tests/eval/eval_memory.py`。
- **判定太粗**，字符串子串匹配的假阳性问题（见第三节）。
- **只有模块级**。这一层是 mock 级契约断言，端到端评测（真实 LLM 下 `used_tool` 对不对、回复有没有用上召回的记忆）是下一层的事，那层才烧额度。
- **没有 CI**。项目里既没有 `.github/` 也没有 `.gitlab-ci.yml`，评测靠手动跑。不挂到提交钩子上，它迟早会被忘掉。

## 八、给同样在写个人项目的人

1. **先划清楚能测哪一层**，别硬上端到端。测不了的部分明确写"未覆盖"，比声称"评测通过"诚实。
2. **判定逻辑越笨越好**。LLM 当裁判会让数字失去可比性——而可比性正是评测唯一的价值。
3. **指标要成组**：效果 + 成本 + 性能。单看任何一个都会被误导。
4. **失败要聚类**，不然你拿到的只是一个不敢动的百分比。
5. **让脚本能自证**：环境跑不通的时候，得有个办法区分"脚本坏了"和"依赖没装"。

搭评测花掉的时间，比反复调 prompt 花掉的时间值。
