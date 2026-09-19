from tests.conftest import live_id
from tests.harness import AGENT, write_letter


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
