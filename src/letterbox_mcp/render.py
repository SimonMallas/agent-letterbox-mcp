from letterbox_mcp.constants import (
    CHECK_CHAR_CAP,
    CHECK_LETTER_CAP,
    CHECK_TABLE_HEADER,
    DEFAULT_MAX_BODY_CHARS,
)
from letterbox_mcp.mailbox import Letter


def render_check(letters: list[Letter]) -> tuple[list[dict], str, bool, int]:
    """Apply letter and character caps. Rows are atomic. Table and refs agree."""
    shown: list[Letter] = []
    table = CHECK_TABLE_HEADER
    for letter in letters:
        if len(shown) >= CHECK_LETTER_CAP:
            remaining = len(letters) - len(shown)
            return [item.as_ref() for item in shown], table, remaining > 0, remaining
        row = _check_row(letter)
        candidate = table + row
        if len(candidate) > CHECK_CHAR_CAP:
            remaining = len(letters) - len(shown)
            return [item.as_ref() for item in shown], table, remaining > 0, remaining
        table = candidate
        shown.append(letter)
    remaining = len(letters) - len(shown)
    return [item.as_ref() for item in shown], table, remaining > 0, remaining


def _check_row(letter: Letter) -> str:
    ref = letter.as_ref()
    return f"{ref['id']} {ref['from']} {ref['state']} {ref['age']}\n"


def clip_body(body: str, max_body_chars: int | None) -> tuple[str, bool]:
    cap = DEFAULT_MAX_BODY_CHARS if max_body_chars is None else max_body_chars
    if len(body) <= cap:
        return body, False
    return body[:cap], True


def envelope_text(ref: dict[str, str]) -> str:
    return (
        f"id: {ref['id']}\n"
        f"from: {ref['from']}\n"
        f"to: {ref['to']}\n"
        f"type: {ref['type']}\n"
        f"state: {ref['state']}\n"
        f"age: {ref['age']}\n"
        f"uri: {ref['uri']}\n"
    )
