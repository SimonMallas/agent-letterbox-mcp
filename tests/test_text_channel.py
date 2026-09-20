"""Text-channel sufficiency: assert on the text block, ignore structuredContent."""

import json

import pytest

from letterbox_mcp.render import json_string
from tests.conftest import live_id
from tests.harness import AGENT, write_letter


def _init(client):
    client.initialize()


def _text(result: dict) -> str:
    return "".join(
        block.get("text", "") for block in result["result"].get("content", []) if "text" in block
    )


def test_check_text_carries_triage_fields(client, mailbox):
    ident = live_id("triage")
    write_letter(
        mailbox,
        ident,
        "body",
        type_name="request",
        priority="now",
        deadline="2026-09-20T17:04:57Z",
        acked=False,
    )
    _init(client)
    result = client.request("tools/call", {"name": "letterbox_check", "arguments": {}})
    text = _text(result)
    assert "type" in text.splitlines()[0]
    row = next(line for line in text.splitlines() if line.startswith(ident))
    assert " request " in f" {row} "
    assert " now " in f" {row} "
    assert " false " in f" {row} "
    assert json_string("2026-09-20T17:04:57Z") in row
    assert " open " in f" {row} "
    assert row.split()[-1].endswith("m") or row.split()[-1].endswith("h") or row.split()[-1].endswith("d")


def test_footer_sixty_and_three(client, mailbox):
    for i in range(60):
        write_letter(mailbox, live_id(f"s{i:02d}{i:02d}"), "x")
    _init(client)
    sixty = client.request("tools/call", {"name": "letterbox_check", "arguments": {}})
    assert "shown=50 remaining=10 truncated=true" in _text(sixty)


def test_footer_three_complete(client, mailbox):
    for i in range(3):
        write_letter(mailbox, live_id(f"t{i}"), "x")
    _init(client)
    three = client.request("tools/call", {"name": "letterbox_check", "arguments": {}})
    assert "shown=3 remaining=0 truncated=false" in _text(three)


def test_deadline_cell_is_ensure_ascii_true(client, mailbox):
    ident = live_id("escdead")
    write_letter(mailbox, ident, "x", deadline="ab\u202ew")
    _init(client)
    result = client.request("tools/call", {"name": "letterbox_check", "arguments": {}})
    text = _text(result)
    expected = json.dumps("ab\u202ew", ensure_ascii=True)
    assert expected in text
    assert "\u202e" not in text


def test_read_json_is_ensure_ascii_true(client, mailbox):
    ident = live_id("readjson")
    write_letter(mailbox, ident, "hello", deadline="2026-09-21T09:00:00Z", thread="th1", re_field="re1")
    _init(client)
    result = client.request(
        "tools/call",
        {"name": "letterbox_read", "arguments": {"id": ident, "include_body": False}},
    )
    text = _text(result)
    parsed = json.loads(text)
    assert parsed["deadline"] == "2026-09-21T09:00:00Z"
    assert parsed["thread"] == "th1"
    assert parsed["re"] == "re1"
    assert "body" not in parsed
    assert json.dumps(parsed, separators=(",", ":"), ensure_ascii=True) == text


@pytest.mark.parametrize(
    "suffix,value",
    (
        ("p65", "p" * 65),
        ("pc0", "ab\x01cd"),
        ("pls", "ab\u2028cd"),
        ("prlo", "ab\u202ecd"),
    ),
)
def test_priority_hazards_fail_both_tools(client, mailbox, suffix, value):
    ident = live_id(suffix)
    write_letter(mailbox, ident, "x", priority=value)
    _init(client)
    check = client.request("tools/call", {"name": "letterbox_check", "arguments": {}})
    assert check["result"]["isError"] is True
    assert ident in _text(check)
    read = client.request("tools/call", {"name": "letterbox_read", "arguments": {"id": ident}})
    assert read["result"]["isError"] is True
    assert ident in _text(read)


def test_thread_over_256_fails_read_only(client, mailbox):
    ident = live_id("th256")
    write_letter(mailbox, ident, "x", thread="t" * 257)
    _init(client)
    check = client.request("tools/call", {"name": "letterbox_check", "arguments": {}})
    assert check["result"]["isError"] is False
    assert ident in _text(check)
    read = client.request("tools/call", {"name": "letterbox_read", "arguments": {"id": ident}})
    assert read["result"]["isError"] is True
    assert ident in _text(read)


def test_deadline_over_256_fails_check_and_read(client, mailbox):
    ident = live_id("d256")
    write_letter(mailbox, ident, "x", deadline="d" * 257)
    _init(client)
    check = client.request("tools/call", {"name": "letterbox_check", "arguments": {}})
    assert check["result"]["isError"] is True
    assert ident in _text(check)
    read = client.request("tools/call", {"name": "letterbox_read", "arguments": {"id": ident}})
    assert read["result"]["isError"] is True
    assert ident in _text(read)


def test_duplicate_from_fails_loudly(client, mailbox):
    ident = live_id("dupfrom")
    inbox = mailbox / AGENT / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / f"{ident}.md").write_text(
        f"---\nid: {ident}\nfrom: beta\nfrom: pi\nto: {AGENT}\ntype: info\npriority: next\nrequires_ack: false\ndeadline:\n---\nbody\n",
        encoding="utf-8",
    )
    _init(client)
    check = client.request("tools/call", {"name": "letterbox_check", "arguments": {}})
    assert check["result"]["isError"] is True
    assert ident in _text(check)
    assert "shown=" not in _text(check) or "letters" not in (check["result"].get("structuredContent") or {})
    read = client.request("tools/call", {"name": "letterbox_read", "arguments": {"id": ident}})
    assert read["result"]["isError"] is True
    assert "duplicate_key" in _text(read)
    assert "message not found in your inbox" not in _text(read)
