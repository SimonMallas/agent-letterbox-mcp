import jsonschema
import mcp.types as types

from letterbox_mcp.schemas import CHECK_OUTPUT_SCHEMA, READ_OUTPUT_SCHEMA
from letterbox_mcp.server import _guard_tool_output, enforce_output_schema


def _valid_check() -> dict:
    return {
        "letters": [
            {
                "id": "a",
                "from": "beta",
                "to": "alpha",
                "type": "info",
                "state": "open",
                "age": "0m",
                "uri": "letterbox://letter/a",
                "priority": "next",
                "requires_ack": False,
                "deadline": "",
            }
        ],
        "truncated": False,
        "remaining": 0,
    }


def test_check_output_rejects_injected_path():
    payload = {**_valid_check(), "path": "/tmp/leak"}
    try:
        enforce_output_schema(CHECK_OUTPUT_SCHEMA, payload)
        raise AssertionError("path must not pass additionalProperties: false")
    except jsonschema.ValidationError:
        pass


def test_read_output_rejects_injected_path():
    payload = {
        "id": "a",
        "from": "beta",
        "to": "alpha",
        "type": "info",
        "state": "open",
        "age": "0m",
        "uri": "letterbox://letter/a",
        "priority": "next",
        "requires_ack": False,
        "deadline": "",
        "thread": "",
        "re": "",
        "path": "/tmp/leak",
    }
    try:
        enforce_output_schema(READ_OUTPUT_SCHEMA, payload)
        raise AssertionError("path must not pass additionalProperties: false")
    except jsonschema.ValidationError:
        pass


def test_guard_rejects_injected_path_and_does_not_emit_it():
    leaked = types.CallToolResult(
        content=[types.TextContent(type="text", text="ok")],
        structuredContent={**_valid_check(), "path": "/tmp/leak"},
        isError=False,
    )
    guarded = _guard_tool_output("letterbox_check", leaked)
    assert guarded.isError is True
    blob = str(guarded.model_dump())
    assert "/tmp/leak" not in blob
    assert not guarded.structuredContent
