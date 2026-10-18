from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schema import loc_tools_spec, parse_loc_action, validate_loc_action

SKIP_DIRS = {".git", ".hg", "__pycache__", "node_modules", ".venv", "venv"}
MAX_GREP_HITS = 30
MAX_OBS = 2500


def _safe(root: Path, path: str) -> Path:
    target = (root / path).resolve()
    root_r = root.resolve()
    if root_r not in target.parents and target != root_r:
        raise ValueError("path_escape")
    return target


def _clip(obj: Any) -> dict[str, Any]:
    text = json.dumps(obj, ensure_ascii=False)
    if len(text) <= MAX_OBS:
        return obj if isinstance(obj, dict) else {"value": obj}
    if isinstance(obj, dict):
        clipped = dict(obj)
        clipped["truncated"] = True
        return clipped
    return {"truncated": True, "value": text[:MAX_OBS]}


class LocEnv:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = Path(repo_root)

    def execute(self, action: dict[str, Any]) -> dict[str, Any]:
        name = action["tool"]
        args = action.get("args") or {}
        if name == "list_dir":
            return self.list_dir(str(args.get("path") or "."))
        if name == "read_file":
            start = int(args.get("start", 1))
            end = int(args.get("end", 40))
            return self.read_file(str(args["path"]), start, end)
        if name == "grep":
            return self.grep(str(args["pattern"]), str(args.get("path") or "."))
        if name == "run":
            return {"ok": False, "reason": "test_runner_not_configured_for_p2"}
        raise ValueError(f"unknown_tool:{name}")

    def list_dir(self, path: str) -> dict[str, Any]:
        target = _safe(self.repo_root, path)
        if not target.exists():
            return {"ok": False, "reason": "not_found", "path": path}
        if not target.is_dir():
            return {"ok": False, "reason": "not_dir", "path": path}
        names = []
        for child in sorted(target.iterdir(), key=lambda p: p.name.lower()):
            if child.name in SKIP_DIRS:
                continue
            names.append(child.name + ("/" if child.is_dir() else ""))
        return {"ok": True, "path": path, "entries": names[:80], "n": len(names)}

    def read_file(self, path: str, start: int, end: int) -> dict[str, Any]:
        target = _safe(self.repo_root, path)
        if not target.is_file():
            return {"ok": False, "reason": "not_file", "path": path}
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return {"ok": False, "reason": str(exc), "path": path}
        lines = text.splitlines()
        start = max(1, start)
        end = min(len(lines), end)
        chunk = "\n".join(f"{i}|{lines[i-1]}" for i in range(start, end + 1))
        return {
            "ok": True,
            "path": path,
            "start": start,
            "end": end,
            "n_lines": len(lines),
            "text": chunk[:2000],
        }

    def grep(self, pattern: str, path: str) -> dict[str, Any]:
        if not pattern:
            return {"ok": False, "reason": "empty_pattern"}
        target = _safe(self.repo_root, path)
        hits: list[dict[str, Any]] = []
        files = [target] if target.is_file() else target.rglob("*")
        for file in files:
            if not file.is_file():
                continue
            if any(part in SKIP_DIRS for part in file.parts):
                continue
            if file.suffix.lower() not in {".py", ".md", ".txt", ".toml", ".cfg", ".ini", ".json", ".yml", ".yaml", ""}:
                if file.suffix.lower() not in {".c", ".h", ".js", ".ts"}:
                    continue
            try:
                lines = file.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            rel = file.relative_to(self.repo_root).as_posix()
            for i, line in enumerate(lines, 1):
                if pattern in line:
                    hits.append({"path": rel, "line": i, "text": line.strip()[:200]})
                    if len(hits) >= MAX_GREP_HITS:
                        return {"ok": True, "pattern": pattern, "hits": hits, "capped": True}
        return {"ok": True, "pattern": pattern, "hits": hits, "capped": False}


def normalize_gold(edit_functions: list[str]) -> list[str]:
    out = []
    for item in edit_functions:
        item = str(item).replace("\\", "/")
        if "::" in item:
            out.append(item)
            continue
        if ":" in item:
            path, func = item.split(":", 1)
            out.append(f"{path}::{func}")
        else:
            out.append(item)
    return out


def score_loc_final(final: str | None, gold_funcs: list[str]) -> dict[str, Any]:
    gold = normalize_gold(gold_funcs)
    gold_files = {g.split("::", 1)[0] for g in gold if "::" in g}
    if not final:
        return {"file_ok": False, "func_ok": False, "predicted": None, "gold": gold}
    pred = final.replace("\\", "/").strip()
    pred_file = pred.split("::", 1)[0]
    return {
        "file_ok": pred_file in gold_files,
        "func_ok": pred in gold,
        "predicted": pred,
        "gold": gold,
    }


def loc_format_ok(raw: str, *, lenient: bool = False) -> tuple[bool, dict[str, Any] | None, str | None]:
    action, err = parse_loc_action(raw, lenient=lenient)
    if err:
        return False, None, err
    reason = validate_loc_action(action)  # type: ignore[arg-type]
    if reason:
        return False, action, reason
    return True, action, None
