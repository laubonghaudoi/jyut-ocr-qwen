#!/usr/bin/env python3
"""Offline check of the book repair tool's text-run stage
(scripts/_repair_runs.py, stage `runs`) through scripts/repair_book.py.

No model, no GPU, no corpus: a made-up book (tests/repair_fixture.py), each
page changed only where a case is set up.  Every rule has a case it must
repair and a look-alike it must leave:

- N1 writes a figure both engines read between two characters the page
  holds without it (T1); a bracketed Latin name both engines read where
  the page holds the empty bracket pair; where the page has one mark of
  the engines' and lacks the others (T2), the figure with the marks beside
  it - but not a bracket that would find no partner on its line; a table
  cell's figure where the page's row has the empty cell; a figure in a
  table row that phase 3 moved to the page before (the seal's tableStitch),
  written there.
- N5 writes the marks both engines read in a table's cells where the page
  holds none, the cells' characters in an engine A block labelled a table
  (one the punctuator never read): a comma between two characters, a full
  stop before a cell boundary, the two title marks of a pair written in
  two gaps of one row, a dash in an empty cell, the marks either side of a
  cell's line break, each line's marks on its side of a space the page
  holds where engine A breaks the line; in the rows phase 3 moved to the
  page before, also where the rule under the continuation's first row
  stands between the two rows an edit touches.  Left: the same marks in
  running text, on a line that merely holds a pipe, and in a page table
  whose characters lie in a punctuated text block; a gap where the engines
  differ (no doubt); a bracket whose partner is not written, two brackets
  with a cell boundary between them, and the two about a gap between them
  that is not written where engine A reads brackets there (two titles
  would read as one); a star, a character a renderer reads as markup, one
  that prints nothing; a gap beside a note marker; a gap where the page
  holds a mark or a model answer wrote; cell boundaries that are not the
  engines' one to one; a page punctuated whole, and the one table of a
  page rebuilt from its crop (the seal's record).  The marks the rule found
  and could not write - on the page, or in moved rows whose host row has
  changed - are one `run-no-place` doubt a page, with their count; an edit
  whose cell marks were all withheld is N1's.
- N2 writes a whole line of Western text both engines read between two
  paragraphs, one engine with emphasis markers in it.
- N3 rewrites `）（` as the engines' `（1522-66）`.
- R1 puts back a refused first answer's mark where it equals engine A's and
  the page's kept retry differs; a first answer that differs from engine A
  changes nothing.
- N4 (called on its own: an S11 record made for it) moves an entry's number
  the contents stage put at the head of its line back to the end of the
  line before, where both engines read it; run again, the stage changes
  nothing.
- left alone, as doubts: a figure the engines read differently
  (`run-engines-differ`); one engine A alone read (`run-one-engine`); one
  beside a note marker (`note-markers-unverified`, no run written); a
  figure that opens a line in engine A (`run-no-place`); a figure the page
  already holds (nothing).
- `--no-runs` switches the stage off; every run replays its log to its
  output; the made-up book with nothing to repair gets no edit from the
  stage (tests/check_repair_readonly.py).

Usage:
    python3 tests/check_repair_runs.py
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import re
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
import _repair_rules as rr  # noqa: E402
import _repair_runs as rn  # noqa: E402
import proofread_pages as pp  # noqa: E402
import repair_book  # noqa: E402


FAILURES: list[str] = []
OTHER_STAGES_OFF = ("--no-furniture", "--no-marks", "--no-headings", "--no-contents", "--no-title-page",
                    "--no-levels", "--no-paragraphs", "--no-joins")


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
    return text.replace("，", "丶").replace("。", "口")


def insert(spec: dict[int, dict[str, Any]], scan: int, para: int, a_text: str, b_text: str | None,
           sealed_text: str | None, at: int = 1) -> tuple[str, str]:
    """Put A_TEXT (engine A), B_TEXT (engine B) and SEALED_TEXT (the page)
    between characters AT+1 and AT+2 of paragraph PARA of SCAN (a stretch
    with no mark in it); returns the two characters either side."""
    text = paragraphs(spec[scan])[para]
    old = text[at:at + 4]
    assert "，" not in old and text.count(old) == 1, (scan, para, old)
    left, right = old[:2], old[2:]
    page = spec[scan]
    page.setdefault("aEdits", []).append((old, left + a_text + right))
    if b_text is not None:
        page.setdefault("bEdits", []).append((b_form(old), b_form(left) + b_text + b_form(right)))
    if sealed_text is not None:
        page.setdefault("sealedEdits", []).append((old, left + sealed_text + right))
    return left, right


def make_spec() -> dict[int, dict[str, Any]]:
    spec = fx.make_spec()
    # N1 T1: a year both engines read; a bracketed Latin name where the page
    # holds the empty pair; T2: the page holds the opening bracket only.
    insert(spec, 6, 0, "1989", "1989", None)
    insert(spec, 6, 1, "（G. W. Skinner）", "(G. W. Skinner)", "（）")
    insert(spec, 6, 2, "（1522-66）", "(1522-66)", "（")
    # T2: the comma before a year, written with it beside the bracket the
    # page has; an opening bracket with no partner on its line, withheld.
    insert(spec, 6, 0, "，1996）", "，1996）", "）", at=9)
    insert(spec, 6, 1, "7〈", "7〈", None, at=9)
    # Left alone: the engines differ; engine A alone; a note marker beside it.
    insert(spec, 8, 0, "1989", "1980", None)
    insert(spec, 8, 1, "1989", None, None)
    insert(spec, 8, 2, "⑫1989", "⑫1989", None)
    # The page already holds the figure; a figure that opens a line of engine
    # A (the second column of the paragraph: its 39th character).
    insert(spec, 10, 0, "1989", "1989", "1989")
    insert(spec, 10, 2, "1989", "1989", "1980")
    text = paragraphs(spec[10])[1]
    old = text[43:47]
    assert "，" not in old and text.count(old) == 1 and len(pp.CJK(text[:43])) == 38
    spec[10].setdefault("aEdits", []).append((old, "18" + old))
    spec[10].setdefault("bEdits", []).append((b_form(old), "18" + b_form(old)))
    # N3: the bracket pair reversed and emptied on the page.
    insert(spec, 12, 0, "（1522-66）", "(1522-66)", "）（")
    # A table: the page's row has an empty cell and a cell short of its
    # figure; engine A the HTML table, engine B the row as a line.
    spec[12]["extraSealed"] = ["| 贛州 | | 弘治 |"]
    spec[12]["extraBlocks"] = [{"text": "<table><tr><td>贛州</td><td>1496</td><td>弘治9</td></tr></table>",
                                "boundingBox": [0.1, 0.9, 0.5, 0.03], "blockLabel": "table"}]
    last = paragraphs(spec[12])[2]
    tail = b_form(last[-4:])
    spec[12].setdefault("bEdits", []).append((tail, tail + "\n贛州 1496 弘治9"))
    # N2: a line of Western text between scan 8's last two paragraphs (no
    # full stop there: engine B writes one as a character), engine B with
    # emphasis markers around the title.
    end = paragraphs(spec[8])[1][-2:]
    spec[8].setdefault("sealedEdits", []).append((end, end[:-1]))
    spec[8].setdefault("aEdits", []).append((end, end[:-1] + "\nHobsbawm, E. J. Bandits. London: Weidenfeld, 1969."))
    spec[8].setdefault("bEdits", []).append((b_form(end), end[:-1] + "\nHobsbawm, E. J. *Bandits*. London: Weidenfeld, 1969."))
    # A table row of scan 18 that phase 3 moved into scan 17's table: the
    # seal of scan 18 holds its text before the move and the row moved;
    # scan 18's engines read the row with its figure.
    spec[17]["extraSealed"] = ["| 贛州 | 弘治 |\n| --- | --- |\n| 南安 | 嘉靖 |"]
    before = fx.sealed_text(spec[18]) + "\n| 南安 | 嘉靖 |\n"
    spec[18]["tableStitch"] = {"before": before, "continuation": {"head": {"page": 17, "table": 0},
                                                                   "moved": "| 南安 | 嘉靖 |"}}
    spec[18]["extraBlocks"] = [{"text": "<table><tr><td>南安</td><td>嘉靖3</td></tr></table>",
                                "boundingBox": [0.1, 0.9, 0.5, 0.03], "blockLabel": "table"}]
    tail = b_form(paragraphs(spec[18])[-1][-4:])
    spec[18].setdefault("bEdits", []).append((tail, tail + "\n南安 嘉靖3"))
    # N5: a table of scan 9 whose cells the page holds without the marks both
    # engines read (engine A the HTML table, engine B its rows as lines); in
    # its last row the engines differ on a mark, and read the title's opening
    # bracket alike but not its closing one.  The same comma in running text.
    spec[9]["extraSealed"] = ["| 府 | 事由 | 出處 |\n| --- | --- | --- |\n| 贛州 | 城砌以石高尺 | 康熙上猶縣志 |\n"
                              "| 汀州 | 平亂建鎮 | 明史 |"]
    spec[9]["extraBlocks"] = [{"text": "<table><tr><td>府</td><td>事由</td><td>出處</td></tr><tr><td>贛州</td>"
                                       "<td>城砌以石，高18尺。</td><td>康熙《上猶縣志》3/2a-b。</td></tr><tr><td>汀州</td>"
                                       "<td>平亂，建鎮</td><td>《明史》</td></tr></table>",
                               "boundingBox": [0.1, 0.9, 0.5, 0.05], "blockLabel": "table"}]
    tail = b_form(paragraphs(spec[9])[-1][-4:])
    spec[9].setdefault("bEdits", []).append(
        (tail, tail + "\n府 事由 出處\n贛州 城砌以石，高18尺。 康熙《上猶縣志》3/2a-b。\n汀州 平亂；建鎮 《明史"))
    insert(spec, 9, 0, "，", "，", None)
    # N5 on rows moved: the last two rows of scan 14's table are scan 15's,
    # whose text before the move holds them as a table of its own, the rule
    # under its first row.
    spec[14]["extraSealed"] = ["| 府 | 事由 |\n| --- | --- |\n| 贛州 | 城周三里 |\n| 南安 | 城圮官修議出公帑 |\n| 汀州 | 動支河稅 |"]
    part = "| 南安 | 城圮官修議出公帑 |\n| --- | --- |\n| 汀州 | 動支河稅 |"
    spec[15]["tableStitch"] = {"before": fx.sealed_text(spec[15]) + "\n" + part + "\n",
                               "continuation": {"head": {"page": 14, "table": 0}, "moved": part}}
    spec[15]["extraBlocks"] = [{"text": "<table><tr><td>南安</td><td>城圮，官修。議出公帑。</td></tr><tr><td>《汀州》</td>"
                                        "<td>動支河稅。</td></tr></table>",
                                "boundingBox": [0.1, 0.9, 0.5, 0.05], "blockLabel": "table"}]
    tail = b_form(paragraphs(spec[15])[-1][-4:])
    spec[15].setdefault("bEdits", []).append((tail, tail + "\n南安 城圮，官修。議出公帑。\n《汀州》 動支河稅。"))
    # R1: a kept retry wrote 。 where the first answer and engine A have ，
    # (scan 14, the first paragraph's first column); a first answer that
    # differs from engine A (、 for ，) in the second paragraph.
    first = paragraphs(spec[14])[0]
    block = first[:45]
    assert len(pp.CJK(block)) == 40 and block[15] == "，"
    spec[14].setdefault("sealedEdits", []).append((first[8:16], first[8:15] + "。"))
    second = paragraphs(spec[14])[1]
    block2 = second[:45]
    spec[14]["punctuationPasses"] = [
        {"block": 3, "range": [0, 40], "ok": True, "label": "vertical_text", "census": 15, "places": 5,
         "marks": 5, "firstAnswerMarks": 5, "reason": "5 places marked but 15 counted on the page (after retry)",
         "firstAnswer": block},
        {"block": 5, "range": [0, 40], "ok": True, "label": "vertical_text", "census": 15, "places": 5,
         "marks": 5, "firstAnswerMarks": 5, "reason": "5 places marked but 15 counted on the page (after retry)",
         "firstAnswer": block2.replace("，", "、", 1)},
    ]
    return spec


def n4_spec() -> dict[int, dict[str, Any]]:
    """Scan 15 with contents-like lines after its text: the engines put the
    second's number at the end of the first; the third opens with a bracket
    both engines read; the fourth has its number on a line of its own."""
    spec = fx.make_spec()
    spec[15]["extraSealed"] = ["卷首語……", "跋語……", "- （甲）後記……", "- 附錄"]
    spec[15]["extraBlocks"] = [{"text": "卷首語……7", "boundingBox": [0.1, 0.88, 0.3, 0.02], "blockLabel": "text"},
                               {"text": "跋語……", "boundingBox": [0.1, 0.91, 0.3, 0.02], "blockLabel": "text"},
                               {"text": "（甲）後記……", "boundingBox": [0.1, 0.93, 0.3, 0.02], "blockLabel": "text"},
                               {"text": "9", "boundingBox": [0.1, 0.95, 0.02, 0.02], "blockLabel": "text"},
                               {"text": "附錄", "boundingBox": [0.1, 0.97, 0.3, 0.02], "blockLabel": "text"}]
    last = paragraphs(spec[15])[-1]
    tail = b_form(last[-4:])
    spec[15].setdefault("bEdits", []).append((tail, tail + "\n卷首語……7\n跋語……\n(甲)後記……\n9\n附錄"))
    return spec


def gap_of(page: str, a: str, b: str | None = None, edge: str = "") -> rn.Gap:
    """A made-up gap: the page's text, engine A's and engine B's (engine A's
    when None)."""
    b = a if b is None else b
    return rn.Gap(1, 0, len(page), rn.tokens(page, "page"), rn.tokens(a, "a"), rn.tokens(b, "b"), a, b, 0, edge=edge)


def run_page(text: str, a: str, b: str | None = None, record: dict[str, Any] | None = None,
             mask: rn.Mask | None = None, labels: list[str] | None = None) -> tuple[str, list[dict[str, Any]], list[Any]]:
    """One made-up page through the stage's page step (N1, N5, N3, N2): the
    page's TEXT, engine A's body A - one layout block per line, labelled
    `table` where the line holds a table's markup (a tag, a pipe) and
    `text` otherwise, or by LABELS, one per line - and engine B's (A's when
    None), the seal's RECORD (one that recorded doubts, none, unless given);
    returns the text it leaves, the records and the doubts."""
    b = a if b is None else b
    lines = a.split("\n")
    labels = labels or ["table" if re.search(r"<t[adr]|\|", line) else "text" for line in lines]
    blocks = [{"text": line, "label": label, "index": k} for k, (line, label) in enumerate(zip(lines, labels))]
    pd = rr.PageData(scan=1, text=text, entry={}, record={"doubts": [], **(record or {})}, a_body=a, a_blocks=blocks,
                     b_text=b, b_body=b, band_text="", band_numbers=[])
    setting = rn.Setting(None, {}, None, [1], {1: text}, mask or rn.Mask({}, {}))
    plan = rr.Plan()
    ledger = re_.Ledger({1: text})
    records = ledger.apply("runs", rn._page_runs(setting, rn.PageRuns(pd, set()), plan))
    return ledger.texts[1], records, plan.doubts


TABLE = ("表一\n\n| 年代 | 規模 | 出處 |\n| --- | --- | --- |\n| 正德年間 | 城砌以石高尺馬道實以土 | 康熙上猶縣志 |\n"
         "| 嘉靖五年 | 周圍三里門三 |  | 明世宗實錄 |\n")
TABLE_A = ("表一\n<table><tr><td>年代</td><td>規模</td><td>出處</td></tr><tr><td>正德年間</td>"
           "<td>城砌以石，高18尺，馬道實以土。</td><td>康熙《上猶縣志》3/2a-b。</td></tr><tr><td>嘉靖五年</td>"
           "<td>周圍三里，門三。</td><td>—</td><td>《明世宗實錄》</td></tr></table>")
TABLE_DONE = ("表一\n\n| 年代 | 規模 | 出處 |\n| --- | --- | --- |\n"
              "| 正德年間 | 城砌以石，高18尺，馬道實以土。 | 康熙《上猶縣志》3/2a-b。 |\n"
              "| 嘉靖五年 | 周圍三里，門三。 |  — | 《明世宗實錄》 |\n")


def cell_checks() -> None:
    """N5 on made-up pages: what it must write, and each look-alike it must
    leave."""
    text, records, doubts = run_page(TABLE, TABLE_A)
    rules = [(r["rule"], r["after"]) for r in records]
    check(text == TABLE_DONE, f"N5: the marks both engines read in a table's cells are written, the cell boundaries kept ({text!r})")
    check([r["evidence"]["tier"] for r in records if r["rule"] == "N5"] == ["cell marks"] * 7
          and ("N1", "18") in rules and ("N1", "》3/2a-b。 |\n| ") in rules and not doubts,
          f"N5: a gap of marks alone is N5's, a gap whose marks N1 writes with its run stays N1's, no doubt ({rules})")
    check(not any(r["evidence"].get("withheld") for r in records),
          "N5: the two title marks written in two gaps of one row pair up (none withheld, N1's closing one too)")
    check(run_page(text, TABLE_A)[1] == [], "N5: run again on its own output, nothing changes")
    check(pp.CJK(text) == pp.CJK(TABLE), "N5: no CJK character changes")
    # The look-alikes in running text and on a line that is no table.
    check(run_page("城砌以石高尺\n", "城砌以石，高尺。")[0] == "城砌以石高尺\n",
          "N5: in running text an empty gap where both engines read a mark stays (the punctuator's reading)")
    check(run_page("甲乙丙丁 | 戊己庚辛\n", "甲乙，丙丁。 | 《戊己》庚辛")[0] == "甲乙丙丁 | 戊己庚辛\n",
          "N5: a line that merely holds a pipe is no table")
    row = "| 甲 | 乙 |\n| --- | --- |\n| 城砌以石高尺 | 馬道實以土 |\n"

    def engines(cell: str, other: str = "馬道實以土") -> str:
        return f"<table><tr><td>甲</td><td>乙</td></tr><tr><td>{cell}</td><td>{other}</td></tr></table>"

    # The block's label decides, not the page's shape: the structure pass
    # builds a page table from a punctuated text block too, and its empty
    # gaps are the punctuator's.
    passes = {"punctuationPasses": [{"block": 0, "label": "text", "ok": True, "range": [0, 12], "marks": 1}]}
    text, records, doubts = run_page(row, engines("城砌以石，高尺"), record=passes, labels=["text"])
    check(text == row and not records and not doubts,
          "N5: a page table whose characters lie in an engine A text block (one the punctuator read) gets no edit")
    check(run_page(row, engines("城砌以石，高尺"), record=passes)[0] == row.replace("以石高", "以石，高"),
          "N5: the same page and engines, the block labelled a table: the comma is written")
    # The seal's record: a model read the table's marks from the image.
    text, records, _ = run_page(TABLE, TABLE_A, record={"doubts": [{"kind": "punctuation-whole-page", "detail": "x"}]})
    check(not [r for r in records if r["rule"] == "N5"] and "城砌以石高18尺馬道實以土 |" in text,
          "N5: a page punctuated whole keeps its cells' empty gaps (the runs are still N1's)")
    text, records, _ = run_page(TABLE, TABLE_A, record={"tablesRebuilt": [{"block": 1, "outcome": "accepted"}]})
    check(not [r for r in records if r["rule"] == "N5"] and "城砌以石高18尺馬道實以土 |" in text,
          "N5: a table rebuilt from its crop (the seal names its block) keeps its cells' empty gaps")
    two = "| 甲 | 乙 |\n| --- | --- |\n| 丙丁 | 戊己 |\n\n| 庚 | 辛 |\n| --- | --- |\n| 壬癸 | 子丑 |\n"
    two_a = ("<table><tr><td>甲</td><td>乙</td></tr><tr><td>丙，丁</td><td>戊己</td></tr></table>\n"
             "<table><tr><td>庚</td><td>辛</td></tr><tr><td>壬，癸</td><td>子丑</td></tr></table>")
    text, records, _ = run_page(two, two_a, record={"tablesRebuilt": [{"block": 0, "outcome": "accepted"}]})
    check(text == two.replace("壬癸", "壬，癸") and len(records) == 1,
          f"N5: a rebuilt table is set aside per table; the page's other table gets its marks ({text!r})")
    check(rn.unread_marks({"doubts": []}) and rn.unread_marks({"tablesRebuilt": [{"outcome": "refused"}], "doubts": [{"kind": "table-rebuild"}]})
          and not rn.unread_marks({}) and not rn.unread_marks({"tablesRebuilt": []})
          and rn.unread_marks({"punctuationPasses": [{"block": 0, "ok": True}]}),
          "unread_marks: a seal with no doubts key is an older one, taken as read unless it records block passes")
    refused = {"tablesRebuilt": [{"block": 0, "from": "nominated", "outcome": "refused"}], **passes}
    check([r["rule"] for r in run_page(TABLE, TABLE_A, record={"tablesRebuilt": [{"block": 1, "outcome": "refused"}]})[1]].count("N5") == 7
          and run_page(row, engines("城砌以石，高尺"), record=refused, labels=["text"])[0] == row,
          "N5: a refused rebuild does not switch the rule off for a table block; a nominated text block kept its pass")
    # Engines that differ, a star, a note marker, a mark of the page, an answer.
    text, records, doubts = run_page(row, engines("城砌以石，高尺"), engines("城砌以石；高尺"))
    check(text == row and not doubts, "N5: a gap where the engines read different marks is left, with no doubt")
    text, records, doubts = run_page(row, engines("城砌以石*高尺"))
    check(text == row and not doubts, "N5: a star both engines read (a table's note sign) is not written")
    for cell in ("城砌以石~高尺", "城砌以石[高]尺", "城砌以石<高尺", "城砌以石\\高尺", "城砌以石 高尺", "城砌以石​高尺"):
        text, records, doubts = run_page(row, engines(cell))
        check(text == row and not doubts, f"N5: a character a renderer reads as markup, or one that prints nothing, is not written ({cell!r})")
    text, records, doubts = run_page(row, engines("城砌以石①，高尺"))
    check(text == row, "N5: a gap that holds a note marker is not written")
    marked = row.replace("以石高", "以石、高")
    check(run_page(marked, engines("城砌以石，高尺"))[0] == marked, "N5: a gap where the page holds a mark of its own is left")
    at = row.index("高尺")
    mask = rn.Mask({1: [False] * len(row)}, {1: [at]})
    check(run_page(row, engines("城砌以石，高尺"), mask=mask)[0] == row, "N5: a gap where a model answer took text away is left")
    text, records, doubts = run_page(row, engines("城砌以石，高尺", "《馬道實以土"))
    check(text == row.replace("以石高", "以石，高") and len(records) == 1
          and [(d[0], d[3].get("marks"), d[3].get("withheld")) for d in doubts] == [("run-no-place", 1, 1)],
          f"N5: a bracket with no partner on its row is withheld, the other marks written, the page's one doubt counts it ({text!r})")
    # Cell boundaries that are not the engines' one to one.
    text, records, doubts = run_page(row, "<table><tr><td>甲</td><td>乙</td></tr><tr><td>城砌以石，高尺。</td><td>—</td>"
                                          "<td>《馬道實以土》</td></tr></table>")
    check(text == row.replace("以石高", "以石，高")
          and [(d[0], d[3].get("marks"), d[3].get("gaps"), d[3].get("withheld")) for d in doubts] == [("run-no-place", 4, 1, 1)],
          f"N5: where the page's cell boundaries are not the engines' one to one, the gap across them is left, its three marks "
          f"counted with the closing bracket withheld after it ({text!r})")
    # An HTML table, a cell's line break.
    html = "<table>\n<tr>\n<td>治世餘聞<br>繼事紀聞</td>\n<td>城漸圮巡撫酌議</td>\n</tr>\n</table>\n"
    text, records, _ = run_page(html, "<table><tr><td>《治世餘聞》\\n《繼事紀聞》</td><td>城漸圮，巡撫酌議。</td></tr></table>",
                                "<table><tr><td>《治世餘聞》<br>《繼事紀聞》</td><td>城漸圮，巡撫酌議。</td></tr></table>")
    check(text == "<table>\n<tr>\n<td>《治世餘聞》<br>《繼事紀聞》</td>\n<td>城漸圮，巡撫酌議。</td>\n</tr>\n</table>\n",
          f"N5: an HTML table's cells get their marks, each side of a cell's line break ({text!r})")
    text, records, _ = run_page(html, "<table><tr><td>《治世餘聞\\n繼事紀聞》</td><td>城漸圮巡撫酌議</td></tr></table>")
    check("<td>《治世餘聞<br>繼事紀聞》</td>" in text, f"N5: a pair written about a cell's line break stands ({text!r})")
    text, records, doubts = run_page(html, "<table><tr><td>《治世餘聞》《繼事紀聞》</td><td>城漸圮巡撫酌議</td></tr></table>")
    check(text == html and [(d[0], d[3].get("marks")) for d in doubts] == [("run-no-place", 4)],
          f"N5: marks whose side of the page's line break engine A does not give are not written, nor the brackets "
          f"about them (two titles would read as one); the four are the page's one doubt ({text!r})")
    # The bracket guard: two titles of one cell with a gap between them the
    # engines differ in; a cell boundary between an opening and a closing one.
    text, records, doubts = run_page("| 甲 | 乙 |\n| --- | --- |\n| 治世餘聞繼事紀聞 | 庚辛 |\n",
                                     engines("《治世餘聞》《繼事紀聞》", "庚辛"), engines("《治世餘聞》、《繼事紀聞》", "庚辛"))
    check("| 治世餘聞繼事紀聞 |" in text and not records and [(d[0], d[3].get("withheld")) for d in doubts] == [("run-no-place", 2)],
          f"N5: the outer brackets of two titles are no pair where the gap between them is not written ({text!r})")
    text, records, doubts = run_page("| 甲 | 乙 |\n| --- | --- |\n| 見明史卷三 | 及實錄載 |\n", engines("見《明史卷三", "及實錄》載"))
    check("| 見明史卷三 | 及實錄載 |" in text and not records and [d[3].get("withheld") for d in doubts] == [2],
          f"N5: an opening bracket in one cell and a closing one in the next are no pair ({text!r})")
    html2 = "<table><tr><td>甲乙</td><td>丙丁</td></tr></table>\n"
    check(run_page(html2, html2.replace("甲乙", "甲《乙").replace("丙丁", "丙》丁").strip())[0] == html2,
          "N5: an HTML cell boundary on one line parts two brackets too")
    # The page's space where engine A breaks the line in the cell.
    text, records, _ = run_page("| 甲 | 乙 |\n| --- | --- |\n| 治世餘聞 繼事紀聞 | 庚辛 |\n",
                                engines("《治世餘聞》\\n《繼事紀聞》", "庚辛"), engines("《治世餘聞》<br>《繼事紀聞》", "庚辛"))
    check("| 《治世餘聞》 《繼事紀聞》 |" in text,
          f"N5: where the page's cell holds a space and engine A breaks the line, each line's marks go on its side ({text!r})")
    text, records, doubts = run_page("| 甲 | 乙 |\n| --- | --- |\n| 治世餘聞 繼事紀聞 | 庚辛 |\n",
                                     engines("《治世餘聞》\\n——\\n《繼事紀聞》", "庚辛"), engines("《治世餘聞》<br>——<br>《繼事紀聞》", "庚辛"))
    check("| 治世餘聞 繼事紀聞 |" in text and [d[3].get("marks") for d in doubts] == [5],
          f"N5: a line of marks between them has no side of the page's space: the stretch is left, its marks counted ({text!r})")
    # N5 names the edit for the marks N1 leaves; with every one withheld it is N1's.
    text, records, _ = run_page("<table>\n<tr>\n<td>丙丁<br>戊己</td>\n</tr>\n</table>\n", "<table><tr><td>丙丁》\\nAD戊己</td></tr></table>",
                                "<table><tr><td>丙丁》<br>AD戊己</td></tr></table>")
    check("<td>丙丁<br>AD戊己</td>" in text and [(r["rule"], r["evidence"]["tier"], r["evidence"].get("withheld")) for r in records]
          == [("N1", "T2", ["》"])],
          f"N5: an edit whose cell marks were all withheld is N1's, its run written ({text!r})")
    # The table's edge: what stands before the table is running text.
    text, records, _ = run_page("表一城池\n\n| 甲乙 | 丙丁 |\n| --- | --- |\n| 戊己 | 庚辛 |\n",
                                "表一城池。\n<table><tr><td>《甲乙》</td><td>丙丁</td></tr><tr><td>戊己</td><td>庚辛</td></tr></table>")
    check(text.startswith("表一城池\n\n| 《甲乙》 | 丙丁 |"),
          f"N5: in the gap that enters a table, the cell's mark is written and the line before keeps its end ({text!r})")
    # stretches() on a made-up gap: the offsets of N5's marks, the brackets listed.
    gap = gap_of(" | ", "。</td><td>《")
    gap.tables, gap.bare = [(-1, 99)], (True, True)
    check(rn.weave(gap)[0] == "。 | 《" and gap.cells == [0, 4] and gap.wrote == [4],
          "N5: a stretch of marks alone in a table is written, its marks listed, its bracket listed for the pairing guard")
    gap = gap_of(" | ", "。</td><td>《")
    gap.tables = [(-1, 99)]
    check(rn.weave(gap)[0] == " | " and gap.cells == [] and not gap.cell_lost,
          "N5: a stretch beside no character of a block the punctuator never read is N1's alone, which leaves marks with no run")
    check(rn.table_spans("甲 | 乙\n\n| 甲 | 乙 |\n| --- | --- |\n| 丙 | 丁 |\n") == [(7, 40)],
          "table_spans: a Markdown table is its label row, rule and rows; a line with a pipe is none")


def unit_checks() -> None:
    """The stage's functions on made-up gaps: what each must write, and the
    look-alike it must leave."""
    gap = gap_of("-。", "119-140。")
    check(rn.weave(gap)[0] == "119-140。" and gap.dropped == 1,
          "N1: the hyphen a dropped run left on the page goes with the run written")
    gap = gap_of("》：（），", "》5:3（1994），")
    check(rn.weave(gap)[0] == "》5：3（1994），", "N1: a run takes the page's own form of the connector it left behind")
    check(rn.permuted(gap_of("</u>）（", "（1987）")) is None, "N3: a gap that holds the page's markup is left")
    gap = gap_of("，）。", "，1999）", "，1999)。")
    check(rn.weave(gap)[0] is None, "N1: a full stop of the page that engine A lacks and no run carries is not dropped")
    check(rn.weave(gap_of("「", "（1582）「"))[0] == "（1582）「",
          "N1: the page's mark is matched to the engines' mark of its own class (the year stays outside the quotation)")
    check(rn.weave(gap_of("（？）", "（？-1604）"))[0] == "（？-1604）",
          "N1 T2: the hyphen both engines read beside the year is written with it")
    check(rn.weave(gap_of("，", "，，1989"))[0] is None,
          "N1 T2: a run whose place among the page's marks differs by the matching is not written")
    check(rn.weave(gap_of("\n\n", "1989"))[0] is None,
          "N1: a run with no mark beside it is not put on a side of the page's line break engine A does not give")
    check(rn.weave(gap_of("。\n\n", "。\nIbid.\n"))[0] is None,
          "N1: a run on a line of its own in engine A is not joined to the next line")
    check(rn.permuted(gap_of("』，）（", "》45：4（1987），")) == "』45：4（1987），",
          "N3: the gap in the engines' order keeps the page's own bracket shape")
    for text, wanted in (("。\n18 Fernand Braudel", True), ("。\n〔1〕", True), ("，1989", False)):
        toks = rn.tokens(text, "a")
        check(rn.line_initial_figure(toks, rn.runs_of(toks)[0]) is wanted,
              f"a figure opening a line of engine A is a line's own number: {text!r} -> {wanted}")
    check(rn.note_like(rn.tokens("。12", "a")) and rn.note_like(rn.tokens("。」3", "a"))
          and not rn.note_like(rn.tokens("》12", "a")) and not rn.note_like(rn.tokens("pp. 12", "a")),
          "a short figure right after a sentence's end is taken for a note number, one after a title mark is not")
    check([t.kind for t in rn.tokens(" - ", "page")] == [rn.SPACE, rn.MARK, rn.SPACE]
          and rn.tokens("\n- ", "page")[1].kind == rn.STRUCT and rn.tokens("\n---\n", "page")[1].kind == rn.STRUCT,
          "tokens: a hyphen inside a line is a mark; a list marker and a rule at a line's start are structure")
    check(rn.tokens("。<sup>3</sup>", "a")[1].kind == rn.MARKER and rn.tokens("。❶", "a")[1].kind == rn.MARKER,
          "tokens: an HTML superscript and a dingbat figure are note markers")
    check(rn.agree(rn.tokens("Chu, T. Local Government. Harvard, 1962.", "a"),
                   rn.tokens("Chu, T. *Local Government*. Harvard, 1962.", "b"))
          and not rn.agree(rn.tokens("30</td><td>29", "a"), rn.tokens("3029", "b")),
          "two readings that cut the same characters into runs differently agree; two figures and one figure do not")
    import _repair_inputs as ri
    import _repair_joins as rj
    frame = ri.parse_assembly("<!-- page_001 -->\n\n甲\n\n<!-- page_002 -->\n<!-- page_003 -->\n\n乙\n")
    composed = frame.compose({2: "Tang Li-chung\n\n2002\n"})
    check(composed == "<!-- page_001 -->\n\n甲\n\n<!-- page_002 -->\n\nTang Li-chung\n\n2002\n\n<!-- page_003 -->\n\n乙\n"
          and frame.compose({}) == "<!-- page_001 -->\n\n甲\n\n<!-- page_002 -->\n<!-- page_003 -->\n\n乙\n"
          and not rj.contract_problems(composed, {1: "start", 2: "paragraph", 3: "paragraph"}),
          "compose: a text written into a page sealed empty gets a blank line each side; unchanged, the frame is byte for byte")
    hyphenated = rn.tokens("eds., Challenging Authority: The Historical Study of Conten-tious Politics (London, 1998), pp. 91-104.", "b")
    joined = rn.tokens("eds., Challenging Authority: The Historical Study of Contentious Politics (London, 1998), pp. 91-104.", "a")
    check(not rn.agree(joined, hyphenated) and rn.nearly(joined, hyphenated)
          and rn.nearly(rn.tokens("'Brigand Region' and 'District':", "a"), rn.tokens("\u2018Brigand Region\u2019 and \u2018District\u2019:", "b"))
          and not rn.nearly(joined, rn.tokens("eds., Challenging Authority: The Historical Study of Contentious Politic (London, 1998), pp. 91-104.", "b"))
          and not rn.nearly(joined, rn.tokens("eds., Challenging Authority: The Historical Study of Contentious Politics (London, 1998), pp. 91104.", "b"))
          and not rn.nearly(rn.tokens("1997", "a"), rn.tokens("", "b")),
          "nearly: a word hyphenated by one engine, curly and straight apostrophes; not a letter less, not a hyphen between figures, not a reading of nothing")
    text, brackets = rn.written(rn.tokens('Skinner, "Introduction," in Leong, Migration (Stanford: Press, 1997), pp. 1-18.', "a"))
    check(text == 'Skinner, "Introduction," in Leong, Migration (Stanford: Press, 1997), pp. 1-18.',
          f"written: Western text keeps its spaces and its ASCII marks ({text!r})")
    check(rn.written(rn.tokens("(1996),", "a"))[0] == "（1996），" and rn.written(rn.tokens("12 34", "a"))[0] == "12 34",
          "written: an ASCII mark beside figures takes its full-width form; two figures stay apart")
    ledger = re_.Ledger({1: "甲乙（丙）丁"})
    ledger.apply("questions", [re_.Edit(1, 2, 5, "", question="Q1", answer="x", crop="c.png", crop_sha256="0" * 64)])
    mask = rn.question_mask(ledger)
    check(rn.written_in(mask, 1, 2, 2) and not rn.written_in(mask, 1, 0, 1),
          "the answers' mask knows the place a model answer took text from")
    ledger = re_.Ledger({1: "甲\n乙（）丙"})
    ledger.apply("questions", [re_.Edit(1, 4, 4, "X", question="Q1", answer="x", crop="c.png", crop_sha256="0" * 64)])
    ledger.apply("runs", [re_.Edit(1, 0, 1, "甲甲甲", rule="N4")])
    check(rn.written_in(rn.question_mask(ledger), 1, 6, 7), "the answers' mask follows the text an earlier edit of the stage moved")
    text = "卷7天文志，頁8a。"
    edit = re_.Edit(1, 2, 2, "〈", rule="N1")
    wrote = {id(edit): [0]}
    rn.unpaired(text, [edit], wrote)
    check(edit.after == "" and edit.evidence.get("withheld") == ["〈"],
          "a bracket written from the engines that finds no partner on its line is withheld")


def page_text(out: Path, scan: int) -> str:
    return (out / "pages" / f"page-{scan:04d}.md").read_text(encoding="utf-8")


def main() -> int:
    unit_checks()
    cell_checks()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        spec = make_spec()
        book = fx.write_book(tmp / "book", spec)
        out = tmp / "out"
        status = run(str(book), "--output", str(out), "--no-model", *OTHER_STAGES_OFF)
        report = json.loads((out / "repair-report.json").read_text(encoding="utf-8"))
        check(status == 0 and report["checks"]["logReplay"]["passed"],
              f"the run exits 0 and its log replays to its output (exit {status})")
        check(report["stages"]["runs"]["status"] == "ran" and report["stages"]["runs"]["rules"] == ["N4", "R1", "N1", "N5", "N3", "N2"],
              "the runs stage ran and names its rules")
        records = re_.read_log((out / "repair-log.jsonl").read_text(encoding="utf-8").splitlines())
        by_rule = {}
        for r in records:
            by_rule.setdefault(r["rule"], []).append(r)
        doubts = json.loads((out / "doubts.json").read_text(encoding="utf-8"))
        kinds = {(d["kind"], d["page"]) for d in doubts}

        p6 = page_text(out, 6)
        texts6 = paragraphs(spec[6])
        check(texts6[0][1:3] + "1989" + texts6[0][3:5] in p6, "N1 T1: a year both engines read is written between its characters")
        check(texts6[1][1:3] + "（G. W. Skinner）" + texts6[1][3:5] in p6,
              "N1 T1: a bracketed Latin name goes into the page's empty bracket pair, spaces kept")
        check(texts6[2][1:3] + "（1522-66）" + texts6[2][3:5] in p6,
              "N1 T2: a figure goes in beside the one bracket the page has, with the bracket it lacks")
        check(texts6[0][9:11] + "，1996）" + texts6[0][11:13] in p6,
              "N1 T2: the comma both engines read before a year is written with it")
        n1 = [r for r in by_rule.get("N1", []) if r["page"] == 6]
        check(texts6[1][9:11] + "7" + texts6[1][11:13] in p6 and "〈" not in p6
              and any(r["evidence"].get("withheld") == ["〈"] for r in n1),
              "N1 T2: a bracket with no partner on its line is withheld, its figure written")
        check(len(n1) == 5 and sorted(r["evidence"]["tier"] for r in n1) == ["T1", "T1", "T2", "T2", "T2"],
              f"N1: five edits on scan 6, two T1 and three T2 ({[r['evidence']['tier'] for r in n1]})")
        check(all(pp.CJK(page_text(out, s)) == pp.CJK(book.joinpath('proofread', f'page-{s:04d}.md').read_text(encoding='utf-8'))
                  for s in (6, 8, 9, 10, 12, 14, 15, 17, 18)), "no CJK character changes on any page")

        p8 = page_text(out, 8)
        check("1989" not in p8 and "1980" not in p8, "left alone: a figure the engines read differently")
        check(("run-engines-differ", 8) in kinds, "`run-engines-differ` is recorded for it")
        check(("run-one-engine", 8) in kinds, "`run-one-engine` is recorded for the figure engine A alone read")
        check(("note-markers-unverified", 8) in kinds and "⑫" not in p8,
              "a figure beside a note marker is not written; the page's markers are one doubt")
        check("\n\nHobsbawm, E. J. Bandits. London: Weidenfeld, 1969.\n\n" in p8
              and any(r["page"] == 8 for r in by_rule.get("N2", [])),
              "N2: a whole line of Western text goes in as a paragraph, one engine's emphasis markers aside")
        p17 = page_text(out, 17)
        moved = [r for r in by_rule.get("N1", []) if r["page"] == 17]
        check("| 南安 | 嘉靖3 |" in p17 and len(moved) == 1 and moved[0]["evidence"].get("movedFrom") == 18
              and "嘉靖3" not in page_text(out, 18),
              f"N1: a figure of a row moved to the page before is written there ({p17.splitlines()[-1]!r})")
        p10 = page_text(out, 10)
        check(p10.count("1989") == 1 and not [r for r in by_rule.get("N1", []) if r["page"] == 10],
              "a figure the page already holds is left as it is")
        check("18" not in p10 and ("run-no-place", 10) in kinds,
              "a figure that opens a line in engine A is not written (`run-no-place`)")
        check("1980" in p10 and any(d["kind"] == "run-no-place" and d["page"] == 10 and d.get("pageRuns") == ["1980"]
                                   for d in doubts),
              "a figure the page holds in another form is left, with a `run-no-place` doubt naming both")

        p12 = page_text(out, 12)
        texts12 = paragraphs(spec[12])
        check(texts12[0][1:3] + "（1522-66）" + texts12[0][3:5] in p12 and any(r["page"] == 12 for r in by_rule.get("N3", [])),
              "N3: `）（` becomes the engines' `（1522-66）`")
        check("| 贛州 | 1496 | 弘治9 |" in p12, f"N1: a table row's empty cell and short cell get their figures ({p12.splitlines()[-1]!r})")

        p9 = page_text(out, 9)
        n5 = [r for r in by_rule.get("N5", []) if r["page"] == 9]
        check("| 贛州 | 城砌以石，高18尺。 | 康熙《上猶縣志》3/2a-b。 |" in p9 and sorted(r["after"] for r in n5) == sorted(["，", "。 | ", "《"]),
              f"N5: a table row's cells get the marks both engines read, the title marks as a pair ({p9.splitlines()[-2]!r})")
        check(not any(r["evidence"].get("withheld") for r in records if r["page"] == 9)
              and sum(1 for r in by_rule.get("N1", []) if r["page"] == 9) == 2,
              "N5: the closing title mark N1 writes with its figure finds the opening one N5 wrote")
        check("| 汀州 | 平亂建鎮 | 明史 |" in p9
              and [(d["kind"], d.get("marks"), d.get("withheld")) for d in doubts if d["page"] == 9] == [("run-no-place", 1, 1)],
              "N5: marks the engines read differently are not written, with no doubt; the bracket with no partner is "
              "withheld and is the page's one doubt")
        text9 = paragraphs(spec[9])[0]
        check(text9[1:5] in p9, "N5: the same comma both engines read in running text is not written")
        p14 = page_text(out, 14)
        moved = [r for r in by_rule.get("N5", []) if r["page"] == 14]
        check("| 南安 | 城圮，官修。議出公帑。 |\n| 《汀州》 | 動支河稅。 |" in p14
              and len(moved) == 6 and all(r["evidence"].get("movedFrom") == 15 for r in moved)
              and "城圮" not in page_text(out, 15),
              f"N5: the marks of rows moved to the page before are written there, either side of the rule the move dropped "
              f"({p14.splitlines()[-2:]!r})")
        first = paragraphs(spec[14])[0]
        check(first[8:16] in p14 and first[8:15] + "。" not in p14 and any(r["page"] == 14 and r["rule"] == "R1" for r in records),
              "R1: the kept retry's 。 becomes the first answer's ， where engine A has it")
        second = paragraphs(spec[14])[1]
        check(second[:45] in p14 and len([r for r in records if r["page"] == 14 and r["rule"] == "R1"]) == 1,
              "R1: a first answer that differs from engine A changes nothing")

        status = run(str(book), "--output", str(tmp / "off"), "--no-model", "--no-runs", *OTHER_STAGES_OFF)
        report = json.loads((tmp / "off" / "repair-report.json").read_text(encoding="utf-8"))
        check(status == 0 and report["stages"]["runs"]["status"] == "off (--no-runs)" and report["counts"]["edits"] == 0,
              "--no-runs switches the stage off")

        # The rows moved to scan 14, one of them changed there: the marks of
        # that row find no place, and are the page's one doubt.
        spec_moved = make_spec()
        spec_moved[14]["extraSealed"] = [spec_moved[14]["extraSealed"][0].replace("| 汀州 | 動支河稅 |", "| 汀州 | 動支河稅銀 |")]
        book_moved = fx.write_book(tmp / "book-moved", spec_moved)
        status = run(str(book_moved), "--output", str(tmp / "out-moved"), "--no-model", *OTHER_STAGES_OFF)
        doubts_moved = json.loads((tmp / "out-moved" / "doubts.json").read_text(encoding="utf-8"))
        p14 = page_text(tmp / "out-moved", 14)
        moved = [(d["kind"], d.get("movedTo"), d.get("marks"), d.get("gaps")) for d in doubts_moved if d["page"] == 15]
        check(status == 0 and "| 南安 | 城圮，官修。議出公帑 |\n| 汀州 | 動支河稅銀 |" in p14 and moved == [("run-no-place", 14, 4, 3)],
              f"N5: marks of a moved row that no longer stands on the host unchanged are not written (the full stop before "
              f"the row goes with the bracket after it: one edit, all or none), and are one doubt of the page they were "
              f"read on, with their count ({moved}, {p14.splitlines()[-2:]!r})")

        # N4 on its own: a ledger holding an S11 record the engines contradict.
        spec4 = n4_spec()
        book4 = fx.write_book(tmp / "book4", spec4)
        out4 = tmp / "out4"
        status = run(str(book4), "--output", str(out4), "--no-model", "--no-runs", *OTHER_STAGES_OFF)
        check(status == 0, f"the N4 book's plain run exits 0 (exit {status})")
        loaded = ri.load_book(ri.InputPaths.resolve(book4, {}))
        model = json.loads((out4 / "book-model.json").read_text(encoding="utf-8"))
        order = list(loaded.assembly.order)
        ledger = re_.Ledger({scan: loaded.pages[scan].sealed_text for scan in order})
        text15 = ledger.texts[15]
        at = text15.index("跋語……")
        ledger.apply("contents", [re_.Edit(15, at, at + len("跋語……"), "7 跋語……", rule="S11", evidence={
            "kind": "entry", "number": 7, "numbers": {"engineA": "7", "engineB": "7"}, "place": 2})])
        text15 = ledger.texts[15]
        at = text15.index("- （甲）後記……")
        ledger.apply("contents", [re_.Edit(15, at, at + len("- （甲）後記……"), "甲）後記……", rule="S11", evidence={
            "kind": "entry", "number": None, "numbers": {}, "place": 3})])
        text15 = ledger.texts[15]
        at = text15.index("- 附錄")
        ledger.apply("contents", [re_.Edit(15, at, at + len("- 附錄"), "9 附錄", rule="S11", evidence={
            "kind": "entry", "number": 9, "numbers": {"engineA": "9", "engineB": "9"}, "place": 4})])
        check(ledger.texts[15].count("7 跋語……") == 1 and "\n甲）後記……" in ledger.texts[15] and "9 附錄" in ledger.texts[15],
              "the S11 records stand on the page")
        facts = rr.book_facts(loaded, model)
        plan = rn.runs(loaded, model, ledger, order, lambda edits: ledger.apply("runs", edits), facts, None)
        ledger.apply("runs", plan.edits)
        rules = [r["rule"] for r in ledger.records if r["stage"] == "runs"]
        check("N4" in rules and "7 跋語……" not in ledger.texts[15] and "\n跋語……" in ledger.texts[15],
              f"N4: the number S11 put at the line's head goes, where both engines read it at the line before's end ({rules})")
        check("卷首語……7" in ledger.texts[15], "N1 then writes the number after its own leaders")
        check("\n（甲）後記……" in ledger.texts[15],
              "N4: the bracket S11 dropped with the line's list marker is put back, where both engines read it")
        check("9 附錄" in ledger.texts[15],
              "N4: a number the engines read on a line of its own before the entry stays at the entry's head")
        plan = rn.runs(loaded, model, ledger, order, lambda edits: ledger.apply("runs", edits), facts, None)
        check(not plan.edits and not [r for r in ledger.records[len(ledger.records):]],
              "the stage run again on its own output changes nothing")
    print("\nFAILURES:" if FAILURES else "\nall checks passed")
    for failure in FAILURES:
        print(" -", failure)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
