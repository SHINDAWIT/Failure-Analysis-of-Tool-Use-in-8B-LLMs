from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "spec"
PUBLIC = ROOT / "fixtures" / "public"
PRIVATE = ROOT / "fixtures" / "private"

THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
ACTIONS = ("tool_call", "request_for_info", "cannot_answer")
LOC_TOOLS = ("list_dir", "read_file", "grep", "run")

# Arm B only. Single observed slip: a stray double quote closing a bare number,
# e.g. {"start": 1, "end": 80"}. Arm A treats it as fatal.
STRAY_QUOTE_AFTER_NUM = re.compile(r'(:\s*-?\d+)"')
TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")


def repair_json_text(text: str) -> str:
    return TRAILING_COMMA_RE.sub(r"\1", STRAY_QUOTE_AFTER_NUM.sub(r"\1", text))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def f0() -> dict[str, Any]:
    return load_json(SPEC / "f0.json")


def selected() -> dict[str, Any]:
    return load_json(SPEC / "selected.json")


def loc_tools_spec() -> dict[str, Any]:
    return load_json(SPEC / "loc_tools.json")


def public_fixture(uuid: str) -> dict[str, Any]:
    return load_json(PUBLIC / f"{uuid}.json")


def private_answers() -> dict[str, Any]:
    return load_json(PRIVATE / "when2call_answers.json")


def strip_think(text: str) -> str:
    return THINK_RE.sub("", text)


def _scan_objects(cleaned: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    found: list[dict[str, Any]] = []
    for i, ch in enumerate(cleaned):
        if ch != "{":
            continue
        try:
            obj, _end = decoder.raw_decode(cleaned[i:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            found.append(obj)
    return found


def extract_json_object(text: str, *, lenient: bool = False) -> tuple[dict[str, Any] | None, str | None]:
    if text is None:
        return None, "empty_output"
    cleaned = strip_think(text).strip()
    fences = list(FENCE_RE.finditer(cleaned))
    if fences:
        cleaned = fences[-1].group(1).strip()
    if not cleaned:
        return None, "empty_after_think"
    candidates = _scan_objects(cleaned)
    if not candidates and lenient:
        # arm B is a strict superset of arm A: repair only after strict parsing found nothing
        candidates = _scan_objects(repair_json_text(cleaned))
    if not candidates:
        return None, "no_json_object"
    for obj in reversed(candidates):
        if any(key in obj for key in ("action", "tool", "final")):
            return obj, None
    return candidates[-1], None


def parse_when2call_action(text: str) -> tuple[dict[str, Any] | None, str | None]:
    obj, err = extract_json_object(text)
    if err:
        return None, err
    assert obj is not None
    if "action" in obj:
        action = obj["action"]
        if action not in ACTIONS:
            return None, f"unknown_action:{action}"
        if action == "tool_call":
            tool = obj.get("tool")
            args = obj.get("args", {})
            if not isinstance(tool, str) or not tool:
                return None, "tool_name_invalid"
            if not isinstance(args, dict):
                return None, "args_not_object"
            extra = set(obj) - {"action", "tool", "args"}
            if extra:
                return None, "tool_extra_keys"
            return {"action": "tool_call", "tool": tool, "args": args}, None
        if action == "request_for_info":
            question = obj.get("question")
            if not isinstance(question, str) or not question.strip():
                return None, "question_invalid"
            extra = set(obj) - {"action", "question"}
            if extra:
                return None, "rfi_extra_keys"
            return {"action": "request_for_info", "question": question.strip()}, None
        extra = set(obj) - {"action"}
        if extra:
            return None, "cannot_extra_keys"
        return {"action": "cannot_answer"}, None
    if "tool" in obj and "final" in obj:
        return None, "both_tool_and_final"
    if "tool" in obj:
        args = obj.get("args", {})
        if not isinstance(obj["tool"], str) or not obj["tool"]:
            return None, "tool_name_invalid"
        if not isinstance(args, dict):
            return None, "args_not_object"
        extra = set(obj) - {"tool", "args"}
        if extra:
            return None, "tool_extra_keys"
        return {"action": "tool_call", "tool": obj["tool"], "args": args}, None
    return None, "missing_action"


def parse_loc_action(text: str, *, lenient: bool = False) -> tuple[dict[str, Any] | None, str | None]:
    obj, err = extract_json_object(text, lenient=lenient)
    if err:
        return None, err
    assert obj is not None
    if "final" in obj and "tool" in obj:
        return None, "both_tool_and_final"
    if "final" in obj:
        if len(obj) != 1:
            return None, "final_extra_keys"
        value = obj["final"]
        if not isinstance(value, str) or "::" not in value:
            return None, "final_not_path_func"
        path, func = value.split("::", 1)
        if not path.strip() or not func.strip():
            return None, "final_not_path_func"
        return {"final": value.strip()}, None
    if "tool" in obj:
        args = obj.get("args", {})
        if not isinstance(obj["tool"], str) or obj["tool"] not in LOC_TOOLS:
            return None, "tool_name_invalid"
        if not isinstance(args, dict):
            return None, "args_not_object"
        extra = set(obj) - {"tool", "args"}
        if extra:
            return None, "tool_extra_keys"
        return {"tool": obj["tool"], "args": args}, None
    return None, "missing_tool_or_final"


def validate_loc_action(action: dict[str, Any]) -> str | None:
    spec = loc_tools_spec()["tools"]
    if "final" in action:
        return None
    name = action["tool"]
    schema = spec[name]
    args = action["args"]
    missing = [k for k in schema["required"] if k not in args]
    if missing:
        return f"missing_args:{','.join(missing)}"
    extra = [k for k in args if k not in schema["properties"]]
    if extra:
        return f"unexpected_args:{','.join(extra)}"
    if name == "run":
        target = args.get("target", "test")
        if target != "test":
            return "run_target_not_test"
    if name == "read_file":
        start = args.get("start", 1)
        end = args.get("end", 40)
        if isinstance(start, bool) or isinstance(end, bool):
            return "bad_type:line"
        if not isinstance(start, int) or not isinstance(end, int):
            return "bad_type:line"
        if start < 1 or end < start:
            return "bad_range"
    return None


def pass_at_k(n: int, c: int, k: int) -> float:
    if n < 1 or k < 1 or k > n:
        raise ValueError("need 1 <= k <= n")
    if c < 0 or c > n:
        raise ValueError("need 0 <= c <= n")
    if n - c < k:
        return 1.0
    prod = 1.0
    for i in range(k):
        prod *= (n - c - i) / (n - i)
    return 1.0 - prod
