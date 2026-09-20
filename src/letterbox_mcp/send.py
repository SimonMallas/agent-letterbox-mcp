"""Send preflight. Fail before the CLI; mailbox stays byte-identical."""

from __future__ import annotations

import re
from pathlib import Path

from letterbox_mcp.constants import TYPE_MAX_CODEPOINTS
from letterbox_mcp.deadline import validate_send_deadline
SENDABLE_TYPES = ("request", "delegate", "status", "blocker", "info")
UNSENDABLE_TYPES = ("ack", "nack", "result")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
AGENT_RE = re.compile(r"^[a-z][a-z0-9-]*$")
ID_MAX = 128
STAMP_LEN = 15  # YYYY-MM-DDTHHMMSS
SUFFIX_LEN = 8


def predicted_id_length(agent: str, type_name: str, subject: str) -> int:
    return STAMP_LEN + 1 + len(agent) + 1 + len(type_name) + 1 + len(subject) + 1 + SUFFIX_LEN


def default_requires_ack(type_name: str) -> bool:
    return type_name in ("request", "delegate")


def preflight_send(
    *,
    root: str,
    agent: str,
    to: str,
    type_name: str,
    subject: str,
    body: str,
    requires_ack: bool | None,
    deadline: str,
) -> str | None:
    if type_name not in SENDABLE_TYPES:
        return "type is not sendable"
    if not body:
        return "body must be non-blank"
    if AGENT_RE.fullmatch(to) is None:
        return "invalid recipient"
    if not (Path(root) / to / "inbox").is_dir():
        return "unknown recipient"
    if SLUG_RE.fullmatch(subject) is None:
        return "subject is not a legal slug"
    if predicted_id_length(agent, type_name, subject) > ID_MAX:
        return "generated id would exceed 128 code points"
    if requires_ack is False and type_name == "delegate":
        return "delegate requires requires_ack true"
    err = validate_send_deadline(deadline, type_name=type_name)
    if err:
        return err
    if len(to) > TYPE_MAX_CODEPOINTS:
        return "invalid recipient"
    return None
