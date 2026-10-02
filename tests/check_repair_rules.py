#!/usr/bin/env python3
"""Offline check of the book repair tool's mechanical rules
(scripts/_repair_rules.py) through scripts/repair_book.py: running heads and
folios (F1-F7), engine B's stand-ins, marks and brackets (K1-K13, K-seq), and
the blank line around a heading (P5).

No model, no GPU, no corpus: made-up books (tests/repair_fixture.py), each
page changed only where a rule's case is set up.  Every rule has a case it
must repair and a look-alike it must leave:

Furniture (a book whose running head is 青山文叢 with its run's suffix, the
folio under it):
- F1: a head line (with a stray numeral, a misread character and the folio)
  is deleted; a line of the body that reads like the head, which engine A
  read in the body, stays; so do the title page's title (the stem inside a
  longer title, on a page that prints no running head) and the first
  contents page's title.
- F2: the page's own suffix alone is deleted; the divider's suffix, printed
  large, stays.  F3: the contents word alone on the second contents page is
  deleted.
- F4: a numeral line at the page's foot that is the folio engine A read in
  the band is deleted; a numeral line engine A read in the body, and one
  that is no piece of the folio, stay.
- F5: the head engine B read glued to the end of a paragraph is deleted
  there and the paragraph kept.
- F6: an adjudicator's answer at the band where engine A read nothing and
  engine B the folio is deleted; the same answer where engine B read a
  numeral that is not the folio stays.  F7: a leading line of such an answer
  and band characters is deleted.
- F2b / F2c: the suffix opening the page's first line (both engines start
  the body after it), and ending a line just before a head line (the marks
  around it become a question), are deleted.
- F5 also where engine A glued the head, suffix and folio to a body block.
- a book whose band gate fails (no folio anywhere) changes nothing.
- look-alikes on pages that print a running head, each kept: a title
  holding the stem and suffix, a paragraph opening with the book's name, the
  book named in the prose (a question where engine B alone read it), a line
  ending with the suffix before a head line, a head-like heading and a
  folio-like section numeral engine A read in one block with their
  paragraph, a numeral line that is the folio by the sequence but that no
  engine read in the band, a printed 一 that is a piece of the folio (a
  question), a head character engine B read, and a character engine A read
  and the adjudicator answered; on the title page (no running head) the
  title, the title with more after it and an answer below it; on the first
  contents page its title (the contents word) and an answer below it.

Marks (a book where engine B writes 丁 for engine A's bracketed figures,
乛 for its corner quotes, 丨 for its dashes and 丶 for its dots, besides 丶
and 口 for its commas and full stops):
- K1 writes （1） over 丁）（; a figure the page already holds, and a
  printed ）（ engine A read, stay; a figure that does not go on from the
  one before it (K-seq) is a question, not an edit; so is a character before
  a figure that stands for no mark engine A read there.
- K2 writes a heading's figure over its stand-in; K3 a dash over 丨; K4 a
  dot over 丶, and deletes 丶 beside a dot already written; K5 keeps one 口
  of 口口 with engine A's mark, and asks where engine B read a doubled 口
  besides its full stop; K6 writes 上
  over a stand-in engine A never reads; K7a deletes a quote glyph beside a
  written quote when the seal shows engine B alone put it there, and keeps
  it without that record; engine A's closing quote where the page opens
  none is a question (K7b); K8, K9, K10 fix a bracket's shape; K12 inserts
  the closing quote engine A read; K13 writes engine A's corner quotes over
  brackets, and turns neither side of a pair whose other side engine B read
  as a bracket (a question).
- guards: a glyph twice where engine A read the dash and one copy (K3), a
  figure read without the dot its neighbours carry (K-seq), a 一 of the
  text engine A read as the figure 1 (K-seq: a 1 the page holds as a CJK
  numeral needs the 2 after it), a closing
  bracket the next page supplies (K12) are left; a [ engine A read stays
  (K10); a heading figure that goes on from nothing but is the contents'
  number is written (K-seq).
- K1 writes （4） over the numeral 四 engine B read for it, on a book where
  engine B was seen to write numerals for figures (M-7b).
- a book whose engine B stand-ins are not learned (none, and no numerals
  read for figures) changes no mark.

Spacing: P5 puts a blank line after a heading that has none, and leaves a
heading engine A read in one block with the line after it - unless a date
under the heading ends that block.

Every run replays its log to its output, and the rules run again on their
own output change nothing.

Usage:
    python3 tests/check_repair_rules.py
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import offline  # noqa: E402,F401
import repair_fixture as fx  # noqa: E402

sys.path.insert(0, str(HERE.parent / "scripts"))
import _repair_edits as re_  # noqa: E402
import _repair_inputs as ri  # noqa: E402
import _repair_model as rm  # noqa: E402
import _repair_rules as rr  # noqa: E402
import repair_book  # noqa: E402


FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    print(f"{'ok  ' if condition else 'FAIL'} {message}")
    if not condition:
        FAILURES.append(message)


def run(*argv: str) -> int:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return repair_book.main(["--workers", "1", *argv])


def paragraphs(page: dict[str, Any]) -> list[str]:
    return [item[1] for item in page["items"] if item[0] == "para"]


def b_form(text: str) -> str:
    """Engine B's reading of printed text in the made-up book."""
    return text.replace("，", "丶").replace("。", "口")


def column(page: dict[str, Any]) -> tuple[int, str]:
    """The page's first body column: its index and its text."""
    columns = fx.layout(page)["columns"]
    k = next(i for i, c in enumerate(columns) if c["label"] == "vertical_text")
    return k, columns[k]["text"]


class Result:
    """What a run wrote: the exit status, the report, the log, the
    questions, and the pages."""

    def __init__(self, status: int, out: Path, book: Path):
        self.status = status
        self.out = out
        self.report = json.loads((out / "repair-report.json").read_text(encoding="utf-8"))
        self.log = [json.loads(line) for line in (out / "repair-log.jsonl").read_text(encoding="utf-8").splitlines()]
        self.questions = json.loads((out / "questions.json").read_text(encoding="utf-8"))
        self.pages = {int(p.stem.split("-")[1]): p.read_text(encoding="utf-8") for p in (out / "pages").glob("*.md")}
        self.sealed = {int(p.stem.split("-")[1]): p.read_text(encoding="utf-8")
                       for p in (book / "proofread").glob("page-*.md")}

    def rules(self, page: int) -> list[str]:
        return [r["rule"] for r in self.log if r["page"] == page]

    def asked(self, page: int) -> list[str]:
        return [q["rule"] for q in self.questions if q["page"] == page]


# The structure stages (tests/check_repair_structure.py) are off here: these
# cases change only what the furniture, mark and spacing rules act on.
STRUCTURE_OFF = ("--no-headings", "--no-contents", "--no-title-page", "--no-levels", "--no-joins")


def repair(root: Path, spec: dict[int, dict[str, Any]], name: str, *argv: str) -> Result:
    book = fx.write_book(root / name, spec)
    out = root / f"{name}-out"
    status = run(str(book), "--output", str(out), "--no-model", *STRUCTURE_OFF, *argv)
    return Result(status, out, book)


def again(root: Path, name: str, result: Result) -> list[re_.Edit]:
    """The furniture, mark and spacing rules run on RESULT's own pages (with
    the model of the book): what they would change."""
    book = ri.load_book(ri.InputPaths.resolve(root / name, {}))
    model = json.loads((result.out / "book-model.json").read_text(encoding="utf-8"))
    order = list(book.assembly.order)
    ledger = re_.Ledger({scan: result.pages[scan] for scan in order})
    facts = rr.book_facts(book, model)
    edits = rr.furniture(book, model, ledger.texts, order, facts).edits
    ledger.apply("furniture", edits)
    first: list[re_.Edit] = []

    def apply(proposed):
        first.extend(proposed)
        ledger.apply("marks", proposed)
    edits = edits + rr.marks(book, model, ledger.texts, order, apply, facts).edits + first
    return edits + rr.spacing(book, model, ledger.texts, order).edits


# --- furniture -----------------------------------------------------------------

def furniture_spec() -> dict[int, dict[str, Any]]:
    spec = fx.make_spec()
    head, digits = fx.HEAD, fx.numeral
    # F1: a head line at the foot of scan 6; one with a stray numeral, a
    # misread character and the folio on scan 8 (folio 4).
    spec[6]["extraSealed"] = [head + "甲編"]
    spec[8]["extraSealed"] = ["一" + head[0] + "丈" + head[2:] + "甲編" + digits(4)]
    # A line of the body of scan 10 that reads like the head: engine A reads
    # it in the body.
    spec[10]["items"].insert(1, ("line", head))
    # F2: the suffix alone on scan 12; F4: the folio at the foot of scan 16
    # (folio 4); a numeral line that is no piece of the folio (九) at the
    # foot of scan 14 (folio 2), and one engine A read in its body.
    spec[12]["extraSealed"] = ["# 甲編"]
    spec[16]["extraSealed"] = [digits(4)]
    spec[14]["extraSealed"] = ["九"]
    spec[14]["items"].insert(1, ("line", "五"))
    # F3: the contents word alone on the second contents page.
    first = spec[3]["items"][0][1]
    spec[3]["sealedEdits"] = [(first, "# 目次\n\n" + first)]
    # F5: engine B read the head at the end of scan 11 (headInB end); the
    # page holds it glued to its last paragraph, the folio before it.
    last = paragraphs(spec[11])[-1]
    spec[11]["sealedEdits"] = [(last, last + digits(7) + head + "甲編")]
    # F6: an answer at the band at the start of scan 15 (engine B reads the
    # head first: folio 3); the same answer where engine B read a numeral
    # that is no folio, on scan 17 (folio 7).
    for scan, engine_b in ((15, digits(3)), (17, "三一")):
        spec[scan]["headInB"] = "start"
        body = paragraphs(spec[scan])[0]
        spec[scan]["sealedEdits"] = [(body, "一" + body)]
        spec[scan]["adjudications"] = [{
            "context_before": head + "乙編", "context_after": fx.pp.CJK(body)[:8], "draft_reading": "",
            "writer_reading": engine_b, "resolved": "一", "resolved_from": "adjudicator",
            "trigger": "numeral-disagreement"}]
    # F7: a leading line of an answer at the band and band characters
    # (scan 19, folio 9: engine B reads the folio there).
    spec[19]["headInB"] = "start"
    body = paragraphs(spec[19])[0]
    spec[19]["sealedEdits"] = [(body, "丙乙編\n\n" + body)]
    spec[19]["adjudications"] = [{
        "context_before": head + "乙編", "context_after": fx.pp.CJK(body)[:8], "draft_reading": "",
        "writer_reading": digits(9), "resolved": "丙", "resolved_from": "adjudicator",
        "trigger": "engine-disagreement"}]
    # F2b: the suffix glued to the first line of scan 20, where both engines
    # start the body after it (engine B read no head there: where it read
    # one, F5 takes the same span); F2c: the suffix ending a line of scan 7
    # just before a head line (engine B read its head at the page's start).
    body = paragraphs(spec[20])[0]
    spec[20]["sealedEdits"] = [(body, "乙編" + body)]
    spec[20]["bHeadless"] = True
    last = paragraphs(spec[7])[-1]
    spec[7]["sealedEdits"] = [(last, last + "，甲編，")]
    spec[7]["extraSealed"] = [head]
    spec[7]["headInB"] = "start"
    # F5 where engine A glued the band - head, suffix and folio - to the end
    # of scan 18's last body column (folio 8), and the seal holds the head
    # and suffix glued to the last paragraph.
    last = paragraphs(spec[18])[-1]
    spec[18]["headInB"] = "end"
    spec[18]["aHeadless"] = True
    spec[18]["aEdits"] = [(last[-5:], last[-5:] + head + "乙編" + digits(8))]
    spec[18]["sealedEdits"] = [(last, last + head + "乙編")]
    return spec


def furniture_checks(tmp: Path) -> None:
    spec = furniture_spec()
    result = repair(tmp, spec, "furniture", "--no-marks", "--no-paragraphs")
    pages, sealed = result.pages, result.sealed
    head = fx.HEAD
    check(result.status == 0 and result.report["checks"]["logReplay"]["passed"] is True,
          f"the run exits 0 and its log replays to its output (exit {result.status})")
    check(result.rules(6) == ["F1"] and head + "甲編" not in pages[6] and pages[6].endswith("。\n"),
          f"F1: a head line at the page's foot is deleted, one separator left ({result.rules(6)})")
    check(result.rules(8) == ["F1"] and "丈" not in pages[8],
          f"F1: a head line with a stray numeral, a misread character and the folio is deleted ({result.rules(8)})")
    check(not result.rules(10) and "\n" + head + "\n" in pages[10],
          f"F1: a line of the body that reads like the head, which engine A read in the body, stays "
          f"({result.rules(10)})")
    check(not result.rules(1) and pages[1] == sealed[1] and not result.rules(2),
          "F1/F5: the title page's title (the stem inside it, on a page with no running head) and the first "
          "contents page's title stay")
    check(result.rules(12) == ["F2"] and "甲編" not in pages[12], f"F2: the suffix alone is deleted ({result.rules(12)})")
    check(not result.rules(5) and pages[5] == sealed[5] and not result.rules(13),
          "F2: the dividers' suffix, printed large, stays")
    check(result.rules(3) == ["F3"] and "# 目次" not in pages[3],
          f"F3: the contents word alone on the second contents page is deleted ({result.rules(3)})")
    check(result.rules(16) == ["F4"] and not pages[16].rstrip().endswith(fx.numeral(4)),
          f"F4: the folio at the page's foot is deleted ({result.rules(16)})")
    check(not result.rules(14) and pages[14].rstrip().endswith("九") and "\n五\n" in pages[14],
          "F4: a numeral line that is no piece of the folio, and one engine A read in the body, stay")
    check(result.rules(11) == ["F5"] and head not in pages[11] and pages[11].rstrip().endswith("。"),
          f"F5: the head engine B read glued to a paragraph's end is deleted there, the paragraph kept "
          f"({result.rules(11)})")
    check(result.rules(18) == ["F5"] and head not in pages[18] and pages[18].rstrip().endswith("。"),
          f"F5: the head engine A glued (with its suffix and folio) to the end of a body block is deleted "
          f"({result.rules(18)})")
    first15 = paragraphs(spec[15])[0]
    check(result.rules(15) == ["F6"] and first15 in pages[15] and "一" + first15 not in pages[15],
          f"F6: the answer at the band is deleted ({result.rules(15)})")
    check(not result.rules(17) and "一" + paragraphs(spec[17])[0] in pages[17],
          "F6: the same answer where engine B read a numeral that is not the folio stays")
    check(result.rules(19) == ["F7"] and "丙乙編" not in pages[19],
          f"F7: a leading line of an answer and band characters is deleted ({result.rules(19)})")
    check(result.rules(20) == ["F2b"] and pages[20].startswith(paragraphs(spec[20])[0]),
          f"F2b: the suffix opening the first line is deleted ({result.rules(20)})")
    check(sorted(result.rules(7)) == ["F1", "F2c"] and "甲編" not in pages[7] and "F2c" in result.asked(7),
          f"F2c: the suffix ending a line before a head line is deleted, and its marks are a question "
          f"({result.rules(7)}, asked {result.asked(7)})")
    extra = sorted({r["page"] for r in result.log} - {3, 6, 7, 8, 11, 12, 15, 16, 18, 19, 20})
    check(not extra, f"no page but the cases' changes ({extra})")
    check(not again(tmp, "furniture", result), "the rules run on their own output change nothing")

    spec = furniture_spec()
    for page in spec.values():
        page["folio"] = None
    result = repair(tmp, spec, "no-band", "--no-marks", "--no-paragraphs")
    check(result.status == 0 and not result.log and result.report["gates"]["M-1"] is False,
          f"with the band's gate failed (no folio anywhere) the furniture rules change nothing "
          f"({[r['rule'] for r in result.log]})")
    lookalike_checks(tmp)


def set_paragraph(page: dict[str, Any], old: str, new: str) -> None:
    """The page prints NEW where it printed the paragraph OLD."""
    k = next(i for i, item in enumerate(page["items"]) if item[0] == "para" and item[1] == old)
    page["items"][k] = ("para", new, page["items"][k][2])


def lookalike_spec() -> dict[int, dict[str, Any]]:
    """Printed text that looks like the band, on pages that print a running
    head (a folio in the band): each must stay."""
    spec = fx.make_spec()
    head, digits = fx.HEAD, fx.numeral
    # F5: a title holding the stem and the run's suffix at the top of scan 7
    # (engine B reads it before its head, at the start of its reading); a
    # paragraph opening scan 17 with the book's name (engine B reads its head
    # last); the book named in the prose of scan 8.
    spec[7]["items"].insert(0, ("heading", head + "甲編序", 3))
    body = paragraphs(spec[17])[0]
    set_paragraph(spec[17], body, head + "所收諸篇，" + body)
    body = paragraphs(spec[8])[1]
    set_paragraph(spec[8], body, body[:20] + "讀" + head + "，" + body[20:])
    # The same on scan 12, where engine A dropped the name: engine B alone
    # read it, inside its reading of the body.
    body = paragraphs(spec[12])[1]
    set_paragraph(spec[12], body, body[:20] + "讀" + head + "，" + body[20:])
    spec[12]["aEdits"] = [("讀" + head + "，", "讀，")]
    # F2c: a line of scan 9 that ends with the run's suffix (both engines
    # read it), just before a head line the seal holds.
    last = paragraphs(spec[9])[-1]
    set_paragraph(spec[9], last, last[:-1] + "，見甲編。")
    spec[9]["extraSealed"] = [head + "甲編"]
    spec[9]["headInB"] = "start"
    # F1 / F4: a heading that reads like the head (scan 10), and a section's
    # numeral that is the folio (scan 16, folio 4), each printed in its own
    # line, which engine A read in one block with the paragraph after it.
    for scan, lead in ((10, head + "甲編"), (16, digits(4))):
        body = paragraphs(spec[scan])[0]
        set_paragraph(spec[scan], body, lead + body)
        spec[scan]["sealedEdits"] = [(lead + body, lead + "\n\n" + body)]
    # F6: the first paragraph of scan 20 (folio 一〇) opens with a printed 一
    # and that of scan 19 (folio 9) with a printed 山, a character of the
    # head: engine A dropped them, engine B read them, and the adjudicator
    # answered them from the image.  On scan 15 engine A read a printed 山
    # where engine B read the folio, and the adjudicator answered 山.
    for scan, char, a_reads in ((20, "一", False), (19, "山", False), (15, "山", True)):
        spec[scan]["headInB"] = "start"
        body = paragraphs(spec[scan])[0]
        set_paragraph(spec[scan], body, char + body)
        if a_reads:
            spec[scan]["bEdits"] = [(char + b_form(body[:5]), digits(spec[scan]["folio"]) + b_form(body[:5]))]
        else:
            spec[scan]["aEdits"] = [(char + body[:6], body[:6])]
        spec[scan]["adjudications"] = [{
            "context_before": head + "乙編", "context_after": fx.pp.CJK(body)[:8],
            "draft_reading": char if a_reads else "", "writer_reading": digits(spec[scan]["folio"]) if a_reads else char,
            "resolved": char, "resolved_from": "adjudicator", "trigger": "engine-disagreement"}]
    # The title page prints no running head: its lines are the book's title
    # with more after it (F5), the title alone (F1), and an author's line
    # whose first character neither engine read and the adjudicator answered
    # below the title (F6).  Engine A read none of the title's lines in its
    # body.
    spec[1]["items"] = [("line", head + "全集"), ("heading", head, 1), ("line", "林泉撰")]
    spec[1]["aEdits"] = [(head + "全集", ""), (head, ""), ("林泉撰", "泉撰")]
    spec[1]["bEdits"] = [("林泉撰", "泉撰")]
    spec[1]["adjudications"] = [{
        "context_before": head, "context_after": "泉撰", "draft_reading": "", "writer_reading": "",
        "resolved": "林", "resolved_from": "adjudicator", "trigger": "engine-disagreement"}]
    # The first contents page prints its title as the contents word alone
    # (engine A did not read it in its body: F3), and an adjudicator's answer
    # below it that neither engine read (F6).
    spec[2]["sealedEdits"] = [("# " + head + fx.CONTENTS_WORD, "# " + fx.CONTENTS_WORD)]
    spec[2]["aEdits"] = [(head + fx.CONTENTS_WORD, ""), ("甲編 詩文", "編 詩文")]
    spec[2]["bEdits"] = [("甲編 詩文", "編 詩文")]
    spec[2]["adjudications"] = [{
        "context_before": fx.CONTENTS_WORD, "context_after": "編詩文", "draft_reading": "", "writer_reading": "",
        "resolved": "甲", "resolved_from": "adjudicator", "trigger": "engine-disagreement"}]
    # F4: scan 14 (folio 2) opens with a printed 二 engine A did not read;
    # no engine read the folio in the band (engine A misread its folio block,
    # engine B read no head).
    spec[14]["items"].insert(0, ("line", "二"))
    spec[14]["aEdits"] = [("二", "")]
    spec[14]["aFolio"] = "工"
    spec[14]["bHeadless"] = True
    return spec


def lookalike_checks(tmp: Path) -> None:
    spec = lookalike_spec()
    result = repair(tmp, spec, "lookalikes", "--no-marks", "--no-paragraphs")
    pages, sealed = result.pages, result.sealed
    check(result.status == 0 and result.report["checks"]["logReplay"]["passed"] is True,
          f"look-alikes: the run exits 0 and its log replays to its output (exit {result.status})")
    check(not result.rules(7) and pages[7] == sealed[7],
          f"F5: a title holding the stem and the suffix, which both engines read, stays ({result.rules(7)})")
    check(not result.rules(17) and pages[17] == sealed[17],
          f"F5: a paragraph opening with the book's name, which both engines read, stays ({result.rules(17)})")
    check(not result.rules(8) and pages[8] == sealed[8],
          f"F5: the book named in the prose, which both engines read, stays ({result.rules(8)})")
    check(not result.rules(12) and pages[12] == sealed[12] and "F5" in result.asked(12),
          f"F5: the book named in the prose, which engine B alone read inside the body, stays and is a question "
          f"({result.rules(12)}, asked {result.asked(12)})")
    check(result.rules(9) == ["F1"] and "見甲編。" in pages[9],
          f"F2c: a line that ends with the suffix both engines read stays before the head line F1 deletes "
          f"({result.rules(9)})")
    check(not result.rules(10) and pages[10] == sealed[10],
          f"F1: a heading that reads like the head, which engine A read in one block with its paragraph, stays "
          f"({result.rules(10)})")
    check(not result.rules(16) and pages[16] == sealed[16],
          f"F4: a section numeral that is the folio, which engine A read in one block with its paragraph, stays "
          f"({result.rules(16)})")
    check(not result.rules(20) and pages[20] == sealed[20] and "F6" in result.asked(20),
          f"F6: a printed 一 that engine B read, a piece of the folio 一〇, stays and is a question "
          f"({result.rules(20)}, asked {result.asked(20)})")
    check(not result.rules(19) and pages[19] == sealed[19],
          f"F6: a printed character of the head that engine B read stays ({result.rules(19)})")
    check(not result.rules(15) and pages[15] == sealed[15],
          f"F6: a character engine A read and the adjudicator answered stays ({result.rules(15)})")
    check(not result.rules(1) and pages[1] == sealed[1],
          f"F1/F5/F6: the title page's title, the title with more after it, and an answer below it stay on a page "
          f"that prints no running head ({result.rules(1)})")
    check(not result.rules(2) and pages[2] == sealed[2],
          f"F3/F6: the first contents page's title (the contents word) and an answer below it stay "
          f"({result.rules(2)})")
    check(not result.rules(14) and pages[14] == sealed[14],
          f"F4: a numeral line that is the folio by the sequence, which no engine read in the band, stays "
          f"({result.rules(14)})")
    extra = sorted({r["page"] for r in result.log} - {9})
    check(not extra, f"look-alikes: no page but the head line's changes ({extra})")


# --- marks and spacing ---------------------------------------------------------

def edit_column(spec: dict[int, dict[str, Any]], scan: int, cut: int, a_text: str, sealed: str | None = None,
                b_text: str | None = None, end: int | None = None) -> None:
    """At character CUT of scan SCAN's first body column (to END, replaced):
    engine A reads A_TEXT there, the page holds SEALED (engine A's reading
    when None: the figure or mark is printed and written), engine B reads
    B_TEXT (nothing when None)."""
    page = spec[scan]
    k, text = column(page)
    end = cut if end is None else end
    marks = dict(page.get("aMarks") or {})
    current = marks.get(k, text)
    offset = len(current) - len(text)
    marks[k] = current[:cut + offset] + a_text + current[end + offset:]
    page["aMarks"] = marks
    # The page's own text is found by the four characters before the place.
    lead = text[max(0, cut - 4):cut]
    if sealed is not None:
        page.setdefault("sealedEdits", []).append((lead + text[cut:end], lead + sealed))
    if b_text is not None:
        page.setdefault("bEdits", []).append((b_form(lead + text[cut:end]), b_form(lead) + b_text))


def marks_spec() -> dict[int, dict[str, Any]]:
    spec = fx.make_spec()
    # What engine B writes on this book, on enough pages for M-7 to learn:
    # 丁 for engine A's bracketed figures (between two 一), 丨 for a dash,
    # 丶 for a dot, 乛 for corner quotes.
    for scan, number, sealed in ((6, 1, "丁）（"), (8, 2, "（2）"), (10, 3, "丁）（"), (14, 9, "丁）（")):
        edit_column(spec, scan, 3, f"（{number}）", sealed, "一丁一")
    for scan, sealed in ((7, "丨"), (9, None), (11, None)):
        edit_column(spec, scan, 5, "——", sealed, "丨")
    for scan, sealed in ((15, "丶"), (18, None)):
        edit_column(spec, scan, 4, "·", sealed, "丶")
    for scan in (16, 17, 19):
        k, text = column(spec[scan])
        edit_column(spec, scan, 6, "「" + text[6:9] + "」", "「乛" + text[6:9] + "」" if scan in (16, 17) else None,
                    "乛" + b_form(text[6:9]) + "乛", end=9)
    # K7a's record: engine B alone put 乛 there (a question engine A read
    # nothing for) on scan 16; scan 17 has no such record.
    k, text = column(spec[16])
    spec[16]["adjudications"] = [{"context_before": fx.pp.CJK(text[:6])[-8:], "context_after": text[6:9],
                                  "draft_reading": "", "writer_reading": "乛", "resolved": "乛",
                                  "resolved_from": "engine-A-default", "trigger": "engine-disagreement"}]
    # K7b refused: on scan 8 engine A read 「…」 but the page holds only the
    # glyph engine B wrote for the closing quote, with the seal's record;
    # engine A's 」 there would close nothing the page opens.
    k, text = column(spec[8])
    edit_column(spec, 8, 10, "「" + text[10:13] + "」", text[10:13] + "乛", "乛" + b_form(text[10:13]) + "乛", end=13)
    spec[8]["adjudications"] = [{"context_before": fx.pp.CJK(text[:13])[-8:], "context_after": fx.pp.CJK(text[13:])[:8],
                                 "draft_reading": "", "writer_reading": "乛", "resolved": "乛",
                                 "resolved_from": "engine-A-default", "trigger": "engine-disagreement"}]
    # K2: a heading whose figure the page holds as a stand-in.
    heading = next(item[1] for item in spec[9]["items"] if item[0] == "heading")
    spec[9]["sealedEdits"] = [("### " + heading, "### 丁" + heading.split(" ", 1)[1])]
    # K5: 口 written twice where engine A read it once, before its full stop.
    edit_column(spec, 20, 6, "口。", "口口。", "口口")
    # A printed doubled 口 after a full stop (scan 4): engine A read one,
    # engine B both and a third for the full stop.
    edit_column(spec, 4, 10, "。口", "。口口", "口口口")
    # A dot the page already holds beside engine B's glyph for it (scan 4).
    edit_column(spec, 4, 30, "•", "·丶", "丶")
    # A printed 口 (engine B's glyph for a full stop too) just before a
    # bracketed figure (scan 13): engine A dropped it, engine B read it.
    edit_column(spec, 13, 8, "（1）", "口（1）", "口一丁一")
    # K6: a stand-in engine A never reads, where engine A read 上.
    edit_column(spec, 12, 8, "上", "丁", "丁")
    # A printed ）（ engine A read, before a bracketed figure.
    edit_column(spec, 12, 3, "）（5）", "）（5）")
    # K8, K9, K10, K12, K13.
    edit_column(spec, 19, 16, "（二）", "（二、）", "八二一")
    k, text = column(spec[17])
    spec[17]["sealedEdits"] = spec[17].get("sealedEdits", []) + [(text[10:14], "︵" + text[10:13] + "︶" + text[13])]
    spec[14]["items"].insert(1, ("line", "4.牧童晚歸"))
    spec[14]["sealedEdits"] = spec[14].get("sealedEdits", []) + [("4.牧童晚歸", "[4.牧童晚歸")]
    k, text = column(spec[10])
    edit_column(spec, 10, 12, "「" + text[12:15] + "」", "「" + text[12:15], "乛" + b_form(text[12:15]) + "乛", end=15)
    k, text = column(spec[20])
    edit_column(spec, 20, 14, "「" + text[14:17] + "」", "（" + text[14:17] + "）", "乛" + b_form(text[14:17]) + "乛",
                end=17)
    # The same on scan 18, where engine B read the closing one as a bracket.
    k, text = column(spec[18])
    edit_column(spec, 18, 14, "「" + text[14:17] + "」", "（" + text[14:17] + "）", "乛" + b_form(text[14:17]) + "）",
                end=17)
    # P5: a heading with no blank line after it; a heading printed over two
    # lines, engine A's one block.
    heading = next(item[1] for item in spec[5]["items"] if item[0] == "heading")
    spec[5]["sealedEdits"] = [("### " + heading + "\n\n", "### " + heading + "\n")]
    heading = next(item[1] for item in spec[11]["items"] if item[0] == "heading")
    spec[11]["sealedEdits"] = [("### " + heading, "### " + heading[:-2] + "\n" + heading[-2:])]
    # A heading engine A read in one block with the date printed under it
    # (scan 7): the date ends the heading's block, so the blank line goes in.
    k = next(i for i, item in enumerate(spec[7]["items"]) if item[0] == "heading")
    heading = spec[7]["items"][k][1]
    spec[7]["items"][k] = ("heading", heading + "十七年五月", spec[7]["items"][k][2])
    spec[7]["sealedEdits"] = spec[7].get("sealedEdits", []) + [
        ("### " + heading + "十七年五月", "### " + heading + "\n十七年五月")]
    # K3: engine A read the dash, then the glyph as a character (engine B
    # the glyph once); the page holds it twice (scan 4): which copy is the
    # dash is a reading.
    edit_column(spec, 4, 36, "——丨", "丨丨", "丨")
    # K10: a [ opening a line before a figure, which engine A read too.
    spec[14]["items"].insert(2, ("line", "[5.漁舟唱晚"))
    # K-seq: a list whose figures carry a dot (scan 19), the middle one read
    # by engine A without it where the page holds a stand-in.
    for n, words in ((1, "春風吹"), (2, "小橋流"), (3, "水人家")):
        spec[19]["items"].insert(n, ("line", f"{n}.{words}"))
    spec[19]["aEdits"] = [("2.小橋流", "2小橋流")]
    spec[19]["sealedEdits"] = spec[19].get("sealedEdits", []) + [("2.小橋流", "丁小橋流")]
    # Engine B reads engine A's （5） as the numeral 五 on three pages, the
    # page holding （5）: M-7b sees engine B write numerals for figures.
    for scan in (15, 16, 20):
        edit_column(spec, scan, 30, "（5）", "（5）", "五")
    # K1 over a numeral: the page holds 四）（ where engine A read （4）
    # (scan 11), engine B the numeral between its bracket strokes.
    edit_column(spec, 11, 20, "（4）", "四）（", "一四一")
    # K-seq for a figure the page holds in CJK numerals: a line printed
    # 一般原則 that engine A read 1般原則 (scan 16), and a list on scan 17
    # whose first figure the page holds as 一, with 2 after it.
    spec[16]["items"].insert(1, ("line", "一般原則"))
    spec[16]["aEdits"] = [("一般原則", "1般原則")]
    spec[17]["items"][1:1] = [("line", "1.漁舟唱"), ("line", "2.竹籬茅")]
    spec[17]["sealedEdits"] = spec[17].get("sealedEdits", []) + [("1.漁舟唱", "一漁舟唱")]
    # K-seq by the contents: engine A misread scan 15's heading figure (7 for
    # 2), so scan 18's figure 3 goes on from nothing; the contents give 3.
    spec[15]["aEdits"] = [("2 田園小記", "7 田園小記")]
    spec[18]["sealedEdits"] = spec[18].get("sealedEdits", []) + [("### 3 松下問答", "### 丁松下問答")]
    # K12: scan 19's last paragraph opens a bracket that scan 20 closes;
    # engine A read a closing one on scan 19 that is not printed.
    last = paragraphs(spec[19])[-1]
    printed = last[:-6] + "（" + last[-6:-1]
    set_paragraph(spec[19], last, printed)
    spec[19]["aEdits"].append(("（" + last[-6:-4], "（" + last[-6:-4] + "）"))
    first = paragraphs(spec[20])[0]
    at = [i for i, c in enumerate(first) if c == "，"][5]
    set_paragraph(spec[20], first, first[:at] + "）" + first[at:])
    return spec


def marks_checks(tmp: Path) -> None:
    spec = marks_spec()
    result = repair(tmp, spec, "marks", "--no-furniture")
    pages = result.pages
    model = json.loads((result.out / "book-model.json").read_text(encoding="utf-8"))
    standins = model["standIns"]
    check("丁" in standins["figure"] and "丨" in standins["dash"] and "丶" in standins["dot"]
          and "乛" in standins["markAliases"]["B"],
          f"M-7 learns the made-up book's stand-ins ({standins['figure']}, {standins['dash']}, {standins['dot']}, "
          f"{sorted(standins['markAliases']['B'])})")
    check(result.status == 0 and result.report["checks"]["logReplay"]["passed"] is True,
          f"the run exits 0 and its log replays to its output (exit {result.status})")
    k, text = column(spec[6])
    check("K1" in result.rules(6) and text[:3] + "（1）" + text[3:6] in pages[6] and "丁" not in pages[6],
          f"K1: （1） over the stand-ins ({result.rules(6)})")
    check(not result.rules(8) and "（2）" in pages[8], "K1: a figure the page already holds stays")
    check("K1" not in result.rules(13) and "口（1）" in pages[13] and "K1" in result.asked(13),
          f"K1: a character before the figure that stands for no mark engine A read there stays, and is a "
          f"question ({result.rules(13)}, asked {result.asked(13)})")
    check("K7b" in result.asked(8) and "乛" in pages[8],
          f"K7b: engine A's closing quote where the page opens none is a question, not an edit "
          f"(asked {result.asked(8)})")
    check("K1" in result.rules(10), f"K1: （3） follows （2） ({result.rules(10)})")
    check("K1" in result.rules(11) and "（4）" in pages[11] and "四）（" not in pages[11],
          f"K1: （4） over the numeral engine B read for it, on a book where engine B writes numerals for "
          f"figures ({result.rules(11)})")
    check("K1" not in result.rules(14) and "丁）（" in pages[14] and "K-seq" in result.asked(14),
          f"K-seq: （9） after （3） is a question, not an edit ({result.rules(14)}, asked {result.asked(14)})")
    check("K3" in result.rules(7) and "——" in pages[7] and "丨" not in pages[7], f"K3: —— over 丨 ({result.rules(7)})")
    check("K4b" in result.rules(15) and "·" in pages[15], f"K4b: the dot over 丶 ({result.rules(15)})")
    check("K4a" in result.rules(4) and "··" not in pages[4] and "·" in pages[4] and "丶" not in pages[4],
          f"K4a: the glyph beside a dot the page already holds goes, and no second dot is written "
          f"({result.rules(4)})")
    check("K7a" in result.rules(16) and "乛" not in pages[16], f"K7a: the quote glyph beside a written quote, which "
          f"the seal shows engine B alone put there, is deleted ({result.rules(16)})")
    check("K7a" not in result.rules(17) and "乛" in pages[17],
          "K7a: the same glyph without that record stays")
    heading = next(item[1] for item in spec[9]["items"] if item[0] == "heading")
    check("K2" in result.rules(9) and "### " + heading in pages[9], f"K2: the heading's figure ({result.rules(9)})")
    check("K5" in result.rules(20) and "口口" not in pages[20], f"K5: one 口 of two ({result.rules(20)})")
    check("K5" not in result.rules(4) and "。口口" in pages[4] and "K5" in result.asked(4),
          f"K5: a doubled 口 engine B read twice besides the full stop stays, and is a question "
          f"({result.rules(4)}, asked {result.asked(4)})")
    check("K6" in result.rules(12) and "丁" not in pages[12] and "上" in pages[12] and "）（5）" in pages[12],
          f"K6: 上 over a stand-in engine A never reads; a printed ）（ engine A read stays ({result.rules(12)})")
    check("K8" in result.rules(19) and "（二）" in pages[19], f"K8: （二、） becomes （二） ({result.rules(19)})")
    check("K9" in result.rules(17) and "︵" not in pages[17], f"K9: ︵︶ become （） ({result.rules(17)})")
    check("K10" in result.rules(14) and "[4." not in pages[14], f"K10: [ before a line's figure ({result.rules(14)})")
    check("K12" in result.rules(10) and "」" in pages[10], f"K12: the closing quote engine A read ({result.rules(10)})")
    k, text = column(spec[20])
    check("K13" in result.rules(20) and "「" + text[14:17] + "」" in pages[20] and "（" + text[14:17] not in pages[20],
          f"K13: engine A's corner quotes over brackets ({result.rules(20)})")
    k, text = column(spec[18])
    check("K13" not in result.rules(18) and "（" + text[14:17] + "）" in pages[18] and "K13" in result.asked(18),
          f"K13: a bracket pair engine B read a bracket of turns on neither side, and is a question "
          f"({result.rules(18)}, asked {result.asked(18)})")
    heading = next(item[1] for item in spec[5]["items"] if item[0] == "heading")
    check("P5" in result.rules(5) and "### " + heading + "\n\n" in pages[5],
          f"P5: a blank line after a heading that had none ({result.rules(5)})")
    check("P5" not in result.rules(11), f"P5: a heading engine A read in one block with the next line gets none "
                                         f"({result.rules(11)})")
    check("P5" in result.rules(7) and "秋夜讀書\n\n十七年五月" in pages[7],
          f"P5: a heading engine A read in one block with the date under it gets its blank line ({result.rules(7)})")
    check("K3" not in result.rules(4) and "丨丨" in pages[4] and "K3" in result.asked(4),
          f"K3: a glyph twice where engine A read the dash and one copy is a question ({result.rules(4)}, "
          f"asked {result.asked(4)})")
    check("[5.漁舟唱晚" in pages[14], "K10: a [ engine A read before a line's figure stays")
    check("丁小橋流" in pages[19] and "K-seq" in result.asked(19),
          f"K-seq: a figure engine A read without the dot the figures beside it carry is a question "
          f"({result.rules(19)}, asked {result.asked(19)})")
    check("一般原則" in pages[16] and "K-seq" in result.asked(16),
          f"K-seq: a line's 一 engine A read as the figure 1, with no 2 after it, is a question "
          f"({result.rules(16)}, asked {result.asked(16)})")
    check("K2" in result.rules(17) and "1.漁舟唱" in pages[17],
          f"K-seq: a list's first figure the page holds as 一, with 2 after it, is written ({result.rules(17)})")
    check("K2" in result.rules(18) and "### 3 松下問答" in pages[18],
          f"K-seq: a heading's figure the contents give its title is written ({result.rules(18)}, "
          f"asked {result.asked(18)})")
    check("K12" not in result.rules(19), f"K12: no closing bracket where the next page closes it "
                                         f"({result.rules(19)})")
    check(not again(tmp, "marks", result), "the rules run on their own output change nothing")

    book = ri.load_book(ri.InputPaths.resolve(tmp / "marks", {}))
    bare = copy.deepcopy(model)
    bare["standIns"] = {"markAliases": {"A": {}, "B": {}}, "figure": [], "dash": [], "dot": []}
    order = list(book.assembly.order)
    ledger = re_.Ledger({scan: book.pages[scan].sealed_text for scan in order})
    first: list[re_.Edit] = []
    plan = rr.marks(book, bare, ledger.texts, order, lambda edits: first.extend(edits), rr.book_facts(book, bare))
    rules = sorted({e.rule for e in first + plan.edits} - {"K8", "K9", "K10", "K12", "K13"})
    check(not rules, f"with no stand-ins learned (nor numerals read for figures) no rule that acts on a stand-in "
                     f"(K1-K7) fires ({rules})")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        furniture_checks(Path(tmp))
        marks_checks(Path(tmp))
    print(f"{'FAIL' if FAILURES else 'ok  '} check_repair_rules: {len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
