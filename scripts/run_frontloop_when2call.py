"""Run When2Call 40 x N=8 for the model currently served on :8080."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "experiments" / "monkeys-passk-frontloop"
sys.path.insert(0, str(PKG))

from monkeys_passk_frontloop.client import LlamaServerClient  # noqa: E402
from monkeys_passk_frontloop.harness import run_when2call_attempt  # noqa: E402
from monkeys_passk_frontloop.schema import f0, pass_at_k, selected  # noqa: E402

OUT = ROOT / "runs" / "benchmarks" / "monkeys-passk-frontloop"


def ledger_for(arm: str) -> Path:
    """Arm A is the frozen record and lives in its own file. Every other arm gets
    a separate file so no later run can append to, or be confused with, arm A."""
    return OUT / ("when2call_ledger.jsonl" if arm == "A" else f"when2call_ledger_arm{arm}.jsonl")


def wait_health(client: LlamaServerClient, timeout_s: float = 240.0) -> dict:
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout_s:
        try:
            last = client.health()
            if last:
                return last
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
            time.sleep(2)
    raise SystemExit(f"llama-server health timeout: {last}")


def load_done(arm: str) -> set[str]:
    done: set[str] = set()
    path = ledger_for(arm)
    if not path.exists():
        return done
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            done.add(json.loads(line)["assignment_id"])
    return done


def append_row(row: dict, arm: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    slim = {k: v for k, v in row.items() if k != "outputs"}
    slim["output"] = row["outputs"][0] if row.get("outputs") else ""
    with ledger_for(arm).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(slim, ensure_ascii=False) + "\n")


def load_rows(arm: str) -> list[dict]:
    path = ledger_for(arm)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def summarize(rows: list[dict], model: str, arm: str = "A") -> dict:
    subset = [r for r in rows if r["model"] == model and r["arm"] == arm]
    by_uuid: dict[str, list[dict]] = {}
    for row in subset:
        by_uuid.setdefault(row["uuid"], []).append(row)
    ks = f0()["sampling"]["k"]
    items = []
    for uid, group in sorted(by_uuid.items()):
        n = len(group)
        c_fmt = sum(1 for r in group if r["format_ok"])
        c_sem = sum(1 for r in group if r["semantic_ok"])
        items.append(
            {
                "uuid": uid,
                "gold": group[0]["gold_action"],
                "n": n,
                "c_format": c_fmt,
                "c_semantic": c_sem,
                "passk_format": {str(k): pass_at_k(n, c_fmt, k) for k in ks} if n else {},
                "passk_semantic": {str(k): pass_at_k(n, c_sem, k) for k in ks} if n else {},
            }
        )
    macro_fmt = {str(k): (sum(it["passk_format"][str(k)] for it in items) / len(items) if items else 0.0) for k in ks}
    macro_sem = {str(k): (sum(it["passk_semantic"][str(k)] for it in items) / len(items) if items else 0.0) for k in ks}
    confusion = Counter((r["gold_action"], r.get("predicted_action") or "none") for r in subset)
    reas = [r.get("reasoning_chars", 0) for r in subset]
    toks = [(r.get("usage") or {}).get("completion_tokens", 0) for r in subset]
    return {
        "model": model,
        "arm": arm,
        "manipulation_check": {
            "mean_reasoning_chars": (sum(reas) / len(reas)) if reas else 0.0,
            "rows_with_any_reasoning": sum(1 for x in reas if x > 0),
            "mean_completion_tokens": (sum(toks) / len(toks)) if toks else 0.0,
        },
        "n_rows": len(subset),
        "n_items": len(items),
        "format_rate": (sum(1 for r in subset if r["format_ok"]) / len(subset)) if subset else 0.0,
        "semantic_rate": (sum(1 for r in subset if r["semantic_ok"]) / len(subset)) if subset else 0.0,
        "macro_passk_format": macro_fmt,
        "macro_passk_semantic": macro_sem,
        "confusion_gold_pred": {f"{a}->{b}": c for (a, b), c in sorted(confusion.items())},
        "items": items,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="granite", choices=["granite", "ministral"])
    parser.add_argument("--limit", type=int, default=0, help="max new assignments this process")
    parser.add_argument("--arm", default="A", help="A is the frozen arm; any other label writes its own ledger")
    parser.add_argument("--thinking-off", action="store_true", help="disable the thinking channel via chat_template_kwargs")
    parser.add_argument("--n-predict", type=int, default=0, help="override the frozen generation budget")
    args = parser.parse_args()
    if args.arm == "A" and (args.thinking_off or args.n_predict):
        raise SystemExit("refusing to write a modified condition into the frozen arm A ledger; pass --arm")
    cfg = f0()
    ids = selected()["stage1_when2call"]["ids"]
    reps = list(cfg["independent"]["replicate_id"])
    client = LlamaServerClient(timeout_s=float(cfg["runtime"]["wall_time_s"]) + 15)
    health = wait_health(client)
    print("health", json.dumps(health), flush=True)
    done = load_done(args.arm)
    planned = [f"{uid}:{args.model}:{args.arm}:{rid}" for uid in ids for rid in reps]
    todo = [aid for aid in planned if aid not in done]
    print(f"arm={args.arm} ledger={ledger_for(args.arm).name} planned={len(planned)} done={len(done)} todo={len(todo)}", flush=True)
    n_run = 0
    for aid in todo:
        uuid, model, arm, rid_s = aid.rsplit(":", 3)
        row = run_when2call_attempt(
            client,
            uuid,
            model_name=model,
            replicate_id=int(rid_s),
            arm=arm,
            n_predict=args.n_predict or None,
            thinking=False if args.thinking_off else None,
        )
        append_row(row, args.arm)
        n_run += 1
        print(
            f"{row['assignment_id']} fmt={row['format_ok']} sem={row['semantic_ok']} "
            f"pred={row['predicted_action']} gold={row['gold_action']} "
            f"term={row['live_terminal']} ms={row['elapsed_ms']}",
            flush=True,
        )
        if args.limit and n_run >= args.limit:
            break
    summary = summarize(load_rows(args.arm), args.model, args.arm)
    suffix = "" if args.arm == "A" else f"-arm{args.arm}"
    path = OUT / f"when2call-{args.model}{suffix}-summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", path)
    print(json.dumps({k: summary[k] for k in summary if k != "items"}, indent=2))


if __name__ == "__main__":
    main()
