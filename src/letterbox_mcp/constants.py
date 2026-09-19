"""Frozen numeric and protocol values. Do not derive or adjust."""

PROTOCOL_VERSION = "2025-11-25"
SERVER_NAME = "letterbox-mcp"
SERVER_VERSION = "0.1.0"

ID_PATTERN = r"^[A-Za-z0-9_.:-]{1,128}$"

# Documented source set. Never enforced: type is carried verbatim.
LETTER_TYPES = (
    "request",
    "delegate",
    "status",
    "blocker",
    "result",
    "ack",
    "nack",
    "info",
)
LETTER_STATES = ("open", "acked", "processed")
TYPE_MAX_CODEPOINTS = 64

# Frozen Bidi_Control set at UCD 16.0.0. Do not derive from unicodedata.
BIDI_CONTROL_SOURCE_UCD = "16.0.0"
BIDI_CONTROL_CHARS = (
    "\u061c",
    "\u200e",
    "\u200f",
    "\u202a",
    "\u202b",
    "\u202c",
    "\u202d",
    "\u202e",
    "\u2066",
    "\u2067",
    "\u2068",
    "\u2069",
)

CHECK_LETTER_CAP = 50
CHECK_CHAR_CAP = 4000
DEFAULT_MAX_BODY_CHARS = 4000
MAX_BODY_CHARS_MIN = 1
MAX_BODY_CHARS_MAX = 32000
RESOURCE_BYTE_CEILING = 1_048_576
STALE_SECONDS = 14 * 86400

URI_PREFIX = "letterbox://letter/"
LETTER_MIME = "text/markdown"

JSONRPC_INVALID_PARAMS = -32602
JSONRPC_TOO_LARGE = -32000
JSONRPC_NOT_FOUND = -32002

REASON_NOT_FOUND = "not_found"
REASON_TOO_LARGE = "too_large"

CHECK_TABLE_HEADER = "id from state age\n"
