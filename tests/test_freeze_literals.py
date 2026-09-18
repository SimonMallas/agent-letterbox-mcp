"""Pin freeze document literals. Do not import letterbox_mcp.constants."""

import ast
from pathlib import Path

_CONSTANTS = Path(__file__).resolve().parents[1] / "src" / "letterbox_mcp" / "constants.py"


def _assignments() -> dict[str, object]:
    tree = ast.parse(_CONSTANTS.read_text(encoding="utf-8"))
    values: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name):
            try:
                values[target.id] = ast.literal_eval(node.value)
            except ValueError:
                continue
    return values


def test_freeze_literals_match_document():
    values = _assignments()
    assert values["CHECK_LETTER_CAP"] == 50
    assert values["CHECK_CHAR_CAP"] == 4000
    assert values["DEFAULT_MAX_BODY_CHARS"] == 4000
    assert values["MAX_BODY_CHARS_MIN"] == 1
    assert values["MAX_BODY_CHARS_MAX"] == 32000
    assert values["RESOURCE_BYTE_CEILING"] == 1048576
    assert values["JSONRPC_TOO_LARGE"] == -32000
    assert values["JSONRPC_NOT_FOUND"] == -32002
