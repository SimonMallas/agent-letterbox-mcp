"""Invoke the Letterbox CLI. Mailbox root is BUS_DIR; never leak paths."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

RING_LINE = re.compile(
    r"^doorbell-outcome v=1 outcome=(\S+) reason=(\S+) target=(\S+)\s*$"
)
OUTCOMES = frozenset({"submitted", "pasted_not_submitted", "no_live_surface"})
SENT_LINE = re.compile(r"^sent: .*/([^/]+)\.md\s*$")
ALREADY_FILED = re.compile(r"^already filed:")
FILED_LINE = re.compile(r"^filed:")


@dataclass(frozen=True)
class CliResult:
    ok: bool
    stdout: str
    stderr: str
    ring: dict[str, str] | None
    letter_id: str | None
    already_filed: bool
    already_closed: bool


def run_cli(
    mailbox_root: str,
    agent: str,
    args: list[str],
    *,
    stdin: str = "",
    timeout: float = 30.0,
) -> CliResult:
    configured_cli = os.environ.get("LETTERBOX_CLI")
    if not configured_cli:
        return CliResult(
            ok=False,
            stdout="",
            stderr="LETTERBOX_CLI must be explicitly configured",
            ring=None,
            letter_id=None,
            already_filed=False,
            already_closed=False,
        )
    cli = Path(configured_cli)
    env = os.environ.copy()
    env["BUS_DIR"] = str(Path(mailbox_root).resolve())
    env["BUS_AGENT"] = agent
    proc = subprocess.run(
        [str(cli), *args],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        check=False,
    )
    stdout = proc.stdout or ""
    stderr = _sanitize(proc.stderr or "", mailbox_root)
    ring = parse_ring(stdout)
    letter_id = _parse_sent_id(stdout)
    already = bool(ALREADY_FILED.search(stdout))
    closed = any(line.startswith("already closed:") for line in stdout.splitlines())
    ok = proc.returncode == 0
    return CliResult(
        ok=ok,
        stdout=stdout,
        stderr=stderr,
        ring=ring,
        letter_id=letter_id,
        already_filed=already,
        already_closed=closed,
    )


def parse_ring(stdout: str) -> dict[str, str] | None:
    for line in stdout.splitlines():
        match = RING_LINE.fullmatch(line)
        if match:
            outcome, reason, target = match.group(1), match.group(2), match.group(3)
            if outcome not in OUTCOMES:
                return None
            return {"outcome": outcome, "reason": reason, "target": target}
    return None


def _parse_sent_id(stdout: str) -> str | None:
    for line in stdout.splitlines():
        match = SENT_LINE.fullmatch(line)
        if match:
            return match.group(1)
        if line.startswith("sent: "):
            name = Path(line[6:].strip()).name
            if name.endswith(".md"):
                return name[:-3]
    return None


def _sanitize(text: str, mailbox_root: str) -> str:
    root = str(Path(mailbox_root).resolve())
    home = str(Path.home())
    cleaned = text.replace(root, "").replace(home, "")
    return cleaned.strip()[:500]
