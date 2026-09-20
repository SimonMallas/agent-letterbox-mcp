from __future__ import annotations

import json
import re
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
    DEFAULT_MAX_BODY_CHARS,
    JSONRPC_INVALID_PARAMS,
    LETTER_MIME,
    RESOURCE_BYTE_CEILING,
    SERVER_NAME,
    SERVER_VERSION,
    URI_PREFIX,
)
from letterbox_mcp.errors import not_found_error, too_large_error, unknown_id_tool_text
from letterbox_mcp.ids import is_letter_id, letter_uri, parse_letter_uri
from letterbox_mcp.cli import run_cli
from letterbox_mcp.mailbox import (
    Mailbox,
    derived_reply_body,
    derived_reply_path,
    duplicate_key_message,
    preflight_for_file,
    preflight_for_reply,
)
from letterbox_mcp.render import clip_body, render_check
from letterbox_mcp.schemas import (
    CHECK_INPUT_SCHEMA,
    CHECK_OUTPUT_SCHEMA,
    CHECK_TOOL_ANNOTATIONS,
    FILE_INPUT_SCHEMA,
    FILE_OUTPUT_SCHEMA,
    FILE_TOOL_ANNOTATIONS,
    READ_INPUT_SCHEMA,
    READ_OUTPUT_SCHEMA,
    READ_TOOL_ANNOTATIONS,
    REPLY_INPUT_SCHEMA,
    REPLY_OUTPUT_SCHEMA,
    REPLY_TOOL_ANNOTATIONS,
    SEND_INPUT_SCHEMA,
    SEND_OUTPUT_SCHEMA,
    SEND_TOOL_ANNOTATIONS,
)
from letterbox_mcp.send import default_requires_ack, preflight_send

STAGE_TOOLS = (
    "letterbox_check",
    "letterbox_read",
    "letterbox_send",
    "letterbox_reply",
    "letterbox_file",
)
_INPUT_SCHEMAS = {
    "letterbox_check": CHECK_INPUT_SCHEMA,
    "letterbox_read": READ_INPUT_SCHEMA,
    "letterbox_send": SEND_INPUT_SCHEMA,
    "letterbox_reply": REPLY_INPUT_SCHEMA,
    "letterbox_file": FILE_INPUT_SCHEMA,
}
_OUTPUT_SCHEMAS = {
    "letterbox_check": CHECK_OUTPUT_SCHEMA,
    "letterbox_read": READ_OUTPUT_SCHEMA,
    "letterbox_send": SEND_OUTPUT_SCHEMA,
    "letterbox_reply": REPLY_OUTPUT_SCHEMA,
    "letterbox_file": FILE_OUTPUT_SCHEMA,
}

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
            types.Tool(
                name="letterbox_send",
                description="Send a letter. Server text always includes id, uri, and ring outcome/reason/target.",
                inputSchema=SEND_INPUT_SCHEMA,
                outputSchema=SEND_OUTPUT_SCHEMA,
                annotations=types.ToolAnnotations(**SEND_TOOL_ANNOTATIONS),
            ),
            types.Tool(
                name="letterbox_reply",
                description="Reply ack, nack, or result. Ring facts only for result.",
                inputSchema=REPLY_INPUT_SCHEMA,
                outputSchema=REPLY_OUTPUT_SCHEMA,
                annotations=types.ToolAnnotations(**REPLY_TOOL_ANNOTATIONS),
            ),
            types.Tool(
                name="letterbox_file",
                description="File a non-task letter. Repeat file is success and says already filed.",
                inputSchema=FILE_INPUT_SCHEMA,
                outputSchema=FILE_OUTPUT_SCHEMA,
                annotations=types.ToolAnnotations(**FILE_TOOL_ANNOTATIONS),
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
                raise not_found_error()
            if raw != normalized:
                raise not_found_error()
            letter_id = parse_letter_uri(raw)
            if letter_id is None:
                raise not_found_error()
            loaded = mailbox.read_file_bytes(letter_id)
            if loaded is None:
                raise not_found_error(uri=letter_uri(letter_id))
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
        if name not in STAGE_TOOLS:
            raise McpError(ErrorData(code=JSONRPC_INVALID_PARAMS, message="unknown tool"))
        arguments = req.params.arguments or {}
        schema = _INPUT_SCHEMAS[name]
        try:
            jsonschema.validate(instance=arguments, schema=schema)
        except jsonschema.ValidationError as exc:
            return _tool_error(_schema_error_text(exc, schema))
        rpc_id = _rpc_id(server)
        started = time.monotonic()
        if name == "letterbox_check":
            result = _guard_tool_output(name, _do_check(mailbox))
        elif name == "letterbox_read":
            result = _guard_tool_output(name, _do_read(mailbox, arguments))
        elif name == "letterbox_send":
            result = _guard_tool_output(name, _do_send(mailbox, arguments))
        elif name == "letterbox_reply":
            result = _guard_tool_output(name, _do_reply(mailbox, arguments))
        else:
            result = _guard_tool_output(name, _do_file(mailbox, arguments))
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
    """Frozen encoder: Python JSON with ensure_ascii=True."""
    return json.dumps(data, separators=(",", ":"), ensure_ascii=True)


def enforce_output_schema(schema: dict, data: dict) -> None:
    jsonschema.validate(instance=data, schema=schema)


def _guard_tool_output(name: str, result: types.CallToolResult) -> types.CallToolResult:
    if result.isError or not isinstance(result.structuredContent, dict):
        return result
    schema = _OUTPUT_SCHEMAS[name]
    try:
        enforce_output_schema(schema, result.structuredContent)
    except jsonschema.ValidationError:
        return _tool_error("output failed freeze schema")
    return result


def _unrepresentable_metadata_error(letter_id: str) -> types.CallToolResult:
    return _tool_error(f"unrepresentable metadata on {letter_id}")


def _do_check(mailbox: Mailbox) -> types.CallToolResult:
    open_letters = mailbox.list_open()
    dup = next((item for item in open_letters if item.duplicate_key), None)
    if dup is not None:
        return _tool_error(duplicate_key_message(dup))
    bad = next((item for item in open_letters if item.metadata_unrepresentable), None)
    if bad is not None:
        return _unrepresentable_metadata_error(bad.id)
    over = next((item for item in open_letters if item.deadline_over_bound), None)
    if over is not None:
        return _tool_error(f"deadline exceeds 256 code points on {over.id}")
    refs, table, truncated, remaining = render_check(open_letters)
    structured = {"letters": refs, "truncated": truncated, "remaining": remaining}
    enforce_output_schema(CHECK_OUTPUT_SCHEMA, structured)
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=table)],
        structuredContent=structured,
        isError=False,
    )


def _json_result(
    schema: dict, structured: dict, extra_text: str | None = None
) -> types.CallToolResult:
    enforce_output_schema(schema, structured)
    blocks = [types.TextContent(type="text", text=dump_structured_json(structured))]
    if extra_text:
        blocks.append(types.TextContent(type="text", text=extra_text))
    return types.CallToolResult(
        content=blocks,
        structuredContent=structured,
        isError=False,
    )


def _do_send(mailbox: Mailbox, arguments: dict[str, Any]) -> types.CallToolResult:
    to = arguments["to"]
    type_name = arguments["type"]
    subject = arguments["subject"]
    body = arguments["body"]
    deadline = arguments.get("deadline") or ""
    requires_ack = arguments.get("requires_ack")
    if requires_ack is None:
        requires_ack = default_requires_ack(type_name)
    err = preflight_send(
        root=mailbox._root,
        agent=mailbox._agent,
        to=to,
        type_name=type_name,
        subject=subject,
        body=body,
        requires_ack=requires_ack,
        deadline=deadline,
    )
    if err:
        return _tool_error(err)
    args = ["send", to, type_name, subject, "--now"]
    if requires_ack:
        args.append("--ack")
    if deadline:
        args.extend(["--deadline", deadline])
    cli = run_cli(mailbox._root, mailbox._agent, args, stdin=body)
    if not cli.ok:
        return _tool_error(cli.stderr or "CLI refused")
    if not cli.letter_id or not cli.ring:
        return _tool_error("CLI produced no doorbell-outcome")
    structured = {
        "id": cli.letter_id,
        "uri": letter_uri(cli.letter_id),
        "ring": {
            "outcome": cli.ring["outcome"],
            "reason": cli.ring["reason"],
            "target": cli.ring["target"],
        },
    }
    return _json_result(SEND_OUTPUT_SCHEMA, structured)


def _do_reply(mailbox: Mailbox, arguments: dict[str, Any]) -> types.CallToolResult:
    letter_id = arguments["id"]
    action = arguments["action"]
    body = arguments["body"]
    if not is_letter_id(letter_id):
        return _tool_error(unknown_id_tool_text())
    letter = mailbox.get(letter_id, inbox_only=False)
    if letter is None:
        return _tool_error(unknown_id_tool_text())
    err = preflight_for_reply(
        letter, root=mailbox._root, agent=mailbox._agent, action=action
    )
    if err:
        return _tool_error(err)
    existing = derived_reply_path(mailbox._root, letter, mailbox._agent, action)
    already_acked = False
    if action == "ack" and existing is not None:
        already_acked = derived_reply_body(existing) == body.rstrip("\n")
    args = ["reply", letter_id, action, "reply"]
    if action == "result":
        args.append("--now")
    cli = run_cli(mailbox._root, mailbox._agent, args, stdin=body)
    if not cli.ok:
        return _tool_error(cli.stderr or "CLI refused")
    structured: dict[str, Any] = {"action": action, "id": letter_id}
    extra = None
    if already_acked:
        extra = "ack already existed"
    if action == "result":
        if cli.already_closed:
            extra = "already closed"
        elif cli.ring:
            structured["ring"] = {
                "outcome": cli.ring["outcome"],
                "reason": cli.ring["reason"],
                "target": cli.ring["target"],
            }
        else:
            return _tool_error("CLI produced no doorbell-outcome")
    return _json_result(REPLY_OUTPUT_SCHEMA, structured, extra)


def _do_file(mailbox: Mailbox, arguments: dict[str, Any]) -> types.CallToolResult:
    letter_id = arguments["id"]
    if not is_letter_id(letter_id):
        return _tool_error(unknown_id_tool_text())
    letter = mailbox.get(letter_id, inbox_only=False)
    if letter is None:
        return _tool_error(unknown_id_tool_text())
    err = preflight_for_file(letter)
    if err:
        return _tool_error(err)
    cli = run_cli(mailbox._root, mailbox._agent, ["file", letter_id])
    if not cli.ok:
        return _tool_error(cli.stderr or "CLI refused")
    done = mailbox.get(letter_id, inbox_only=False)
    if done is None:
        return _tool_error("CLI filed but letter is missing")
    extra = "already filed" if cli.already_filed else None
    return _json_result(FILE_OUTPUT_SCHEMA, {"letter": done.as_ref()}, extra)


def _do_read(mailbox: Mailbox, arguments: dict[str, Any]) -> types.CallToolResult:
    letter_id = arguments["id"]
    if not is_letter_id(letter_id):
        return _tool_error(unknown_id_tool_text())
    letter = mailbox.get(letter_id, inbox_only=True)
    if letter is None:
        return _tool_error(unknown_id_tool_text())
    if letter.duplicate_key:
        return _tool_error(duplicate_key_message(letter))
    if letter.metadata_unrepresentable:
        return _unrepresentable_metadata_error(letter.id)
    if letter.deadline_over_bound:
        return _tool_error(f"deadline exceeds 256 code points on {letter.id}")
    if letter.thread_over_bound:
        return _tool_error(f"thread exceeds 256 code points on {letter.id}")
    if letter.re_over_bound:
        return _tool_error(f"re exceeds 256 code points on {letter.id}")
    include_body = bool(arguments.get("include_body", False))
    max_body_chars = arguments.get("max_body_chars")
    if max_body_chars is None and include_body:
        max_body_chars = DEFAULT_MAX_BODY_CHARS
    envelope = letter.as_envelope()
    link = types.ResourceLink(
        type="resource_link",
        name="letter",
        uri=letter_uri(letter.id),
        mimeType=LETTER_MIME,
    )
    if include_body:
        body, truncated = clip_body(letter.body, max_body_chars)
        envelope = {**envelope, "body": body, "truncated": truncated}
    enforce_output_schema(READ_OUTPUT_SCHEMA, envelope)
    dumped = dump_structured_json(envelope)
    return types.CallToolResult(
        content=[
            types.TextContent(type="text", text=dumped),
            link,
        ],
        structuredContent=envelope,
        isError=False,
    )


_VALIDATOR_TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


def _schema_error_text(exc: jsonschema.ValidationError, schema: dict) -> str:
    """Name only schema-owned facts. Never the failed instance or an extra key."""
    keyword = exc.validator if isinstance(exc.validator, str) else "invalid"
    if _VALIDATOR_TOKEN.fullmatch(keyword) is None:
        keyword = "invalid"
    owned = schema.get("properties") or {}
    parts: list[str] = []
    for part in exc.absolute_path:
        if isinstance(part, str) and part in owned:
            parts.append(part)
        else:
            break
    if parts:
        return f"invalid arguments {'/'.join(parts)} {keyword}"
    return f"invalid arguments {keyword}"


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
