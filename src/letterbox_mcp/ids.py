import re

from letterbox_mcp.constants import ID_PATTERN, URI_PREFIX

_ID_RE = re.compile(ID_PATTERN)


def is_letter_id(value: str) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if "%" in value:
        return False
    return _ID_RE.fullmatch(value) is not None


def letter_uri(letter_id: str) -> str:
    return f"{URI_PREFIX}{letter_id}"


def parse_letter_uri(uri: str) -> str | None:
    """Return the id only if `uri` is exactly letterbox://letter/<allowlisted-id>.

    Never decode. Never accept a string that would need normalization to match.
    """
    raw = uri if isinstance(uri, str) else str(uri)
    if "%" in raw:
        return None
    if not raw.startswith(URI_PREFIX):
        return None
    ident = raw[len(URI_PREFIX) :]
    if not is_letter_id(ident):
        return None
    if raw != letter_uri(ident):
        return None
    return ident
