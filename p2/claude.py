"""One `claude -p` call, the way the 13 lab makes it, for the reranker and the answers.

- It launches the claude command by its full path, on the model from p2.toml (default Sonnet),
  with --tools "" (no tools: the model sees only what the prompt gives it), --json-schema (the reply
  is forced into that shape), --output-format json (so the token counts come back), and, when a
  system prompt is given, --system-prompt (it replaces Claude Code's own instructions).
- It runs in an empty temporary folder with --setting-sources project,local, so no CLAUDE.md or
  user setting changes the call, and --no-session-persistence, so calls do not fill your history.
- It uses your Claude Code sign-in: ANTHROPIC_API_KEY and ANTHROPIC_AUTH_TOKEN are removed from the
  child's environment, so a leftover key is never billed by accident.
- The prompt goes in on standard input, which has no length limit (a command line on Windows stops
  near 32,000 characters).
- With a cache folder, a reply is saved under a hash of everything sent, and the same call later
  returns the saved reply at no cost; pass no cache folder (or --fresh) to ask again.
- The call's model and token counts are added to the open trace span (see p2/trace.py).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from p2 import trace

KEY_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
TIMEOUT_S = 600
_warned_keys = False


class ClaudeNotFound(RuntimeError):
    pass


@dataclass
class Reply:
    output: dict | None  # the structured reply, or None on an error
    seconds: float
    input_tokens: int
    output_tokens: int
    model: str
    error: str | None = None
    cost_usd: float | None = None
    cached: bool = False


def find_claude() -> str:
    """The full path of the claude command."""
    path = shutil.which("claude")
    if not path:
        raise ClaudeNotFound("Could not find the claude command; install Claude Code (see setup.md in the course repo) and open a new terminal.")
    return path


def child_env() -> dict[str, str]:
    """A copy of the environment without API keys, so the call uses your sign-in."""
    global _warned_keys
    removed = [k for k in KEY_VARS if os.environ.get(k)]
    if removed and not _warned_keys:
        print(f"Note: {', '.join(removed)} is set in your environment; claude -p calls ignore it and use your sign-in.", file=sys.stderr)
        _warned_keys = True
    return {k: v for k, v in os.environ.items() if k not in KEY_VARS}


def command(claude: str, schema: dict, model: str, system: str | None) -> list[str]:
    cmd = [
        claude, "-p",
        "--model", model,
        "--tools", "",
        "--output-format", "json",
        "--json-schema", json.dumps(schema),
        "--setting-sources", "project,local",
        "--no-session-persistence",
    ]  # fmt: skip
    if system is not None:
        cmd += ["--system-prompt", system]
    return cmd


def parse(stdout: str, stderr: str, seconds: float, model: str) -> Reply:
    """A Reply from claude's --output-format json output."""
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        detail = (stderr.strip() or stdout.strip() or "no output")[:300]
        return Reply(None, seconds, 0, 0, model, error=f"unparseable output: {detail}")
    if not isinstance(data, dict):
        return Reply(None, seconds, 0, 0, model, error="unexpected output shape")
    usage = data.get("usage") or {}
    tokens_in = sum(int(usage.get(k) or 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    tokens_out = int(usage.get("output_tokens") or 0)
    used = list((data.get("modelUsage") or {}).keys())
    resolved = max(used, key=lambda m: (data["modelUsage"][m] or {}).get("outputTokens", 0)) if used else model
    cost = data.get("total_cost_usd")
    output = data.get("structured_output")
    if data.get("is_error") or not isinstance(output, dict):
        reason = data.get("result") if isinstance(data.get("result"), str) and data.get("result") else data.get("subtype")
        return Reply(None, seconds, tokens_in, tokens_out, resolved, error=str(reason or "no structured_output in the reply")[:300], cost_usd=cost)
    return Reply(output, seconds, tokens_in, tokens_out, resolved, cost_usd=cost)


def cache_key(prompt: str, schema: dict, model: str, system: str | None) -> str:
    blob = json.dumps([model, system, schema, prompt], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]


def call(prompt: str, schema: dict, system: str | None = None, model: str = "sonnet", cache_dir: Path | None = None, timeout: int = TIMEOUT_S) -> Reply:
    """One claude -p call with no tools and a reply forced into `schema`."""
    cache_file = Path(cache_dir) / f"{cache_key(prompt, schema, model, system)}.json" if cache_dir else None
    if cache_file and cache_file.is_file():
        saved = json.loads(cache_file.read_text(encoding="utf-8"))
        reply = Reply(saved["output"], saved["seconds"], saved["input_tokens"], saved["output_tokens"], saved["model"], cost_usd=saved.get("cost_usd"), cached=True)
        trace.add_usage(reply.model, reply.input_tokens, reply.output_tokens, reply.cost_usd, cached=True)
        return reply
    cmd = command(find_claude(), schema, model, system)
    start = time.perf_counter()
    try:
        with tempfile.TemporaryDirectory() as empty:  # an empty folder, so no CLAUDE.md is picked up
            done = subprocess.run(
                cmd, cwd=empty, env=child_env(), input=prompt, capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=timeout,
            )  # fmt: skip
    except subprocess.TimeoutExpired:
        seconds = time.perf_counter() - start
        trace.add_usage(model, 0, 0)
        return Reply(None, seconds, 0, 0, model, error=f"no reply within {timeout} s")
    seconds = time.perf_counter() - start
    reply = parse(done.stdout, done.stderr, seconds, model)
    trace.add_usage(reply.model, reply.input_tokens, reply.output_tokens, reply.cost_usd)
    if cache_file and reply.error is None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        saved = {"output": reply.output, "seconds": round(seconds, 1), "input_tokens": reply.input_tokens, "output_tokens": reply.output_tokens, "model": reply.model, "cost_usd": reply.cost_usd}
        cache_file.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8", newline="\n")
    return reply


def cache_folder(cfg) -> Path | None:
    """The reply cache for these settings: .cache/claude/, or None when replies must be fresh."""
    return cfg.root / ".cache" / "claude" if cfg.cache_claude else None
