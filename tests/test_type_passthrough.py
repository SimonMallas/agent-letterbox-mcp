import pytest

from tests.conftest import live_id
from tests.harness import AGENT, write_letter

# Unicode characters that str.splitlines() treats as line breaks, besides \n/\r.
_SPLITLINES_CONTROLS = (
    "\u000b",  # VT
    "\u000c",  # FF
    "\u001c",  # FS
    "\u001d",  # GS
    "\u001e",  # RS
    "\u0085",  # NEL
)


def _init(client):
    client.initialize()


def _check(client):
    return client.request("tools/call", {"name": "letterbox_check", "arguments": {}})


def _read(client, ident: str):
    return client.request("tools/call", {"name": "letterbox_read", "arguments": {"id": ident}})


def _assert_loud_both(client, ident: str) -> None:
    check = _check(client)
    assert check["result"]["isError"] is True
    check_text = "".join(block.get("text", "") for block in check["result"]["content"])
    assert ident in check_text
    structured = check["result"].get("structuredContent") or {}
    assert "letters" not in structured
    read = _read(client, ident)
    assert read["result"]["isError"] is True
    read_text = "".join(block.get("text", "") for block in read["result"]["content"])
    assert ident in read_text
    assert "message not found in your inbox" not in read_text


def test_type_passthrough_verbatim_and_complete(client, mailbox):
    review_id = live_id("treview")
    dotted_id = live_id("trev2")
    ascii64_id = live_id("t64a")
    multi64_id = live_id("t64m")
    missing_id = live_id("tmiss")
    write_letter(mailbox, review_id, "a", type_name="review")
    write_letter(mailbox, dotted_id, "a", type_name="review.v2")
    write_letter(mailbox, ascii64_id, "a", type_name="t" * 64)
    multibyte = "\u4e00" * 64
    assert len(multibyte) == 64
    assert len(multibyte.encode("utf-8")) > 64
    write_letter(mailbox, multi64_id, "a", type_name=multibyte)
    write_letter(mailbox, missing_id, "a", type_name=None)
    _init(client)
    result = _check(client)
    assert result["result"]["isError"] is False
    structured = result["result"]["structuredContent"]
    assert structured["truncated"] is False
    assert structured["remaining"] == 0
    by_id = {item["id"]: item["type"] for item in structured["letters"]}
    assert by_id[review_id] == "review"
    assert by_id[dotted_id] == "review.v2"
    assert by_id[ascii64_id] == "t" * 64
    assert by_id[multi64_id] == multibyte
    assert by_id[missing_id] == ""
    for ident, expected in by_id.items():
        read = _read(client, ident)
        assert read["result"]["isError"] is False
        assert read["result"]["structuredContent"]["type"] == expected


def test_type_65_codepoints_fails_both_tools(client, mailbox):
    ident = live_id("t65")
    write_letter(mailbox, ident, "a", type_name="x" * 65)
    _init(client)
    _assert_loud_both(client, ident)


def test_type_c0_control_fails_both_tools(client, mailbox):
    ident = live_id("tc0")
    write_letter(mailbox, ident, "a", type_name="ab\x01cd")
    _init(client)
    _assert_loud_both(client, ident)


def test_type_65_codepoints_under_64_graphemes_fails_both_tools(client, mailbox):
    ident = live_id("tcomb")
    kind = "e" + ("\u0301" * 64)
    assert len(kind) == 65
    write_letter(mailbox, ident, "a", type_name=kind)
    _init(client)
    _assert_loud_both(client, ident)


def test_odd_type_counted_in_remaining_when_cap_binds(client, mailbox):
    for i in range(50):
        write_letter(mailbox, live_id(f"n{i:02d}{i:02d}"), "short")
    odd_id = "2026-09-18T120000-beta-review-capodd1"
    write_letter(mailbox, odd_id, "short", type_name="review")
    _init(client)
    result = _check(client)
    structured = result["result"]["structuredContent"]
    assert result["result"]["isError"] is False
    assert structured["truncated"] is True
    assert structured["remaining"] == 1
    assert len(structured["letters"]) == 50
    ids = {item["id"] for item in structured["letters"]}
    assert odd_id not in ids


def test_unparseable_files_are_omitted(client, mailbox):
    inbox = mailbox / AGENT / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    missing_from = live_id("nofrom")
    (inbox / f"{missing_from}.md").write_text(
        f"---\nid: {missing_from}\nto: {AGENT}\ntype: info\n---\nbody\n",
        encoding="utf-8",
    )
    missing_to = live_id("noto")
    (inbox / f"{missing_to}.md").write_text(
        f"---\nid: {missing_to}\nfrom: beta\ntype: info\n---\nbody\n",
        encoding="utf-8",
    )
    (inbox / "spaces.md").write_text(
        "---\nid: has spaces\nfrom: beta\nto: alpha\ntype: info\n---\nbody\n",
        encoding="utf-8",
    )
    keep = live_id("keep")
    write_letter(mailbox, keep, "ok")
    _init(client)
    result = _check(client)
    structured = result["result"]["structuredContent"]
    assert result["result"]["isError"] is False
    assert structured["truncated"] is False
    assert structured["remaining"] == 0
    ids = {item["id"] for item in structured["letters"]}
    assert keep in ids
    assert missing_from not in ids
    assert missing_to not in ids
    assert "has spaces" not in ids
    assert _read(client, missing_from)["result"]["isError"] is True


@pytest.mark.parametrize("control", _SPLITLINES_CONTROLS)
def test_type_splitlines_control_fails_both_tools(client, mailbox, control):
    ident = live_id(f"ts{ord(control):04x}")
    write_letter(mailbox, ident, "a", type_name=f"ab{control}cd")
    _init(client)
    _assert_loud_both(client, ident)


def test_type_u0080_still_fails_both_tools(client, mailbox):
    ident = live_id("t80")
    write_letter(mailbox, ident, "a", type_name="ab\u0080cd")
    _init(client)
    _assert_loud_both(client, ident)


def test_id_with_nel_does_not_masquerade(client, mailbox):
    """U+0085 in id is not a line break here; the full value fails the id grammar."""
    inbox = mailbox / AGENT / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    prefix = "2026-09-19T060000-beta-info-pre"
    (inbox / "nel-id.md").write_text(
        f"---\nid: {prefix}\u0085tail\nfrom: beta\nto: {AGENT}\ntype: info\n---\nbody\n",
        encoding="utf-8",
    )
    keep = live_id("idkeep")
    write_letter(mailbox, keep, "ok")
    _init(client)
    result = _check(client)
    structured = result["result"]["structuredContent"]
    assert result["result"]["isError"] is False
    ids = {item["id"] for item in structured["letters"]}
    assert keep in ids
    assert prefix not in ids
    assert f"{prefix}\u0085tail" not in ids
    read = _read(client, prefix)
    assert read["result"]["isError"] is True
    assert "unrepresentable type" not in "".join(
        block.get("text", "") for block in read["result"]["content"]
    )


def test_from_and_to_carry_nel_verbatim(client, mailbox):
    ident = live_id("fromnel")
    inbox = mailbox / AGENT / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / f"{ident}.md").write_text(
        f"---\nid: {ident}\nfrom: ab\u0085cd\nto: xy\u000bcd\ntype: info\n---\nbody\n",
        encoding="utf-8",
    )
    _init(client)
    result = _check(client)
    assert result["result"]["isError"] is False
    structured = result["result"]["structuredContent"]
    assert structured["remaining"] == 0
    match = next(item for item in structured["letters"] if item["id"] == ident)
    assert match["from"] == "ab\u0085cd"
    assert match["to"] == "xy\u000bcd"
    read = _read(client, ident)
    assert read["result"]["isError"] is False
    assert read["result"]["structuredContent"]["from"] == "ab\u0085cd"
    assert read["result"]["structuredContent"]["to"] == "xy\u000bcd"
