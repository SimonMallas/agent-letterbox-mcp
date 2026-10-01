"""Descriptor-bound mailbox. Open the box once; letters via O_NOFOLLOW."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from letterbox_mcp.constants import (
    BIDI_CONTROL_CHARS,
    ESCAPED_FIELD_MAX,
    PARTICIPANT_PATTERN,
    STALE_SECONDS,
    TYPE_MAX_CODEPOINTS,
)
from letterbox_mcp.ids import is_letter_id, letter_uri

_BIDI_CONTROLS = frozenset(BIDI_CONTROL_CHARS)
_PARTICIPANT_RE = re.compile(PARTICIPANT_PATTERN)

_FRONTMATTER_RE = re.compile(
    rb"\A---\r?\n(.*?)\r?\n---\r?\n?(.*)\Z",
    re.DOTALL,
)
_ISO_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{6})")


@dataclass(frozen=True)
class Letter:
    id: str
    from_: str
    to: str
    type: str
    state: str
    age: str
    body: str
    size_bytes: int
    activity_epoch: int
    stale: bool
    priority: str = ""
    requires_ack: bool = False
    deadline: str = ""
    thread: str = ""
    re: str = ""
    metadata_unrepresentable: bool = False
    duplicate_key: bool = False
    deadline_over_bound: bool = False
    thread_over_bound: bool = False
    re_over_bound: bool = False

    def as_ref(self) -> dict:
        return {
            "id": self.id,
            "from": self.from_,
            "to": self.to,
            "type": self.type,
            "state": self.state,
            "age": self.age,
            "uri": letter_uri(self.id),
            "priority": self.priority,
            "requires_ack": self.requires_ack,
            "deadline": self.deadline,
        }

    def as_envelope(self) -> dict:
        return {**self.as_ref(), "thread": self.thread, "re": self.re}


class Mailbox:
    def __init__(self, root: str, agent: str, now: int | None = None):
        if not agent or "/" in agent or "\\" in agent or agent in (".", "..") or "%" in agent:
            raise ValueError("invalid agent")
        self._root = root
        self._agent = agent
        self._now = now

    def list_open(self) -> list[Letter]:
        letters = self._scan("inbox")
        live = [item for item in letters if not item.stale]
        stale = [item for item in letters if item.stale]
        live.sort(key=lambda item: item.activity_epoch, reverse=True)
        stale.sort(key=lambda item: item.activity_epoch, reverse=True)
        return live + stale

    def get(self, letter_id: str, *, inbox_only: bool = False) -> Letter | None:
        if not is_letter_id(letter_id):
            return None
        folders = ("inbox",) if inbox_only else ("inbox", "processed")
        for folder in folders:
            for item in self._scan(folder):
                if item.id == letter_id:
                    return item
        return None

    def read_file_bytes(self, letter_id: str) -> tuple[int, bytes] | None:
        """Return (size, bytes) for resources/read. None if missing. Never follows links."""
        if not is_letter_id(letter_id):
            return None
        root_fd = None
        try:
            root_fd = _open_dir(self._root)
            agent_fd = None
            try:
                agent_fd = _open_child_dir(root_fd, self._agent)
                for folder in ("inbox", "processed"):
                    found = self._read_named(agent_fd, folder, letter_id)
                    if found is not None:
                        return found
            except OSError:
                return None
            finally:
                _close(agent_fd)
        except OSError:
            return None
        finally:
            _close(root_fd)
        return None

    def _read_named(self, agent_fd: int, folder: str, letter_id: str) -> tuple[int, bytes] | None:
        folder_fd = None
        try:
            folder_fd = _open_child_dir(agent_fd, folder)
            for name in os.listdir(folder_fd):
                if not name.endswith(".md") or name.endswith(".md.ack"):
                    continue
                file_fd = None
                try:
                    file_fd = _open_child_file(folder_fd, name)
                    st = os.fstat(file_fd)
                    data = _read_fd(file_fd)
                except OSError:
                    continue
                finally:
                    _close(file_fd)
                parsed = _parse_letter(
                    data,
                    size_bytes=st.st_size,
                    mtime=int(st.st_mtime),
                    folder=folder,
                    ack_epoch=self._ack_epoch(folder_fd, name),
                    now=self._now_epoch(),
                    filename=name,
                )
                if parsed is not None and parsed.id == letter_id:
                    return (st.st_size, data)
            return None
        except OSError:
            return None
        finally:
            _close(folder_fd)

    def _scan(self, folder: str) -> list[Letter]:
        out: list[Letter] = []
        root_fd = None
        try:
            root_fd = _open_dir(self._root)
            agent_fd = None
            try:
                agent_fd = _open_child_dir(root_fd, self._agent)
                folder_fd = None
                try:
                    folder_fd = _open_child_dir(agent_fd, folder)
                    for name in os.listdir(folder_fd):
                        if not name.endswith(".md") or name.endswith(".md.ack"):
                            continue
                        file_fd = None
                        try:
                            file_fd = _open_child_file(folder_fd, name)
                            st = os.fstat(file_fd)
                            data = _read_fd(file_fd)
                        except OSError:
                            continue
                        finally:
                            _close(file_fd)
                        parsed = _parse_letter(
                            data,
                            size_bytes=st.st_size,
                            mtime=int(st.st_mtime),
                            folder=folder,
                            ack_epoch=self._ack_epoch(folder_fd, name),
                            now=self._now_epoch(),
                            filename=name,
                        )
                        if parsed is not None:
                            out.append(parsed)
                except OSError:
                    return []
                finally:
                    _close(folder_fd)
            except OSError:
                return []
            finally:
                _close(agent_fd)
        except OSError:
            return []
        finally:
            _close(root_fd)
        return out

    def _ack_epoch(self, folder_fd: int, letter_name: str) -> int | None:
        ack_name = letter_name + ".ack"
        fd = None
        try:
            fd = _open_child_file(folder_fd, ack_name)
            data = _read_fd(fd)
        except OSError:
            return None
        finally:
            _close(fd)
        text = data.decode("utf-8", errors="replace")
        best: int | None = None
        for key in ("acked_at", "progress_at"):
            for line in text.splitlines():
                if line.startswith(key + ":"):
                    raw = line.split(":", 1)[1].strip()
                    epoch = _iso_to_epoch(raw)
                    if epoch is not None and (best is None or epoch > best):
                        best = epoch
        return best

    def _now_epoch(self) -> int:
        if self._now is not None:
            return self._now
        return int(datetime.now(timezone.utc).timestamp())


def _open_dir(path: str) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    return os.open(path, flags)


def _open_child_dir(dir_fd: int, name: str) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    return os.open(name, flags, dir_fd=dir_fd)


def _open_child_file(dir_fd: int, name: str) -> int:
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    return os.open(name, flags, dir_fd=dir_fd)


def _close(fd: int | None) -> None:
    if fd is None:
        return
    try:
        os.close(fd)
    except OSError:
        pass


def _read_fd(fd: int) -> bytes:
    chunks: list[bytes] = []
    while True:
        piece = os.read(fd, 65536)
        if not piece:
            break
        chunks.append(piece)
    return b"".join(chunks)


def _parse_letter(
    data: bytes,
    *,
    size_bytes: int,
    mtime: int,
    folder: str,
    ack_epoch: int | None,
    now: int,
    filename: str,
) -> Letter | None:
    match = _FRONTMATTER_RE.match(data)
    if not match:
        return None
    header = match.group(1).decode("utf-8", errors="replace")
    body = match.group(2).decode("utf-8", errors="replace")
    fields: dict[str, str] = {}
    duplicate_key = False
    for line in _frontmatter_lines(header):
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = _field_strip(key)
        value = _field_strip(value)
        if key in fields:
            duplicate_key = True
        fields[key] = value
    file_id = filename[:-3] if filename.endswith(".md") else filename
    ident = fields.get("id", "")
    from_ = fields.get("from", "")
    to = fields.get("to", "")
    kind = fields.get("type", "")
    if duplicate_key:
        ident = file_id if _locator_is_safe(file_id) else ""
    elif not is_letter_id(ident) or not from_ or not to:
        return None
    priority = fields.get("priority", "")
    deadline = fields.get("deadline", "")
    thread = fields.get("thread", "")
    re_field = fields.get("re", "")
    requires_ack = fields.get("requires_ack", "").lower() == "true"
    if folder == "processed":
        state = "processed"
    elif ack_epoch is not None:
        state = "acked"
    else:
        state = "open"
    activity = _letter_epoch(ident, mtime)
    if ack_epoch is not None and ack_epoch > activity:
        activity = ack_epoch
    age_s = max(0, now - activity)
    return Letter(
        id=ident,
        from_=from_,
        to=to,
        type=kind,
        state=state,
        age=_format_age(age_s),
        body=body,
        size_bytes=size_bytes,
        activity_epoch=activity,
        stale=age_s > STALE_SECONDS,
        priority=priority,
        requires_ack=requires_ack,
        deadline=deadline,
        thread=thread,
        re=re_field,
        metadata_unrepresentable=(
            _metadata_unrepresentable(kind)
            or _metadata_unrepresentable(from_)
            or _metadata_unrepresentable(to)
            or _metadata_unrepresentable(priority)
        ),
        duplicate_key=duplicate_key,
        deadline_over_bound=len(deadline) > ESCAPED_FIELD_MAX,
        thread_over_bound=len(thread) > ESCAPED_FIELD_MAX,
        re_over_bound=len(re_field) > ESCAPED_FIELD_MAX,
    )


def _locator_is_safe(ident: str) -> bool:
    return is_letter_id(ident) and not _metadata_unrepresentable(ident)


def duplicate_key_message(letter: Letter) -> str:
    if _locator_is_safe(letter.id):
        return f"duplicate_key on {letter.id}"
    return "duplicate_key on file with invalid id"


def preflight_for_file(letter: Letter) -> str | None:
    """Error text if file must refuse without mutating; None if the CLI may run."""
    if letter.duplicate_key:
        return duplicate_key_message(letter)
    if letter.from_ == "telegram-bridge":
        return f"relay letter: reply with alb --reply-to {letter.id} (the bus cannot transmit)"
    if letter.metadata_unrepresentable:
        return f"unrepresentable metadata on {letter.id}"
    if letter.deadline_over_bound:
        return f"deadline exceeds 256 code points on {letter.id}"
    return None


def preflight_for_reply(
    letter: Letter, *, root: str, agent: str, action: str
) -> str | None:
    """Validate fields reply uses or the CLI copies. Not to, priority, or deadline."""
    if letter.duplicate_key:
        return duplicate_key_message(letter)
    if letter.from_ == "telegram-bridge":
        return f"relay letter: reply with alb --reply-to {letter.id} (the bus cannot transmit)"
    if not _participant_name_ok(letter.from_):
        return f"unrepresentable metadata on {letter.id}"
    if not _participant_inbox_real(root, letter.from_):
        return f"unrepresentable metadata on {letter.id}"
    if letter.thread and letter.thread_over_bound:
        return f"thread exceeds 256 code points on {letter.id}"
    derived = f"{letter.id}--{agent}--{action}"
    if not is_letter_id(derived):
        return f"derived reply id would fail grammar on {letter.id}"
    return None


def _participant_name_ok(name: str) -> bool:
    if _PARTICIPANT_RE.fullmatch(name) is None:
        return False
    if _metadata_unrepresentable(name):
        return False
    return True


def _participant_inbox_real(root: str, name: str) -> bool:
    """Open participant/inbox relative to the mailbox fd with O_NOFOLLOW."""
    root_fd = None
    try:
        root_fd = _open_dir(root)
        agent_fd = None
        try:
            agent_fd = _open_child_dir(root_fd, name)
            inbox_fd = None
            try:
                inbox_fd = _open_child_dir(agent_fd, "inbox")
            except OSError:
                return False
            finally:
                _close(inbox_fd)
        except OSError:
            return False
        finally:
            _close(agent_fd)
    except OSError:
        return False
    finally:
        _close(root_fd)
    return True


def derived_reply_path(root: str, letter: Letter, agent: str, action: str) -> Path | None:
    name = f"{letter.id}--{agent}--{action}.md"
    origin = letter.from_
    if not origin or "/" in origin or origin in (".", ".."):
        return None
    for folder in ("inbox", "processed"):
        path = Path(root) / origin / folder / name
        if path.is_file():
            return path
    return None


def derived_reply_body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) < 3:
        return ""
    return parts[2].lstrip("\n").rstrip("\n")


def _frontmatter_lines(header: str) -> list[str]:
    """Split on \\n / \\r\\n only. Unicode line boundaries stay inside the field."""
    return header.replace("\r\n", "\n").split("\n")


def _field_strip(value: str) -> str:
    """Strip ASCII space and tab only, so C0/C1 in the value are preserved."""
    return value.strip(" \t")


def _metadata_unrepresentable(value: str) -> bool:
    if len(value) > TYPE_MAX_CODEPOINTS:
        return True
    for char in value:
        code = ord(char)
        if code <= 0x1F or 0x7F <= code <= 0x9F:
            return True
        if char in "\u2028\u2029":
            return True
        if char in _BIDI_CONTROLS:
            return True
    return False


def _letter_epoch(ident: str, mtime: int) -> int:
    match = _ISO_PREFIX_RE.match(ident)
    if match:
        epoch = _compact_to_epoch(match.group(1))
        if epoch is not None:
            return epoch
    return mtime


def _compact_to_epoch(stamp: str) -> int | None:
    try:
        dt = datetime.strptime(stamp, "%Y-%m-%dT%H%M%S").replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except ValueError:
        return None


def _iso_to_epoch(raw: str) -> int | None:
    raw = raw.strip()
    compact = raw.replace(":", "")
    if compact.endswith("Z"):
        compact = compact[:-1]
    if len(compact) >= 15 and compact[10] == "T":
        return _compact_to_epoch(compact[:15])
    return None


def _format_age(sec: int) -> str:
    if sec < 3600:
        return f"{sec // 60}m"
    if sec < 86400:
        return f"{sec // 3600}h"
    return f"{sec // 86400}d"
