"""The model's answers to the variant-pair question, kept on disk for every book and run.

classify_pair (proofread_pages.py) asks the model whether two characters are
one character written two ways: each pair in both orders, and a third time on
disagreement.  Measured on one 488-page book: the book profile spent about 76
of its 99 minutes on these questions (515 pairs, 1,000 or more calls), and the
answers were kept only in the process's memory, so every book and every
re-profile asked them again.  Of the pairs the calibration corpus's seven books
sent to the model, 14 to 22% had been asked by another book (by the books
before it, or by all six others), and each of the five re-profiled books had
asked all of its pairs before (the profiles' pairClasses).

This store keeps each complete answer, one question (a pair in one order, and
which time it is asked in the procedure) per record, under a key that holds
everything the answer depends on:

- the request as the client sends it: the model id, the prompt text, the
  effort, the token limit, the sampling settings;
- how the client retries: its effort ladder, the kind's own budget, the code
  of its retrying method as the process runs it (its docstring, comments and
  line numbers aside), and switch R2-C's cap on the kind's first rung
  (--top-rung-caps, the client's top_rung_caps), where there is one: under the
  cap a lower rung answers what the first rung would have answered past it, so
  an answer kept under one cap is not another's, nor the answer without one;
  and so, for the same reason, the loop detector's rule (--loop-detector, the
  client's loop_detector), which also streams the request (in the request
  above);
- the server: the process listening on the endpoint's port on this machine, by
  its command line and the SHA-256 of its executable and of every file its
  command line names.  Those files must include one of WEIGHTS_MIN_BYTES or
  more, taken to be the model's weights: a process that names none (a
  forwarder on the port, such as ssh -L, socat or a container's proxy, or a
  server that finds its model by name or in its own configuration) does not
  say which model answers, so the store is not used with it.  The hash of a
  large file is kept beside the store under the file's device, inode, size,
  modification and change times, and a file changed since the server started
  (so the server may hold other contents than the disk) or while it runs
  leaves the store unused.  So does a path on the command line that may have
  led to another file when the server started: a link on it re-pointed, or a
  directory on it renamed or put in place, since (named_file).  A server that
  is not a process of this machine cannot be checked, so the store is not used
  with it.  PAIR_CACHE_MODEL_TAG, when set, is part of the key too: a way to
  start afresh when something the key cannot see changed.

Only complete answers are kept: not a reply cut off on every effort
(degraded), not an empty one, not one without the verdict line, not a failed
call.  And only answers that came over HTTP from the server the key names
(Heard): the real transport (proofread_pages.Client._send, after urlopen
returned) shows the store each response it read and the other end of the
connection it came on, and an answer is kept only when it is the last of those
responses, every response the client read on the way (a ladder's rungs) came
the same way, and the connection was to the endpoint's port on this machine.
Found on 2026-09-29 in this machine's store: 20 answers 「判定：不同」 kept
under the model server's identity by an offline replay, whose stand-in client
named the endpoint the server listened on.  The store identified the server
from /proc and kept what the stand-in answered, where a later real run would
have read it as the model's.  A stand-in client or transport (a Client whose
_send is replaced, as the checks' are), a stand-in for urlopen, a proxy or a
redirect to another port shows the store no such response, and the question is
asked as always with nothing kept (tests/check_pair_cache.py).  Nor is an
answer kept that the transport read but that was changed since, or that
answered a request other than the one the key holds (a hooked transport
sending another prompt, model or sampling to the live server), or that came
while the process the key names no longer held the port (it stopped
listening or exec()ed another program; LocalServer).  Records of schema 1,
kept without any of this (and still written by older checkouts), are never
read (SCHEMA).  Nothing is ever rewritten: records are appended,
one line each, under an exclusive lock, each with the SHA-256 of its own
content, so a line cut short by a crash is skipped and several processes can
write at once.

The default store is ~/.cache/jyut-ocr/pair-class.jsonl (PAIR_CACHE_PATH
overrides it).
"""
from __future__ import annotations

from collections import Counter
import contextlib
import contextvars
from datetime import datetime, timezone
import dis
import errno
import fcntl
import functools
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import stat as file_type
import threading
from types import CodeType
from typing import Any, Callable, Iterator, Mapping
import urllib.parse

# 2 (2026-09-29): answers kept only when heard over HTTP (Heard).  Every
# schema-1 record was kept without that proof, some of them a stand-in's (the
# 20 found that day), and the code that keeps them still runs in the older
# checkouts beside this one, whose checks write the default store: a key of
# schema 1 is never looked up, so none of them is read.
SCHEMA = 2
DEFAULT_PATH = "~/.cache/jyut-ocr/pair-class.jsonl"
PATH_ENV = "PAIR_CACHE_PATH"
TAG_ENV = "PAIR_CACHE_MODEL_TAG"
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
# A file changed less than this long before the server's start, as read from
# /proc (the boot time there is whole seconds, the start in clock ticks), may
# have changed after it: such a server is not trusted.
START_SLACK_NS = 1_000_000_000
HASH_CHUNK = 8 * 1024 * 1024
# The server's command line must name a file at least this large, taken to be
# the model's weights: a model that can answer the pair question is hundreds of
# megabytes or more (a 0.5B-parameter model at 4 bits is about 400 MB), while a
# configuration file, a script, a key or a tokenizer is a few megabytes.  A
# forwarder (ssh -L, socat, a container's proxy) or a server that finds its
# model by name or in its configuration names no such file, and the identity
# would then leave the model out: another model behind the same command line
# would get this one's answers.
WEIGHTS_MIN_BYTES = 64 * 1024 * 1024


def default_path() -> Path:
    return Path(os.environ.get(PATH_ENV) or DEFAULT_PATH).expanduser()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


class JsonLines:
    """An append-only file of JSON records, one per line, each sealed with the
    SHA-256 of its payload.  Appends hold an exclusive flock and are synced;
    reads take only whole lines whose seal holds."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.offset = 0
        self.inode: int | None = None

    def append(self, payload: Mapping[str, Any]) -> None:
        line = canonical({"payload": payload, "sha256": digest(payload)}) + b"\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            size = os.fstat(fd).st_size
            if size and os.pread(fd, 1, size - 1) != b"\n":
                # A writer died mid-line: the next record starts a line of its own.
                line = b"\n" + line
            view = memoryview(line)
            while view:
                view = view[os.write(fd, view):]
            os.fsync(fd)
        finally:
            os.close(fd)

    def read_new(self) -> list[dict[str, Any]]:
        """The records appended since the last read; every record on the first."""
        try:
            fd = os.open(self.path, os.O_RDONLY)
        except FileNotFoundError:
            return []
        try:
            fcntl.flock(fd, fcntl.LOCK_SH)
            stat = os.fstat(fd)
            if stat.st_ino != self.inode or stat.st_size < self.offset:
                self.inode, self.offset = stat.st_ino, 0
            chunks, at = [], self.offset
            while at < stat.st_size:
                chunk = os.pread(fd, min(HASH_CHUNK, stat.st_size - at), at)
                if not chunk:
                    break
                chunks.append(chunk)
                at += len(chunk)
        finally:
            os.close(fd)
        data = b"".join(chunks)
        whole = data.rfind(b"\n") + 1      # a line still being written waits
        self.offset += whole
        out = []
        for raw in data[:whole].split(b"\n"):
            try:
                record = json.loads(raw)
                if record["sha256"] == digest(record["payload"]):
                    out.append(record["payload"])
            except (ValueError, KeyError, TypeError):
                continue
        return out

    @contextlib.contextmanager
    def exclusive(self) -> Iterator[None]:
        """One process at a time (a lock file beside the records)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(str(self.path) + ".lock", "a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield


def stamp(path: str) -> list[int]:
    stat = os.stat(path)
    return [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]


class FileHashes:
    """SHA-256 of files, read once per version of a file: kept under the path
    and its stamp (device, inode, size, modification and change times; the
    change time is the kernel's, which no program sets)."""

    def __init__(self, path: Path):
        self.lines = JsonLines(path)
        self.known: dict[str, str] = {}
        self.lock = threading.Lock()

    def sha256(self, path: str) -> str:
        before = stamp(path)
        key = digest([path, before])
        with self.lock:
            self._load()
            if key in self.known:
                return self.known[key]
            with self.lines.exclusive():
                self._load()
                if key not in self.known:
                    hasher = hashlib.sha256()
                    with open(path, "rb") as handle:
                        for chunk in iter(lambda: handle.read(HASH_CHUNK), b""):
                            hasher.update(chunk)
                    if stamp(path) != before:
                        raise OSError(f"{path} changed while it was read")
                    self.lines.append({"type": "file", "key": key, "path": path, "stamp": before,
                                       "sha256": hasher.hexdigest(), "at": utc_now()})
                    self.known[key] = hasher.hexdigest()
            return self.known[key]

    def _load(self) -> None:
        for record in self.lines.read_new():
            if record.get("type") == "file":
                self.known.setdefault(record["key"], record["sha256"])


def listening_sockets(port: int) -> set[str]:
    """The listening TCP sockets on PORT (any address), as /proc/PID/fd names
    them (socket:[inode])."""
    inodes = set()
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            rows = Path(table).read_text().splitlines()[1:]
        except OSError:
            continue
        for row in rows:
            fields = row.split()
            if len(fields) > 9 and fields[3] == "0A" and int(fields[1].rsplit(":", 1)[1], 16) == port:
                inodes.add(f"socket:[{fields[9]}]")
    return inodes


def holds(pid: int, sockets: set[str]) -> bool:
    """Whether process PID holds one of SOCKETS."""
    for descriptor in os.listdir(f"/proc/{pid}/fd"):
        try:
            if os.readlink(f"/proc/{pid}/fd/{descriptor}") in sockets:
                return True
        except OSError:
            continue
    return False


def listening_pids(port: int, inodes: set[str] | None = None) -> set[int]:
    """The processes holding a listening TCP socket on PORT (any address)."""
    inodes = listening_sockets(port) if inodes is None else inodes
    pids = set()
    if not inodes:
        return pids
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        try:
            descriptors = os.listdir(f"/proc/{name}/fd")
        except OSError:
            continue
        for descriptor in descriptors:
            try:
                if os.readlink(f"/proc/{name}/fd/{descriptor}") in inodes:
                    pids.add(int(name))
                    break
            except OSError:
                continue
    return pids


def process_ticks(pid: int) -> int:
    """A process's start, in clock ticks since boot (field 22 of proc(5))."""
    return int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19])


@functools.lru_cache(maxsize=None)
def boot_time() -> int:
    return next(int(line.split()[1]) for line in Path("/proc/stat").read_text().splitlines()
                if line.startswith("btime "))


def process_start_ns(pid: int) -> tuple[int, int]:
    """(start time in ns since the epoch, start in clock ticks since boot)."""
    ticks = process_ticks(pid)
    return boot_time() * 1_000_000_000 + ticks * 1_000_000_000 // os.sysconf("SC_CLK_TCK"), ticks


def command_files(argv: list[str], cwd: str, since: int) -> tuple[list[str], str | None]:
    """The regular files a command line names (a --flag=value's value too), as
    the process met them when it started (SINCE, ns since the epoch; see
    named_file), or why they cannot be told: a directory, whose contents are
    not checked, or a path that may have led elsewhere then."""
    files = []
    for token in argv[1:]:
        value = token.split("=", 1)[1] if token.startswith("-") and "=" in token else token
        if not value or value.startswith("-"):
            continue
        path, reason = named_file(value, cwd, since)
        if reason:
            return [], reason
        if path is not None:
            files.append(path)
    return files, None


MAX_LINKS = 40


def named_file(value: str, cwd: str, since: int) -> tuple[str | None, str | None]:
    """The regular file that VALUE, a word of a server's command line, names
    now and named when the server started (SINCE, ns since the epoch): (its
    path, None); (None, None) when it names no regular file; (None, why) when
    that cannot be told.

    The path is followed one name at a time, from the server's working
    directory CWD or from the root, through every link, as the kernel follows
    it.  A file's own change time says only that its contents are the ones the
    server read, not that the path led to it then: a link re-pointed while the
    server ran (current -> v2 put in place of current -> v1), or a directory
    renamed into the path, leads to other weights than the server loaded, whose
    change time is old.  So each name on the way must be bound as it was when
    the server started: either the directory holding it has not changed since
    (no name in it was added, removed or re-pointed), or what the name leads to
    has not changed since (making a name lead somewhere - creating the file, the
    directory or the link, renaming it there, linking it - sets the change time
    of what it leads to; checked here for a rename on ext4 and tmpfs, and a
    filesystem that did not would let a renamed directory through).  A name
    that fails both may have been bound after the server started.  A mount made
    over the path after the server started changes no change time and is not
    seen.

    A path (a word with a directory in it) that leads nowhere now is no file
    only if the directory where it breaks has not changed since the server
    started; otherwise the file may have been moved away since, and that
    cannot be told."""
    path_like = os.sep in value
    value = os.path.expanduser(value)
    here = os.sep if os.path.isabs(value) else cwd
    names = [name for name in value.split(os.sep) if name and name != os.curdir]
    links = 0
    while names:
        name = names.pop(0)
        step = os.path.dirname(here) if name == os.pardir else os.path.join(here, name)
        held = os.stat(here).st_ctime_ns < since
        try:
            info = os.lstat(step)
        except NotADirectoryError:                    # a name inside a file: none
            return None, None
        except FileNotFoundError:
            # Missing now.  If its directory has not changed since the server
            # started, it was missing then too: the word is not a file (a model
            # name, org/name).  Otherwise it may have named a file the server
            # read that has been moved or removed since, whose contents the key
            # would leave out - unless the word has no directory in it, which
            # cannot be told from a name (a model id, a number): the server's
            # working directory changes as any directory does.  If such a word
            # named the only weights, the command line is left without weights
            # and is not trusted for that.
            if held or not path_like:
                return None, None
            return None, (f"{step} is missing and {here} changed after the server started, so the server's "
                          f"command line ({value}) may have named a file since moved or removed")
        except OSError as error:
            if error.errno == errno.ENAMETOOLONG:     # no file has such a name
                return None, None
            raise
        if not held and info.st_ctime_ns >= since:
            return None, (f"{step} was put in place or changed after the server started, so the server's "
                          f"command line ({value}) may have led to another file when the server read it")
        if file_type.S_ISLNK(info.st_mode):
            links += 1
            if links > MAX_LINKS:
                return None, f"the server's command line names a path through more than {MAX_LINKS} links ({value})"
            target = os.readlink(step)
            if os.path.isabs(target):
                here = os.sep
            names[:0] = [name for name in target.split(os.sep) if name and name != os.curdir]
            continue
        here = step
    mode = os.stat(here).st_mode
    if file_type.S_ISREG(mode):
        return here, None
    if file_type.S_ISDIR(mode) and path_like:
        return None, f"the server's command line names a directory ({value}), whose contents are not checked"
    return None, None


def same_file(a: str, b: str) -> bool:
    try:
        first, second = os.stat(a), os.stat(b)
    except OSError:
        return False
    return (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino)


class LocalServer:
    """The identity of the server behind an endpoint: a process of this machine
    listening on its port, by its command line and the SHA-256 of its
    executable and of every file the command line names, one of them of
    WEIGHTS_MIN_BYTES or more (the weights).  Worked out once and re-checked
    on every use, before a question and after its answer: the process's start,
    its command line and executable (a process that exec()s another program
    keeps its start and its sockets), the listening sockets on the port and
    that the process holds them (a server that stops listening but lives on,
    another on the port since), and the files' stamps.  A process that
    listens on the port itself (on another loopback address) is not trusted:
    an answer on the port may then be its own."""

    def __init__(self, hashes: FileHashes, tag: str | None):
        self.hashes = hashes
        self.tag = tag
        self.lock = threading.Lock()
        self.known: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}

    def __call__(self, client: Any) -> tuple[dict[str, Any] | None, str | None]:
        endpoint = getattr(client, "endpoint", None)
        if not isinstance(endpoint, str):
            return None, "the client names no endpoint"
        with self.lock:
            held = self.known.get(endpoint)
            if held is not None and self.unchanged(held[1]):
                return held[0], None
            self.known.pop(endpoint, None)
            try:
                identity, watch, reason = self.identify(endpoint)
            except OSError as error:
                return None, f"the server could not be checked: {error}"
            if identity is None:
                return None, reason
            self.known[endpoint] = (identity, watch)
            return identity, None

    def identify(self, endpoint: str) -> tuple[dict[str, Any] | None, dict[str, Any], str | None]:
        parts = urllib.parse.urlsplit(endpoint)
        if parts.hostname not in LOOPBACK:
            return None, {}, f"the server ({parts.hostname}) is not on this machine, so it cannot be checked"
        port = parts.port or (443 if parts.scheme == "https" else 80)
        sockets = listening_sockets(port)
        pids = listening_pids(port, sockets)
        if os.getpid() in pids:
            return None, {}, (f"this process listens on port {port} too (another loopback address), so an "
                              "answer on the port may be its own")
        if len(pids) != 1:
            return None, {}, (f"{'no process' if not pids else 'more than one process'} of this user "
                              f"listens on port {port}")
        pid = pids.pop()
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
        argv = cmdline.decode("utf-8", "replace").rstrip("\0").split("\0")
        executable = os.readlink(f"/proc/{pid}/exe")
        if executable.endswith(" (deleted)"):
            return None, {}, "the server's executable was replaced after it started"
        started, ticks = process_start_ns(pid)
        # The server's paths are followed here as the server followed them: from
        # the same root, through the same mounts, from its working directory.
        cwd = os.readlink(f"/proc/{pid}/cwd")
        if (os.readlink(f"/proc/{pid}/root") != os.sep
                or os.readlink(f"/proc/{pid}/ns/mnt") != os.readlink("/proc/self/ns/mnt")
                or not same_file(cwd, f"/proc/{pid}/cwd")):
            return None, {}, ("the server sees other files than this process (another root or other mounts), "
                              "or its working directory was removed")
        files, reason = command_files(argv, cwd, started - START_SLACK_NS)
        if reason:
            return None, {}, reason
        if not any(os.stat(path).st_size >= WEIGHTS_MIN_BYTES for path in files):
            return None, {}, (f"the server's command line names no file of {WEIGHTS_MIN_BYTES >> 20} MiB or more "
                              "(its weights), so which model answers cannot be checked: a forwarder on the port, "
                              "or a server that finds its model by name or in its own configuration")
        stamps = {}
        for path in [os.path.realpath(executable), *files]:
            stamps[path] = stamp(path)
            if stamps[path][4] >= started - START_SLACK_NS:
                return None, {}, f"{path} changed after the server started, so the server may hold other contents"
        sha = {path: self.hashes.sha256(path) for path in stamps}
        if any(stamp(path) != value for path, value in stamps.items()):
            return None, {}, "a server file changed while it was read"
        identity = {"argv": argv, "executable": os.path.realpath(executable), "sha256": sha,
                    **({"tag": self.tag} if self.tag else {})}
        return identity, {"pid": pid, "ticks": ticks, "stamps": stamps, "cmdline": cmdline, "exe": executable,
                          "port": port, "sockets": sockets}, None

    @staticmethod
    def unchanged(watch: Mapping[str, Any]) -> bool:
        try:
            pid = watch["pid"]
            if (process_ticks(pid) != watch["ticks"]
                    or Path(f"/proc/{pid}/cmdline").read_bytes() != watch["cmdline"]
                    or os.readlink(f"/proc/{pid}/exe") != watch["exe"]):
                return False
            sockets = listening_sockets(watch["port"])
            if sockets != watch["sockets"] or not holds(pid, sockets):
                return False
            return all(stamp(path) == value for path, value in watch["stamps"].items())
        except (OSError, ValueError, IndexError, StopIteration, KeyError):
            return False


@functools.lru_cache(maxsize=None)
def code_shape(function: Callable[..., Any]) -> str:
    """SHA-256 of the code a function runs, its docstring and line numbers
    aside: read from the function's code object (its bytecode, constants and
    names) and its defaults, not from the source file.  The file on disk may no
    longer be the code that runs: a checkout edited during a long run, before
    its first pair question, would key its answers under the new code's shape
    (and lines added above the function would slice the file at another one).
    Another Python version compiles other bytecode, so answers kept under one
    are asked again under the other.  A function with no code object (a
    builtin) has no shape."""
    parts, layer = [], function
    while layer is not None:              # a decorated function: the wrapper, then what it wraps
        code = getattr(layer, "__code__", None)
        if not isinstance(code, CodeType):
            break
        parts.append((code_parts(code, getattr(layer, "__doc__", None)),
                      repr(getattr(layer, "__defaults__", None)), repr(getattr(layer, "__kwdefaults__", None))))
        layer = getattr(layer, "__wrapped__", None)
    return hashlib.sha256(repr(parts).encode("utf-8")).hexdigest() if parts else ""


def code_parts(code: CodeType, doc: str | None = None) -> tuple:
    """What a code object runs, nested code objects (lambdas, inner functions)
    included; its line table and file name left out.  The docstring is the
    first constant (Python 3.12) and no instruction loads it: it is replaced by
    a mark, unless an instruction loads that constant (the same text used as a
    value), which is then kept."""
    constants = list(code.co_consts)
    if (doc is not None and constants and constants[0] == doc
            and not any(op.opcode in dis.hasconst and op.arg == 0 for op in dis.get_instructions(code))):
        constants[0] = "<docstring>"
    return (getattr(code, "co_qualname", code.co_name), code.co_argcount, code.co_posonlyargcount,
            code.co_kwonlyargcount, code.co_flags, code.co_code,
            tuple(code_parts(value) if isinstance(value, CodeType) else (type(value).__name__, repr(value))
                  for value in constants),
            code.co_names, code.co_varnames, code.co_freevars, code.co_cellvars)


def peer_of(response: Any) -> Any:
    """The address at the other end of the connection a urllib response came
    on (host, port, ...), read before its body: reading the body closes the
    connection.  None when the response came on no socket (a stand-in for
    urlopen)."""
    try:
        return response.fp.raw._sock.getpeername()
    except (AttributeError, OSError, TypeError):
        return None


def over_wire(url: str, peer: Any, payload: Any, sent: bytes | None = None) -> None:
    """Called by the real transport alone (proofread_pages.Client._send, once
    urlopen has returned): URL as asked, PEER the other end of the connection
    (peer_of), PAYLOAD the body as read, before any caller sees it, SENT the
    request's body as sent.  Heard only while the store asks a question, in
    the thread asking it."""
    heard = _HEARD.get()
    if heard is not None and heard.thread == threading.get_ident():
        heard.wire.append((url, peer, payload, sealed(payload)))
        heard.sent.append(sent)


def answer_read(payload: Any) -> None:
    """Called by Client.ask with every response it reads an answer from,
    whatever transport gave it."""
    heard = _HEARD.get()
    if heard is not None and heard.thread == threading.get_ident():
        heard.read.append((payload, sealed(payload)))


def sealed(payload: Any) -> str | None:
    try:
        return digest(payload)
    except (TypeError, ValueError):
        return None


# What the retry ladder may change from one request of a question to the next
# (Client.ask_answering): the token limit (never above the question's) and the
# effort.  Anything else sent otherwise is another question.
LADDER_FIELDS = ("max_tokens", "reasoning_effort")


def asked_as_keyed(sent: Any, request: Mapping[str, Any]) -> bool:
    """Whether SENT (a request body as sent, bytes) is REQUEST, the one the
    key holds, but for what the retry ladder changes (LADDER_FIELDS)."""
    try:
        body = json.loads(sent)
        keyed = json.loads(canonical(request))
    except (TypeError, ValueError):
        return False
    if not isinstance(body, dict) or not isinstance(keyed, dict):
        return False
    limit, most = body.get("max_tokens"), keyed.get("max_tokens")
    if not isinstance(limit, int) or not isinstance(most, int) or limit > most:
        return False

    def rest(value: dict) -> dict:
        return {k: v for k, v in value.items() if k not in LADDER_FIELDS}
    return rest(body) == rest(keyed)


def loopback(peer: Any, port: int) -> bool:
    """Whether PEER (a socket address) is PORT on this machine."""
    try:
        address = ipaddress.ip_address(str(peer[0]).split("%")[0])
        at = peer[1]
    except (TypeError, IndexError, ValueError):
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    return at == port and (address.is_loopback or bool(mapped and mapped.is_loopback))


class Heard:
    """What came back over HTTP while the store asked one question, in the
    thread asking it: each response the real transport read (over_wire), with
    where it came from, and each response the client read an answer from
    (answer_read).  A client or transport that answers without HTTP (a
    stand-in) adds to the second alone; a context copied into another thread
    (a worker pool) adds nothing to either."""

    def __init__(self) -> None:
        self.thread = threading.get_ident()
        self.wire: list[tuple[Any, Any, Any, str | None]] = []
        self.sent: list[bytes | None] = []
        self.read: list[tuple[Any, str | None]] = []

    def unproven(self, text: str, endpoint: Any, request: Mapping[str, Any] | None = None) -> str | None:
        """None when TEXT came over HTTP from ENDPOINT's port on this machine:
        it is the answer of the last response the client read, and every
        response it read (a ladder's rungs) is one the real transport read,
        unchanged since (then and now), from a connection to that port on
        this machine; and every request the transport sent is REQUEST (the
        one the key holds, when the client builds it) but for what the retry
        ladder changes (a hooked transport that sends another prompt, model or
        sampling gets the model's answer to another question).  Else why not."""
        if not self.read or not self.wire:
            return ("the answer did not come over HTTP from the server (a stand-in client or transport), "
                    "so it was not kept")
        for payload, seal in self.read:
            if seal is None or not any(payload is got and seal == kept for _, _, got, kept in self.wire):
                return ("an answer the client read did not come over HTTP from the server (a stand-in "
                        "transport), so it was not kept")
            if sealed(payload) != seal:
                return "an answer the client read was changed after it was read, so it was not kept"
        if request is not None and not all(asked_as_keyed(sent, request) for sent in self.sent):
            return ("a request sent was not the question the key holds (another prompt, model or sampling "
                    "than the client builds), so the answer was not kept")
        if not isinstance(endpoint, str):
            return "the client names no endpoint"
        parts = urllib.parse.urlsplit(endpoint)
        port = parts.port or (443 if parts.scheme == "https" else 80)
        for url, peer, _, _ in self.wire:
            if url != endpoint or not loopback(peer, port):
                return (f"a response came from {peer!r}, not over a connection to port {port} on this machine "
                        "(a stand-in for urlopen, a proxy or a redirect), so it was not kept")
        try:
            content = self.read[-1][0]["choices"][0]["message"].get("content") or ""
        except (AttributeError, IndexError, KeyError, TypeError):
            content = None
        if content != text:
            return "the answer is not the last response the client read, so it was not kept"
        return None

    def served_model(self) -> Any:
        """The model the server said answered (the last response's own model id)."""
        payload = self.read[-1][0] if self.read else None
        return payload.get("model") if isinstance(payload, dict) else None


# The question the store is asking in this thread, while it asks it (PairStore.ask).
_HEARD: contextvars.ContextVar[Heard | None] = contextvars.ContextVar("pair_cache_heard", default=None)


class PairStore:
    """The store of complete answers, and single flight for the pairs asked in
    this process.  IDENTIFY(client) gives the server's identity or why there is
    none (default: LocalServer); without one the model is asked as always and
    nothing is read or kept.  An answer is kept only when it came over HTTP
    from the client's endpoint on this machine, in answer to the request the
    key holds (Heard)."""

    def __init__(self, path: Path | str | None = None,
                 identify: Callable[[Any], tuple[dict[str, Any] | None, str | None]] | None = None):
        self.path = Path(path).expanduser() if path else default_path()
        self.records = JsonLines(self.path)
        self.identify = identify or LocalServer(
            FileHashes(self.path.with_name(self.path.stem + "-files.jsonl")), os.environ.get(TAG_ENV) or None)
        self.lock = threading.Lock()
        self.index: dict[str, dict[str, Any]] = {}
        self.servers: dict[str, dict[str, Any]] = {}
        self.flights: dict[Any, list] = {}
        self.counts: Counter = Counter()
        self.server_used: dict[str, Any] | None = None
        self.unused: str | None = None

    @contextlib.contextmanager
    def flight(self, name: Any) -> Iterator[None]:
        """One caller at a time per NAME; the others wait for it."""
        with self.lock:
            entry = self.flights.setdefault(name, [threading.Lock(), 0])
            entry[1] += 1
        try:
            with entry[0]:
                yield
        finally:
            with self.lock:
                entry[1] -= 1
                if not entry[1]:
                    del self.flights[name]

    def server(self, client: Any) -> tuple[str | None, dict[str, Any] | None]:
        identity, reason = self.identify(client)
        with self.lock:
            if identity is None:
                self.unused = reason
                return None, None
            self.server_used = identity
        return digest(identity), identity

    @staticmethod
    def request(client: Any, system: str, user_text: str, max_tokens: int) -> tuple[dict[str, Any], bool]:
        """The request the key holds, and whether the client built it (its
        request_body, as its transport sends it) - else it is made of the
        client's attributes, a shape no client that builds its requests keys
        under."""
        build = getattr(client, "request_body", None)
        if callable(build):
            return build(system, user_text, None, max_tokens), True
        return ({"model": getattr(client, "model", None), "effort": getattr(client, "effort", None),
                 "temperature": getattr(client, "temperature", None), "system": system,
                 "user": user_text, "max_tokens": max_tokens}, False)

    def key(self, client: Any, server: str, system: str, user_text: str, max_tokens: int,
            kind: str, n: int, extra: Mapping[str, Any]) -> str:
        request = self.request(client, system, user_text, max_tokens)[0]
        retry = getattr(type(client), "ask_answering", None)
        # Switch R2-C's cap on this kind's first rung, when the client has one:
        # the rung below it may answer instead (the key without it is as before).
        cap = (getattr(client, "top_rung_caps", None) or {}).get(kind)
        # The loop detector's rule (--loop-detector), when the client has one:
        # a rung it gives up is answered by the rung below, so an answer kept
        # under one rule is not another's, nor the answer without it.
        loops = getattr(client, "loop_detector", None)
        return digest({"schema": SCHEMA, "server": server, "request": request, "kind": kind, "n": n,
                       "ladder": list(getattr(client, "EFFORT_LADDER", None) or []),
                       "retry": code_shape(retry) if retry else "",
                       **({"topRungCap": cap} if cap is not None else {}),
                       **({"loopDetector": loops.text()} if loops is not None else {}), **extra})

    def lookup(self, key: str) -> dict[str, Any] | None:
        """The first complete answer kept under KEY, by this process or any
        other; None when there is none or the store cannot be read (the
        question is then asked as always)."""
        with self.lock:
            if key not in self.index:
                try:
                    found = self.records.read_new()
                except OSError as error:
                    self.unused = f"the store could not be read: {error}"
                    return None
                for record in found:
                    if record.get("type") == "answer":
                        self.index.setdefault(record["key"], record)     # the first one kept wins
                    elif record.get("type") == "server":
                        self.servers.setdefault(record["server"], record)
            return self.index.get(key)

    def ask(self, client: Any, system: str, user_text: str, max_tokens: int, kind: str, n: int,
            usable: Callable[[str], bool], extra: Mapping[str, Any] | None = None
            ) -> tuple[str, str | None]:
        """The answer to one question and, when it came from the store, when it
        was kept there (None when the model was asked now).  N counts the
        times the same question is asked within one procedure: a repeat is a
        question of its own, answered afresh the first time."""
        extra = dict(extra or {})
        server, identity = self.server(client)
        key = self.key(client, server, system, user_text, max_tokens, kind, n, extra) if server else None
        if key is not None:
            found = self.lookup(key)
            if found is not None:
                with self.lock:
                    self.counts["fromStore"] += 1
                return found["text"], found["at"]
        endpoint = getattr(client, "endpoint", None)
        # The request the key holds, as the client builds it before it asks.
        request, built = self.request(client, system, user_text, max_tokens)
        heard = Heard()
        listening = _HEARD.set(heard)
        try:
            text, metrics = client.ask_answering(system, user_text, None, max_tokens, kind=kind)
        finally:
            _HEARD.reset(listening)
        with self.lock:
            self.counts["asked"] += 1
        complete = (bool((text or "").strip()) and not metrics.get("degraded")
                    and metrics.get("finish_reason") == "stop" and usable(text))
        # Kept only when it came over HTTP from the endpoint the server was
        # identified by, in answer to the request the key holds (Heard); a
        # stand-in's answer never is.
        unheard = (heard.unproven(text, endpoint, request if built else None)
                   if key is not None and complete else None)
        if key is None or not complete or unheard or self.server(client)[0] != server:
            with self.lock:
                self.counts["notKept"] += 1
                if unheard:
                    self.unused = unheard
            return text, None
        with self.lock:
            fresh = server not in self.servers
            self.servers.setdefault(server, {"type": "server", "server": server, "identity": identity})
        try:
            if fresh:
                self.records.append({"type": "server", "server": server, "identity": identity, "at": utc_now()})
            record = {"type": "answer", "key": key, "server": server, "question": user_text, "n": n,
                      "kind": kind, "model": getattr(client, "model", None),
                      # The model id the server's own response gave.
                      "servedModel": heard.served_model(),
                      "effort": getattr(client, "effort", None), "maxTokens": max_tokens,
                      "text": text, "finishReason": metrics.get("finish_reason"),
                      "answeredAtEffort": metrics.get("effort"),
                      # The first rung cut at switch R2-C's cap (a lower rung answered).
                      **({"topRungCap": metrics["earlyCut"]} if metrics.get("earlyCut") else {}),
                      # Rungs given up in a loop (--loop-detector; a lower rung answered).
                      **({"loopCuts": metrics["loopCuts"]} if metrics.get("loopCuts") else {}),
                      "completionTokens": metrics.get("completion_tokens"),
                      "reasoningTokens": metrics.get("reasoning_tokens"), "at": utc_now()}
            self.records.append(record)
        except OSError as error:
            with self.lock:
                self.counts["notKept"] += 1
                self.unused = f"the store could not be written: {error}"
            return text, None
        with self.lock:
            self.index.setdefault(key, record)
            self.counts["kept"] += 1
        return text, None

    def summary(self) -> dict[str, Any]:
        """What the run's seal says of the store: where it is, which server its
        answers are keyed to (or why it was not used), and the counts."""
        with self.lock:
            return {"store": str(self.path),
                    "server": self.server_used,
                    "serverSha256": digest(self.server_used) if self.server_used else None,
                    # Why some question could not use the store (the last reason), if any did not.
                    "notUsedBecause": self.unused,
                    "answersFromStore": self.counts["fromStore"],
                    "answersAskedNow": self.counts["asked"],
                    "answersKept": self.counts["kept"],
                    "answersNotKept": self.counts["notKept"]}
