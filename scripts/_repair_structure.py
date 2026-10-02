"""The book repair tool's structure rules (scripts/repair_book.py): heading
content per page, the contents and the units they list, the title page, and
one heading hierarchy for the whole book.

Each rule acts only on what the book model (_repair_model.py) measured on
this book and on what the engines read; a rule whose gate failed stays
silent, and a site it finds but cannot settle becomes a planned question or
a doubt, never a guess.  Nothing here adds a character no engine read: the
rules move text already on the page, write a figure engine A read, delete a
stand-in engine A did not read or a copy an engine read once, and change
Markdown structure (`#`, blank lines, the space after a number).

The contents map (contents_map) is the book's own second printing of every
unit title: the contents pages (M-6) parsed into their title, their groups
(a line that opens with a run suffix of the body, M-3) and their entries,
each entry's number as the page and the engines read it, and each entry
mapped, in contents order, onto the line of the body that prints it.  An
entry's number is its place in its group only where the book numbers its
entries that way (the `contents-numbering` gate: most numbers read are their
places, and enough of them); elsewhere it is what two sources read alike.

Headings (stage `headings`), per page:
- H-JOIN a heading and the lines under it that engine A read in the same
  block, each no longer than a column (M-8) and not ending a sentence, up
  to a date: one heading printed over two lines -> one heading line.  A
  longer line is the paragraph a run-in lead opens (the levels stage asks).
- S6 in a heading, engine A read a dash between two characters where the
  page holds no dash (nothing, marks, a shorter dash, or stand-ins) ->
  engine A's dash; where one of the two is a stand-in glyph (the page's
  stand-ins there may be the dash itself) -> a question (Q-P).
- S7x a date written twice in a heading, or in a heading and a date line
  next to it, that engine A read once -> the copy inside the heading goes
  (of two inside, the one engine A reads no characters around).
- S8 a date line just above a heading, which engine A reads after the
  heading's text -> moved below the heading.
- S10 a heading opening the page that finishes the previous page's
  sentence: the previous text is unfinished, the page's first column starts
  flush and the previous page's last column is full (M-8b), and the heading
  ends a sentence or engine A read it in a block that is no title -> plain
  text (the page boundary becomes J3's join).
- S15 a run of eight or more characters written twice in a row that engine
  B read once and engine A not twice -> the copy engine B did not read goes.

Contents (stage `contents`), in passes on the text the pass before leaves:
- S9 an entry whose title stands in the body as a plain line, or at the
  start of an engine A block inside a line, where engine A read the entry's
  number before it -> split off (before it, at the start of the block; after
  it, at engine A's next block, or after a date that ends it) and made a
  heading; a title whose end the engines do not show is a question (Q-L).
- S4 a unit heading whose number engine A read as the entry's number ->
  `n[mark] title` with engine A's mark; the prefix it replaces holds only
  what engine A did not read there (stand-ins, the number in the other
  script, marks).  No number, another number, or a prefix engine A read ->
  a question (Q-P).  A number written with no mark (engine A read none, the
  page holds none) where the units on either side in its group carry one
  -> a question (Q-P) over the number as written.
- S16 the engines disagree on one character of a unit title and exactly one
  of them is the contents' character -> that one; an agreement is never
  overridden.
- S7 a date after a unit title -> its own paragraph with what follows it on
  the line (a place clause).  The date's start is certain only where its run
  of numerals starts it, or where one start in the run parses (之四四月…);
  the title ends at its last character the contents' title matches
  (title_end), and a figure just before the date stays with it.  Marks
  between the title and the date that neither engine read between them go
  with the split (left, they would end the heading).
- S11 the contents rebuilt: bullets dropped; each entry `N[mark] title` with
  the number the page, engine A or engine B read where it is the entry's
  number and the mark after it (engine A's, else the page's), a number
  printed after the title moved before it, marks before the title that
  engine A did not read (or read as its figure's mark) dropped; the group
  lines as headings, the run suffix apart from the rest; the contents title
  as a heading; entries that make a Markdown list tight, the others a blank
  line apart.  An entry whose number no source read is a question (Q-P), and
  so is one read without the mark the entries on either side carry: each
  carries the mark its group numbers with, where every number of the group
  written with a mark carries the same one (two at least, none a colon) -
  the answer reads a colon-like mark after the number as it.  An entry with
  no unit in the body is a `unit-not-in-scan` doubt.

Title page (stage `title-page`): S13 on a page where one engine's reading of
a block (four or more characters) is the exact reverse of the other's, the
reversed engine's lines are the page's lines read backwards: the page is
rebuilt in engine A's block order, each line read forwards - as the page
holds it where it does, else as the engine that read it forwards read it -
and a block engine A labels a title as a heading.  One question (Q-L) per
rebuilt line (its glyphs).  A page with a block engine A read as a column,
a line engine B read the same way round as engine A, or anything (a
character, a figure, a mark) no line of engine A's holds is not rebuilt: a
question.

Levels (stage `levels`): every heading gets a kind - book title (the first
heading before the contents, a title block of engine A), contents title,
contents group, division (a divider's suffix, M-5), unit (a contents
entry), heading inside a unit (a block of its own in engine A, a title
block, or display type), occasion line (S12: just under a unit heading, no
enumerator), date line - and one level per contents depth: the book title
`#`, the contents title and the divisions one below it, the groups and units
one below those (at the divisions' level in a book without divisions), a
heading inside a unit one below its unit.  Occasion and date lines become
plain text (a date closing an occasion line its own paragraph); a heading
engine A read as the start of a longer block is a question (Q-Y: a run-in
lead or a heading); any other heading keeps its level and is a
`heading-kind-unknown` doubt.
"""

from __future__ import annotations

import bisect
from collections import Counter
from dataclasses import dataclass, field
import difflib
import re
from typing import Any, Callable, Mapping, Sequence

import proofread_pages as pp
import _book_lint as lint
import _repair_align as ra
import _repair_edits as re_
import _repair_model as rm
import _repair_rules as rr


HEADING = re.compile(r"^(?P<indent> {0,3})(?P<marks>#{1,6})[ \t]+")
LIST_ITEM = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+\S")
# A contents line's markup and leading number: a bullet, a heading marker, a
# stray bracket before the figure, the figure and the mark after it.
ENTRY_LEAD = re.compile(r"^(?P<markup>[ \t]*(?:[-*+][ \t]+)?(?:#{1,6}[ \t]+)?)(?P<pre>[\[［(（]?[ \t]*)"
                        r"(?:(?P<digits>[0-9０-９]{1,3})[ \t]*(?P<mark>[.．,，。、])?)?")
ENTRY_TRAIL = re.compile(r"[ \t]+(?P<digits>[0-9０-９]{1,3})[ \t]*$")
# A figure at the end of an engine's gap, the mark after it and white space.
GAP_FIGURE = re.compile(r"(?<![0-9０-９])(?P<digits>[0-9０-９]{1,3})[ \t]*(?P<mark>[.．,，、。])?\s*$")
# Marks that open what follows them: a split point goes before them.
OPENERS = frozenset("「『（(《〈【“‘[［")
# An enumerator opening a heading (一 導言, （二）, 3.).
ENUMERATOR = re.compile(r"^[（(]?(?:[0-9０-９]{1,3}|[一二三四五六七八九十]{1,3})[）)]?"
                        r"(?:[、，,．.·：:\s]|(?=[㐀-鿿])|$)")
# Marks that read as a colon after a number: a full stop with a speck of
# ink above it reads so too.
COLON_LIKE = frozenset("：:︰")
# How close a contents entry and a body title must be (the book model's
# contents similarity), and how many leading characters either may carry
# that the other lacks (a number's stand-ins).
TITLE_SIMILARITY = rm.CONTENTS_SIMILARITY
LEADING_DROP = rm.CONTENTS_LEADING_DROP
# The weaker pass: between two entries mapped in order, a line whose engine A
# number is the entry's and whose start is at least this close to the title.
WEAK_SIMILARITY = 0.6
# A title of fewer characters than this matches only a heading, or a line
# whose engine A number is the entry's: two characters open many lines.
SHORT_TITLE = 4
# The contents-numbering gate: of the entries whose number a source read, at
# least this share read their place in their group, and at least this many.
NUMBERING_SHARE = 0.8
NUMBERING_MINIMUM = 3
# A heading's prefix before its title that S4 may replace holds at most this
# many characters engine A did not read (a figure read as glyphs: the
# model's STANDIN_RUN).
PREFIX_CHARACTERS = rm.STANDIN_RUN
# What moves with a date into its own paragraph: a place or occasion clause
# of at most this many characters.  With more after it the date is no date
# line's, and nothing is moved.
PLACE_CLAUSE = 16
# S9: without an engine A block break after a title, what may follow the
# title on its line and still be the title's column (a subtitle, a date):
# at most this many characters.  More is a question (where the title ends).
TITLE_TAIL = 40
# The title page: an exact reverse of at least this many characters.
REVERSE_MINIMUM = 4
# A run written twice in a row (S15) is at least this long.
DUPLICATE_MINIMUM = 8

DATE_NUMERALS = rm.NUMERALS + "卄"
DATE_SEPARATORS = "，、．.,"
DIGIT = {c: i for i, c in enumerate("〇一二三四五六七八九")}
DIGIT["零"] = 0
TENS = {"廿": 20, "卄": 20, "卅": 30}


# --- common ------------------------------------------------------------------

def heading_of(line: str) -> re.Match | None:
    return HEADING.match(line)


def heading_body(line: str) -> str:
    match = HEADING.match(line)
    return line[match.end():] if match else line


def folded(text: str) -> str:
    return pp.variant_fold(text)


def date_value(text: str) -> int | None:
    """A date's numeral, strictly: digits read one by one (九五, 一九二八);
    or tens and units (十, 十二, 二十, 二十三, 廿三, 卅一); None otherwise."""
    if not text:
        return None
    if all(c in DIGIT for c in text):
        return int("".join(str(DIGIT[c]) for c in text))
    if text[0] in TENS:
        rest = text[1:]
        if not rest:
            return TENS[text[0]]
        return TENS[text[0]] + DIGIT[rest] if len(rest) == 1 and rest in DIGIT and DIGIT[rest] else None
    match = re.fullmatch(r"([一二三四五六七八九])?十([一二三四五六七八九])?", text)
    if match:
        return (DIGIT[match.group(1)] if match.group(1) else 1) * 10 + (DIGIT[match.group(2)] if match.group(2) else 0)
    if any(c in "百千" for c in text):
        return rm.numeral_value(text)
    return None


DATE_FORMS = (
    re.compile(rf"(?P<y>[{DATE_NUMERALS}]+)年(?:(?P<m>[{DATE_NUMERALS}]+)月(?:(?P<d>[{DATE_NUMERALS}]+)日)?)?"),
    re.compile(rf"(?P<m>[{DATE_NUMERALS}]+)月(?:(?P<d>[{DATE_NUMERALS}]+)日)?"),
    re.compile(rf"(?P<a>[{DATE_NUMERALS}]{{1,4}})[{DATE_SEPARATORS}](?P<b>[{DATE_NUMERALS}]{{1,3}})"
               rf"(?:[{DATE_SEPARATORS}](?P<c>[{DATE_NUMERALS}]{{1,3}}))?[{DATE_SEPARATORS}]?"),
)


def date_at(text: str, at: int) -> int | None:
    """The end of a date starting at AT of TEXT - a year with or without its
    month and day, a month with or without its day, or two or three numeral
    groups between separators - when its numerals parse and the month is
    1-12 and the day 1-31; the longest such date; None when none parses.
    Numeral groups end at a separator, a mark, the text's end or 年/月/日:
    a group that runs on into a word is an enumerator and the word's first
    numeral (一，五湖…), no date."""
    best = None
    for form in DATE_FORMS:
        match = form.match(text, at)
        if not match:
            continue
        g = match.groupdict()
        if g.get("a") is not None:
            a, b = date_value(g["a"]), date_value(g["b"])
            c = date_value(g["c"]) if g.get("c") is not None else None
            end = match.end()
            if a is None or b is None or (g.get("c") is not None and c is None):
                ok = False
            elif text[end - 1] not in DATE_SEPARATORS and end < len(text) and pp.CJK(text[end]) \
                    and text[end] not in "年月日":
                ok = False
            elif c is not None:
                ok = 1 <= b <= 12 and 1 <= c <= 31
            else:
                ok = 1 <= b <= 12 or (1 <= a <= 12 and 1 <= b <= 31)
        else:
            ok = True
            if "y" in g and g.get("y") is not None:
                ok = date_value(g["y"]) is not None
            if g.get("m") is not None:
                ok = ok and 1 <= (date_value(g["m"]) or 0) <= 12
            if g.get("d") is not None:
                ok = ok and 1 <= (date_value(g["d"]) or 0) <= 31
            if "y" not in g and g.get("d") is None:
                # A month alone (三月) is no date line's: too many words hold it.
                ok = False
        if ok and (best is None or match.end() > best):
            best = match.end()
    return best


def find_date(text: str, start: int = 0) -> tuple[int, int] | None:
    """The first date in TEXT[start:] whose start is certain: the date that
    starts where its run of numerals starts, when it parses; else the one
    start inside that run that parses (a subtitle's ordinal glued to the
    date leaves one); None when two starts parse, or none in any run."""
    at = start
    while at < len(text):
        if text[at] not in DATE_NUMERALS:
            at += 1
            continue
        run_end = at
        while run_end < len(text) and text[run_end] in DATE_NUMERALS:
            run_end += 1
        end = date_at(text, at)
        if end is not None:
            return at, end
        found = [(s, e) for s in range(at + 1, run_end) for e in [date_at(text, s)] if e is not None]
        if len(found) == 1:
            return found[0]
        if len(found) > 1:
            return None
        at = run_end
    return None


def is_date_line(text: str) -> bool:
    """A line that is a date and at most a place clause after it."""
    body = lint.LINE_PREFIX.sub("", heading_body(text)).strip()
    if not body or body[0] not in DATE_NUMERALS:
        return False
    found = find_date(body)
    return bool(found) and found[0] == 0 and len(pp.CJK(body[found[1]:])) <= PLACE_CLAUSE


def split_back(text: str, at: int, floor: int, figures: bool = True) -> int:
    """Where to split TEXT before offset AT: back over white space and the
    opening marks just before it (they open what follows), and with FIGURES
    over the figures there too (a block's enumerator), no further back than
    FLOOR."""
    while at > floor and (text[at - 1] in OPENERS or text[at - 1] in " \t"
                          or figures and (text[at - 1].isdigit() or text[at - 1] in "０１２３４５６７８９")):
        at -= 1
    return at


def title_match(entry: str, target: str) -> tuple[float, int, int]:
    """How well ENTRY (a contents title, folded CJK) matches the start of
    TARGET (folded CJK): the best ratio with up to LEADING_DROP leading
    characters dropped from either (those dropped from the entry count
    against it) and the target window a character longer or shorter than
    the entry; and where the title lies in TARGET (start, end), its end
    before what the window holds past the entry's last character
    (title_end).  A title of fewer than three characters is matched whole."""
    best = (0.0, 0, 0)
    if not entry or not target:
        return best
    for de in range(0, min(LEADING_DROP, max(0, len(entry) - 3)) + 1):
        e = entry[de:]
        for dt in range(0, LEADING_DROP + 1):
            if dt >= len(target) or target[dt] != e[0]:
                continue
            for width in (len(e), len(e) - 1, len(e) + 1):
                if width < 1 or dt + width > len(target) or (len(entry) < 3 and width != len(e)):
                    continue
                window = target[dt:dt + width]
                ratio = 1.0 if window == e else difflib.SequenceMatcher(None, e, window, autojunk=False).ratio()
                ratio *= len(e) / len(entry)
                if ratio > best[0] + 1e-9:
                    best = (ratio, dt, dt + title_end(e, window))
    return best


def title_end(entry: str, window: str) -> int:
    """How much of WINDOW (the body's characters where the title ENTRY is
    matched) the title takes: all of it but the characters past the entry's
    last one that match nothing of the entry.  A body title two characters
    short of the contents' still matches with a window one short, and that
    window then holds the first character of what follows the title (the
    first numeral of its date)."""
    ops = difflib.SequenceMatcher(None, entry, window, autojunk=False).get_opcodes()
    if not ops:
        return len(window)
    tag, i1, i2, j1, j2 = ops[-1]
    if tag == "insert":
        return j1
    if tag == "replace" and j2 - j1 > i2 - i1:
        return j1 + (i2 - i1)
    return len(window)


# --- page readings ------------------------------------------------------------

class PageReading:
    """One page as the structure rules read it: the page data
    (_repair_rules.PageData), the alignment with both engines, and engine
    A's block of each of its characters."""

    def __init__(self, pd: rr.PageData):
        self.pd = pd
        self.text = pd.text
        self.align = ra.align_page(pd.text, pd.a_body, pd.b_body)
        self.block_of = rr.a_blocks_of(pd) if pd.a_blocks and pp.CJK(pd.a_body) else []
        self._folds: dict[str, str] = {}

    @property
    def s(self) -> ra.Stream:
        return self.align.sealed

    def chars_in(self, start: int, end: int) -> list[int]:
        """The sealed stream indices of the CJK characters in TEXT[start:end]."""
        offsets = self.s.offsets
        return list(range(bisect.bisect_left(offsets, start), bisect.bisect_left(offsets, end)))

    def a_index(self, k: int) -> int | None:
        return self.align.sealed_to_a[k] if 0 <= k < len(self.align.sealed_to_a) else None

    def b_index(self, k: int) -> int | None:
        return self.align.sealed_to_b[k] if 0 <= k < len(self.align.sealed_to_b) else None

    def block(self, k: int) -> int | None:
        """Engine A's block of sealed character K (None: not read by A)."""
        j = self.a_index(k)
        if j is None or not self.block_of or j >= len(self.block_of):
            return None
        return self.block_of[j]

    def block_start(self, k: int) -> bool:
        """Whether sealed character K is the first character of an engine A
        block."""
        j = self.a_index(k)
        if j is None or not self.block_of or j >= len(self.block_of):
            return False
        return j == 0 or self.block_of[j - 1] != self.block_of[j]

    def _fold(self, engine: str) -> str:
        if engine not in self._folds:
            stream = self.align.a if engine == "a" else self.align.b
            self._folds[engine] = folded(stream.chars)
        return self._folds[engine]

    def figure_at(self, k: int, chars: str = "", engine: str = "a") -> tuple[int, str] | None:
        """The figure an engine read just before sealed character K, by the
        alignment; where K is not aligned to it, just before CHARS (folded
        CJK) found in its page stream.  Its value and the mark after it."""
        j = (self.a_index(k) if engine == "a" else self.b_index(k)) if k >= 0 else None
        if j is None:
            return self.figure_before(chars, engine) if chars else None
        stream = self.align.a if engine == "a" else self.align.b
        return gap_figure(stream.gaps[j])

    def figure_before(self, chars: str, engine: str = "a") -> tuple[int, str] | None:
        """The figure an engine read just before CHARS (folded CJK), found in
        its page stream once: the whole of CHARS, else its longest start
        (three characters at least) that the stream holds only once."""
        stream = self.align.a if engine == "a" else self.align.b
        hay = self._fold(engine)
        for size in range(len(chars), 2, -1):
            j = hay.find(chars[:size])
            if j >= 0:
                if hay.find(chars[:size], j + 1) >= 0:
                    return None
                return gap_figure(stream.gaps[j])
        return None

    def count(self, chars: str, engine: str, without: frozenset[str] | set[str] = frozenset()) -> int:
        """How often ENGINE read CHARS (folded), its stand-in glyphs WITHOUT
        taken out of both (engine B writes a glyph for a comma inside a
        run the page holds without it)."""
        if not chars:
            return 0
        hay = self._fold(engine)
        needle = folded(chars)
        if without:
            hay = "".join(c for c in hay if c not in without)
            needle = "".join(c for c in needle if c not in without)
        return hay.count(needle) if needle else 0

    def find(self, chars: str, engine: str) -> int | None:
        """Where ENGINE read CHARS (folded), when it read them once."""
        hay = self._fold(engine)
        needle = folded(chars)
        at = hay.find(needle) if needle else -1
        if at < 0 or hay.find(needle, at + 1) >= 0:
            return None
        return at


def gap_figure(gap: str) -> tuple[int, str] | None:
    match = GAP_FIGURE.search(gap)
    if not match:
        return None
    return int(match.group("digits").translate(ra.FULLWIDTH_DIGITS)), (match.group("mark") or "")


class Readings:
    """PageReading per page text, computed once."""

    def __init__(self, book: Any, model: Mapping[str, Any]):
        self.book = book
        self.model = model
        self._cache: dict[tuple[int, str], PageReading] = {}

    def get(self, scan: int, text: str) -> PageReading:
        key = (scan, text)
        if key not in self._cache:
            if len(self._cache) > 4096:
                self._cache.clear()
            self._cache[key] = PageReading(rr.page_data(self.book, self.model, scan, text))
        return self._cache[key]


def all_texts(book: Any, texts: Mapping[int, str]) -> dict[int, str]:
    """Every marker page's text: under repair (TEXTS) or, for a page outside
    a subset, as sealed."""
    return {scan: texts[scan] if scan in texts else book.pages[scan].sealed_text
            for scan in sorted(book.pages) if book.pages[scan].marker}


def body_suffixes(model: Mapping[str, Any]) -> list[str]:
    """The run suffixes of the body (M-3), not the contents word; longest
    first."""
    if not rm.gate(model, "M-3"):
        return []
    words = {r.get("contentsWord") for r in (model.get("contents") or {}).get("runs") or []}
    return sorted({r["suffix"] for r in model.get("suffixRuns") or [] if r["suffix"] not in words},
                  key=len, reverse=True)


def line_spans(text: str) -> list[rr.Line]:
    return rr.lines_of(text)


# --- the contents map -----------------------------------------------------------

@dataclass
class Unit:
    """Where a contents entry's title stands in the body: the page, the line
    (1-based, in the text the map was made from), the title's span in that
    line's CJK characters, whether the line is a heading, whether the title
    starts inside the line, and the figure engine A read before it."""
    page: int
    line: int
    start: int
    end: int
    heading: bool
    mid_line: bool
    a_number: tuple[int, str] | None
    score: float
    anchor: int = 0


@dataclass
class Row:
    """One contents line: where it is now, its characters as the book model
    read them, its kind (`title`, `group`, `entry`), its group and place, the
    numbers the sources read, the entry's number and its unit."""
    page: int
    line: int
    chars: str
    kind: str
    matched: bool = False
    group: int = -1
    place: int = 0
    suffix: str | None = None
    numbers: dict[str, tuple[int, str]] = field(default_factory=dict)
    number: int | None = None
    unit: Unit | None = None


@dataclass
class Contents:
    rows: list[Row]
    pages: list[int]
    word: str | None
    numbering: dict[str, Any]
    unit_level: int
    has_divisions: bool

    def entries(self) -> list[Row]:
        return [r for r in self.rows if r.kind == "entry"]

    def groups(self) -> list[Row]:
        return [r for r in self.rows if r.kind == "group"]

    def title(self) -> Row | None:
        return next((r for r in self.rows if r.kind == "title"), None)

    def units_on(self, page: int) -> dict[int, Row]:
        """Line -> entry, for the units standing on PAGE."""
        return {r.unit.line: r for r in self.entries() if r.unit and r.unit.page == page}


@dataclass
class BodyLine:
    page: int
    line: int
    ks: list[int]       # the sealed stream indices of the line's CJK characters
    chars: str          # folded CJK of the line
    heading: bool
    starts: list[int]   # indices into ks where an engine A block starts inside the line


def contents_map(book: Any, model: Mapping[str, Any], texts: Mapping[int, str], readings: Readings,
                 facts: rr.BookFacts) -> Contents | None:
    """The contents parsed and mapped onto the body (the module's docstring);
    None where the book shows no contents (M-6)."""
    if not rm.gate(model, "M-6"):
        return None
    texts = all_texts(book, texts)
    runs = (model.get("contents") or {}).get("runs") or []
    pages = sorted({p for run in runs for p in run.get("pages") or [] if p in texts})
    if not pages:
        return None
    word = next((run.get("contentsWord") for run in runs if run.get("contentsWord")), None)
    suffixes = body_suffixes(model)
    rows: list[Row] = []
    for run in runs:
        by_page: dict[int, list[dict[str, Any]]] = {}
        for entry in run.get("entries") or []:
            by_page.setdefault(entry["page"], []).append(entry)
        for page in run.get("pages") or []:
            if page not in texts:
                continue
            lines = texts[page].split("\n")
            located = lint.locate_rows(lines, by_page.get(page, []))
            for entry, number in zip(by_page.get(page, []), located):
                if number is None:
                    continue
                line = lines[number - 1]
                core = lint.line_core(line)
                # A line of the running head's shape left in the text (the
                # furniture stage off) is no contents line - but the first
                # contents page's heading is its title, whatever it holds.
                matched = entry.get("matchedPage") is not None
                # The title: the first line of the first contents page, no
                # unit's, a heading or holding the contents word.
                title = page == pages[0] and entry is by_page[page][0] and not matched \
                    and bool(heading_of(line) or (word and word in entry["text"]))
                if not title and facts.stems and lint.head_line(core, facts.stems,
                                                                facts.suffixes + ([word] if word else [])):
                    continue
                if not title and word and pp.CJK(line) == word:
                    continue
                rows.append(Row(page, number, entry["text"], "title" if title else "entry", matched=matched))
    rows.sort(key=lambda r: (r.page, r.line))
    group = -1
    place = 0
    for row in rows:
        if row.kind == "title":
            continue
        suffix = next((s for s in suffixes if row.chars.startswith(s)), None)
        if suffix and not row.matched:
            row.kind, row.suffix = "group", suffix
            group += 1
            place = 0
            row.group = group
            continue
        place += 1
        row.group, row.place = max(group, 0), place
    has_divisions = any(r.kind == "group" for r in rows) or bool(model.get("dividers"))
    contents = Contents(rows, pages, word, {}, 3 if has_divisions else 2, has_divisions)
    read_numbers(contents, texts, readings)
    map_units(contents, model, texts, readings)
    return contents


def read_numbers(contents: Contents, texts: Mapping[int, str], readings: Readings) -> None:
    """Each entry's number as the page, engine A and engine B read it; the
    contents-numbering gate; each entry's number."""
    agree = total = 0
    for row in contents.entries():
        line = texts[row.page].split("\n")[row.line - 1]
        match = ENTRY_LEAD.match(line)
        if match and match.group("digits"):
            row.numbers["page"] = (int(match.group("digits").translate(ra.FULLWIDTH_DIGITS)), match.group("mark") or "")
        else:
            trail = ENTRY_TRAIL.search(line)
            if trail and pp.CJK(line[:trail.start()]):
                row.numbers["pageAfter"] = (int(trail.group("digits").translate(ra.FULLWIDTH_DIGITS)), "")
        reading = readings.get(row.page, texts[row.page])
        spans = line_spans(texts[row.page])[row.line - 1]
        ks = reading.chars_in(spans.start, spans.end)
        first = ks[0] if ks else -1
        key = folded(row.chars)
        for engine, name in (("a", "engineA"), ("b", "engineB")):
            found = reading.figure_at(first, key, engine)
            if found:
                row.numbers[name] = found
        values = {v for v, _ in row.numbers.values()}
        if values:
            total += 1
            agree += row.place in values
    passed = total >= NUMBERING_MINIMUM and agree >= NUMBERING_SHARE * total
    contents.numbering = {"passed": passed, "read": total, "atTheirPlace": agree, "needs": NUMBERING_SHARE,
                          "minimum": NUMBERING_MINIMUM}
    for row in contents.entries():
        values = {v for v, _ in row.numbers.values()}
        if passed:
            row.number = row.place
        elif len(values) == 1 and len(row.numbers) >= 2:
            row.number = next(iter(values))


def body_lines(texts: Mapping[int, str], readings: Readings, contents_pages: Sequence[int]) -> list[BodyLine]:
    """The body's lines after the first contents page, each with its folded
    characters and where engine A starts a block inside it."""
    out = []
    first = min(contents_pages)
    skip = set(contents_pages)
    for scan in sorted(texts):
        if scan <= first or scan in skip:
            continue
        text = texts[scan]
        reading = readings.get(scan, text)
        for line in line_spans(text):
            ks = reading.chars_in(line.start, line.end)
            if not ks:
                continue
            chars = folded("".join(reading.s.chars[k] for k in ks))
            starts = [i for i, k in enumerate(ks) if i > 0 and reading.block_start(k)]
            out.append(BodyLine(scan, line.number, ks, chars, bool(heading_of(line.text)), starts))
    return out


def map_units(contents: Contents, model: Mapping[str, Any], texts: Mapping[int, str], readings: Readings) -> None:
    """Each entry's unit: the longest chain, in contents order and in page
    order, of body lines (or engine A block starts inside a line) matching
    the entries, each in its group's run of pages where the group names a
    run; then, between two entries so mapped, the one line that engine A
    numbers as the entry and that starts like its title."""
    entries = contents.entries()
    if not entries:
        return
    lines = body_lines(texts, readings, contents.pages)
    spans: dict[int, tuple[int, int]] = {}
    for row in contents.groups():
        run = next((r for r in (model.get("folio") or {}).get("runs") or [] if r.get("suffix") == row.suffix), None)
        if run and run.get("span"):
            spans[row.group] = (run["span"][0], run["span"][1])
    index: dict[str, list[tuple[int, int]]] = {}
    for n, body in enumerate(lines):
        for c in [0] + body.starts:
            for d in range(LEADING_DROP + 1):
                if c + d < len(body.chars):
                    index.setdefault(body.chars[c + d], []).append((n, c))

    def number_at(body: BodyLine, c: int) -> tuple[int, str] | None:
        reading = readings.get(body.page, texts[body.page])
        return reading.figure_at(body.ks[c], body.chars[c:c + 6]) if c < len(body.ks) else None

    candidates: list[tuple[int, int, int, float, int, int]] = []
    for e, row in enumerate(entries):
        key = folded(row.chars)
        span = spans.get(row.group)
        seen = set()
        for d in range(min(LEADING_DROP, max(0, len(key) - 1)) + 1):
            for n, c in index.get(key[d], ()):
                if (n, c) in seen:
                    continue
                seen.add((n, c))
                body = lines[n]
                if span and not span[0] <= body.page <= span[1]:
                    continue
                ratio, start, end = title_match(key, body.chars[c:])
                if ratio < TITLE_SIMILARITY:
                    continue
                number = number_at(body, c + start)
                agrees = bool(number and row.number is not None and number[0] == row.number)
                whole_heading = body.heading and c == 0
                if len(key) < SHORT_TITLE and not whole_heading and not agrees:
                    continue
                score = ratio + (0.5 if whole_heading else 0.0) + (0.5 if agrees else 0.0)
                candidates.append((e, n, c, score, start, end))
    placed = {cand[0]: cand for cand in longest_chain(candidates)}
    for e, row in enumerate(entries):
        if e in placed or row.number is None:
            continue
        before = max((placed[x][1] for x in placed if x < e), default=-1)
        after = min((placed[x][1] for x in placed if x > e), default=len(lines))
        key = folded(row.chars)
        span = spans.get(row.group)
        found = []
        for n in range(before + 1, after):
            body = lines[n]
            if span and not span[0] <= body.page <= span[1]:
                continue
            for c in [0] + body.starts:
                rest = body.chars[c:]
                number = number_at(body, c)
                if not number or number[0] != row.number:
                    continue
                window = rest[:len(key)]
                ratio = difflib.SequenceMatcher(None, key, window, autojunk=False).ratio()
                if ratio >= WEAK_SIMILARITY:
                    found.append((e, n, c, ratio, 0, title_end(key, window)))
        if len(found) == 1:
            placed[e] = found[0]
    for e, (_, n, c, score, start, end) in placed.items():
        body = lines[n]
        entries[e].unit = Unit(body.page, body.line, c + start, c + end, body.heading and c == 0, c > 0,
                               number_at(body, c + start), round(score, 3), c)


def longest_chain(candidates: Sequence[tuple]) -> list[tuple]:
    """The chain of candidates (entry, line, start, score, ...) with the entry
    and the place in the body both increasing: the longest, then the one
    with the highest score."""
    ordered = sorted(candidates, key=lambda c: (c[0], c[1], c[2]))
    best: list[tuple[int, float, int]] = []
    for i, cand in enumerate(ordered):
        top = (1, cand[3], -1)
        for j in range(i):
            other = ordered[j]
            if other[0] < cand[0] and (other[1], other[2]) < (cand[1], cand[2]):
                length, score, _ = best[j]
                if (length + 1, score + cand[3]) > top[:2]:
                    top = (length + 1, score + cand[3], j)
        best.append(top)
    if not ordered:
        return []
    k = max(range(len(ordered)), key=lambda i: best[i][:2])
    out = []
    while k >= 0:
        out.append(ordered[k])
        k = best[k][2]
    return list(reversed(out))


# --- shared by the stages ----------------------------------------------------------

@dataclass
class Setting:
    """What a structure stage reads: the book, its model, the facts the
    rules share, the page readings, the pages under repair and the texts
    as they stand (updated by the ledger as passes are applied)."""
    book: Any
    model: Mapping[str, Any]
    facts: rr.BookFacts
    readings: Readings
    order: list[int]
    texts: Mapping[int, str]

    def reading(self, scan: int) -> PageReading:
        return self.readings.get(scan, self.texts[scan])

    def contents(self) -> Contents | None:
        return contents_map(self.book, self.model, self.texts, self.readings, self.facts)

    def previous_marker(self, scan: int) -> int | None:
        markers = [s for s in sorted(self.book.pages) if self.book.pages[s].marker]
        k = markers.index(scan) if scan in markers else -1
        return markers[k - 1] if k > 0 else None

    def cells(self) -> int | None:
        return (self.model.get("geometry") or {}).get("cellsPerColumn") if rm.gate(self.model, "M-8") else None

    def finals(self) -> str:
        return "".join(self.model.get("sentenceFinal") or "。！？")


def question_at(kind: str, page: int, rule: str, text: str, start: int, end: int, why: str,
                **fields: Any) -> dict[str, Any]:
    return rr.question(kind, page, rule, text, start, end, why, **fields)


# --- headings (per page) ------------------------------------------------------------

def h_join(setting: Setting, scan: int, plan: rr.Plan) -> None:
    """H-JOIN on one page (the module's docstring)."""
    cells = setting.cells()
    if not cells:
        return
    reading = setting.reading(scan)
    spacing = rr.Spacing(reading.pd)
    lines = line_spans(reading.text)
    for i, line in enumerate(lines):
        if not heading_of(line.text) or rr.has_date(line.text):
            continue
        at = line
        for nxt in lines[i + 1:]:
            body = nxt.text.strip()
            if not body or heading_of(nxt.text) or LIST_ITEM.match(nxt.text) or body.startswith(("|", "<")):
                break
            if rr.starts_with_date(nxt.text) or is_date_line(nxt.text):
                break
            if not spacing.one_block(line, nxt):
                break
            if len(pp.CJK(body)) > cells or body[-1] in "。！？":
                break
            lead = len(nxt.text) - len(nxt.text.lstrip())
            plan.edits.append(re_.Edit(scan, at.end, nxt.start + lead, "", rule="H-JOIN", evidence={
                "heading": line.text, "joined": body, "cellsPerColumn": cells}))
            at = nxt


DASH_SPAN = re.compile("[" + re.escape("".join(sorted(ra.DASH_CHARS))) + "]+")


def dash_form(gap: str) -> str:
    """Engine A's marks in a gap as the page writes them: white space out,
    brackets full width, each dash run `——` (two cells or more) or `—`."""
    marks = rr.marks_of(gap)
    return DASH_SPAN.sub(lambda m: "——" if len(m.group()) >= 2 else "—", marks)


def s6(setting: Setting, scan: int, plan: rr.Plan) -> None:
    """S6 on one page's headings."""
    reading = setting.reading(scan)
    standins = setting.facts.standins()
    text = reading.text
    for line in line_spans(text):
        if not heading_of(line.text):
            continue
        ks = [k for k in reading.chars_in(line.start, line.end) if reading.a_index(k) is not None]
        for k1, k2 in zip(ks, ks[1:]):
            j1, j2 = reading.a_index(k1), reading.a_index(k2)
            if j2 != j1 + 1:
                continue
            a_gap = reading.align.a.gaps[j2]
            if not DASH_SPAN.search(a_gap):
                continue
            start, end = reading.s.offsets[k1] + 1, reading.s.offsets[k2]
            between = text[start:end]
            inner = [reading.s.chars[k] for k in range(k1 + 1, k2)]
            if any(c not in standins for c in inner):
                continue
            page_marks = rr.marks_of(between)
            want = "".join(c for c in dash_form(a_gap) if c == "—" or c in page_marks)
            longest = max((len(m.group()) for m in DASH_SPAN.finditer(between)), default=0)
            if longest >= max(len(m.group()) for m in DASH_SPAN.finditer(a_gap)) and not inner:
                continue
            if page_marks == want:
                continue
            beside = "".join(reading.s.chars[k] for k in (k1, k2) if reading.s.chars[k] in standins)
            if beside:
                # Engine A read a glyph of the book's stand-ins right beside
                # its dash, and the page may hold more of them there: whether
                # they are the dash itself is a reading.  Writing the dash
                # beside them would print it twice.
                plan.questions.append(question_at(
                    "Q-P", scan, "S6", text, reading.s.offsets[k1], reading.s.offsets[k2] + 1,
                    f"engine A read a dash here and {beside!r} beside it, a glyph that stands in for marks in "
                    "this book: is it part of the dash?", engineA=a_gap.strip()))
                continue
            plan.edits.append(re_.Edit(scan, start, end, want, rule="S6", evidence={
                "engineA": a_gap.strip(), "page": between, "standIns": "".join(inner)}))


def date_spans(text: str, start: int = 0, end: int | None = None) -> list[tuple[int, int]]:
    """Every date find_date finds in TEXT[start:end], left to right."""
    end = len(text) if end is None else end
    out = []
    at = start
    while at < end:
        found = find_date(text[:end], at)
        if not found:
            break
        out.append(found)
        at = found[1]
    return out


def s7x(setting: Setting, scan: int, plan: rr.Plan) -> None:
    """S7x on one page's headings."""
    reading = setting.reading(scan)
    text = reading.text
    lines = line_spans(text)
    for i, line in enumerate(lines):
        match = heading_of(line.text)
        if not match:
            continue
        dates = date_spans(text, line.start + match.end(), line.end)
        taken: set[tuple[int, int]] = set()
        for ds, de in dates:
            chars = pp.CJK(text[ds:de])
            if len(chars) < 3 or reading.count(chars, "a") != 1 or (ds, de) in taken:
                continue
            twins = [(s, e) for s, e in dates if (s, e) != (ds, de) and folded(pp.CJK(text[s:e])) == folded(chars)]
            near = [other for other in reversed(lines[:i]) if other.text.strip()][:2] \
                + [other for other in lines[i + 1:] if other.text.strip()][:2]
            alone = [other for other in near if not heading_of(other.text)
                     and is_date_line(other.text) and folded(pp.CJK(other.text)) == folded(chars)]
            if alone:
                victim = (ds, de)
            elif twins:
                # Of two copies inside the heading, the one engine A reads no
                # characters around: the characters on its two sides are
                # adjacent in engine A's reading.
                def breaks_run(span: tuple[int, int]) -> bool:
                    ks = reading.chars_in(span[0], span[1])
                    if not ks or ks[0] == 0 or ks[-1] + 1 >= len(reading.s.chars):
                        return False
                    return ra.adjacent_in(reading.align.sealed_to_a, ks[0] - 1, ks[-1] + 1)
                runs = [span for span in [(ds, de)] + twins if breaks_run(span)]
                if len(runs) != 1:
                    continue
                victim = runs[0]
            else:
                continue
            if victim in taken:
                continue
            taken.add(victim)
            taken.update(twins)
            plan.edits.append(re_.Edit(scan, victim[0], victim[1], "", rule="S7x", evidence={
                "date": chars, "engineACopies": 1, "otherCopy": "date line" if alone else "in the heading"}))


def s8(setting: Setting, scan: int, plan: rr.Plan) -> None:
    """S8 on one page."""
    reading = setting.reading(scan)
    text = reading.text
    lines = line_spans(text)
    for i, line in enumerate(lines):
        if not heading_of(line.text):
            continue
        previous = next((other for other in reversed(lines[:i]) if other.text.strip()), None)
        if previous is None or heading_of(previous.text) or not is_date_line(previous.text):
            continue
        if any(other.text.strip() for other in lines[previous.number:i]):
            continue
        date_at_a = reading.find(pp.CJK(previous.text), "a")
        head_at_a = reading.find(pp.CJK(heading_body(line.text)), "a")
        if date_at_a is None or head_at_a is None or date_at_a <= head_at_a:
            continue
        plan.edits.append(re_.Edit(scan, previous.start, line.start, "", rule="S8", evidence={
            "date": previous.text, "heading": line.text}))
        plan.edits.append(re_.Edit(scan, line.end, line.end, "\n\n" + previous.text.strip(), rule="S8", evidence={
            "date": previous.text, "heading": line.text, "engineA": "reads the date after the heading"}))


def page_top_heading(setting: Setting, scan: int, contents: Contents | None) -> dict[str, Any] | None:
    """S10's test for one page: the evidence when the page's first line is a
    heading that finishes the previous page's sentence (the module's
    docstring), else None."""
    if not (rm.gate(setting.model, "M-8b") and rm.gate(setting.model, "M-8")):
        return None
    reading = setting.reading(scan)
    lines = [line for line in line_spans(reading.text) if line.text.strip()]
    if not lines or not heading_of(lines[0].text):
        return None
    first = lines[0]
    if contents is not None and first.number in contents.units_on(scan):
        return None
    entry = rm.page_entry(setting.model, scan)
    if entry.get("divider"):
        return None
    previous = setting.previous_marker(scan)
    if previous is None:
        return None
    k = ((setting.model.get("geometry") or {}).get("indent") or {}).get("k")
    geometry = entry.get("geometry") or {}
    before = rm.page_entry(setting.model, previous).get("geometry") or {}
    if not k or not geometry.get("columns") or not before.get("columns"):
        return None
    indent = geometry["columns"][0]["topCells"]
    short = before["columns"][-1]["shortCells"]
    if rm.indent_class(indent, k) != "flush" or short >= rm.FULL_COLUMN_SHORT:
        return None
    previous_text = setting.texts.get(previous, setting.book.pages[previous].sealed_text)
    tail = lint.last_line(previous_text)
    finals = setting.finals()
    if not tail or heading_of(tail) or lint.sentence_finished(tail, finals) or is_date_line(tail):
        return None
    body = heading_body(first.text).rstrip()
    ends = bool(body) and body[-1] in finals
    ks = reading.chars_in(first.start, first.end)
    blocks = {reading.block(k) for k in ks} - {None}
    labels = {reading.pd.a_blocks[b].get("label") for b in blocks if b < len(reading.pd.a_blocks)}
    as_text = bool(labels) and not labels & rm.TITLE_LABELS
    if not (ends or as_text):
        return None
    return {"line": first.number, "heading": first.text, "firstColumnTop": indent, "previousShort": short,
            "previousTail": tail[-12:], "endsSentence": ends, "engineALabels": sorted(labels)}


def s10(setting: Setting, scan: int, contents: Contents | None, plan: rr.Plan) -> None:
    found = page_top_heading(setting, scan, contents)
    if not found:
        return
    reading = setting.reading(scan)
    line = line_spans(reading.text)[found["line"] - 1]
    match = heading_of(line.text)
    plan.edits.append(re_.Edit(scan, line.start, line.start + match.end(), "", rule="S10", evidence=found))


def s15(setting: Setting, scan: int, plan: rr.Plan) -> None:
    """S15 on one page."""
    reading = setting.reading(scan)
    standins = setting.facts.standins()
    chars = folded(reading.s.chars)
    size = DUPLICATE_MINIMUM
    grams: dict[str, list[int]] = {}
    for i in range(len(chars) - size + 1):
        grams.setdefault(chars[i:i + size], []).append(i)
    done = -1
    for i in range(len(chars) - 2 * size + 1):
        if i < done:
            continue
        for p in grams.get(chars[i:i + size], ()):
            length = p - i
            if length < size or p + length > len(chars) or chars[i:p] != chars[p:p + length]:
                continue
            run = reading.s.chars[i:p]
            if reading.count(run, "b", standins) != 1 or reading.count(run, "a") > 1:
                continue
            first = sum(1 for k in range(i, p) if reading.b_index(k) is not None)
            second = sum(1 for k in range(p, p + length) if reading.b_index(k) is not None)
            offsets = reading.s.offsets
            if first < second:
                start, end = offsets[i], offsets[p]
            else:
                start, end = offsets[p - 1] + 1, offsets[p + length - 1] + 1
            plan.edits.append(re_.Edit(scan, start, end, "", rule="S15", evidence={
                "run": run, "engineB": 1, "engineA": reading.count(run, "a"),
                "kept": "second" if first < second else "first"}))
            done = p + length
            break


def headings(book: Any, model: Mapping[str, Any], texts: Mapping[int, str], order: Sequence[int],
             apply: Callable[[Sequence[re_.Edit]], None], facts: rr.BookFacts | None = None,
             readings: Readings | None = None) -> rr.Plan:
    """The headings stage over the pages ORDER, in passes applied through
    APPLY: H-JOIN, S15 and S7x; then S6 and S8; then S10."""
    facts = facts or rr.book_facts(book, model)
    setting = Setting(book, model, facts, readings or Readings(book, model), list(order), texts)
    plan = rr.Plan()
    first = rr.Plan()
    for scan in order:
        h_join(setting, scan, first)
        s15(setting, scan, first)
        s7x(setting, scan, first)
    apply(first.edits)
    second = rr.Plan()
    for scan in order:
        s6(setting, scan, second)
        s8(setting, scan, second)
    apply(second.edits)
    for step in (first, second):
        plan.questions.extend(step.questions)
        plan.doubts.extend(step.doubts)
    contents = setting.contents()
    for scan in order:
        s10(setting, scan, contents, plan)
    return plan


# --- contents (book level) ------------------------------------------------------------

def break_span(text: str, at: int, floor: int, figures: bool = True) -> tuple[int, int]:
    """The span to replace with a paragraph break before offset AT: from the
    split point (split_back, FIGURES as there) over the white space after
    it, and back over the white space before it."""
    cut = split_back(text, at, floor, figures)
    start = cut
    while start > floor and text[start - 1] in " \t":
        start -= 1
    end = cut
    while end < len(text) and text[end] in " \t":
        end += 1
    return start, end


def unit_line(setting: Setting, row: Row) -> tuple[PageReading, rr.Line, list[int]]:
    reading = setting.reading(row.unit.page)
    line = line_spans(reading.text)[row.unit.line - 1]
    return reading, line, reading.chars_in(line.start, line.end)


def s9(setting: Setting, contents: Contents, plan: rr.Plan) -> None:
    """S9: each entry whose unit title is not yet a heading of its own."""
    level = contents.unit_level
    for row in contents.entries():
        unit = row.unit
        if unit is None or unit.heading or unit.page not in setting.order:
            continue
        reading, line, ks = unit_line(setting, row)
        text = reading.text
        if unit.end > len(ks):
            continue
        site = (reading.s.offsets[ks[unit.start]], reading.s.offsets[ks[unit.end - 1]] + 1)
        if unit.a_number is None or row.number is None or unit.a_number[0] != row.number:
            plan.questions.append(question_at(
                "Q-Y", unit.page, "S9", text, *site,
                f"the contents' entry {row.number} ({row.chars}) stands here as text, and engine A read "
                + (f"the number {unit.a_number[0]}" if unit.a_number else "no number") + " before it: a heading?",
                entry=row.chars, contentsPage=row.page, contentsLine=row.line, level=level))
            continue
        # After the title: engine A's next block, or the end of a date.
        first_block = next((reading.block(k) for k in ks[unit.start:unit.end] if reading.block(k) is not None), None)
        tail = None
        for k in ks[unit.end:]:
            if reading.block_start(k) and reading.block(k) != first_block:
                tail = reading.s.offsets[k]
                break
        rest = len(ks) - unit.end
        if tail is None and rest > TITLE_TAIL:
            found = find_date(text[:line.end], reading.s.offsets[ks[unit.end - 1]] + 1)
            if found and len(pp.CJK(text[found[1]:line.end])) > PLACE_CLAUSE:
                end = found[1]
                while end < line.end and not pp.CJK(text[end]) and not text[end].isspace():
                    end += 1
                tail = end
            else:
                plan.questions.append(question_at(
                    "Q-L", unit.page, "S9", text, site[0], line.end,
                    f"the contents' entry {row.number} ({row.chars}) runs on into {rest} characters engine A read "
                    "in the same block: where does the title end?", entry=row.chars, level=level))
                continue
        if unit.mid_line:
            anchor = reading.s.offsets[ks[unit.anchor]]
            start, end = break_span(text, anchor, line.start)
            plan.edits.append(re_.Edit(unit.page, start, end, "\n\n" + "#" * level + " ", rule="S9", evidence={
                "entry": row.chars, "number": row.number, "engineA": unit.a_number[0], "split": "engine A block"}))
        else:
            lead = len(line.text) - len(line.text.lstrip())
            plan.edits.append(re_.Edit(unit.page, line.start + lead, line.start + lead, "#" * level + " ",
                                       rule="S9", evidence={"entry": row.chars, "number": row.number,
                                                            "engineA": unit.a_number[0]}))
        if tail is not None:
            start, end = break_span(text, tail, site[1])
            plan.edits.append(re_.Edit(unit.page, start, end, "\n\n", rule="S9", evidence={
                "entry": row.chars, "after": "the title's end: engine A's next block or a date"}))


def s4_s16(setting: Setting, contents: Contents, plan: rr.Plan) -> None:
    """S4 and S16 on each unit heading; then S4's mark question: a unit
    number written with no mark (engine A read none, the page holds none)
    where the units on either side of it in its group carry one - engine A
    misses a small full stop - is asked (Q-P over the number as written),
    the two units' mark the question's numberStyle where it is one."""
    numbered: list[tuple[Row, str, str, int, int]] = []
    for row in contents.entries():
        unit = row.unit
        if unit is None or not unit.heading or unit.page not in setting.order:
            continue
        reading, line, ks = unit_line(setting, row)
        text = reading.text
        match = heading_of(line.text)
        if not match or unit.start >= len(ks):
            continue
        prefix_start = line.start + match.end()
        prefix_end = reading.s.offsets[ks[unit.start]]
        prefix = text[prefix_start:prefix_end]
        s16(reading, row, ks, plan)
        n = row.number
        if n is None:
            continue
        number = unit.a_number
        if number is None or number[0] != n:
            if re.fullmatch(rf"\s*{n}\s*[.．,，、]?\s*", prefix):
                continue
            why = (f"the contents give this unit the number {n}; engine A read "
                   + (f"{number[0]}" if number else "no number") + " before its title")
            plan.questions.append(question_at("Q-P", unit.page, "S4", text, prefix_start, prefix_end, why,
                                              entry=row.chars, contentsNumber=n,
                                              engineA=number[0] if number else None))
            continue
        mark = number[1]
        held = re.match(rf"\s*{n}\s*(?P<mark>[.．,，、。])", prefix)
        if not mark and held:
            # Engine A read the figure and no mark after it; the page's mark
            # there stays (a mark is no stand-in).
            mark = held.group("mark")
        want = f"{n}{mark} "
        numbered.append((row, mark.replace("．", "."), text[:prefix_start] + want + text[prefix_end:], prefix_start,
                         prefix_start + len(want)))
        if prefix == want:
            continue
        pks = reading.chars_in(prefix_start, prefix_end)
        read = [reading.s.chars[k] for k in pks if reading.a_index(k) is not None]
        if read or len(pks) > PREFIX_CHARACTERS:
            plan.questions.append(question_at(
                "Q-P", unit.page, "S4", text, prefix_start, prefix_end,
                f"engine A read the number {n} before this unit's title, and the page holds {prefix!r} there"
                + (f", of which engine A read {''.join(read)}" if read else ""), entry=row.chars,
                contentsNumber=n))
            continue
        plan.edits.append(re_.Edit(unit.page, prefix_start, prefix_end, want, rule="S4", evidence={
            "entry": row.chars, "contentsNumber": n, "engineA": f"{number[0]}{number[1]}",
            "replaced": prefix, "numberSources": sorted(row.numbers)}))
    for i, (row, mark, page, start, end) in enumerate(numbered):
        if mark:
            continue
        before = next((m for other, m, *_ in reversed(numbered[:i]) if other.group == row.group), None)
        after = next((m for other, m, *_ in numbered[i + 1:] if other.group == row.group), None)
        if not before or not after:
            continue
        style = {"numberStyle": before} if before == after and before not in COLON_LIKE else {}
        plan.questions.append(question_at(
            "Q-P", row.unit.page, "S4", page, start, end,
            f"unit {row.number} is written without a mark after its number, where the units on either side of "
            f"it carry {before!r} and {after!r}", entry=row.chars, contentsNumber=row.number, **style))


def other_reading(reading: PageReading, k: int, engine: str) -> str | None:
    """What ENGINE read in place of sealed character K where it disagrees:
    the one character between the engine's readings of K's neighbours."""
    to = reading.align.sealed_to_a if engine == "a" else reading.align.sealed_to_b
    stream = reading.align.a if engine == "a" else reading.align.b
    if k <= 0 or k + 1 >= len(to) or to[k] is not None:
        return None
    before, after = to[k - 1], to[k + 1]
    if before is None or after is None or after != before + 2:
        return None
    return stream.chars[before + 1]


def s16(reading: PageReading, row: Row, ks: Sequence[int], plan: rr.Plan) -> None:
    unit = row.unit
    title = [reading.s.chars[k] for k in ks[unit.start:unit.end]]
    entry = row.chars
    matcher = difflib.SequenceMatcher(None, folded("".join(title)), folded(entry), autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "replace" or i2 - i1 != 1 or j2 - j1 != 1:
            continue
        k = ks[unit.start + i1]
        a_same, b_same = reading.a_index(k) is not None, reading.b_index(k) is not None
        if a_same == b_same:
            continue
        other = other_reading(reading, k, "b" if a_same else "a")
        want = entry[j1]
        if other is None or folded(other) != folded(want) or folded(other) == folded(title[i1]):
            continue
        offset = reading.s.offsets[k]
        plan.edits.append(re_.Edit(unit.page, offset, offset + 1, other, rule="S16", evidence={
            "entry": entry, "page": title[i1], "engineA": title[i1] if a_same else other,
            "engineB": other if a_same else title[i1], "contents": want}))


def s7(setting: Setting, contents: Contents, plan: rr.Plan) -> None:
    """S7 on each unit heading."""
    for row in contents.entries():
        unit = row.unit
        if unit is None or not unit.heading or unit.page not in setting.order:
            continue
        reading, line, ks = unit_line(setting, row)
        if unit.end > len(ks) or unit.end < 1:
            continue
        split_date(setting, reading, line, reading.s.offsets[ks[unit.end - 1]] + 1, "S7", plan,
                   {"entry": row.chars})


def split_date(setting: Setting, reading: PageReading, line: rr.Line, after: int, rule: str, plan: rr.Plan,
               evidence: Mapping[str, Any]) -> bool:
    """A date after offset AFTER on LINE, with at most a place clause after
    it, to its own paragraph (S7).  Whether an edit was proposed."""
    text = reading.text
    found = find_date(text[:line.end], after)
    if not found or len(pp.CJK(text[found[1]:line.end])) > PLACE_CLAUSE:
        return False
    # A figure just before the date's numerals ends what the date follows
    # (an ordinal 之2): no date opens with one.
    start, end = break_span(text, found[0], after, figures=False)
    if start == end and start == after and text[after - 1:after].isspace():
        return False
    # Marks between the title and the date that neither engine read there
    # (the punctuator's comma before a date set apart in smaller type) go
    # with the split: left, they would end the heading.
    dropped = unread_marks_before(reading, after, start)
    if dropped:
        start = after
    plan.edits.append(re_.Edit(reading.pd.scan, start, end, "\n\n", rule=rule, evidence={
        **evidence, "date": text[found[0]:found[1]], "moved": text[found[0]:line.end],
        **({"dropped": dropped} if dropped else {})}))
    return True


def unread_marks_before(reading: PageReading, lo: int, hi: int) -> str:
    """The marks the page holds in TEXT[lo:hi] (between a title's last
    character and a date after it), when that is only marks and white space
    and neither engine read any of them between the two characters: they
    are adjacent in engine A, with none of those marks between, and in
    engine B, with no mark between (engine B's stand-in glyph for a mark is
    a character of its own: adjacent, it read none); else ''."""
    text = reading.text
    held = text[lo:hi]
    if not held.strip() or pp.CJK(held) or any(c.isalnum() for c in held):
        return ""
    ks = reading.chars_in(0, lo)
    k_after = bisect.bisect_left(reading.s.offsets, hi)
    if not ks or k_after >= len(reading.s.chars):
        return ""
    before, following = reading.a_index(ks[-1]), reading.a_index(k_after)
    if before is None or following is None or following != before + 1:
        return ""
    read = rr.marks_of(reading.align.a.gaps[following])
    marks = rr.marks_of(held)
    b_before, b_following = reading.b_index(ks[-1]), reading.b_index(k_after)
    if b_before is None or b_following is None or b_following != b_before + 1 \
            or rr.marks_of(reading.align.b.gaps[b_following]):
        return ""
    return marks if not any(c in read for c in marks) else ""


def entry_line(reading: PageReading, row: Row, line: rr.Line) -> tuple[str, list[dict[str, Any]]]:
    """S11: a contents entry's line as rebuilt, and what it leaves open."""
    text = line.text
    match = ENTRY_LEAD.match(text)
    ks = reading.chars_in(line.start, line.end)
    if not ks:
        return text, []
    title_at = reading.s.offsets[ks[0]] - line.start
    lead_end = match.end() if match else 0
    if lead_end > title_at:
        lead_end = title_at
    stray = text[lead_end:title_at]
    body = text[title_at:]
    trail = ENTRY_TRAIL.search(body)
    moved = None
    if trail and "pageAfter" in row.numbers and row.number == row.numbers["pageAfter"][0]:
        moved = trail.group("digits")
        body = body[:trail.start()]
    body = body.rstrip()
    a_gap = ""
    j = reading.a_index(ks[0])
    if j is not None:
        a_gap = reading.align.a.gaps[j]
    # What engine A read before the title besides its figure and the mark
    # after it (those are the number, written apart).
    figure = GAP_FIGURE.search(a_gap)
    a_lead = a_gap[:figure.start()] if figure else a_gap
    kept = "".join(c for c in stray if not c.isspace() and not c.isdigit() and c in a_lead)
    dropped = "".join(c for c in stray if not c.isspace() and not c.isdigit() and c not in a_lead)
    closers = {"“": "”", "「": "」", "『": "』", "‘": "’"}
    for opener in dropped:
        closer = closers.get(opener)
        if closer and body.endswith(closer):
            jl = reading.a_index(ks[-1])
            after_gap = reading.align.a.gaps[jl + 1] if jl is not None and jl + 1 < len(reading.align.a.gaps) else ""
            if closer not in after_gap:
                body = body[:-1]
    open_items = []
    number = row.number
    sources = [name for name, (value, _) in row.numbers.items() if value == number] if number is not None else []
    if number is None or not sources:
        if number is not None:
            open_items.append({"why": f"no source read the number of entry {number} ({row.chars})"})
        # No number is written: what the page holds before the title that
        # an engine read there, its figures too, stays.
        kept = "".join(c for c in stray if not c.isspace() and (c.isdigit() or c in a_gap))
        return kept + body, open_items
    # The mark after the number: engine A's, else the page's own, else
    # engine B's - a figure read without its mark does not take the page's
    # mark away.
    mark = next((row.numbers[name][1] for name in ("engineA", "page", "engineB", "pageAfter")
                 if name in sources and row.numbers[name][1]), "")
    mark = mark.replace("．", ".")
    return f"{number}{mark} {kept}{body}", open_items


def s11(setting: Setting, contents: Contents, plan: rr.Plan) -> dict[int, str]:
    """S11: the contents pages rebuilt (the module's docstring).  Returns the
    rebuilt texts of the pages it changed, for the questions."""
    level = contents.unit_level
    rebuilt: dict[int, str] = {}
    marks_by_group: dict[int, list[tuple[Row, str]]] = {}
    for scan in contents.pages:
        if scan not in setting.order:
            continue
        reading = setting.reading(scan)
        text = reading.text
        lines = line_spans(text)
        rows = sorted((r for r in contents.rows if r.page == scan), key=lambda r: r.line)
        new_text = {}
        pending: list[dict[str, Any]] = []
        for row in rows:
            line = lines[row.line - 1]
            body = ENTRY_LEAD.match(line.text)
            core = line.text[body.end("markup"):].strip() if body else line.text.strip()
            if row.kind == "title":
                new = "#" * 2 + " " + core
            elif row.kind == "group":
                ks = reading.chars_in(line.start, line.end)
                cut = reading.s.offsets[ks[len(row.suffix) - 1]] + 1 - line.start if len(ks) >= len(row.suffix) else 0
                head = line.text[body.end("markup") if body else 0:cut].strip()
                rest = line.text[cut:].strip()
                new = "#" * level + " " + head + (" " + rest if rest else "")
            else:
                new, open_items = entry_line(reading, row, line)
                for item in open_items:
                    pending.append({"row": row, **item})
                marks_by_group.setdefault(row.group, []).append((row, new))
            new_text[row.line] = new
            if new != line.text:
                plan.edits.append(re_.Edit(scan, line.start, line.end, new, rule="S11", evidence={
                    "kind": row.kind, "numbers": {k: f"{v}{m}" for k, (v, m) in row.numbers.items()},
                    "number": row.number, "place": row.place}))
        for one, two in zip(rows, rows[1:]):
            a, b = lines[one.line - 1], lines[two.line - 1]
            between = text[a.end:b.start]
            if between.strip():
                continue
            tight = bool(LIST_ITEM.match(new_text[one.line]) and LIST_ITEM.match(new_text[two.line]))
            want = "\n" if tight else "\n\n"
            if between != want:
                plan.edits.append(re_.Edit(scan, a.end, b.start, want, rule="S11", evidence={
                    "between": "list items" if tight else "entries"}))
        # The page as rebuilt, for the questions' sites.
        page = "\n".join(new_text.get(line.number, line.text) for line in lines)
        rebuilt[scan] = page
        for item in pending:
            row = item["row"]
            where = page.split("\n")
            offset = sum(len(x) + 1 for x in where[:row.line - 1])
            plan.questions.append(question_at("Q-P", scan, "S11", page, offset, offset, item["why"],
                                              entry=row.chars, contentsNumber=row.number, group=row.group))
    # The mark the numbers of each group carry, where every entry of it
    # written with a number carries the same one (two at least): the book's
    # own numbering, by which an answer reads a colon-like mark after a
    # number (a full stop with a speck above it; decide_print).
    styles: dict[int, str] = {}
    for group, items in marks_by_group.items():
        found = [m.group(2) for m in (re.match(r"(\d{1,3})([^\s\d]?) ", new) for _, new in items) if m]
        marks = {x for x in found if x}
        if len(marks) == 1 and sum(1 for x in found if x) >= 2 and not marks & COLON_LIKE:
            styles[group] = next(iter(marks))
    for q in plan.questions:
        if q.get("rule") == "S11" and q.get("group") in styles:
            q["numberStyle"] = styles[q["group"]]
    # A number written without the mark the entries on either side carry.
    for group, items in marks_by_group.items():
        written = [(row, re.match(r"(\d{1,3})([^\s\d]?) ", new)) for row, new in items]
        for i, (row, match) in enumerate(written):
            if not match or match.group(2):
                continue
            before = next((m.group(2) for _, m in reversed(written[:i]) if m), None)
            after = next((m.group(2) for _, m in written[i + 1:] if m), None)
            around = [x for x in (before, after) if x is not None]
            if len(around) == 2 and around[0] and around[0] == around[1] and row.page in rebuilt:
                page = rebuilt[row.page]
                offset = sum(len(x) + 1 for x in page.split("\n")[:row.line - 1])
                style = {"numberStyle": around[0]} if around[0] not in COLON_LIKE else {}
                plan.questions.append(question_at(
                    "Q-P", row.page, "S11", page, offset, offset + len(match.group(0)),
                    f"entry {row.number} is read without the {around[0]!r} its neighbours carry",
                    entry=row.chars, contentsNumber=row.number, group=row.group, **style))
    return rebuilt


def contents_stage(book: Any, model: Mapping[str, Any], texts: Mapping[int, str], order: Sequence[int],
                   apply: Callable[[Sequence[re_.Edit]], None], facts: rr.BookFacts | None = None,
                   readings: Readings | None = None) -> rr.Plan:
    """The contents stage over the pages ORDER, in passes applied through
    APPLY: S9; S4 and S16; S7; S11.  Returns the last pass's edits, every
    question, the gate's doubt and the `unit-not-in-scan` doubts."""
    facts = facts or rr.book_facts(book, model)
    setting = Setting(book, model, facts, readings or Readings(book, model), list(order), texts)
    plan = rr.Plan()
    contents = setting.contents()
    if contents is None:
        return plan
    if not contents.numbering.get("passed"):
        plan.doubts.append(("gate-failed", None, "contents-numbering: the contents' numbers read are not their "
                            "places in their groups, so no entry's number is taken from its place",
                            {"gate": "contents-numbering", "measured": contents.numbering}))
    # The unit titles S9 is to make headings: the headings stage's S6 saw
    # the others, and asked what it could not settle there.
    promoted = {(row.page, row.line) for row in contents.entries() if row.unit and not row.unit.heading}

    def s6_units(setting: Setting, contents: Contents, plan: rr.Plan) -> None:
        new = {}
        for row in contents.entries():
            if row.unit and row.unit.page in order and (row.page, row.line) in promoted:
                new.setdefault(row.unit.page, set()).add(row.unit.line)
        for scan in sorted({row.unit.page for row in contents.entries() if row.unit and row.unit.page in order}):
            step = rr.Plan()
            s6(setting, scan, step)
            plan.edits.extend(step.edits)
            plan.questions.extend(q for q in step.questions if q["site"]["line"] in new.get(scan, ()))

    for passes in (s9, s6_units, s4_s16, s7):
        step = rr.Plan()
        passes(setting, contents, step)
        plan.questions.extend(step.questions)
        apply(step.edits)
        contents = setting.contents()
    s11(setting, contents, plan)
    for row in contents.entries():
        if row.unit is None and row.page in order:
            plan.doubts.append(("unit-not-in-scan", row.page,
                                f"contents entry {row.number or row.place} of group {row.group + 1} ({row.chars}) has "
                                "no unit in the body", {"entry": row.chars, "line": row.line,
                                                        "number": row.number, "group": row.group + 1}))
    return plan


# --- the title page ----------------------------------------------------------------

def reversed_lines(reading: PageReading) -> tuple[str, list[dict[str, Any]]] | None:
    """S13's test: which engine read the page's lines backwards - one of its
    lines (REVERSE_MINIMUM characters or more) is the exact reverse of a run
    the other engine read, and the other engine never read it that way round
    - and the pairs found.  None when neither did."""
    a_lines = [line for block in reading.pd.a_blocks for line in block["text"].split("\n")]
    # Engine B's whole reading, its head copies too: a title page prints the
    # book's title, which is the running head's stem.
    b_lines = reading.pd.b_text.split("\n")
    a_all, b_all = folded(pp.CJK(reading.pd.a_body)), folded(pp.CJK(reading.pd.b_text))
    for engine, lines, other in (("a", a_lines, b_all), ("b", b_lines, a_all)):
        pairs = []
        for line in lines:
            chars = folded(pp.CJK(line))
            if len(chars) >= REVERSE_MINIMUM and chars[::-1] in other and chars not in other:
                pairs.append({"read": pp.CJK(line), "otherEngine": pp.CJK(line)[::-1]})
        if pairs:
            return engine, pairs
    return None


def title_page(setting: Setting, scan: int, plan: rr.Plan) -> None:
    """S13 on one page (the module's docstring)."""
    reading = setting.reading(scan)
    found = reversed_lines(reading)
    if not found or found[0] != "a" or not reading.pd.a_blocks:
        return
    text = reading.text
    mixed = mixed_directions(setting, scan, reading)
    if mixed:
        # One line read backwards does not make every line of the page one.
        plan.questions.append(question_at("Q-L", scan, "S13", text, 0, len(text.rstrip()),
                                          f"engine A read a line of this page backwards, but {mixed}: copy its "
                                          "lines", pairs=found[1]))
        return
    sealed = folded(pp.CJK(text))
    b_chars = pp.CJK(reading.pd.b_text)
    b_folded = folded(b_chars)
    lines = []
    for block in reading.pd.a_blocks:
        for raw in block["text"].split("\n"):
            chars = pp.CJK(raw)
            if not chars:
                continue
            key = folded(chars)
            where = sealed.find(key)
            if where >= 0:
                # The page holds the line as engine A read it: its own
                # characters, read the other way.
                source = "page"
                cjk = pp.CJK(text)
                forward = cjk[where:where + len(chars)][::-1]
            elif b_folded.find(key[::-1]) >= 0:
                at = b_folded.find(key[::-1])
                source = "engineB"
                forward = b_chars[at:at + len(chars)]
            else:
                source = "engineA"
                forward = chars[::-1]
            heading = block.get("label") in rm.TITLE_LABELS
            lines.append({"text": ("# " if heading else "") + forward, "source": source, "read": raw,
                          "heading": heading})
    if not lines:
        return
    new = "\n\n".join(line["text"] for line in lines) + ("\n" if text.endswith("\n") else "")
    before, after = printed_counts(text), printed_counts(new)
    if before - after:
        # Something the page holds is in no line engine A read (a character,
        # a figure, a mark: the rebuilt lines hold characters only): not
        # rebuilt.
        plan.questions.append(question_at("Q-L", scan, "S13", text, 0, len(text.rstrip()),
                                          "the page reads right to left, but it holds text no line of engine A "
                                          "holds: copy its lines", pairs=found[1]))
        return
    if new == text:
        return
    plan.edits.append(re_.Edit(scan, 0, len(text), new, rule="S13", evidence={
        "reversedEngine": "engineA", "pairs": found[1], "lines": [{k: v for k, v in line.items() if k != "heading"}
                                                                   for line in lines]}))
    at = 0
    for line in lines:
        start = new.find(line["text"], at)
        at = start + len(line["text"])
        plan.questions.append(question_at("Q-L", scan, "S13", new, start, at,
                                          "a line of a page printed right to left, rebuilt from the engines' "
                                          "readings: copy its glyphs", source=line["source"], aLine=line["read"]))


def printed_counts(text: str) -> Counter:
    """Everything TEXT prints, folded: its characters but white space and
    the Markdown heading marker."""
    return Counter(c for c in folded(text) if not c.isspace() and c != "#")


def mixed_directions(setting: Setting, scan: int, reading: PageReading) -> str | None:
    """Why S13 may not read every line of page SCAN backwards, or None: each
    of engine A's blocks of two characters or more lies across the page (a
    horizontal line: a column read backwards is no mirror of a line), and no
    line of engine A's (REVERSE_MINIMUM characters or more) is one engine B
    read the same way round."""
    size = rm.page_size(setting.book.pages[scan])
    if not size:
        return "the page's size is not known (which of its blocks are lines)"
    width, height = size
    b_all = folded(pp.CJK(reading.pd.b_text))
    for block in reading.pd.a_blocks:
        chars = pp.CJK(block.get("text") or "")
        box = block.get("box")
        if len(chars) >= 2 and (not box or box[2] * width <= box[3] * height):
            return f"engine A read {chars[:12]!r} as a column"
        for raw in (block.get("text") or "").split("\n"):
            key = folded(pp.CJK(raw))
            if len(key) >= REVERSE_MINIMUM and key in b_all and key[::-1] not in b_all:
                return f"engine B read {pp.CJK(raw)[:12]!r} the same way round as engine A"
    return None


def title_pages(book: Any, model: Mapping[str, Any], texts: Mapping[int, str], order: Sequence[int],
                facts: rr.BookFacts | None = None, readings: Readings | None = None) -> rr.Plan:
    """The title-page stage over the pages ORDER."""
    facts = facts or rr.book_facts(book, model)
    setting = Setting(book, model, facts, readings or Readings(book, model), list(order), texts)
    plan = rr.Plan()
    for scan in order:
        title_page(setting, scan, plan)
    return plan


# --- levels ---------------------------------------------------------------------------

def own_block(reading: PageReading, line: rr.Line) -> tuple[str, dict[str, Any]]:
    """What engine A shows of a heading line: `own` (a block of its own, a
    title block or display type), `run-in` (the start of a longer block), or
    `none` (engine A did not read it)."""
    ks = reading.chars_in(line.start, line.end)
    blocks = [reading.block(k) for k in ks if reading.block(k) is not None]
    core = folded(pp.CJK(heading_body(line.text)))
    if not blocks and core:
        # Nothing aligned (a line the page holds the other way round from
        # engine A's reading, S13): the block holding its characters either way.
        blocks = [b for b, block in enumerate(reading.pd.a_blocks)
                  if folded(pp.CJK(block["text"])) in (core, core[::-1])][:1]
    if not blocks:
        return "none", {}
    b = blocks[0]
    block = reading.pd.a_blocks[b] if b < len(reading.pd.a_blocks) else {}
    block_core = folded(pp.CJK(block.get("text") or ""))
    evidence = {"label": block.get("label"), "block": block_core[:24]}
    if block.get("label") in rm.TITLE_LABELS:
        return "own", evidence
    if len(block_core) <= len(core) + 2 and difflib.SequenceMatcher(None, core, block_core).ratio() >= TITLE_SIMILARITY:
        return "own", evidence
    return "run-in", evidence


def heading_kinds(setting: Setting, contents: Contents) -> list[dict[str, Any]]:
    """Every heading of the book (marker pages in order) with its kind and
    the level the scheme gives it (None: no heading)."""
    texts = all_texts(setting.book, setting.texts)
    dividers = {d["page"]: d.get("suffix") for d in setting.model.get("dividers") or []}
    first_contents = min(contents.pages)
    unit_level = contents.unit_level
    rows_at = {(r.page, r.line): r for r in contents.rows}
    out = []
    in_unit = False
    after_unit = False
    seen_heading = False
    for scan in sorted(texts):
        text = texts[scan]
        reading = setting.readings.get(scan, text)
        units = contents.units_on(scan)
        for line in line_spans(text):
            body = line.text.strip()
            if not body:
                continue
            match = heading_of(line.text)
            if not match:
                if not is_date_line(line.text):
                    after_unit = False
                continue
            core = pp.CJK(heading_body(line.text))
            kind, level, why = "unknown", None, {}
            row = rows_at.get((scan, line.number))
            if scan in contents.pages:
                if row is not None and row.kind == "title":
                    kind, level = "contents-title", 2
                elif row is not None and row.kind == "group":
                    kind, level = "contents-group", unit_level
            elif scan < first_contents:
                show, why = own_block(reading, line)
                if not seen_heading and (why.get("label") in rm.TITLE_LABELS):
                    kind, level = "book-title", 1
            elif scan in dividers and dividers[scan] and rm.levenshtein(core, dividers[scan]) <= 1:
                kind, level = "division", 2
                in_unit = False
            elif line.number in units:
                kind, level = "unit", unit_level
                in_unit = after_unit = True
                why = {"entry": units[line.number].chars}
            elif is_date_line(line.text):
                kind = "date"
            elif after_unit and not ENUMERATOR.match(heading_body(line.text).strip()):
                kind = "occasion"
            elif in_unit:
                show, why = own_block(reading, line)
                lead = ENUMERATOR.match(heading_body(line.text).strip())
                words = pp.CJK(heading_body(line.text).strip()[lead.end():] if lead else heading_body(line.text))
                # A heading of its own holds words beyond its enumerator: a
                # numeral alone (in a number block) opens what follows it.
                if show == "own" and words and why.get("label") != "number":
                    kind, level = "in-unit", unit_level + 1
                elif show == "run-in":
                    kind = "run-in"
            seen_heading = True
            if kind not in ("unit", "date", "occasion"):
                after_unit = kind == "unit"
            out.append({"page": scan, "line": line.number, "text": line.text, "kind": kind, "level": level,
                        "current": len(match.group("marks")), "why": why})
    return out


def levels(book: Any, model: Mapping[str, Any], texts: Mapping[int, str], order: Sequence[int],
           facts: rr.BookFacts | None = None, readings: Readings | None = None) -> rr.Plan:
    """The levels stage over the pages ORDER (the module's docstring)."""
    facts = facts or rr.book_facts(book, model)
    setting = Setting(book, model, facts, readings or Readings(book, model), list(order), texts)
    plan = rr.Plan()
    contents = setting.contents()
    if contents is None:
        return plan
    for item in heading_kinds(setting, contents):
        scan = item["page"]
        if scan not in setting.order:
            continue
        reading = setting.reading(scan)
        line = line_spans(reading.text)[item["line"] - 1]
        match = heading_of(line.text)
        kind = item["kind"]
        evidence = {"kind": kind, **item["why"]}
        if kind in ("occasion", "date"):
            plan.edits.append(re_.Edit(scan, line.start, line.start + match.end(), "",
                                       rule="S12" if kind == "occasion" else "S5", evidence=evidence))
            if kind == "occasion":
                body_at = line.start + match.end()
                first = next((i for i, c in enumerate(line.text[match.end():]) if pp.CJK(c)), None)
                if first is not None:
                    split_date(setting, reading, line, body_at + first + 1, "S12", plan, {"occasion": line.text})
            continue
        if item["level"] is None:
            if kind == "run-in":
                plan.questions.append(question_at(
                    "Q-Y", scan, "S5", reading.text, line.start, line.end,
                    "engine A read this heading as the start of a longer block: a heading, or a paragraph's "
                    "run-in lead?", **{k: v for k, v in item["why"].items() if k in ("label", "block")}))
            else:
                plan.doubts.append(("heading-kind-unknown", scan, f"no rule places the heading {line.text[:40]!r}; "
                                    "its level is left as it is", {"line": item["line"], "heading": line.text}))
            continue
        if item["current"] != item["level"]:
            plan.edits.append(re_.Edit(scan, line.start + len(match.group("indent")),
                                       line.start + len(match.group("indent")) + item["current"],
                                       "#" * item["level"], rule="S5", evidence={**evidence,
                                                                                "from": item["current"]}))
    return plan
