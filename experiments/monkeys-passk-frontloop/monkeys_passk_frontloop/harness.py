from __future__ import annotations

import time
from typing import Any

from .client import LlamaServerClient, combine_output
from .evaluator import score_when2call
from .prompts import system_prompt, user_prompt
from .schema import f0, private_answers, public_fixture


def run_when2call_attempt(
    client: LlamaServerClient,
    uuid: str,
    *,
    model_name: str,
    replicate_id: int,
    arm: str = "A",
    n_predict: int | None = None,
    thinking: bool | None = None,
) -> dict[str, Any]:
    cfg = f0()
    profile = cfg["profiles"][model_name]
    fixture = public_fixture(uuid)
    gold = private_answers()[uuid]
    allowed = [t["name"] for t in fixture["tools"] if isinstance(t, dict) and t.get("name")]
    messages = [
        {"role": "system", "content": system_prompt(fixture["tools"])},
        {"role": "user", "content": user_prompt(fixture["question"])},
    ]
    t0 = time.time()
    live_terminal = "ok"
    raw = ""
    usage: dict[str, Any] = {}
    reasoning_chars = 0
    # the Granite 4.2 template ignores {"thinking": false} without warning, so the
    # only key that actually disables the thinking channel is enable_thinking
    ctk = {"enable_thinking": False} if thinking is False else None
    try:
        result = client.chat(
            messages,
            temperature=float(profile["temperature"]),
            top_p=float(profile["top_p"]),
            max_tokens=int(n_predict or cfg["runtime"]["n_predict"]),
            seed=int(replicate_id),
            repeat_penalty=float(profile.get("repeat_penalty") or 1.0),
            chat_template_kwargs=ctk,
        )
        raw = combine_output(result)
        usage = result.usage
        reasoning_chars = len(result.reasoning or "")
    except Exception as exc:  # noqa: BLE001
        live_terminal = "infra_error"
        raw = f"<infra>{exc}</infra>"
    scored = score_when2call(raw, gold, allowed)
    if live_terminal == "ok" and not scored["format_ok"]:
        live_terminal = "format_stop"
    elif live_terminal == "ok":
        live_terminal = scored["predicted_action"]
    elapsed_ms = int((time.time() - t0) * 1000)
    return {
        "assignment_id": f"{uuid}:{model_name}:{arm}:{replicate_id}",
        "uuid": uuid,
        "model": model_name,
        "arm": arm,
        "replicate_id": int(replicate_id),
        "source": fixture.get("source"),
        "n_tools": fixture.get("n_tools"),
        "gold_action": gold["correct_answer"],
        "format_ok": scored["format_ok"] if live_terminal != "infra_error" else False,
        "semantic_ok": scored["semantic_ok"] if live_terminal != "infra_error" else False,
        "predicted_action": scored["predicted_action"],
        "parse_reason": scored["parse_reason"],
        "tool_name": scored["tool_name"],
        "tool_in_list": scored["tool_in_list"],
        "tool_name_match": scored["tool_name_match"],
        "live_terminal": live_terminal,
        "n_predict": int(n_predict or cfg["runtime"]["n_predict"]),
        "thinking_requested": thinking,
        "reasoning_chars": reasoning_chars,
        "elapsed_ms": elapsed_ms,
        "usage": usage,
        "outputs": [raw],
        "model_calls": 0 if live_terminal == "infra_error" else 1,
    }
