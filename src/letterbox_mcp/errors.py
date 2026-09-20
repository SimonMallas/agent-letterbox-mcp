from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

from letterbox_mcp.constants import (
    JSONRPC_NOT_FOUND,
    JSONRPC_TOO_LARGE,
    REASON_NOT_FOUND,
    REASON_TOO_LARGE,
    RESOURCE_BYTE_CEILING,
)
from letterbox_mcp.ids import letter_uri


def not_found_error(*, uri: str) -> McpError:
    data = {"uri": uri, "reason": REASON_NOT_FOUND}
    return McpError(
        ErrorData(
            code=JSONRPC_NOT_FOUND,
            message="not_found",
            data=data,
        )
    )


def too_large_error(letter_id: str, size_bytes: int) -> McpError:
    data = {
        "uri": letter_uri(letter_id),
        "reason": REASON_TOO_LARGE,
        "size_bytes": size_bytes,
        "limit_bytes": RESOURCE_BYTE_CEILING,
    }
    return McpError(
        ErrorData(
            code=JSONRPC_TOO_LARGE,
            message=f"too_large size_bytes={size_bytes} limit_bytes={RESOURCE_BYTE_CEILING}",
            data=data,
        )
    )


def unknown_id_tool_text() -> str:
    return "message not found in your inbox"
