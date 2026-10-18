"""Arm C: the Loc loop expressed in Granite's own tool-call notation.

The point of this arm is to move the change from the scorer to the generator.
Arm B loosened the JSON parser and the termination rate tripled, which invites the
objection that the result came from relaxing the scoring rule. Here the parser stays
strict and only the notation changes, so a collapse in format_stop cannot be blamed
on the grader.

Strictness is mirrored from parse_loc_action + validate_loc_action, decision by
decision:

  JSON contract                             this notation
  ----------------------------------------  ----------------------------------------
  last action-bearing object wins           last action-bearing construct wins
  tool not in LOC_TOOLS -> tool_name_invalid  same
  keys outside {tool, args} -> extra keys   text outside <parameter=...> -> extra
  arg not in schema -> unexpected_args      same on parameter names
  missing required -> missing_args           same
  duplicate JSON keys: last wins            duplicate parameter: last wins
  final must be a lone key, path::func      <final> must be path::func
  start/end must be int -> bad_type:line    see below
  start < 1 or end < start -> bad_range     same

One rule cannot be literally identical. JSON carries types, so `{"end": "80"}` is
rejected as a string. Tag-delimited text has no types at all, so requiring a
non-string would reject every possible input. The tightest symmetric rule is to
demand that a number-typed value match an integer literal exactly, which is what
NUMBER_LITERAL enforces: "80" passes, "80.5", "eighty", "8 0" and "" all fail with
the same bad_type:line that JSON would raise.
"""

from __future__ import annotations

import re
from typing import Any

from .schema import LOC_TOOLS, loc_tools_spec, strip_think

FENCE_RE = re.compile(r"```(?:[a-zA-Z0-9_+-]*)\n(.*?)```", re.S)
TOOL_CALL_RE = re.compile(r"<tool_call>\s*<function=([^>\s]*)>(.*?)</function>\s*</tool_call>", re.S)
PARAM_RE = re.compile(r"<parameter=([^>\s]*)>(.*?)</parameter>", re.S)
FINAL_RE = re.compile(r"<final>(.*?)</final>", re.S)
NUMBER_LITERAL = re.compile(r"-?\d+")

NATIVE_PROTOCOL = """You are a localization assistant. Think privately if needed, then emit exactly one tool call or one final answer, and nothing after it.

Explore the repository with tools, then name the function that should be changed.

To call a tool, reply in exactly this format with no suffix:

<tool_call>
<function=read_file>
<parameter=path>
src/auth.py
</parameter>
<parameter=start>
1
</parameter>
<parameter=end>
80
</parameter>
</function>
</tool_call>

To give the answer, reply with exactly:

<final>src/auth.py::check_token</final>

Allowed tools:
- list_dir(path) - list a directory. Start with path "."
- read_file(path, start, end) - read 1-indexed lines. Default 40 lines if omitted.
- grep(pattern, path) - literal substring search. path defaults to "."

Rules:
- One tool call or one final per message, never both.
- Do not invent file paths. Use tools.
- final must be exactly path::function, for example src/auth.py::check_token
- Class methods use Class.method after ::
- After at most 8 tool calls you must emit final.
"""


def native_system_prompt() -> str:
    return NATIVE_PROTOCOL


def native_user_prompt(instance_id: str, problem: str) -> str:
    return (
        f"Instance: {instance_id}\n"
        "Find the function that should be edited to address this issue.\n\n"
        f"{problem.strip()}\n\n"
        "Start by listing the repo root with\n"
        "<tool_call>\n<function=list_dir>\n<parameter=path>\n.\n</parameter>\n</function>\n</tool_call>"
    )


def _clean(text: str) -> str:
    cleaned = strip_think(text or "").strip()
    fences = list(FENCE_RE.finditer(cleaned))
    if fences:
        cleaned = fences[-1].group(1).strip()
    return cleaned


def parse_loc_native_action(text: str) -> tuple[dict[str, Any] | None, str | None]:
    cleaned = _clean(text)
    if not cleaned:
        return None, "empty_after_think"

    calls = list(TOOL_CALL_RE.finditer(cleaned))
    finals = list(FINAL_RE.finditer(cleaned))
    if not calls and not finals:
        if "<tool_call>" in cleaned or "<function=" in cleaned:
            return None, "tool_call_not_closed"
        if "<final>" in cleaned:
            return None, "final_not_closed"
        return None, "no_native_construct"

    # last construct wins, mirroring the JSON parser's reversed scan
    last_call = calls[-1] if calls else None
    last_final = finals[-1] if finals else None
    if last_call and last_final:
        take_call = last_call.start() > last_final.start()
    else:
        take_call = last_call is not None

    if not take_call:
        assert last_final is not None
        value = last_final.group(1).strip()
        if "::" not in value:
            return None, "final_not_path_func"
        path, func = value.split("::", 1)
        if not path.strip() or not func.strip():
            return None, "final_not_path_func"
        return {"final": value}, None

    assert last_call is not None
    name = last_call.group(1).strip()
    body = last_call.group(2)
    if name not in LOC_TOOLS:
        return None, "tool_name_invalid"

    params = list(PARAM_RE.finditer(body))
    if PARAM_RE.sub("", body).strip():
        return None, "tool_body_extra"

    args: dict[str, Any] = {}
    for m in params:
        key = m.group(1).strip()
        if not key:
            return None, "empty_param_name"
        args[key] = m.group(2).strip()  # duplicate name: last wins, as json.loads does

    return {"tool": name, "args": args}, None


def validate_loc_native_action(action: dict[str, Any]) -> str | None:
    if "final" in action:
        return None
    spec = loc_tools_spec()["tools"]
    name = action["tool"]
    schema = spec[name]
    args = action["args"]

    missing = [k for k in schema["required"] if k not in args]
    if missing:
        return f"missing_args:{','.join(missing)}"
    extra = [k for k in args if k not in schema["properties"]]
    if extra:
        return f"unexpected_args:{','.join(extra)}"

    for key, kind in schema["properties"].items():
        if kind != "number" or key not in args:
            continue
        raw = args[key]
        if not NUMBER_LITERAL.fullmatch(str(raw)):
            return "bad_type:line"
        args[key] = int(raw)

    if name == "read_file":
        start = args.get("start", 1)
        end = args.get("end", 40)
        if start < 1 or end < start:
            return "bad_range"
    return None


def loc_native_format_ok(raw: str) -> tuple[bool, dict[str, Any] | None, str | None]:
    action, err = parse_loc_native_action(raw)
    if err:
        return False, None, err
    reason = validate_loc_native_action(action)  # type: ignore[arg-type]
    if reason:
        return False, action, reason
    return True, action, None
