"""Loc-Bench attempts for the model on :8080. Resume from loc_ledger.jsonl."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "experiments" / "monkeys-passk-frontloop"
sys.path.insert(0, str(PKG))

from monkeys_passk_frontloop.client import LlamaServerClient  # noqa: E402
from monkeys_passk_frontloop.loc_harness import run_loc_attempt  # noqa: E402
from monkeys_passk_frontloop.schema import f0, pass_at_k, selected  # noqa: E402

OUT = ROOT / "runs" / "benchmarks" / "monkeys-passk-frontloop"
JSONL = OUT / "loc_ledger.jsonl"
SMOKE_ID = "latchset__jwcrypto-195"


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


def ledger_path(arm: str) -> Path:
    """Arm A keeps the frozen ledger; later arms get their own file."""
    return JSONL if arm == "A" else OUT / f"loc_ledger_arm{arm}.jsonl"


def load_done(path: Path) -> set[str]:
    done: set[str] = set()
    if not path.exists():
        return done
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            done.add(json.loads(line)["assignment_id"])
    return done


def load_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_row(row: dict, path: Path) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    slim = {k: v for k, v in row.items() if k != "outputs"}
    slim["n_outputs"] = len(row.get("outputs") or [])
    slim["last_output"] = (row.get("outputs") or [""])[-1][:1500]
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(slim, ensure_ascii=False) + "\n")


def summarize(rows: list[dict], model: str, arm: str = "A") -> dict:
    subset = [r for r in rows if r.get("model") == model and r.get("arm") == arm]
    by: dict[str, list[dict]] = {}
    for row in subset:
        by.setdefault(row["instance_id"], []).append(row)
    ks = f0()["sampling"]["k"]
    items = []
    for iid, group in sorted(by.items()):
        n = len(group)
        c_fmt = sum(1 for r in group if r.get("format_ok"))
        c_file = sum(1 for r in group if r.get("file_ok"))
        c_func = sum(1 for r in group if r.get("func_ok"))
        items.append(
            {
                "instance_id": iid,
                "n": n,
                "c_format": c_fmt,
                "c_file": c_file,
                "c_func": c_func,
                "passk_format": {str(k): pass_at_k(n, c_fmt, k) for k in ks} if n >= max(ks) else {},
                "passk_file": {str(k): pass_at_k(n, c_file, k) for k in ks} if n >= max(ks) else {},
                "passk_func": {str(k): pass_at_k(n, c_func, k) for k in ks} if n >= max(ks) else {},
                "terminals": {t: sum(1 for r in group if r.get("live_terminal") == t) for t in sorted({r.get("live_terminal") for r in group})},
            }
        )
    n_items = len(items) or 1
    return {
        "model": model,
        "arm": arm,
        "n_rows": len(subset),
        "n_items": len(items),
        "format_rate": (sum(1 for r in subset if r.get("format_ok")) / len(subset)) if subset else 0.0,
        "file_rate": (sum(1 for r in subset if r.get("file_ok")) / len(subset)) if subset else 0.0,
        "func_rate": (sum(1 for r in subset if r.get("func_ok")) / len(subset)) if subset else 0.0,
        "macro_passk_file": {str(k): sum(it["passk_file"].get(str(k), 0.0) for it in items) / n_items for k in ks},
        "macro_passk_func": {str(k): sum(it["passk_func"].get(str(k), 0.0) for it in items) / n_items for k in ks},
        "items": items,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="granite")
    parser.add_argument("--instance", default="")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--n", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--arm", default="A")
    parser.add_argument("--lenient", action="store_true", help="arm B: repair the stray-quote JSON slip")
    parser.add_argument("--exclude", default="", help="comma-separated instance_ids to skip")
    parser.add_argument(
        "--notation",
        default="json",
        choices=["json", "native"],
        help="arm C: express the same loop in the model's own tool-call notation, parser stays strict",
    )
    args = parser.parse_args()
    if args.notation == "native" and args.lenient:
        raise SystemExit("arm C changes the generator, not the grader; do not combine --notation native with --lenient")
    if args.notation == "native" and args.arm in ("A", "B"):
        raise SystemExit("--notation native needs its own arm label, e.g. --arm C")
    cfg = f0()
    if args.all:
        ids = list(selected()["stage2_locbench_security"]["ids"])
    elif args.instance:
        ids = [args.instance]
    else:
        ids = [SMOKE_ID]
    skip = {s.strip() for s in args.exclude.split(",") if s.strip()}
    if skip:
        ids = [i for i in ids if i not in skip]
        print(f"excluded={sorted(skip)} remaining={len(ids)}", flush=True)
    reps = list(cfg["independent"]["replicate_id"])[: args.n]
    client = LlamaServerClient(timeout_s=float(cfg["runtime"]["wall_time_s"]) + 15)
    print("health", json.dumps(wait_health(client)), flush=True)
    ledger = ledger_path(args.arm)
    done = load_done(ledger)
    planned = [f"{iid}:{args.model}:{args.arm}:{rid}" for iid in ids for rid in reps]
    todo = [aid for aid in planned if aid not in done]
    print(f"arm={args.arm} lenient={args.lenient} planned={len(planned)} done={len(done)} todo={len(todo)}", flush=True)
    n_run = 0
    for aid in todo:
        iid, model, arm, rid_s = aid.rsplit(":", 3)
        row = run_loc_attempt(
            client,
            iid,
            model_name=model,
            replicate_id=int(rid_s),
            arm=arm,
            lenient=args.lenient,
            notation=args.notation,
        )
        append_row(row, ledger)
        n_run += 1
        print(
            f"{row['assignment_id']} fmt={row['format_ok']} file={row['file_ok']} "
            f"func={row['func_ok']} pred={row.get('predicted')} term={row['live_terminal']} "
            f"tools={row.get('tool_calls')} ms={row.get('elapsed_ms')}",
            flush=True,
        )
        if args.limit and n_run >= args.limit:
            break
    summary = summarize(load_rows(ledger), args.model, args.arm)
    suffix = "" if args.arm == "A" else f"-arm{args.arm}"
    path = OUT / f"loc-{args.model}{suffix}-summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", path)
    print(json.dumps({k: summary[k] for k in summary if k != "items"}, indent=2))


if __name__ == "__main__":
    main()
