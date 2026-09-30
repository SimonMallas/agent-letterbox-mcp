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
    for line in header.replace("\r\n", "\n").split("\n"):
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


def test_relay_reply_refused_byte_identical(client, mailbox):
    ident = live_id("relay")
    write_letter(mailbox, ident, "phone question", type_name="info", from_agent="telegram-bridge")
    _init(client)
    before = _snapshot(mailbox)
    result = client.request(
        "tools/call",
        {"name": "letterbox_reply", "arguments": {"id": ident, "action": "result", "body": "done"}},
    )
    assert result["result"]["isError"] is True
    assert _text(result) == f"relay letter: reply with alb --reply-to {ident} (the bus cannot transmit)"
    assert _snapshot(mailbox) == before


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
    assert (inbox / f"{ident}.md").is_file()
    assert not list((mailbox / AGENT / "processed").glob(f"{ident}*"))
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


def test_repeat_ack_different_body_is_collision(client, mailbox):
    ident = live_id("ackdiff")
    write_letter(mailbox, ident, "task", type_name="request", deadline="2026-09-21T09:00:00Z")
    path = mailbox / AGENT / "inbox" / f"{ident}.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("requires_ack: false", "requires_ack: true"),
        encoding="utf-8",
    )
    _init(client)
    first = client.request(
        "tools/call",
        {"name": "letterbox_reply", "arguments": {"id": ident, "action": "ack", "body": "on it"}},
    )
    assert first["result"]["isError"] is False
    second = client.request(
        "tools/call",
        {"name": "letterbox_reply", "arguments": {"id": ident, "action": "ack", "body": "different body"}},
    )
    assert second["result"]["isError"] is True
    assert "collision" in _text(second).lower()
    assert "ring" not in (second["result"].get("structuredContent") or {})


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


def test_sidecar_without_durable_ack_is_first_ack(client, mailbox):
    ident = live_id("sidecaronly")
    write_letter(mailbox, ident, "task", type_name="request", deadline="2026-09-21T09:00:00Z")
    path = mailbox / AGENT / "inbox" / f"{ident}.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("requires_ack: false", "requires_ack: true"),
        encoding="utf-8",
    )
    (mailbox / AGENT / "inbox" / f"{ident}.md.ack").write_text(
        "acked_at: 2026-09-20T150000Z\n", encoding="utf-8"
    )
    _init(client)
    result = client.request(
        "tools/call",
        {"name": "letterbox_reply", "arguments": {"id": ident, "action": "ack", "body": "on it"}},
    )
    assert result["result"]["isError"] is False
    assert "already existed" not in _text(result)
    ack_path = mailbox / "beta" / "inbox" / f"{ident}--{AGENT}--ack.md"
    assert ack_path.is_file()


def _copied_thread(mailbox: Path, ident: str, action: str = "result") -> str:
    path = mailbox / "beta" / "inbox" / f"{ident}--{AGENT}--{action}.md"
    return _frontmatter(path)["thread"]


def test_reply_copies_bounded_hazardous_threads(client, mailbox):
    import json

    cases = [
        ("thesc", "ok\x1bthread"),
        ("thls", "ok\u2028x"),
        ("thrlo", "ok\u202eth"),
        ("th65", "t" * 65),
        ("th256", "t" * 256),
    ]
    _init(client)
    for suffix, thread in cases:
        ident = live_id(suffix)
        write_letter(mailbox, ident, "q", type_name="info", thread=thread)
        result = client.request(
            "tools/call",
            {"name": "letterbox_reply", "arguments": {"id": ident, "action": "result", "body": "done"}},
        )
        assert result["result"]["isError"] is False, suffix
        copied = _copied_thread(mailbox, ident)
        assert copied == thread
        escaped = json.dumps(copied, ensure_ascii=True)
        assert "\x1b" not in escaped
        assert "\u2028" not in escaped
        assert "\u202e" not in escaped


def test_reply_overlong_thread_refused(client, mailbox):
    ident = live_id("thlong")
    write_letter(mailbox, ident, "q", type_name="info", thread="t" * 257)
    _init(client)
    before = _snapshot(mailbox)
    result = client.request(
        "tools/call",
        {"name": "letterbox_reply", "arguments": {"id": ident, "action": "result", "body": "done"}},
    )
    assert result["result"]["isError"] is True
    assert _snapshot(mailbox) == before


def test_reply_ignores_target_deadline_and_priority(client, mailbox):
    ident = live_id("ignorefields")
    write_letter(
        mailbox,
        ident,
        "q",
        type_name="info",
        deadline="d" * 257,
        priority="ab\u202ecd",
    )
    _init(client)
    result = client.request(
        "tools/call",
        {"name": "letterbox_reply", "arguments": {"id": ident, "action": "result", "body": "done"}},
    )
    assert result["result"]["isError"] is False


def test_reply_hazardous_from_refused(client, mailbox):
    ident = live_id("hazfrom")
    write_letter(mailbox, ident, "q", type_name="info", from_agent="be\x1bta")
    _init(client)
    before = _snapshot(mailbox)
    result = client.request(
        "tools/call",
        {"name": "letterbox_reply", "arguments": {"id": ident, "action": "result", "body": "done"}},
    )
    assert result["result"]["isError"] is True
    assert _snapshot(mailbox) == before


def test_reply_path_from_refused(client, mailbox):
    _init(client)
    for origin in ("../beta", "a/b", ".", ".."):
        ident = live_id("path" + origin.replace("/", "x").replace(".", "d"))
        write_letter(mailbox, ident, "q", type_name="info", from_agent=origin)
        before = _snapshot(mailbox)
        result = client.request(
            "tools/call",
            {"name": "letterbox_reply", "arguments": {"id": ident, "action": "result", "body": "done"}},
        )
        assert result["result"]["isError"] is True, origin
        assert _snapshot(mailbox) == before


def test_reply_from_65_refused_33_succeeds(client, mailbox):
    ident65 = live_id("from65r")
    write_letter(mailbox, ident65, "q", type_name="info", from_agent="b" * 65)
    _init(client)
    before = _snapshot(mailbox)
    result = client.request(
        "tools/call",
        {"name": "letterbox_reply", "arguments": {"id": ident65, "action": "result", "body": "done"}},
    )
    assert result["result"]["isError"] is True
    assert _snapshot(mailbox) == before

    long_ok = "b" * 33
    (mailbox / long_ok / "inbox").mkdir(parents=True, exist_ok=True)
    (mailbox / long_ok / "processed").mkdir(parents=True, exist_ok=True)
    ident33 = live_id("from33r")
    write_letter(mailbox, ident33, "q", type_name="info", from_agent=long_ok)
    result = client.request(
        "tools/call",
        {"name": "letterbox_reply", "arguments": {"id": ident33, "action": "result", "body": "done"}},
    )
    assert result["result"]["isError"] is False


def test_reply_ignores_hazardous_to(client, mailbox):
    ident = live_id("badto")
    write_letter(mailbox, ident, "q", type_name="info", to_agent="al\x1bpha")
    _init(client)
    result = client.request(
        "tools/call",
        {"name": "letterbox_reply", "arguments": {"id": ident, "action": "result", "body": "done"}},
    )
    assert result["result"]["isError"] is False


def test_reply_static_symlink_participant_refused(client, mailbox, tmp_path):
    ident = live_id("symdir")
    outside = tmp_path / "outside-bus"
    (outside / "inbox").mkdir(parents=True)
    (outside / "processed").mkdir(parents=True)
    sneak = mailbox / "sneaky"
    sneak.symlink_to(outside)
    write_letter(mailbox, ident, "q", type_name="info", from_agent="sneaky")
    _init(client)
    before = _snapshot(mailbox)
    result = client.request(
        "tools/call",
        {"name": "letterbox_reply", "arguments": {"id": ident, "action": "result", "body": "done"}},
    )
    assert result["result"]["isError"] is True
    assert _snapshot(mailbox) == before


def test_reply_static_symlink_inbox_refused(client, mailbox, tmp_path):
    ident = live_id("syminbox")
    outside = tmp_path / "outside-inbox"
    outside.mkdir()
    host = mailbox / "sneaky2"
    host.mkdir()
    (host / "inbox").symlink_to(outside)
    (host / "processed").mkdir()
    write_letter(mailbox, ident, "q", type_name="info", from_agent="sneaky2")
    _init(client)
    before = _snapshot(mailbox)
    result = client.request(
        "tools/call",
        {"name": "letterbox_reply", "arguments": {"id": ident, "action": "result", "body": "done"}},
    )
    assert result["result"]["isError"] is True
    assert _snapshot(mailbox) == before


def test_derived_reply_id_overflow_refused_all_actions(client, mailbox):
    ident = ("2026-09-20T150000-beta-info-" + ("x" * 128))[:128]
    assert len(ident) == 128
    write_letter(mailbox, ident, "q", type_name="info")
    _init(client)
    before = _snapshot(mailbox)
    for action in ("ack", "nack", "result"):
        result = client.request(
            "tools/call",
            {"name": "letterbox_reply", "arguments": {"id": ident, "action": action, "body": "done"}},
        )
        assert result["result"]["isError"] is True, action
        assert _snapshot(mailbox) == before


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
