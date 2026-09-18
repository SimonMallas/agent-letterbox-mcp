from tests.conftest import live_id
from tests.harness import write_letter
from letterbox_mcp.constants import LETTER_TYPES
from letterbox_mcp.schemas import FILE_TOOL_ANNOTATIONS


def _init(client):
    result = client.initialize()
    caps = result["result"]["capabilities"]
    assert "tools" in caps
    assert caps["tools"] == {}
    assert caps["resources"] == {}
    assert "listChanged" not in caps["tools"]
    assert "subscribe" not in caps["resources"]
    assert "tasks" not in caps or caps["tasks"] in (None, {})


def test_extra_keys_rejected_as_tool_error(client, mailbox):
    _init(client)
    ident = live_id("extra")
    write_letter(mailbox, ident, "hello")
    check = client.request("tools/call", {"name": "letterbox_check", "arguments": {"unexpected": True}})
    assert check["result"]["isError"] is True
    read = client.request(
        "tools/call",
        {"name": "letterbox_read", "arguments": {"id": ident, "extra": 1}},
    )
    assert read["result"]["isError"] is True


def test_enum_exhaustiveness_type_set():
    assert LETTER_TYPES == (
        "request",
        "delegate",
        "status",
        "blocker",
        "result",
        "ack",
        "nack",
        "info",
    )


def test_read_rejects_non_boolean_include_body(client, mailbox):
    _init(client)
    ident = live_id("enum")
    write_letter(mailbox, ident, "hello")
    result = client.request(
        "tools/call",
        {"name": "letterbox_read", "arguments": {"id": ident, "include_body": "yes"}},
    )
    assert result["result"]["isError"] is True


def test_file_annotations_frozen():
    assert FILE_TOOL_ANNOTATIONS["idempotentHint"] is True
    assert FILE_TOOL_ANNOTATIONS["destructiveHint"] is True


def test_tools_list_stage_one_only(client, mailbox):
    _init(client)
    listed = client.request("tools/list")
    names = [tool["name"] for tool in listed["result"]["tools"]]
    assert names == ["letterbox_check", "letterbox_read"]
    for tool in listed["result"]["tools"]:
        assert tool["inputSchema"]["additionalProperties"] is False
        assert "outputSchema" in tool
