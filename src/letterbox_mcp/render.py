import json

from letterbox_mcp.constants import (
    CHECK_CHAR_CAP,
    CHECK_LETTER_CAP,
    CHECK_TABLE_HEADER,
    DEFAULT_MAX_BODY_CHARS,
)
from letterbox_mcp.mailbox import Letter


def json_string(value: str) -> str:
    """Python JSON string token with ensure_ascii=True, quotes included."""
    return json.dumps(value, ensure_ascii=True)


def completeness_footer(shown: int, remaining: int, truncated: bool) -> str:
    flag = "true" if truncated else "false"
    return f"shown={shown} remaining={remaining} truncated={flag}\n"


def render_check(letters: list[Letter]) -> tuple[list[dict], str, bool, int]:
    """Apply letter and character caps. Rows are atomic. Footer always present."""
    shown: list[Letter] = []
    for letter in letters:
        if len(shown) >= CHECK_LETTER_CAP:
            break
        trial = shown + [letter]
        remaining = len(letters) - len(trial)
        truncated = remaining > 0
        table = _assemble(trial, remaining, truncated)
        if len(table) > CHECK_CHAR_CAP:
            break
        shown = trial
    remaining = len(letters) - len(shown)
    truncated = remaining > 0
    table = _assemble(shown, remaining, truncated)
    return [item.as_ref() for item in shown], table, truncated, remaining


def _assemble(shown: list[Letter], remaining: int, truncated: bool) -> str:
    rows = "".join(_check_row(item) for item in shown)
    footer = completeness_footer(len(shown), remaining, truncated)
    return CHECK_TABLE_HEADER + rows + footer


def _check_row(letter: Letter) -> str:
    ref = letter.as_ref()
    ack = "true" if ref["requires_ack"] else "false"
    deadline = json_string(ref["deadline"])
    return (
        f"{ref['id']} {ref['from']} {ref['type']} {ref['priority']} "
        f"{ack} {deadline} {ref['state']} {ref['age']}\n"
    )


def clip_body(body: str, max_body_chars: int | None) -> tuple[str, bool]:
    cap = DEFAULT_MAX_BODY_CHARS if max_body_chars is None else max_body_chars
    if len(body) <= cap:
        return body, False
    return body[:cap], True
