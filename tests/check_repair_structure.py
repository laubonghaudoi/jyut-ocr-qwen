#!/usr/bin/env python3
"""Offline check of the book repair tool's structure rules
(scripts/_repair_structure.py) through scripts/repair_book.py: heading
content (H-JOIN, S6, S7x, S8, S10, S15), the contents and their units (S9,
S4, S16, S7, S11), the title page (S13) and the heading levels (S5, S12).

No model, no GPU, no corpus: made-up books (tests/repair_fixture.py), each
page changed only where a rule's case is set up.  Every rule has a case it
must repair and a look-alike it must leave:

Contents (the made-up contents: two groups, each a run suffix and its
subtitle, entries `n title`):
- S11 rebuilds the contents: an entry whose bullet stands where its number
  was gets the number engines A and B read; a number printed after the title
  goes before it; a mark before the title engine A did not read goes; the
  mark after a number the page holds stays where engine A read the figure
  without it; the mark engine A read after its figure, which the page holds
  where the figure was lost, is written once; the group line becomes a
  heading, the suffix apart from the rest; an entry whose number no source
  read is a question, and an entry with no unit in the body a
  `unit-not-in-scan` doubt.
- S4 writes engine A's number over a glyph it did not read before a unit's
  title; a unit whose number engine A did not read is a question, and so is
  one whose heading holds, before the number, characters engine A read.
- S9 makes a unit title that stands as text a heading - split from the
  paragraph run onto its line at engine A's next block, and split from the
  paragraph it was glued to at the start of its engine A block.
- S16 takes the contents' character where the engines disagree on a unit
  title; where both engines read the other character it stays.
- S7 moves the date after a unit title to its own paragraph, whole where the
  body's title is two characters short of the contents' (the title's match
  ends at its last character, not in the date).
- The date parser takes the one start a run of numerals allows (之四四月),
  the run's own start where that parses, and none where two parse; an
  enumerator and a word that opens with a numeral (一，五湖…) is no date.

Headings:
- H-JOIN joins a heading printed over two lines that engine A read as one
  block; a heading whose next line is the paragraph it leads (longer than a
  column) stays apart.
- S6 writes engine A's dash between a title and its subtitle where the page
  holds none; a heading where engine A read no dash is left; where engine A
  read a stand-in glyph beside its dash (the page's stand-ins may be the
  dash) it is a question.
- S7x deletes a date's copy inside a heading that engine A read once, beside
  its date line; a date printed twice stays.
- S8 moves a date line engine A reads after its heading below it; one printed
  above its heading stays.
- S10 makes plain text of a page-top heading that finishes the previous
  page's sentence (a flush first column after a full last one), and the
  boundary before it is J3's join; a heading after a finished page stays.
- S15 keeps one copy of a run written twice that engine B read once; a run
  printed twice stays.

Levels and the title page:
- S13 rebuilds a page printed right to left: engine A read its lines
  backwards, engine B read its title forwards, the page held one line
  backwards and lost the title; one question per line.  It asks instead
  where engine A read a column on the page, where engine B read one of
  engine A's lines the same way round, and where the page holds anything -
  a character or a figure - no line of engine A's holds.
- S5 sets one level per contents depth: the book title `#`, the contents
  title and the dividers `##`, the groups and the units `###`, a heading of
  its own inside a unit `####`; S12 makes an occasion line under a unit
  heading plain text and its date a paragraph; a date written as a heading
  is plain text; a heading engine A read at the start of a longer block is a
  question, an enumerator and a word that opens with a numeral too; a
  heading no rule places keeps its level, a `heading-kind-unknown` doubt.

Gates: contents whose numbers are not their places fail the
`contents-numbering` gate (a `gate-failed` doubt) and no number is taken
from a place; a book with no contents (M-6) gets no contents or level edit.

Every run replays its log to its output, and the stages run again on their
own output change nothing.

Usage:
    python3 tests/check_repair_structure.py
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
import _repair_structure as rs  # noqa: E402
import repair_book  # noqa: E402


FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    print(f"{'ok  ' if condition else 'FAIL'} {message}")
    if not condition:
        FAILURES.append(message)


class Result:
    def __init__(self, status: int, out: Path, book: Path):
        self.status = status
        self.out = out
        self.book = book
        self.report = json.loads((out / "repair-report.json").read_text(encoding="utf-8"))
        self.log = [json.loads(line) for line in (out / "repair-log.jsonl").read_text(encoding="utf-8").splitlines()]
        self.questions = json.loads((out / "questions.json").read_text(encoding="utf-8"))
        self.doubts = json.loads((out / "doubts.json").read_text(encoding="utf-8"))
        self.pages = {int(p.stem.split("-")[1]): p.read_text(encoding="utf-8") for p in (out / "pages").glob("*.md")}
        self.sealed = {int(p.stem.split("-")[1]): p.read_text(encoding="utf-8")
                       for p in (book / "proofread").glob("page-*.md")}

    def rules(self, page: int) -> list[str]:
        return [r["rule"] for r in self.log if r["page"] == page]

    def asked(self, page: int) -> list[str]:
        return [q["rule"] for q in self.questions if q["page"] == page]

    def doubted(self, kind: str) -> list[int | None]:
        return [d["page"] for d in self.doubts if d["kind"] == kind]


def repair(root: Path, spec: dict[int, dict[str, Any]], name: str, *argv: str) -> Result:
    book = fx.write_book(root / name, spec)
    out = root / f"{name}-out"
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        status = repair_book.main(["--workers", "1", str(book), "--output", str(out), "--no-model", *argv])
    return Result(status, out, book)


def heading_of(spec: dict[int, dict[str, Any]], scan: int) -> str:
    return next(item[1] for item in spec[scan]["items"] if item[0] == "heading")


def set_heading(spec: dict[int, dict[str, Any]], scan: int, text: str) -> None:
    """The unit heading of SCAN printed (and read, and sealed) as TEXT."""
    items = spec[scan]["items"]
    k = next(i for i, item in enumerate(items) if item[0] == "heading")
    items[k] = ("heading", text, items[k][2])


def seal(spec: dict[int, dict[str, Any]], scan: int, old: str, new: str) -> None:
    spec[scan].setdefault("sealedEdits", []).append((old, new))


def paragraphs(spec: dict[int, dict[str, Any]], scan: int) -> list[str]:
    return [item[1] for item in spec[scan]["items"] if item[0] == "para"]


def retitle(spec: dict[int, dict[str, Any]], contents: int, unit: int, old: str, new: str) -> None:
    """A unit's title OLD printed as NEW, in the contents (scan CONTENTS)
    and over the unit (scan UNIT)."""
    for scan in (contents, unit):
        items = spec[scan]["items"]
        for i, item in enumerate(items):
            if item[0] in ("line", "heading") and item[1].endswith(" " + old):
                items[i] = (item[0], item[1][:-len(old)] + new, *item[2:])


def run_on(seed: int, size: int) -> str:
    """SIZE made-up characters with a comma every seven and no full stop:
    prose that goes on past the page."""
    chars = fx.filler(seed, size)
    return "".join(c + ("，" if i % 7 == 0 and i < size else "") for i, c in enumerate(chars, 1))


def again(root: Path, name: str, result: Result) -> list[re_.Edit]:
    """The structure stages run on RESULT's own pages (with the model of the
    book): what they would change."""
    book = ri.load_book(ri.InputPaths.resolve(root / name, {}))
    model = json.loads((result.out / "book-model.json").read_text(encoding="utf-8"))
    order = list(book.assembly.order)
    ledger = re_.Ledger({scan: result.pages[scan] for scan in order})
    facts = rr.book_facts(book, model)
    proposed: list[re_.Edit] = []

    def apply(edits):
        proposed.extend(edits)
        ledger.apply("again", edits)
    for step in (lambda: rs.headings(book, model, ledger.texts, order, apply, facts),
                 lambda: rs.contents_stage(book, model, ledger.texts, order, apply, facts),
                 lambda: rs.title_pages(book, model, ledger.texts, order, facts),
                 lambda: rs.levels(book, model, ledger.texts, order, facts)):
        apply(step().edits)
    return proposed


# --- the date parser --------------------------------------------------------------

def date_checks() -> None:
    text = "訓話之四四月二十三日"
    found = rs.find_date(text)
    check(found is not None and text[found[0]:found[1]] == "四月二十三日",
          f"a subtitle's ordinal glued to a date: the one start the run allows ({found})")
    text = "紀念演說十八，六，十七，"
    found = rs.find_date(text)
    check(found is not None and text[found[0]:found[1]].startswith("十八，六，十七"),
          f"a date that starts where its run of numerals starts is taken whole ({found})")
    check(rs.find_date("訓詞之一十九五，十二") is None,
          "two starts inside a run of numerals that both parse: no date is taken")
    check(rs.find_date("訓話之十二十月十五日") is not None
          and "訓話之十二十月十五日"[rs.find_date("訓話之十二十月十五日")[0]:].startswith("十月"),
          "a month over twelve is no date: 之十二 then 十月十五日")
    check(rs.find_date("一年來之近況") is not None and rs.find_date("三月之間") is None,
          "a year alone is a date; a month alone is not (too many words hold one)")
    check(rs.is_date_line("三年五月七日") and not rs.is_date_line("三年來的工作與今後的計劃之大要與其方法及步驟"),
          "a date line is a date and at most a short clause after it")
    check(rs.find_date("一，五湖四海之遊") is None and not rs.is_date_line("一，五湖四海之遊")
          and not rs.is_date_line("二、三民之說"),
          "an enumerator and a word that opens with a numeral is no date (一，五湖…)")
    check(all(rs.is_date_line(line) for line in ("廿，八月", "三，九，在山中作", "九，十二。")),
          "numeral groups that end at 月, a separator or a mark are a date")


# --- contents ------------------------------------------------------------------------

# A unit title long enough to match with two of its characters lost.
LONG_TITLE = "山居雜詠松風竹影梅花明月溪橋煙雨漁舟唱晚歸來"


def contents_spec() -> dict[int, dict[str, Any]]:
    spec = fx.make_spec()
    # S11 on the first contents page: a bullet where the number was (both
    # engines read it), a number printed after its title, a mark before the
    # title engine A did not read, the group line as plain text.
    seal(spec, 2, "1 春日遊記", "- 春日遊記")
    seal(spec, 2, "2 秋夜讀書", "秋夜讀書 2")
    seal(spec, 2, "3 山居雜詠", "。山居雜詠")
    seal(spec, 2, "### 甲編 詩文", "甲編詩文")
    # An entry whose number no source read; an entry with no unit.
    spec[2]["aEdits"] = [("4 江上聽雨", "江上聽雨")]
    spec[2]["bEdits"] = [("4 江上聽雨", "江上聽雨")]
    seal(spec, 2, "4 江上聽雨", "江上聽雨")
    spec[3]["items"].append(("line", "4 竹林清話"))
    # S4: a glyph engine A did not read where it read the unit's number;
    # a unit whose number engine A did not read (a question).
    seal(spec, 7, "### 2 秋夜讀書", "### 丄秋夜讀書")
    spec[18]["aEdits"] = [("3 松下問答", "松下問答")]
    seal(spec, 18, "### 3 松下問答", "### 松下問答")
    # S16: engine A read 古, engine B 鼓 (the contents' character); both
    # engines read 計 where the contents print 記.
    retitle(spec, 3, 13, "晨鐘暮鼓", "晨鐘暮鼓山寺早課聽松")
    spec[13]["aEdits"] = [("1 晨鐘暮鼓", "1 晨鐘暮古")]
    seal(spec, 13, "### 1 晨鐘暮鼓", "### 1 晨鐘暮古")
    retitle(spec, 3, 15, "田園小記", "田園小記春耕秋收冬藏")
    spec[15]["aEdits"] = [("2 田園小記", "2 田園小計")]
    spec[15]["bEdits"] = [("2 田園小記", "2 田園小計")]
    seal(spec, 15, "### 2 田園小記", "### 2 田園小計")
    # S7: a date printed at the foot of the title's column; one after a
    # subtitle's ordinal set as a figure.
    set_heading(spec, 5, "1 春日遊記三年五月七日")
    set_heading(spec, 7, "2 秋夜讀書之2三年六月八日")
    # S7: a long title whose body copy lost two characters (it still
    # matches, with a window one short), its date after it.
    retitle(spec, 2, 9, "山居雜詠", LONG_TITLE)
    set_heading(spec, 9, f"3 {LONG_TITLE}十年五月七日")
    seal(spec, 9, f"### 3 {LONG_TITLE}", f"### 3 {LONG_TITLE.replace('明月', '')}")
    # S11: the mark after a number the page holds, which engine A read
    # without it; the mark engine A read after its figure, which the page
    # holds where the figure was lost.
    items = spec[3]["items"]
    for i, item in enumerate(items):
        if item[0] == "line" and item[1][:2] in ("1 ", "2 "):
            items[i] = ("line", item[1][0] + "." + item[1][2:])
    spec[3]["aEdits"] = [("1.晨鐘", "1晨鐘")]
    seal(spec, 3, "2.田園", ".田園")
    # S4: a heading that holds, before the unit's number, characters engine
    # A read there.
    set_heading(spec, 11, "卷首 4 江上聽雨")
    return spec


def units_spec() -> dict[int, dict[str, Any]]:
    """S9's book: two more units in the second group (so that each contents
    page still maps, M-6, with one title off its line's start)."""
    spec = fx.make_spec()
    for n, scan, title in ((4, 19, "竹林清話"), (5, 20, "漁舟唱晚")):
        spec[3]["items"].append(("line", f"{n} {title}"))
        spec[scan]["items"].insert(1, ("heading", f"{n} {title}", 3))
    # A unit title run onto its paragraph's line, as text; a unit title
    # glued to the end of the paragraph before it.
    first = paragraphs(spec, 11)[0]
    seal(spec, 11, "### 4 江上聽雨\n\n" + first, "4 江上聽雨" + first)
    before = run_on(180, 30) + "。"
    spec[18]["items"].insert(0, ("para", before, True))
    seal(spec, 18, before + "\n\n### 3 松下問答", before + "3 松下問答")
    return spec


def units_checks(tmp: Path) -> None:
    spec = units_spec()
    result = repair(tmp, spec, "units")
    pages = result.pages
    check(result.status == 0 and result.report["checks"]["logReplay"]["passed"] is True,
          f"units: the run exits 0 and its log replays to its output (exit {result.status})")
    first = paragraphs(spec, 11)[0]
    check(pages[11].startswith("### 4 江上聽雨\n\n" + first) and "S9" in result.rules(11),
          f"S9: the title run onto its paragraph's line is split off at engine A's next block and made a heading "
          f"({pages[11][:30]!r})")
    check("。\n\n### 3 松下問答\n\n" in pages[18] and "S9" in result.rules(18),
          f"S9: the title glued to the paragraph before it is split off where its engine A block starts "
          f"({result.rules(18)})")
    rest = again(tmp, "units", result)
    check(not rest, f"units: the stages run again on their own output change nothing "
                    f"({[(e.page, e.rule) for e in rest]})")


def contents_checks(tmp: Path) -> None:
    spec = contents_spec()
    result = repair(tmp, spec, "contents")
    pages = result.pages
    check(result.status == 0 and result.report["checks"]["logReplay"]["passed"] is True,
          f"contents: the run exits 0 and its log replays to its output (exit {result.status})")
    lines = pages[2].split("\n")
    check("1 春日遊記" in lines and "- 春日遊記" not in pages[2],
          f"S11: the bullet goes, the number both engines read is written ({lines})")
    check("2 秋夜讀書" in lines and "秋夜讀書 2" not in pages[2],
          "S11: the number printed after the title goes before it")
    check(f"3 {LONG_TITLE}" in lines and "。山居雜詠" not in pages[2],
          "S11: a mark before the title engine A did not read goes")
    check("### 甲編 詩文" in lines, "S11: the group line is a heading, the run suffix apart from the rest")
    check("江上聽雨" in lines and any(q["rule"] == "S11" and "江上聽雨" in q.get("entry", "")
                                    for q in result.questions),
          f"S11: an entry whose number no source read is a question, not a guess ({result.asked(2)})")
    check(3 in result.doubted("unit-not-in-scan") and any("竹林清話" in d["detail"] for d in result.doubts),
          "an entry with no unit in the body is a `unit-not-in-scan` doubt")
    check("### 2 秋夜讀書" in pages[7] and "丄" not in pages[7] and "S4" in result.rules(7),
          f"S4: engine A's number replaces the glyph it did not read ({result.rules(7)})")
    check("### 松下問答" in pages[18] and "S4" in result.asked(18) and "S4" not in result.rules(18),
          f"S4: a unit whose number engine A did not read is a question ({result.asked(18)})")
    check("### 1 晨鐘暮鼓山寺" in pages[13] and "S16" in result.rules(13),
          f"S16: where the engines disagree, the one that reads the contents' character wins ({result.rules(13)})")
    check("### 2 田園小計春耕" in pages[15] and "S16" not in result.rules(15),
          "S16: a character both engines read stays, though the contents print another")
    check("### 1 春日遊記\n\n三年五月七日" in pages[5] and "S7" in result.rules(5),
          f"S7: the date after the title is its own paragraph ({result.rules(5)})")
    check("### 2 秋夜讀書之2\n\n三年六月八日" in pages[7],
          f"S7: a figure just before the date stays with the title ({pages[7].split(chr(10))[:3]})")
    short = LONG_TITLE.replace("明月", "")
    check(f"### 3 {short}\n\n十年五月七日" in pages[9],
          f"S7: the date after a title two characters short of the contents' moves whole "
          f"({[line for line in pages[9].split(chr(10)) if line.strip()][:2]})")
    later = pages[3].split("\n")
    check("1. 晨鐘暮鼓山寺早課聽松" in later,
          f"S11: the mark after a number the page holds stays where engine A read the figure without it "
          f"({[line for line in pages[3].split(chr(10)) if line.strip()]})")
    check("2. 田園小記春耕秋收冬藏" in later and "2. ." not in pages[3],
          "S11: the mark engine A read after its figure, held by the page where the figure was lost, is written once")
    check("### 卷首 4 江上聽雨" in pages[11] and "S4" in result.asked(11) and "S4" not in result.rules(11),
          f"S4: characters engine A read before the unit's number stay, and the site is a question "
          f"({result.rules(11)}, {result.asked(11)})")
    rest = again(tmp, "contents", result)
    check(not rest, f"contents: the stages run again on their own output change nothing "
                    f"({[(e.page, e.rule) for e in rest]})")


# --- headings --------------------------------------------------------------------------

def headings_spec() -> dict[int, dict[str, Any]]:
    spec = fx.make_spec()
    # H-JOIN: a heading printed over two lines, engine A's one block.
    set_heading(spec, 11, "4 江上聽雨——在江邊作")
    seal(spec, 11, "### 4 江上聽雨——在江邊作", "### 4 江上聽雨\n——在江邊作")
    # Its look-alike: a lead written as a heading over the paragraph it
    # opens (engine A's one block, longer than a column).
    lead = paragraphs(spec, 12)[1]
    spec[12]["items"][1] = ("para", "甲、春耕" + lead, False)
    seal(spec, 12, "甲、春耕" + lead, "## 甲、春耕\n" + lead)
    # S6: the dash engine A read between title and subtitle, lost.
    set_heading(spec, 7, "2 秋夜讀書——在山中作")
    seal(spec, 7, "### 2 秋夜讀書——在山中作", "### 2 秋夜讀書在山中作")
    # Its look-alike: engine A read a stand-in glyph beside its dash, and
    # the page holds two of them (engine B's) where the dash is.
    set_heading(spec, 5, "1 春日遊記——在園中作")
    spec[5]["aEdits"] = [("春日遊記——在", "春日遊記——口在")]
    spec[5]["bEdits"] = [("春日遊記——在", "春日遊記口口在")]
    seal(spec, 5, "### 1 春日遊記——在園中作", "### 1 春日遊記口口在園中作")
    # S7x: a date's copy inside a heading, beside its date line; a date
    # printed twice (in the heading and in its line) stays.
    spec[9]["items"].insert(1, ("line", "五年二月三日"))
    seal(spec, 9, "### 3 山居雜詠", "### 3 山居五年二月三日雜詠")
    set_heading(spec, 13, "1 晨鐘暮鼓八年九月十日")
    spec[13]["items"].insert(3, ("line", "八年九月十日"))
    # S8: a date line printed under its heading, written above it; one
    # printed above its heading stays.
    spec[15]["items"].insert(1, ("line", "六年三月四日"))
    seal(spec, 15, "### 2 田園小記\n\n六年三月四日", "六年三月四日\n\n### 2 田園小記")
    spec[18]["items"].insert(0, ("line", "七年四月五日"))
    # S10: scan 16 ends mid-sentence with a full last column; scan 17 opens
    # with the sentence's end in a flush column, written as a heading.  Its
    # look-alike: scan 20 opens with a heading after scan 19's finished text.
    spec[16]["items"][-1] = ("para", run_on(160, 78), False)
    spec[17]["items"].insert(0, ("para", "好景常在。", True))
    seal(spec, 17, "好景常在。\n\n", "# 好景常在。\n\n")
    first = paragraphs(spec, 20)[0]
    seal(spec, 20, first, "# " + first)
    # S15: a run written twice that engine B read once; a run printed twice.
    body = paragraphs(spec, 10)[1]
    run = body[:12]
    seal(spec, 10, run, run + run)
    body = paragraphs(spec, 14)[2]
    spec[14]["items"][2] = ("para", body[:12] + body, False)
    return spec


def headings_checks(tmp: Path) -> None:
    spec = headings_spec()
    result = repair(tmp, spec, "headings", "--no-contents", "--no-levels", "--no-title-page", "--no-paragraphs")
    pages = result.pages
    check(result.status == 0 and result.report["checks"]["logReplay"]["passed"] is True,
          f"headings: the run exits 0 and its log replays to its output (exit {result.status})")
    check("### 4 江上聽雨——在江邊作\n" in pages[11] and "H-JOIN" in result.rules(11),
          f"H-JOIN: a heading printed over two lines, engine A's one block, is one line ({result.rules(11)})")
    check("## 甲、春耕\n" in pages[12] and "H-JOIN" not in result.rules(12),
          "H-JOIN: a heading over the paragraph it leads (longer than a column) is not joined")
    check("### 2 秋夜讀書——在山中作" in pages[7] and "S6" in result.rules(7),
          f"S6: engine A's dash between the title and its subtitle is written ({result.rules(7)})")
    check("S6" not in [r for p in (9, 13, 15, 18) for r in result.rules(p)],
          "S6: a heading where engine A read no dash is left")
    check("口口在園中作" in pages[5] and "S6" not in result.rules(5) and "S6" in result.asked(5),
          f"S6: engine A's dash beside a stand-in glyph it read is a question, not written beside the page's "
          f"stand-ins ({[line for line in pages[5].split(chr(10)) if line.startswith('#')]}, {result.asked(5)})")
    check("### 3 山居雜詠\n" in pages[9] and "五年二月三日" in pages[9] and "S7x" in result.rules(9),
          f"S7x: the date's copy inside the heading goes, its line stays ({result.rules(9)})")
    check("### 1 晨鐘暮鼓八年九月十日" in pages[13] and "S7x" not in result.rules(13),
          "S7x: a date printed in the heading and in its line (engine A read both) stays")
    check(pages[15].index("### 2 田園小記") < pages[15].index("六年三月四日") and "S8" in result.rules(15),
          f"S8: a date line engine A reads after its heading goes below it ({result.rules(15)})")
    check(pages[18].index("七年四月五日") < pages[18].index("### 3 松下問答") and "S8" not in result.rules(18),
          "S8: a date line printed above its heading stays there")
    check(pages[17].startswith("好景常在。") and "S10" in result.rules(17),
          f"S10: a page-top heading that finishes the previous page's sentence is text ({result.rules(17)})")
    evidence = json.loads((result.out / "boundary-evidence.json").read_text(encoding="utf-8"))["boundaries"]
    check(evidence["17"]["label"] == "join" and evidence["17"]["rule"] == "J3",
          f"J3: the boundary before it is a join ({evidence['17']})")
    check(pages[20].startswith("# ") and "S10" not in result.rules(20),
          "S10: a page-top heading after a page whose text is finished stays")
    body = paragraphs(spec, 10)[1]
    check(pages[10].count(body[:12]) == 1 and "S15" in result.rules(10),
          f"S15: a run written twice that engine B read once is kept once ({result.rules(10)})")
    check(pages[14].count(paragraphs(spec, 14)[2][:12]) == 2 and "S15" not in result.rules(14),
          "S15: a run printed twice (both engines read it twice) stays")
    rest = [e for e in again(tmp, "headings", result) if e.rule in ("H-JOIN", "S6", "S7x", "S8", "S10", "S15")]
    check(not rest, f"headings: the rules run again on their own output change nothing "
                    f"({[(e.page, e.rule) for e in rest]})")


# --- levels and the title page ---------------------------------------------------------

def title_page(**changes: Any) -> dict[str, Any]:
    """The title page printed right to left, set across the page: engine A
    read both lines backwards, engine B the title forwards only; the page
    lost the title and holds the second line backwards.  Its title is the
    running head's stem alone.  CHANGES replace any of these."""
    page = {"items": [("heading", fx.HEAD, 1), ("line", "林泉書屋藏版")], "aHorizontal": True,
            "aEdits": [(fx.HEAD, fx.HEAD[::-1]), ("林泉書屋藏版", "版藏屋書泉林")],
            "bEdits": [("林泉書屋藏版\n", "")],
            "sealedEdits": [("# " + fx.HEAD + "\n\n林泉書屋藏版", "版藏屋書泉林")]}
    page.update(changes)
    return page


def levels_spec() -> dict[int, dict[str, Any]]:
    spec = fx.make_spec()
    # S13: the title page printed right to left; engine A read both lines
    # backwards, engine B the title forwards only; the page lost the title
    # and holds the second line backwards.
    # Its title is the running head's stem alone.
    spec[1].update(title_page())
    # Levels set page by page, each off the scheme.
    seal(spec, 2, "## 青山文叢目次", "# 青山文叢目次")
    seal(spec, 3, "### 乙編 詩文", "## 乙編 詩文")
    seal(spec, 5, "## 甲編", "# 甲編")
    seal(spec, 7, "### 2 秋夜讀書", "## 2 秋夜讀書")
    # A heading of its own inside a unit; an occasion line under a unit
    # heading, its date at its end; a date written as a heading; a lead
    # written as a heading over its paragraph; a heading no rule places.
    spec[6]["items"].insert(2, ("heading", "一 總說", 2))
    k = next(i for i, item in enumerate(spec[9]["items"]) if item[0] == "heading")
    spec[9]["items"].insert(k + 1, ("heading", "在山中作 三年五月七日", 3))
    spec[11]["items"].insert(2, ("heading", "四年六月八日", 3))
    lead = paragraphs(spec, 12)[1]
    spec[12]["items"][1] = ("para", "甲、春耕" + lead, False)
    seal(spec, 12, "甲、春耕" + lead, "## 甲、春耕\n" + lead)
    # The same, its enumerator's word opening with a numeral (no date).
    lead = paragraphs(spec, 14)[1]
    spec[14]["items"][1] = ("para", "一，五湖" + lead, False)
    seal(spec, 14, "一，五湖" + lead, "## 一，五湖\n" + lead)
    spec[4]["items"].insert(0, ("heading", "序", 2))
    # A numeral alone written as a heading inside a unit (it opens the
    # paragraph under it): no heading of its own.
    spec[8]["items"].insert(2, ("heading", "三", 2))
    return spec


def levels_checks(tmp: Path) -> None:
    spec = levels_spec()
    result = repair(tmp, spec, "levels")
    pages = result.pages
    check(result.status == 0 and result.report["checks"]["logReplay"]["passed"] is True,
          f"levels: the run exits 0 and its log replays to its output (exit {result.status})")
    check(pages[1] == f"# {fx.HEAD}\n\n林泉書屋藏版\n" and "S13" in result.rules(1),
          f"S13: the page printed right to left is rebuilt line by line, its title from engine B ({pages[1]!r})")
    lint = json.loads((result.out / "lint.json").read_text(encoding="utf-8"))["after"]["hits"]
    check(not [h for h in lint["FURN-HEAD"] if h["page"] == 1] and 1 not in result.doubted("heading-kind-unknown"),
          "the rebuilt title (the stem alone, which engine A read backwards) is the book's title: no running-head "
          "count, no heading doubt")
    check(result.asked(1).count("S13") == 2, f"S13: one question per rebuilt line ({result.asked(1)})")
    check(not [r for p in range(2, 21) for r in result.rules(p) if r == "S13"],
          "S13: no other page is taken for one printed right to left")
    check(pages[2].startswith("## 青山文叢目次") and "### 乙編 詩文" in pages[3] and pages[5].startswith("## 甲編")
          and "### 2 秋夜讀書" in pages[7],
          "S5: the contents title and the divider at ##, the group and the unit at ###")
    check("#### 一 總說" in pages[6], f"S5: a heading of its own inside a unit is one below the unit "
                                      f"({[l for l in pages[6].split(chr(10)) if l.startswith('#')]})")
    check("\n在山中作\n\n三年五月七日\n" in pages[9] and "S12" in result.rules(9),
          f"S12: the occasion line under a unit heading is text, its date its own paragraph ({result.rules(9)})")
    check("\n四年六月八日\n" in pages[11] and "#" not in pages[11].split("四年六月八日")[0].split("\n")[-1],
          "S5: a date written as a heading is text")
    check("## 甲、春耕" in pages[12] and "S5" in result.asked(12),
          f"a heading engine A read at the start of a longer block keeps its level and is a question "
          f"({result.asked(12)})")
    check("## 一，五湖" in pages[14] and "S5" in result.asked(14),
          f"an enumerator and a word that opens with a numeral is no date line: kept, a question "
          f"({result.asked(14)}, {result.rules(14)})")
    check("## 三" in pages[8] and 8 in result.doubted("heading-kind-unknown"),
          "a numeral alone written as a heading inside a unit is no heading of its own: its level stays, a "
          "`heading-kind-unknown` doubt")
    check("## 序" in pages[4] and 4 in result.doubted("heading-kind-unknown"),
          f"a heading no rule places keeps its level, a `heading-kind-unknown` doubt "
          f"({result.doubted('heading-kind-unknown')})")
    rest = again(tmp, "levels", result)
    check(not rest, f"levels: the stages run again on their own output change nothing "
                    f"({[(e.page, e.rule) for e in rest]})")


def title_page_checks(tmp: Path) -> None:
    """S13's guards, each on a book of its own (only the title-page stage
    runs)."""
    only = ("--no-furniture", "--no-marks", "--no-headings", "--no-contents", "--no-levels", "--no-paragraphs",
            "--no-joins")
    cases = {
        # The title set across the page, the second line a column engine A
        # read forwards (the page holds it so).
        "column": title_page(aHorizontal=[0], aEdits=[(fx.HEAD, fx.HEAD[::-1])], sealedEdits=[]),
        # Both lines across the page; engine B read the second one the same
        # way round as engine A.
        "same-way": title_page(aEdits=[(fx.HEAD, fx.HEAD[::-1])], bEdits=[], sealedEdits=[]),
        # The page holds a line no line of engine A's holds.
        "unread-line": title_page(extraSealed=["竹影松風"]),
        # The page holds figures no line of engine A's holds.
        "unread-figures": title_page(extraSealed=["1933"]),
    }
    for name, page in cases.items():
        spec = fx.make_spec()
        spec[1].update(page)
        result = repair(tmp, spec, f"title-{name}", *only)
        check(result.pages[1] == result.sealed[1] and "S13" not in result.rules(1) and "S13" in result.asked(1),
              f"S13 ({name}): the page is not rebuilt, it is a question ({result.pages[1]!r}, {result.asked(1)})")


# --- gates -----------------------------------------------------------------------------

def gate_checks(tmp: Path) -> None:
    # Contents numbered by tens: the numbers read are not the entries'
    # places.
    spec = fx.make_spec()
    for scan in spec:
        items = spec[scan]["items"]
        for i, item in enumerate(items):
            if item[0] in ("line", "heading") and item[1][:1].isdigit():
                n, title = item[1].split(" ", 1)
                items[i] = (item[0], f"{int(n) * 10} {title}", *item[2:])
    result = repair(tmp, spec, "tens")
    check(result.status == 0 and any(d.get("gate") == "contents-numbering" for d in result.doubts),
          "contents whose numbers are not their places fail the contents-numbering gate (a `gate-failed` doubt)")
    check(not [r for r in result.log if r["rule"] in ("S11", "S4")],
          f"with the gate failed, no number is written from a place "
          f"({[(r['page'], r['rule']) for r in result.log if r['rule'] in ('S11', 'S4')]})")
    # No contents: the contents pages set as prose.
    spec = fx.make_spec()
    for scan in (2, 3):
        spec[scan]["items"] = [("para", fx.paragraph(scan + 300, 90), False)]
    seal(spec, 7, "### 2 秋夜讀書", "# 2 秋夜讀書")
    result = repair(tmp, spec, "no-contents")
    structural = [r for r in result.log if r["rule"] in ("S9", "S4", "S16", "S7", "S11", "S5", "S12")]
    check(not result.report["gates"].get("M-6") and not structural and not result.doubted("heading-kind-unknown"),
          f"a book with no contents (M-6 failed) gets no contents or level edit and no heading doubt "
          f"({[(r['page'], r['rule']) for r in structural]})")


def main() -> int:
    date_checks()
    with tempfile.TemporaryDirectory() as tmp:
        contents_checks(Path(tmp))
        units_checks(Path(tmp))
        headings_checks(Path(tmp))
        levels_checks(Path(tmp))
        title_page_checks(Path(tmp))
        gate_checks(Path(tmp))
    print(f"{'FAIL' if FAILURES else 'ok  '} check_repair_structure: {len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
