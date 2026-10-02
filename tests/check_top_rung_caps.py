#!/usr/bin/env python3
"""Offline checks of switch R2-C, --top-rung-caps KIND=N,... (off by default).

No model, no GPU, no HTTP, no corpus.  The real Client runs with its transport
replaced by a stand-in (Ladder, over Client._send): a request finishes when
its max_tokens reaches what its kind and effort need, and is cut off at
max_tokens otherwise, writing nothing - the shape of a runaway at the top
effort.  So Client.ask, the call ledger and Client.ask_answering's effort
ladder are the runner's own.

What the switch does: the first rung of a named kind - the client's own
effort, xhigh by default - is asked with at most N completion tokens; cut off
there, the ladder goes straight on to the next rung with the full max_tokens,
not to the same rung again.  Checked:

- an answer that finishes under N is the answer without the switch;
- a first rung cut at N goes to medium with the full max_tokens, and one
  that would have finished between N and max_tokens is answered by medium;
- kinds not named, a retry begun lower (ask_lower), a client with one rung
  and a call whose max_tokens is below N are asked as without the switch;
- a CALL_BUDGETS budget below N escalates to N at the same effort, not past
  it, and the rung after the cut has the full max_tokens even when the
  kind's budget is smaller;
- the ladder's bookkeeping (rungsAsked, rungsCutOff, degraded), no_answer's
  reason and the cut's note, when every rung is cut or the next rung answers
  empty;
- with a CALL_BUDGETS budget, the ledger marks only the ask at the cap, and
  the note counts the rungs as without a budget;
- the entries' order: by kind and place, not by the threads' timing;
- the page's call ledger and calls (earlyCut, earlyCutTokensSaved), its
  decisionChanges, its provenance and the run report, on a whole page
  (proofread_pages.main with the stand-in), and a page sealed under other
  caps is not current;
- where each entry says its cut call was (call_site): a 裁決 at its spot's
  crop, context, readings and place in the merged text - the main
  questions, D24's, D16's second look and a table character no engine read
  - even where the page's verdicts all answer alike; a punctuation pass at
  its block, range and tile; a comma's re-read at its gap;
- the flag's parsing, and that CALL_KINDS names every kind the runner and
  the book repair tool (scripts/_repair_questions.py) ask.

Usage:
    python3 tests/check_top_rung_caps.py
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import threading
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import proofread_pages as pp  # noqa: E402
import stand_in  # noqa: E402

failures = 0
RECOMMENDED = pp.parse_top_rung_caps(pp.TOP_RUNG_CAPS_RECOMMENDED)


def check(name: str, got, want) -> None:
    global failures
    if got != want:
        failures += 1
        print(f"FAIL {name}: got {got!r}, want {want!r}")
    else:
        print(f"ok   {name}")


class Ladder(pp.Client):
    """The runner's Client with a stand-in transport.  NEEDS maps (kind,
    effort) or kind to the completion tokens a request needs to finish (100
    by default), or is a function of (kind, effort, question text) to them;
    a request whose max_tokens is below it is cut off there, nothing
    written.  A finished request answers ANSWERS[(kind, effort)] ("" is an
    empty reply that finished on its own), else what the stand-in model for
    its effort (INNERS, by effort; "xhigh"'s by default) answers, else
    "答 <effort>".  SEEN: each request's (kind, max_tokens, effort)."""

    def __init__(self, *args, needs=None, answers=None, inners=None, **kwargs):
        super().__init__(*(args or ("stand-in", "stand-in", "xhigh", 30)), **kwargs)
        self.needs = needs if callable(needs) else dict(needs or {})
        self.answers = dict(answers or {})
        self.inners = dict(inners or {})
        self.seen: list[tuple[str, int, str]] = []
        self.lock = threading.Lock()

    def _send(self, body, kind):
        effort = body.get("reasoning_effort") or "none"
        with self.lock:
            self.seen.append((kind, body["max_tokens"], effort))
        need = (self.needs(kind, effort, body["messages"][1]["content"][0]["text"]) if callable(self.needs)
                else self.needs.get((kind, effort), self.needs.get(kind, 100)))
        if body["max_tokens"] < need:
            content, finish, used = "", "length", body["max_tokens"]
        elif (kind, effort) in self.answers:
            content, finish, used = self.answers[(kind, effort)], "stop", need
        elif self.inners:
            inner = self.inners.get(effort) or self.inners["xhigh"]
            system, user = body["messages"][0]["content"], body["messages"][1]["content"][0]["text"]
            content, finish, used = inner.ask_answering(system, user, None, body["max_tokens"], kind=kind)[0], "stop", need
        else:
            content, finish, used = f"答 {effort}", "stop", need
        return {"choices": [{"message": {"content": content}, "finish_reason": finish}],
                "usage": {"prompt_tokens": 10, "completion_tokens": used,
                          "completion_tokens_details": {"reasoning_tokens": max(0, used - 1)}}}, 0.0


def asked(caps, needs, kind="adjudicate", max_tokens=16000, effort="xhigh", answers=None, lower=None):
    """One ask_answering of KIND on a Ladder: (answer, metrics, requests seen)."""
    client = Ladder("stand-in", "stand-in", effort, 30, top_rung_caps=caps, needs=needs, answers=answers)
    if lower is not None:
        text, m = pp.ask_lower(client, lower, "s", "t", None, max_tokens, kind=kind)
    else:
        text, m = client.ask_answering("s", "t", None, max_tokens, kind=kind)
    return text, m, client.seen


def recorded(caps, needs, kind="adjudicate", **kwargs):
    """asked() with the page's call ledger and R2-C notes set: its answer,
    metrics and requests, each request's ledger marks (max_tokens, effort,
    topRungCap, earlyCut, earlyCutTokensSaved), the ledger and the notes."""
    ledger, notes = [], []
    pp._CALL_LEDGER.set(ledger)
    pp._EARLY_CUTS.set(notes)
    try:
        text, m, seen = asked(caps, needs, kind=kind, **kwargs)
    finally:
        pp._CALL_LEDGER.set(None)
        pp._EARLY_CUTS.set(None)
    marks = [(c["maxTokens"], c.get("effort"), c.get("topRungCap"), c.get("earlyCut"), c.get("earlyCutTokensSaved"))
             for c in ledger]
    return text, m, seen, marks, ledger, notes


def check_ladder() -> None:
    caps = {"adjudicate": 13000, "format": 13000, "format-retry": 13000}
    # Under the cap: the answer is the one without the switch.
    text, m, seen = asked(caps, {("adjudicate", "xhigh"): 12000})
    plain, plain_m, plain_seen = asked({}, {("adjudicate", "xhigh"): 12000})
    check("under the cap: one request, at the cap", seen, [("adjudicate", 13000, "xhigh")])
    check("... without the switch: one request, at max_tokens", plain_seen, [("adjudicate", 16000, "xhigh")])
    check("... the same answer", (text, m.get("completion_tokens")), (plain, plain_m.get("completion_tokens")))
    check("... no early cut, not degraded", ("earlyCut" in m, m.get("degraded")), (False, None))
    # A runaway: cut at the cap, then medium with the full max_tokens.
    text, m, seen = asked(caps, {("adjudicate", "xhigh"): 20000})
    check("a runaway: the cap, then medium with max_tokens", seen,
          [("adjudicate", 13000, "xhigh"), ("adjudicate", 16000, "medium")])
    check("... answered by medium", (text, m.get("effort"), m.get("earlyCut")), ("答 medium", "medium", 13000))
    check("... not degraded, no rung bookkeeping, no budget escalation",
          [key for key in ("degraded", "rungsAsked", "budgetEscalated") if key in m], [])
    check("... tokens summed over both rungs", m["completion_tokens"], 13000 + 100)
    _, _, plain_seen = asked({}, {("adjudicate", "xhigh"): 20000})
    check("... without the switch: xhigh to max_tokens, then medium", plain_seen,
          [("adjudicate", 16000, "xhigh"), ("adjudicate", 16000, "medium")])
    # Would have finished between the cap and max_tokens: answered a rung lower.
    text, m, seen = asked(caps, {("adjudicate", "xhigh"): 14000})
    plain, _, _ = asked({}, {("adjudicate", "xhigh"): 14000})
    check("finished between the cap and max_tokens: medium answers instead",
          (plain, text, [s[1:] for s in seen]), ("答 xhigh", "答 medium", [(13000, "xhigh"), (16000, "medium")]))
    # Exempt: a kind not named, as without the switch.
    _, m, seen = asked(caps, {("census", "xhigh"): 20000}, kind="census")
    check("a kind not named: as without the switch", seen,
          [("census", 16000, "xhigh"), ("census", 16000, "medium")])
    check("... no early cut", "earlyCut" in m, False)
    # Every rung cut: the bookkeeping is the ladder's, the cap one rung of it.
    text, m, seen = asked(caps, {"format": 20000}, kind="format")
    check("every rung cut: the cap, then the full max_tokens", [s[1:] for s in seen],
          [(13000, "xhigh"), (16000, "medium"), (16000, "low"), (16000, "none")])
    check("... rungsAsked 4, rungsCutOff 4, degraded",
          (m["rungsAsked"], m["rungsCutOff"], m["degraded"], m["earlyCut"]), (4, 4, True, 13000))
    check("... no_answer: cut at every effort", pp.no_answer(text, m),
          "no answer: cut off at the token budget at every effort, nothing written")
    *_, notes = recorded(caps, {"format": 20000}, kind="format")
    check("... its note: four rungs asked, none answered",
          [(n["rungsAsked"], n["degraded"], n["answeredAt"], n["answerTokens"], n["cutTokens"]) for n in notes],
          [(4, True, None, None, 13000)])
    # Cut at the cap, then an empty reply that finished on its own.
    text, m, seen = asked(caps, {("format", "xhigh"): 20000}, kind="format", answers={("format", "medium"): ""})
    check("cut at the cap, then an empty reply: two rungs, one cut",
          ([s[1:] for s in seen], m["rungsAsked"], m["rungsCutOff"], m["degraded"]),
          ([(13000, "xhigh"), (16000, "medium")], 2, 1, True))
    check("... no_answer says so", pp.no_answer(text, m),
          "no answer: cut off at the token budget at 1 effort(s), then an empty reply, nothing written")
    *_, notes = recorded(caps, {("format", "xhigh"): 20000}, kind="format", answers={("format", "medium"): ""})
    check("... its note: two rungs asked, none answered",
          [(n["rungsAsked"], n["degraded"], n["answeredAt"], n["answerTokens"]) for n in notes],
          [(2, True, None, None)])
    # A retry begun lower (ask_lower after a cut): its first rung is not the client's own.
    _, _, seen = asked(caps, {"format-retry": 20000}, kind="format-retry", lower=pp.NO_ANSWER_RETRY_EFFORT)
    check("a retry begun at low: no cap", [s[1:] for s in seen], [(16000, "low"), (16000, "none")])
    _, _, seen = asked(caps, {"format-retry": 20000}, kind="format-retry", lower="")
    check("a retry begun at the client's own rung: capped", [s[1:] for s in seen][:2],
          [(13000, "xhigh"), (16000, "medium")])
    # One rung (reasoning omitted): nothing below to go on to, no cap.
    _, _, seen = asked(caps, {"adjudicate": 20000}, effort=None)
    check("a client with one rung: no cap", seen, [("adjudicate", 16000, "none")])
    # The client's own effort is the first rung, whatever it is.
    _, _, seen = asked(caps, {("adjudicate", "medium"): 20000}, effort="medium")
    check("a client at medium: medium capped, then low", [s[1:] for s in seen], [(13000, "medium"), (16000, "low")])
    # A call whose max_tokens is at or below the cap: nothing to cap.
    _, _, seen = asked(caps, {("adjudicate", "xhigh"): 20000}, max_tokens=4000)
    check("max_tokens below the cap: as without the switch", [s[1:] for s in seen][:2],
          [(4000, "xhigh"), (4000, "medium")])


def check_call_budgets() -> None:
    saved = dict(pp.CALL_BUDGETS)
    caps = {"adjudicate": 13000}
    try:
        pp.CALL_BUDGETS.clear()
        pp.CALL_BUDGETS["adjudicate"] = 500
        _, m, seen, marks, ledger, notes = recorded(caps, {("adjudicate", "xhigh"): 20000})
        check("a budget below the cap escalates to the cap, not past it", [s[1:] for s in seen],
              [(500, "xhigh"), (13000, "xhigh"), (16000, "medium")])
        check("... escalated, then cut early", (m.get("budgetEscalated"), m.get("earlyCut")), (True, 13000))
        check("... the ledger marks the ask at the cap alone, cut, with what it left of max_tokens", marks,
              [(500, "xhigh", None, None, None), (13000, "xhigh", 13000, True, 3000),
               (16000, "medium", None, None, None)])
        check("... one early cut in the calls", {k: v for k, v in pp.summarize_calls(ledger)["adjudicate"].items()
                                                 if k.startswith("earlyCut")},
              {"earlyCut": 1, "earlyCutTokensSaved": 3000})
        check("... one note: the cut at the cap, two rungs asked",
              [(n["cap"], n["cutTokens"], n["rungsAsked"], n["answeredAt"], n["degraded"]) for n in notes],
              [(13000, 13000, 2, "medium", False)])
        _, m, seen, marks, _, notes = recorded(caps, {("adjudicate", "xhigh"): 800})
        check("... answered at the cap: no early cut", ([s[1:] for s in seen], "earlyCut" in m, notes),
              ([(500, "xhigh"), (13000, "xhigh")], False, []))
        check("... the ask at the cap marked, not cut", marks,
              [(500, "xhigh", None, None, None), (13000, "xhigh", 13000, None, None)])
        pp.CALL_BUDGETS["adjudicate"] = 14000
        _, _, seen, marks, _, notes = recorded(caps, {("adjudicate", "xhigh"): 20000,
                                                      ("adjudicate", "medium"): 15000})
        check("a budget above the cap: the rung after the cut has the full max_tokens",
              [s[1:] for s in seen], [(13000, "xhigh"), (16000, "medium")])
        check("... the cut at the cap marked", (marks, [n["rungsAsked"] for n in notes]),
              ([(13000, "xhigh", 13000, True, 3000), (16000, "medium", None, None, None)], [2]))
        pp.CALL_BUDGETS["census"] = 500
        _, _, seen = asked(caps, {("census", "xhigh"): 800}, kind="census")
        check("a kind not named keeps CALL_BUDGETS' escalation", [s[1:] for s in seen],
              [(500, "xhigh"), (16000, "xhigh")])
    finally:
        pp.CALL_BUDGETS.clear()
        pp.CALL_BUDGETS.update(saved)


def png() -> bytes:
    import io
    from PIL import Image
    out = io.BytesIO()
    Image.new("L", (40, 20), 255).save(out, "PNG")
    return out.getvalue()


def check_ledger() -> None:
    crop = png()
    client = Ladder("stand-in", "stand-in", "xhigh", 30, top_rung_caps={"adjudicate": 13000, "format": 13000},
                    needs={("adjudicate", "xhigh"): 20000, ("format", "xhigh"): 5000, ("census", "xhigh"): 20000})
    ledger, notes = [], []
    pp._CALL_LEDGER.set(ledger)
    pp._EARLY_CUTS.set(notes)
    try:
        for kind in ("adjudicate", "format", "census"):
            client.ask_answering("s", f"question {kind}", crop if kind == "adjudicate" else None, 16000, kind=kind)
    finally:
        pp._CALL_LEDGER.set(None)
        pp._EARLY_CUTS.set(None)
    marked = [(c["kind"], c["maxTokens"], c.get("topRungCap"), c.get("earlyCut"), c.get("earlyCutTokensSaved"))
              for c in ledger]
    check("ledger: the capped first rungs are marked, the cut one with what it left unspent", marked,
          [("adjudicate", 13000, 13000, True, 3000), ("adjudicate", 16000, None, None, None),
           ("format", 13000, 13000, None, None),
           ("census", 16000, None, None, None), ("census", 16000, None, None, None)])
    calls = pp.summarize_calls(ledger)
    check("calls: per capped kind, early cuts and tokens saved",
          {kind: (row.get("earlyCut"), row.get("earlyCutTokensSaved")) for kind, row in calls.items()},
          {"adjudicate": (1, 3000), "format": (0, 0), "census": (None, None)})
    check("calls: the rest of the row as without the switch", (calls["adjudicate"]["n"],
          calls["adjudicate"]["truncated"], calls["adjudicate"]["maxCompletion"]), (2, 1, 13000))
    check("one note, for the cut call", [(n["kind"], n["cap"], n["cutTokens"], n["answeredAt"], n["answerTokens"],
                                          n["rungsAsked"], n["degraded"], n["answer"]) for n in notes],
          [("adjudicate", 13000, 13000, "medium", 100, 2, False, "答 medium")])
    changes = pp.top_rung_changes(notes)
    check("its decisionChanges entry", [(c["decision"], c["rule"], c["switch"], c["kind"], c["before"], c["after"],
                                         c["afterBy"], c["evidence"]["cap"], c["evidence"]["maxTokens"])
                                        for c in changes],
          [("R2-C", "top-rung-cap", "--top-rung-caps", "adjudicate", None, "答 medium", "medium", 13000, 16000)])
    check("... the question is the crop's too", changes[0]["evidence"]["questionSha256"],
          __import__("hashlib").sha256("s".encode() + b"\0" + "question adjudicate".encode() + b"\0" + crop).hexdigest())
    # Off: no row carries the keys, nothing is noted.
    client = Ladder(needs={("adjudicate", "xhigh"): 20000})
    ledger, notes = [], []
    pp._CALL_LEDGER.set(ledger)
    pp._EARLY_CUTS.set(notes)
    try:
        client.ask_answering("s", "t", None, 16000, kind="adjudicate")
    finally:
        pp._CALL_LEDGER.set(None)
        pp._EARLY_CUTS.set(None)
    check("off: no early-cut keys, no notes",
          ([key for call in ledger for key in call if key.startswith(("topRung", "earlyCut"))], notes), ([], []))


def check_order() -> None:
    """The entries' order is the page's, by kind and then place, not the
    order in which the page's threads finished their calls."""
    client = Ladder(top_rung_caps={"adjudicate": 13000, "census": 13000},
                    needs={("adjudicate", "xhigh"): 20000, ("census", "xhigh"): 20000})
    notes = []
    pp._EARLY_CUTS.set(notes)
    try:
        for kind, where in (("census", {"block": 1, "mergedOffset": 0}), ("adjudicate", {"mergedOffset": 30}),
                            ("adjudicate", {}), ("adjudicate", {"mergedOffset": 5})):
            with pp.call_site(where):
                client.ask_answering("s", f"{kind} {where}", None, 16000, kind=kind)
    finally:
        pp._EARLY_CUTS.set(None)
    changes = pp.top_rung_changes(notes)
    check("entries by kind, then place, a call with no place last",
          [(c["kind"], c.get("mergedOffset")) for c in changes],
          [("adjudicate", 5), ("adjudicate", 30), ("adjudicate", None), ("census", 0)])
    check("... whatever order the calls ended in", [pp.top_rung_changes(notes[::-1]),
                                                     pp.top_rung_changes(notes[1:] + notes[:1])], [changes, changes])


def check_parse() -> None:
    check("the recommended value", RECOMMENDED, {"adjudicate": 13000, "format": 13000, "format-retry": 13000,
                                                 "punctuate": 15000, "punctuate-retry": 15000})
    check("sealed as KIND=N by kind", pp.top_rung_caps_text({"punctuate": 15000, "adjudicate": 13000}),
          "adjudicate=13000,punctuate=15000")
    for bad in ("adjudication=13000", "adjudicate", "adjudicate=0", "adjudicate=1.5", "adjudicate=-3",
                "adjudicate=13000,adjudicate=12000", "", "other=100"):
        try:
            pp.parse_top_rung_caps(bad)
            got = "accepted"
        except Exception as error:  # noqa: BLE001
            got = type(error).__name__
        check(f"refused: {bad!r}", got, "ArgumentTypeError")
    runner = (Path(pp.__file__)).read_text(encoding="utf-8")
    used = set(re.findall(r'kind="([a-z-]+)"', runner)) | set(re.findall(r'kind="([a-z-]+)" if', runner))
    used |= {"chart"}  # kind="chart-retry" if attempt else "chart"
    # The book repair tool asks with the same Client: its kinds are the
    # values of its CALL_KIND table.
    repair = (Path(pp.__file__).with_name("_repair_questions.py")).read_text(encoding="utf-8")
    table = re.search(r"^CALL_KIND = \{(.*?)\}", repair, re.M | re.S)
    used |= set(re.findall(r':\s*"(repair-[a-z-]+)"', table.group(1) if table else ""))
    check("CALL_KINDS names every kind the runner and the repair tool ask", sorted(used - set(pp.CALL_KINDS)), [])
    check("... and nothing else", sorted(set(pp.CALL_KINDS) - used), [])
    on = pp.decision_provenance(SimpleNamespace(top_rung_caps={"format": 13000, "adjudicate": 13000}))
    off = pp.decision_provenance(SimpleNamespace())
    check("provenance: the caps when on, nothing when off",
          (on.get("topRungCaps"), "topRungCaps" in off), ("adjudicate=13000,format=13000", False))
    check("... a key a resume compares when absent", "topRungCaps" in pp.OPTIONAL_PROVENANCE, True)


# A page with one numeral disagreement, which goes to 裁決 whatever the
# preference: engine A 二, engine B 三.
PAGE = {1: ([stand_in.block("民國十二年春三月天地玄黃宇宙洪荒", [0.10, 0.10, 0.80, 0.05])],
            "民國十三年春三月天地玄黃宇宙洪荒")}
# 裁決 at xhigh answers engine B's reading, at medium engine A's; at xhigh it
# finishes after NEEDS tokens.
INNERS = {"xhigh": stand_in.StandIn(census=0, judge=lambda a, b: b),
          "medium": stand_in.StandIn(census=0, judge=lambda a, b: a)}


def run_page(root: Path, extra=(), xhigh_needs=14000, overwrite=True):
    made = []

    def factory(*args, **kwargs):
        made.append(Ladder(*args, needs={("adjudicate", "xhigh"): xhigh_needs, ("format", "xhigh"): 5000},
                           inners=INNERS, **kwargs))
        return made[-1]

    engine_a = "\n".join(path.read_text(encoding="utf-8") for path in sorted((root / "a").glob("page-*.txt")))
    for inner in INNERS.values():
        inner.engine_a_text = engine_a
    real = pp.Client
    pp.Client = factory
    try:
        status = pp.main([str(root / "renders"), str(root / "a"), str(root / "out"),
                          "--draft2-directory", str(root / "b"), "--prefer-engine", "A", "--pages", "1",
                          "--reasoning-effort", "xhigh", "--report", str(root / "report.json"),
                          *(["--overwrite"] if overwrite else []), *extra])
    finally:
        pp.Client = real
    report = json.loads((root / "report.json").read_text(encoding="utf-8"))
    if not overwrite:
        # A resume: a page sealed under other decisions is blocked, not
        # written over (status 1).
        return status, report["counts"]
    assert status == 0, status
    record = json.loads((root / "out" / "page-0001.json").read_text(encoding="utf-8"))
    markdown = (root / "out" / "page-0001.md").read_text(encoding="utf-8")
    return record, markdown, report, made[0]


def r2c(record):
    return [change for change in record["decisionChanges"] if change["decision"] == "R2-C"]


def check_page() -> None:
    with stand_in.book(PAGE) as root:
        off, off_md, off_report, off_client = run_page(root)
        on, on_md, on_report, on_client = run_page(root, ["--top-rung-caps", pp.TOP_RUNG_CAPS_RECOMMENDED])
        under, under_md, _, _ = run_page(root, ["--top-rung-caps", "adjudicate=15000,format=13000"])
        runaway_off, runaway_off_md, _, _ = run_page(root, xhigh_needs=20000)
        runaway_on, runaway_on_md, _, _ = run_page(root, ["--top-rung-caps", "adjudicate=13000"], xhigh_needs=20000)
        # Resume: the page sealed with the caps is current under the same
        # caps, not under other caps nor without them; a page sealed without
        # them is not current with them.
        resumed = [run_page(root, extra, xhigh_needs=20000, overwrite=False)
                   for extra in (["--top-rung-caps", "adjudicate=13000"], ["--top-rung-caps", "adjudicate=12000"], [])]
        run_page(root, xhigh_needs=20000)
        resumed += [run_page(root, extra, xhigh_needs=20000, overwrite=False)
                    for extra in ([], ["--top-rung-caps", "adjudicate=13000"])]
    check("off: 裁決 at xhigh answers, engine B's 三", ("十三年" in off_md, "十二年" in off_md), (True, False))
    check("off: no R2-C entry, no provenance key, no early-cut keys in calls",
          (r2c(off), "topRungCaps" in off["provenance"],
           [key for row in off["calls"].values() for key in row if key.startswith("earlyCut")]), ([], False, []))
    check("off: the report says so", (off_report["topRungCaps"], off_report["topRungEarlyCuts"],
                                      off_report["pages"][0]["earlyCuts"]), ("off", {}, 0))
    check("on: xhigh would have finished at 14,000, cut at 13,000; medium answers engine A's 二",
          ("十二年" in on_md, "十三年" in on_md), (True, False))
    check("on: the requests", sorted({s for s in on_client.seen if s[0] in ("adjudicate", "format", "census")}),
          [("adjudicate", 13000, "xhigh"), ("adjudicate", 16000, "medium"), ("census", 16000, "xhigh"),
           ("format", 13000, "xhigh")])
    entries = r2c(on)
    check("on: one decisionChanges entry, for 裁決",
          [(c["rule"], c["switch"], c["kind"], c["before"], c["afterBy"], c["after"]) for c in entries],
          [("top-rung-cap", "--top-rung-caps", "adjudicate", None, "medium", "構件：略\n定案：十二\nRESEARCH: no")])
    check("... its evidence", {k: v for k, v in entries[0]["evidence"].items() if k != "questionSha256"},
          {"cap": 13000, "cutTokens": 13000, "maxTokens": 16000, "answerTokens": 100, "rungsAsked": 2,
           "degraded": False, "crop": "page-0001-adjudication-01.png"})
    check("... its place: the spot, as the adjudication record gives it, and where it stands in the text",
          place(entries[0]), spot(on["adjudications"][0], pp.CJK(on_md).index("十二年")))
    check("... the adjudication records medium's verdict", [a["verdict"] for a in on["adjudications"]],
          [entries[0]["after"].replace("\nRESEARCH: no", "").strip()])
    check("on: calls count the cut, a capped kind that finished has none",
          {kind: (row.get("earlyCut"), row.get("earlyCutTokensSaved")) for kind, row in on["calls"].items()},
          {"adjudicate": (1, 3000), "format": (0, 0), "census": (None, None)})
    check("on: sealed in provenance", on["provenance"].get("topRungCaps"), pp.TOP_RUNG_CAPS_RECOMMENDED)
    check("on: the report", (on_report["topRungCaps"], on_report["topRungEarlyCuts"],
                             on_report["pages"][0]["earlyCuts"], on_report["calls"]["adjudicate"]["earlyCut"],
                             on_report["decisionChanges"].get("R2-C")),
          (pp.TOP_RUNG_CAPS_RECOMMENDED,
           {"adjudicate": {"earlyCut": 1, "earlyCutTokensSaved": 3000},
            "format": {"earlyCut": 0, "earlyCutTokensSaved": 0},
            "format-retry": {"earlyCut": 0, "earlyCutTokensSaved": 0},
            "punctuate": {"earlyCut": 0, "earlyCutTokensSaved": 0},
            "punctuate-retry": {"earlyCut": 0, "earlyCutTokensSaved": 0}}, 1, 1, 1))
    check("under the cap: the page as without the switch",
          (under_md, under["adjudications"], r2c(under)), (off_md, off["adjudications"], []))
    check("a runaway: the same page with and without the switch (medium answers both ways)",
          (runaway_on_md, runaway_on["adjudications"]), (runaway_off_md, runaway_off["adjudications"]))
    check("... the switch recorded where it cut", [c["evidence"]["cutTokens"] for c in r2c(runaway_on)], [13000])
    check("... and the calls it saved", runaway_on["calls"]["adjudicate"]["completionTokens"],
          runaway_off["calls"]["adjudicate"]["completionTokens"] - 3000)
    check("resume: sealed with caps, current under the same caps only; sealed without, current without only",
          [(status, counts["skippedCurrent"], counts["blocked"]) for status, counts in resumed],
          [(0, 1, 0), (1, 0, 1), (1, 0, 1), (0, 1, 0), (1, 0, 1)])
    for name, extra in (("a cap at --max-tokens", ["--top-rung-caps", "adjudicate=16000"]),
                        ("caps with no rung below the client's", ["--top-rung-caps", "adjudicate=13000",
                                                                  "--reasoning-effort", "none"])):
        with stand_in.book(PAGE) as root:
            status = pp.main([str(root / "renders"), str(root / "a"), str(root / "out"),
                              "--draft2-directory", str(root / "b"), "--prefer-engine", "A", *extra])
            check(f"refused: {name}", (status, (root / "out" / "page-0001.json").exists()), (2, False))


def run_cut(pages, model, caps=None, runaway=lambda kind, text: True, profile=None):
    """PAGES (stand_in.book) proofread by the runner's Client over the stand-in
    MODEL: the xhigh rung of every call RUNAWAY picks (by kind and question
    text) reasons on past max_tokens, cut off wherever it is asked; every
    other request finishes and MODEL answers it, whatever its effort.  CAPS:
    a --top-rung-caps value, None for the switch off.  Returns the page's
    record and Markdown."""
    def factory(*args, **kwargs):
        return Ladder(*args, needs=lambda kind, effort, text: 10 ** 9 if effort == "xhigh" and runaway(kind, text)
                      else 100, inners={"xhigh": model}, **kwargs)

    with stand_in.book(pages, profile=profile) as root:
        model.engine_a_text = "\n".join(path.read_text(encoding="utf-8")
                                        for path in sorted((root / "a").glob("page-*.txt")))
        real = pp.Client
        pp.Client = factory
        try:
            status = pp.main([str(root / "renders"), str(root / "a"), str(root / "out"),
                              "--draft2-directory", str(root / "b"),
                              *(["--profile", str(root / "profile.json")] if profile else ["--prefer-engine", "A"]),
                              "--pages", "1", "--reasoning-effort", "xhigh", "--overwrite",
                              "--report", str(root / "report.json"),
                              *(["--top-rung-caps", caps] if caps else [])])
        finally:
            pp.Client = real
        assert status == 0, status
        record = json.loads((root / "out" / "page-0001.json").read_text(encoding="utf-8"))
        return record, (root / "out" / "page-0001.md").read_text(encoding="utf-8")


def place(change):
    """Where an R2-C entry says its call was: its place and, from its
    evidence, what of its call's site is not a place (crop, range, tile, gap)."""
    return ({key: change[key] for key in pp.SITE_PLACE_KEYS if key in change},
            {key: change["evidence"][key] for key in ("crop", "range", "tile", "gap") if key in change["evidence"]})


def spot(adjudication, merged_offset, block=0, engine_b=None):
    """The place an adjudication record gives its spot, as an R2-C entry of a
    call on it should say it."""
    return ({"block": adjudication.get("block", block), "contextBefore": adjudication["context_before"],
             "contextAfter": adjudication["context_after"], "engineA": adjudication["draft_reading"],
             "engineB": adjudication["writer_reading"] if engine_b is None else engine_b,
             "mergedOffset": merged_offset}, {"crop": adjudication["crop"]})


# Three 裁決 on one page that all answer 算, one of them decision D24's: engine
# A read 筍 where engine B wrote a rare codepoint twice, and 筍 once more in a
# stretch engine B did not read.
P1, P2, P3 = "天地玄黃宇宙洪荒日月盈昃辰宿列張", "寒來暑往秋收冬藏閏餘成歲律呂調陽", "雲騰致雨露結為霜金生麗水玉出崑岡"
ONLY_A, P4 = "劍號巨闕珠筍夜光果珍李柰", "菜重芥薑海鹹河淡鱗潛羽翔龍師火帝"
SUAN = {1: ([stand_in.block(P1 + "珠筍" + P2 + "筍法" + P3 + ONLY_A + P4, [0.3, 0.1, 0.4, 0.8])],
            P1 + "珠𮅕" + P2 + "𮅕法" + P3 + P4)}
# Where each 筍 stands in the merged text.
SUAN_AT = [len(P1) + 1, len(P1 + "珠筍" + P2), len(P1 + "珠筍" + P2 + "筍法" + P3) + ONLY_A.index("筍")]


def check_places() -> None:
    """A cut call's entry says where its answer went, as every decisionChanges
    entry does: the entry of a call on a spot ties to its adjudication record
    (its crop, context, readings) and to its place in the merged text; a
    punctuation pass's to its punctuationPasses record; a comma re-read's to
    its gap.  And the switch changes nothing else: here medium answers as
    xhigh would have."""
    judge = stand_in.StandIn(census=0, judge=lambda a, b: a.replace("筍", "算") if b in ("𮅕", "算") else a)
    off, off_md = run_cut(SUAN, judge)
    on, on_md = run_cut(SUAN, judge, "adjudicate=13000")
    adjudications = on["adjudications"]
    check("three 裁決, one of them D24's, all answering 算", ([a.get("askedFor") for a in adjudications],
          {a["verdict"] for a in adjudications}, [pp.CJK(on_md)[at] for at in SUAN_AT]),
          ([None, None, "D24"], {"構件：略\n定案：算"}, ["算"] * 3))
    check("... the page as without the switch", (on_md, adjudications), (off_md, off["adjudications"]))
    check("... each entry at its own spot: crop, context, readings and place in the merged text",
          [place(c) for c in r2c(on)],
          [spot(adjudications[0], SUAN_AT[0]), spot(adjudications[1], SUAN_AT[1]),
           spot(adjudications[2], SUAN_AT[2], engine_b="")])
    check("... D24's as its D24 entry gives it", place(r2c(on)[2])[0],
          {key: c[key] for c in on["decisionChanges"] if c["decision"] == "D24" for key in pp.SITE_PLACE_KEYS})
    # One of the three cut: its entry says which, though its answer is all three's.
    one, _ = run_cut(SUAN, judge, "adjudicate=13000", runaway=lambda kind, text: "下文：法" in text)
    check("one cut of three answering alike: its entry names its spot",
          ([c["after"] for c in r2c(one)], [place(c) for c in r2c(one)]),
          (["構件：略\n定案：算\nRESEARCH: no"], [spot(one["adjudications"][1], SUAN_AT[1])]))

    # D16's second look at a 無 whose reading stands nearby (confirm_nothing):
    # the coverage read is at the spot its 裁決 was.
    body, body2 = "天地玄黃宇宙洪荒日月盈昃辰宿列張寒來暑往秋收冬藏", "閏餘成歲律呂調陽雲騰致雨露結爲霜金生麗水玉出崑岡"
    printed = body + "茲奉大總統令着大總統府秘書長即日到任" + body2
    skipped = body + "茲奉大總統令着府秘書長即日到任" + body2
    pages = {1: ([stand_in.block(skipped, [0.3, 0.1, 0.4, 0.8])], printed)}
    nothing = stand_in.StandIn(census=0, judge=lambda a, b: "無")
    off, off_md = run_cut(pages, nothing, profile={"preferEngine": "adjudicate"})
    on, on_md = run_cut(pages, nothing, "adjudicate=13000,coverage-read=13000", profile={"preferEngine": "adjudicate"})
    [adjudication] = on["adjudications"]
    check("D16's coverage read: the page as without the switch",
          (on_md, adjudication["resolved_from"], "coverageRead" in adjudication),
          (off_md, "adjudicator-empty", True))
    check("... 裁決 and the coverage read, each at the spot",
          [(c["kind"], place(c)) for c in r2c(on)],
          [(kind, spot(adjudication, len(body + "茲奉大總統令着"))) for kind in ("adjudicate", "coverage-read")])

    # A character no engine read, confirmed by 裁決 on its own crop in a
    # rebuilt table (headerCharacters): its block and context as its
    # adjudication record gives them, and where the table's region begins
    # (the region's first block is the body, before the header holding it).
    first, second = "第一種讀本每課可供一小時", "第二種讀本每頁可習寫三日"
    prose = ("右表所列各本均係本年新頒之書其用法詳見各本卷首凡例之中此處不贅"
             "凡塾中教員務須先將各本通讀一過然後按表所定年期逐課教授勿稍躐等")
    pages = {1: ([stand_in.block(prose, [0.70, 0.10, 0.25, 0.80]),
                  stand_in.block(first + second, [0.10, 0.20, 0.52, 0.70], "vertical_text"),
                  stand_in.block("書名册全數書課每數册年備期用敎授要", [0.60, 0.20, 0.06, 0.60], "vertical_text")],
                 prose + "書名全書册數每册課數備用年期" + second + first)}
    region = (f"| 書名 | 全書册數 | 每册課數 | 備用年期 | 敎授要言 |\n| --- | --- | --- | --- | --- |\n"
              f"| {first[:5]} | {first[5:]} | {second[:5]} | {second[5:]} | |")
    table = stand_in.StandIn(census=0, judge=lambda a, b: "言" if (a, b) == ("", "言") else a or "無",
                             rebuild=lambda text: region if "書名" in text else f"| {first} |\n| --- |\n| {second} |")
    off, off_md = run_cut(pages, table)
    on, on_md = run_cut(pages, table, "adjudicate=13000")
    [header] = [c for c in on["decisionChanges"] if c["decision"] == "headerCharacters"]
    check("a table character no engine read: the page as without the switch",
          (on_md, "敎授要言" in on_md, [(a.get("askedFor"), a.get("block")) for a in on["adjudications"]],
           header["block"], header["mergedOffset"]), (off_md, True, [("headerCharacters", 2)], 1, len(prose)))
    check("... its 裁決 at the spot's block and context, and where the table's entries put the region",
          [place(c) for c in r2c(on)], [spot(on["adjudications"][0], len(prose), engine_b="")])

    # Punctuation: each block's census and punctuate at its pass, as its
    # punctuationPasses record gives it; a comma re-read at its gap.
    texts = ["天地玄黃宇宙洪荒日月盈昃", "辰宿列張寒來暑往秋收冬藏", "閏餘成歲律呂調陽雲騰致雨"]

    def punctuate(span: str) -> str:
        return span[:3] + ("，" if span == texts[1] else "") + span[3:6] + "。" + span[6:] + "。。"

    pages = {1: ([stand_in.block(t, [0.85 - 0.12 * i, 0.1, 0.06, 0.6]) for i, t in enumerate(texts)], "".join(texts))}
    marks = stand_in.StandIn(census=2, punctuate=punctuate, gap="。")
    caps = "census=13000,punctuate=13000,gap-recheck=13000"
    # The last block is punctuated in two column groups.
    real_tiles = pp.block_tiles
    pp.block_tiles = lambda render, block, n, limit=pp.TILE_CHARACTERS: (
        [(png(), 0, 6), (png(), 6, 12)] if block["text"] == texts[2] else None)
    try:
        off, off_md = run_cut(pages, marks)
        on, on_md = run_cut(pages, marks, caps)
    finally:
        pp.block_tiles = real_tiles
    passes = on["punctuationPasses"]
    check("punctuation: the page as without the switch, the comma re-read to a circle, the last block in two",
          (on_md, [(p["block"], p["range"], p.get("tile"), p.get("gapRechecks")) for p in passes]),
          (off_md, [(0, [0, 12], None, None), (1, [0, 12], None, [{"gap": 3, "before": "，", "after": "。"}]),
                    (2, [0, 6], 0, None), (2, [6, 12], 1, None)]))
    starts = [len("".join(texts[:p["block"]])) for p in passes]
    check("... each pass's census and punctuate at the pass",
          [(c["kind"], place(c)) for c in r2c(on) if c["kind"] in ("census", "punctuate")],
          [(kind, ({"block": p["block"], "mergedOffset": start + p["range"][0]},
                   {"range": p["range"], **({"tile": p["tile"]} if "tile" in p else {})}))
           for kind in ("census", "punctuate") for p, start in zip(passes, starts)])
    check("... the comma's re-read at its gap", [place(c) for c in r2c(on) if c["kind"] == "gap-recheck"],
          [({"block": 1, "mergedOffset": len(texts[0]) + 3}, {"gap": 3})])


def main() -> int:
    check_ladder()
    check_call_budgets()
    check_ledger()
    check_order()
    check_parse()
    check_page()
    check_places()
    print(f"{'FAIL' if failures else 'ok  '} {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
