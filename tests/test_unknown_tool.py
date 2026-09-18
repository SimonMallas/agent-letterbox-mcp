from letterbox_mcp.constants import JSONRPC_INVALID_PARAMS


def test_unknown_tool_is_protocol_error(client, mailbox):
    client.initialize()
    resp = client.request("tools/call", {"name": "letterbox_send", "arguments": {"to": "beta"}})
    assert resp["error"]["code"] == JSONRPC_INVALID_PARAMS
    assert "result" not in resp or resp.get("result") is None
