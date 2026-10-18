"""Check that arm C's parser is not quietly more forgiving than arm A's.

Each case is written twice, once in the JSON contract and once in the native
notation, and both parsers must agree on accept/reject. If the native parser
accepted things the JSON parser rejects, any drop in format_stop would just be a
looser grader wearing a different hat.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "monkeys-passk-frontloop"))

from monkeys_passk_frontloop.loc_env import loc_format_ok  # noqa: E402
from monkeys_passk_frontloop.loc_native import loc_native_format_ok  # noqa: E402

# (label, json form, native form, must_be_accepted)
CASES = [
    (
        "well formed read_file",
        '{"tool": "read_file", "args": {"path": "a.py", "start": 1, "end": 80}}',
        "<tool_call><function=read_file><parameter=path>a.py</parameter>"
        "<parameter=start>1</parameter><parameter=end>80</parameter></function></tool_call>",
        True,
    ),
    (
        "well formed final",
        '{"final": "src/auth.py::check_token"}',
        "<final>src/auth.py::check_token</final>",
        True,
    ),
    (
        "list_dir root",
        '{"tool": "list_dir", "args": {"path": "."}}',
        "<tool_call><function=list_dir><parameter=path>.</parameter></function></tool_call>",
        True,
    ),
    (
        "unknown tool name",
        '{"tool": "open_file", "args": {"path": "a.py"}}',
        "<tool_call><function=open_file><parameter=path>a.py</parameter></function></tool_call>",
        False,
    ),
    (
        "unexpected argument",
        '{"tool": "list_dir", "args": {"path": ".", "depth": 2}}',
        "<tool_call><function=list_dir><parameter=path>.</parameter>"
        "<parameter=depth>2</parameter></function></tool_call>",
        False,
    ),
    (
        "missing required argument",
        '{"tool": "grep", "args": {"path": "."}}',
        "<tool_call><function=grep><parameter=path>.</parameter></function></tool_call>",
        False,
    ),
    (
        "final without :: separator",
        '{"final": "src/auth.py"}',
        "<final>src/auth.py</final>",
        False,
    ),
    (
        "final with empty function half",
        '{"final": "src/auth.py::"}',
        "<final>src/auth.py::</final>",
        False,
    ),
    (
        "non integer line number",
        '{"tool": "read_file", "args": {"path": "a.py", "start": 1, "end": 80.5}}',
        "<tool_call><function=read_file><parameter=path>a.py</parameter>"
        "<parameter=start>1</parameter><parameter=end>80.5</parameter></function></tool_call>",
        False,
    ),
    (
        "word instead of a line number",
        '{"tool": "read_file", "args": {"path": "a.py", "end": "eighty"}}',
        "<tool_call><function=read_file><parameter=path>a.py</parameter>"
        "<parameter=end>eighty</parameter></function></tool_call>",
        False,
    ),
    (
        "inverted line range",
        '{"tool": "read_file", "args": {"path": "a.py", "start": 90, "end": 10}}',
        "<tool_call><function=read_file><parameter=path>a.py</parameter>"
        "<parameter=start>90</parameter><parameter=end>10</parameter></function></tool_call>",
        False,
    ),
    (
        "prose with no construct at all",
        "I should look at the auth module first.",
        "I should look at the auth module first.",
        False,
    ),
    (
        "opened but never closed",
        '{"tool": "read_file", "args": {"path": "a.py"',
        "<tool_call><function=read_file><parameter=path>a.py",
        False,
    ),
    (
        "empty output",
        "",
        "",
        False,
    ),
    (
        "stray text inside the call",
        '{"tool": "read_file", "note": "checking", "args": {"path": "a.py"}}',
        "<tool_call><function=read_file>checking<parameter=path>a.py</parameter>"
        "</function></tool_call>",
        False,
    ),
    (
        "two calls, last one wins and is valid",
        '{"tool": "list_dir", "args": {"path": "bad"}}\n{"tool": "list_dir", "args": {"path": "."}}',
        "<tool_call><function=list_dir><parameter=path>bad</parameter></function></tool_call>\n"
        "<tool_call><function=list_dir><parameter=path>.</parameter></function></tool_call>",
        True,
    ),
    (
        "thinking block then a valid call",
        '<think>let me look</think>{"tool": "list_dir", "args": {"path": "."}}',
        "<think>let me look</think><tool_call><function=list_dir>"
        "<parameter=path>.</parameter></function></tool_call>",
        True,
    ),
]


def main() -> None:
    bad = 0
    print(f"{'case':38s} {'JSON':>8s} {'native':>8s} {'want':>6s}")
    for label, js, nat, want in CASES:
        j_ok, _, j_err = loc_format_ok(js, lenient=False)
        n_ok, _, n_err = loc_native_format_ok(nat)
        mark = "ok"
        if j_ok != want or n_ok != want:
            mark = "MISMATCH"
            bad += 1
        print(f"{label:38s} {str(j_ok):>8s} {str(n_ok):>8s} {str(want):>6s}  {mark}"
              + ("" if mark == "ok" else f"   json_err={j_err} native_err={n_err}"))
    print()
    if bad:
        raise SystemExit(f"{bad} case(s) disagree; the two parsers are not symmetric")
    print(f"all {len(CASES)} cases agree: the native parser is no more forgiving than the JSON one")


if __name__ == "__main__":
    main()
