from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
CANARY = "LETTERBOX_BODY_CANARY_8F29C1"
AGENT = "alpha"


class RpcClient:
    def __init__(self, mailbox: Path):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "letterbox_mcp", "--mailbox", str(mailbox), "--agent", AGENT],
            cwd=str(ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )
        self._next_id = 1
        self.stdout_log: list[str] = []

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=2)

    def request(self, method: str, params: dict | None = None) -> dict:
        msg_id = self._next_id
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params is not None:
            payload["params"] = params
        assert self.proc.stdin is not None
        assert self.proc.stdout is not None
        self.proc.stdin.write(json.dumps(payload) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            stderr = self.proc.stderr.read() if self.proc.stderr else ""
            raise RuntimeError(f"server closed stdout; stderr={stderr!r}")
        self.stdout_log.append(line)
        return json.loads(line)

    def notify(self, method: str, params: dict | None = None) -> None:
        payload: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(payload) + "\n")
        self.proc.stdin.flush()

    def transcript(self) -> str:
        return "".join(self.stdout_log)

    def initialize(self) -> dict:
        result = self.request(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "letterbox-mcp-tests", "version": "0"},
            },
        )
        self.notify("notifications/initialized")
        return result


def write_letter(
    mailbox: Path,
    ident: str,
    body: str,
    *,
    from_agent: str = "beta",
    to_agent: str = AGENT,
    type_name: str | None = "info",
    folder: str = "inbox",
    acked: bool = False,
    extra_bytes: int | None = None,
    priority: str = "next",
    deadline: str = "",
    thread: str = "",
    re_field: str = "",
) -> Path:
    dest = mailbox / AGENT / folder
    dest.mkdir(parents=True, exist_ok=True)
    type_line = "" if type_name is None else f"type: {type_name}\n"
    header = (
        f"---\n"
        f"id: {ident}\n"
        f"from: {from_agent}\n"
        f"to: {to_agent}\n"
        f"{type_line}"
        f"re: {re_field}\n"
        f"thread: {thread}\n"
        f"priority: {priority}\n"
        f"requires_ack: {'true' if acked else 'false'}\n"
        f"deadline: {deadline}\n"
        f"---\n"
    )
    text = header + body
    path = dest / f"{ident}.md"
    if extra_bytes is not None:
        encoded = text.encode("utf-8")
        if extra_bytes < len(encoded):
            raise ValueError("extra_bytes smaller than header+body")
        path.write_bytes(encoded + (b"x" * (extra_bytes - len(encoded))))
    else:
        path.write_text(text, encoding="utf-8")
    if acked:
        (dest / f"{ident}.md.ack").write_text("acked_at: 2026-09-18T080000Z\n", encoding="utf-8")
    return path


def sized_letter(mailbox: Path, ident: str, size: int) -> Path:
    return write_letter(mailbox, ident, "", extra_bytes=size)
