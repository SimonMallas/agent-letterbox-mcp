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
    table_ids = [line.split(" ", 1)[0] for line in table.strip().splitlines()[1:] if line]
    assert table_ids == [item["id"] for item in structured["letters"]]


def test_character_cap_binds_first(client, mailbox):
    for i in range(30):
        ident = (live_id(f"{i:02d}") + ("w" * 128))[:128]
        write_letter(mailbox, ident, "x")
    _init(client)
    result = client.request("tools/call", {"name": "letterbox_check", "arguments": {}})
    structured = result["result"]["structuredContent"]
    table = result["result"]["content"][0]["text"]
    rows = [line for line in table.splitlines() if line and not line.startswith("id ")]
    assert len(rows) == len(structured["letters"])
    assert len(structured["letters"]) < 30
    assert len(structured["letters"]) < 50
    assert structured["truncated"] is True
    assert structured["remaining"] == 30 - len(structured["letters"])
    assert len(table) <= 4000
    if rows:
        last = rows[-1]
        assert last == f"{structured['letters'][-1]['id']} {structured['letters'][-1]['from']} {structured['letters'][-1]['state']} {structured['letters'][-1]['age']}"
        assert not last.endswith(" ")
