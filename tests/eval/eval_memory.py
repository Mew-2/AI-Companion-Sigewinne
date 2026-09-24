#!/usr/bin/env python3
"""记忆召回评测：批量跑 memory_recall_cases.json，把准确率/延迟/token 写入 eval_report.md。

评测范围（必读）
────────────────
只覆盖**检索层**：store_memory 写入 -> recall_memories 召回 -> importance 排序截断。
不覆盖 LLM 事实抽取（extract_facts）与回复生成。原因：WSL 环境访问不到 DeepSeek API，
且端到端评测会把 120 条用例放大成上千次 API 调用。抽取层/端到端是下一层评测的事。

隔离（必读）
────────────────
脚本先 chdir 到临时目录，**再** import memory_service。这样 memory_service 里所有
相对路径——DB_PATH="chat.db"（memory_service.py:23）与 UserMemoryRAG("./chroma_db")
（user_memory.py:16）——全部落在临时目录。生产库不会被写入一个字节。
运行结束临时目录自动清理（--keep-tmp 可保留以便排查）。

用法
────
    HF_HUB_OFFLINE=1 venv/bin/python tests/eval/eval_memory.py
    HF_HUB_OFFLINE=1 venv/bin/python tests/eval/eval_memory.py --top-k 3 --limit 10
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import statistics
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = Path(__file__).resolve().parent
CASES_PATH = EVAL_DIR / "memory_recall_cases.json"
REPORT_PATH = EVAL_DIR / "eval_report.md"

CATEGORY_LABEL = {
    "fact_recall": "事实记忆",
    "long_context": "多轮上下文依赖",
    "emotion_memory": "情感记忆",
    "distractor": "干扰项",
    "forgetting": "遗忘验证",
}

# ── 隔离：必须发生在 import 项目模块之前 ────────────────────────
_TMP = Path(tempfile.mkdtemp(prefix="eval_mem_"))
os.chdir(_TMP)
sys.path.insert(0, str(ROOT))

# 保险：无 .env 时也不让 OpenAI 客户端构造失败（评测全程不调 LLM）
os.environ.setdefault("DEEPSEEK_API_KEY", "eval-offline-dummy")

import memory_service  # noqa: E402  （chdir 之后才能 import）

try:  # token 计数器：优先精确分词，缺包时退化为字符数
    import tiktoken

    _ENC = tiktoken.get_encoding("cl100k_base")
    _TOKEN_MODE = "tiktoken cl100k_base（近似 DeepSeek 分词）"
except Exception:  # pragma: no cover
    _ENC = None
    _TOKEN_MODE = "字符数（未安装 tiktoken，按 1 字符≈1 token 粗估）"


def count_tokens(text: str) -> int:
    if not text:
        return 0
    if _ENC is not None:
        return len(_ENC.encode(text))
    return len(text)


# ── 评测原语 ───────────────────────────────────────────────


def reset_store() -> None:
    """清空评测库：SQLite memories 表 + Chroma user_memories collection。"""
    conn = sqlite3.connect(memory_service.DB_PATH)
    conn.execute("DELETE FROM memories")
    conn.commit()
    conn.close()
    memory_service.user_memory_rag.clear()


def seed(turns: list[dict]) -> float:
    """写入 setup_turns，返回总耗时（秒）。"""
    t0 = time.perf_counter()
    for turn in turns:
        memory_service.store_memory(turn["fact"], turn["keywords"], turn["importance"])
    return time.perf_counter() - t0


def _bigrams(text: str) -> set[str]:
    return {text[i : i + 2] for i in range(len(text) - 1)}


class _StubRag:
    """评测流水线自检用的替身向量库：不加载 embedding 模型、不做向量检索。

    它存在的唯一目的，是让**没有 torch / HF 模型的环境**也能把评测脚本整条流水线
    （读取用例 -> 隔离建库 -> 写入 -> 召回 -> 判定 -> 统计 -> 出报告）跑一遍，
    从而把"脚本自身的 bug"和"环境缺失"区分开。
    其产出的数字**不代表记忆系统的真实召回能力**，不得用于结论。
    """

    def __init__(self) -> None:
        self._docs: dict[str, str] = {}

    def add_memory(self, memory_id, fact, keywords, importance=5, source="dialogue") -> None:
        self._docs[str(memory_id)] = fact

    def recall(self, query: str, top_k: int = 5, min_importance: int = 1) -> list[dict]:
        q = _bigrams(query)
        scored = []
        for mid, fact in self._docs.items():
            overlap = len(q & _bigrams(fact))
            if overlap:
                scored.append((overlap, mid, fact))
        scored.sort(key=lambda x: -x[0])
        return [
            {
                "id": mid,
                "fact": fact,
                "keywords": [],
                "importance": 5,
                "created_at": "",
                "distance": 1.0 / (1 + overlap),
            }
            for overlap, mid, fact in scored[:top_k]
        ]

    def clear(self) -> None:
        self._docs.clear()

    def count(self) -> int:
        return len(self._docs)


def judge(recalled: list[dict], expected: dict) -> dict:
    """判定召回是否满足期望。

    match_any       —— 至少一条召回 fact 命中该子串（正例应命中）
    must_not_match  —— 任何召回 fact 都不得命中（干扰项不得混入）
    should_recall   —— 该信息「应不应该被想起来」的语义标签，仅用于报告归类
    """
    facts = [m.get("fact", "") for m in recalled]

    hit_any = any(
        tok in fact for fact in facts for tok in expected.get("match_any") or []
    )
    hit_bad = any(
        tok in fact for fact in facts for tok in expected.get("must_not_match") or []
    )

    if expected.get("should_recall", True):
        passed = hit_any and not hit_bad
    else:
        passed = not hit_any and not hit_bad

    return {
        "passed": passed,
        "hit_any": hit_any,
        "hit_bad": hit_bad,
        "recalled_facts": facts,
        "prompt_text": "\n".join(f"- {f}" for f in facts),
    }


def run_case(case: dict, top_k: int) -> dict:
    reset_store()
    seed_sec = seed(case["setup_turns"])

    t0 = time.perf_counter()
    recalled = memory_service.recall_memories(case["query"], top_k=top_k)
    latency_ms = (time.perf_counter() - t0) * 1000

    verdict = judge(recalled, case["expected"])
    verdict.update(
        {
            "id": case["id"],
            "category": case["category"],
            "difficulty": case["difficulty"],
            "query": case["query"],
            "expected": case["expected"],
            "seeded": len(case["setup_turns"]),
            "recalled_n": len(recalled),
            "seed_ms": seed_sec * 1000,
            "latency_ms": latency_ms,
            "tokens": count_tokens(verdict["prompt_text"]),
            "distances": [m.get("distance") for m in recalled],
        }
    )
    return verdict


# ── 统计 ───────────────────────────────────────────────────


def _rate(passed: int, total: int) -> str:
    return f"{passed / total * 100:.1f}%" if total else "n/a"


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
    return ordered[idx]


def summarize(results: list[dict]) -> dict:
    by_cat: dict[str, list[dict]] = {}
    for r in results:
        by_cat.setdefault(r["category"], []).append(r)

    latencies = [r["latency_ms"] for r in results]
    seeded_total = sum(r["seeded"] for r in results)
    seed_ms_total = sum(r["seed_ms"] for r in results)
    summary = {
        "total": len(results),
        "passed": sum(r["passed"] for r in results),
        "by_category": {
            cat: {
                "total": len(rs),
                "passed": sum(r["passed"] for r in rs),
                "rate": _rate(sum(r["passed"] for r in rs), len(rs)),
            }
            for cat, rs in by_cat.items()
        },
        "by_difficulty": {
            diff: {
                "total": len(rs),
                "passed": sum(r["passed"] for r in rs),
                "rate": _rate(sum(r["passed"] for r in rs), len(rs)),
            }
            for diff, rs in (
                (d, [r for r in results if r["difficulty"] == d])
                for d in sorted({r["difficulty"] for r in results})
            )
        },
        "latency": {
            "mean": statistics.fmean(latencies) if latencies else 0.0,
            "median": statistics.median(latencies) if latencies else 0.0,
            "p95": _p95(latencies),
            "max": max(latencies) if latencies else 0.0,
        },
        "seed_ms_mean": statistics.fmean([r["seed_ms"] for r in results]),
        "seeded_total": seeded_total,
        "seed_ms_per_item": (seed_ms_total / seeded_total) if seeded_total else 0.0,
        "tokens_mean": statistics.fmean([r["tokens"] for r in results]),
        "tokens_median": statistics.median([r["tokens"] for r in results]),
        "recalled_n_mean": statistics.fmean([r["recalled_n"] for r in results]),
    }
    return summary


def build_report(summary: dict, results: list[dict], args, elapsed: float) -> str:
    cases_bytes = CASES_PATH.read_bytes()
    digest = hashlib.sha256(cases_bytes).hexdigest()[:12]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = []
    add = lines.append

    add("# 记忆召回评测报告")
    add("")
    add(f"> 生成时间：{now}｜用例集：`memory_recall_cases.json`（sha256:{digest}）")
    add(f"> 召回 top_k：{args.top_k}（与 main.py:173 `recall_memories(msg, top_k=3)` 一致）")
    add(f"> 总耗时：{elapsed:.1f}s｜token 计量：{_TOKEN_MODE}")
    if args.backend == "stub":
        add("> 召回后端：**stub 替身（字符 bigram 重叠）**")
    else:
        add("> 召回后端：ChromaDB + `BAAI/bge-small-zh-v1.5`（真实向量检索）")
    add("")
    if args.backend == "stub":
        add("> ⚠️ **本次为流水线自检运行，不是真实评测结果。**")
        add("> stub 后端不加载 embedding 模型、不做向量检索，只用字符 bigram 重叠当替身，")
        add("> 唯一目的是验证脚本流程（读用例 -> 隔离建库 -> 写入 -> 召回 -> 判定 -> 统计 -> 出报告）可跑通，")
        add("> 从而把「脚本自身的 bug」与「运行环境缺依赖」区分开。下面的数字**不得用于任何结论**。")
        add(">")
        add("> 真实结果请在项目 venv 内运行：`HF_HUB_OFFLINE=1 venv/bin/python tests/eval/eval_memory.py`")
        add("")
    add("**评测范围**：只覆盖检索层（`store_memory` 写入 + `recall_memories` 召回 + importance 排序截断）。")
    add("**不覆盖**：LLM 事实抽取（`extract_facts`）与回复生成——WSL 环境访问不到 DeepSeek API。")
    add("**隔离**：脚本 chdir 到临时目录后才 import，生产 `chat.db` / `chroma_db` 未被写入。")
    add("")

    # 总览
    add("## 1. 总览")
    add("")
    add("| 指标 | 值 |")
    add("|---|---|")
    add(f"| 用例总数 | {summary['total']} |")
    add(f"| 通过 | {summary['passed']} |")
    add(f"| **总准确率** | **{_rate(summary['passed'], summary['total'])}** |")
    add(f"| 平均召回延迟 | {summary['latency']['mean']:.1f} ms |")
    add(f"| 中位召回延迟 | {summary['latency']['median']:.1f} ms |")
    add(f"| P95 召回延迟 | {summary['latency']['p95']:.1f} ms |")
    add(f"| 最大召回延迟 | {summary['latency']['max']:.1f} ms |")
    add(f"| 平均每用例写入耗时 | {summary['seed_ms_mean']:.1f} ms（写入 {summary['seeded_total']} 条） |")
    add(f"| **平均单条记忆写入延迟** | **{summary['seed_ms_per_item']:.1f} ms** |")
    add(f"| 平均召回条数 | {summary['recalled_n_mean']:.2f} |")
    add(f"| **平均注入 token** | **{summary['tokens_mean']:.1f}**（中位 {summary['tokens_median']:.1f}） |")
    add("")
    add("> token 指召回结果被拼进 System Prompt 的那段文本的 token 数（`main.py:163-166` 的 `memory_text`），")
    add("> 召回层自身不调 LLM，因此没有 API token 消耗；这个数字衡量的是**每轮对话被记忆占用的上下文成本**。")
    add("")

    # 分类
    add("## 2. 分类准确率")
    add("")
    add("| 类别 | 用例数 | 通过 | 准确率 |")
    add("|---|---|---|---|")
    for cat, label in CATEGORY_LABEL.items():
        s = summary["by_category"].get(cat)
        if not s:
            continue
        add(f"| {label} `{cat}` | {s['total']} | {s['passed']} | {s['rate']} |")
    add("")

    add("### 按难度")
    add("")
    add("| 难度 | 用例数 | 通过 | 准确率 |")
    add("|---|---|---|---|")
    for diff, s in summary["by_difficulty"].items():
        add(f"| {diff} | {s['total']} | {s['passed']} | {s['rate']} |")
    add("")

    # 失败案例
    add("## 3. 失败案例明细")
    add("")
    failed = [r for r in results if not r["passed"]]
    if not failed:
        add("无失败用例。")
        add("")
    else:
        for cat, label in CATEGORY_LABEL.items():
            cat_failed = [r for r in failed if r["category"] == cat]
            if not cat_failed:
                continue
            add(f"### {label}（{len(cat_failed)}/{len([r for r in results if r['category'] == cat])} 失败）")
            add("")
            for r in cat_failed[:8]:
                exp = r["expected"]
                add(f"- **`{r['id']}`** · {r['difficulty']} · 写入 {r['seeded']} 条")
                add(f"  - query：`{r['query']}`")
                add(f"  - 期望：should_recall={exp['should_recall']}，match_any={exp.get('match_any')}，must_not_match={exp.get('must_not_match')}")
                got = "；".join(r["recalled_facts"]) or "（空）"
                add(f"  - 实召：{got}")
                add(f"  - 判定：hit_any={r['hit_any']}，hit_bad={r['hit_bad']}")
            if len(cat_failed) > 8:
                add(f"  - …… 其余 {len(cat_failed) - 8} 条同类失败略")
            add("")

    # 失败模式聚类
    add("## 4. 失败模式聚类")
    add("")
    modes = Counter()
    for r in failed:
        if r["hit_bad"]:
            modes["干扰项混入（应排除的记忆进了 top_k）"] += 1
        elif not r["expected"]["should_recall"] and r["hit_any"]:
            modes["应遗忘却仍被召回（无遗忘机制）"] += 1
        elif r["expected"]["should_recall"] and not r["hit_any"]:
            modes["目标记忆未进 top_k（被挤出/排序丢失相关性）"] += 1
        else:
            modes["其他"] += 1
    if modes:
        add("| 失败模式 | 条数 |")
        add("|---|---|")
        for mode, n in modes.most_common():
            add(f"| {mode} | {n} |")
    else:
        add("无。")
    add("")

    # 结论（基于实测数据自动生成）
    add("## 5. 结论与缺口")
    add("")
    cat = summary["by_category"]

    forget = cat.get("forgetting")
    if forget and forget["passed"] == 0:
        add(f"- **遗忘验证 {forget['rate']} 全灭——符合实现现状，不是测试写错。**")
        add("  项目没有任何遗忘/衰减/覆盖机制：`user_memory.delete()`（`user_memory.py:92-93`）定义后无调用者，")
        add("  `min_importance` 恒传 1（`memory_service.py:236`）等于不过滤，`importance` 只用于排序（`:253`）。")
        add("  本类断言的是「已过期/已被更正的信息不应被想起来」——这是产品缺口，不是回归。")
    elif forget:
        add(f"- 遗忘验证准确率 {forget['rate']}（{forget['passed']}/{forget['total']}）。")

    dist = cat.get("distractor")
    if dist and dist["passed"] < dist["total"]:
        add(f"- **干扰项 {dist['rate']}**：相似但无关的记忆混入 top_k。")
        add("  根因是 `recall_memories` 取满 top_k 且**无相关性阈值**（`memory_service.py:236` 传 `min_importance=1`，")
        add("  `user_memory.py:52-54` 因此不构造 where 过滤），distance 只记录不参与决策（`user_memory.py:77-79`）。")

    lc = cat.get("long_context")
    fr = cat.get("fact_recall")
    if lc and fr and lc["passed"] < fr["passed"]:
        add(f"- **长上下文衰减**：多轮场景 {lc['rate']} vs 基础事实 {fr['rate']}。")
        add("  20+ 条闲聊把目标挤出 top_k 时，说明「记忆能存下」与「能被想起来」是两件事。")

    add(f"- 平均每轮注入 {summary['tokens_mean']:.0f} token 的记忆上下文；")
    add(f"  召回延迟 P95 {summary['latency']['p95']:.0f}ms，相对一次 LLM 调用（秒级）可忽略，**延迟不是瓶颈**。")
    add("")
    add("> 完整失败清单见上；每条用例的判定依据只取决于 `recall_memories` 的返回，")
    add("> 不涉及主观打分，任何人重跑本脚本都应得到同样的通过/失败集合（检索层无随机性）。")
    add("")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="记忆召回评测")
    parser.add_argument("--top-k", type=int, default=3, help="召回条数，默认 3（与生产一致）")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 条（调试用）")
    parser.add_argument("--keep-tmp", action="store_true", help="保留临时目录以便排查")
    parser.add_argument(
        "--backend",
        choices=["real", "stub"],
        default="real",
        help="real=真实 Chroma 向量检索（默认）；stub=替身检索，仅用于验证评测流水线自身",
    )
    args = parser.parse_args()

    if args.backend == "stub":
        memory_service.user_memory_rag = _StubRag()
        print("[eval] 已切到 stub 后端：自检模式，产出的数字无意义")

    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if args.limit:
        cases = cases[: args.limit]

    print(f"[eval] 隔离目录: {_TMP}")
    print(f"[eval] 用例 {len(cases)} 条，top_k={args.top_k}，token 计量: {_TOKEN_MODE}")
    print("[eval] 预热 embedding 模型（首次加载较慢）...")

    warmup_t0 = time.perf_counter()
    try:
        memory_service.recall_memories("预热", top_k=1)
    except Exception as exc:  # 空库时的边界，忽略
        print(f"[eval] 预热提示: {exc}")
    print(f"[eval] 预热完成 {time.perf_counter() - warmup_t0:.1f}s")

    started = time.perf_counter()
    results: list[dict] = []
    for i, case in enumerate(cases, 1):
        try:
            results.append(run_case(case, args.top_k))
        except Exception as exc:
            print(f"[eval] !! {case['id']} 执行异常: {exc}")
            results.append({
                "id": case["id"], "category": case["category"],
                "difficulty": case["difficulty"], "query": case["query"],
                "expected": case["expected"], "seeded": len(case["setup_turns"]),
                "recalled_n": 0, "seed_ms": 0.0, "latency_ms": 0.0, "tokens": 0,
                "distances": [], "passed": False, "hit_any": False, "hit_bad": False,
                "recalled_facts": [f"<异常: {exc}>"],
            })
        if i % 20 == 0 or i == len(cases):
            ok = sum(r["passed"] for r in results)
            print(f"[eval] {i}/{len(cases)} 通过 {ok} ({ok / len(results) * 100:.1f}%)")

    elapsed = time.perf_counter() - started
    summary = summarize(results)
    REPORT_PATH.write_text(build_report(summary, results, args, elapsed), encoding="utf-8")

    print(f"\n[eval] 完成：{summary['passed']}/{summary['total']} "
          f"= {_rate(summary['passed'], summary['total'])}")
    print(f"[eval] 报告已写入 {REPORT_PATH}")

    if not args.keep_tmp:
        shutil.rmtree(_TMP, ignore_errors=True)
    else:
        print(f"[eval] 临时目录保留在 {_TMP}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
