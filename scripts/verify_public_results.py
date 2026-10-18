"""Publication-time arithmetic/integrity check; does not execute experiment code."""

from __future__ import annotations

import ast
import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def read_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def count(value: object, maximum: int, label: str) -> None:
    require(type(value) is int and 0 <= value <= maximum, f"Invalid count: {label}")


def percentage(numerator: int, denominator: int) -> str:
    return str(
        (Decimal(numerator) * 100 / denominator).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )
    )


def verify() -> None:
    results = read_json("results/paper_results.json")
    references = read_json("results/reference_aggregates.json")
    manifest = read_json("publication_manifest.json")
    expected_groups = {
        "locbench": {
            "granite_strict", "granite_relaxed", "granite_native_xml", "ministral_json"
        },
        "when2call": {
            "granite_thinking_on", "granite_thinking_off", "ministral"
        },
    }
    for group, expected in expected_groups.items():
        data = results[group]
        n = data["attempts_per_condition"]
        require(n == data["n_items"] * data["replicates_per_item"], f"{group}: grid")
        conditions = data["conditions"]
        require(len(conditions) == len(expected), f"{group}: condition count")
        require({row["key"] for row in conditions} == expected, f"{group}: keys")
        for row in conditions:
            ref = references[group][row["key"]]
            require(ref["n_items"] == data["n_items"], f"{row['key']}: items")
            require(ref["n_attempts"] == n, f"{row['key']}: denominator")
            if group == "locbench":
                for key in ["format_stop", "tool_cap", "final", "file_correct", "function_correct"]:
                    count(row[key], n, f"{row['key']}.{key}")
                    reference_value = ref["terminals"][key] if key in ref["terminals"] else ref[key]
                    require(row[key] == reference_value, f"{row['key']}.{key}: reference mismatch")
                require(
                    row["format_stop"] + row["tool_cap"] + row["final"] == n,
                    f"{row['key']}: terminal sum",
                )
                require(
                    row["function_correct"] <= row["file_correct"] <= row["final"],
                    f"{row['key']}: correctness versus submission",
                )
                print(
                    f"{row['label']}: "
                    f"format_stop={row['format_stop']}/{n} "
                    f"({percentage(row['format_stop'], n)}%), "
                    f"function={row['function_correct']}/{n} "
                    f"({percentage(row['function_correct'], n)}%)"
                )
            else:
                for key in ["format_correct", "action_correct"]:
                    count(row[key], n, f"{row['key']}.{key}")
                    require(row[key] == ref[key], f"{row['key']}.{key}: reference mismatch")
                require(
                    row["action_correct"] <= row["format_correct"],
                    f"{row['key']}: action correctness requires valid format",
                )
                print(
                    f"{row['label']}: format={percentage(row['format_correct'], n)}%, "
                    f"action={percentage(row['action_correct'], n)}%"
                )

    python_files = 0
    for entry in [manifest["paper"], *manifest["unchanged_files"]]:
        relative = entry["path"]
        target = (ROOT / relative).resolve()
        require(ROOT in target.parents, f"Invalid manifest path: {relative}")
        raw = target.read_bytes()
        require(
            hashlib.sha256(raw).hexdigest() == entry["sha256"],
            f"Hash mismatch: {relative}",
        )
        if target.suffix == ".py":
            ast.parse(raw.decode("utf-8-sig"), filename=relative)
            python_files += 1
    require(
        (ROOT / results["paper"]).read_bytes().startswith(b"%PDF-"),
        "Paper file is not a PDF",
    )
    print(
        f"PASS: 7 result conditions; {len(manifest['unchanged_files']) + 1} "
        f"paper/source/figure hashes; {python_files} archived Python syntax checks."
    )
    print("Scope: publication arithmetic and integrity; no experiment execution.")


def main() -> int:
    try:
        verify()
    except (OSError, ValueError, KeyError, TypeError, SyntaxError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
