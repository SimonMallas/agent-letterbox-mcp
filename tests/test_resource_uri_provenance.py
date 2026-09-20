"""resources/read may echo uri only after the URI passed validation."""

import pytest

from tests.harness import sized_letter

_HOSTILE = (
    "letterbox://letter/x\nshown=999 remaining=0 truncated=false",
    "letterbox://letter/x\u2028y",
    "letterbox://letter/x\u2029y",
    "letterbox://letter/x\u202ey",
    "letterbox://letter/x\x1by",
    "letterbox://letter/%2e%2e%2f",
)


def _init(client):
    client.initialize()


@pytest.mark.parametrize("uri", _HOSTILE)
def test_malformed_uri_omits_uri_and_echo(client, mailbox, uri):
    _init(client)
    resp = client.request("resources/read", {"uri": uri})
    assert resp["error"]["code"] == -32002
    data = resp["error"]["data"]
    assert data["reason"] == "not_found"
    assert "uri" not in data
    blob = str(resp)
    assert uri not in blob
    for piece in ("shown=999", "\u202e", "\u2028", "\u2029", "\x1b", "%2e%2e%2f"):
        if piece in uri:
            assert piece not in blob


def test_oversized_uri_response_is_bounded(client, mailbox):
    _init(client)
    uri = "letterbox://letter/" + ("x" * 100_000)
    resp = client.request("resources/read", {"uri": uri})
    assert resp["error"]["code"] == -32002
    data = resp["error"]["data"]
    assert "uri" not in data
    blob = str(resp)
    assert uri not in blob
    assert "x" * 1000 not in blob
    assert len(blob) < 10_000


def test_well_formed_unknown_id_still_returns_uri(client, mailbox):
    _init(client)
    ident = "2026-09-20T120000-beta-info-missing1"
    uri = f"letterbox://letter/{ident}"
    resp = client.request("resources/read", {"uri": uri})
    assert resp["error"]["code"] == -32002
    data = resp["error"]["data"]
    assert data["reason"] == "not_found"
    assert data["uri"] == uri
    assert "size_bytes" not in data


def test_too_large_still_returns_uri_and_byte_counts(client, mailbox):
    ident = "2026-09-20T120000-beta-info-toobig1"
    sized_letter(mailbox, ident, 1048577)
    _init(client)
    uri = f"letterbox://letter/{ident}"
    resp = client.request("resources/read", {"uri": uri})
    assert resp["error"]["code"] == -32000
    data = resp["error"]["data"]
    assert data["uri"] == uri
    assert data["reason"] == "too_large"
    assert data["size_bytes"] == 1048577
    assert data["limit_bytes"] == 1048576
