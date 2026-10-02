#!/usr/bin/env python3
"""Checks of the store of the model's answers to the variant-pair question
(scripts/_pair_cache.py, classify_pair in proofread_pages.py): a complete answer
is kept on disk and read back by a later run instead of asking the model again,
under a key that changes with the prompt, the model, the effort, the token limit
and the server; an answer cut off on every effort, one without the verdict line
and a failed call are not kept; nor is an answer that did not come over HTTP
from the endpoint's port (a stand-in transport, a stand-in model naming the
endpoint, an answer changed after it was read or edited in place after, a
stand-in for urlopen), nor one to another request than the key holds (a hooked
transport sending another prompt or sampling), even with a live server on that
port that the store identifies, directly or through the runner, while the real
client's answers from it are kept with the model id the server gave; records of
schema 1 (kept without that proof) are not read; answers that came after the
identified server stopped listening or exec()ed another program are not kept
under its identity, and a process that listens on the port itself (another
loopback address, a proxy there) is not trusted; several processes write one store at once; a pair asked twice
at once in one process is asked once; the book profile records each pair's
votes and which came from the store, and phase 3 each page's; --no-pair-cache
is as before; the stand-in harness (tests/stand_in.py) runs on stores of its
own, never the default path.

No model, no GPU, no corpus, no request to any server but the stand-ins this
check starts on free ports of 127.0.0.1: a stand-in model server in this
process (the real client, its retry ladder and its transport, over canned
answers), stores in temporary directories, and for the server's identity
stand-in processes that listen on a free port, some of them answering over
HTTP, one also on 127.0.0.2 of that port in this process (their weights a sparse file of the size weights are taken to have at least; a
process that names no such file is not trusted).

Usage: python3 tests/check_pair_cache.py   (exits non-zero if any check fails)
"""
from __future__ import annotations

import copy
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _pair_cache as pc  # noqa: E402
import book_profile as bp  # noqa: E402
import proofread_pages as pp  # noqa: E402
import stand_in  # noqa: E402

failures = 0
SCRATCH = Path(tempfile.mkdtemp(prefix="pair-cache-check-"))
# Nothing here may touch the store of the machine this runs on.
os.environ[pc.PATH_ENV] = str(SCRATCH / "never-used.jsonl")
os.environ.pop(pc.TAG_ENV, None)


def check(name: str, got, want) -> None:
    global failures
    if got != want:
        failures += 1
        print(f"FAIL {name}: got {got!r}, want {want!r}")
    else:
        print(f"ok   {name}")


class Offline(pp.Client):
    """The real client (its effort ladder, its request body, its transport)
    asking a model server in this process (stand_in.Served) that answers
    canned answers per (甲, 乙): "cut" is cut off at the token limit on every
    effort, "error" fails (HTTP 500); a list answers the question's first,
    second, ... asking in turn.  The store keeps only answers that came over
    HTTP, so the stand-in model answers there, not in place of the transport."""

    def __init__(self, answers=None, model="stand-in", effort="xhigh", delay=0.0):
        super().__init__(stand_in.served().endpoint(self.respond), model, effort, 30)
        self.answers = answers or {}
        self.delay = delay
        self.calls: list[str] = []
        self.lock = threading.Lock()

    def respond(self, body):
        user_text = body["messages"][1]["content"][0]["text"]
        x, y = re.findall(r"「(.)」", user_text)
        with self.lock:
            asked = sum(1 for call in self.calls if call == user_text)
            self.calls.append(user_text)
        time.sleep(self.delay)
        answer = self.answers.get((x, y), "判定：不同")
        if isinstance(answer, list):
            answer = answer[min(asked, len(answer) - 1)]
        if answer == "error":
            return 500
        if answer == "cut":
            return stand_in.reply("", "length", body["max_tokens"])
        return stand_in.reply(answer, completion_tokens_details={"reasoning_tokens": 8})


def server(name: str = "server-1"):
    return lambda client: ({"stand-in": name}, None)


def new_process() -> None:
    """What a new process starts with: no pair classified in memory."""
    pp._PAIR_CACHE.clear()
    pp._PAIR_ORIGIN.clear()


def classify(store, client, a, b, max_tokens=4000):
    new_process()
    previous = pp.use_pair_store(store)
    try:
        return pp.classify_pair(client, a, b, max_tokens=max_tokens)
    finally:
        pp.use_pair_store(previous)


def records(path: Path, kind: str = "answer") -> list[dict]:
    return [r for r in pc.JsonLines(path).read_new() if r.get("type") == kind]


# --- miss, then hit ------------------------------------------------------------------
path = SCRATCH / "store.jsonl"
cold = Offline({("甲", "乙"): "判定：異體", ("乙", "甲"): "判定：異體"})
check("miss: asked in both orders", (classify(pc.PairStore(path, server()), cold, "甲", "乙"), cold.calls),
      ("variant", ["甲「甲」 乙「乙」", "甲「乙」 乙「甲」"]))
check("miss: both complete answers kept, and the server once", (len(records(path)), len(records(path, "server"))), (2, 1))
warm = Offline()
store = pc.PairStore(path, server())
check("hit: a new process asks nothing and gets the kept verdict", (classify(store, warm, "甲", "乙"), warm.calls),
      ("variant", []))
kept_at = sorted(r["at"] for r in records(path))
origin = pp._PAIR_ORIGIN[frozenset("甲乙")]
check("hit: each vote says it came from the store, with when it was kept",
      [(v["asked"], v["vote"], v["fromStore"]) for v in origin["votes"]],
      [("甲|乙", "variant", kept_at[0]), ("乙|甲", "variant", kept_at[1])])
check("hit: the store's counts", {k: store.summary()[k] for k in ("answersFromStore", "answersAskedNow", "answersKept")},
      {"answersFromStore": 2, "answersAskedNow": 0, "answersKept": 0})
reverse = Offline()
check("hit: the pair met in the other order finds both first answers",
      (classify(pc.PairStore(path, server()), reverse, "乙", "甲"), reverse.calls), ("variant", []))

# The two orders disagree: the first order is asked again.  A later run that meets
# the pair in the other order has both first answers and asks only its own repeat,
# as the procedure asks it, and gets the verdict the procedure gives in that order.
split = {("丙", "丁"): "判定：異體", ("丁", "丙"): "判定：不同"}
first = Offline(split)
check("disagreement: three questions, the first order twice",
      (classify(pc.PairStore(path, server()), first, "丙", "丁"), first.calls),
      ("variant", ["甲「丙」 乙「丁」", "甲「丁」 乙「丙」", "甲「丙」 乙「丁」"]))
other = Offline(split)
check("disagreement: in the other order only that order's repeat is asked",
      (classify(pc.PairStore(path, server()), other, "丁", "丙"), other.calls),
      ("different", ["甲「丁」 乙「丙」"]))
same = Offline(split)
check("disagreement: in the first order again nothing is asked",
      (classify(pc.PairStore(path, server()), same, "丙", "丁"), same.calls), ("variant", []))

# --- what the key holds -------------------------------------------------------------
def asked_again(name: str, client: Offline, identify=server(), max_tokens: int = 4000) -> None:
    check(f"key: {name} asks again", (classify(pc.PairStore(path, identify), client, "甲", "乙", max_tokens),
                                      len(client.calls)), ("different", 2))


asked_again("another model", Offline(model="stand-in-2"))
asked_again("another effort", Offline(effort="medium"))
asked_again("another token limit", Offline(), max_tokens=3000)
asked_again("another server", Offline(), identify=server("server-2"))
saved_prompt = pp.PAIR_SYSTEM
pp.PAIR_SYSTEM = saved_prompt + "\n"
try:
    asked_again("another prompt", Offline())
finally:
    pp.PAIR_SYSTEM = saved_prompt
pp.CALL_BUDGETS["pair-class"] = 2000
try:
    asked_again("a budget for the kind", Offline())
finally:
    pp.CALL_BUDGETS.pop("pair-class")
unchanged = Offline()
classify(pc.PairStore(path, server()), unchanged, "甲", "乙")
check("key: the same request to the same server still hits after all that", unchanged.calls, [])

# --- what is not kept ---------------------------------------------------------------
lost = SCRATCH / "not-kept.jsonl"
cut = Offline({("戊", "己"): "cut", ("己", "戊"): "判定：異體"})
check("cut off on every effort: four efforts, voted 'different', so that order asked again (four more)",
      (classify(pc.PairStore(lost, server()), cut, "戊", "己"), len(cut.calls)), ("different", 9))
check("cut off on every effort: not kept (the complete answer is)",
      [r["question"] for r in records(lost)], ["甲「己」 乙「戊」"])
again = Offline({("戊", "己"): "判定：異體", ("己", "戊"): "判定：異體"})
classify(pc.PairStore(lost, server()), again, "戊", "己")
check("cut off on every effort: a later run asks it again", again.calls, ["甲「戊」 乙「己」"])
noline = Offline({("庚", "辛"): "兩個字唔同", ("辛", "庚"): "判定：不同"})
classify(pc.PairStore(lost, server()), noline, "庚", "辛")
check("an answer without the verdict line: not kept",
      sorted(r["question"] for r in records(lost) if "庚" in r["question"]), ["甲「辛」 乙「庚」"])
failing = Offline({("壬", "癸"): "error"})
try:
    classify(pc.PairStore(lost, server()), failing, "壬", "癸")
    raised = False
except pp.ProofreadError:
    raised = True
check("a failed call: raised as before, nothing kept",
      (raised, [r for r in records(lost) if "壬" in r["question"]]), (True, []))
flaky = iter([({"stand-in": "server-1"}, None), ({"stand-in": "restarted"}, None)] * 10)
moved = Offline()
classify(pc.PairStore(SCRATCH / "moved.jsonl", lambda client: next(flaky)), moved, "子", "丑")
check("the server changed while the model answered: not kept", records(SCRATCH / "moved.jsonl"), [])
nowhere = Offline()
store = pc.PairStore(SCRATCH / "nowhere.jsonl", lambda client: (None, "the client names no endpoint"))
classify(store, nowhere, "子", "丑")
check("no server identity: asked as always, the store neither read nor written",
      (len(nowhere.calls), (SCRATCH / "nowhere.jsonl").exists(), store.summary()["notUsedBecause"]),
      (2, False, "the client names no endpoint"))

unreadable = SCRATCH / "a-directory.jsonl"
unreadable.mkdir()
blocked = Offline({("子", "丑"): "判定：異體", ("丑", "子"): "判定：異體"})
store = pc.PairStore(unreadable, server())
check("a store that cannot be read or written: asked as always, the reason said",
      (classify(store, blocked, "子", "丑"), len(blocked.calls), store.summary()["answersNotKept"],
       store.summary()["notUsedBecause"].split(":")[0]),
      ("variant", 2, 2, "the store could not be written"))

# --- only what came over HTTP from the server -------------------------------------------
# Found on 2026-09-29 in the machine's store: 20 answers 「判定：不同」 kept under
# the model server's identity by an offline replay whose stand-in client named
# the endpoint the server listened on.  An answer is kept only when the real
# transport read it from a connection to the endpoint's port on this machine.

class Replay(pp.Client):
    """The real client with a stand-in transport (Client._send replaced, as
    the checks' Ladder and an offline replay replace it): each request is
    answered by the stand-in model (stand_in.StandIn answers the pair question
    「判定：不同」), nothing is sent."""

    def __init__(self, endpoint, effort="xhigh"):
        super().__init__(endpoint, "stand-in", effort, 30)
        self.inner = stand_in.StandIn(census=0)
        self.sent: list[tuple[str, dict]] = []

    def _send(self, body, kind):
        self.sent.append((kind, body))
        system, user = body["messages"][0]["content"], body["messages"][1]["content"][0]["text"]
        return stand_in.reply(self.inner.ask_answering(system, user, None, body["max_tokens"], kind)[0]), 0.0


class Edited(Offline):
    """The real transport, its answer changed after it was read."""

    def _send(self, body, kind):
        payload, waited = super()._send(body, kind)
        payload["choices"][0]["message"]["content"] = "判定：異體"
        return payload, waited


class Canned:
    """What a stand-in for urlopen returns: a response on no connection."""

    def __init__(self, payload):
        self.raw = json.dumps(payload, ensure_ascii=False).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.raw


NOT_OVER_HTTP = "the answer did not come over HTTP from the server"


def unheard(name: str, client, why: str, identify=server()) -> None:
    """CLIENT's answers to one pair, with the server's identity known: asked,
    none kept, and the summary says why (WHY, its start)."""
    path = SCRATCH / f"unheard-{re.sub(r'[^a-z]+', '-', name)}.jsonl"
    store = pc.PairStore(path, identify)
    classify(store, client, "甲", "乙")
    summary = store.summary()
    check(f"not over HTTP from the server - {name}: asked, nothing kept, the reason said",
          (summary["answersAskedNow"], summary["answersKept"], records(path),
           (summary["notUsedBecause"] or "").startswith(why)), (2, 0, [], True))


class Named(stand_in.StandIn):
    """A stand-in model in place of the client that names a live endpoint and
    says its answers finished (finish_reason "stop"), as the real client's do."""

    def __init__(self, endpoint):
        super().__init__(census=0)
        self.endpoint = endpoint

    def ask_answering(self, system, user_text, image_bytes, max_tokens, kind="other"):
        text, metrics = super().ask_answering(system, user_text, image_bytes, max_tokens, kind)
        return text, {**metrics, "finish_reason": "stop"}


unheard("the real client with a stand-in transport", Replay(Offline().endpoint), NOT_OVER_HTTP)
unheard("a stand-in model naming the endpoint", Named(Offline().endpoint), NOT_OVER_HTTP)
unheard("the real transport's answer changed after it was read", Edited(),
        "an answer the client read did not come over HTTP")
real_urlopen = pp.urllib.request.urlopen
pp.urllib.request.urlopen = lambda request, timeout=None: Canned(stand_in.reply("判定：異體"))
try:
    unheard("a stand-in for urlopen (a response on no connection)", Offline(), "a response came from None")
finally:
    pp.urllib.request.urlopen = real_urlopen
heard = Offline({("甲", "乙"): "判定：異體", ("乙", "甲"): "判定：異體"})
store = pc.PairStore(SCRATCH / "heard.jsonl", server())
classify(store, heard, "甲", "乙")
check("over HTTP from the endpoint: kept, with the model id the server's response gave",
      ([r.get("servedModel") for r in records(SCRATCH / "heard.jsonl")], store.summary()["notUsedBecause"]),
      (["stand-in", "stand-in"], None))


class Rephrased(Offline):
    """The real transport, hooked to send the server another question than
    the client builds (another system prompt, as a prompt experiment might):
    the model's answer to that question, not to the one the key holds."""

    def _send(self, body, kind):
        body = {**body, "messages": [{"role": "system", "content": "另一個實驗嘅提示。" + body["messages"][0]["content"]},
                                     *body["messages"][1:]]}
        return super()._send(body, kind)


class Resampled(Offline):
    """The real transport, hooked to send another temperature."""

    def _send(self, body, kind):
        return super()._send({**body, "temperature": 0.7}, kind)


unheard("the real transport sending another prompt than the key holds",
        Rephrased({("甲", "乙"): "判定：不同", ("乙", "甲"): "判定：不同"}),
        "a request sent was not the question the key holds")
unheard("the real transport sending another sampling than the key holds",
        Resampled({("甲", "乙"): "判定：不同", ("乙", "甲"): "判定：不同"}),
        "a request sent was not the question the key holds")
# The real transport's response, read and passed on unchanged, then edited in
# place and its edit answered (hooks on the instance: the key is the real
# client's).
edited_later = Offline({("甲", "乙"): "判定：異體", ("乙", "甲"): "判定：異體"})
held_payloads = []
plain_send, plain_answering = edited_later._send, edited_later.ask_answering


def keep_payload(body, kind):
    payload, waited = plain_send(body, kind)
    held_payloads.append(payload)
    return payload, waited


def edit_after(*args, **kwargs):
    text, metrics = plain_answering(*args, **kwargs)
    held_payloads[-1]["choices"][0]["message"]["content"] = "判定：不同"
    return "判定：不同", metrics


edited_later._send, edited_later.ask_answering = keep_payload, edit_after
unheard("the real transport's answer edited in place after the client read it", edited_later,
        "an answer the client read was changed after it was read")
# Records of schema 1 were kept without the proof (the stand-in answers found
# on 2026-09-29 among them), and the checkouts beside this one still write
# them to the default store: none is read.
schema_one = SCRATCH / "schema-one.jsonl"
current_schema = pc.SCHEMA
pc.SCHEMA = 1
try:
    for x, y in (("甲", "乙"), ("乙", "甲")):
        old_key = pc.PairStore(schema_one, server()).key(
            Offline(), pc.digest({"stand-in": "server-1"}), pp.PAIR_SYSTEM, f"甲「{x}」 乙「{y}」", 4000,
            "pair-class", 0, {"callBudget": pp.CALL_BUDGETS.get("pair-class")})
        pc.JsonLines(schema_one).append({"type": "answer", "key": old_key, "text": "判定：不同", "at": "schema 1"})
finally:
    pc.SCHEMA = current_schema
store = pc.PairStore(schema_one, server())
fresh = Offline({("甲", "乙"): "判定：異體", ("乙", "甲"): "判定：異體"})
check("records of schema 1 (kept without the proof, by older checkouts): not read, the question asked",
      (classify(store, fresh, "甲", "乙"), store.summary()["answersFromStore"], store.summary()["answersKept"]),
      ("variant", 0, 2))

# --- the file ----------------------------------------------------------------------
torn = SCRATCH / "torn.jsonl"
pc.JsonLines(torn).append({"type": "answer", "key": "k1", "text": "判定：異體", "at": "t1"})
with torn.open("ab") as handle:
    handle.write(b'{"payload":{"type":"answer","key":"k2"')        # a writer died here
pc.JsonLines(torn).append({"type": "answer", "key": "k3", "text": "判定：不同", "at": "t3"})
lines = torn.read_bytes().split(b"\n")
tampered = json.loads(lines[0])
tampered["payload"]["text"] = "判定：不同"
with torn.open("ab") as handle:
    handle.write(json.dumps(tampered).encode() + b"\n")
check("a line cut short by a crash and a line whose seal fails are skipped",
      [r["key"] for r in pc.JsonLines(torn).read_new()], ["k1", "k3"])

WRITER = """
import sys; sys.path.insert(0, sys.argv[1])
import _pair_cache as pc
lines = pc.JsonLines(sys.argv[2])
for n in range(int(sys.argv[4])):
    lines.append({"type": "answer", "key": sys.argv[3] + str(n), "text": "x" * 3000, "at": "t"})
"""
shared = SCRATCH / "shared.jsonl"
writers = [subprocess.Popen([sys.executable, "-c", WRITER, str(Path(pc.__file__).parent), str(shared), f"w{w}-", "150"])
           for w in range(6)]
check("concurrent writers: six processes finish", [w.wait() for w in writers], [0] * 6)
written = pc.JsonLines(shared).read_new()
check("concurrent writers: every record whole, none lost",
      (len(written), len({r["key"] for r in written}), shared.read_bytes().count(b"\n")), (900, 900, 900))

# --- single flight ------------------------------------------------------------------
store = pc.PairStore(SCRATCH / "flight.jsonl", server())
slow = Offline({("寅", "卯"): "判定：異體", ("卯", "寅"): "判定：異體"}, delay=0.05)
gate = threading.Barrier(12)
results: list[str] = []


def racer(i: int) -> None:
    gate.wait()
    previous_order = ("寅", "卯") if i % 2 else ("卯", "寅")
    results.append(pp.classify_pair(slow, *previous_order))


new_process()
previous = pp.use_pair_store(store)
try:
    threads = [threading.Thread(target=racer, args=(i,)) for i in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
finally:
    pp.use_pair_store(previous)
check("single flight: twelve callers at once, either order, ask the pair once",
      (len(slow.calls), sorted(set(results)), len(results)), (2, ["variant"], 12))

# --- the retrying code's shape ------------------------------------------------------
# The key holds the shape of the retrying code the process runs, not of the
# file on disk: a checkout edited during a long run, before its first pair
# question, must not key the old code's answers under the new code's shape (a
# later run of the new code would take answers its own retrying would not
# have given), nor, with lines added above, under another function's.
import importlib.util  # noqa: E402

RETRYING = """class Client:
    def ask_answering(self, text, budget=2000):
        \"\"\"{doc}\"\"\"
        # {comment}
        if len(text) < budget:
            return text
        return text[:budget]
"""


def loaded(name: str, source: str, edited: str | None = None):
    """Client.ask_answering of SOURCE, loaded as a module; the file then
    rewritten as EDITED, as a checkout is edited under a running process."""
    path = SCRATCH / f"{name}.py"
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if edited is not None:
        path.write_text(edited, encoding="utf-8")
    return module.Client.ask_answering


code_x = RETRYING.format(doc="Retry.", comment="a comment")
code_y = code_x.replace("if len(text) < budget:", "if len(text) < 0:     ")        # other code, the same lines
running = loaded("edited_under_it", code_x, code_y)
shape_x, shape_y = pc.code_shape(loaded("fresh_x", code_x)), pc.code_shape(loaded("fresh_y", code_y))
check("code shape: the file edited after the code was loaded - the shape of the code that runs",
      (pc.code_shape(running) == shape_x, pc.code_shape(running) == shape_y), (True, False))
check("code shape: lines added above the function after it was loaded - still its own shape",
      pc.code_shape(loaded("shifted_under_it", code_x, "# a line added above\n" * 3 + code_x)), shape_x)
check("code shape: another docstring, comment and line numbers - the same shape",
      pc.code_shape(loaded("reworded", "\n\n" + RETRYING.format(doc="Retry, reworded.", comment="another"))),
      shape_x)
check("code shape: another default - another shape",
      pc.code_shape(loaded("other_default", code_x.replace("budget=2000", "budget=4000"))) != shape_x, True)

# --- the server's identity ------------------------------------------------------------
LISTEN = "import socket,time;s=socket.socket();s.bind(('127.0.0.1',0));s.listen();print(s.getsockname()[1],flush=True);time.sleep(120)"


def listening(workdir: Path, *arguments: str):
    process = subprocess.Popen([sys.executable, "-c", LISTEN, *arguments], cwd=workdir,
                               stdout=subprocess.PIPE, text=True)
    return process, int(process.stdout.readline())


class Pointed:
    def __init__(self, port: int):
        self.endpoint = f"http://127.0.0.1:{port}/v1/chat/completions"


# The size a model's weights file is taken to have at least (64 MiB before the constant existed).
WEIGHTS_MIN = getattr(pc, "WEIGHTS_MIN_BYTES", 64 * 1024 * 1024)


def weights_file(path: Path, content: bytes) -> str:
    """A file the size of a model's weights (CONTENT, then zeros, sparse), and its SHA-256."""
    with path.open("wb") as handle:
        handle.write(content)
        handle.truncate(WEIGHTS_MIN)
    hasher = hashlib.sha256(content)
    zeros = bytes(1 << 20)
    left = WEIGHTS_MIN - len(content)
    while left:
        hasher.update(zeros[:min(left, len(zeros))])
        left -= min(left, len(zeros))
    return hasher.hexdigest()


import hashlib  # noqa: E402
work = SCRATCH / "server"
work.mkdir()
weights_one = weights_file(work / "weights.bin", b"weights one" * 1000)
(work / "config.yaml").write_text("model: weights.bin\n")
time.sleep(2.2)          # a file changed just before the start is not trusted
process, port = listening(work, "weights.bin", "--flag", "x")
try:
    hashes = pc.FileHashes(SCRATCH / "files.jsonl")
    identity, reason = pc.LocalServer(hashes, None)(Pointed(port))
    weights = str((work / "weights.bin").resolve())
    check("server: the process on the port, its command line and its files' SHA-256",
          (reason, identity and identity["argv"][-3:], identity and identity["sha256"].get(weights)),
          (None, ["weights.bin", "--flag", "x"], weights_one))
    check("server: each file is read once per version (kept beside the store)",
          len([r for r in pc.JsonLines(SCRATCH / "files.jsonl").read_new() if r["path"] == weights]), 1)
    pc.LocalServer(pc.FileHashes(SCRATCH / "files.jsonl"), None)(Pointed(port))
    check("server: a new process finds the hash kept", len(records(SCRATCH / "files.jsonl", "file")),
          len(identity["sha256"]))
    tagged, _ = pc.LocalServer(hashes, "after-a-rebuild")(Pointed(port))
    check("server: PAIR_CACHE_MODEL_TAG is part of the identity",
          (tagged["tag"], pc.digest(tagged) != pc.digest(identity)), ("after-a-rebuild", True))
    watcher = pc.LocalServer(hashes, None)
    watcher(Pointed(port))
    weights_file(work / "weights.bin", b"weights two" * 1000)
    gone, reason = watcher(Pointed(port))
    check("server: a file changed after the server started - not trusted",
          (gone, bool(reason and "changed after the server started" in reason)), (None, True))
finally:
    process.kill()
    process.wait()
time.sleep(2.2)
process, port = listening(work, "weights.bin", "--flag", "x")
try:
    restarted, reason = pc.LocalServer(hashes, None)(Pointed(port))
    check("server: restarted on the changed file - another identity",
          (reason, restarted and pc.digest(restarted) != pc.digest(identity)), (None, True))
finally:
    process.kill()
    process.wait()
(work / "model-dir").mkdir()
time.sleep(2.2)
process, port = listening(work, "./model-dir")
try:
    check("server: a directory on the command line - not trusted",
          pc.LocalServer(hashes, None)(Pointed(port))[1],
          "the server's command line names a directory (./model-dir), whose contents are not checked")
finally:
    process.kill()
    process.wait()
# A process that names no weights says nothing of the model that answers: a
# forwarder on the port (ssh -L, socat), whose backend can be swapped with the
# forwarder's command line unchanged, or a server that finds its model by name
# or in its configuration, whose model can be updated under the same name.
NO_WEIGHTS = f"the server's command line names no file of {WEIGHTS_MIN >> 20} MiB or more"
for name, arguments in (("a forwarder (a command line naming no file)", ["--to", "127.0.0.1:1"]),
                        ("a model found by name", ["serve", "org/model-name"]),
                        ("a configuration file only", ["--config", "config.yaml"])):
    process, port = listening(work, *arguments)
    try:
        found, reason = pc.LocalServer(hashes, None)(Pointed(port))
        check(f"server: {name} - not trusted", (found, bool(reason and reason.startswith(NO_WEIGHTS))), (None, True))
        found, reason = pc.LocalServer(hashes, "a-tag")(Pointed(port))
        check(f"server: {name}, with PAIR_CACHE_MODEL_TAG set - still not trusted",
              (found, bool(reason and reason.startswith(NO_WEIGHTS))), (None, True))
    finally:
        process.kill()
        process.wait()

# The file a path on the command line leads to now may not be the one the
# server loaded: a link re-pointed (current -> v2 in place of current -> v1) or
# a directory renamed into the path while the server runs leaves the old model
# in memory and the new weights at the path, both with old change times.  The
# servers' files are in a tree of their own, made before any server starts,
# so that no name on their paths is bound after a start but the ones moved here.
SERVERS = Path(tempfile.mkdtemp(prefix="pair-cache-servers-"))
for folder in ("linked/v1", "linked/v2", "renamed/live", "renamed/v2", "moved/main", "moved/extra", "bare"):
    (SERVERS / folder).mkdir(parents=True)
model_one = weights_file(SERVERS / "linked" / "v1" / "weights.bin", b"model one" * 100)
model_two = weights_file(SERVERS / "linked" / "v2" / "weights.bin", b"model two" * 100)
weights_file(SERVERS / "renamed" / "live" / "weights.bin", b"model one" * 100)
weights_file(SERVERS / "renamed" / "v2" / "weights.bin", b"model two" * 100)
weights_file(SERVERS / "moved" / "main" / "weights.bin", b"model one" * 100)
weights_file(SERVERS / "moved" / "extra" / "projector.bin", b"projector one" * 100)
weights_file(SERVERS / "bare" / "weights.bin", b"model one" * 100)
(SERVERS / "linked" / "current").symlink_to("v1")
time.sleep(2.2)
linked = SERVERS / "linked"
process, port = listening(linked, "current/weights.bin")
try:
    found, reason = pc.LocalServer(hashes, None)(Pointed(port))
    check("server: a path through a link made before the server started - the file it leads to",
          (reason, found and found["sha256"].get(str((linked / "v1" / "weights.bin").resolve()))), (None, model_one))
    (linked / "notes.txt").write_text("a file added beside the link while the server runs\n")
    found, reason = pc.LocalServer(hashes, None)(Pointed(port))
    check("server: a file added beside the link while the server runs - still the same file",
          (reason, found and found["sha256"].get(str((linked / "v1" / "weights.bin").resolve()))), (None, model_one))
    (linked / "next").symlink_to("v2")
    (linked / "next").replace(linked / "current")        # re-pointed while the old model is in memory
    found, reason = pc.LocalServer(hashes, None)(Pointed(port))
    check("server: the link re-pointed while the server runs - not trusted",
          (found, bool(reason and "current was put in place or changed after the server started" in reason)),
          (None, True))
finally:
    process.kill()
    process.wait()
time.sleep(2.2)
process, port = listening(linked, "current/weights.bin")
try:
    found, reason = pc.LocalServer(hashes, None)(Pointed(port))
    check("server: restarted after the link was re-pointed - the new file",
          (reason, found and found["sha256"].get(str((linked / "v2" / "weights.bin").resolve()))), (None, model_two))
finally:
    process.kill()
    process.wait()
renamed = SERVERS / "renamed"
process, port = listening(renamed, "live/weights.bin")
try:
    found, reason = pc.LocalServer(hashes, None)(Pointed(port))
    check("server: a path through directories unchanged since the server started - trusted",
          (reason, found and found["sha256"].get(str((renamed / "live" / "weights.bin").resolve()))),
          (None, model_one))
    (renamed / "live").rename(renamed / "old")
    (renamed / "v2").rename(renamed / "live")             # the new version renamed into the path
    found, reason = pc.LocalServer(hashes, None)(Pointed(port))
    check("server: a directory on the path renamed while the server runs - not trusted",
          (found, bool(reason and "live was put in place or changed after the server started" in reason)),
          (None, True))
finally:
    process.kill()
    process.wait()
# A file the command line names that is missing when the server is checked
# (moved aside while the server runs) must not drop out of the identity: two
# servers whose projector differs, each moved aside, would share one key.
moved = SERVERS / "moved"
process, port = listening(moved, "main/weights.bin", "--projector", "extra/projector.bin",
                          "--alias", "org/model-name")
try:
    found, reason = pc.LocalServer(hashes, None)(Pointed(port))
    check("server: a path that never led anywhere (org/name) in a directory unchanged since the start - "
          "not a file, trusted", (reason, found and len(found["sha256"])), (None, 3))
    (moved / "extra" / "projector.bin").rename(moved / "extra" / "projector.bin.old")
    found, reason = pc.LocalServer(hashes, None)(Pointed(port))
    check("server: a file on the command line moved aside while the server runs - not trusted",
          (found, bool(reason and "projector.bin is missing and" in reason)), (None, True))
finally:
    process.kill()
    process.wait()
bare = SERVERS / "bare"
process, port = listening(bare, "weights.bin")
try:
    (bare / "weights.bin").rename(bare / "weights.bin.old")
    found, reason = pc.LocalServer(hashes, None)(Pointed(port))
    check("server: the only weights, named without a directory, moved aside while the server runs - not trusted",
          (found, bool(reason and reason.startswith(NO_WEIGHTS))), (None, True))
finally:
    process.kill()
    process.wait()
shutil.rmtree(SERVERS, ignore_errors=True)
remote = Pointed(1)
remote.endpoint = "https://api.example.invalid/v1/chat/completions"
check("server: not on this machine - not trusted", pc.LocalServer(hashes, None)(remote)[0], None)
check("server: a client with no endpoint (a stand-in) - not trusted",
      pc.LocalServer(hashes, None)(stand_in.StandIn()), (None, "the client names no endpoint"))

# --- a live server on the endpoint's port ------------------------------------------------
# What the replay met: a model server the store identifies (a process of this
# machine listening on the endpoint's port, its weights on its command line)
# while a stand-in answers.  Here the server is a stand-in process that
# answers every chat request over HTTP (判定：異體, its model id
# "served-model"), and the store identifies it as it would the real one.
SERVE = ("import json\nfrom http.server import BaseHTTPRequestHandler, HTTPServer\n"
         "class Handler(BaseHTTPRequestHandler):\n"
         "    def do_POST(self):\n"
         "        self.rfile.read(int(self.headers['Content-Length']))\n"
         "        raw = json.dumps({'model': 'served-model', 'choices': [{'message': {'content': '判定：異體'},\n"
         "                          'finish_reason': 'stop'}], 'usage': {'completion_tokens': 12}}).encode()\n"
         "        self.send_response(200)\n"
         "        self.send_header('Content-Length', str(len(raw)))\n"
         "        self.end_headers()\n"
         "        self.wfile.write(raw)\n"
         "    def log_message(self, *args):\n"
         "        pass\n"
         "server = HTTPServer(('127.0.0.1', 0), Handler)\n"
         "print(server.server_address[1], flush=True)\n"
         "server.serve_forever()\n")
assert os.sep not in SERVE      # a word of the command line with no path in it
# A made-up book whose engines disagree on two variant pairs (甲/乙, 辰/巳),
# which phase 3 and the book profile ask the model about.
OPENINGS = {1: "第一章總論", 2: "第二章各論", 3: "第三章附則"}
TEXT_A = "此事甲國計辰"
TEXT_B = "此事乙國計巳"
PAGES = {page: ([stand_in.block(opening + TEXT_A, [0.3, 0.1, 0.4, 0.8])], opening + TEXT_B)
         for page, opening in OPENINGS.items()}
live = SCRATCH / "live"
live.mkdir()
weights_file(live / "weights.bin", b"live weights" * 1000)
time.sleep(2.2)          # a file changed just before the start is not trusted
process = subprocess.Popen([sys.executable, "-c", SERVE, "weights.bin"], cwd=live, stdout=subprocess.PIPE, text=True)
try:
    live_endpoint = f"http://127.0.0.1:{int(process.stdout.readline())}/v1/chat/completions"
    replay = Replay(live_endpoint)
    store = pc.PairStore(SCRATCH / "live-replay.jsonl")
    classify(store, replay, "甲", "乙")
    summary = store.summary()
    check("live server, a stand-in transport: the store identifies the server on the port",
          (summary["server"] or {}).get("argv", [])[-1:], ["weights.bin"])
    check("live server, a stand-in transport: asked, nothing kept (where the replay kept its answers), "
          "the reason said",
          ([kind for kind, _ in replay.sent], summary["answersKept"], records(SCRATCH / "live-replay.jsonl"),
           (summary["notUsedBecause"] or "").startswith(NOT_OVER_HTTP)), (["pair-class"] * 2, 0, [], True))
    # The same through the runner, as the replay ran: stand_in.run with the
    # stand-in transport's client naming the live server's endpoint.
    with stand_in.book(PAGES) as root:
        replay = Replay(live_endpoint)
        stand_in.run(root, replay, pages="1-3")
        report = json.loads((root / "report.json").read_text(encoding="utf-8"))["pairClassCache"]
        check("live server, the runner with a stand-in transport: the server identified, pairs asked, "
              "nothing kept in the run's store",
              (report["server"] is not None, report["answersAskedNow"] > 0, report["answersKept"],
               records(root / "pair-class.jsonl")), (True, True, 0, []))
    # The real client, its transport unchanged: kept, with the model id the
    # server's own response gave, and read back by a later run.
    store = pc.PairStore(SCRATCH / "live-real.jsonl")
    check("live server, the real client: the server's answer", classify(store, pp.Client(live_endpoint, "stand-in",
                                                                                          "xhigh", 30), "甲", "乙"),
          "variant")
    check("live server, the real client: both answers kept, with the server's model id",
          ([r.get("servedModel") for r in records(SCRATCH / "live-real.jsonl")], store.summary()["answersKept"],
           store.summary()["notUsedBecause"]), (["served-model", "served-model"], 2, None))
    store = pc.PairStore(SCRATCH / "live-real.jsonl")
    classify(store, pp.Client(live_endpoint, "stand-in", "xhigh", 30), "甲", "乙")
    check("live server, the real client again: both answers from the store",
          {k: store.summary()[k] for k in ("answersFromStore", "answersAskedNow")},
          {"answersFromStore": 2, "answersAskedNow": 0})
finally:
    process.kill()
    process.wait()

# --- another process on the port since the server was identified -----------------------
# The identity is worked out once and re-checked on every question, before it
# and after its answer.  The process it names must still be the one on the
# port: not one that stopped listening but lives on while another server (other
# weights) took the port, nor one that exec()ed another program on the same
# socket (same process, same start).  And a process that listens on the port
# itself, on another loopback address, may answer in the server's place (a
# proxy there): not trusted.  SWITCH is a model server of model-a or model-b
# (argv: weights, model, port, then what to exec into): SIGUSR1 stops its
# listening, SIGUSR2 exec()s the rest of its command line on the same socket.
SWITCH = "\n".join([
    "import json, os, signal, socket, sys, threading, time",
    "from http.server import BaseHTTPRequestHandler, HTTPServer",
    "model, port, then = sys.argv[2], int(sys.argv[3]), sys.argv[4:]",
    "class Handler(BaseHTTPRequestHandler):",
    "    def do_POST(self):",
    "        self.rfile.read(int(self.headers['Content-Length']))",
    "        answer = '判定：異體' if model == 'model-a' else '判定：不同'",
    "        raw = json.dumps({'model': model, 'choices': [{'message': {'content': answer}, 'finish_reason': 'stop'}],",
    "                          'usage': {'completion_tokens': 12}}).encode()",
    "        self.send_response(200)",
    "        self.send_header('Content-Length', str(len(raw)))",
    "        self.end_headers()",
    "        self.wfile.write(raw)",
    "    def log_message(self, *args):",
    "        pass",
    "inherited = int(os.environ.pop('SWITCH_FD', '-1'))",
    "if inherited >= 0:",
    "    server = HTTPServer(('127.0.0.1', 0), Handler, bind_and_activate=False)",
    "    server.socket.close()",
    "    server.socket = socket.socket(fileno=inherited)",
    "    server.server_address = server.socket.getsockname()",
    "else:",
    "    server = HTTPServer(('127.0.0.1', port), Handler)",
    "threading.Thread(target=server.serve_forever, daemon=True).start()",
    "def stop(*args):",
    "    server.shutdown()",
    "    server.server_close()",
    "def become(*args):",
    "    os.set_inheritable(server.socket.fileno(), True)",
    "    os.environ['SWITCH_FD'] = str(server.socket.fileno())",
    "    os.execv(sys.executable, [sys.executable, '-c', os.environ['SWITCH_SRC'], *then])",
    "signal.signal(signal.SIGUSR1, stop)",
    "signal.signal(signal.SIGUSR2, become)",
    "print(server.server_address[1], flush=True)",
    "while True:",
    "    time.sleep(1)",
])
assert os.sep not in SWITCH      # a word of the command line with no path in it
switch_dir = SCRATCH / "switch"
switch_dir.mkdir()
weights_file(switch_dir / "a.bin", b"model a" * 1000)
weights_file(switch_dir / "b.bin", b"model b" * 1000)
time.sleep(2.2)          # a file changed just before the start is not trusted


def switching(*arguments: str):
    """A SWITCH server in SCRATCH/switch, and the port it listens on."""
    started = subprocess.Popen([sys.executable, "-c", SWITCH, *arguments], cwd=switch_dir, stdout=subprocess.PIPE,
                               text=True, env={**os.environ, "SWITCH_SRC": SWITCH})
    return started, int(started.stdout.readline())


def by_server(path: Path, first: str) -> list:
    """Each answer kept: the model the server said answered, and whether it
    is kept under FIRST (the identity digest of the server first asked)."""
    return [(r.get("servedModel"), r["server"] == first) for r in records(path)]


servers = []
try:
    a_server, port = switching("a.bin", "model-a", "0")
    servers.append(a_server)
    endpoint = f"http://127.0.0.1:{port}/v1/chat/completions"
    client = pp.Client(endpoint, "stand-in", "xhigh", 30)
    store = pc.PairStore(SCRATCH / "switch.jsonl")
    classify(store, client, "甲", "乙")
    first = store.summary()["serverSha256"]
    a_server.send_signal(signal.SIGUSR1)
    for _ in range(100):                        # until A no longer accepts
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
        except (ConnectionRefusedError, ConnectionResetError):
            # A server closing its socket may reset a connection it had
            # queued instead of refusing it (1 run in 8 of this check).
            break
        time.sleep(0.05)
    b_server, _ = switching("b.bin", "model-b", str(port))
    servers.append(b_server)
    check("another server on the port: server A still identified until it stopped listening",
          (first is not None, a_server.poll()), (True, None))
    classify(store, client, "丙", "丁")
    check("another server on the port, server A alive but no longer listening: B's answers kept under B's "
          "identity, not A's", by_server(SCRATCH / "switch.jsonl", first),
          [("model-a", True), ("model-a", True), ("model-b", False), ("model-b", False)])

    a_server, port = switching("a.bin", "model-a", "0", "b.bin", "model-b", "0")
    servers.append(a_server)
    client = pp.Client(f"http://127.0.0.1:{port}/v1/chat/completions", "stand-in", "xhigh", 30)
    store = pc.PairStore(SCRATCH / "exec.jsonl")
    classify(store, client, "甲", "乙")
    first = store.summary()["serverSha256"]
    a_server.send_signal(signal.SIGUSR2)
    a_server.stdout.readline()                  # B is up on A's socket, in A's process
    classify(store, client, "丙", "丁")
    check("the server exec()s another program on the same socket (same process, same start): B's answers kept "
          "under B's identity, not A's", by_server(SCRATCH / "exec.jsonl", first),
          [("model-a", True), ("model-a", True), ("model-b", False), ("model-b", False)])

    a_server, port = switching("a.bin", "model-a", "0")
    servers.append(a_server)

    class Here(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - http.server's name
            self.rfile.read(int(self.headers["Content-Length"]))
            raw = json.dumps(stand_in.reply("判定：不同", model="this-process"), ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *_: object) -> None:
            pass

    here = HTTPServer(("127.0.0.2", port), Here)
    threading.Thread(target=here.serve_forever, daemon=True).start()
    urllib.request.install_opener(urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": f"http://127.0.0.2:{port}"})))
    try:
        store = pc.PairStore(SCRATCH / "here.jsonl")
        verdict = classify(store, pp.Client(f"http://127.0.0.1:{port}/v1/chat/completions", "stand-in", "xhigh", 30),
                           "甲", "乙")
        check("this process listening on the server's port at another loopback address (a proxy there): "
              "not trusted, nothing kept",
              (verdict, store.summary()["answersKept"], records(SCRATCH / "here.jsonl"),
               (store.summary()["notUsedBecause"] or "").startswith(f"this process listens on port {port} too")),
              ("different", 0, [], True))
    finally:
        urllib.request.install_opener(None)
        here.shutdown()
        here.server_close()
finally:
    for started in servers:
        started.kill()
        started.wait()

# --- the book profile ------------------------------------------------------------------

class BookModel(stand_in.StandIn):
    """The stand-in model; the pair question answered per pair and counted,
    by a model server in this process over HTTP (the real client asks it):
    the store keeps only answers that came over HTTP from the endpoint."""

    answers = {("甲", "乙"): "判定：異體", ("乙", "甲"): "判定：異體"}

    def __init__(self):
        super().__init__(census=0)
        self.pair_calls: list[str] = []
        self.wire = pp.Client(stand_in.served().endpoint(self.respond), "stand-in", None, 30)
        self.endpoint = self.wire.endpoint

    def respond(self, body):
        user_text = body["messages"][1]["content"][0]["text"]
        self.pair_calls.append(user_text)
        x, y = re.findall(r"「(.)」", user_text)
        return stand_in.reply(self.answers.get((x, y), "判定：不同"))

    def ask_answering(self, system, user_text, image_bytes, max_tokens, kind="other"):
        if system == pp.PAIR_SYSTEM:
            return self.wire.ask_answering(system, user_text, image_bytes, max_tokens, kind=kind)
        return super().ask_answering(system, user_text, image_bytes, max_tokens, kind)


class Known:
    """In place of LocalServer: the stand-in model's server is known."""

    def __init__(self, hashes, tag):
        pass

    def __call__(self, client):
        return {"stand-in": "book-server"}, None


def profile(root: Path, extra=()):
    new_process()
    model = BookModel()
    real_client, real_server = pp.Client, pc.LocalServer
    pp.Client, pc.LocalServer = (lambda *args, **kwargs: model), Known
    try:
        status = bp.main([str(root / "renders"), str(root / "a"), str(root / "b"), str(root / "book-profile.json"),
                          "--workers", "2", "--no-variant-vote", *extra])
    finally:
        pp.Client, pc.LocalServer = real_client, real_server
    assert status == 0, status
    return model, json.loads((root / "book-profile.json").read_text(encoding="utf-8"))


def comparable(profile: dict) -> dict:
    out = copy.deepcopy(profile)
    for key in ("generatedAt", "seconds", "cropsDirectory", "pairClassCache"):
        out.pop(key, None)
    return out


with stand_in.book(PAGES) as root:
    os.environ[pc.PATH_ENV] = str(root / "store.jsonl")
    off_model, off = profile(root, ["--no-pair-cache"])
    check("--no-pair-cache: the store is not touched", (root / "store.jsonl").exists(), False)
    check("--no-pair-cache: no record of a store in the profile", "pairClassCache" in off, False)
    check("--no-pair-cache: the pairs asked as before", sorted(off_model.pair_calls),
          sorted(["甲「甲」 乙「乙」", "甲「乙」 乙「甲」", "甲「辰」 乙「巳」", "甲「巳」 乙「辰」"]))
    cold_model, cold = profile(root)
    check("store, first run: the same questions and the same profile",
          (sorted(cold_model.pair_calls), comparable(cold)), (sorted(off_model.pair_calls), comparable(off)))
    check("store, first run: every answer kept",
          {k: cold["pairClassCache"][k] for k in ("answersAskedNow", "answersKept", "answersFromStore",
                                                  "pairsAskedNow", "pairsAllFromStore")},
          {"answersAskedNow": 4, "answersKept": 4, "answersFromStore": 0, "pairsAskedNow": 2, "pairsAllFromStore": 0})
    warm_model, warm = profile(root)
    kept = {r["question"]: r["at"] for r in records(root / "store.jsonl")}
    check("store, second run: no pair question asked, the same profile",
          (warm_model.pair_calls, comparable(warm) == comparable(off)), ([], True))
    check("store, second run: each pair's votes came from the store, with when each was kept",
          {pair: [(v["asked"], v["vote"], v["fromStore"]) for v in origin["votes"]]
           for pair, origin in warm["pairClassCache"]["pairs"].items()},
          {"甲|乙": [("甲|乙", "variant", kept["甲「甲」 乙「乙」"]), ("乙|甲", "variant", kept["甲「乙」 乙「甲」"])],
           "辰|巳": [("辰|巳", "different", kept["甲「辰」 乙「巳」"]), ("巳|辰", "different", kept["甲「巳」 乙「辰」"])]})
    check("store, second run: the server the answers are keyed to is in the profile",
          (warm["pairClassCache"]["server"], warm["pairClassCache"]["pairsAllFromStore"]),
          ({"stand-in": "book-server"}, 2))

    # --- phase 3 ---------------------------------------------------------------------
    # A fourth page with a pair the profile never met (午/未), whose two orders
    # disagree: phase 3 asks the model three times.
    stand_in.write_book(root, {4: ([stand_in.block("第四章罰則此事午國計甲", [0.3, 0.1, 0.4, 0.8])],
                                   "第四章罰則此事未國計乙")})
    BookModel.answers = {**BookModel.answers, ("午", "未"): "判定：異體", ("未", "午"): "唔肯定"}

    def phase3(name: str, extra=()):
        new_process()
        model = BookModel()
        real_client, real_server = pp.Client, pc.LocalServer
        pp.Client, pc.LocalServer = (lambda *args, **kwargs: model), Known
        try:
            status = pp.main([str(root / "renders"), str(root / "a"), str(root / name), "--draft2-directory",
                              str(root / "b"), "--profile", str(root / "book-profile.json"), "--pages", "1-4",
                              "--report", str(root / f"{name}.json"), *extra])
        finally:
            pp.Client, pc.LocalServer = real_client, real_server
        assert status == 0, status
        pages = {path.name: json.loads(path.read_text(encoding="utf-8")) for path in sorted((root / name).glob("*.json"))}
        texts = {path.name: path.read_text(encoding="utf-8") for path in sorted((root / name).glob("*.md"))}
        return model, pages, texts, json.loads((root / f"{name}.json").read_text(encoding="utf-8"))

    def sealed(pages: dict) -> dict:
        out = copy.deepcopy(pages)
        for record in out.values():
            # "calls": the page's call ledger, which counts the pair questions
            # now that they go through the real client, and which the store
            # makes smaller by design.
            for key in ("generatedAt", "seconds", "pairClassCache", "calls"):
                record.pop(key, None)
            record.get("provenance", {}).pop("jsonPayloadSha256", None)
        return out

    store_path = root / "phase3-store.jsonl"
    os.environ[pc.PATH_ENV] = str(store_path)
    off_model, off_pages, off_texts, off_report = phase3("off", ["--no-pair-cache"])
    check("phase 3 --no-pair-cache: asked as before, the store not touched, nothing sealed of it",
          (off_model.pair_calls, store_path.exists(),
           [n for n, r in off_pages.items() if "pairClassCache" in r], "pairClassCache" in off_report),
          (["甲「午」 乙「未」", "甲「未」 乙「午」", "甲「午」 乙「未」"], False, [], False))
    cold_model, cold_pages, cold_texts, cold_report = phase3("cold")
    check("phase 3, first run: the same questions, the same pages and seals but for the new record",
          (cold_model.pair_calls, cold_texts == off_texts, sealed(cold_pages) == sealed(off_pages)),
          (off_model.pair_calls, True, True))
    check("phase 3, first run: the page that used the pair lists its votes, asked now",
          {n: r["pairClassCache"] for n, r in cold_pages.items() if "pairClassCache" in r},
          {"page-0004.json": {"午|未": {"pair": "午|未", "verdict": "variant", "votes": [
              {"asked": "午|未", "vote": "variant", "fromStore": None},
              {"asked": "未|午", "vote": "different", "fromStore": None},
              {"asked": "午|未", "vote": "variant", "fromStore": None}]}}})
    check("phase 3, first run: the report's counts (the answer without a verdict line not kept)",
          {k: cold_report["pairClassCache"][k] for k in ("answersAskedNow", "answersKept", "answersNotKept",
                                                         "answersFromStore")},
          {"answersAskedNow": 3, "answersKept": 2, "answersNotKept": 1, "answersFromStore": 0})
    warm_model, warm_pages, warm_texts, warm_report = phase3("warm")
    kept = {(r["question"], r["n"]): r["at"] for r in records(store_path)}
    check("phase 3, second run: only the answer not kept is asked again, the same pages",
          (warm_model.pair_calls, warm_texts == off_texts, sealed(warm_pages) == sealed(off_pages)),
          (["甲「未」 乙「午」"], True, True))
    check("phase 3, second run: the page's votes say which came from the store, and when each was kept",
          [(v["asked"], v["fromStore"]) for v in warm_pages["page-0004.json"]["pairClassCache"]["午|未"]["votes"]],
          [("午|未", kept[("甲「午」 乙「未」", 0)]), ("未|午", None), ("午|未", kept[("甲「午」 乙「未」", 1)])])
    os.environ[pc.PATH_ENV] = str(SCRATCH / "never-used.jsonl")

# --- the stand-in harness and the machine's store ---------------------------------------
# stand_in.run() gives each run a store of its own beside the book, whatever
# the environment names: here none (PAIR_CACHE_PATH unset, so the default path
# is the store), with HOME a scratch directory so that the default path is one
# this check may look at.  The server is known and the pair answers come over
# HTTP, so the run keeps them: in its own store, and nothing at the default path.
check("the stand-in harness: importing it points the store at a temporary one of the process's own, "
      "and the default endpoint at a port nothing listens on",
      (stand_in.PRIVATE_STORE.parent.parent == Path(tempfile.gettempdir()),
       stand_in.PRIVATE_STORE != Path(pc.DEFAULT_PATH).expanduser(),
       os.environ.get("PROOFREAD_ENDPOINT"), pp.build_parser().parse_args(["r", "d", "o"]).endpoint),
      (True, True, stand_in.CLOSED_ENDPOINT, stand_in.CLOSED_ENDPOINT))
home = SCRATCH / "home"
home.mkdir()
saved_home, saved_store = os.environ.get("HOME"), os.environ.pop(pc.PATH_ENV, None)
os.environ["HOME"] = str(home)
try:
    with stand_in.book(PAGES) as root:
        new_process()
        model = BookModel()
        real_server = pc.LocalServer
        pc.LocalServer = Known
        try:
            stand_in.run(root, model, pages="1-3")
        finally:
            pc.LocalServer = real_server
        whole = json.loads((root / "report.json").read_text(encoding="utf-8"))
        report = whole["pairClassCache"]
        check("the stand-in harness: the run's store is its own, beside the book, and was used; "
              "its endpoint a port nothing listens on",
              (report["store"], report["answersKept"], len(records(root / "pair-class.jsonl")), whole["endpoint"]),
              (str(root / "pair-class.jsonl"), 4, 4, stand_in.CLOSED_ENDPOINT))
        check("the stand-in harness: the environment's store as it was after the run (none)",
              os.environ.get(pc.PATH_ENV), None)
finally:
    if saved_home is None:
        os.environ.pop("HOME", None)
    else:
        os.environ["HOME"] = saved_home
    os.environ[pc.PATH_ENV] = saved_store or str(SCRATCH / "never-used.jsonl")
check("the stand-in harness: nothing at the default path (HOME/.cache)", sorted(p.name for p in home.iterdir()), [])
# Every check that runs the scripts (their main(), or the scripts as processes)
# imports tests/offline.py, directly or through tests/stand_in.py, before it
# does: its runs and the processes it starts have a store of their own.
MAINS = re.compile(r"\b(?:pp|bp|book_profile|proofread_pages|variant_vote|vv)\.main\(")
SCRIPTS = re.compile(r"\b(?:proofread_pages|book_profile|variant_vote)\.py\b")
GUARDED = re.compile(r"^\s*(?:import (?:offline|stand_in)\b|from (?:offline|stand_in) import)", re.M)
sources = {path.name: path.read_text(encoding="utf-8") for path in Path(__file__).resolve().parent.glob("check_*.py")}
unguarded = sorted(name for name, text in sources.items()
                   if (MAINS.search(text) or ("subprocess" in text and SCRIPTS.search(text)))
                   and not GUARDED.search(text))
check("every check that runs the scripts imports tests/offline.py (a store of its own)", unguarded, [])

check("the machine's own store was never touched", (SCRATCH / "never-used.jsonl").exists(), False)
shutil.rmtree(SCRATCH, ignore_errors=True)
print(f"{'FAIL' if failures else 'ok  '} {failures} failure(s)")
sys.exit(1 if failures else 0)
