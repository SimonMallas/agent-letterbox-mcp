"""Stage two: send, reply, file. Assert from written letters, not only the response."""

from pathlib import Path

from tests.conftest import live_id
from tests.harness import AGENT, write_letter

PEER = "beta"


def _init(client):
    client.initialize()


def _text(result: dict) -> str:
    return "".join(block.get("text", "") for block in result["result"].get("content", []) if "text" in block)


def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    header = text.split("---", 2)[1]
    fields: dict[str, str] = {}
    for line in header.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    return fields


def _peer_letters(mailbox: Path) -> list[Path]:
    return [p for p in (mailbox / PEER / "inbox").glob("*.md") if p.is_file()]


def _snapshot(mailbox: Path) -> dict:
    return {p.relative_to(mailbox): p.read_bytes() for p in mailbox.rglob("*") if p.is_file()}


def test_send_defaults_from_written_letter(client, mailbox):
    _init(client)
    expected = {
        "request": True,
        "delegate": True,
        "status": False,
        "blocker": False,
        "info": False,
    }
    for type_name, ack in expected.items():
        before = len(_peer_letters(mailbox))
        args = {
            "to": PEER,
            "type": type_name,
            "subject": f"s-{type_name}",
            "body": f"body-{type_name}",
        }
        if type_name == "request":
            args["deadline"] = "2026-09-21T09:00:00Z"
        result = client.request("tools/call", {"name": "letterbox_send", "arguments": args})
        assert result["result"]["isError"] is False
        text = _text(result)
        structured = result["result"]["structuredContent"]
        for key in ("id", "uri", "outcome", "reason", "target"):
            assert key in structured
            assert structured[key] in text
        assert structured["outcome"] in ("submitted", "pasted_not_submitted", "no_live_surface")
        assert structured["outcome"] != "unconfirmed"
        letters = _peer_letters(mailbox)
        assert len(letters) == before + 1
        fields = _frontmatter(max(letters, key=lambda p: p.stat().st_mtime))
        assert fields["type"] == type_name
        assert fields["requires_ack"] == ("true" if ack else "false")
        assert fields["from"] == AGENT
        assert f"-{type_name}-s-{type_name}-" in fields["id"] or f"-{type_name}-s-{type_name.replace('-', '-')}-" in fields["id"]
        assert f"-s-{type_name}-" in fields["id"]


def test_unsendable_types_create_no_letter(client, mailbox):
    _init(client)
    before = _snapshot(mailbox)
    for type_name in ("ack", "nack", "result"):
        result = client.request(
            "tools/call",
            {
                "name": "letterbox_send",
                "arguments": {"to": PEER, "type": type_name, "subject": "nope", "body": "x"},
            },
        )
        assert result["result"]["isError"] is True
        assert _snapshot(mailbox) == before


def test_subject_rewrites_and_echo_options_refused(client, mailbox):
    _init(client)
    before = _snapshot(mailbox)
    for subject in ("Review.V2", "a_b", "x:y", "-n", "-ne", "-en", "-abc"):
        result = client.request(
            "tools/call",
            {
                "name": "letterbox_send",
                "arguments": {"to": PEER, "type": "info", "subject": subject, "body": "x"},
            },
        )
        assert result["result"]["isError"] is True, subject
        assert _snapshot(mailbox) == before


def test_legal_subjects_appear_unchanged_in_id(client, mailbox):
    _init(client)
    for subject in ("a-b-c", "a"):
        result = client.request(
            "tools/call",
            {
                "name": "letterbox_send",
                "arguments": {"to": PEER, "type": "info", "subject": subject, "body": "x"},
            },
        )
        assert result["result"]["isError"] is False
        ident = result["result"]["structuredContent"]["id"]
        assert f"-{subject}-" in ident


def test_delegate_explicit_false_ack_refused(client, mailbox):
    _init(client)
    before = _snapshot(mailbox)
    result = client.request(
        "tools/call",
        {
            "name": "letterbox_send",
            "arguments": {
                "to": PEER,
                "type": "delegate",
                "subject": "task",
                "body": "x",
                "requires_ack": False,
            },
        },
    )
    assert result["result"]["isError"] is True
    assert _snapshot(mailbox) == before


def test_deadline_refusals_create_no_letter(client, mailbox):
    _init(client)
    before = _snapshot(mailbox)
    bad = [
        "2026-01-01T00:00:00Z\nfrom: pi",
        "2026-99-99T99:99:99Z",
        "２０２６-09-21T09:00:00Z",
    ]
    for deadline in bad:
        result = client.request(
            "tools/call",
            {
                "name": "letterbox_send",
                "arguments": {
                    "to": PEER,
                    "type": "info",
                    "subject": "dl",
                    "body": "x",
                    "deadline": deadline,
                },
            },
        )
        assert result["result"]["isError"] is True
        assert _snapshot(mailbox) == before


def test_file_non_task_and_repeat(client, mailbox):
    ident = live_id("tofile")
    write_letter(mailbox, ident, "note", type_name="info", acked=False)
    _init(client)
    first = client.request("tools/call", {"name": "letterbox_file", "arguments": {"id": ident}})
    assert first["result"]["isError"] is False
    assert first["result"]["structuredContent"]["state"] == "processed"
    assert first["result"]["structuredContent"]["already_filed"] is False
    assert ident in _text(first)
    assert "processed" in _text(first)
    second = client.request("tools/call", {"name": "letterbox_file", "arguments": {"id": ident}})
    assert second["result"]["isError"] is False
    assert second["result"]["structuredContent"]["already_filed"] is True
    assert "already" in _text(second).lower()


def test_subject_overflow_refused_before_cli(client, mailbox):
    _init(client)
    before = _snapshot(mailbox)
    subject = "s" * 120
    result = client.request(
        "tools/call",
        {
            "name": "letterbox_send",
            "arguments": {"to": PEER, "type": "info", "subject": subject, "body": "x"},
        },
    )
    assert result["result"]["isError"] is True
    assert _snapshot(mailbox) == before


def test_reply_result_carries_ring(client, mailbox):
    ident = live_id("repring")
    write_letter(mailbox, ident, "please", type_name="info")
    _init(client)
    result = client.request(
        "tools/call",
        {"name": "letterbox_reply", "arguments": {"id": ident, "action": "result", "body": "done"}},
    )
    assert result["result"]["isError"] is False
    text = _text(result)
    structured = result["result"]["structuredContent"]
    assert structured["action"] == "result"
    assert structured["id"] == ident
    assert "outcome" in structured
    assert structured["outcome"] in ("submitted", "pasted_not_submitted", "no_live_surface")
    assert structured["outcome"] in text
    assert ident in text


def test_file_open_task_refused(client, mailbox):
    ident = live_id("task")
    write_letter(mailbox, ident, "work", type_name="request", acked=False, deadline="2026-09-21T09:00:00Z")
    # requires_ack true
    path = mailbox / AGENT / "inbox" / f"{ident}.md"
    text = path.read_text(encoding="utf-8").replace("requires_ack: false", "requires_ack: true")
    path.write_text(text, encoding="utf-8")
    _init(client)
    before = _snapshot(mailbox)
    result = client.request("tools/call", {"name": "letterbox_file", "arguments": {"id": ident}})
    assert result["result"]["isError"] is True
    assert _snapshot(mailbox) == before
