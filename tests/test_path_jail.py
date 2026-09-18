import os

from letterbox_mcp.ids import parse_letter_uri
from tests.harness import AGENT, write_letter

JAIL_BODY = "JAIL_TARGET_BODY"


def _init(client):
    client.initialize()


def _target_x(mailbox):
    write_letter(mailbox, "x", JAIL_BODY, type_name="info")


def _assert_refused(resp: dict) -> None:
    assert "error" in resp
    assert resp["error"]["code"] == -32002
    data = resp["error"]["data"]
    assert data["reason"] == "not_found"
    assert "size_bytes" not in data
    dumped = str(resp)
    assert JAIL_BODY not in dumped
    assert "/inbox/" not in dumped
    assert "processed/" not in dumped


def test_parse_letter_uri_rejects_traversal_on_raw_string():
    assert parse_letter_uri("letterbox://letter/x") == "x"
    assert parse_letter_uri("letterbox://letter/../x") is None
    assert parse_letter_uri("letterbox://letter/./x") is None
    assert parse_letter_uri("letterbox://letter/%2e%2e%2f") is None
    assert parse_letter_uri("file:///etc/passwd") is None


def test_jail_dotdot_with_real_target(client, mailbox):
    _target_x(mailbox)
    _init(client)
    served = client.request("resources/read", {"uri": "letterbox://letter/x"})
    assert JAIL_BODY in served["result"]["contents"][0]["text"]
    _assert_refused(client.request("resources/read", {"uri": "letterbox://letter/../x"}))
    tool = client.request("tools/call", {"name": "letterbox_read", "arguments": {"id": "../x"}})
    assert tool["result"]["isError"] is True
    assert JAIL_BODY not in str(tool)


def test_jail_percent_encoded_with_real_target(client, mailbox):
    _target_x(mailbox)
    _init(client)
    _assert_refused(client.request("resources/read", {"uri": "letterbox://letter/%2e%2e%2f"}))
    tool = client.request("tools/call", {"name": "letterbox_read", "arguments": {"id": "%2e%2e%2f"}})
    assert tool["result"]["isError"] is True
    assert JAIL_BODY not in str(tool)


def test_jail_file_uri_with_real_target(client, mailbox):
    _target_x(mailbox)
    _init(client)
    _assert_refused(client.request("resources/read", {"uri": "file:///etc/passwd"}))
    tool = client.request("tools/call", {"name": "letterbox_read", "arguments": {"id": "file:///etc/passwd"}})
    assert tool["result"]["isError"] is True
    assert JAIL_BODY not in str(tool)
    assert "root:" not in str(tool)


def test_jail_symlink_out(client, mailbox, tmp_path):
    outside = tmp_path / "outside-secret.md"
    outside.write_text("SECRET_OUTSIDE_BODY\n", encoding="utf-8")
    inbox = mailbox / AGENT / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    os.symlink(outside, inbox / "x.md")
    _init(client)
    resp = client.request("resources/read", {"uri": "letterbox://letter/x"})
    _assert_refused(resp)
    assert "SECRET_OUTSIDE_BODY" not in str(resp)
    tool = client.request("tools/call", {"name": "letterbox_read", "arguments": {"id": "x"}})
    assert tool["result"]["isError"] is True
    assert "SECRET_OUTSIDE_BODY" not in str(tool)
