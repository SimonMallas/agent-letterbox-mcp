from letterbox_mcp.cli import run_cli


def test_unset_letterbox_cli_refuses_without_live_fallback(monkeypatch, tmp_path):
    monkeypatch.delenv("LETTERBOX_CLI", raising=False)

    result = run_cli(str(tmp_path), "desktop", ["file", "any-id"])

    assert result.ok is False
    assert result.stderr == "LETTERBOX_CLI must be explicitly configured"
    assert result.stdout == ""
