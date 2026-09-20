"""Input-side deadline grammar for send. Not used to refuse letters already on disk."""

from __future__ import annotations

import re
from datetime import datetime, timezone

# ASCII digits only. Never \\d — that matches full-width and Arabic-Indic digits.
DEADLINE_LEX = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)
DEADLINE_STRPTIME = "%Y-%m-%dT%H:%M:%SZ"


def validate_send_deadline(value: str, *, type_name: str) -> str | None:
    """Return an error message, or None if the value may reach the CLI."""
    if type_name == "request" and not value:
        return "request requires a non-blank deadline"
    if not value:
        return None
    if DEADLINE_LEX.fullmatch(value) is None:
        return "deadline must be ASCII UTC ISO"
    try:
        parsed = datetime.strptime(value, DEADLINE_STRPTIME).replace(tzinfo=timezone.utc)
    except ValueError:
        return "deadline is not a real instant"
    if parsed.strftime(DEADLINE_STRPTIME) != value:
        return "deadline does not round-trip"
    return None
