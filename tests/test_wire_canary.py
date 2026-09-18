from tests.conftest import canary_letter, live_id
from tests.harness import CANARY


def test_wire_canary_whole_transcript(client, mailbox):
    ident = live_id("wirecanary")
    canary_letter(mailbox, ident, 50_000)
    client.initialize()
    client.request("tools/list")
    client.request("tools/call", {"name": "letterbox_check", "arguments": {}})
    client.request("resources/list")
    client.request("resources/templates/list")
    client.request(
        "tools/call",
        {"name": "letterbox_read", "arguments": {"id": ident, "include_body": False}},
    )
    ping = client.request("ping")
    assert "result" in ping
    quiet = client.transcript()
    assert CANARY not in quiet
    assert "LETTERBOX_BODY_CANARY_" not in quiet

    shown = client.request(
        "tools/call",
        {"name": "letterbox_read", "arguments": {"id": ident, "include_body": True}},
    )
    structured = shown["result"]["structuredContent"]
    assert CANARY in structured["body"]
    text_blocks = [block.get("text", "") for block in shown["result"]["content"] if block.get("type") == "text"]
    assert any(CANARY in block for block in text_blocks)
    for block in shown["result"]["content"]:
        if block.get("type") == "resource_link":
            assert CANARY not in str(block.get("uri", ""))
    # The canary may appear only in structured body and the duplicated JSON text block.
    for block in shown["result"]["content"]:
        if block.get("type") == "text":
            assert block["text"].startswith("{")
            assert '"body":' in block["text"]
