from letterbox_mcp.mailbox import Mailbox, preflight_for_file
from tests.conftest import live_id
from tests.harness import AGENT, write_letter


def _snapshot(mailbox):
    return {
        path.relative_to(mailbox): path.read_bytes()
        for path in mailbox.rglob("*")
        if path.is_file()
    }


def test_file_preflight_deadline_over_256_does_not_mutate(mailbox):
    ident = live_id("filedl")
    write_letter(mailbox, ident, "x", deadline="d" * 257)
    before = _snapshot(mailbox)
    box = Mailbox(str(mailbox), AGENT)
    letter = box.get(ident, inbox_only=True)
    assert letter is not None
    err = preflight_for_file(letter)
    assert err is not None
    assert ident in err
    assert _snapshot(mailbox) == before


def test_file_preflight_priority_rlo_does_not_mutate(mailbox):
    ident = live_id("filerlo")
    write_letter(mailbox, ident, "x", priority="ab\u202ecd")
    before = _snapshot(mailbox)
    box = Mailbox(str(mailbox), AGENT)
    letter = box.get(ident, inbox_only=True)
    assert letter is not None
    err = preflight_for_file(letter)
    assert err is not None
    assert ident in err
    assert _snapshot(mailbox) == before


def test_file_preflight_duplicate_key_does_not_mutate(mailbox):
    ident = live_id("filedup")
    inbox = mailbox / AGENT / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / f"{ident}.md").write_text(
        f"---\nid: {ident}\nfrom: beta\nfrom: pi\nto: {AGENT}\ntype: info\n---\n",
        encoding="utf-8",
    )
    before = _snapshot(mailbox)
    box = Mailbox(str(mailbox), AGENT)
    letter = box.get(ident, inbox_only=True)
    assert letter is not None
    err = preflight_for_file(letter)
    assert err is not None
    assert "duplicate_key" in err
    assert _snapshot(mailbox) == before
