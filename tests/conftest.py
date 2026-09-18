from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.harness import AGENT, RpcClient, write_letter


@pytest.fixture
def mailbox(tmp_path: Path) -> Path:
    (tmp_path / AGENT / "inbox").mkdir(parents=True)
    (tmp_path / AGENT / "processed").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def client(mailbox: Path):
    rpc = RpcClient(mailbox)
    try:
        yield rpc
    finally:
        rpc.close()


def live_id(suffix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    ident = f"{stamp}-beta-info-{suffix}"
    return ident[:128]


def canary_letter(mailbox: Path, ident: str, body_chars: int = 50_000) -> None:
    from tests.harness import CANARY

    pad = max(0, body_chars - len(CANARY))
    write_letter(mailbox, ident, CANARY + ("x" * pad))
