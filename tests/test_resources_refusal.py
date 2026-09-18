from tests.harness import sized_letter


def _init(client):
    client.initialize()


def test_resources_list_empty(client, mailbox):
    _init(client)
    listed = client.request("resources/list")
    assert listed["result"]["resources"] == []


def test_templates_list_single(client, mailbox):
    _init(client)
    listed = client.request("resources/templates/list")
    templates = listed["result"]["resourceTemplates"]
    assert len(templates) == 1
    assert templates[0]["uriTemplate"] == "letterbox://letter/{id}"


def test_too_large_and_not_found_shapes_differ(client, mailbox):
    over_id = "2026-09-18T120000-beta-info-oversize1"
    under_id = "2026-09-18T120000-beta-info-underceil"
    sized_letter(mailbox, under_id, 1048576)
    sized_letter(mailbox, over_id, 1048577)
    _init(client)

    under = client.request("resources/read", {"uri": f"letterbox://letter/{under_id}"})
    assert "result" in under
    assert under["result"]["contents"]
    text = under["result"]["contents"][0]["text"]
    assert isinstance(text, str)

    over = client.request("resources/read", {"uri": f"letterbox://letter/{over_id}"})
    err = over["error"]
    assert err["code"] == -32000
    data = err["data"]
    assert data["reason"] == "too_large"
    assert data["size_bytes"] == 1048577
    assert data["limit_bytes"] == 1048576
    assert set(data) == {"uri", "reason", "size_bytes", "limit_bytes"}
    assert str(mailbox) not in str(over)
    assert "result" not in over

    missing = client.request("resources/read", {"uri": "letterbox://letter/2026-09-18T120000-beta-info-missing1"})
    err2 = missing["error"]
    assert err2["code"] == -32002
    data2 = err2["data"]
    assert data2["reason"] == "not_found"
    assert "size_bytes" not in data2
    assert "limit_bytes" not in data2
    assert set(data2) == {"uri", "reason"}
    assert err["code"] != err2["code"]
    assert str(mailbox) not in str(missing)
    assert "contents" not in missing.get("result", {})
