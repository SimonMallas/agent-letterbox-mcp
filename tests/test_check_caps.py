from tests.conftest import canary_letter, live_id
from tests.harness import CANARY, write_letter


def _init(client):
    client.initialize()


def test_metadata_only_check_hides_50k_body(client, mailbox):
    ident = live_id("canary50k")
    canary_letter(mailbox, ident, 50_000)
    _init(client)
    result = client.request("tools/call", {"name": "letterbox_check", "arguments": {}})
    blob = client.transcript() + str(result)
    assert CANARY not in blob
    structured = result["result"]["structuredContent"]
    assert "letters" in structured
    assert structured["truncated"] is False
    assert structured["remaining"] == 0
    text = result["result"]["content"][0]["text"]
    assert CANARY not in text
    assert ident in text


def test_letter_cap_binds(client, mailbox):
    for i in range(60):
        write_letter(mailbox, live_id(f"n{i:02d}{i:02d}"), "short")
    _init(client)
    result = client.request("tools/call", {"name": "letterbox_check", "arguments": {}})
    structured = result["result"]["structuredContent"]
    assert len(structured["letters"]) == 50
    assert structured["truncated"] is True
    assert structured["remaining"] == 10
    table = result["result"]["content"][0]["text"]
    assert "shown=50 remaining=10 truncated=true" in table
    table_ids = [
        line.split(" ", 1)[0]
        for line in table.splitlines()
        if line and not line.startswith("id ") and not line.startswith("shown=")
    ]
    assert table_ids == [item["id"] for item in structured["letters"]]


def test_character_cap_binds_first(client, mailbox):
    for i in range(30):
        ident = (live_id(f"{i:02d}") + ("w" * 128))[:128]
        write_letter(mailbox, ident, "x")
    _init(client)
    result = client.request("tools/call", {"name": "letterbox_check", "arguments": {}})
    structured = result["result"]["structuredContent"]
    table = result["result"]["content"][0]["text"]
    rows = [
        line
        for line in table.splitlines()
        if line and not line.startswith("id ") and not line.startswith("shown=")
    ]
    assert len(rows) == len(structured["letters"])
    assert len(structured["letters"]) < 30
    assert len(structured["letters"]) < 50
    assert structured["truncated"] is True
    assert structured["remaining"] == 30 - len(structured["letters"])
    assert len(table) <= 4000
    if rows:
        from letterbox_mcp.render import json_string

        last_ref = structured["letters"][-1]
        ack = "true" if last_ref["requires_ack"] else "false"
        expected = (
            f"{last_ref['id']} {last_ref['from']} {last_ref['type']} {last_ref['priority']} "
            f"{ack} {json_string(last_ref['deadline'])} {last_ref['state']} {last_ref['age']}"
        )
        assert rows[-1] == expected
        assert not rows[-1].endswith(" ")
