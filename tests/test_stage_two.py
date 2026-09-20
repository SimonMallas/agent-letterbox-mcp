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
        assert "id" in structured and "uri" in structured
        ring = structured["ring"]
        assert set(ring) == {"outcome", "reason", "target"}
        assert ring["outcome"] in ("submitted", "pasted_not_submitted", "no_live_surface")
        assert ring["outcome"] != "unconfirmed"
        assert '"ring"' in text
        assert ring["outcome"] in text
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
    letter = first["result"]["structuredContent"]["letter"]
    assert letter["state"] == "processed"
    assert "already_filed" not in first["result"]["structuredContent"]
    assert ident in _text(first)
    assert "processed" in _text(first)
    second = client.request("tools/call", {"name": "letterbox_file", "arguments": {"id": ident}})
    assert second["result"]["isError"] is False
    assert "already_filed" not in second["result"]["structuredContent"]
    assert second["result"]["structuredContent"]["letter"]["state"] == "processed"
    assert "already filed" in _text(second).lower()


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
    ring = structured["ring"]
    assert ring["outcome"] in ("submitted", "pasted_not_submitted", "no_live_surface")
    assert ring["outcome"] in text
    assert ident in text


def test_reply_duplicate_from_refused_byte_identical(client, mailbox):
    ident = live_id("duprep")
    inbox = mailbox / AGENT / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / f"{ident}.md").write_text(
        f"---\nid: {ident}\nfrom: beta\nfrom: pi\nto: {AGENT}\ntype: request\nrequires_ack: true\ndeadline: 2026-09-21T09:00:00Z\n---\nbody\n",
        encoding="utf-8",
    )
    _init(client)
    before = _snapshot(mailbox)
    result = client.request(
        "tools/call",
        {"name": "letterbox_reply", "arguments": {"id": ident, "action": "result", "body": "done"}},
    )
    assert result["result"]["isError"] is True
    assert "duplicate_key" in _text(result)
    assert _snapshot(mailbox) == before
    assert not list((mailbox / "beta" / "inbox").glob("*.md"))


def test_file_non_letter_not_found_before_cli(client, mailbox):
    ident = live_id("nofrom")
    inbox = mailbox / AGENT / "inbox"
    (inbox / f"{ident}.md").write_text(
        f"---\nid: {ident}\nto: {AGENT}\ntype: info\nrequires_ack: false\n---\nbody\n",
        encoding="utf-8",
    )
    _init(client)
    before = _snapshot(mailbox)
    result = client.request("tools/call", {"name": "letterbox_file", "arguments": {"id": ident}})
    assert result["result"]["isError"] is True
    assert "not found" in _text(result).lower()
    assert _snapshot(mailbox) == before


def test_repeat_ack_succeeds_and_says_existed(client, mailbox):
    ident = live_id("acktwice")
    write_letter(mailbox, ident, "task", type_name="request", deadline="2026-09-21T09:00:00Z")
    path = mailbox / AGENT / "inbox" / f"{ident}.md"
    path.write_text(path.read_text(encoding="utf-8").replace("requires_ack: false", "requires_ack: true"), encoding="utf-8")
    _init(client)
    first = client.request(
        "tools/call",
        {"name": "letterbox_reply", "arguments": {"id": ident, "action": "ack", "body": "on it"}},
    )
    assert first["result"]["isError"] is False
    assert "ring" not in first["result"]["structuredContent"]
    second = client.request(
        "tools/call",
        {"name": "letterbox_reply", "arguments": {"id": ident, "action": "ack", "body": "on it"}},
    )
    assert second["result"]["isError"] is False
    assert "ack already existed" in _text(second)
    assert "ring" not in second["result"]["structuredContent"]


def test_repeat_result_already_closed_no_ring(client, mailbox):
    ident = live_id("restwice")
    write_letter(mailbox, ident, "q", type_name="info")
    _init(client)
    first = client.request(
        "tools/call",
        {"name": "letterbox_reply", "arguments": {"id": ident, "action": "result", "body": "done"}},
    )
    assert first["result"]["isError"] is False
    assert "ring" in first["result"]["structuredContent"]
    second = client.request(
        "tools/call",
        {"name": "letterbox_reply", "arguments": {"id": ident, "action": "result", "body": "done again"}},
    )
    assert second["result"]["isError"] is False
    assert "already closed" in _text(second)
    assert "ring" not in second["result"]["structuredContent"]


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
