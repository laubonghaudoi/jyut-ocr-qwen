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
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        spec = make_spec()
        book = fx.write_book(tmp / "book", spec)
        out = tmp / "out"
        status = run(str(book), "--output", str(out), "--no-model", *OTHER_STAGES_OFF)
        report = json.loads((out / "repair-report.json").read_text(encoding="utf-8"))
        check(status == 0 and report["checks"]["logReplay"]["passed"],
              f"the run exits 0 and its log replays to its output (exit {status})")
        check(report["stages"]["runs"]["status"] == "ran" and report["stages"]["runs"]["rules"] == ["N4", "R1", "N1", "N3", "N2"],
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
                  for s in (6, 8, 10, 12, 14, 17, 18)), "no CJK character changes on any page")

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

        p14 = page_text(out, 14)
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
