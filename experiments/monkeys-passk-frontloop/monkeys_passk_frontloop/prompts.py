from __future__ import annotations

import json
from typing import Any


PROTOCOL = """You are a tool-using assistant. Think privately if needed, then emit exactly one JSON object and nothing else after the JSON.

Decide whether to call a listed tool, ask for missing information, or refuse because you cannot fulfill the request with the listed tools.

Use exactly one of:
{"action": "tool_call", "tool": "<name>", "args": {<key>: <value>, ...}}
{"action": "request_for_info", "question": "<one clarifying question>"}
{"action": "cannot_answer"}

Rules:
- One JSON object per message.
- Only call a tool from the listed tools. Do not invent a tool name.
- If a required argument is missing from the user message, use request_for_info. Do not invent values.
- If none of the listed tools can fulfill the request, use cannot_answer. Do not call a related but wrong tool, and do not answer from world knowledge.
- Do not give a direct factual answer. The three actions above are the only valid outputs.
"""


def _compact_tool(tool: dict[str, Any]) -> str:
    params = tool.get("parameters") or {}
    required = params.get("required") or []
    props = params.get("properties") or {}
    prop_bits = []
    for name, spec in props.items():
        if not isinstance(spec, dict):
            prop_bits.append(name)
            continue
        typ = spec.get("type", "any")
        bit = f"{name}:{typ}"
        if name in required:
            bit += "*"
        prop_bits.append(bit)
    desc = str(tool.get("description") or "").replace("\n", " ").strip()
    if len(desc) > 220:
        desc = desc[:217] + "..."
    req = ",".join(str(x) for x in required) if required else "(none)"
    return f"- {tool.get('name')}: {desc}\n  required=[{req}] args={{{', '.join(prop_bits)}}}"


def tool_block(tools: list[dict[str, Any]]) -> str:
    if not tools:
        return "Listed tools: (none)"
    lines = ["Listed tools:"]
    for tool in tools:
        lines.append(_compact_tool(tool))
    return "\n".join(lines)


def system_prompt(tools: list[dict[str, Any]]) -> str:
    examples = (
        'Example tool call:\n{"action": "tool_call", "tool": "example.get", "args": {"id": "1"}}\n\n'
        'Example request for info:\n{"action": "request_for_info", "question": "Which city should I use?"}\n\n'
        'Example cannot answer:\n{"action": "cannot_answer"}'
    )
    return f"{PROTOCOL}\n{tool_block(tools)}\n\n{examples}"


def user_prompt(question: str) -> str:
    return question
