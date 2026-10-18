"""Compare When2Call arms against the pre-registered predictions.

Arm A and every later arm run the same 40 frozen items, so the comparison is
paired: the bootstrap resamples items, not attempts, and the statistic is the
per-item difference. That is much tighter than treating the arms as independent
samples, and it is the only correct interval for this design.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs" / "benchmarks" / "monkeys-passk-frontloop"
LABELS = ["tool_call", "request_for_info", "cannot_answer"]
KS = [1, 2, 4, 8]
B = 10000


def ledger(arm: str) -> Path:
    return OUT / ("when2call_ledger.jsonl" if arm == "A" else f"when2call_ledger_arm{arm}.jsonl")


def groups(arm: str, model: str) -> dict[str, list[dict]]:
    rows = [json.loads(x) for x in ledger(arm).read_text(encoding="utf-8").splitlines() if x.strip()]
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("model") == model and r.get("arm") == arm:
            by[r["uuid"]].append(r)
    return dict(by)


def pass_at_k(n: int, c: int, k: int) -> float:
    if n - c < k:
        return 1.0
    p = 1.0
    for i in range(k):
        p *= (n - c - i) / (n - i)
    return 1.0 - p


def think_chars(text: str) -> int:
    if "<think>" not in text:
        return 0
    tail = text.split("<think>", 1)[1]
    return len(tail.split("</think>", 1)[0])


def item_rate(g: list[dict], field: str) -> float:
    return sum(1 for r in g if r.get(field)) / len(g)


def block(gs: dict[str, list[dict]]) -> dict:
    rows = [r for g in gs.values() for r in g]
    n = len(rows)
    conf = Counter((r["gold_action"], r.get("predicted_action") or "none") for r in rows)
    per_gold: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        per_gold[r["gold_action"]][1] += 1
        per_gold[r["gold_action"]][0] += int(bool(r.get("semantic_ok")))
    # arm A predates the reasoning_chars field; recover it from the <think> block
    # that combine_output() wrote into the stored output
    reas = [r.get("reasoning_chars") if r.get("reasoning_chars") is not None else think_chars(r.get("output") or "") for r in rows]
    return {
        "n_items": len(gs),
        "n_attempts": n,
        "contract_compliance": round(100 * sum(1 for r in rows if r.get("format_ok")) / n, 2),
        "semantic": round(100 * sum(1 for r in rows if r.get("semantic_ok")) / n, 2),
        "passk_semantic": {
            str(k): round(100 * sum(pass_at_k(len(g), sum(1 for r in g if r.get("semantic_ok")), k) for g in gs.values()) / len(gs), 2)
            for k in KS
        },
        "per_gold_semantic_pct": {
            g: round(100 * v[0] / v[1], 1) for g, v in sorted(per_gold.items())
        },
        "confusion": {f"{a}->{b}": c for (a, b), c in sorted(conf.items())},
        "mean_reasoning_chars": round(sum(reas) / n, 1) if n else 0.0,
        "mean_completion_tokens": round(sum((r.get("usage") or {}).get("completion_tokens", 0) for r in rows) / n, 1),
        "mean_seconds": round(sum(r.get("elapsed_ms", 0) for r in rows) / n / 1000, 2),
    }


def paired_delta(a: dict[str, list[dict]], b: dict[str, list[dict]], field: str, seed: int = 0) -> dict:
    common = sorted(set(a) & set(b))
    diffs = [item_rate(b[u], field) - item_rate(a[u], field) for u in common]
    mean = sum(diffs) / len(diffs)
    rng = random.Random(seed)
    boots = []
    for _ in range(B):
        s = [diffs[rng.randrange(len(diffs))] for _ in range(len(diffs))]
        boots.append(sum(s) / len(s))
    boots.sort()
    lo, hi = boots[int(0.025 * B)], boots[int(0.975 * B)]
    return {
        "n_common_items": len(common),
        "mean_delta_pp": round(100 * mean, 2),
        "ci95_pp": [round(100 * lo, 2), round(100 * hi, 2)],
        "items_better": sum(1 for d in diffs if d > 0),
        "items_worse": sum(1 for d in diffs if d < 0),
        "items_tied": sum(1 for d in diffs if d == 0),
        "excludes_zero": bool(lo > 0 or hi < 0),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="A")
    ap.add_argument("--arm", required=True)
    ap.add_argument("--model", default="granite")
    args = ap.parse_args()

    a, b = groups(args.base, args.model), groups(args.arm, args.model)
    payload = {
        "model": args.model,
        "base_arm": args.base,
        "test_arm": args.arm,
        f"arm_{args.base}": block(a),
        f"arm_{args.arm}": block(b),
        "paired_delta_semantic": paired_delta(a, b, "semantic_ok"),
        "paired_delta_compliance": paired_delta(a, b, "format_ok"),
    }
    dest = OUT / f"when2call-arm{args.base}-vs-arm{args.arm}.json"
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("wrote", dest)


if __name__ == "__main__":
    main()
