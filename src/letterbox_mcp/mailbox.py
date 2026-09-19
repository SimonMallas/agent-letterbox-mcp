"""Descriptor-bound mailbox. Open the box once; letters via O_NOFOLLOW."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from letterbox_mcp.constants import STALE_SECONDS, TYPE_MAX_CODEPOINTS
from letterbox_mcp.ids import is_letter_id, letter_uri

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
    metadata_unrepresentable: bool = False

    def as_ref(self) -> dict[str, str]:
        return {
            "id": self.id,
            "from": self.from_,
            "to": self.to,
            "type": self.type,
            "state": self.state,
            "age": self.age,
            "uri": letter_uri(self.id),
        }


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
) -> Letter | None:
    match = _FRONTMATTER_RE.match(data)
    if not match:
        return None
    header = match.group(1).decode("utf-8", errors="replace")
    body = match.group(2).decode("utf-8", errors="replace")
    fields: dict[str, str] = {}
    for line in _frontmatter_lines(header):
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[_field_strip(key)] = _field_strip(value)
    ident = fields.get("id", "")
    from_ = fields.get("from", "")
    to = fields.get("to", "")
    kind = fields.get("type", "")
    if not is_letter_id(ident) or not from_ or not to:
        return None
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
        metadata_unrepresentable=(
            _metadata_unrepresentable(kind)
            or _metadata_unrepresentable(from_)
            or _metadata_unrepresentable(to)
        ),
    )


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
