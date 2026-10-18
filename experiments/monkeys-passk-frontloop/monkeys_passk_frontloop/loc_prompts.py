from __future__ import annotations

LOC_PROTOCOL = """You are a localization assistant. Think privately if needed, then emit exactly one JSON object and nothing else after the JSON.

Explore the repository with tools, then name the function that should be changed.

Use one of:
{"tool": "<name>", "args": {<key>: <value>, ...}}
{"final": "<path>::<func>"}

Allowed tools:
- list_dir(path) — list a directory. Start with path "."
- read_file(path, start, end) — read 1-indexed lines. Default 40 lines if omitted.
- grep(pattern, path) — literal substring search. path defaults to "."
- run(target) — only target \\"test\\" is allowed; may be unavailable.

Rules:
- One JSON object per message.
- Do not invent file paths. Use tools.
- final must be exactly path::function, for example src/auth.py::check_token
- Class methods use Class.method after ::
- After at most 8 tool calls you must emit final.
"""


def loc_system_prompt() -> str:
    return LOC_PROTOCOL


def loc_user_prompt(instance_id: str, problem: str) -> str:
    return (
        f"Instance: {instance_id}\n"
        "Find the function that should be edited to address this issue.\n\n"
        f"{problem.strip()}\n\n"
        'Start by listing the repo root with {"tool":"list_dir","args":{"path":"."}}'
    )


def loc_observation(obs: dict) -> str:
    import json

    return "Tool result:\n" + json.dumps(obs, ensure_ascii=False)
