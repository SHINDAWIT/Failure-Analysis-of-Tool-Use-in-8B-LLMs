from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .client import LlamaServerClient, combine_output
from .loc_env import LocEnv, loc_format_ok, score_loc_final
from .loc_native import loc_native_format_ok, native_system_prompt, native_user_prompt
from .loc_prompts import loc_observation, loc_system_prompt, loc_user_prompt
from .schema import f0, load_json

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "fixtures" / "loc_public"
PRIVATE = ROOT / "fixtures" / "loc_private" / "answers.json"
REPOS = ROOT / "repos"


def loc_public(instance_id: str) -> dict[str, Any]:
    return load_json(PUBLIC / f"{instance_id}.json")


def loc_private() -> dict[str, Any]:
    return load_json(PRIVATE)


def run_loc_attempt(
    client: LlamaServerClient,
    instance_id: str,
    *,
    model_name: str,
    replicate_id: int,
    arm: str = "A",
    lenient: bool = False,
    notation: str = "json",
) -> dict[str, Any]:
    cfg = f0()
    profile = cfg["profiles"][model_name]
    fixture = loc_public(instance_id)
    gold = loc_private()[instance_id]
    repo_dir = REPOS / instance_id
    if not repo_dir.is_dir():
        return {
            "assignment_id": f"{instance_id}:{model_name}:{arm}:{replicate_id}",
            "instance_id": instance_id,
            "model": model_name,
            "arm": arm,
            "replicate_id": int(replicate_id),
            "format_ok": False,
            "file_ok": False,
            "func_ok": False,
            "live_terminal": "infra_missing_repo",
            "outputs": [],
            "model_calls": 0,
        }
    env = LocEnv(repo_dir)
    native = notation == "native"
    if native and lenient:
        raise ValueError("arm C keeps the parser strict; lenient repair is arm B only")
    messages = [
        {
            "role": "system",
            "content": native_system_prompt() if native else loc_system_prompt(),
        },
        {
            "role": "user",
            "content": (native_user_prompt if native else loc_user_prompt)(
                instance_id, fixture["problem_statement"]
            ),
        },
    ]
    outputs: list[str] = []
    steps: list[dict[str, Any]] = []
    tool_ok = 0
    live_terminal = "ok"
    predicted = None
    t0 = time.time()
    max_calls = 10
    max_tools = 8
    prompt_chars = sum(len(m.get("content") or "") for m in messages)
    try:
        for _ in range(max_calls):
            result = client.chat(
                messages,
                temperature=float(profile["temperature"]),
                top_p=float(profile["top_p"]),
                max_tokens=int(cfg["runtime"]["n_predict"]),
                seed=int(replicate_id),
                repeat_penalty=float(profile.get("repeat_penalty") or 1.0),
            )
            raw = combine_output(result)
            outputs.append(raw)
            messages.append({"role": "assistant", "content": result.content or raw})
            if native:
                fmt_ok, action, reason = loc_native_format_ok(raw)
            else:
                fmt_ok, action, reason = loc_format_ok(raw, lenient=lenient)
            step: dict[str, Any] = {
                "parse_ok": fmt_ok,
                "reason": reason,
                "prompt_chars": prompt_chars,
                "usage": result.usage,
            }
            if not fmt_ok or action is None:
                live_terminal = "format_stop"
                steps.append(step)
                break
            if "final" in action:
                predicted = action["final"]
                live_terminal = "final"
                step["final"] = predicted
                steps.append(step)
                break
            if tool_ok >= max_tools:
                live_terminal = "tool_cap"
                steps.append(step)
                break
            try:
                obs = env.execute(action)
            except ValueError as exc:
                live_terminal = "format_stop"
                outputs.append(f"<tool_error>{exc}</tool_error>")
                step["tool_error"] = str(exc)
                steps.append(step)
                break
            tool_ok += 1
            obs_msg = loc_observation(obs)
            messages.append({"role": "user", "content": obs_msg})
            prompt_chars += len(result.content or raw) + len(obs_msg)
            step["tool"] = action.get("tool")
            step["args"] = action.get("args")
            step["obs_ok"] = bool(obs.get("ok")) if isinstance(obs, dict) else None
            step["obs_chars"] = len(obs_msg)
            steps.append(step)
        else:
            live_terminal = "call_cap"
    except Exception as exc:  # noqa: BLE001
        live_terminal = "infra_error"
        outputs.append(f"<infra>{exc}</infra>")
        steps.append({"infra": str(exc)})
    scored = score_loc_final(predicted, gold.get("edit_functions") or [])
    format_ok = live_terminal == "final" and predicted is not None
    return {
        "assignment_id": f"{instance_id}:{model_name}:{arm}:{replicate_id}",
        "instance_id": instance_id,
        "model": model_name,
        "arm": arm,
        "lenient_parse": bool(lenient),
        "notation": notation,
        "replicate_id": int(replicate_id),
        "format_ok": format_ok if live_terminal != "infra_error" else False,
        "file_ok": bool(scored["file_ok"]) if format_ok else False,
        "func_ok": bool(scored["func_ok"]) if format_ok else False,
        "predicted": predicted,
        "gold": scored.get("gold"),
        "live_terminal": live_terminal,
        "tool_calls": tool_ok,
        "model_calls": len(outputs),
        "elapsed_ms": int((time.time() - t0) * 1000),
        "prompt_chars_end": prompt_chars,
        "steps": steps,
        "outputs": outputs,
    }
