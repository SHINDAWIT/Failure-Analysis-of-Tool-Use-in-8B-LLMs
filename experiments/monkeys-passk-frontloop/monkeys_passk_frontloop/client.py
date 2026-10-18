from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class ChatResult:
    content: str
    reasoning: str | None
    raw: dict[str, Any]
    usage: dict[str, Any]
    tool_calls: list[dict[str, Any]] | None = None


class LlamaServerClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8080", timeout_s: float = 195.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def health(self) -> dict[str, Any]:
        with urllib.request.urlopen(self.base_url + "/health", timeout=5) as resp:
            body = resp.read().decode("utf-8")
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = {"raw": body}
            if isinstance(parsed, dict):
                parsed["http_status"] = resp.status
                return parsed
            return {"raw": parsed, "http_status": resp.status}

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        top_p: float,
        max_tokens: int,
        seed: int | None = None,
        repeat_penalty: float | None = None,
        chat_template_kwargs: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResult:
        body: dict[str, Any] = {
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if chat_template_kwargs:
            body["chat_template_kwargs"] = chat_template_kwargs
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        if seed is not None:
            body["seed"] = seed
        if repeat_penalty is not None and repeat_penalty != 1.0:
            body["repeat_penalty"] = repeat_penalty
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/v1/chat/completions",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"llama-server request failed: {exc}") from exc
        choice = payload["choices"][0]["message"]
        content = choice.get("content") or ""
        reasoning = choice.get("reasoning_content")
        return ChatResult(
            content=content,
            reasoning=reasoning,
            raw=payload,
            usage=payload.get("usage") or {},
            tool_calls=choice.get("tool_calls"),
        )


def combine_output(result: ChatResult) -> str:
    content = result.content or ""
    if result.reasoning:
        return f"<think>{result.reasoning}</think>\n{content}"
    return content
