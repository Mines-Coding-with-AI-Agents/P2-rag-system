"""The claude -p helper: the command it builds, how it reads replies, the cache, the trace, and a fake claude end to end."""

import json
import os
import stat
import sys

import pytest

from p2 import claude, trace

SCHEMA = {"type": "object", "properties": {"order": {"type": "array"}}, "required": ["order"]}
REPLY = {
    "type": "result", "subtype": "success", "is_error": False, "result": "",
    "structured_output": {"order": [2, 1]},
    "usage": {"input_tokens": 10, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 5, "output_tokens": 7},
    "modelUsage": {"claude-sonnet-4-5": {"outputTokens": 7}}, "total_cost_usd": 0.01,
}  # fmt: skip


def test_command_flags():
    cmd = claude.command("/bin/claude", SCHEMA, "sonnet", "be brief")
    assert cmd[:2] == ["/bin/claude", "-p"]
    assert cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--model") + 1] == "sonnet"
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == SCHEMA
    assert cmd[cmd.index("--output-format") + 1] == "json"
    assert cmd[cmd.index("--setting-sources") + 1] == "project,local"
    assert cmd[-2:] == ["--system-prompt", "be brief"]
    assert "--system-prompt" not in claude.command("/bin/claude", SCHEMA, "sonnet", None)


def test_parse_success_error_and_garbage():
    ok = claude.parse(json.dumps(REPLY), "", 1.5, "sonnet")
    assert ok.output == {"order": [2, 1]} and ok.error is None
    assert (ok.input_tokens, ok.output_tokens, ok.model) == (115, 7, "claude-sonnet-4-5")
    failed = claude.parse(json.dumps({**REPLY, "is_error": True, "result": "Not logged in"}), "", 1.0, "sonnet")
    assert failed.output is None and failed.error == "Not logged in"
    garbage = claude.parse("oops", "boom", 1.0, "sonnet")
    assert garbage.error.startswith("unparseable output: boom")


def test_child_env_drops_keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok")
    env = claude.child_env()
    assert "ANTHROPIC_API_KEY" not in env and "ANTHROPIC_AUTH_TOKEN" not in env


@pytest.mark.skipif(os.name == "nt", reason="the fake claude is a POSIX script")
def test_fake_claude_end_to_end_with_cache_and_trace(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    fake = bin_dir / "claude"
    fake.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "prompt = sys.stdin.read()\n"
        f"open({str(log)!r}, 'a').write(json.dumps({{'argv': sys.argv[1:], 'prompt': prompt, 'cwd': os.getcwd(), 'key': os.environ.get('ANTHROPIC_API_KEY')}}) + '\\n')\n"
        f"sys.stdout.write({json.dumps(REPLY)!r})\n",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-leak")
    cache = tmp_path / "cache"
    with trace.Tracer(tmp_path / "t.jsonl") as tracer:
        with tracer.span("retrieval rerank", "retrieval", "rerank", "q1"):
            first = claude.call("Rank these.", SCHEMA, model="sonnet", cache_dir=cache)
            second = claude.call("Rank these.", SCHEMA, model="sonnet", cache_dir=cache)
    calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert len(calls) == 1  # the second call came from the cache
    assert calls[0]["prompt"] == "Rank these." and calls[0]["key"] is None
    assert calls[0]["cwd"] != os.getcwd()
    assert first.output == second.output == {"order": [2, 1]} and second.cached
    span = trace.read(tmp_path / "t.jsonl")[0]
    assert span["p2.claude_calls"] == 2 and span["p2.cached_calls"] == 1
    assert span["gen_ai.usage.input_tokens"] == 230 and span["gen_ai.response.model"] == "claude-sonnet-4-5"
