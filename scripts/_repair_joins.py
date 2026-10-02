"""The book repair tool's paragraph and page-boundary rules
(scripts/repair_book.py): where a paragraph starts inside a page, and what
each page marker stands for - the labels of boundaries.json that
finalize_page_markers.py applies.

The print shows a paragraph's start: the book model measured where its
columns start (M-8) and how far a paragraph's first column is set down
(M-8b: two clusters, flush and k cells, with almost nothing between).  Each
rule reads that measure for the column where engine A starts a block, the
previous column's foot, and the text; a rule acts only where the book passed
the gates it needs, and a site whose signals disagree, fall between the
clusters, or cannot be measured becomes a question, never a guess.

Paragraphs (stage `paragraphs`), within each page, in two passes:
- P4 a line that repeats the line before it exactly, which engine A read
  once -> the second copy goes.
- P7 engine A starts a block inside a line of the page, and the block's
  first column is set down at the paragraph indent -> a paragraph break
  there (before the marks and figures engine A read opening the block); an
  indent between the clusters is a question (Q-Y), and so is a numeral or
  stand-in the page holds just before the block that engine A read outside
  it (a run-in enumerator, or the end of the paragraph before).  Not inside
  a heading.
- P1 a soft break (two ordinary lines, one newline) where the second line
  starts an engine A block whose first column is at the paragraph indent,
  or where either line is a date line -> a blank line.
- P2 a soft break where the second line runs on in engine A's block, or
  starts a block whose first column is flush after a full column -> the
  lines joined.  Any other soft break is a question (Q-Y); with M-8b failed,
  every soft break is.
- P6 two items of one list (the same marker; numbered ones in sequence)
  with only blank lines between -> one newline (a tight list); an item's
  text written on as an indented paragraph after a blank line, where the
  print runs on (engine A's one block, or a flush column after a full one)
  -> joined into the item.
- P5 (_repair_rules) the blank line around a heading.

Page boundaries (stage `joins`), each marker page against the marker page
before it; the previous page's last column and the next page's first
column, measured with the band masked (M-8), and whether the previous text
is finished (a sentence-final mark of the book, M-10, a date line or a
heading):
- S  the first marker -> `start`.
- T  inside the contents (M-6) -> `list-new` when the next line is a list
  item, else `paragraph`; from another page into the first contents page, or
  onto a divider (M-5), whose first line is a heading -> `structural`.
- H  the next page opens with a heading set below the frame's top (its
  column not flush), after finished text or a short column -> `structural`;
  the previous page ends with a heading and the next column is not flush ->
  `structural`.
- L  a list item after an item of the same list -> `list-new`; P-3 a list
  item after a column at least two cells short, its column not flush ->
  `structural`.
- J4 an indented block (set lower than the paragraph indent) that goes on
  at the same indent as the previous page's full last column, the text
  unfinished -> `join`.  After a finished sentence the print does not show
  whether a new block starts there (the paragraph indent, M-8b, is measured
  on the body's columns, not on a block set lower): a question.
- J1 flush after a full column, the text unfinished -> `join` (J3 where the
  headings stage made the page's first line text, S10); J2 the same after a
  finished sentence, only where the book opens its paragraphs indented
  (M-8b) -> `join`.
- P-1 the paragraph indent after finished text -> `paragraph`; P-2 a column
  set down (at the paragraph indent or lower: a date, a quotation) after a
  column at least 1.5 cells short -> `paragraph`.
- anything else -> a question (Q-B) and `paragraph`, which keeps both sides
  and splices nothing, marked unverified (a `boundary-unverified` doubt).
A join is never written into a heading, a list item, a table or an HTML
block (finalize's contract).  After a join onto a list item that the next
page's first paragraph finishes, the blank line before the list's next item
goes (P6).  boundary-evidence.json records each label's rule, the measures
and whether it is verified.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
import re
from typing import Any, Callable, Mapping, Sequence

import proofread_pages as pp
import _book_lint as lint
import _ocr_markdown as om
import _repair_edits as re_
import _repair_model as rm
import _repair_rules as rr
import _repair_structure as rs


HEADING = rs.HEADING
LIST_NUMBER = re.compile(r"^[ \t]*(?P<n>\d+)[.)][ \t]+\S")
LIST_BULLET = re.compile(r"^[ \t]*(?P<b>[-*+])[ \t]+\S")
# A block's first column holds another block's text above it when its ink
# starts more than this many cells above the block's box: the block then
# starts inside the column, at no measured indent.
ABOVE_BLOCK = 1.0
# P-3: a list opens a new block of the page after a column at least this many
# cells short of the foot (more than a paragraph's end, PARAGRAPH_END_SHORT:
# a list item's column ends where its words end).
LIST_AFTER_SHORT = 2.0


def ordinary(line: str) -> bool:
    """A line of prose (the auditor's `ordinary` line): not blank, not
    Markdown structure, no HTML or footnote."""
    if not line.strip() or om.is_structural_line(line):
        return False
    return not line.strip().startswith(("<", "[//]:", "[^"))


def kind_of(line: str) -> str:
    body = om.line_body(line)
    if HEADING.match(body):
        return "heading"
    if om.LIST_ITEM_RE.match(body):
        return "list"
    if om.is_table_row(body) or body.lstrip().startswith("<"):
        return "table"
    if body.startswith(("  ", "\t")):
        return "indented"
    return "prose"


@dataclass
class Measure:
    """The model's measures the rules read: whether its gates passed, the
    indent k, and the sentence-final marks."""
    geometry: bool
    indent: bool
    k: float | None
    finals: str

    @classmethod
    def of(cls, model: Mapping[str, Any]) -> "Measure":
        return cls(rm.gate(model, "M-8"), rm.gate(model, "M-8b") and rm.gate(model, "M-8"),
                   ((model.get("geometry") or {}).get("indent") or {}).get("k"),
                   "".join(model.get("sentenceFinal") or "。！？"))


def block_column(setting: rs.Setting, scan: int, reading: rs.PageReading, block: int,
                 last: bool = False) -> dict[str, Any] | None:
    """The first column (in reading order) of engine A's block BLOCK on page
    SCAN, from the model's measured columns: the first column whose centre
    lies in the block's box; None when there is none, or when its ink starts
    well above the block (another block's text above it in the column).
    With LAST, the block's last column, None when its ink runs on well
    below the block (another block's text under it)."""
    geometry = rm.page_entry(setting.model, scan).get("geometry") or {}
    columns = geometry.get("columns") or []
    size = rm.page_size(setting.book.pages[scan])
    if not columns or not size or block is None or block >= len(reading.pd.a_blocks):
        return None
    width, height = size
    x, y, w, h = reading.pd.a_blocks[block]["box"]
    left, right = x * width, (x + w) * width
    top, foot = y * height, (y + h) * height
    pitch = geometry.get("pitch") or 1
    inside = [c for c in columns if left <= (c["x0"] + c["x1"]) / 2 <= right and c["foot"] > top and c["top"] < foot]
    if not inside:
        return None
    column = inside[-1] if last else inside[0]
    if not last and top - column["top"] > ABOVE_BLOCK * pitch:
        return None
    if last and column["foot"] - foot > ABOVE_BLOCK * pitch:
        return None
    return column


def block_class(setting: rs.Setting, measure: Measure, scan: int, reading: rs.PageReading,
                block: int | None) -> tuple[str | None, float | None]:
    """Where engine A's block BLOCK starts against the paragraph indent:
    `flush`, `paragraph`, `above`, `between` (rm.indent_class), or None when
    it cannot be measured."""
    column = block_column(setting, scan, reading, block) if block is not None else None
    if column is None or not measure.k:
        return None, None
    return rm.indent_class(column["topCells"], measure.k), column["topCells"]


# --- paragraphs -----------------------------------------------------------------

def p4(setting: rs.Setting, scan: int, plan: rr.Plan) -> None:
    """P4 on one page."""
    reading = setting.reading(scan)
    lines = [line for line in rs.line_spans(reading.text) if line.text.strip()]
    for one, two in zip(lines, lines[1:]):
        body = two.text.strip()
        chars = pp.CJK(body)
        if body != one.text.strip() or len(chars) < 2 or HEADING.match(body):
            continue
        if reading.count(chars, "a") != 1 or reading.count(chars, "b") > 1:
            continue
        plan.edits.append(re_.Edit(scan, one.end, two.end, "", rule="P4", evidence={
            "line": body, "engineA": 1}))


def p7(setting: rs.Setting, measure: Measure, scan: int, plan: rr.Plan) -> None:
    """P7 on one page."""
    reading = setting.reading(scan)
    text = reading.text
    if not reading.block_of:
        return
    a_to = reading.align.a_to_sealed
    lines = rs.line_spans(text)
    starts = [line.start for line in lines]
    for b in sorted(set(reading.block_of)):
        j = reading.block_of.index(b)
        k = a_to[j] if j < len(a_to) else None
        if k is None:
            continue
        offset = reading.s.offsets[k]
        line = lines[max(0, bisect.bisect_right(starts, offset) - 1)]
        if HEADING.match(line.text) or not ordinary(line.text):
            continue
        before = reading.chars_in(line.start, offset)
        if not before:
            continue
        cls, top = block_class(setting, measure, scan, reading, b)
        if cls == "paragraph":
            at = lead_start(reading, j, offset, line.start)
            tail = trailing_run(reading, before)
            if tail and len(tail) <= 2 and all(c in rm.NUMERALS or c in setting.facts.standins() for c in tail):
                # The page holds a numeral or a stand-in just before the
                # block, which engine A read outside it: a run-in
                # enumerator of the paragraph, or the end of the one before.
                plan.questions.append(rr.question(
                    "Q-Y", scan, "P7", text, reading.s.offsets[before[-len(tail)]], min(line.end, offset + 8),
                    f"engine A starts a paragraph here (its first column {top} cells down), and the page holds "
                    f"{tail!r} just before it, outside engine A's block: which paragraph does it open or end?",
                    firstColumnTop=top))
                continue
            start, end = rs.break_span(text, at, line.start)
            plan.edits.append(re_.Edit(scan, start, end, "\n\n", rule="P7", evidence={
                "block": b, "firstColumnTop": top, "k": measure.k, "after": text[max(line.start, start - 8):start],
                "before": text[end:end + 8]}))
        elif cls == "between":
            plan.questions.append(rr.question(
                "Q-Y", scan, "P7", text, offset, min(line.end, offset + 8),
                f"engine A starts a block here, inside the page's paragraph, and its first column is set {top} cells "
                f"down (between flush and the paragraph indent {measure.k}): a new paragraph?",
                firstColumnTop=top))


def lead_start(reading: rs.PageReading, j: int, offset: int, floor: int) -> int:
    """Where engine A's block whose first character is its character J (at
    the page's OFFSET) starts on the page: before the marks and figures
    engine A read opening the block (a figure's brackets), where the page
    holds them just before OFFSET."""
    stream = reading.align.a
    gap = stream.gaps[j]
    lead = rr.marks_of(gap.split("\n")[-1])
    if lead:
        text = reading.text
        at = offset
        want = lead
        while want and at > floor and (text[at - 1].isspace() or rr.marks_of(text[at - 1]) == want[-1:]):
            if not text[at - 1].isspace():
                want = want[:-1]
            at -= 1
        if not want:
            return at
    return offset


def trailing_run(reading: rs.PageReading, before: Sequence[int]) -> str:
    """The run of CJK characters that ends just before a split, back to the
    nearest mark or white space."""
    out = []
    for k in reversed(before):
        out.append(reading.s.chars[k])
        prev = k - 1
        if prev < 0 or reading.s.offsets[k] - reading.s.offsets[prev] != 1:
            break
    return "".join(reversed(out))


def soft_breaks(setting: rs.Setting, measure: Measure, scan: int, plan: rr.Plan) -> None:
    """P1 and P2 on one page."""
    reading = setting.reading(scan)
    text = reading.text
    lines = rs.line_spans(text)
    for one, two in zip(lines, lines[1:]):
        if not (ordinary(one.text) and ordinary(two.text)):
            continue
        ks = reading.chars_in(two.start, two.end)
        prev = reading.chars_in(one.start, one.end)
        dated = rs.is_date_line(one.text) or rs.is_date_line(two.text)
        evidence: dict[str, Any] = {"line": two.text[:12]}
        label = None
        if dated:
            label = "P1"
            evidence["dateLine"] = True
        elif ks and measure.indent:
            k = ks[0]
            b = reading.block(k)
            if b is not None and not reading.block_start(k) and prev and reading.block(prev[-1]) == b:
                label = "P2"
                evidence["engineA"] = "runs on in one block"
            elif b is not None and reading.block_start(k):
                cls, top = block_class(setting, measure, scan, reading, b)
                evidence.update(firstColumnTop=top, k=measure.k)
                label = {"paragraph": "P1", "flush": "P2"}.get(cls or "")
                if label == "P2":
                    # Flush after a full column: the paragraph goes on.  After
                    # a short one the print ended something there.
                    before = reading.block(prev[-1]) if prev else None
                    column = block_column(setting, scan, reading, before, last=True) if before is not None else None
                    short = column["shortCells"] if column else None
                    evidence["previousColumnShort"] = short
                    if short is None or short >= rm.FULL_COLUMN_SHORT:
                        label = None
        if label == "P1":
            plan.edits.append(re_.Edit(scan, one.end, one.end, "\n", rule="P1", evidence=evidence))
        elif label == "P2":
            tail = one.text.rstrip()
            head = two.text.lstrip()
            glue = " " if tail[-1:].isascii() and tail[-1:].isalnum() and head[:1].isascii() and head[:1].isalnum() else ""
            plan.edits.append(re_.Edit(scan, one.start + len(tail), two.start + len(two.text) - len(head), glue,
                                       rule="P2", evidence=evidence))
        else:
            short = evidence.get("previousColumnShort")
            why = ("the book's paragraph indent is not measured (M-8b)" if not measure.indent
                   else "engine A's block here cannot be placed against the paragraph indent"
                   if evidence.get("firstColumnTop") is None
                   else f"it starts flush after a column {short} cells short" if "previousColumnShort" in evidence
                   else f"its first column is set {evidence['firstColumnTop']} cells down, neither flush nor at the "
                        f"paragraph indent {measure.k}")
            plan.questions.append(rr.question("Q-Y", scan, "P1", text, one.end, one.end + 1,
                                              f"a line break inside a paragraph: {why}; the same paragraph, or a "
                                              "new one?", line=two.text[:12]))


def list_marker(line: str) -> tuple[str, int | None] | None:
    match = LIST_NUMBER.match(line)
    if match:
        return "number", int(match.group("n"))
    match = LIST_BULLET.match(line)
    if match:
        return match.group("b"), None
    return None


def same_list(one: str, two: str) -> bool:
    a, b = list_marker(one), list_marker(two)
    if not a or not b or a[0] != b[0]:
        return False
    return a[1] is None or b[1] == a[1] + 1


def p6(setting: rs.Setting, measure: Measure, scan: int, plan: rr.Plan) -> None:
    """P6 on one page: two items of one list a blank line apart; and a list
    item's text written on as an indented paragraph of its own, which the
    print runs on (engine A's one block, or a flush column after a full
    one) -> joined into the item."""
    reading = setting.reading(scan)
    text = reading.text
    lines = [line for line in rs.line_spans(text) if line.text.strip()]
    for one, two in zip(lines, lines[1:]):
        between = text[one.end:two.start]
        if between.count("\n") < 2 or between.strip():
            continue
        if same_list(one.text, two.text):
            plan.edits.append(re_.Edit(scan, one.end, two.start, "\n", rule="P6", evidence={
                "items": [one.text[:8], two.text[:8]]}))
            continue
        if kind_of(two.text) != "indented" or not (list_marker(one.text) or kind_of(one.text) == "indented") \
                or not measure.indent:
            continue
        ks, prev = reading.chars_in(two.start, two.end), reading.chars_in(one.start, one.end)
        if not ks or not prev:
            continue
        b, a = reading.block(ks[0]), reading.block(prev[-1])
        runs_on = b is not None and b == a and not reading.block_start(ks[0])
        if not runs_on and b is not None and reading.block_start(ks[0]):
            cls, _ = block_class(setting, measure, scan, reading, b)
            column = block_column(setting, scan, reading, a, last=True) if a is not None else None
            runs_on = cls == "flush" and column is not None and column["shortCells"] < rm.FULL_COLUMN_SHORT
        if runs_on:
            lead = len(two.text) - len(two.text.lstrip())
            plan.edits.append(re_.Edit(scan, one.end, two.start + lead, "", rule="P6", evidence={
                "item": one.text[:8], "runsOn": two.text.strip()[:8]}))


def paragraphs(book: Any, model: Mapping[str, Any], texts: Mapping[int, str], order: Sequence[int],
               apply: Callable[[Sequence[re_.Edit]], None], facts: rr.BookFacts | None = None,
               readings: rs.Readings | None = None) -> rr.Plan:
    """The paragraphs stage over the pages ORDER: P4 and P7, applied through
    APPLY; then P1, P2, P6 and P5."""
    facts = facts or rr.book_facts(book, model)
    setting = rs.Setting(book, model, facts, readings or rs.Readings(book, model), list(order), texts)
    measure = Measure.of(model)
    plan = rr.Plan()
    first = rr.Plan()
    for scan in order:
        p4(setting, scan, first)
        if measure.indent:
            p7(setting, measure, scan, first)
    plan.questions.extend(first.questions)
    apply(first.edits)
    for scan in order:
        soft_breaks(setting, measure, scan, plan)
        p6(setting, measure, scan, plan)
    spacing = rr.spacing(book, model, texts, order)
    # P5 and the soft-break rules act on different lines (a heading's, and
    # two ordinary lines'), so they do not meet.
    plan.edits.extend(spacing.edits)
    return plan


# --- page boundaries -------------------------------------------------------------

def first_line(text: str) -> str:
    return next((line for line in text.split("\n") if line.strip()), "")


def last_line(text: str) -> str:
    return lint.last_line(text)


def finished(line: str, finals: str) -> bool:
    if HEADING.match(line) or rs.is_date_line(line):
        return True
    return lint.sentence_finished(line, finals)


def boundary(setting: rs.Setting, measure: Measure, prev: int, scan: int,
             demoted: set[int]) -> tuple[str, dict[str, Any], str | None]:
    """The label of the boundary between marker pages PREV and SCAN, its
    evidence, and why it is not settled (None when it is)."""
    model = setting.model
    before, after = setting.texts[prev], setting.texts[scan]
    if not before.strip() or not after.strip():
        return "paragraph", {"rule": "empty", "why": "a page with no text"}, None
    tail, head = last_line(before), first_line(after)
    prev_geo = rm.page_entry(model, prev).get("geometry") or {}
    next_geo = rm.page_entry(model, scan).get("geometry") or {}
    last = (prev_geo.get("columns") or [None])[-1]
    first = (next_geo.get("columns") or [None])[0]
    short = last["shortCells"] if last else None
    top = first["topCells"] if first else None
    cls = rm.indent_class(top, measure.k) if top is not None and measure.k else None
    done = finished(tail, measure.finals)
    kinds = (kind_of(tail), kind_of(head))
    evidence: dict[str, Any] = {"previousTail": tail[-12:], "nextHead": head[:12], "previousFinished": done,
                                "previousLastShort": short, "nextFirstTop": top, "nextFirstClass": cls,
                                "kinds": list(kinds)}
    contents = set(model.get("contentsPages") or [])
    entry = rm.page_entry(model, scan)
    geo = measure.geometry and measure.indent and short is not None and top is not None

    def settled(label: str, rule: str) -> tuple[str, dict[str, Any], None]:
        evidence["rule"] = rule
        return label, evidence, None

    def unsettled(why: str) -> tuple[str, dict[str, Any], str]:
        evidence["rule"] = "Q-B"
        return "paragraph", evidence, why

    if prev in contents and scan in contents:
        return settled("list-new" if kinds[1] == "list" else "paragraph", "T")
    if kinds[1] == "heading":
        if entry.get("divider") or (scan in contents and prev not in contents):
            return settled("structural", "T" if scan in contents else "H")
        if measure.indent and cls in ("paragraph", "above") and (
                done or (short is not None and short >= rm.FULL_COLUMN_SHORT)):
            return settled("structural", "H")
        return unsettled("the next page opens with a heading, and the print does not show it set apart")
    if kinds[0] == "heading":
        if geo and cls != "flush":
            return settled("structural", "H")
        return unsettled("the previous page ends with a heading, and the next column starts flush")
    if kinds[1] == "table" or kinds[0] == "table":
        return unsettled("a table or an HTML block at the page's edge")
    if kinds[1] == "list":
        if kinds[0] == "list" and same_list(tail, head):
            return settled("list-new", "L")
        if geo and short >= LIST_AFTER_SHORT and cls != "flush":
            return settled("structural", "P-3")
        return unsettled("the next page opens with a list item that goes on from no item of the same list")
    if kinds[1] == "indented":
        return unsettled("the next page opens with an indented line")
    if not geo:
        return unsettled("the columns at the page edges are not measured (M-8/M-8b)")
    full = short < rm.FULL_COLUMN_SHORT
    last_top = last["topCells"]
    if full and cls == "above" and abs(top - last_top) <= rm.PARAGRAPH_TOLERANCE:
        if not done:
            return settled("join", "J4")
        return unsettled(f"a block set {top} cells down goes on at its indent after a full column, and the text "
                         "before it is finished: the same block, or a new one?")
    if cls == "flush" and full:
        if not done:
            return settled("join", "J3" if scan in demoted else "J1")
        return settled("join", "J2")
    if cls == "paragraph" and done:
        return settled("paragraph", "P-1")
    if cls in ("paragraph", "above") and short >= rm.PARAGRAPH_END_SHORT:
        return settled("paragraph", "P-2")
    return unsettled(f"the next page's first column is {cls} ({top} cells) and the previous page's last column "
                     f"{short} cells short; the text is {'finished' if done else 'unfinished'}")


def joins(book: Any, model: Mapping[str, Any], texts: Mapping[int, str], order: Sequence[int],
          demoted: set[int], facts: rr.BookFacts | None = None,
          readings: rs.Readings | None = None) -> tuple[rr.Plan, dict[int, str], dict[str, Any]]:
    """The joins stage over the assembly's marker pages ORDER: the plan (P6's
    edits after joins, the questions, the doubts), the labels and the
    evidence.  DEMOTED holds the pages whose first line S10 made text."""
    facts = facts or rr.book_facts(book, model)
    setting = rs.Setting(book, model, facts, readings or rs.Readings(book, model), list(order), texts)
    measure = Measure.of(model)
    plan = rr.Plan()
    labels: dict[int, str] = {}
    evidence: dict[str, Any] = {}
    markers = [s for s in sorted(book.pages) if book.pages[s].marker]
    for n, scan in enumerate(order):
        if n == 0:
            labels[scan] = "start"
            evidence[str(scan)] = {"label": "start", "rule": "S", "verified": True}
            continue
        prev = order[n - 1]
        k = markers.index(scan) if scan in markers else -1
        if k <= 0 or markers[k - 1] != prev:
            labels[scan] = "paragraph"
            evidence[str(scan)] = {"label": "paragraph", "rule": "gap", "verified": False,
                                   "why": f"the pages between {prev} and {scan} are not in this run"}
            plan.doubts.append(("boundary-unverified", scan, f"page {scan} follows page {prev} in this run, "
                                "with pages between them left out: written `paragraph`", {"previous": prev}))
            continue
        label, found, why = boundary(setting, measure, prev, scan, demoted)
        labels[scan] = label
        found = {"label": label, **found, "verified": why is None}
        if why is not None:
            question = rr.question("Q-B", scan, "J", texts[scan], 0, len(first_line(texts[scan])), why,
                                   previousPage=prev, previousTail=found.get("previousTail"))
            plan.questions.append(question)
            found["why"] = why
            plan.doubts.append(("boundary-unverified", scan, f"the boundary before page {scan}: {why}; written "
                                "`paragraph`", {"previous": prev, "rule": found.get("rule")}))
        evidence[str(scan)] = found
        if label == "join" and kind_of(last_line(texts[prev])) == "list":
            close_list(setting, scan, plan)
    return plan, labels, evidence


def close_list(setting: rs.Setting, scan: int, plan: rr.Plan) -> None:
    """P6 across a page: the next page's first paragraph finishes the list
    item the previous page ends with (a join), and the list's next item
    follows it after a blank line: the blank line goes."""
    text = setting.texts[scan]
    lines = [line for line in rs.line_spans(text) if line.text.strip()]
    if len(lines) < 2:
        return
    one, two = lines[0], lines[1]
    between = text[one.end:two.start]
    if between.count("\n") >= 2 and not between.strip() and kind_of(one.text) == "prose" and list_marker(two.text):
        plan.edits.append(re_.Edit(scan, one.end, two.start, "\n", rule="P6", evidence={
            "across": "the previous page's list item goes on here", "item": two.text[:8]}))


def contract_problems(combined: str, labels: Mapping[int, str]) -> list[str]:
    """finalize_page_markers.py's contract for LABELS on the annotated book
    COMBINED."""
    lines = om.split_lines(combined)
    markers, malformed = om.find_page_markers(lines)
    problems = [f"line {n}: malformed page marker {body!r}" for n, body in malformed]
    return problems + om.boundary_contract_problems(lines, markers, dict(labels))
