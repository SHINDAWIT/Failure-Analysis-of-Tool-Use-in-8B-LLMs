"""Materialize Loc-Bench Security 29. Gold stays private."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "experiments" / "monkeys-passk-frontloop"
sys.path.insert(0, str(PKG))

from monkeys_passk_frontloop.schema import selected  # noqa: E402

PUBLIC = PKG / "fixtures" / "loc_public"
PRIVATE = PKG / "fixtures" / "loc_private"


def main() -> None:
    path = hf_hub_download(
        repo_id="czlll/Loc-Bench_V1",
        filename="data/test-00000-of-00001.parquet",
        repo_type="dataset",
        cache_dir=r"D:\hf-cache",
    )
    rows = pq.read_table(path).to_pylist()
    by_id = {r["instance_id"]: r for r in rows}
    ids = selected()["stage2_locbench_security"]["ids"]
    PUBLIC.mkdir(parents=True, exist_ok=True)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    answers = {}
    missing = []
    for iid in ids:
        row = by_id.get(iid)
        if row is None:
            missing.append(iid)
            continue
        edits = row.get("edit_functions") or []
        if hasattr(edits, "tolist"):
            edits = list(edits)
        public = {
            "instance_id": iid,
            "repo": row["repo"],
            "base_commit": row["base_commit"],
            "problem_statement": row.get("problem_statement") or "",
            "n_edit_functions": len(edits),
            "has_test_patch": bool(row.get("test_patch")),
        }
        (PUBLIC / f"{iid}.json").write_text(
            json.dumps(public, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        answers[iid] = {
            "edit_functions": [str(x) for x in edits],
        }
    if missing:
        raise SystemExit(f"missing loc ids: {missing}")
    (PRIVATE / "answers.json").write_text(
        json.dumps(answers, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(ids)} loc fixtures")


if __name__ == "__main__":
    main()
