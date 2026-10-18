from __future__ import annotations

from typing import Any

from .schema import parse_when2call_action


def score_when2call(raw_output: str, gold: dict[str, Any], allowed_tool_names: list[str]) -> dict[str, Any]:
    action, reason = parse_when2call_action(raw_output)
    format_ok = action is not None
    predicted = action["action"] if action else None
    gold_label = gold["correct_answer"]
    semantic_ok = bool(format_ok and predicted == gold_label)
    tool_name = action.get("tool") if action else None
    tool_in_list = bool(tool_name and tool_name in allowed_tool_names)
    target = gold.get("target_tool")
    tool_name_match = bool(tool_name and target and tool_name == target)
    return {
        "format_ok": format_ok,
        "semantic_ok": semantic_ok,
        "predicted_action": predicted,
        "gold_action": gold_label,
        "parse_reason": reason,
        "tool_name": tool_name,
        "tool_in_list": tool_in_list,
        "tool_name_match": tool_name_match,
        "action": action,
    }
