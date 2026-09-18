from tests.conftest import canary_letter, live_id
from tests.harness import CANARY


def _init(client):
    client.initialize()


def test_default_max_body_chars_on_50k(client, mailbox):
    ident = live_id("body50k")
    canary_letter(mailbox, ident, 50_000)
    _init(client)
    result = client.request(
        "tools/call",
        {"name": "letterbox_read", "arguments": {"id": ident, "include_body": True}},
    )
    structured = result["result"]["structuredContent"]
    assert structured["truncated"] is True
    assert len(structured["body"]) == 4000
    blob = client.transcript()
    assert CANARY in structured["body"]
    assert "x" * 50_000 not in blob
    assert structured["body"] != CANARY + ("x" * (50_000 - len(CANARY)))


def test_max_body_chars_bounds(client, mailbox):
    ident = live_id("bounds")
    canary_letter(mailbox, ident, 50_000)
    _init(client)
    rejected_zero = client.request(
        "tools/call",
        {"name": "letterbox_read", "arguments": {"id": ident, "include_body": True, "max_body_chars": 0}},
    )
    assert rejected_zero["result"]["isError"] is True
    rejected_over = client.request(
        "tools/call",
        {"name": "letterbox_read", "arguments": {"id": ident, "include_body": True, "max_body_chars": 32001}},
    )
    assert rejected_over["result"]["isError"] is True
    accepted_min = client.request(
        "tools/call",
        {"name": "letterbox_read", "arguments": {"id": ident, "include_body": True, "max_body_chars": 1}},
    )
    assert accepted_min["result"]["isError"] is False
    assert accepted_min["result"]["structuredContent"]["body"]
    assert len(accepted_min["result"]["structuredContent"]["body"]) == 1
    assert accepted_min["result"]["structuredContent"]["truncated"] is True
    accepted_max = client.request(
        "tools/call",
        {"name": "letterbox_read", "arguments": {"id": ident, "include_body": True, "max_body_chars": 32000}},
    )
    assert accepted_max["result"]["isError"] is False
    assert len(accepted_max["result"]["structuredContent"]["body"]) == 32000
    assert accepted_max["result"]["structuredContent"]["truncated"] is True


def test_include_body_omitted_defaults_false(client, mailbox):
    ident = live_id("omitbody")
    canary_letter(mailbox, ident, 50_000)
    _init(client)
    result = client.request("tools/call", {"name": "letterbox_read", "arguments": {"id": ident}})
    structured = result["result"]["structuredContent"]
    assert "body" not in structured
    assert CANARY not in client.transcript()


def test_include_body_false_omits_body(client, mailbox):
    ident = live_id("nobody")
    canary_letter(mailbox, ident, 50_000)
    _init(client)
    result = client.request(
        "tools/call",
        {"name": "letterbox_read", "arguments": {"id": ident, "include_body": False}},
    )
    structured = result["result"]["structuredContent"]
    assert "body" not in structured
    text = "".join(block.get("text", "") for block in result["result"]["content"] if "text" in block)
    assert CANARY not in text
    assert CANARY not in str(structured)
    kinds = [block["type"] for block in result["result"]["content"]]
    assert "resource_link" in kinds
