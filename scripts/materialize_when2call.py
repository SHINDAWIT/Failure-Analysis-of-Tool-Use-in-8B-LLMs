"""Materialize frozen When2Call 40 into public/private fixtures. No labels in public files."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "experiments" / "monkeys-passk-frontloop"
sys.path.insert(0, str(PKG))

from monkeys_passk_frontloop.schema import selected  # noqa: E402

JSONL = Path(
    r"D:\hf-cache\datasets--nvidia--When2Call\snapshots"
    r"\0582f7749df63a96fdc3070932e83e72396ace53\test\when2call_test_llm_judge.jsonl"
)
PUBLIC = PKG / "fixtures" / "public"
PRIVATE = PKG / "fixtures" / "private"


def parse_tool_list(raw: list[str] | None) -> list[dict]:
    tools: list[dict] = []
    for item in raw or []:
        if isinstance(item, dict):
            tools.append(item)
            continue
        tools.append(json.loads(item))
    return tools


def main() -> None:
    ids = selected()["stage1_when2call"]["ids"]
    wanted = set(ids)
    found: dict[str, dict] = {}
    with JSONL.open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            uid = row["uuid"]
            if uid in wanted:
                found[uid] = row
    missing = [uid for uid in ids if uid not in found]
    if missing:
        raise SystemExit(f"missing When2Call ids: {missing}")

    PUBLIC.mkdir(parents=True, exist_ok=True)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    answers = {}
    for uid in ids:
        row = found[uid]
        tools = parse_tool_list(row.get("tools"))
        public = {
            "uuid": uid,
            "source": row.get("source"),
            "source_id": row.get("source_id"),
            "question": row["question"],
            "tools": tools,
            "n_tools": len(tools),
        }
        (PUBLIC / f"{uid}.json").write_text(
            json.dumps(public, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        answers[uid] = {
            "correct_answer": row["correct_answer"],
            "target_tool": row.get("target_tool"),
            "held_out_param": row.get("held_out_param"),
        }
    (PRIVATE / "when2call_answers.json").write_text(
        json.dumps(answers, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    hist: dict[str, int] = {}
    for item in answers.values():
        hist[item["correct_answer"]] = hist.get(item["correct_answer"], 0) + 1
    print(f"wrote {len(ids)} public fixtures to {PUBLIC}")
    print("label histogram", json.dumps(hist, sort_keys=True))


if __name__ == "__main__":
    main()
