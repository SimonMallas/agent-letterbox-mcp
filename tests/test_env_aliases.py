"""Resolve public Letterbox names first; legacy bus names are explicit fallback only."""
from unittest.mock import patch

import pytest

from letterbox_mcp import __main__ as entry


@pytest.mark.parametrize(
    "env,argv,expected,warnings",
    [
        ({"LETTERBOX_DIR": "/public", "LETTERBOX_AGENT": "alpha",
          "BUS_DIR": "/private", "BUS_AGENT": "beta"}, [], ("/public", "alpha"), False),
        ({"BUS_DIR": "/private", "BUS_AGENT": "beta"}, [], ("/private", "beta"), True),
        ({"BUS_DIR": "/private", "BUS_AGENT": "beta"},
         ["--mailbox", "/explicit", "--agent", "alpha"], ("/explicit", "alpha"), False),
    ],
)
def test_env_precedence_and_deprecated_fallback(monkeypatch, capsys, env, argv, expected, warnings):
    for name in ("LETTERBOX_DIR", "LETTERBOX_AGENT", "BUS_DIR", "BUS_AGENT"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    with patch.object(entry, "Mailbox", side_effect=lambda root, agent: (root, agent)) as mailbox, \
         patch.object(entry, "run_stdio", new=lambda mailbox: None), \
         patch.object(entry.asyncio, "run"):
        entry.main(argv)
    assert mailbox.call_args.args == expected
    stderr = capsys.readouterr().err
    assert ("is deprecated" in stderr) is warnings
    assert "/private" not in stderr and "/public" not in stderr


def test_no_ambient_root_or_agent_refuses(monkeypatch, capsys):
    for name in ("LETTERBOX_DIR", "LETTERBOX_AGENT", "BUS_DIR", "BUS_AGENT"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SystemExit, match="2"):
        entry.main([])
    assert "required" in capsys.readouterr().err
