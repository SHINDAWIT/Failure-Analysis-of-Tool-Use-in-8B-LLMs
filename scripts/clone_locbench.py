"""Clone Loc-Bench security repos at frozen base commits. Failures stay as infra rows."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "experiments" / "monkeys-passk-frontloop"
sys.path.insert(0, str(PKG))

from monkeys_passk_frontloop.schema import selected  # noqa: E402

PUBLIC = PKG / "fixtures" / "loc_public"
REPOS = PKG / "repos"
STATUS = ROOT / "runs" / "benchmarks" / "monkeys-passk-frontloop" / "loc_clone_status.json"

# Do not restore these clones. Windows Defender flags Impacket example scripts
# (Trojan:Script/Wacatac.H!ml). Ledger rows for the IDs may remain; the trees must not.
DO_NOT_CLONE = {
    "fortra__impacket-1636": "av_heuristic: Trojan:Script/Wacatac.H!ml on Impacket examples/",
}


def run(cmd: list[str], cwd: Path | None = None, timeout_s: int = 600) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True, timeout=timeout_s)


def clone_one(instance_id: str, timeout_s: int) -> dict:
    dest = REPOS / instance_id
    if instance_id in DO_NOT_CLONE:
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        return {
            "instance_id": instance_id,
            "status": "skipped_av",
            "path": str(dest),
            "elapsed_s": 0,
            "reason": DO_NOT_CLONE[instance_id],
        }
    fixture = json.loads((PUBLIC / f"{instance_id}.json").read_text(encoding="utf-8"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    commit = fixture["base_commit"]
    url = "https://github.com/" + fixture["repo"] + ".git"
    t0 = time.time()
    if (dest / ".git").is_dir():
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=dest,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if head.startswith(commit) or commit.startswith(head):
            return {
                "instance_id": instance_id,
                "status": "ok",
                "path": str(dest),
                "elapsed_s": 0,
                "skipped": True,
            }
    if dest.exists() and not (dest / ".git").is_dir():
        shutil.rmtree(dest, ignore_errors=True)
    try:
        if not (dest / ".git").is_dir():
            run(["git", "clone", "--filter=blob:none", url, str(dest)], timeout_s=timeout_s)
        run(["git", "checkout", "--detach", commit], cwd=dest, timeout_s=120)
        return {
            "instance_id": instance_id,
            "status": "ok",
            "path": str(dest),
            "elapsed_s": round(time.time() - t0, 1),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "instance_id": instance_id,
            "status": "timeout",
            "error": str(exc),
            "elapsed_s": round(time.time() - t0, 1),
        }
    except subprocess.CalledProcessError as exc:
        return {
            "instance_id": instance_id,
            "status": "git_fail",
            "error": str(exc),
            "elapsed_s": round(time.time() - t0, 1),
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="", help="comma instance ids")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    ids = selected()["stage2_locbench_security"]["ids"]
    if args.only:
        ids = [x.strip() for x in args.only.split(",") if x.strip()]
    missing = [i for i in ids if not (PUBLIC / f"{i}.json").exists()]
    if missing:
        raise SystemExit("materialize loc fixtures first: " + ",".join(missing[:5]))
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    prev = {}
    if STATUS.exists():
        prev = {r["instance_id"]: r for r in json.loads(STATUS.read_text(encoding="utf-8")).get("rows", [])}
    rows = []
    for iid in ids:
        row = clone_one(iid, args.timeout)
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        STATUS.write_text(
            json.dumps({"rows": list(prev.values()) + rows, "when": time.strftime("%Y-%m-%dT%H:%M:%S")}, indent=2),
            encoding="utf-8",
        )
    ok = sum(1 for r in rows if r["status"] == "ok")
    print(f"clone done ok={ok}/{len(rows)}")


if __name__ == "__main__":
    main()
