"""Frozen tool schemas. additionalProperties is false on inputs and outputs."""

from letterbox_mcp.constants import (
    LETTER_STATES,
    MAX_BODY_CHARS_MAX,
    MAX_BODY_CHARS_MIN,
)

LETTER_REF_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "from": {"type": "string"},
        "to": {"type": "string"},
        "type": {"type": "string"},
        "state": {"type": "string", "enum": list(LETTER_STATES)},
        "age": {"type": "string"},
        "uri": {"type": "string"},
        "priority": {"type": "string"},
        "requires_ack": {"type": "boolean"},
        "deadline": {"type": "string"},
    },
    "required": [
        "id",
        "from",
        "to",
        "type",
        "state",
        "age",
        "uri",
        "priority",
        "requires_ack",
        "deadline",
    ],
    "additionalProperties": False,
}

LETTER_ENVELOPE_SCHEMA = {
    "type": "object",
    "properties": {
        **LETTER_REF_SCHEMA["properties"],
        "thread": {"type": "string"},
        "re": {"type": "string"},
        "body": {"type": "string"},
        "truncated": {"type": "boolean"},
    },
    "required": list(LETTER_REF_SCHEMA["required"]) + ["thread", "re"],
    "additionalProperties": False,
}

CHECK_INPUT_SCHEMA = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

CHECK_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "letters": {"type": "array", "items": LETTER_REF_SCHEMA},
        "truncated": {"type": "boolean"},
        "remaining": {"type": "integer", "minimum": 0},
    },
    "required": ["letters", "truncated", "remaining"],
    "additionalProperties": False,
}

READ_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "include_body": {"type": "boolean"},
        "max_body_chars": {
            "type": "integer",
            "minimum": MAX_BODY_CHARS_MIN,
            "maximum": MAX_BODY_CHARS_MAX,
        },
    },
    "required": ["id"],
    "additionalProperties": False,
}

READ_OUTPUT_SCHEMA = LETTER_ENVELOPE_SCHEMA

SENDABLE_TYPE_ENUM = ["request", "delegate", "status", "blocker", "info"]
REPLY_ACTION_ENUM = ["ack", "nack", "result"]

SEND_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "to": {"type": "string", "minLength": 1},
        "type": {"type": "string", "enum": SENDABLE_TYPE_ENUM},
        "subject": {"type": "string", "minLength": 1},
        "body": {"type": "string", "minLength": 1},
        "requires_ack": {"type": "boolean"},
        "deadline": {"type": "string"},
    },
    "required": ["to", "type", "subject", "body"],
    "additionalProperties": False,
}

RING_SCHEMA = {
    "type": "object",
    "properties": {
        "outcome": {"type": "string"},
        "reason": {"type": "string"},
        "target": {"type": "string"},
    },
    "required": ["outcome", "reason", "target"],
    "additionalProperties": False,
}

SEND_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "uri": {"type": "string"},
        "ring": RING_SCHEMA,
    },
    "required": ["id", "uri", "ring"],
    "additionalProperties": False,
}

REPLY_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "action": {"type": "string", "enum": REPLY_ACTION_ENUM},
        "body": {"type": "string", "minLength": 1},
    },
    "required": ["id", "action", "body"],
    "additionalProperties": False,
}

REPLY_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string"},
        "id": {"type": "string"},
        "ring": RING_SCHEMA,
    },
    "required": ["action", "id"],
    "additionalProperties": False,
}

FILE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "minLength": 1},
    },
    "required": ["id"],
    "additionalProperties": False,
}

FILE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "letter": LETTER_REF_SCHEMA,
    },
    "required": ["letter"],
    "additionalProperties": False,
}

SEND_TOOL_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": False,
}

REPLY_TOOL_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": False,
}

# Stage two: freeze annotations now; the tool is not registered in stage one.
FILE_TOOL_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": True,
    "idempotentHint": True,
}

CHECK_TOOL_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}

READ_TOOL_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
