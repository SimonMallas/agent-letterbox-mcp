from __future__ import annotations

import json
import sys
import time
from typing import Any

import anyio
import jsonschema
import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import McpError
from mcp.shared.message import SessionMessage
from mcp.types import ErrorData, JSONRPCRequest

from letterbox_mcp.constants import (
    BIDI_CONTROL_CHARS,
    DEFAULT_MAX_BODY_CHARS,
    JSONRPC_INVALID_PARAMS,
    LETTER_MIME,
    RESOURCE_BYTE_CEILING,
    SERVER_NAME,
    SERVER_VERSION,
    URI_PREFIX,
)

_JSON_TEXT_ESCAPES = {
    ord(ch): f"\\u{ord(ch):04x}"
    for ch in ("\u2028", "\u2029", *BIDI_CONTROL_CHARS)
}
from letterbox_mcp.errors import not_found_error, too_large_error, unknown_id_tool_text
from letterbox_mcp.ids import is_letter_id, letter_uri, parse_letter_uri
from letterbox_mcp.mailbox import Mailbox
from letterbox_mcp.render import clip_body, envelope_text, render_check
from letterbox_mcp.schemas import (
    CHECK_INPUT_SCHEMA,
    CHECK_OUTPUT_SCHEMA,
    CHECK_TOOL_ANNOTATIONS,
    READ_INPUT_SCHEMA,
    READ_OUTPUT_SCHEMA,
    READ_TOOL_ANNOTATIONS,
)

STAGE_ONE_TOOLS = ("letterbox_check", "letterbox_read")

# Raw resources/read URIs keyed by JSON-RPC id, captured before AnyUrl normalizes.
# Bounded: SDK validation can reject before the handler pops.
RAW_URI_CAP = 8
_RAW_URIS: dict[object, str] = {}


def store_raw_uri(request_id: object, uri: str) -> None:
    _RAW_URIS.pop(request_id, None)
    _RAW_URIS[request_id] = uri
    while len(_RAW_URIS) > RAW_URI_CAP:
        _RAW_URIS.pop(next(iter(_RAW_URIS)))


def take_raw_uri(request_id: object | None) -> str | None:
    if request_id is None:
        return None
    return _RAW_URIS.pop(request_id, None)


def build_server(mailbox: Mailbox) -> Server:
    server = Server(SERVER_NAME)

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="letterbox_check",
                description="List open letters. Never returns bodies.",
                inputSchema=CHECK_INPUT_SCHEMA,
                outputSchema=CHECK_OUTPUT_SCHEMA,
                annotations=types.ToolAnnotations(**CHECK_TOOL_ANNOTATIONS),
            ),
            types.Tool(
                name="letterbox_read",
                description="Read one letter by id. Body stays off the text channel unless include_body is true.",
                inputSchema=READ_INPUT_SCHEMA,
                outputSchema=READ_OUTPUT_SCHEMA,
                annotations=types.ToolAnnotations(**READ_TOOL_ANNOTATIONS),
            ),
        ]

    @server.list_resources()
    async def list_resources() -> list[types.Resource]:
        return []

    @server.list_resource_templates()
    async def list_resource_templates() -> list[types.ResourceTemplate]:
        return [
            types.ResourceTemplate(
                name="letter",
                uriTemplate=f"{URI_PREFIX}{{id}}",
                mimeType=LETTER_MIME,
                description="A single letter on the durable plane.",
            )
        ]

    async def handle_read_resource(req: types.ReadResourceRequest) -> types.ServerResult:
        request_id = getattr(req, "id", None)
        if request_id is None:
            request_id = _rpc_id(server)
        raw = take_raw_uri(request_id)
        try:
            normalized = str(req.params.uri)
            if raw is None:
                raise not_found_error(uri=normalized)
            if raw != normalized:
                raise not_found_error(uri=raw)
            letter_id = parse_letter_uri(raw)
            if letter_id is None:
                raise not_found_error(uri=raw)
            loaded = mailbox.read_file_bytes(letter_id)
            if loaded is None:
                raise not_found_error(uri=raw)
            size, data = loaded
            if size > RESOURCE_BYTE_CEILING:
                raise too_large_error(letter_id, size)
            text = data.decode("utf-8", errors="replace")
            return types.ServerResult(
                types.ReadResourceResult(
                    contents=[
                        types.TextResourceContents(
                            uri=types.AnyUrl(letter_uri(letter_id)),
                            text=text,
                            mimeType=LETTER_MIME,
                        )
                    ]
                )
            )
        finally:
            take_raw_uri(request_id)

    server.request_handlers[types.ReadResourceRequest] = handle_read_resource

    async def call_tool(req: types.CallToolRequest) -> types.ServerResult:
        name = req.params.name
        if name not in STAGE_ONE_TOOLS:
            raise McpError(ErrorData(code=JSONRPC_INVALID_PARAMS, message=f"Unknown tool: {name}"))
        arguments = req.params.arguments or {}
        schema = CHECK_INPUT_SCHEMA if name == "letterbox_check" else READ_INPUT_SCHEMA
        try:
            jsonschema.validate(instance=arguments, schema=schema)
        except jsonschema.ValidationError as exc:
            return _tool_error(exc.message)
        rpc_id = _rpc_id(server)
        started = time.monotonic()
        if name == "letterbox_check":
            result = _guard_tool_output(name, _do_check(mailbox))
            _log(rpc_id, name, None, started, False)
            return types.ServerResult(result)
        result = _guard_tool_output(name, _do_read(mailbox, arguments))
        body_inlined = bool(
            not result.isError
            and isinstance(result.structuredContent, dict)
            and "body" in result.structuredContent
        )
        letter_id = arguments.get("id") if isinstance(arguments.get("id"), str) else None
        _log(rpc_id, name, letter_id, started, body_inlined)
        return types.ServerResult(result)

    server.request_handlers[types.CallToolRequest] = call_tool
    return server


def initialization_options() -> InitializationOptions:
    return InitializationOptions(
        server_name=SERVER_NAME,
        server_version=SERVER_VERSION,
        capabilities=types.ServerCapabilities(
            tools=types.ToolsCapability(),
            resources=types.ResourcesCapability(),
        ),
    )


async def run_stdio(mailbox: Mailbox) -> None:
    server = build_server(mailbox)
    async with stdio_server() as (read_stream, write_stream):
        tap_send, tap_recv = anyio.create_memory_object_stream(0)
        async with anyio.create_task_group() as tg:
            tg.start_soon(_tap_raw_uris, read_stream, tap_send)
            try:
                await server.run(tap_recv, write_stream, initialization_options())
            finally:
                tg.cancel_scope.cancel()


async def _tap_raw_uris(source, dest) -> None:
    try:
        async with dest:
            async for item in source:
                if isinstance(item, SessionMessage):
                    root = item.message.root
                    if isinstance(root, JSONRPCRequest) and root.method == "resources/read":
                        params = root.params
                        if isinstance(params, dict):
                            uri = params.get("uri")
                            if isinstance(uri, str):
                                store_raw_uri(root.id, uri)
                await dest.send(item)
    except anyio.get_cancelled_exc_class():
        pass


def dump_structured_json(data: dict) -> str:
    """JSON text block: C0/C1 via json.dumps; U+2028/U+2029 and Bidi_Control too."""
    text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return text.translate(_JSON_TEXT_ESCAPES)


def enforce_output_schema(schema: dict, data: dict) -> None:
    jsonschema.validate(instance=data, schema=schema)


def _guard_tool_output(name: str, result: types.CallToolResult) -> types.CallToolResult:
    if result.isError or not isinstance(result.structuredContent, dict):
        return result
    schema = CHECK_OUTPUT_SCHEMA if name == "letterbox_check" else READ_OUTPUT_SCHEMA
    try:
        enforce_output_schema(schema, result.structuredContent)
    except jsonschema.ValidationError:
        return _tool_error("output failed freeze schema")
    return result


def _unrepresentable_metadata_error(letter_id: str) -> types.CallToolResult:
    return _tool_error(f"unrepresentable metadata on {letter_id}")


def _do_check(mailbox: Mailbox) -> types.CallToolResult:
    open_letters = mailbox.list_open()
    bad = next((item for item in open_letters if item.metadata_unrepresentable), None)
    if bad is not None:
        return _unrepresentable_metadata_error(bad.id)
    refs, table, truncated, remaining = render_check(open_letters)
    structured = {"letters": refs, "truncated": truncated, "remaining": remaining}
    enforce_output_schema(CHECK_OUTPUT_SCHEMA, structured)
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=table)],
        structuredContent=structured,
        isError=False,
    )


def _do_read(mailbox: Mailbox, arguments: dict[str, Any]) -> types.CallToolResult:
    letter_id = arguments["id"]
    if not is_letter_id(letter_id):
        return _tool_error(unknown_id_tool_text())
    letter = mailbox.get(letter_id, inbox_only=True)
    if letter is None:
        return _tool_error(unknown_id_tool_text())
    if letter.metadata_unrepresentable:
        return _unrepresentable_metadata_error(letter.id)
    include_body = bool(arguments.get("include_body", False))
    max_body_chars = arguments.get("max_body_chars")
    if max_body_chars is None and include_body:
        max_body_chars = DEFAULT_MAX_BODY_CHARS
    ref = letter.as_ref()
    link = types.ResourceLink(
        type="resource_link",
        name="letter",
        uri=letter_uri(letter.id),
        mimeType=LETTER_MIME,
    )
    if not include_body:
        enforce_output_schema(READ_OUTPUT_SCHEMA, ref)
        return types.CallToolResult(
            content=[
                types.TextContent(type="text", text=envelope_text(ref)),
                link,
            ],
            structuredContent=ref,
            isError=False,
        )
    body, truncated = clip_body(letter.body, max_body_chars)
    structured = {**ref, "body": body, "truncated": truncated}
    enforce_output_schema(READ_OUTPUT_SCHEMA, structured)
    dumped = dump_structured_json(structured)
    return types.CallToolResult(
        content=[
            types.TextContent(type="text", text=dumped),
            link,
        ],
        structuredContent=structured,
        isError=False,
    )


def _tool_error(message: str) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=message)],
        isError=True,
    )


def _rpc_id(server: Server) -> str | int | None:
    try:
        return server.request_context.request_id
    except LookupError:
        return None


def _log(
    rpc_id: str | int | None,
    tool: str,
    letter_id: str | None,
    started: float,
    body_inlined: bool,
) -> None:
    payload = {
        "rpc_id": rpc_id,
        "tool": tool,
        "letter_id": letter_id,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "body_inlined": body_inlined,
    }
    sys.stderr.write(json.dumps(payload, separators=(",", ":")) + "\n")
    sys.stderr.flush()
