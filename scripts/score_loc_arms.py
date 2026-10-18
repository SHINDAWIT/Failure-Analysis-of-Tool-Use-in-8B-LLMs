"""Compare Loc arm A (strict parser) and arm B (one repair rule) on the common items.

Arm A was frozen on 29 items. The Impacket clone was deleted from disk after the
host antivirus quarantined a file in it, so arm B covers 28. All A-vs-B numbers
below are restricted to those 28 items; the 29-item arm A column is kept for the
frozen record.

Writes runs/benchmarks/monkeys-passk-frontloop/loc-arms.json
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs" / "benchmarks" / "monkeys-passk-frontloop"
A_LEDGER = OUT / "loc_ledger.jsonl"
B_LEDGER = OUT / "loc_ledger_armB.jsonl"
GOLD = ROOT / "experiments" / "monkeys-passk-frontloop" / "fixtures" / "loc_private" / "answers.json"
DEST = OUT / "loc-arms.json"
DROPPED = "fortra__impacket-1636"
KS = [1, 2, 4, 8]


def pass_at_k(n: int, c: int, k: int) -> float:
    if n - c < k:
        return 1.0
    prod = 1.0
    for i in range(k):
        prod *= (n - c - i) / (n - i)
    return 1.0 - prod


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def norm(p: str) -> str:
    return str(p).replace("\\", "/").strip().lstrip("./")


def gold_files() -> dict[str, set[str]]:
    raw = json.loads(GOLD.read_text(encoding="utf-8"))
    out: dict[str, set[str]] = {}
    for iid, val in raw.items():
        funcs = val.get("edit_functions") if isinstance(val, dict) else val
        out[iid] = {norm(f).rsplit(":", 1)[0] for f in (funcs or [])}
    return out


def block(rows: list[dict], gf: dict[str, set[str]]) -> dict:
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by[r["instance_id"]].append(r)
    n = len(rows)
    terms = Counter(r["live_terminal"] for r in rows)
    reasons = Counter()
    tools = Counter()
    steps_len: list[int] = []
    visited_items: set[str] = set()
    for r in rows:
        steps = r.get("steps") or []
        steps_len.append(len(steps))
        touched = False
        for s in steps:
            if s.get("tool"):
                tools[s["tool"]] += 1
            if not s.get("parse_ok"):
                reasons[s.get("reason") or "unknown"] += 1
            args = s.get("args") or {}
            vals = [norm(v) for v in args.values() if isinstance(v, str)] if isinstance(args, dict) else []
            for v in vals:
                for g in gf.get(r["instance_id"], set()):
                    if v and (v == g or g.endswith("/" + v) or v.endswith("/" + g)):
                        touched = True
        if touched:
            visited_items.add(r["instance_id"])

    final_items = {r["instance_id"] for r in rows if r["live_terminal"] == "final"}
    file_items = {r["instance_id"] for r in rows if r.get("file_ok")}
    func_items = {r["instance_id"] for r in rows if r.get("func_ok")}
    finals = [r for r in rows if r["live_terminal"] == "final"]

    macro = {"file": {}, "func": {}}
    for key, flag in (("file", "file_ok"), ("func", "func_ok")):
        for k in KS:
            vals = []
            for group in by.values():
                m = len(group)
                c = sum(1 for r in group if r.get(flag))
                if m >= k:
                    vals.append(pass_at_k(m, c, k))
            macro[key][str(k)] = sum(vals) / len(vals) if vals else 0.0

    return {
        "n_items": len(by),
        "n_attempts": n,
        "terminals": {t: [terms[t], round(100 * terms[t] / n, 1)] for t in sorted(terms)},
        "file_rate": round(100 * sum(1 for r in rows if r.get("file_ok")) / n, 1),
        "func_rate": round(100 * sum(1 for r in rows if r.get("func_ok")) / n, 1),
        "final_attempts": len(finals),
        "file_ok_given_final": f"{sum(1 for r in finals if r.get('file_ok'))}/{len(finals)}",
        "func_ok_given_final": f"{sum(1 for r in finals if r.get('func_ok'))}/{len(finals)}",
        "items_any_final": len(final_items),
        "items_any_file": len(file_items),
        "items_any_func": len(func_items),
        "items_touching_gold_file": len(visited_items),
        "items_touched_but_never_final": len(visited_items - final_items),
        "mean_steps": round(sum(steps_len) / len(steps_len), 2),
        "parse_fail_reasons": dict(reasons.most_common()),
        "tool_usage": dict(tools.most_common()),
        "macro_pass_at_k": macro,
    }


def main() -> None:
    gf = gold_files()
    a_all = [r for r in load(A_LEDGER) if r.get("model") == "granite" and r.get("arm") == "A"]
    b_all = [r for r in load(B_LEDGER) if r.get("model") == "granite" and r.get("arm") == "B"]
    common = sorted({r["instance_id"] for r in a_all} & {r["instance_id"] for r in b_all})
    a_common = [r for r in a_all if r["instance_id"] in common]
    b_common = [r for r in b_all if r["instance_id"] in common]

    payload = {
        "dropped_from_comparison": DROPPED,
        "n_common_items": len(common),
        "armA_frozen_29": block(a_all, gf),
        "armA_common": block(a_common, gf),
        "armB_common": block(b_common, gf),
    }
    DEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    keys = ("n_items", "n_attempts", "terminals", "file_rate", "func_rate", "final_attempts",
            "file_ok_given_final", "func_ok_given_final", "items_any_final", "items_any_func",
            "items_touching_gold_file", "items_touched_but_never_final", "mean_steps",
            "parse_fail_reasons", "macro_pass_at_k")
    for name in ("armA_frozen_29", "armA_common", "armB_common"):
        print("=" * 30, name)
        for k in keys:
            print(" ", k, "=", json.dumps(payload[name][k], ensure_ascii=False))


if __name__ == "__main__":
    main()
