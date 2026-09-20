"""Duplicate keys are corruption, judged before the letter gate, named by filename."""

from letterbox_mcp.mailbox import Mailbox, preflight_for_file
from tests.conftest import live_id
from tests.harness import AGENT


def _init(client):
    client.initialize()


def _text(result: dict) -> str:
    return "".join(
        block.get("text", "") for block in result["result"].get("content", []) if "text" in block
    )


def _write_dup(mailbox, ident: str, header_body: str) -> None:
    inbox = mailbox / AGENT / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / f"{ident}.md").write_text(header_body, encoding="utf-8")


def _assert_three_tools(client, mailbox, ident: str, *, injected: str | None = None) -> None:
    _init(client)
    check = client.request("tools/call", {"name": "letterbox_check", "arguments": {}})
    assert check["result"]["isError"] is True
    check_text = _text(check)
    assert ident in check_text
    assert "shown=" not in check_text
    if injected:
        assert injected not in check_text
    read = client.request("tools/call", {"name": "letterbox_read", "arguments": {"id": ident}})
    assert read["result"]["isError"] is True
    assert "duplicate_key" in _text(read)
    assert "message not found in your inbox" not in _text(read)
    if injected:
        other = client.request("tools/call", {"name": "letterbox_read", "arguments": {"id": injected}})
        assert other["result"]["isError"] is True
        assert "duplicate_key" not in _text(other)
        assert "message not found in your inbox" in _text(other)
    before = {
        path.relative_to(mailbox): path.read_bytes()
        for path in mailbox.rglob("*")
        if path.is_file()
    }
    box = Mailbox(str(mailbox), AGENT)
    letter = box.get(ident, inbox_only=True)
    assert letter is not None
    err = preflight_for_file(letter)
    assert err is not None
    assert "duplicate_key" in err
    assert ident in err
    if injected:
        assert injected not in err
    after = {
        path.relative_to(mailbox): path.read_bytes()
        for path in mailbox.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_duplicate_id_last_invalid(client, mailbox):
    ident = live_id("dupidinv")
    _write_dup(
        mailbox,
        ident,
        f"---\nid: {ident}\nid: has spaces\nfrom: beta\nto: {AGENT}\ntype: info\n---\n",
    )
    _assert_three_tools(client, mailbox, ident)


def test_duplicate_id_last_injected_valid(client, mailbox):
    ident = live_id("dupidinj")
    injected = "2026-09-20T000000-beta-info-injected"
    _write_dup(
        mailbox,
        ident,
        f"---\nid: {ident}\nid: {injected}\nfrom: beta\nto: {AGENT}\ntype: info\n---\n",
    )
    _assert_three_tools(client, mailbox, ident, injected=injected)


def test_duplicate_from_last_empty(client, mailbox):
    ident = live_id("dupfrome")
    _write_dup(
        mailbox,
        ident,
        f"---\nid: {ident}\nfrom: beta\nfrom:\nto: {AGENT}\ntype: info\n---\n",
    )
    _assert_three_tools(client, mailbox, ident)


def test_duplicate_to_last_empty(client, mailbox):
    ident = live_id("duptoe")
    _write_dup(
        mailbox,
        ident,
        f"---\nid: {ident}\nfrom: beta\nto: {AGENT}\nto:\ntype: info\n---\n",
    )
    _assert_three_tools(client, mailbox, ident)


def test_duplicate_to_two_values(client, mailbox):
    ident = live_id("dupto2")
    _write_dup(
        mailbox,
        ident,
        f"---\nid: {ident}\nfrom: beta\nto: {AGENT}\nto: other\ntype: info\n---\n",
    )
    _assert_three_tools(client, mailbox, ident)


def test_duplicate_type_two_values(client, mailbox):
    ident = live_id("duptype")
    _write_dup(
        mailbox,
        ident,
        f"---\nid: {ident}\nfrom: beta\nto: {AGENT}\ntype: info\ntype: request\n---\n",
    )
    _assert_three_tools(client, mailbox, ident)
