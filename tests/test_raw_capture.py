import anyio
import mcp.types as types
from mcp.shared.exceptions import McpError

from letterbox_mcp.mailbox import Mailbox
from letterbox_mcp.server import (
    RAW_URI_CAP,
    _RAW_URIS,
    build_server,
    store_raw_uri,
    take_raw_uri,
)
from tests.harness import AGENT, write_letter

JAIL_BODY = "JAIL_TARGET_BODY"


def _read_req(uri: str, request_id: int) -> types.ReadResourceRequest:
    return types.ReadResourceRequest.model_validate(
        {
            "method": "resources/read",
            "params": {"uri": uri},
            "jsonrpc": "2.0",
            "id": request_id,
        }
    )


def _run_handler(mailbox_path, req: types.ReadResourceRequest):
    server = build_server(Mailbox(str(mailbox_path), AGENT))
    handler = server.request_handlers[types.ReadResourceRequest]

    async def go():
        return await handler(req)

    return anyio.run(go)


def test_absent_capture_refuses_even_when_letter_exists(mailbox):
    write_letter(mailbox, "x", JAIL_BODY)
    _RAW_URIS.clear()
    req = _read_req("letterbox://letter/x", 1)
    try:
        result = _run_handler(mailbox, req)
    except McpError as err:
        assert err.error.code == -32002
        assert err.error.data["reason"] == "not_found"
        assert "uri" not in (err.error.data or {})
        assert JAIL_BODY not in str(err.error)
        assert 1 not in _RAW_URIS
        return
    dumped = str(result.model_dump()) if hasattr(result, "model_dump") else str(result)
    raise AssertionError(f"absent capture must refuse, got {dumped}")


def test_malformed_flood_stays_bounded():
    _RAW_URIS.clear()
    for i in range(100):
        store_raw_uri(i, f"letterbox://letter/flood-{i}")
    assert len(_RAW_URIS) <= RAW_URI_CAP
    assert len(_RAW_URIS) == RAW_URI_CAP
    _RAW_URIS.clear()


def test_entry_never_survives_success_or_failure(mailbox):
    write_letter(mailbox, "x", JAIL_BODY)
    _RAW_URIS.clear()

    store_raw_uri(10, "letterbox://letter/x")
    result = _run_handler(mailbox, _read_req("letterbox://letter/x", 10))
    assert 10 not in _RAW_URIS
    contents = result.root.contents
    assert JAIL_BODY in contents[0].text

    store_raw_uri(11, "letterbox://letter/missing")
    try:
        _run_handler(mailbox, _read_req("letterbox://letter/missing", 11))
    except McpError as err:
        assert err.error.code == -32002
    else:
        raise AssertionError("missing letter must refuse")
    assert 11 not in _RAW_URIS
    assert take_raw_uri(11) is None
