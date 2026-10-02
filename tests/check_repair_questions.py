#!/usr/bin/env python3
"""Offline check of the book repair tool's questions to the model
(scripts/_repair_questions.py) through scripts/repair_book.py.

No GPU, no model server, no corpus: made-up books (tests/repair_fixture.py,
with the pages the other repair checks lay out for their rules) and a
stand-in model that answers each question as the check says; the real
Client is checked against a model server in this process (tests/stand_in.py's
Served), never the machine's.

- the prompts are 粵文 and end with the fixed answer line; the parser reads
  無 and the other EMPTY_VERDICTS (a 無 an engine read there is the
  character), figures and marks as the page writes them, a damaged
  character, 睇唔清, and nothing from a reply without its answer line;
- a crop masks the running head's band (not for a question about the band),
  and a thin crop is padded to the server's aspect limit; engine A's cells
  stand on their glyphs (a figure's cell, a full stop set close under its
  character, touching glyphs, uneven spacing);
- print questions (Q-P) on the marks rules' pages: an answer is written
  between its anchors, its line structure kept, and logged with the
  question, its answer and its crop; G1 (no answer line; a reply cut off on
  every rung), G2 (the question's own words), G5 (a character no engine
  read), G6 (a figure that does not go on from its list) refuse, each a
  `look-refused` doubt and no edit;
- glyph questions (Q-G): a blind answer that is an engine's reading is
  written after one call; one that is neither engine's asks the question a
  second time with the candidates, whose answer is written when it names
  one or says the print is damaged, and is a doubt otherwise; G2 (too long),
  G3 (a neighbour's character), G4 (the running head's character next to
  the band) refuse;
- copies (Q-L) of a page printed right to left: a character no engine read
  there (at its place: not anywhere on the line) is written only when a
  glyph question on its cell agrees, or, where that question reads another
  character, when a second round with the two readings names one; each line
  of engine A's block of two lines has its own row of cells;
- layout (Q-Y): a run-in lead becomes its paragraph's start, a heading
  stays; a line break becomes one paragraph or two; a numeral before a
  block opens a new paragraph;
- boundaries (Q-B): an answer settles the label (verified, rule Q-B, no
  `boundary-unverified` doubt); 睇唔清 leaves it `paragraph`, unverified;
- G7: two answers over the same text - the first question's is written, the
  second is a `conflict` doubt; a site an edit changed after the question
  was planned is a `conflict` doubt; a site moved by an edit is found; two
  questions about one site are asked once;
- --verify-sample's print question over a rule's edit writes nothing, and
  one that reads otherwise is a `verify-disagrees` doubt;
- what an answer may not delete or write: a figure before a unit's title
  that is not the contents' number (G6, the figure just before the anchor),
  while units' numbers no engine read, asked in one round, are written
  where they are the contents' numbers, two-figure ones too (G6, G2);
  nothing printed where the page and both engines each hold a character
  they read two ways (G5); a full stop the page and engine A both hold
  between the anchors (G5); a copy with no character, or one leaving out a
  character of a line only engine A read (Q-L); a heading's or list item's
  marker (a figure answer opening a heading keeps its `### `); 續文 at a
  page opening with a heading engine A reads further down the page (a
  doubt, the heading kept) - and at one engine A reads first (a join); the
  marks a furniture deletion left are asked after the deletion, and an
  answer writing the deleted suffix again is refused (G4);
- a paragraph question names the place its answer breaks (a P7 site's
  start); snap takes one glyph's run of ink, not two glyphs run together;
- units numbered `n.`: S7 moves a date with the comma before it that
  neither engine read (one engine A or engine B read stays); S4 asks about a unit number
  with no mark between units that carry one, the answer written;
- F8: a character both engines read at a page's head or foot, lost from
  the page, is a glyph question at the edge, its answer written there (at
  the foot before the mark engine A reads after it);
- K14: a stand-in glyph no rule settled is asked (bounded: a longer run of
  stand-ins is not), its answer written, G5 refusing a character no engine
  read and an answer that deletes the stand-in;
- a contents entry's number printed at its column's head, above the block
  engine A read its title in: the print question's crop takes it in, the
  question carries the mark its group's numbers print, and an answer
  reading the number with a colon-like mark writes that mark, a space
  before the title; where engine A's box cuts the number at its top, the
  tick before the title stands below the number, above the title;
- --resume asks nothing it holds: a run stopped by the model server (exit
  6) keeps its answers, and the resumed run asks only the rest and writes
  the same book; a resumed run of a finished one asks nothing; with
  --no-model it uses the answers held and lists the rest (model.unasked);
- the real Client, over HTTP: every request at xhigh with max_tokens 16000,
  a reply cut off at the budget asked again a rung lower, the ledger's
  kinds the repair-* kinds.

Usage:
    python3 tests/check_repair_questions.py
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import threading
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import offline  # noqa: E402,F401 - first: the private store and the closed endpoint
import repair_fixture as fx  # noqa: E402
import check_repair_boundaries as cb  # noqa: E402
import check_repair_rules as cr  # noqa: E402
import check_repair_structure as cs  # noqa: E402
import stand_in  # noqa: E402

sys.path.insert(0, str(HERE.parent / "scripts"))
import proofread_pages as pp  # noqa: E402
import _repair_edits as re_  # noqa: E402
import _repair_inputs as ri  # noqa: E402
import _repair_model as rm  # noqa: E402
import _repair_questions as rq  # noqa: E402
import _repair_rules as rr  # noqa: E402
import _repair_structure as rs  # noqa: E402
import repair_book  # noqa: E402


FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    print(f"{'ok  ' if condition else 'FAIL'} {message}")
    if not condition:
        FAILURES.append(message)


class Model:
    """A stand-in for phase 3's Client: each call is answered by REPLY(kind,
    system, user, crop), a reply or (reply, metrics)."""

    model, effort, temperature = "stand-in", "xhigh", 0.0

    def __init__(self, reply: Callable[[str, str, str, bytes], Any]):
        self.reply = reply
        self.calls: list[dict[str, Any]] = []
        self.lock = threading.Lock()

    def ask_answering(self, system: str, user: str, crop: bytes | None, max_tokens: int,
                      kind: str = "other") -> tuple[str, dict[str, Any]]:
        with self.lock:
            self.calls.append({"kind": kind, "system": system, "user": user, "crop": crop,
                               "maxTokens": max_tokens, "hash": rq.call_hash(system, user, crop or b"")})
        out = self.reply(kind, system, user, crop or b"")
        text, metrics = out if isinstance(out, tuple) else (out, {})
        return text, {"prompt_tokens": 3, "completion_tokens": 5, "effort": "xhigh", "finish_reason": "stop",
                      **metrics}


class Result:
    def __init__(self, status: int, out: Path, book: Path, model: Model | None):
        self.status = status
        self.out = out
        self.book = book
        self.model = model
        self.report = json.loads((out / "repair-report.json").read_text(encoding="utf-8"))
        log = out / "repair-log.jsonl"
        self.log = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.is_file() else []
        self.questions = json.loads((out / "questions.json").read_text(encoding="utf-8"))
        self.doubts = json.loads((out / "doubts.json").read_text(encoding="utf-8"))
        self.pages = {int(p.stem.split("-")[1]): p.read_text(encoding="utf-8") for p in (out / "pages").glob("*.md")}
        self.sealed = {scan: (book / "proofread" / f"page-{scan:04d}.md").read_text(encoding="utf-8")
                       for scan in self.pages}
        labels = out / "boundaries.json"
        self.labels = {int(k): v for k, v in json.loads(labels.read_text(encoding="utf-8"))["boundaries"].items()} \
            if labels.is_file() else {}
        evidence = out / "boundary-evidence.json"
        self.evidence = json.loads(evidence.read_text(encoding="utf-8"))["boundaries"] if evidence.is_file() else {}

    def question(self, page: int, rule: str, kind: str | None = None) -> dict[str, Any]:
        found = [q for q in self.questions if q["page"] == page and q.get("rule") == rule
                 and (kind is None or q["kind"] == kind)]
        assert found, (page, rule, [(q["page"], q.get("rule")) for q in self.questions])
        return found[0]

    def doubts_of(self, question: str) -> list[dict[str, Any]]:
        return [d for d in self.doubts if d.get("question") == question]

    def edits_of(self, question: str) -> list[dict[str, Any]]:
        return [r for r in self.log if r.get("question") == question]


def repair(book: Path, out: Path, model: Model | None, *argv: str) -> Result:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        status = repair_book.main(["--workers", "1", str(book), "--output", str(out), *argv], client=model)
    return Result(status, out, book, model)


def planned(book: Path, out: Path, *argv: str) -> list[dict[str, Any]]:
    """The questions a run plans, with their calls' hashes (--plan-only)."""
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        repair_book.main(["--workers", "1", str(book), "--output", str(out), "--plan-only", *argv])
    return json.loads((out / "questions.json").read_text(encoding="utf-8"))


def by_question(questions: list[dict[str, Any]], table: dict[tuple[int, str], Any] | Callable[[dict], Any],
                default: Callable[[str, str, str, bytes], Any]) -> Callable[[str, str, str, bytes], Any]:
    """A reply function: the reply TABLE gives a question's first call - by
    its (page, rule), or a function of the planned question - found by the
    call's hash in the plan; DEFAULT for every other call."""
    replies = {}
    for q in questions:
        found = table(q) if callable(table) else table.get((q["page"], q.get("rule")))
        if found is not None and q.get("hash"):
            replies[q["hash"]] = found

    def reply(kind: str, system: str, user: str, crop: bytes) -> Any:
        found = replies.get(rq.call_hash(system, user, crop))
        return found if found is not None else default(kind, system, user, crop)
    return reply


def same_answers(kind: str, system: str, user: str, crop: bytes) -> Any:
    """What the stand-in answers when the check does not say: the page is
    right (a print question: nothing between the anchors is no answer; a
    boundary: a new paragraph)."""
    return {"repair-glyph": "定案：睇唔清", "repair-print": "印刷：睇唔清", "repair-line": "印刷：睇唔清",
            "repair-layout": "答：睇唔清", "repair-boundary": "答：另起一段"}[kind]


# --- prompts and the parser ---------------------------------------------------------------

CANTONESE = re.compile(r"[係嘅咗唔喺乜]")
FIXED = re.compile(r"^最後一行一模一樣寫：`(定案|印刷|答)：")


def prompt_checks() -> None:
    prompts = {
        "Q-G": rq.glyph_user("一個字位", "春風", "吹過"),
        "Q-G across": rq.glyph_user("一個字位", "春風", "吹過", across=True),
        "Q-G second round": pp.adjudicate_prompt({"before": "春風", "after": "吹過", "a": "國", "b": "圖"},
                                                 note=rq.GLYPH_ROUND_TWO_NOTE),
        "Q-P": rq.print_user("春風", "吹過", 2),
        "Q-L": rq.line_user(1, True),
        "Q-L title": rq.title_end_user("春日遊記"),
        "Q-Y heading": rq.heading_user("甲、春耕"),
        "Q-Y paragraph": rq.paragraph_user("春風", "吹過", 2, True),
        "Q-B": rq.boundary_user(2, True),
    }
    for name, text in prompts.items():
        last = text.strip().splitlines()[-1]
        fixed = FIXED.match(last) or (name == "Q-G second round" and last.endswith("`定案：<字>`"))
        check(bool(CANTONESE.search(text)) and bool(fixed),
              f"prompt {name}: 粵文, and its last line names the fixed answer line ({last!r})")
    check(bool(CANTONESE.search(rq.REPAIR_SYSTEM)) and "唔好估" in rq.REPAIR_SYSTEM,
          "the questions' system prompt is 粵文 and says not to guess")
    check("印壞" in prompts["Q-G second round"] and "甲) 國" in prompts["Q-G second round"],
          "the second glyph round is phase 3's 裁決 question with the candidates, and says how to write damaged "
          "print")

    def parsed(kind: str, raw: str, readings: tuple[str, ...] = ()) -> tuple[Any, ...]:
        p = rq.parse(kind, raw, readings)
        return p.value is not None, p.empty, p.unsure, p.text, sorted(p.damaged)
    check(all(parsed("Q-G", f"構件：略\n定案：{v}\nRESEARCH: no")[1] for v in pp.EMPTY_VERDICTS)
          and all(parsed("Q-P", f"印刷：{v}")[1] for v in pp.EMPTY_VERDICTS),
          "every EMPTY_VERDICTS answer says nothing is printed (a RESEARCH line after the answer set aside)")
    check(parsed("Q-G", "定案：無", ("無",)) == (True, False, False, "無", []),
          "無 that an engine read at the place is the character")
    check([parsed("Q-P", f"印刷：{v}")[3] for v in ("( 3 )", "３．", "︵二︶", "｜｜", "—", "•", "「一」，")]
          == ["（3）", "3.", "（二）", "——", "—", "·", "「一」，"],
          "figures and marks as the page writes them: brackets full width, a dash run by its length, the dot ·")
    check(parsed("Q-G", "構件：…\n`定案：國（印壞）`") == (True, False, False, "國", [0])
          and parsed("Q-L", "印刷：春風（印壞）吹")[4] == [1],
          "a damaged character is read with its place")
    check(parsed("Q-Y", "答：睇唔清")[2] and parsed("Q-P", "印刷：睇唔清")[2], "睇唔清 is an answer that settles nothing")
    gaps = [rq.print_gap(gap, answer) for gap, answer in (
        ("丁丶", "（2），"),                    # no line break: the answer as it stands
        ("丁\n\n", "——"),                     # print before the break only: it stays there
        ("\n\n### 丁 ", "3."),                # print after a heading marker only: after it, the space kept
        ("。\n\n丁", "。2."),                  # print on both sides: closing marks before, the rest after
        ("。\n\n丁", ""),                     # nothing printed: the line break alone
        ("\n\n### ", "1"),                   # the gap ends with a heading's marker: its space is the marker's
        ("。\n\n### ", "。1"),                # ... and a figure after the full stop opens the heading
        ("\n- ", "6."))]                      # a list item's marker kept
    check(gaps == ["（2），", "——\n\n", "\n\n### 3. ", "。\n\n2.", "\n\n", "\n\n### 1", "。\n\n### 1", "\n- 6."],
          f"a print answer replaces the gap's print where it stands, the page's line structure kept ({gaps})")
    check(not parsed("Q-G", "紅框入面係國字。")[0] and not parsed("Q-P", "印刷：（1）\n以上係答案")[0],
          "a reply whose last line is not the answer line has no answer")


def crop_checks(tmp: Path) -> None:
    from PIL import Image, ImageDraw
    spec = fx.make_spec()
    book = fx.write_book(tmp / "crops", spec)
    loaded = ri.load_book(ri.InputPaths.resolve(book, {}))
    model = rm.learn(loaded)
    reading = rs.Readings(loaded, model).get(7, loaded.pages[7].sealed_text)
    pim = rq.PageImage(loaded, model, 7, reading)
    width, height = pim.size
    x, y, w, h = pim.band[0]
    box = [x * width - 4, y * height - 4, (x + w) * width + 4, (y + h) * height + 4]

    def ink(mask: bool) -> int:
        crop = rq.region_crop(pim, box, mask, pad=0.0)
        with Image.open(io.BytesIO(crop)) as image:
            gray = image.convert("L")
            inner = gray.crop((12, 12, gray.width - 12, gray.height - 12))
            return sum(inner.point(lambda v: 255 if v < 128 else 0).histogram()[255:])
    check(pim.band and ink(False) > 0 and ink(True) == 0,
          f"a crop over the running head's band shows it only for a question about the band (ink {ink(False)} "
          f"as printed, {ink(True)} masked)")
    # engine A's cells on a made-up column: a figure engine A read (no CJK
    # character, but a cell of its own), a full stop set close under its
    # character, two glyphs that touch, spacing that is not even, and a
    # column of plain glyphs beside it.  Each character's cell must stand on
    # its own glyph.
    page = Image.new("L", (400, 900), 255)
    pen = ImageDraw.Draw(page)
    glyphs = {}
    y = 100
    for unit, (height, gap) in zip("4對第四。軍政府", ((40, 16), (40, 0), (40, 14), (40, 3), (12, 30), (40, 12),
                                                      (40, 22), (40, 10))):
        box = (160, y, 200, y + height) if unit != "。" else (172, y, 186, y + height)
        pen.rectangle(box, fill=0)
        glyphs[unit] = box
        y += height + gap
    for k in range(8):
        pen.rectangle((80, 100 + k * 52, 120, 140 + k * 52), fill=0)
    path = tmp / "column.png"
    page.save(path)
    block = {"text": "44對第四。軍政府", "box": [150 / 400, 90 / 900, 60 / 400, (y - 60) / 900]}
    cells = rq.block_cells(path, block, (400, 900), pitch=52.0, masked=page.convert("RGB"))
    placed = {c: (cell["y0"], cell["y1"]) for c, cell in zip("對第四軍政府", cells or [])}
    wrong = [c for c, (a, b) in placed.items() if not (glyphs[c][1] - 3 <= a and b <= glyphs[c][3] + 3)]
    check(cells is not None and len(placed) == 6 and not wrong,
          f"engine A's cells stand on their glyphs: after a figure, beside a full stop set close under its "
          f"character, where two glyphs touch, however unevenly spaced ({wrong}, {placed})")
    thin = Image.new("RGB", (3, 700), (255, 255, 255))
    piece = rq.Piece([0, 0, 3, 700])
    crop = rq.compose(thin, [piece], [rq.Mark(0, "line", (0, 350, 3, 350))], 255)
    with Image.open(io.BytesIO(crop)) as image:
        size = image.size
    check(max(size) <= pp.MEDIA_ASPECT_LIMIT * min(size), f"a thin crop is padded to the aspect limit ({size})")


# --- print questions on the marks rules' pages ------------------------------------------------

def degraded(kind: str, system: str, user: str, crop: bytes) -> Any:
    return "印刷：（", {"degraded": True, "finish_reason": "length", "rungsAsked": 4, "rungsCutOff": 4}


def print_checks(tmp: Path) -> dict[str, Any]:
    spec = cr.marks_spec()
    book = fx.write_book(tmp / "marks", spec)
    plan = planned(book, tmp / "marks-plan", "--no-furniture")
    kinds = sorted({(q["page"], q.get("rule"), q["kind"]) for q in plan if q["kind"] == "Q-P"})
    table = {
        (13, "K1"): "逗號，然後括號入面係阿拉伯數字1。\n印刷：，（1）",
        (19, "K-seq"): "印刷：2.",
        (14, "K-seq"): "印刷：（9）",
        (4, "K3"): "印刷：紅線——",
        (4, "K5"): degraded,
        (8, "K7b"): "兩條紅線之間係一個引號。",
        (18, "K13"): "印刷：（龍）",
    }
    table = {key: (value("", "", "", b"") if callable(value) else value) for key, value in table.items()}
    model = Model(by_question(plan, table, same_answers))
    result = repair(book, tmp / "marks-out", model, "--no-furniture")
    pages = result.pages
    check(result.status == 0 and result.report["checks"]["logReplay"]["passed"] is True
          and result.report["stages"]["questions"]["status"] == "ran",
          f"the questions stage runs, the run exits 0 and its log replays (exit {result.status}, "
          f"{result.report['stages']['questions']})")
    q = result.question(13, "K1")
    edits = result.edits_of(q["id"])
    k, text = cr.column(spec[13])
    check(q["status"] == "answered" and "口（1）" not in pages[13] and text[4:8] + "（1）" in pages[13]
          and edits and all(e["crop"] == q["crop"] and e["answer"] == "，（1）" for e in edits),
          f"Q-P: the answer is written between its anchors and logged with its answer and crop "
          f"({q['status']}, {edits})")
    crop = result.out / q["crop"]
    check(crop.is_file() and pp.sha256_file(crop) == q["cropSha256"] == edits[0]["cropSha256"],
          "the crop is kept, its hash in the question and the log")
    q = result.question(19, "K-seq")
    check(q["status"] == "answered" and "1.春風吹\n\n2.小橋流" in pages[19],
          f"Q-P: a line's figure is written after the line break, the page's own line structure kept "
          f"({q['status']}, {pages[19][:60]!r})")
    for page, rule, guard, what in ((14, "K-seq", "G6", "a figure that does not go on from its list"),
                                    (4, "K3", "G2", "the question's own words"),
                                    (4, "K5", "G1", "a reply cut off on every rung"),
                                    (8, "K7b", "G1", "no answer line"),
                                    (18, "K13", "G5", "a character no engine read")):
        q = result.question(page, rule)
        doubts = result.doubts_of(q["id"])
        check(q["status"] == "refused" and q["guard"]["guard"] == guard and not result.edits_of(q["id"])
              and [d["kind"] for d in doubts] == ["look-refused"] and doubts[0].get("guard") == guard,
              f"{guard} refuses {what} ({rule} on scan {page}): a `look-refused` doubt, no edit "
              f"({q['status']}, {q.get('guard')})")
    check(pages[14] == result.sealed[14] or "丁）（" in pages[14], "the refused figure leaves the page as it was")
    joins = [q for q in result.questions if q["kind"] == "Q-B"]
    check(joins and all(q["status"] == "answered" and result.labels[q["page"]] == "paragraph"
                        and result.evidence[str(q["page"])]["rule"] == "Q-B"
                        and result.evidence[str(q["page"])]["verified"] for q in joins)
          and not [d for d in result.doubts if d["kind"] == "boundary-unverified"],
          f"Q-B: an answered boundary is verified, its rule Q-B, and no `boundary-unverified` doubt "
          f"({len(joins)} boundaries)")
    kinds_asked = sorted({c["kind"] for c in model.calls})
    check(kinds_asked == ["repair-boundary", "repair-print"] and all(c["maxTokens"] == 16000 for c in model.calls)
          and all(c["system"] == rq.REPAIR_SYSTEM for c in model.calls),
          f"the calls are asked as repair-print and repair-boundary, with phase 3's 16000 max_tokens "
          f"({kinds_asked})")
    journal = (result.out / rq.ANSWERS_NAME).read_text(encoding="utf-8").splitlines()
    check(len(journal) == len(model.calls) == result.report["model"]["asked"]
          and result.report["model"]["ladder"] == ["xhigh", "medium", "low", "none"],
          f"every answer is kept in answers.jsonl as it comes; the report names the effort ladder "
          f"({len(journal)} kept, {len(model.calls)} asked)")
    return {"book": book, "plan": plan, "table": table, "pages": pages, "calls": len(model.calls)}


def listed_doubts(result: Result) -> list[dict[str, Any]]:
    """The questions --no-model left unasked (not those no crop could be cut
    for, which no run asks)."""
    return [d for d in result.doubts if d["kind"] == "look-not-asked" and "--no-model" in d["detail"]]


def resume_checks(tmp: Path, first: dict[str, Any]) -> None:
    book = first["book"]
    out = tmp / "marks-out"

    def refuse(kind: str, system: str, user: str, crop: bytes) -> Any:
        raise AssertionError("asked again")
    model = Model(refuse)
    result = repair(book, out, model, "--no-furniture", "--resume")
    check(result.status == 0 and not model.calls and result.pages == first["pages"]
          and result.report["resume"]["answersReused"] == first["calls"],
          f"--resume asks nothing it holds and writes the same book (exit {result.status}, "
          f"{len(model.calls)} asked, {result.report['resume']['answersReused']} reused)")

    # A run the model server stops after three answers (one lane: in order).
    served = {"n": 0}
    good = by_question(first["plan"], first["table"], same_answers)

    def stops(kind: str, system: str, user: str, crop: bytes) -> Any:
        served["n"] += 1
        if served["n"] > 3:
            raise pp.ProofreadError("endpoint unreachable after 3 attempts: made-up")
        return good(kind, system, user, crop)
    stopped = tmp / "stopped"
    result = repair(book, stopped, Model(stops), "--no-furniture", "--max-inflight", "1")
    kept = (stopped / rq.ANSWERS_NAME).read_text(encoding="utf-8").splitlines()
    check(result.status == 6 and result.report["status"] == "failed" and len(kept) == 3,
          f"a run the model server stops exits 6, its answers kept ({result.status}, {len(kept)} kept)")
    # --no-model on a resumed run: what the stopped run holds is used, the
    # rest is listed, nothing is asked (the Client is never called; it names
    # the model the answers were asked of, as a run that asks would).
    listed = tmp / "stopped-listed"
    shutil.copytree(stopped, listed)
    result = repair(book, listed, None, "--no-furniture", "--resume", "--no-model", "--model", Model.model)
    unasked = (result.report.get("model") or {}).get("unasked") or {}
    answered = [q for q in result.questions if q["status"] not in ("planned", "not-asked", "merged")]
    check(result.status == 0 and result.report["resume"]["answersReused"] == 3 and len(answered) == 3
          and unasked.get("calls") == first["calls"] - 3
          and len(listed_doubts(result)) == first["calls"] - 3,
          f"--resume --no-model uses the answers held and lists the rest, asking nothing ({len(answered)} answered, "
          f"{unasked}, {len(listed_doubts(result))} not asked)")
    listed = tmp / "finished-listed"
    shutil.copytree(out, listed)
    result = repair(book, listed, None, "--no-furniture", "--resume", "--no-model", "--model", Model.model)
    check(result.status == 0 and result.pages == first["pages"]
          and ((result.report.get("model") or {}).get("unasked") or {}).get("calls") == 0,
          "--resume --no-model on a finished run writes the same book as the run that asked")
    model = Model(good)
    result = repair(book, stopped, model, "--no-furniture", "--resume")
    check(result.status == 0 and len(model.calls) == first["calls"] - 3 and result.pages == first["pages"],
          f"the resumed run asks only the rest and writes the same book ({len(model.calls)} asked of "
          f"{first['calls']})")


# --- glyph questions ------------------------------------------------------------------------

def glyph_checks(tmp: Path) -> None:
    """Glyph questions on a made-up place in the middle of a page (engine A
    reads 龍 where the page and engine B hold another character), asked
    with the questions module on its own; and the furniture rules' glyph
    question at the band, through the whole run."""
    spec = fx.make_spec()
    body = cr.paragraphs(spec[6])[1]
    held = body[10]
    spec[6]["aEdits"] = [(body[8:13], body[8:10] + "龍" + body[11:13])]
    book = fx.write_book(tmp / "glyph", spec)
    loaded = ri.load_book(ri.InputPaths.resolve(book, {}))
    model = rm.learn(loaded)
    order = list(loaded.assembly.order)
    cases = {
        "the page's own reading (engine B's)": (["定案：" + held], "answered", held, ["main"]),
        "engine A's reading": (["定案：龍"], "answered", "龍", ["main"]),
        "a blind miss, then a candidate named": (["定案：鳳", "定案：龍"], "answered", "龍", ["main", "round2"]),
        "a blind miss, then damaged print": (["定案：鳳", "定案：鳳（印壞）"], "answered", "鳳", ["main", "round2"]),
        "a blind miss, then neither candidate": (["定案：鳳", "定案：鳳"], "refused", held, ["main", "round2"]),
        "nothing printed where both engines read one": (["定案：無", "定案：無"], "refused", held, ["main", "round2"]),
        "G2: two characters for one": (["定案：龍龍"], "refused", held, ["main"]),
        "G3: the character beside it": (["定案：" + body[11]], "refused", held, ["main"]),
    }
    for n, (name, (answers, status, written, roles)) in enumerate(cases.items()):
        ledger = re_.Ledger({scan: loaded.pages[scan].sealed_text for scan in order})
        text = ledger.texts[6]
        at = text.index(body) + 10
        question = rr.question("Q-G", 6, "T-glyph", text, at, at + 1, "made up")
        question["id"] = "Q0001"
        out = tmp / f"glyph-{n}"
        out.mkdir()

        def reply(kind: str, system: str, user: str, crop: bytes, answers: list[str] = answers) -> Any:
            return f"構件：略\n{answers[1 if '甲)' in user else 0]}\nRESEARCH: no"
        stand = Model(reply)
        asker = rq.Asker(stand, out, {}, 16000, 2)
        env = rq.Env(loaded, model, ledger, rs.Readings(loaded, model), rr.book_facts(loaded, model), asker, order)
        rq.ask([question], env)
        new = ledger.texts[6]
        guard = (question.get("guard") or {}).get("guard")
        doubts = [d["kind"] for d in ledger.doubts]
        check(question["status"] == status and new[at] == written and [c["role"] for c in question["calls"]] == roles
              and (status == "answered" or doubts == ["look-refused"]) and (new != text) == (written != held),
              f"Q-G, {name}: {status}, the page holds {written!r}, calls {roles} ({question['status']}, guard "
              f"{guard}, {new[at]!r}, {[c['role'] for c in question['calls']]})")
        if name.startswith("G"):
            check(guard == name[:2], f"{name}: refused by {name[:2]} ({guard})")
        if n == 0:
            check(all(c["system"] == pp.ADJUDICATE_SYSTEM and "甲)" not in c["user"] and c["kind"] == "repair-glyph"
                      for c in stand.calls),
                  "the first glyph question is blind: 裁決's system prompt, no candidates, kind repair-glyph")
        if n == 2:
            second = stand.calls[-1]["user"]
            check("甲) 龍" in second and f"乙) {held}" in second and stand.calls[-1]["crop"] == stand.calls[0]["crop"],
                  "the second round shows both engines' readings as candidates, on the same crop")

    # The furniture rules' glyph question: a printed 一 opening scan 20
    # (folio 一〇), which engine B read in what the book model takes for its
    # head and engine A dropped.
    spec = cr.lookalike_spec()
    book = fx.write_book(tmp / "glyphs", spec)
    argv = ("--no-marks", "--no-paragraphs", "--pages", "19-20")
    body = cr.paragraphs(spec[20])[0]
    runs = {
        "G4: the folio's other character": (["定案：〇"], "refused", "一", ["main"]),
        "G4: the folio's piece itself, which no engine read in the body": (["定案：一"], "refused", "一", ["main"]),
        "damaged print read by meaning, in the second round": (["定案：二", "定案：二（印壞）"], "answered", "二",
                                                              ["main", "round2"]),
    }
    for n, (name, (answers, status, first, roles)) in enumerate(runs.items()):
        def reply(kind: str, system: str, user: str, crop: bytes, answers: list[str] = answers) -> Any:
            if kind != "repair-glyph":
                return same_answers(kind, system, user, crop)
            return f"構件：略\n{answers[1 if '甲)' in user else 0]}\nRESEARCH: no"
        result = repair(book, tmp / f"glyphs-{n}", Model(reply), *argv)
        q = result.question(20, "F6", "Q-G")
        guard = (q.get("guard") or {}).get("guard")
        start = result.pages[20].lstrip("#").lstrip()
        edits = result.edits_of(q["id"])
        check(result.status == 0 and q["status"] == status and [c["role"] for c in q["calls"]] == roles
              and start.startswith(first + body[1:4]) and bool(edits) == (status == "answered")
              and (status == "answered" or guard == "G4"),
              f"Q-G at the band, {name}: {status}, the page opens {first!r} ({q['status']}, guard {guard}, "
              f"{start[:5]!r}, {len(edits)} edit(s))")


# --- copies and layout -----------------------------------------------------------------------

def line_checks(tmp: Path) -> None:
    spec = cs.levels_spec()
    book = fx.write_book(tmp / "lines", spec)
    plan = planned(book, tmp / "lines-plan")
    lead12 = cs.paragraphs(spec, 12)[1]

    def pick(q: dict[str, Any]) -> str | None:
        # The title page's lines: the title as printed, and the second line
        # with a character the engines did not read (板 for 版).
        if q["kind"] == "Q-L" and q["page"] == 1:
            return "印刷：" + (fx.HEAD if fx.HEAD in q["site"]["text"] else "林泉書屋藏板")
        if q["kind"] == "Q-Y" and q["page"] in (12, 14):
            return "答：段落開頭" if q["page"] == 12 else "答：標題"
        return None
    for agree in (True, False):
        def glyph(kind: str, system: str, user: str, crop: bytes, agree: bool = agree) -> Any:
            if kind == "repair-glyph":
                return "構件：略\n定案：" + ("板" if agree else "版") + "\nRESEARCH: no"
            return same_answers(kind, system, user, crop)
        model = Model(by_question(plan, pick, glyph))
        result = repair(book, tmp / f"lines-{agree}", model)
        lines = [q for q in result.questions if q["kind"] == "Q-L" and q["page"] == 1]
        checks = [c for q in lines for c in q["calls"] if c["role"].startswith("check")]
        if agree:
            check(result.status == 0 and "林泉書屋藏板" in result.pages[1] and len(checks) == 1
                  and all(q["status"] == "answered" for q in lines)
                  and any(r["question"] for r in result.log if r["page"] == 1 and "板" in r["after"]),
                  f"Q-L: a copied character no engine read is written when a glyph question on its cell agrees "
                  f"({result.pages[1]!r}, {len(checks)} glyph question(s), {[q['status'] for q in lines]})")
            # The glyph question's crop is the cell of 版 as engine A read the
            # line backwards: its first character.
            loaded = ri.load_book(ri.InputPaths.resolve(book, {}))
            model_data = json.loads((result.out / "book-model.json").read_text(encoding="utf-8"))
            pim = rq.PageImage(loaded, model_data, 1, rs.Readings(loaded, model_data).get(1, result.pages[1]))
            raw = "版藏屋書泉林"
            b = next(n for n, block in enumerate(pim.blocks) if raw in pp.CJK(block["text"]))
            cells = rq.line_cells(pim, b, raw) or []
            crops = [pp.sha256_bytes(rq.cell_crop(pim, cells[k], True)) for k in range(len(cells))]
            check(checks and checks[0]["cropSha256"] == crops[0] and crops.count(crops[0]) == 1,
                  "the glyph question's crop is the copied character's own cell (the line read backwards)")
            check(lead12[:12] in result.pages[12] and "## 甲、春耕" not in result.pages[12]
                  and "## 一，五湖" in result.pages[14],
                  "Q-Y: a run-in lead becomes the start of its paragraph; a heading the model says is one stays")
            check(result.report["stages"]["title-page"].get("answered", {}).get("asked", 0) >= 1
                  and result.report["stages"]["levels"].get("answered", {}).get("asked", 0) >= 1,
                  "the title page's and the levels' questions are asked as soon as their stages have run")
        else:
            check("林泉書屋藏版" in result.pages[1] and len(checks) == 1
                  and any(d["kind"] == "look-refused" and d.get("guard") == "Q-L-character" for d in result.doubts),
                  "Q-L: a copied character the glyph question does not confirm is a doubt, not an edit")
    # The second line only engine A read (engine B read the title alone): a
    # copy with no character, or one leaving a character out, deletes none
    # of engine A's characters.
    for n, copy in enumerate(("無", "林泉書藏版")):
        def lossy(q: dict[str, Any], copy: str = copy) -> str | None:
            if q["kind"] == "Q-L" and q["page"] == 1:
                return "印刷：" + (fx.HEAD if fx.HEAD in q["site"]["text"] else copy)
            return pick(q)
        result = repair(book, tmp / f"lines-lossy-{n}", Model(by_question(plan, lossy, same_answers)))
        line = next(q for q in result.questions if q["kind"] == "Q-L" and q["page"] == 1
                    and fx.HEAD not in q["site"]["text"])
        # A copy with no character is no answer (G2); one leaving a
        # character out has that change refused (G5).
        guard = (line.get("guard") or {}).get("guard") if n == 0 else \
            next((d.get("guard") for d in result.doubts_of(line["id"]) if d["kind"] == "look-refused"), None)
        check(result.status == 0 and "林泉書屋藏版" in result.pages[1] and guard == ("G2" if n == 0 else "G5")
              and any(d["kind"] == "look-refused" for d in result.doubts_of(line["id"])),
              f"Q-L: a copy {copy!r} of a line only engine A read deletes none of its characters: a doubt "
              f"({line['status']}, {guard}, {result.pages[1]!r})")


def title_copy_checks(tmp: Path) -> None:
    """Copies of a title page's lines (Q-L after S13): each line of engine
    A's block of two lines has its own row of cells (a glyph question's
    crop on its own character); a copied character that an engine read
    elsewhere on the line, but not at its place, is asked about on its
    cell; where the glyph question reads another character, a second round
    with the two readings as candidates settles it."""
    from PIL import Image, ImageDraw
    # engine A's block of two lines read backwards, the second shorter and
    # set wide: each character's cell stands on its own glyph in its own row.
    image = Image.new("RGB", (800, 400), (255, 255, 255))
    pen = ImageDraw.Draw(image)
    glyphs: dict[tuple[int, int], tuple[int, int]] = {}
    for row, (count, left, step, top) in enumerate(((10, 100, 60, 100), (4, 250, 90, 200))):
        for k in range(count):
            pen.rectangle((left + k * step, top, left + k * step + 40, top + 40), fill=(0, 0, 0))
            glyphs[(row, k)] = (left + k * step, left + k * step + 40)
    pim = object.__new__(rq.PageImage)
    pim.size = (800, 400)
    pim.blocks = [{"text": "甲乙丙丁戊己庚辛壬癸\n子丑寅卯", "box": [90 / 800, 90 / 400, 600 / 800, 160 / 400]}]
    pim._images = {True: image}
    pim.paper = 255
    lines = [(getattr(rq, "line_cells", lambda *a: None)(pim, 0, raw) or []) for raw in ("甲乙丙丁戊己庚辛壬癸", "子丑寅卯")]
    def on_glyph(row: int, k: int, cell: dict[str, Any]) -> bool:
        """The cell holds its glyph, reaches neither neighbour, and stands in
        its own row."""
        left, right = glyphs[(row, k)]
        before = glyphs.get((row, k - 1), (None, -1))[1]
        after = glyphs.get((row, k + 1), (10 ** 6, None))[0]
        return (before < cell["x0"] <= left + 2 and right - 2 <= cell["x1"] < after
                and cell["y0"] <= 100 + 100 * row and cell["y1"] >= 140 + 100 * row and cell["y1"] - cell["y0"] < 100)
    wrong = [(row, k) for row, cells in enumerate(lines) for k, cell in enumerate(cells) if not on_glyph(row, k, cell)]
    check([len(cells) for cells in lines] == [10, 4] and not wrong,
          f"a line of engine A's block of two lines has its own cells, each on its glyph, in its own row ({wrong})")

    spec = cs.levels_spec()
    book = fx.write_book(tmp / "title-copy", spec)
    plan = planned(book, tmp / "title-copy-plan")

    def copy(q: dict[str, Any]) -> str | None:
        if q["kind"] == "Q-L" and q["page"] == 1:
            return "印刷：" + (fx.HEAD if fx.HEAD in q["site"]["text"] else "林泉書屋藏林")
        return None
    for name, (blind, second, written, roles) in {
            "the glyph question agrees": ("林", None, "林泉書屋藏林", ["main", "check1"]),
            "it reads another character, which the second round names": ("板", "板", "林泉書屋藏板",
                                                                        ["main", "check1", "second1"]),
            "the second round names neither": ("板", "書", "林泉書屋藏版", ["main", "check1", "second1"])}.items():
        def glyph(kind: str, system: str, user: str, crop: bytes, blind: str = blind, second: str | None = second) -> Any:
            if kind == "repair-glyph":
                return "構件：略\n定案：" + (second if "甲)" in user else blind) + "\nRESEARCH: no"
            return same_answers(kind, system, user, crop)
        result = repair(book, tmp / f"title-copy-{len(roles)}-{written}", Model(by_question(plan, copy, glyph)))
        line = next(q for q in result.questions if q["kind"] == "Q-L" and q["page"] == 1
                    and fx.HEAD not in q["site"]["text"])
        check(result.status == 0 and written in result.pages[1] and [c["role"] for c in line["calls"]] == roles,
              f"Q-L: a copy writing 林 where the engines read 版 (林 read elsewhere on the line) - {name}: the page "
              f"holds {written!r} ({result.pages[1]!r}, {[c['role'] for c in line['calls']]})")


def layout_checks(tmp: Path) -> None:
    spec = cb.paragraph_spec()
    book = fx.write_book(tmp / "paragraphs", spec)
    plan = planned(book, tmp / "paragraphs-plan")
    model = Model(by_question(plan, {(12, "P1"): "答：同一段", (16, "P7"): "答：另起一段"}, same_answers))
    result = repair(book, tmp / "paragraphs-out", model)
    p1 = result.question(12, "P1")
    p7 = result.question(16, "P7")
    one, two = cb.paragraphs(spec, 16)[1:3]
    check(p1["status"] == "answered" and cb.prose(1201, 20, False) + cb.prose(1202, 45, True) in result.pages[12],
          f"Q-Y: a line break the model says is inside one paragraph is joined ({p1['status']}, {p1.get('answer')})")
    check(p7["status"] == "answered" and one + "\n\n二" + two in result.pages[16],
          f"Q-Y: a numeral before engine A's block opens the new paragraph ({p7['status']}, {p7.get('answer')})")
    # The question names the place its answer breaks (the site's start: the
    # end of the paragraph before, the block's first characters), not the
    # characters past the site.
    named = re.findall(r"「([^」]*)」", p7["prompt"])
    check(named[:2] == [pp.CJK(one)[-6:], pp.CJK(two)[:6]] and named[2] == named[1],
          f"Q-Y: the paragraph question names the place its answer breaks ({named}, "
          f"{pp.CJK(one)[-6:]!r} | {pp.CJK(two)[:6]!r})")


def boundary_checks(tmp: Path) -> None:
    spec = cb.boundary_spec()
    book = fx.write_book(tmp / "boundaries", spec)
    plan = planned(book, tmp / "boundaries-plan")
    model = Model(by_question(plan, {(6, "J"): "答：續文", (19, "J"): "答：睇唔清"}, same_answers))
    result = repair(book, tmp / "boundaries-out", model)
    check(result.status == 0 and result.report["checks"]["boundaryContract"]["passed"] is True,
          "the labels the answers settle pass finalize's contract")
    check(result.labels[6] == "join" and result.evidence["6"]["rule"] == "Q-B" and result.evidence["6"]["verified"]
          and not [d for d in result.doubts if d["kind"] == "boundary-unverified" and d["page"] == 6],
          f"Q-B: 續文 settles the boundary as a join, verified ({result.labels[6]}, {result.evidence['6']})")
    q = result.question(19, "J")
    check(result.labels[19] == "paragraph" and not result.evidence["19"]["verified"] and q["status"] == "unsure"
          and [d for d in result.doubts if d["kind"] == "boundary-unverified" and d["page"] == 19],
          f"Q-B: 睇唔清 leaves the boundary `paragraph`, unverified, a doubt ({q['status']})")


# --- G7 and the site ------------------------------------------------------------------------------

def site_checks(tmp: Path) -> None:
    spec = fx.make_spec()
    # Engine A reads no comma on scan 6: an answer changes a mark the page
    # and engine A both hold nowhere (G5), and these questions' answers
    # change the page's commas.
    spec[6]["aMarks"] = {k: column["text"].replace("，", "")
                         for k, column in enumerate(fx.layout(spec[6])["columns"])}
    book = fx.write_book(tmp / "sites", spec)
    loaded = ri.load_book(ri.InputPaths.resolve(book, {}))
    model = rm.learn(loaded)
    order = list(loaded.assembly.order)
    ledger = re_.Ledger({scan: loaded.pages[scan].sealed_text for scan in order})
    text = ledger.texts[6]
    comma = [i for i, c in enumerate(text) if c == "，"]
    a, b, c, d = comma[2], comma[4], comma[6], comma[8]
    questions = [
        rr.question("Q-P", 6, "T-one", text, a, a + 1, "made up"),            # a comma
        rr.question("Q-P", 6, "T-two", text, a - 1, a + 2, "made up"),        # the same comma, with its neighbours
        rr.question("Q-P", 6, "T-moved", text, b, b + 1, "made up"),          # moved by an edit before it
        rr.question("Q-P", 6, "T-changed", text, c, c + 1, "made up"),        # changed by an edit
        rr.question("Q-P", 6, "T-same", text, d, d + 1, "made up"),
        rr.question("Q-P", 6, "T-same-again", text, d, d + 1, "made up"),
    ]
    for n, q in enumerate(questions, 1):
        q["id"] = f"Q{n:04d}"
    # Edits applied after the questions were planned: marks inserted before
    # the third site, and the fourth site's comma replaced.
    ledger.apply("made-up", [re_.Edit(6, b - 3, b - 3, "〔〕", rule="T-insert"),
                             re_.Edit(6, c, c + 1, "。", rule="T-replace")])
    out = tmp / "sites-out"
    out.mkdir()

    def reply(kind: str, system: str, user: str, crop: bytes) -> Any:
        before = re.search(r"「([^」]*)」最後一個字之後", user).group(1)
        # The second question's anchors are one character further out.
        return f"印刷：{text[a - 1]}、{text[a + 1]}" if before.endswith(text[a - 2]) else "印刷：、"
    stand = Model(reply)
    asker = rq.Asker(stand, out, {}, 16000, 2)
    env = rq.Env(loaded, model, ledger, rs.Readings(loaded, model), rr.book_facts(loaded, model), asker, order)
    rq.ask(questions, env)
    status = {q["rule"]: q["status"] for q in questions}
    new = ledger.texts[6]
    check(status["T-one"] == "answered" and status["T-two"] == "conflict" and new[a] == "、"
          and any(x["kind"] == "conflict" and x.get("question") == "Q0002" and x.get("guard") == "G7"
                  for x in ledger.doubts),
          f"G7: two answers over the same mark - the first is written, the second is a `conflict` doubt ({status})")
    check(status["T-moved"] == "answered" and new[b + 2] == "、" and "〔〕" in new,
          f"a site an edit before it moved is found where it went ({status['T-moved']})")
    check(status["T-changed"] == "conflict" and new[c + 2] == "。"
          and any(x["kind"] == "conflict" and x.get("record") for x in ledger.doubts if x.get("question") == "Q0004"),
          f"a site an edit changed after the question was planned is a `conflict` doubt, the edit standing "
          f"({status['T-changed']})")
    check(status["T-same"] == "answered" and status["T-same-again"] == "merged" and len(stand.calls) == 4,
          f"two questions about one site are asked once ({status['T-same-again']}, {len(stand.calls)} calls)")

    # --verify-sample: a print question over a rule's edit; its answer is
    # never written, and one that reads otherwise is a doubt.
    for answer, disagrees in (("印刷：、", False), ("印刷：。", True)):
        ledger = re_.Ledger({scan: loaded.pages[scan].sealed_text for scan in order})
        at = [i for i, x in enumerate(ledger.texts[6]) if x == "，"][3]
        ledger.apply("made-up", [re_.Edit(6, at, at + 1, "、", rule="T-rule")])
        question = {"id": "Q0001", "kind": "Q-P", "purpose": "verify", "edit": "E0001", "page": 6, "status": "planned"}
        before = ledger.texts[6]
        stand = Model(lambda kind, system, user, crop, answer=answer: answer)
        asker = rq.Asker(stand, tmp / f"verify-{disagrees}", {}, 16000, 2)
        (tmp / f"verify-{disagrees}").mkdir()
        env = rq.Env(loaded, model, ledger, rs.Readings(loaded, model), rr.book_facts(loaded, model), asker, order)
        rq.ask([question], env)
        kinds = [x["kind"] for x in ledger.doubts]
        check(ledger.texts[6] == before and len(ledger.records) == 1 and question["status"] == "answered"
              and kinds == (["verify-disagrees"] if disagrees else []),
              f"--verify-sample: a print question over a rule's edit writes nothing; one that reads otherwise is a "
              f"`verify-disagrees` doubt ({kinds})")


# --- what an answer may not delete or write --------------------------------------------------------

def ask_one(tmp: Path, name: str, spec: dict[int, dict[str, Any]], make: Callable[[str], dict[str, Any]],
            answer: str) -> tuple[dict[str, Any], str, str, list[dict[str, Any]]]:
    """One print question, made by MAKE from the sealed page text, asked of
    the made-up book SPEC with the questions module on its own and answered
    ANSWER: the question, the page before and after, and the doubts."""
    book = fx.write_book(tmp / name, spec)
    loaded = ri.load_book(ri.InputPaths.resolve(book, {}))
    model = rm.learn(loaded)
    order = list(loaded.assembly.order)
    ledger = re_.Ledger({scan: loaded.pages[scan].sealed_text for scan in order})
    question = make(ledger)
    question["id"] = "Q0001"
    before = ledger.texts[question["page"]]
    out = tmp / f"{name}-out"
    out.mkdir()
    asker = rq.Asker(Model(lambda kind, system, user, crop: "看過。\n" + answer), out, {}, 16000, 2)
    env = rq.Env(loaded, model, ledger, rs.Readings(loaded, model), rr.book_facts(loaded, model), asker, order)
    rq.ask([question], env)
    return question, before, ledger.texts[question["page"]], ledger.doubts


def guard_checks(tmp: Path) -> None:
    # G6: a figure written just before the title it opens is the contents'
    # number of the unit, or no figure is written (the figure pattern needs
    # the character after it, which the page holds after the gap).
    spec = fx.make_spec()
    title = "秋夜讀書"
    spec[7]["sealedEdits"] = [("### 2 " + title, "### " + title)]

    def unit(ledger: re_.Ledger) -> dict[str, Any]:
        text = ledger.texts[7]
        at = text.index(title)
        return rr.question("Q-P", 7, "T-number", text, at, at, "made up", contentsNumber=2)
    for n, (answer, status, written) in enumerate((("印刷：3", "refused", "### " + title),
                                                   ("印刷：2", "answered", "### 2" + title))):
        q, before, after, doubts = ask_one(tmp, f"unit-{n}", spec, unit, answer)
        check(q["status"] == status and after.startswith(written)
              and (status == "answered" or q["guard"]["guard"] == "G6"),
              f"G6: a unit's figure written before its title is the contents' number ({answer}: {q['status']}, "
              f"{q.get('guard')}, {after[:12]!r})")

    # G5: a character engine A reads one way and engine B and the page
    # another (no variant table joins them) is one all three saw: nothing
    # printed there deletes it.
    spec = fx.make_spec()
    body = cr.paragraphs(spec[6])[1]
    spec[6]["aEdits"] = [(body[8:13], body[8:10] + "龍" + body[11:13])]

    def glyph(ledger: re_.Ledger) -> dict[str, Any]:
        text = ledger.texts[6]
        at = text.index(body) + 10
        return rr.question("Q-P", 6, "T-glyph", text, at, at + 1, "made up")
    q, before, after, doubts = ask_one(tmp, "seen", spec, glyph, "印刷：無")
    check(q["status"] == "refused" and q["guard"]["guard"] == "G5" and after == before
          and [d["kind"] for d in doubts] == ["look-refused"],
          f"G5: nothing printed, where the page and both engines each hold a character (read two ways), deletes "
          f"nothing ({q['status']}, {q.get('guard')})")

    # G5: a full stop the page and engine A both hold between the anchors
    # (the paragraph before a place at the next one's start) is kept.
    spec = fx.make_spec()
    one, two = cr.paragraphs(spec[6])[:2]

    def opening(ledger: re_.Ledger) -> dict[str, Any]:
        text = ledger.texts[6]
        at = text.index(two)
        return rr.question("Q-P", 6, "T-opening", text, at, at + 1, "made up")
    for n, (answer, status) in enumerate(((two[0], "refused"), ("。" + two[0], "answered"))):
        q, before, after, doubts = ask_one(tmp, f"agreed-{n}", spec, opening, "印刷：" + answer)
        check(q["status"] == status and after == before and one in after
              and (status == "answered" or q["guard"]["guard"] == "G5"),
              f"G5: an answer leaving out the full stop the page and engine A both hold between the anchors is "
              f"refused ({answer!r}: {q['status']}, {q.get('guard')})")


def numbers_checks(tmp: Path) -> None:
    """Units whose numbers no engine read, asked in one round: each figure
    that is the contents' number is written, though the figures beside it
    are not written yet (G6), and a two-figure number with its mark is not
    too long where no engine read anything (G2)."""
    spec = fx.make_spec()
    units = ((7, 2, 2, "秋夜讀書"), (9, 3, 3, "山居雜詠"), (11, 4, 4, "江上聽雨"), (13, 1, 10, "晨鐘暮鼓"))
    for scan, printed, _, title in units:
        spec[scan]["sealedEdits"] = [(f"### {printed} {title}", f"### {title}")]
        spec[scan]["aEdits"] = [(f"{printed} {title}", title)]
        spec[scan]["bEdits"] = [(f"{printed} {title}", title)]
    book = fx.write_book(tmp / "numbers", spec)
    loaded = ri.load_book(ri.InputPaths.resolve(book, {}))
    model = rm.learn(loaded)
    order = list(loaded.assembly.order)
    ledger = re_.Ledger({scan: loaded.pages[scan].sealed_text for scan in order})
    questions = []
    for n, (scan, _, number, title) in enumerate(units, 1):
        text = ledger.texts[scan]
        at = text.index(title)
        question = rr.question("Q-P", scan, "T-number", text, at, at, "made up", contentsNumber=number)
        question["id"] = f"Q{n:04d}"
        questions.append(question)
    answers = {title[:4]: f"印刷：{number}." for _, _, number, title in units}

    def reply(kind: str, system: str, user: str, crop: bytes) -> str:
        after = re.search(r"下面係「([^」]*)」", user)
        return next((a for key, a in answers.items() if after and after.group(1).startswith(key)), "印刷：睇唔清")
    out = tmp / "numbers-out"
    out.mkdir()
    env = rq.Env(loaded, model, ledger, rs.Readings(loaded, model), rr.book_facts(loaded, model),
                 rq.Asker(Model(reply), out, {}, 16000, 2), order)
    rq.ask(questions, env)
    written = {q["page"]: (q["status"], (q.get("guard") or {}).get("guard")) for q in questions}
    check(all(f"### {number}.{title}\n" in ledger.texts[scan] for scan, _, number, title in units),
          f"G6/G2: units' numbers no engine read, asked in one round, are written where they are the contents' "
          f"numbers, a two-figure one too ({written})")


def contents_number_spec() -> tuple[dict[int, dict[str, Any]], tuple[int, int, int, int]]:
    """The made-up book with its contents numbered `n.`; on scan 2 the second
    entry's number is printed at its column's head (drawn apart, above the
    title's first cell) where engine A read no block, so no source reads it.
    The spec, and the number's ink box (x, top, width, height)."""
    spec = fx.make_spec()
    for scan in (2, 3):
        spec[scan]["items"] = [(item[0], re.sub(r"^(\d) ", r"\1. ", item[1]), *item[2:]) if item[0] == "line"
                               else item for item in spec[scan]["items"]]
    items = spec[2]["items"]
    k = next(i for i, item in enumerate(items) if item[0] == "line" and item[1].startswith("2. "))
    items[k] = ("line", items[k][1][3:], 1)
    x = next(c["x"] for c in fx.layout(spec[2])["columns"] if c["text"] == items[k][1])
    ink = (x - 5, fx.FRAME_TOP + 3, 10, 13)
    spec[2]["stamp"] = ink
    return spec, ink


def contents_number_checks(tmp: Path) -> None:
    """A contents entry's number printed at the head of its column, above the
    title engine A's block starts at: the print question's crop is cut from
    the column's head, so the number is between its red lines; the question
    carries the numbers' mark its group prints (all `n.`), and an answer
    reading the number with a colon-like mark writes that mark, a space
    before the title as S11 writes it.  Where engine A's box cuts the number
    at its top, the tick after the number stands below it, above the
    title's first glyph."""
    spec, (x, top, _, _) = contents_number_spec()
    book = fx.write_book(tmp / "contents-number", spec)
    plan = planned(book, tmp / "contents-number-plan")
    asked = [q for q in plan if q["page"] == 2 and q.get("rule") == "S11" and q.get("contentsNumber") == 2]
    check(len(asked) == 1 and asked[0].get("numberStyle") == ".",
          f"S11: an entry whose number no source read is asked, with the '.' its group's numbers carry "
          f"({[(q.get('contentsNumber'), q.get('numberStyle')) for q in asked]})")
    loaded = ri.load_book(ri.InputPaths.resolve(book, {}))
    model = rm.learn(loaded)
    text = loaded.pages[2].sealed_text
    reading = rs.Readings(loaded, model).get(2, text)
    pim = rq.PageImage(loaded, model, 2, reading)
    at = text.index("秋夜讀書")
    found = rq.stretch(pim, rq.make_spot(reading, 2, at, at), rq.PRINT_REACH)
    pieces = found[0] if found else []
    column = next((p for p in pieces if p.box[0] <= x <= p.box[2]), None)
    check(column is not None and column.box[1] <= top,
          f"the print question's crop takes in the number set at its column's head, above engine A's block "
          f"(piece top {column.box[1] if column else None}, number's ink at {top})")
    model_answers = Model(by_question(plan, lambda q: "印刷：2:" if q in asked else None, same_answers))
    result = repair(book, tmp / "contents-number-out", model_answers)
    q = result.question(2, "S11")
    edits = [e for e in result.edits_of(q["id"])]
    check(result.status == 0 and "\n2. 秋夜讀書" in result.pages[2] and "2：" not in result.pages[2]
          and edits and edits[0]["evidence"].get("numberStyle") == ".",
          f"an answer reading the number with a colon-like mark writes the mark its group's numbers carry, a space "
          f"before the title ({q['status']}, {result.pages[2][:80]!r})")
    # Engine A's box cuts the number at its top (its cells spread from the
    # number's foot down): the tick before the title goes above the title's
    # first glyph, below the number - not across or above the number, where
    # the model would see it outside the place.
    spec, (x, top, _, height) = contents_number_spec()
    k = next(i for i, c in enumerate(fx.layout(spec[2])["columns"]) if c["text"].startswith("秋夜讀書"))
    spec[2]["aTops"] = {k: top + height // 2}
    book = fx.write_book(tmp / "contents-number-cut", spec)
    loaded = ri.load_book(ri.InputPaths.resolve(book, {}))
    model = rm.learn(loaded)
    text = loaded.pages[2].sealed_text
    reading = rs.Readings(loaded, model).get(2, text)
    at = text.index("秋夜讀書")
    pim = rq.PageImage(loaded, model, 2, reading)
    drawn: list[Any] = []
    real = rq.compose
    rq.compose = lambda image, pieces, marks, paper: drawn.extend(marks) or real(image, pieces, marks, paper)
    try:
        rq.print_crop(pim, rq.make_spot(reading, 2, at, at), True, number=True)
    except TypeError:
        rq.print_crop(pim, rq.make_spot(reading, 2, at, at), True)
    finally:
        rq.compose = real
    ticks = [m.at[1] for m in drawn if m.shape == "line"]
    glyph = fx.FRAME_TOP + fx.PITCH + 2
    check(len(ticks) == 2 and top + height <= ticks[1] <= glyph + 1,
          f"a number question's tick after a number engine A's box cut stands above the title's first glyph, "
          f"below the number (tick {ticks[1:]}, number's ink {top}-{top + height}, glyph at {glyph})")


def standin_checks(tmp: Path) -> None:
    """K14: engine B's comma glyph (丶, a stand-in the book model learns)
    left in the text where engine A read a comma and no rule settles it is
    asked (a print question over the gap), and the answer is written; a gap
    of more stand-ins than STANDIN_RUN is not asked (bounded); G5 still
    refuses an answer writing a character no engine read, and an answer
    that deletes the stand-in (無: engine A's cell beside it may stand on the
    ink of the mark it stands for, outside the red lines) is refused too."""
    spec = fx.make_spec()
    one = cr.paragraphs(spec[6])[1]
    at = one.index("，")
    spec[6]["sealedEdits"] = [(one[:at + 1], one[:at] + "丶")]
    two = cr.paragraphs(spec[8])[1]
    far = two.index("，")
    spec[8]["sealedEdits"] = [(two[:far + 1], two[:far] + "丶" * (rm.STANDIN_RUN + 1))]
    book = fx.write_book(tmp / "standins", spec)
    plan = planned(book, tmp / "standins-plan")
    asked = {q["page"]: q for q in plan if q.get("rule") == "K14"}
    check(6 in asked and asked[6]["site"]["text"] == "丶" and 8 not in asked,
          f"K14: a stand-in no rule settled is asked; a gap of more than {rm.STANDIN_RUN} is not "
          f"({sorted(asked)}, {asked.get(6, {}).get('site')})")
    for n, (answer, status, held) in enumerate((("印刷：，", "answered", one[:at + 1]),
                                                ("印刷：龍", "refused", one[:at] + "丶"),
                                                ("印刷：無", "refused", one[:at] + "丶"))):
        model = Model(by_question(plan, lambda q, answer=answer: answer if q.get("rule") == "K14" else None,
                                  same_answers))
        result = repair(book, tmp / f"standins-{n}", model)
        q = next((q for q in result.questions if q["page"] == 6 and q.get("rule") == "K14"), {"status": None})
        check(result.status == 0 and q["status"] == status and held in result.pages[6]
              and (status == "answered" or (q.get("guard") or {}).get("guard") == "G5"),
              f"K14: {answer} is {status} ({q['status']}, {q.get('guard')}, "
              f"{result.report['lint']['after']['MARK-STANDIN']} stand-ins left)")


def edge_checks(tmp: Path) -> None:
    """F8: a character both engines read at a page's head (engine A as
    another glyph) or foot, which the page lost: a glyph question at the
    page's edge, its crop the page's first (last) column's end, and the
    answer written there - at the foot before the full stop engine A reads
    after it; an answer that is neither engine's reading nor named in the
    second round writes nothing."""
    spec = fx.make_spec()
    skip = set(fx.HEAD) | set("甲編乙編目次") | set(fx.DIGITS)
    head_scan = next(scan for scan in (8, 10, 12, 14) if cr.paragraphs(spec[scan])[0][0] not in skip)
    first = cr.paragraphs(spec[head_scan])[0]
    lost = first[0]
    spec[head_scan]["sealedEdits"] = [(first[:4], first[1:4])]
    spec[head_scan]["aEdits"] = [(first[:4], "龍" + first[1:4])]
    foot_scan = 16
    last = cr.paragraphs(spec[foot_scan])[-1]
    spec[foot_scan]["sealedEdits"] = [(last[-4:], last[-4:-2] + "。")]
    book = fx.write_book(tmp / "edges", spec)
    plan = planned(book, tmp / "edges-plan")
    asked = {(q["page"], q.get("edge")): q for q in plan if q.get("rule") == "F8"}
    check((head_scan, "head") in asked and (foot_scan, "foot") in asked
          and asked[(head_scan, "head")].get("atPlace") == {"a": "龍", "b": lost}
          and asked[(foot_scan, "foot")].get("atPlace") == {"a": last[-2], "b": last[-2]},
          f"F8: a character both engines read at a page's head or foot, lost from the page, is asked "
          f"({sorted(asked)})")
    for n, (head_answer, written) in enumerate(((lost, lost + first[1:4]), ("鳳", first[1:4]))):
        def glyph(kind: str, system: str, user: str, crop: bytes, head_answer: str = head_answer) -> Any:
            if kind != "repair-glyph":
                return same_answers(kind, system, user, crop)
            return "構件：略\n定案：" + (head_answer if first[1] in user or "甲)" in user and "龍" in user
                                         else last[-2]) + "\nRESEARCH: no"
        result = repair(book, tmp / f"edges-{n}", Model(glyph))
        head = next((q for q in result.questions if q.get("rule") == "F8" and q["page"] == head_scan), {})
        foot = next((q for q in result.questions if q.get("rule") == "F8" and q["page"] == foot_scan), {})
        check(result.status == 0 and result.pages[head_scan].lstrip("#").lstrip().startswith(written)
              and head.get("status") == ("answered" if n == 0 else "refused"),
              f"F8 at the head, answered {head_answer!r}: the page opens {written!r} "
              f"({head.get('status')}, {result.pages[head_scan][:6]!r})")
        if n == 0:
            check(foot.get("status") == "answered" and result.pages[foot_scan].rstrip().endswith(last[-4:]),
                  f"F8 at the foot: the lost character is written before the full stop engine A reads after it "
                  f"({foot.get('status')}, {result.pages[foot_scan][-6:]!r}, want {last[-4:]!r})")


def unit_mark_checks(tmp: Path) -> None:
    """Unit headings numbered `n.`: a date after a unit's title moves to its
    own paragraph and takes with it the comma before it that neither engine
    read (S7; one engine A or engine B read stays); a unit number written with no
    mark (engine A read none, the page none) between units that carry '.'
    is asked (S4), and the answer `3.` is written with its space."""
    spec = fx.make_spec()
    for scan in (5, 7, 9, 11):
        spec[scan]["items"] = [("heading", re.sub(r"^(\d) ", r"\1. ", item[1]), item[2]) if item[0] == "heading"
                               else item for item in spec[scan]["items"]]
    # Scan 7: the date printed after the title, no comma; the page holds one.
    k = next(i for i, item in enumerate(spec[7]["items"]) if item[0] == "heading")
    spec[7]["items"][k] = ("heading", "2. 秋夜讀書三年五月七日", 3)
    spec[7]["sealedEdits"] = [("### 2. 秋夜讀書三年五月七日", "### 2. 秋夜讀書，三年五月七日")]
    # Scan 11: the same, and engine A read the comma: it is printed.
    k = next(i for i, item in enumerate(spec[11]["items"]) if item[0] == "heading")
    spec[11]["items"][k] = ("heading", "4. 江上聽雨，三年六月八日", 3)
    # Scan 5: the same, the comma printed; engine A missed it, engine B read
    # it (its stand-in glyph): it is printed.
    k = next(i for i, item in enumerate(spec[5]["items"]) if item[0] == "heading")
    spec[5]["items"][k] = ("heading", "1. 春日遊記，三年四月六日", 3)
    spec[5]["aEdits"] = [("春日遊記，三年", "春日遊記三年")]
    # Scan 9: unit 3's dot engine A and the page lost.
    spec[9]["aEdits"] = [("3. 山居雜詠", "3 山居雜詠")]
    spec[9]["sealedEdits"] = [("### 3. 山居雜詠", "### 3 山居雜詠")]
    book = fx.write_book(tmp / "unit-marks", spec)
    plan = planned(book, tmp / "unit-marks-plan")
    asked = [q for q in plan if q["page"] == 9 and q.get("rule") == "S4"]
    check(len(asked) == 1 and asked[0].get("numberStyle") == "." and asked[0]["site"]["text"] == "3 ",
          f"S4: a unit number with no mark between units that carry '.' is asked ({[q.get('why') for q in asked]})")
    model = Model(by_question(plan, lambda q: "印刷：3." if q in asked else None, same_answers))
    result = repair(book, tmp / "unit-marks-out", model)
    check(result.status == 0 and "### 3. 山居雜詠" in result.pages[9],
          f"S4: the answer writes the unit's mark, a space before its title ({result.pages[9][:40]!r})")
    check("### 2. 秋夜讀書\n\n三年五月七日" in result.pages[7] and "秋夜讀書，" not in result.pages[7],
          f"S7: the comma before the date that neither engine read goes with the date's move "
          f"({result.pages[7][:40]!r})")
    check("江上聽雨，\n\n三年六月八日" in result.pages[11],
          f"S7: a comma engine A read before the date stays ({result.pages[11][:40]!r})")
    check("春日遊記，\n\n三年四月六日" in result.pages[5],
          f"S7: a comma engine B read before the date (engine A did not) stays ({result.pages[5][:40]!r})")


def heading_join_checks(tmp: Path) -> None:
    """Q-B's 續文 at a page opening with a heading: the heading becomes text
    only where engine A reads it first on the page; a heading the page sets
    at its top that engine A reads further down would stand inside the
    previous page's sentence."""
    spec = fx.make_spec()
    for scan in (9, 11):
        cb.end_page(spec, scan, full=True, final=False)
    # Scan 10: the print goes on flush from scan 9 and sets a heading below
    # the first paragraph; the page holds the heading at its top.
    first = cb.paragraphs(spec, 10)[0]
    spec[10]["items"].insert(1, ("heading", "甲 餘論", 3))
    cb.seal(spec, 10, first + "\n\n### 甲 餘論", "### 甲 餘論\n\n" + first)
    # Scan 12: the heading is printed at the top, where engine A reads it.
    spec[12]["items"].insert(0, ("heading", "乙 續篇", 3))
    book = fx.write_book(tmp / "heading-join", spec)
    plan = planned(book, tmp / "heading-join-plan")
    asked = {q["page"] for q in plan if q["kind"] == "Q-B"}
    model = Model(by_question(plan, {(10, "J"): "答：續文", (12, "J"): "答：續文"}, same_answers))
    result = repair(book, tmp / "heading-join-out", model)
    q10 = result.question(10, "J", "Q-B") if 10 in asked else {}
    q12 = result.question(12, "J", "Q-B") if 12 in asked else {}
    check({10, 12} <= asked and result.status == 0, f"a page opening with a heading after unfinished text asks Q-B "
          f"({sorted(asked)}, exit {result.status})")
    check(q10.get("status") == "refused" and re.match(r"#+ 甲 餘論\n", result.pages[10]) is not None
          and result.labels[10] == "paragraph" and not result.evidence["10"].get("verified")
          and any(d["kind"] == "look-refused" for d in result.doubts_of(q10.get("id"))),
          f"Q-B: 續文 at a heading engine A reads further down the page joins nothing and keeps the heading "
          f"({q10.get('status')}, {result.labels.get(10)}, {result.pages[10][:10]!r})")
    check(q12.get("status") == "answered" and result.pages[12].startswith("乙 續篇") and result.labels[12] == "join",
          f"Q-B: 續文 at a heading engine A reads first on the page makes it text and joins ({q12.get('status')}, "
          f"{result.labels.get(12)}, {result.pages[12][:10]!r})")


def follows_checks(tmp: Path) -> None:
    """The marks a furniture deletion leaves (F2c): asked after the
    deletion, not taken for an edit that made the question moot; an answer
    writing characters (the deleted suffix read again: engine A read it into
    the body there) is refused."""
    spec = cr.furniture_spec()
    last = cr.paragraphs(spec[7])[-1]
    spec[7]["aEdits"] = [(last[-5:], last[-5:] + "甲編")]
    book = fx.write_book(tmp / "follows", spec)
    plan = planned(book, tmp / "follows-plan", "--no-marks", "--no-paragraphs")
    for n, (answer, status, end) in enumerate((("印刷：。", "answered", "。\n"),
                                               ("印刷：。甲編", "refused", "。，，\n"))):
        model = Model(by_question(plan, {(7, "F2c"): answer}, same_answers))
        result = repair(book, tmp / f"follows-{n}", model, "--no-marks", "--no-paragraphs")
        q = result.question(7, "F2c")
        check(q["status"] == status and result.pages[7].endswith(end) and "甲編" not in result.pages[7]
              and (status == "answered" or q["guard"]["guard"] == "G4"),
              f"the marks a deleted suffix left are asked after the deletion; {answer}: {status} "
              f"({q['status']}, {q.get('guard')}, {result.pages[7][-6:]!r})")


def snap_checks() -> None:
    """A cell is moved onto one glyph's ink, never onto two glyphs (or a
    glyph and a dash's stroke) run together."""
    import numpy as np
    gray = np.full((500, 100), 255, dtype=np.uint8)
    for top, foot in ((100, 145), (150, 195), (300, 345)):
        gray[top:foot, 30:70] = 0
    pim = object.__new__(rq.PageImage)
    pim._gray, pim.paper = gray, 255

    def cell(y0: float, y1: float) -> dict[str, Any]:
        return {"x0": 20.0, "x1": 80.0, "y0": y0, "y1": y1, "left": 20.0, "right": 80.0, "pitch": 50.0,
                "across": False}
    merged = pim.snap(cell(125.0, 170.0))
    single = pim.snap(cell(310.0, 355.0))
    check((merged["y0"], merged["y1"]) == (125.0, 170.0) and (single["y0"], single["y1"]) == (300.0, 345.0),
          f"snap takes one glyph's run of ink, not two glyphs set close together ({merged['y0']}-{merged['y1']}, "
          f"{single['y0']}-{single['y1']})")


# --- the real Client -------------------------------------------------------------------------------

def client_checks(tmp: Path) -> None:
    spec = cr.marks_spec()
    book = fx.write_book(tmp / "client", spec)
    bodies: list[dict[str, Any]] = []
    lock = threading.Lock()
    first: dict[str, str] = {}

    def respond(body: dict) -> Any:
        user = body["messages"][1]["content"][0]["text"]
        with lock:
            bodies.append(body)
            if "印刷" in user and not first:
                first["user"] = user
            cut = user == first.get("user") and body.get("reasoning_effort") == "xhigh"
        if cut:
            return stand_in.reply("", finish="length", completion_tokens=16000)
        return stand_in.reply("答：另起一段" if "續文" in user else "印刷：睇唔清")
    endpoint = stand_in.served().endpoint(respond)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        status = repair_book.main(["--workers", "1", str(book), "--output", str(tmp / "client-out"),
                                   "--no-furniture", "--endpoint", endpoint, "--max-inflight", "2"])
    report = json.loads((tmp / "client-out" / "repair-report.json").read_text(encoding="utf-8"))
    efforts = [b.get("reasoning_effort") for b in bodies if b["messages"][1]["content"][0]["text"] == first.get("user")]
    check(status == 0 and bodies and all(b["max_tokens"] == 16000 for b in bodies)
          and all(b.get("reasoning_effort") == "xhigh" for b in bodies
                  if b["messages"][1]["content"][0]["text"] != first.get("user")),
          f"phase 3's Client asks every question at xhigh with max_tokens 16000 (exit {status}, {len(bodies)} "
          f"requests)")
    check(efforts == ["xhigh", "medium"], f"a reply cut off at the budget is asked again a rung lower ({efforts})")
    kinds = report["model"]["calls"]
    check(set(kinds) == {"repair-print", "repair-boundary"} and sum(k["n"] for k in kinds.values()) == len(bodies)
          and report["tokens"]["completion"] > 0,
          f"the call ledger counts every request by its repair kind, and the report its tokens ({sorted(kinds)})")


def main() -> int:
    prompt_checks()
    snap_checks()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        crop_checks(tmp)
        first = print_checks(tmp)
        resume_checks(tmp, first)
        glyph_checks(tmp)
        line_checks(tmp)
        title_copy_checks(tmp)
        layout_checks(tmp)
        boundary_checks(tmp)
        site_checks(tmp)
        guard_checks(tmp)
        numbers_checks(tmp)
        contents_number_checks(tmp)
        standin_checks(tmp)
        edge_checks(tmp)
        unit_mark_checks(tmp)
        heading_join_checks(tmp)
        follows_checks(tmp)
        client_checks(tmp)
    print(f"{'FAIL' if FAILURES else 'ok  '} check_repair_questions: {len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
