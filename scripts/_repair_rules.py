"""The book repair tool's mechanical rules (scripts/repair_book.py): per page,
running heads and folios (furniture, F1-F7), engine B's stand-ins, marks and
brackets (K1-K13, K-seq), and the blank line around a heading (P5).

Each rule is a detector over one page that proposes offset edits
(_repair_edits.Edit) with the rule's name and its evidence, and each acts
only on what the book model (_repair_model.py) measured on this book: a rule
whose gate failed stays silent.  A site a rule finds but cannot settle - its
evidence falls short, or two sources disagree - becomes a planned question
(questions.json; the question stage asks it, --no-model makes it a
`look-not-asked` doubt), never a guess.

What each rule may delete (the conservation the design asks for): furniture
(F: characters the band holds, or an adjudicator's answer at a band spot
where neither engine read body text); a glyph engine B writes for a mark or
a figure that engine A did not read (K); a duplicate engine A read once (K5).
What each may write: what engine A read at that place (its figure, dash,
dot, quote or bracket), the ordinary form of a vertical bracket, or a blank
line (P5).

Furniture (stage `furniture`), in the order evaluated:
- F6 answer at a band spot: a phase-3 adjudication (resolved by the
  adjudicator, engine A's default or moved-kept-once) with a context in the
  band, where engine A read nothing, band text or folio figures and engine
  B read nothing, folio figures, its own head span or a run suffix: neither
  engine read body text there, so the answer is not the page's.  Located by
  the body context on its other side.  An answer an engine read too (the
  adjudicator confirmed it) goes only when that reading is the band as a
  whole - a suffix, the whole folio, a whole head - not a piece of the folio
  or one character of the head.  An answer that is a folio figure where
  engine A read a body character, or where an engine read it as only a piece
  of the folio, is a question (Q-G), not an edit.
- whole lines: F1 a running head (at most one stray numeral, a stem copy,
  optionally a run suffix, optionally folio figures); F2 the page's own run
  suffix alone, on a page that is not a divider or a contents page; F3 the
  contents word alone on a contents page after the first.  A line engine A
  read in its body (outside the band) - as a line of its own, or most of its
  characters inside a block with the text around it - is printed and is
  kept.
- at the page's leading and trailing edge (after the lines above are gone):
  F4 a numeral-only line that is the folio or a piece of it - by the folio
  sequence or engine A's folio block - and that an engine read in the band
  (and engine A not in its body);
  F7 a line made only of F6 answers and characters of engine A's band.
- inline: F5 what the page holds where engine B read its running head,
  anchored by the body characters B read on either side, when it is only
  head, suffix, folio, misread and F6 characters and holds a stem's core (or
  is the page's own suffix) - where engine B read the head at an end of its
  reading (a stem copy with body it read on both sides is a mention or a
  title; a question when engine A did not read it in its body), and, where
  engine A read the run in its body, as the band glued to a text block (with
  the suffix or folio beside the stem, not in a title); F2b the page's own
  suffix opening the first
  line where both engines start the body after it; F2c the page's own
  suffix ending a line just before an F1 line (the label only; the marks
  around it are a question) - each only when the page's kept lines hold
  more copies of the suffix than an engine read in its body.
The first contents page and the dividers are exempt from F2, F5 and F6.
- F8, on the page as the edits above leave it: one or two characters both
  engines read at the page's head or foot, beyond the first (last)
  character they share with it, that are not the band's, numerals or
  stand-ins, where the page holds none (the two may read them as different
  glyphs) - a body character that went out with an answer at the band - is
  a glyph question (Q-G) at the page's edge, cut from the page's first
  (last) measured column, the engines' readings its candidates.

Marks (stage `marks`), between two characters the page and engine A share
and that are adjacent in engine A, on characters engine A did not read:
- K1 engine A read a bracketed figure (d): the page holds at most four
  stand-ins or a `）（`/`（）` pair there -> `（d）` with engine A's marks.
  Each stand-in must stand for what engine A read there (the figure, or a
  mark, dash or dot of its gap); one that does not is a question.
- K1 and K2 take a CJK numeral for engine B's reading of engine A's figure
  only on a book where engine B was seen to write numerals for engine A's
  figures (M-7b); elsewhere the numeral is no stand-in.
- K2 engine A's line opens with a figure: the page's heading, item or line
  opens with one to three stand-ins or CJK numerals (or only a stray mark) ->
  the figure (`d`, `d.`, or `（d）` where B read a bracket's glyphs round it).
- K3 one or two stand-ins where engine A read a dash and no character, and
  engine B read no character but stand-ins there -> `——` (`—` for one cell).
- K4 a dot stand-in (M-7d): deleted where engine A's marks there (its dot
  among them) are all written (K4a); else where engine A read a dot, the dot
  `·` (K4b).
- K5 a mark-alias glyph engine A did not read beside the same glyph engine A
  read, only marks between -> one glyph with engine A's marks; a question
  when no mark it stands for is beside it, or engine B read the glyph more
  often than once plus those marks (a doubled character).
- K6 a stand-in engine A never reads anywhere in the book, where engine A
  read a character at the same aligned place -> engine A's character.
- K7a/K7b a lone quote-alias glyph beside a quote or bracket already written
  (K7a), or where engine A read a quote the page lacks (K7b), when the seal
  shows it came in through an engine-B-only decision -> deleted, engine A's
  marks written.
- K8 `（X、）` where engine A read `（X）` -> `（X）`; K9 `︵︶` -> `（）`; K10 a
  `[` opening a line before a figure, unclosed, that engine A did not read ->
  deleted.
- second pass, on the text the first leaves: K12 a closing bracket or quote
  engine A read that the page lacks, when the page (page turn aware) is
  short of exactly one -> inserted; K13 brackets where engine A read corner
  quotes at the same gaps, all other marks equal, no bracket read by either
  engine -> engine A's quotes, a bracket together with its partner on the
  page (one whose partner does not qualify is a question).
- K14, last: each stand-in glyph the page still holds where engine A read
  no character (what no rule settled; the MARK-STANDIN counter's sites) is
  a print question over the gap between the nearest characters the page
  and engine A share - bounded: at most STANDIN_RUN characters engine A
  did not read in the gap, at most one character engine A read there, no
  edit of the second pass touched, not a heading or list line of stand-ins
  alone.  Its answer passes the print questions' guards (G5: no character
  no engine read there).
- K-seq: a figure K1 or K2 writes must continue its list (the previous
  figure of its kind is one less, or it is 1); one that does not is a
  question (Q-P), not an edit; on a contents page one read without the dot
  the figures beside it carry asks with that dot as its list's mark (a
  colon-like mark in the answer is read as it).  Where the page holds the
  figure's value in CJK numerals and nothing else (the print read in the
  other script), 1 and that agreement settle nothing: the figures around
  it or the contents do.

Spacing (stage `paragraphs`): P5 a blank line before and after an ATX
heading - unless the heading and the next line are one block of engine A's
(a heading printed over two lines, which the heading stage joins).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import bisect
import math
import re
from typing import Any, Iterable, Mapping, Sequence

import proofread_pages as pp
import _book_lint as lint
import _repair_align as ra
import _repair_edits as re_
import _repair_model as rm


# --- common ----------------------------------------------------------------

@dataclass
class Plan:
    """What a rule family proposes: edits, planned questions and doubts
    (kind, page, detail, fields)."""
    edits: list[re_.Edit] = field(default_factory=list)
    questions: list[dict[str, Any]] = field(default_factory=list)
    doubts: list[tuple[str, int | None, str, dict[str, Any]]] = field(default_factory=list)


@dataclass
class Line:
    number: int  # 1-based
    start: int
    end: int     # the line's end, its newline excluded
    text: str


def lines_of(text: str) -> list[Line]:
    out = []
    at = 0
    for number, line in enumerate(text.split("\n"), 1):
        out.append(Line(number, at, at + len(line), line))
        at += len(line) + 1
    return out


NUMERALS = rm.NUMERALS
ZERO_READS = "口"  # a folio's zero, read as a square
QUOTES = frozenset("「」『』")
BRACKET_MARKS = frozenset("（）")
PAIRED = QUOTES | BRACKET_MARKS
NORM = str.maketrans({"(": "（", ")": "）", "︵": "（", "︶": "）", ",": "，", ";": "；", "?": "？", "!": "！",
                      ":": "："})
DOT = "·"
DOT_READS = frozenset("·•・")
DASH_RUN = re.compile("[" + re.escape("".join(sorted(ra.DASH_CHARS))) + "]+")


def marks_of(text: str) -> str:
    """TEXT's marks: every character but white space, brackets in their
    ordinary full-width form."""
    return "".join(c for c in text.translate(NORM) if not c.isspace())


def subsequence(small: str, big: str) -> bool:
    it = iter(big)
    return all(c in it for c in small)


def common_run(a: str, b: str) -> int:
    """The longest run of characters A and B share."""
    best = 0
    for i in range(len(a)):
        for j in range(len(b)):
            k = 0
            while i + k < len(a) and j + k < len(b) and a[i + k] == b[j + k]:
                k += 1
            best = max(best, k)
    return best


def lcs(a: str, b: str) -> int:
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b, 1):
            cur.append(prev[j - 1] + 1 if x == y else max(prev[j], cur[j - 1]))
        prev = cur
    return prev[-1]


def question(kind: str, page: int, rule: str, text: str, start: int, end: int, why: str,
             **fields: Any) -> dict[str, Any]:
    """A planned question about TEXT[start:end] of PAGE (the text as the
    stage saw it): the site's text and the characters on either side, so a
    later stage finds it again after other edits."""
    before = pp.CJK(text[:start])[-8:]
    after = pp.CJK(text[end:])[:8]
    return {"kind": kind, "page": page, "rule": rule, "status": "planned", "why": why,
            "site": {"line": text.count("\n", 0, start) + 1, "start": start, "end": end,
                     "text": text[start:end], "before": before, "after": after}, **fields}


@dataclass
class BookFacts:
    """What the rules read of the book model, and the book-wide counts."""
    gates: dict[str, bool]
    stems: list[str]
    suffixes: list[str]
    contents_word: str | None
    contents_first: set[int]
    dividers: set[int]
    misread_chars: set[str]
    aliases: dict[str, dict[str, int]]
    figure: set[str]
    dash: set[str]
    dot: set[str]
    numeral_figures: bool
    a_counts: Counter

    def standins(self) -> set[str]:
        return set(self.aliases) | self.figure | self.dash | self.dot

    def aliases_of(self, marks: Iterable[str]) -> set[str]:
        """The glyphs engine B writes for any of MARKS."""
        wanted = set(marks)
        return {g for g, found in self.aliases.items() if wanted & set(found)}


def book_facts(book: Any, model: Mapping[str, Any]) -> BookFacts:
    gates = {name: bool(g.get("passed")) for name, g in (model.get("gates") or {}).items()}
    s = model.get("standIns") or {}
    contents_first = set()
    word = None
    for run in (model.get("contents") or {}).get("runs") or []:
        if run.get("pages"):
            contents_first.add(min(run["pages"]))
        word = word or run.get("contentsWord")
    misreads = set()
    for found in (model.get("stemMisreads") or {}).values():
        misreads.update(found)
    a_counts: Counter = Counter()
    for scan in sorted(book.pages):
        page = book.pages[scan]
        entry = rm.page_entry(model, scan)
        a_body, _ = rm.body_streams(page, entry.get("band") or [], [])
        a_counts.update(pp.CJK(a_body))
    return BookFacts(
        gates=gates,
        stems=list(model.get("stems") or []) if gates.get("M-2") else [],
        suffixes=sorted({r["suffix"] for r in model.get("suffixRuns") or []}) if gates.get("M-3") else [],
        contents_word=word if gates.get("M-3") and gates.get("M-6") else None,
        contents_first=contents_first,
        dividers={d["page"] for d in model.get("dividers") or []},
        misread_chars=misreads,
        aliases={g: dict(m) for g, m in ((s.get("markAliases") or {}).get("B") or {}).items()},
        figure=set(s.get("figure") or []),
        dash=set(s.get("dash") or []),
        dot=set(s.get("dot") or []),
        numeral_figures=bool(s.get("numeralsAtFigures")),
        a_counts=a_counts,
    )


@dataclass
class PageData:
    """One page as a rule reads it: the text under repair, the model's entry,
    the seal's records and both engines' readings (engine A without its band
    blocks, engine B whole and without its head copies)."""
    scan: int
    text: str
    entry: dict[str, Any]
    record: dict[str, Any]
    a_body: str
    a_blocks: list[dict[str, Any]]
    b_text: str
    b_body: str
    band_text: str
    band_numbers: list[str]


def page_data(book: Any, model: Mapping[str, Any], scan: int, text: str) -> PageData:
    page = book.pages[scan]
    entry = rm.page_entry(model, scan)
    band = entry.get("band") or []
    band_blocks = {b["block"] for b in band}
    a_blocks = [b for b in page.engine_a_blocks() if b.get("index") not in band_blocks]
    a_body, b_body = rm.body_streams(page, band, entry.get("headSpansB") or [])
    numbers = []
    for b in band:
        if b.get("label") == "number":
            value = normal_numerals(b["text"])
            if value:
                numbers.append(value)
    return PageData(scan=scan, text=text, entry=entry, record=page.record, a_body=a_body, a_blocks=a_blocks,
                    b_text=page.engine_b_text(), b_body=b_body,
                    band_text="".join(pp.CJK(b["text"]) for b in band), band_numbers=numbers)


ARABIC_TO_CJK = str.maketrans("0123456789０１２３４５６７８９", "〇一二三四五六七八九〇一二三四五六七八九")


def normal_numerals(text: str) -> str:
    """A folio as read: CJK digits (a zero read as a square or a Latin O is
    〇), Arabic figures in CJK form; empty if anything else is in it."""
    out = []
    for c in text:
        if c.isspace():
            continue
        c = c.replace("O", "〇").replace("o", "〇").replace(ZERO_READS, "〇").translate(ARABIC_TO_CJK)
        c = pp.CJK(c) or c
        if c not in rm.DIGIT_VALUE and c not in rm.UNIT_VALUE:
            return ""
        out.append(c)
    return "".join(out)


def pieces(text: str) -> set[str]:
    return {text[i:j] for i in range(len(text)) for j in range(i + 1, len(text) + 1)}


# --- furniture ---------------------------------------------------------------

@dataclass
class Answer:
    """An adjudicator's answer at a band spot (F6): its text, where it is on
    the page (sealed CJK indices, or None when it is not found once), and
    the record."""
    text: str
    at: int | None
    record: dict[str, Any]
    source: str


class Furniture:
    """The furniture rules on one page."""

    def __init__(self, pd: PageData, facts: BookFacts):
        self.pd = pd
        self.facts = facts
        self.text = pd.text
        self.lines = [line for line in lines_of(pd.text) if line.text.strip()]
        self.sealed = ra.stream(pd.text)
        self.suffix = pd.entry.get("suffix")
        folio = pd.entry.get("folio")
        self.folio_forms = {f.translate(ARABIC_TO_CJK) for f in lint.folio_forms(folio)}
        self.band_numeral_pieces = set().union(*(pieces(n) for n in pd.band_numbers)) if pd.band_numbers else set()
        self.exempt = pd.scan in facts.dividers or pd.scan in facts.contents_first
        # A page that prints a running head shows it: a folio the sequence
        # gives it or an engine read in the band, or its run's suffix read
        # there.  A page with none of them (a title page, a plate) prints no
        # running head, and a stem copy on it is the page's own text.
        self.running = bool(pd.entry.get("folio") or pd.entry.get("folioReadings") or pd.entry.get("suffixRead")
                            or pd.band_numbers)
        self.printed = Counter(lint.line_core(line) for line in pd.a_body.split("\n"))
        self.printed_lines = set(self.printed)
        self.b = ra.stream(pd.b_text)
        self.a = ra.stream(pd.a_body)
        self.to_a = ra.mapping(self.a.chars, self.sealed.chars)
        self.block_of = a_blocks_of(pd) if pd.a_blocks and pp.CJK(pd.a_body) else []
        b_to_a = ra.mapping(self.a.chars, self.b.chars)
        self.head_cores, self.head_numerals = self._b_heads(b_to_a)

    def read_in_body(self, start: int, end: int) -> bool:
        """Engine A read most of the page's characters in START:END in its
        body (outside the band): they are printed there, whether engine A
        read them as a line of their own or inside a block with the text
        around them (a heading engine A joined to its paragraph)."""
        offsets = self.sealed.offsets
        ks = range(bisect.bisect_left(offsets, start), bisect.bisect_left(offsets, end))
        return len(ks) > 0 and 2 * sum(self.to_a[k] is not None for k in ks) > len(ks)

    def glued_head(self, aligned: Sequence[int], allowed: set[str]) -> bool:
        """Whether engine A's reading of a held run (the indices ALIGNED of
        its body stream) is the band glued to one of its body blocks: a block
        of text, not a title, where the run with the band's characters engine
        A read next to it holds the page's suffix or its folio besides the
        stem.  A stem copy engine A read in a title, or bare inside a block's
        text (a mention of the book), is the page's own."""
        if not self.block_of or not aligned:
            return False
        lo, hi = min(aligned), max(aligned)
        block = self.block_of[lo]
        if self.block_of[hi] != block or self.pd.a_blocks[block].get("label") in rm.TITLE_LABELS:
            return False
        chars = self.a.chars
        while lo > 0 and self.block_of[lo - 1] == block and chars[lo - 1] in allowed:
            lo -= 1
        while hi + 1 < len(chars) and self.block_of[hi + 1] == block and chars[hi + 1] in allowed:
            hi += 1
        run = chars[lo:hi + 1]
        numerals = re.findall("[" + NUMERALS + ZERO_READS + "]+", run)
        return any(s in run for s in self.facts.suffixes) or any(self.folio_whole(n) for n in numerals)

    # engine B's head: each stem copy with the suffix and numerals the model
    # read beside it - and, where no suffix follows the stem copy, the
    # page's own suffix read with one character wrong, when engine A's body
    # does not hold those characters there.
    def _b_heads(self, b_to_a: Sequence[int | None]) -> tuple[list[str], set[str]]:
        chars = self.b.chars
        cores, numerals = [], set()
        for span in self.pd.entry.get("headSpansB") or []:
            start, end = span.get("startAll", span["start"]), span.get("endAll", span["end"])
            if not (0 <= start < end <= len(chars)):
                continue
            stop = end
            suffix = self.suffix
            if suffix and len(suffix) >= 2 and not span.get("suffix") and not span.get("suffixAtEnd"):
                window = chars[end:end + len(suffix)]
                if len(window) == len(suffix) and window != suffix \
                        and sum(x == y for x, y in zip(window, suffix)) >= len(suffix) - 1 \
                        and all(b_to_a[j] is None for j in range(end, end + len(suffix))):
                    stop = end + len(suffix)
            lead, middle, trail = rm.strip_folio(chars[start:stop])
            cores.append(middle)
            for run in (span.get("numeralsBefore") or "", span.get("numeralsAfter") or "", lead, trail):
                if run:
                    numerals.update(pieces(normal_numerals(run)))
        return cores, numerals - {""}

    def folio_piece(self, text: str) -> bool:
        value = normal_numerals(text)
        return bool(value) and (value in self.folio_forms or value in self.band_numeral_pieces)

    def folio_whole(self, text: str) -> bool:
        """TEXT is the page's folio as a whole - the value the sequence gives
        the page, or what engine A read in its folio block - not a piece of
        it (a piece, 一 of 一〇, is as likely a numeral of the body)."""
        value = normal_numerals(text)
        if not value:
            return False
        folio = self.pd.entry.get("folio")
        return (folio is not None and rm.numeral_value(value) == folio) or value in self.pd.band_numbers

    def without_suffixes(self, text: str) -> str:
        for suffix in sorted(self.facts.suffixes, key=len, reverse=True):
            text = text.replace(suffix, "")
        return text

    def band_context(self, context: str) -> bool:
        chars = pp.CJK(context)
        if not chars:
            return False
        for stem in self.facts.stems:
            if rm.stem_matches(chars, stem) or common_run(chars, stem) >= math.ceil(rm.STEM_POSITION_SHARE * len(stem)):
                return True
        return bool(self.suffix and self.suffix in chars)

    def a_ok(self, reading: str) -> bool:
        """Engine A read no body text at the spot: nothing, a run suffix,
        text of its band blocks, or folio figures."""
        rest = self.without_suffixes(pp.CJK(reading))
        return not rest or rest in self.pd.band_text or self.folio_piece(rest)

    def b_ok(self, reading: str) -> bool:
        """Engine B read no body text at the spot: nothing, a run suffix,
        folio figures, or text of its running head."""
        rest = self.without_suffixes(pp.CJK(reading))
        return not rest or self.folio_piece(rest) or any(rest in core for core in self.head_cores)

    def band_whole(self, reading: str) -> bool:
        """READING is the band as a whole: nothing but a run suffix, the
        page's folio (whole), or a running head as an engine read it (a band
        block of engine A, or engine B's head with the folio beside it).  A
        character of the head alone, or a piece of the folio (一 of 一〇), is
        as likely a character of the body."""
        rest = self.without_suffixes(pp.CJK(reading))
        if not rest or self.folio_whole(rest):
            return True
        lead, middle, trail = rm.strip_folio(rest)
        heads = {self.without_suffixes(core) for core in self.head_cores}
        heads |= {self.without_suffixes(pp.CJK(b["text"])) for b in self.pd.entry.get("band") or []}
        return bool(middle) and middle in heads and all(not x or self.folio_whole(x) for x in (lead, trail))

    def answers(self) -> tuple[list[Answer], list[dict[str, Any]]]:
        """F6's answers on this page, and the questions for a folio figure
        written where engine A read a body character, or where an engine
        read that figure as only a piece of the folio."""
        records = []
        for a in self.pd.record.get("adjudications") or []:
            if isinstance(a, dict):
                records.append(("adjudication", a.get("context_before"), a.get("draft_reading"),
                                a.get("writer_reading"), a.get("resolved"), a.get("context_after"),
                                a.get("resolved_from"), a))
        for e in self.pd.record.get("engineDisagreements") or []:
            if isinstance(e, dict) and e.get("resolved_by") == "moved-kept-once":
                records.append(("moved-kept-once", e.get("context_before"), e.get("engineA"), e.get("engineB"),
                                e.get("resolved"), e.get("context_after"), "moved-kept-once", e))
        found: list[Answer] = []
        asks: list[dict[str, Any]] = []
        if self.exempt or not self.facts.stems or not self.running:
            return found, asks
        for source, before, a_read, b_read, resolved, after, how, record in records:
            answer = pp.CJK(str(resolved or ""))
            if not answer or how not in ("adjudicator", "engine-A-default", "moved-kept-once"):
                continue
            band_before, band_after = self.band_context(str(before or "")), self.band_context(str(after or ""))
            if not (band_before or band_after):
                continue
            a_chars, b_chars = pp.CJK(str(a_read or "")), pp.CJK(str(b_read or ""))
            at = self.locate(answer, str(before or ""), str(after or ""), band_before, band_after)
            # An engine that read the answer itself, which the adjudicator
            # confirmed from the image, read band text there only when its
            # reading is the band as a whole; an answer of the adjudicator's
            # own, where the engines read the band's characters or nothing,
            # is not the page's.
            a_fine = self.band_whole(a_chars) if a_chars == answer else self.a_ok(a_chars)
            b_fine = self.band_whole(b_chars) if b_chars == answer else self.b_ok(b_chars)
            if a_fine and b_fine:
                found.append(Answer(answer, at, record, source))
                continue
            if at is None or not self.folio_piece(answer):
                continue
            if a_chars and not self.a_ok(a_chars):
                why = "a folio figure written where engine A read a body character"
            elif answer in (a_chars, b_chars):
                why = "a piece of the folio written where an engine read it, not the folio as a whole"
            else:
                continue
            start = self.sealed.offsets[at]
            end = self.sealed.offsets[at + len(answer) - 1] + 1
            asks.append(question("Q-G", self.pd.scan, "F6", self.text, start, end, why,
                                 engineA=a_chars, engineB=b_chars))
        # One answer per place: an adjudication and a move of the same answer.
        unique: dict[Any, Answer] = {}
        for answer in found:
            key = (answer.text, answer.at) if answer.at is not None else (answer.text, id(answer))
            unique.setdefault(key, answer)
        return list(unique.values()), [q for k, q in enumerate(asks) if q not in asks[:k]]

    def locate(self, answer: str, before: str, after: str, band_before: bool, band_after: bool) -> int | None:
        chars = self.sealed.chars
        before, after = pp.CJK(before), pp.CJK(after)
        candidates = []
        if band_before and band_after:
            if chars.startswith(answer):
                candidates.append(0)
            if chars.endswith(answer):
                candidates.append(len(chars) - len(answer))
        elif band_before:
            body = after[:3]
            if body:
                candidates = [m.start() for m in re.finditer(re.escape(answer + body), chars)]
            elif chars.endswith(answer):
                candidates = [len(chars) - len(answer)]
        else:
            body = before[-3:]
            if body:
                candidates = [m.start() + len(body) for m in re.finditer(re.escape(body + answer), chars)]
            elif chars.startswith(answer):
                candidates = [0]
        candidates = sorted(set(candidates))
        return candidates[0] if len(candidates) == 1 else None

    # whole lines
    def whole_line(self, line: Line) -> tuple[str, str] | None:
        core = lint.line_core(line.text)
        if not core:
            return None
        facts = self.facts
        rule = None
        if facts.stems and self.running and lint.head_line(core, facts.stems, facts.suffixes):
            rule = ("F1", "a running head: a stem copy with at most a stray numeral, a run suffix and folio figures")
        elif self.suffix and core == self.suffix and self.suffix in facts.suffixes and not self.exempt \
                and not self.pd.entry.get("contents"):
            rule = ("F2", "the page's own run suffix alone, on a page that is not a divider or a contents page")
        elif facts.contents_word and core == facts.contents_word and self.pd.entry.get("contents") \
                and self.pd.scan not in facts.contents_first:
            rule = ("F3", "the contents word alone on a contents page after the first")
        if rule and self.printed[core] > 0:
            # Engine A read this line in its body: it is printed there.
            self.printed[core] -= 1
            return None
        if rule and self.read_in_body(line.start, line.end):
            # So it is when engine A read it in a block with the text around it.
            return None
        return rule

    def folio_line(self, line: Line) -> tuple[str, str] | None:
        core = lint.line_core(line.text)
        if not lint.numeral_only(core) or self.printed[core] > 0 or self.read_in_body(line.start, line.end):
            return None
        value = normal_numerals(core)
        if not value or not (value in self.folio_forms or value in self.band_numeral_pieces):
            return None
        # An engine read it in the band: engine A's folio block, or the
        # numerals engine B read beside its running head.
        if value not in self.band_numeral_pieces and value not in self.head_numerals:
            return None
        return ("F4", "a numeral-only line at the page's edge: the folio (or a piece of it) an engine read in the band")

    def answer_line(self, line: Line, answers: Sequence[Answer]) -> tuple[str, str] | None:
        rest = pp.CJK(line.text)
        if not rest:
            return None
        took = False
        for text in sorted({a.text for a in answers}, key=len, reverse=True):
            while text in rest:
                rest = rest.replace(text, "", 1)
                took = True
        if took and all(c in self.pd.band_text for c in rest):
            return ("F7", "a line at the page's edge made only of answers at band spots and characters of "
                          "engine A's band")
        return None

    def plan(self) -> Plan:
        plan = Plan()
        pd = self.pd
        answers, asks = self.answers()
        plan.questions.extend(asks)
        deleted: dict[int, tuple[str, str]] = {}
        for line in self.lines:
            found = self.whole_line(line)
            if found:
                deleted[line.number] = found
        for ordered in (self.lines, list(reversed(self.lines))):
            for line in ordered:
                if line.number in deleted:
                    continue
                found = self.folio_line(line) or self.answer_line(line, answers)
                if not found:
                    break
                deleted[line.number] = found
        spans = self.deletion_spans(set(deleted))
        for line in self.lines:
            if line.number not in deleted:
                continue
            rule, why = deleted[line.number]
            start, end = spans[line.number]
            plan.edits.append(re_.Edit(pd.scan, start, end, "", rule=rule, evidence={
                "deletes": "furniture", "line": line.number, "text": line.text, "why": why,
                "band": [b["text"] for b in pd.entry.get("band") or []], "folio": pd.entry.get("folio"),
                "suffix": self.suffix}))

        def inside_deleted(start: int, end: int) -> bool:
            return any(line.number in deleted and line.start <= start and end <= line.end for line in self.lines)

        inline: list[tuple[int, int, str, str, dict[str, Any]]] = []
        for answer in answers:
            if answer.at is None:
                continue
            start = self.sealed.offsets[answer.at]
            end = self.sealed.offsets[answer.at + len(answer.text) - 1] + 1
            record = answer.record
            inline.append((start, end, "F6", "an answer at a band spot where neither engine read body text", {
                "answer": answer.text, "record": answer.source,
                "engineA": record.get("draft_reading", record.get("engineA")),
                "engineB": record.get("writer_reading", record.get("engineB")),
                "contextBefore": record.get("context_before"), "contextAfter": record.get("context_after")}))
        if not self.exempt:
            inline.extend(self.inline_heads(answers, deleted, plan.questions))
            inline.extend(self.inline_suffixes(deleted))
        kept: list[tuple[int, int, str, str, dict[str, Any]]] = []
        for item in sorted(inline, key=lambda x: (x[0], -(x[1] - x[0]))):
            start, end = item[0], item[1]
            if inside_deleted(start, end):
                continue
            container = next((k for k in kept if k[0] <= start and end <= k[1]), None)
            if container is not None:
                container[4].setdefault("alsoRules", []).append(item[2])
                continue
            kept.append(item)
        for start, end, rule, why, evidence in kept:
            plan.edits.append(re_.Edit(pd.scan, start, end, "", rule=rule, evidence={
                "deletes": "furniture", "text": self.text[start:end], "why": why, **evidence}))
            ask = self.marks_beside(start, end, rule)
            if ask:
                plan.questions.append(ask)
        return plan

    def deletion_spans(self, deleted: set[int]) -> dict[int, tuple[int, int]]:
        """The span each deleted line takes: the line and one separator
        beside it, so the page keeps one separator between the lines left -
        the stronger (more newlines) of the two around a deleted group."""
        lines = self.lines
        spans: dict[int, tuple[int, int]] = {}
        i = 0
        while i < len(lines):
            if lines[i].number not in deleted:
                i += 1
                continue
            j = i
            while j + 1 < len(lines) and lines[j + 1].number in deleted:
                j += 1
            group = lines[i:j + 1]
            prev = lines[i - 1] if i > 0 else None
            nxt = lines[j + 1] if j + 1 < len(lines) else None
            keep_before = True
            if prev is not None and nxt is not None:
                sep_before = self.text[prev.end:group[0].start].count("\n")
                sep_after = self.text[group[-1].end:nxt.start].count("\n")
                keep_before = sep_before >= sep_after
            elif prev is not None:
                keep_before = False
            for k, line in enumerate(group):
                if keep_before:
                    stop = group[k + 1].start if k + 1 < len(group) else (nxt.start if nxt else line.end)
                    spans[line.number] = (line.start, stop)
                else:
                    begin = group[k - 1].end if k else prev.end
                    spans[line.number] = (begin, line.end)
            i = j + 1
        return spans

    def in_deleted(self, offset: int, deleted: Mapping[int, Any]) -> bool:
        return any(line.number in deleted and line.start <= offset < line.end for line in self.lines)

    def inline_heads(self, answers: Sequence[Answer], deleted: Mapping[int, Any],
                     out_asks: list[dict[str, Any]]) -> list[tuple[int, int, str, str, dict[str, Any]]]:
        """F5: what the page holds where engine B read its running head (the
        sites it cannot settle go to OUT_ASKS)."""
        out = []
        if not self.facts.stems or not self.running:
            return out
        chars = self.sealed.chars
        to_b = ra.mapping(self.b.chars, chars)
        b_to_s: dict[int, int] = {j: k for k, j in enumerate(to_b) if j is not None}
        allowed = set("".join(self.facts.stems)) | set("".join(self.facts.suffixes)) | set(NUMERALS) \
            | set(ZERO_READS) | self.facts.misread_chars | set("".join(a.text for a in answers))
        for span in self.pd.entry.get("headSpansB") or []:
            start, end = span.get("startAll", span["start"]), span.get("endAll", span["end"])
            # The body characters engine B read on either side, where the
            # page holds them.
            lo = next((b_to_s[j] for j in range(start - 1, -1, -1) if j in b_to_s), -1)
            hi = next((b_to_s[j] for j in range(end, len(self.b.chars)) if j in b_to_s), len(chars))
            if hi <= lo + 1:
                continue
            # The held run's part in the lines the page keeps: a run that
            # goes on into a line deleted whole is cut at that line; one
            # that crosses between two kept lines is not taken.
            ks = [k for k in range(lo + 1, hi) if not self.in_deleted(self.sealed.offsets[k], deleted)]
            if not ks or ks != list(range(ks[0], ks[-1] + 1)):
                continue
            s = self.sealed.offsets[ks[0]]
            e = self.sealed.offsets[ks[-1]] + 1
            held = chars[ks[0]:ks[-1] + 1]
            if "\n" in self.text[s:e] or not all(c in allowed for c in held):
                continue
            core = any(lcs(held, stem) >= math.ceil(rm.STEM_POSITION_SHARE * len(stem)) for stem in self.facts.stems)
            if not (core or held == self.suffix):
                continue
            # A whole line is F1's to judge.  Engine A read the run as a line
            # of its body (outside the band): it is printed there, a title
            # that holds the stem.  (Engine A now and then glues the head to
            # the end of the body column beside it; that is no line of its
            # own.)
            line = next(l for l in self.lines if l.start <= s < l.end)
            if pp.CJK(line.text) == held or held in self.printed_lines:
                continue
            aligned = [self.to_a[k] for k in ks if self.to_a[k] is not None]
            in_body = 2 * len(aligned) > len(ks)
            # Engine B reads the band first or last: a stem copy with text of
            # the page it read on both sides is one it read inside the body
            # (a mention of the book, a title that holds it).
            inside = lo >= 0 and hi < len(chars)
            # Engine A read the run in its body: the band glued to a text
            # block carries its suffix or folio beside the stem; a stem copy
            # in a title, or bare in a block's text, is the page's own.
            if inside or (in_body and not self.glued_head(aligned, allowed)):
                if inside and not in_body:
                    out_asks.append(question(
                        "Q-P", self.pd.scan, "F5", self.text, s, e,
                        "engine B read its running head here, inside its reading of the body, and engine A did "
                        "not read these characters in its body: are they printed?", engineB=span.get("read")))
                continue
            out.append((s, e, "F5", "what the page holds where engine B read its running head: only head, "
                                    "suffix, folio and misread characters", {"engineB": span.get("read"),
                                                                              "held": held}))
        return out

    def inline_suffixes(self, deleted: Mapping[int, Any]) -> list[tuple[int, int, str, str, dict[str, Any]]]:
        """F2b and F2c: the page's own suffix glued to the body's first line
        or to a line just before a running head."""
        out = []
        suffix = self.suffix
        if not suffix or suffix not in self.facts.suffixes or self.pd.entry.get("contents"):
            return out
        a_chars = pp.CJK(self.pd.a_body)
        b_chars = pp.CJK(self.pd.b_body)
        # A copy of the suffix beyond what one engine read in its body: a
        # printed one both engines read (engine B's body leaves out what it
        # read as its head; engine A now and then glues the suffix to the
        # body column beside the band).
        # The copies in lines deleted whole (a head line) are not counted.
        kept_copies = sum(pp.CJK(line.text).count(suffix) for line in self.lines if line.number not in deleted)
        extra = kept_copies - min(a_chars.count(suffix), b_chars.count(suffix))
        if extra <= 0:
            return out
        kept = [line for line in self.lines if line.number not in deleted]
        if kept:
            first = kept[0]
            rest = lint.LINE_PREFIX.sub("", first.text)
            lead = len(first.text) - len(rest)
            if pp.CJK(rest).startswith(suffix) and rest.startswith(suffix):
                body = pp.CJK(rest[len(suffix):])[:3]
                if len(body) >= 2 and a_chars.startswith(body) and b_chars.startswith(body):
                    s = first.start + lead
                    out.append((s, s + len(suffix), "F2b", "the page's own suffix opening the first line, where "
                                                           "both engines start the body after it", {}))
        for k, line in enumerate(self.lines[:-1]):
            if line.number in deleted or self.lines[k + 1].number not in deleted \
                    or deleted[self.lines[k + 1].number][0] != "F1":
                continue
            match = re.search(rf"{re.escape(suffix)}([^\w]*)$", line.text)
            if match and pp.CJK(line.text[:match.start()]):
                s = line.start + match.start()
                out.append((s, s + len(suffix), "F2c", "the page's own suffix ending the line just before a "
                                                       "running head (the label only)", {}))
        return out

    def a_between(self, start: int, end: int) -> str | None:
        """What engine A read between the page's nearest characters it shares
        before START and at or after END (the page's edges where there are
        none); None when the two are not in order in engine A."""
        offsets = self.sealed.offsets
        lo = next((k for k in range(bisect.bisect_left(offsets, start) - 1, -1, -1) if self.to_a[k] is not None), None)
        hi = next((k for k in range(bisect.bisect_left(offsets, end), len(offsets)) if self.to_a[k] is not None), None)
        a_lo = self.a.offsets[self.to_a[lo]] + 1 if lo is not None else 0
        a_hi = self.a.offsets[self.to_a[hi]] if hi is not None else len(self.a.text)
        return self.a.text[a_lo:a_hi] if a_lo <= a_hi else None

    def marks_beside(self, start: int, end: int, rule: str) -> dict[str, Any] | None:
        """A question about the marks a deletion leaves beside the band: the
        marks the page holds right before or after the span, in its line,
        when engine A read none of them between the characters on either
        side."""
        text = self.text
        s = start
        while s > 0 and text[s - 1] not in "\n" and not pp.CJK(text[s - 1]) and not text[s - 1].isspace():
            s -= 1
        e = end
        while e < len(text) and text[e] not in "\n" and not pp.CJK(text[e]) and not text[e].isspace():
            e += 1
        marks = marks_of(text[s:start] + text[end:e])
        marks = "".join(c for c in marks if not c.isalnum() and c not in "#-*>")
        if not marks:
            return None
        read = self.a_between(start, end)
        if read is not None and subsequence(marks, marks_of(read)):
            return None
        # The site holds the deleted span; the question is asked after the
        # deletion (FOLLOWS names it, so the question stage does not take it
        # for an edit that made the question moot).
        return question("Q-P", self.pd.scan, rule, text, s, e,
                        "marks left beside furniture that was deleted: are they printed?", marks=marks,
                        engineA=read, follows={"start": start, "end": end, "text": text[start:end]})


def furniture(book: Any, model: Mapping[str, Any], texts: Mapping[int, str], order: Sequence[int],
              facts: BookFacts | None = None) -> Plan:
    """The furniture rules over the pages ORDER (their texts TEXTS)."""
    facts = facts or book_facts(book, model)
    plan = Plan()
    if not facts.gates.get("M-1"):
        return plan
    for scan in order:
        page_plan = Furniture(page_data(book, model, scan, texts[scan]), facts).plan()
        plan.edits.extend(page_plan.edits)
        plan.questions.extend(page_plan.questions)
        plan.doubts.extend(page_plan.doubts)
        # F8 on the page as its furniture edits leave it (where the stage
        # applies them): its first and last characters are the body's.
        local = re_.Ledger({scan: texts[scan]})
        local.apply("furniture", page_plan.edits)
        plan.questions.extend(lost_at_edges(page_data(book, model, scan, local.texts[scan]), facts))
    return plan


# F8: at most this many characters both engines read at a page's edge that
# the page lacks (a character, or two, that went out with the band).
LOST_EDGE = 2


def edge_run(chars: str, outward: Sequence[int], skip: set[str]) -> tuple[str, list[int]]:
    """The characters of CHARS at the indices OUTWARD (from the page's
    shared text out to its edge) that are not in SKIP: the first run of
    them, past any SKIP characters beside the shared text (engine B's
    stand-ins for the marks there), up to the next SKIP character (the
    band's, a numeral); and their indices."""
    out: list[int] = []
    for i in outward:
        if chars[i] in skip:
            if out:
                break
            continue
        out.append(i)
    return "".join(chars[i] for i in out), out


def lost_at_edges(pd: PageData, facts: BookFacts) -> list[dict[str, Any]]:
    """F8: the body's first or last character(s) that both engines read, one
    or two, where the page holds none - beyond the page's first (last)
    character, which both engines share with it, each engine read a run of
    as many characters that are not the band's (its blocks, the stems, the
    run suffixes), numerals or the book's stand-ins; the two may read them
    differently (a damaged glyph).  On a real book the adjudication at a
    folio spot answered the folio and dropped the body's first character
    with it, and one at the foot answered that no glyph could settle it:
    the character was lost and nothing asked about it.  A glyph question
    (Q-G) at the page's edge, the engines' readings of the run its
    candidates; the answer goes before the first character (after the last
    line's marks at the foot)."""
    text = pd.text
    s, a, b = ra.stream(text), ra.stream(pd.a_body), ra.stream(pd.b_body)
    if not s.chars or not a.chars or not b.chars:
        return []
    to_a, to_b = ra.mapping(a.chars, s.chars), ra.mapping(b.chars, s.chars)
    skip = (set(pd.band_text) | set("".join(facts.stems)) | set("".join(facts.suffixes)) | facts.standins()
            | set(NUMERALS) | set(ZERO_READS) | set(rm.UNIT_VALUE))
    out = []
    for edge in ("head", "foot"):
        k = 0 if edge == "head" else len(s.chars) - 1
        ja, jb = to_a[k], to_b[k]
        if ja is None or jb is None:
            continue
        if edge == "head":
            a_run, a_at = edge_run(a.chars, range(ja - 1, -1, -1), skip)
            b_run, _ = edge_run(b.chars, range(jb - 1, -1, -1), skip)
            a_run, b_run = a_run[::-1], b_run[::-1]
        else:
            a_run, a_at = edge_run(a.chars, range(ja + 1, len(a.chars)), skip)
            b_run, _ = edge_run(b.chars, range(jb + 1, len(b.chars)), skip)
        if not (1 <= len(a_run) <= LOST_EDGE and len(a_run) == len(b_run)):
            continue
        # Where the run goes among the page's marks beside its edge
        # character: as engine A reads the marks between the two.
        line_start = text.rfind("\n", 0, s.offsets[0]) + 1
        if edge == "head":
            between = marks_of(a.text[a.offsets[max(a_at)] + 1:a.offsets[ja]])
            held = text[line_start:s.offsets[0]]
            lead = re.match(r"[ \t]*(?:#{1,6}[ \t]+|[-*+][ \t]+)?", held).end()
            at = s.offsets[0]
            while at > line_start + lead and between and marks_of(text[at - 1]) == between[-1:]:
                at -= 1
                between = between[:-1]
        else:
            between = marks_of(a.text[a.offsets[ja] + 1:a.offsets[min(a_at)]])
            end = len(text.rstrip())
            at = s.offsets[-1] + 1
            while at < end and between and marks_of(text[at]) == between[:1]:
                at += 1
                between = between[1:]
        out.append(question("Q-G", pd.scan, "F8", text, at, at,
                            f"both engines read {a_run!r} / {b_run!r} at the page's {edge}, beyond the first "
                            f"character they share with it, where the page holds none", engineA=a_run,
                            engineB=b_run, atPlace={"a": a_run, "b": b_run}, edge=edge))
    return out


# --- marks -------------------------------------------------------------------

# A structure token of a span: line breaks, and a heading or list marker
# opening a line.
STRUCTURE = re.compile(r"(?:\n+|^)(?:[ \t]*(?:#{1,6}|[-*+])[ \t]+)|\n+")
FIGURE_GAP = re.compile(r"(?P<pre>[^（0-9０-９]*)(?P<fig>（[0-9０-９]{1,3}）)(?P<post>[^0-9０-９]*)")
LINE_FIGURE_GAP = re.compile(r"(?P<pre>[^0-9０-９]*?)(?P<d>[0-9０-９]{1,3})(?P<dot>[.．])?")
LINE_FIGURE_END = re.compile(r"\n\s*[0-9０-９]{1,3}\s*[.．]?\s*$")


def split_structure(span: str) -> list[tuple[str, str]]:
    """SPAN as tokens: ("c", a character) or ("s", a structure run)."""
    out: list[tuple[str, str]] = []
    at = 0
    for match in STRUCTURE.finditer(span):
        if match.end() == match.start():
            continue
        out.extend(("c", c) for c in span[at:match.start()])
        out.append(("s", match.group()))
        at = match.end()
    out.extend(("c", c) for c in span[at:])
    return out


def with_structure(tokens: Sequence[tuple[str, str]], before: str, after: str) -> str:
    """BEFORE ahead of the span's structure, AFTER behind its last heading or
    list marker (the line's own text starts there)."""
    structures = [t for kind, t in tokens if kind == "s"]
    if not structures:
        return before + after
    last = max((i for i, t in enumerate(structures) if re.search(r"[#*+-]", t)), default=len(structures) - 1)
    return before + "".join(structures[:last + 1]) + after + "".join(structures[last + 1:])


def figure_value(text: str) -> int:
    return int(text.translate(ra.FULLWIDTH_DIGITS))


class Marks:
    """The mark rules on one page (the text the stage starts from)."""

    def __init__(self, pd: PageData, facts: BookFacts):
        self.pd = pd
        self.facts = facts
        self.text = pd.text
        self.s = ra.stream(pd.text)
        self.a = ra.stream(pd.a_body)
        self.b = ra.stream(pd.b_body)
        self.to_a = ra.mapping(self.a.chars, self.s.chars)
        self.to_b = ra.mapping(self.b.chars, self.s.chars)
        # A CJK numeral stands for engine A's figure only on a book where
        # engine B was seen to write numerals for engine A's figures (M-7b's
        # numeralsAtFigures): elsewhere which script the page prints is a
        # reading.
        self.standins = facts.standins() | (set(NUMERALS) if facts.numeral_figures else set())
        self.open_aliases = facts.aliases_of("（")
        self.close_aliases = facts.aliases_of("）")
        self.quote_aliases = facts.aliases_of(PAIRED)

    def span(self, k1: int, k2: int) -> tuple[int, int]:
        start = 0 if k1 < 0 else self.s.offsets[k1] + 1
        end = self.s.offsets[k2] if k2 < len(self.s.offsets) else len(self.text)
        return start, end

    def b_between(self, k1: int, k2: int) -> str | None:
        if k1 < 0:
            return None
        return ra.engine_between(self.b, self.to_b, k1, k2)

    def figure_glyphs(self, k1: int, k2: int) -> set[str]:
        """The glyphs engine B read for a figure between two sealed
        characters: those between a bracket's glyphs (an opening one before,
        and a closing one after or nothing), after the mark glyphs before."""
        read = self.b_between(k1, k2)
        if not read:
            return set()
        glyphs = pp.CJK(read)
        at = 0
        while at < len(glyphs) and glyphs[at] in self.facts.aliases and glyphs[at] not in self.open_aliases:
            at += 1
        if at >= len(glyphs) or glyphs[at] not in self.open_aliases:
            return set()
        inner = glyphs[at + 1:]
        if inner and inner[-1] in self.close_aliases:
            inner = inner[:-1]
        return set(inner) if 1 <= len(inner) <= 2 else set()

    def accounted(self, glyph: str, gap: str, figure_glyphs: set[str]) -> bool:
        """Whether GLYPH, a character engine A did not read where it read
        GAP, is engine B's stand-in for something engine A read there: a
        glyph B read for the figure, a figure stand-in or a numeral, or a
        stand-in for one of the marks, dashes or dots in GAP - a mark engine
        B was seen to write it for at as many sites as phase 3 needs to call
        it an alias (once is chance, such as this very site).  A stand-in of
        the book for a mark engine A did not read there (often a character
        of the text too) is not."""
        if glyph in NUMERALS:
            return self.facts.numeral_figures
        if glyph in figure_glyphs or glyph in self.facts.figure:
            return True
        if any(n >= pp.MARK_ALIAS_MINIMUM and mark in gap for mark, n in self.facts.aliases.get(glyph, {}).items()):
            return True
        if glyph in self.facts.dash and any(c in ra.DASH_CHARS for c in gap):
            return True
        return glyph in self.facts.dot and any(c in DOT_READS for c in gap)

    def pairs(self) -> list[tuple[int, int]]:
        shared = [k for k, j in enumerate(self.to_a) if j is not None]
        return ([(-1, shared[0])] if shared else []) + list(zip(shared, shared[1:]))

    def plan(self) -> Plan:
        plan = Plan()
        text, s = self.text, self.s
        proposals: list[tuple[int, int, str, str, dict[str, Any]]] = []
        for k1, k2 in self.pairs():
            start, end = self.span(k1, k2)
            span = text[start:end]
            non = [s.chars[k] for k in range(k1 + 1, k2)]
            ia = self.to_a[k2]
            gap_raw = self.a.gaps[ia]
            gap = marks_of(gap_raw)
            adjacent = k1 < 0 or ia == self.to_a[k1] + 1
            if not adjacent or (not span.strip() and not gap):
                continue
            found = (self.k1(k1, k2, span, non, gap) or self.k2(k1, k2, span, non, gap, gap_raw)
                     or self.k3(k1, k2, span, non, gap) or self.k4(span, non, gap, gap_raw)
                     or self.k7(k1, k2, span, non, gap))
            if isinstance(found, dict):
                plan.questions.append(found)
                continue
            if found and found[0] != span:
                new, rule, evidence = found
                proposals.append((start, end, new, rule, {"engineA": gap_raw, **evidence}))
        twins, asks = self.twins()
        proposals.extend(twins)
        plan.questions.extend(asks)
        proposals.extend(self.k6())
        proposals.extend(self.shapes())
        taken: list[tuple[int, int]] = []
        for start, end, new, rule, evidence in sorted(proposals, key=lambda p: (p[0], p[1])):
            if any(re_.overlaps((start, end), t) for t in taken):
                continue
            taken.append((start, end))
            plan.edits.append(re_.Edit(self.pd.scan, start, end, new, rule=rule, evidence={
                "before": text[start:end], **evidence}))
        return plan

    # K1: a bracketed figure engine A read.
    def k1(self, k1: int, k2: int, span: str, non: list[str], gap: str) -> Any:
        match = FIGURE_GAP.fullmatch(gap)
        tokens = split_structure(span)
        content = "".join(t for kind, t in tokens if kind == "c")
        if not match or len(non) > 4 or not (non or "）（" in content or "（）" in content):
            return None
        figure_glyphs = self.figure_glyphs(k1, k2)
        strange = [c for c in non if not self.accounted(c, gap, figure_glyphs)]
        if strange:
            start, end = self.span(k1, k2)
            return question("Q-P", self.pd.scan, "K1", self.text, start, end,
                            "engine A read a bracketed figure here, and the page holds characters that are not "
                            "engine B's stand-ins for what engine A read there", engineA=gap,
                            characters="".join(strange))
        first = min([content.index(c) for c in non if c in content]
                    + [content.index(x) for x in ("）（", "（）") if x in content] + [len(content)])
        lead = content[:first].replace("（", "")
        pre = match["pre"]
        add = pre if not lead.endswith(pre) else ""
        figure = match["fig"].translate(ra.FULLWIDTH_DIGITS)
        new = with_structure(tokens, lead + add, figure + match["post"])
        return new, "K1", {"figure": figure_value(figure[1:-1]), "style": "bracket", "standIns": "".join(non),
                           "aIndex": self.to_a[k2]}

    # K2: a figure opening one of engine A's lines.
    def k2(self, k1: int, k2: int, span: str, non: list[str], gap: str, gap_raw: str) -> Any:
        match = LINE_FIGURE_GAP.fullmatch(gap)
        # The figure opens one of engine A's lines: after a line break in its
        # gap, or at the start of its text.
        if not match or not (LINE_FIGURE_END.search(gap_raw) or self.to_a[k2] == 0):
            return None
        tokens = split_structure(span)
        marker = max((i for i, (kind, t) in enumerate(tokens) if kind == "s" and re.search(r"[#*+-]", t)),
                     default=None)
        plain = False
        if k1 < 0 and marker is None and tokens and tokens[0][0] == "c":
            marker = -1
        if marker is None:
            marker = max((i for i, (kind, _) in enumerate(tokens) if kind == "s"), default=None)
            plain = True
        if marker is None:
            return None
        head = "".join(t for kind, t in tokens[:max(marker, 0)] if kind == "c")
        tail = "".join(t for kind, t in tokens[marker + 1:] if kind == "c").strip()
        tail_cjk = [c for c in tail if pp.CJK(c)]
        digits = re.findall(r"[0-9０-９]+", tail)
        d = match["d"].translate(ra.FULLWIDTH_DIGITS)
        if any(pp.CJK(c) for c in head) or (digits and [x.translate(ra.FULLWIDTH_DIGITS) for x in digits] != [d]):
            return None
        stand = bool(tail_cjk) and len(tail_cjk) <= 3 and all(c in self.standins for c in tail_cjk)
        stray = not plain and not tail_cjk and not digits and bool(re.fullmatch(r"[（，。、]+", tail or "x"))
        if not (stand or stray):
            return None
        bracketed = len(tail_cjk) >= 3 and tail_cjk[0] in self.open_aliases and tail_cjk[-1] in self.close_aliases
        structures = [t for kind, t in tokens if kind == "s"]
        last = max((i for i, t in enumerate(structures) if re.search(r"[#*+-]", t)), default=len(structures) - 1)
        if bracketed:
            figure = f"（{d}）"
        elif match["dot"]:
            figure = d + "."
        else:
            # A figure without a dot, run into the title after it on its
            # line: a space between them (the number and its title).
            follows = self.text[self.span(k1, k2)[1]:self.span(k1, k2)[1] + 1]
            runs_on = not structures[last + 1:] and follows and not follows.isspace()
            figure = d + (" " if runs_on else "")
        # The page's marks before the line break are kept (engine A's that
        # are missing are added), as K1 keeps them before its figure.
        lead = "".join(c for c in head if not c.isspace())
        pre = match["pre"].strip()
        new = with_structure(tokens, lead + (pre if not lead.endswith(pre) else ""), figure)
        heading = bool(structures[last:last + 1]) and "#" in structures[last] if structures else False
        return new, "K2" if stand else "K2-stray", {
            "figure": int(d), "style": "bracket" if bracketed else ("heading" if heading else "line"),
            "dot": bool(match["dot"]), "standIns": "".join(tail_cjk), "aIndex": self.to_a[k2]}

    # K3: a dash.
    def k3(self, k1: int, k2: int, span: str, non: list[str], gap: str) -> Any:
        dash = DASH_RUN.search(gap)
        if not non or not dash or ra.DIGITS.search(gap):
            return None
        start, end = self.span(k1, k2)
        glyphs = "".join(non)
        read = self.b_between(k1, k2)
        others = marks_of(span.replace(glyphs, "", 1)) if glyphs in span else None
        # The stand-ins must be engine B's, engine B must have read no
        # character there either, and the page's other marks there must be
        # engine A's: anything else is a reading of the spot, asked.
        # And engine A itself must not have read the glyph right beside the
        # spot (one copy read, one not: which is the dash is a reading).
        beside = {self.s.chars[k] for k in (k1, k2) if 0 <= k < len(self.s.chars)}
        if len(non) > 2 or glyphs not in span or not all(c in self.facts.standins() for c in non) \
                or (read is not None and any(c not in self.facts.standins() for c in pp.CJK(read))) \
                or not subsequence(others or "", "".join(c for c in gap if c not in ra.DASH_CHARS)) \
                or beside & set(non):
            return question("Q-P", self.pd.scan, "K3", self.text, start, end,
                            "engine A read a dash and no character here, where the page holds characters "
                            "engine A did not read", engineA=gap, engineB=read, characters=glyphs)
        written = "——" if len(dash.group()) >= 2 else "—"
        return span.replace(glyphs, written, 1), "K3", {"standIns": glyphs}

    # K4: a dot's stand-in.
    def k4(self, span: str, non: list[str], gap: str, gap_raw: str) -> Any:
        if len(non) != 1 or non[0] not in self.facts.dot:
            return None
        glyph = non[0]
        # Engine A's marks there all written already (its dot among them):
        # the glyph goes, and no second dot is written.
        dots = str.maketrans({c: DOT for c in DOT_READS})
        rest = marks_of(span.replace(glyph, "", 1))
        if gap and rest and subsequence(gap.translate(dots), rest.translate(dots)):
            return span.replace(glyph, "", 1), "K4a", {"standIns": glyph}
        if any(c in DOT_READS for c in gap_raw):
            return span.replace(glyph, DOT, 1), "K4b", {"standIns": glyph}
        return None

    # K7: a lone quote glyph.
    def k7(self, k1: int, k2: int, span: str, non: list[str], gap: str) -> Any:
        if len(non) != 1 or non[0] not in self.quote_aliases:
            return None
        glyph = non[0]
        chars = self.s.chars
        if (k1 >= 0 and chars[k1] == glyph) or chars[k2] == glyph:
            return None
        tokens = split_structure(span)
        content = "".join(t for kind, t in tokens if kind == "c")
        rest = content.replace(glyph, "", 1)
        k = k1 + 1
        new = rule = None
        if re.search(f"{re.escape(glyph)}[「」『』（）]|[「」『』（）]{re.escape(glyph)}", content):
            merged = gap if (gap and subsequence(rest, gap)) else rest + "".join(c for c in gap if c not in rest)
            new = with_structure(tokens, merged, "") if not any(kind == "s" for kind, _ in tokens) \
                else span.replace(glyph, "", 1)
            rule = "K7a"
        elif gap and subsequence(rest, gap) and any(c in PAIRED and c not in rest for c in gap):
            new = span.replace(content, gap) if content and content in span else with_structure(tokens, gap, "")
            rule = "K7b"
        if rule is None:
            return None
        record = self.b_only_record(k, glyph)
        if record is None:
            return None
        start, end = self.span(k1, k2)
        if self.leaves_unpaired(start, end, new):
            # Engine A's quote there leaves a quote or bracket of the page
            # without its partner: the other one is not where engine A has
            # it, which is a reading of the page.
            return question("Q-P", self.pd.scan, rule, self.text, start, end,
                            "engine A's marks here would leave a quote or bracket unpaired", engineA=gap)
        return new, rule, {"standIns": glyph, "seal": record}

    def leaves_unpaired(self, start: int, end: int, new: str) -> bool:
        """Whether writing NEW over the page's START:END leaves a closing
        quote or bracket with nothing open before it, or an opening one
        that nothing closes - unless engine A reads, later on the page, a
        closing one the page lacks there (the second pass writes it, K12)."""
        after = self.text[:start] + new + self.text[end:]
        for opener, closer in lint.BRACKETS.items():
            before_state, after_state = pair_state(self.text, opener, closer), pair_state(after, opener, closer)
            if after_state[1] > before_state[1]:
                return True
            if after_state[0] > before_state[0]:
                k = bisect.bisect_left(self.s.offsets, end)
                ia = next((self.to_a[j] for j in range(k, len(self.s.chars)) if self.to_a[j] is not None), None)
                a_rest = self.a.text[self.a.offsets[ia]:] if ia is not None else ""
                if a_rest.translate(NORM).count(closer) <= self.text[end:].translate(NORM).count(closer):
                    return True
        return False

    def b_only_record(self, k: int, glyph: str) -> dict[str, Any] | None:
        """The seal's record of the decision that wrote GLYPH at sealed
        character K from engine B alone: a question engine A read nothing
        for (a numeral question, or engine A's default with A empty)."""
        chars = self.s.chars
        for record in self.pd.record.get("adjudications") or []:
            if not isinstance(record, dict) or pp.CJK(str(record.get("resolved") or "")) != glyph:
                continue
            if pp.CJK(str(record.get("draft_reading") or "")):
                continue
            if record.get("trigger") != "numeral-disagreement" and record.get("resolved_from") != "engine-A-default":
                continue
            before = pp.CJK(str(record.get("context_before") or ""))
            after = pp.CJK(str(record.get("context_after") or ""))
            left = common_suffix(before, chars[:k])
            right = common_prefix(after, chars[k + 1:])
            if left + right >= 4 and (left or k == 0) and (right or k + 1 == len(chars)):
                return {"crop": record.get("crop"), "engineB": record.get("writer_reading"),
                        "trigger": record.get("trigger"), "resolvedFrom": record.get("resolved_from")}
        return None

    # K5: a glyph twice where engine A read it once.
    def twins(self) -> tuple[list[tuple[int, int, str, str, dict[str, Any]]], list[dict[str, Any]]]:
        out = []
        asks = []
        s, text = self.s, self.text
        done = set()
        for k in range(len(s.chars)):
            if self.to_a[k] is not None or s.chars[k] not in self.facts.aliases or k in done:
                continue
            for t in (k - 1, k + 1):
                if not (0 <= t < len(s.chars)) or self.to_a[t] is None or s.chars[t] != s.chars[k]:
                    continue
                lo, hi = min(k, t), max(k, t)
                if lo == 0 or hi + 1 >= len(s.chars):
                    break
                start, end = s.offsets[lo - 1] + 1, s.offsets[hi + 1]
                segment = text[start:end]
                ia = self.to_a[t]
                raw_before, after = self.a.gaps[ia], marks_of(self.a.gaps[ia + 1])
                sealed_marks = marks_of(segment.replace(s.chars[k], ""))
                # The second copy is engine B's glyph for a mark engine A
                # read beside the first: without such a mark there, which
                # copy is printed is a reading.
                if not set(self.facts.aliases[s.chars[k]]) & set(marks_of(raw_before) + after):
                    asks.append(question("Q-P", self.pd.scan, "K5", text, start, end,
                                        "a glyph twice where engine A read it once, and none of the marks it "
                                        "stands for beside it", engineA=raw_before + s.chars[t]))
                    done.add(k)
                    break
                # Engine B wrote the glyph once for each mark it stands for
                # and once for the character: more copies than that are
                # characters it read (a doubled character engine A read
                # once), which copy is printed is a reading.
                read = self.b_between(lo - 1, hi + 1)
                stands = sum(c in self.facts.aliases[s.chars[k]] for c in marks_of(raw_before) + after)
                if read is None or pp.CJK(read).count(s.chars[k]) > 1 + stands:
                    asks.append(question("Q-P", self.pd.scan, "K5", text, start, end,
                                        "a glyph twice where engine A read it once, and engine B read it more "
                                        "often than the marks beside it account for", engineA=raw_before + s.chars[t],
                                        engineB=read))
                    done.add(k)
                    break
                if subsequence(sealed_marks, marks_of(raw_before) + after):
                    breaks = "".join(re.findall(r"\n+", segment))
                    glyph = s.chars[k]
                    if breaks and "\n" in raw_before:
                        first, second = raw_before.split("\n", 1)
                        new = marks_of(first) + breaks + marks_of(second) + glyph + after
                    elif breaks:
                        new = marks_of(segment[:segment.index("\n")]) + breaks + glyph + after
                    else:
                        new = marks_of(raw_before) + glyph + after
                    if new != segment:
                        out.append((start, end, new, "K5", {"standIns": glyph, "engineA": raw_before + glyph}))
                    done.add(k)
                break
        return out, asks

    # K6: a stand-in engine A never reads, where engine A read a character.
    def k6(self) -> list[tuple[int, int, str, str, dict[str, Any]]]:
        out = []
        for tag, i1, i2, j1, j2 in ra.opcodes(self.a.chars, self.s.chars):
            if tag != "replace" or i2 - i1 != j2 - j1:
                continue
            for x in range(j2 - j1):
                glyph, read = self.s.chars[j1 + x], self.a.chars[i1 + x]
                if glyph in self.facts.standins() and self.facts.a_counts[glyph] == 0 and read != glyph:
                    at = self.s.offsets[j1 + x]
                    out.append((at, at + 1, read, "K6", {"standIns": glyph, "engineA": read}))
        return out

    # K8, K9, K10: bracket and line-start shapes.
    def shapes(self) -> list[tuple[int, int, str, str, dict[str, Any]]]:
        out = []
        text, s = self.text, self.s
        for match in re.finditer(r"（([〇一二三四五六七八九十]{1,2})[、，]）", text):
            ks = [bisect.bisect_left(s.offsets, match.start(1) + i) for i in range(len(match.group(1)))]
            if any(self.to_a[k] is None for k in ks):
                continue
            ia, ib = self.to_a[ks[0]], self.to_a[ks[-1]]
            before, after = marks_of(self.a.gaps[ia]), marks_of(self.a.gaps[ib + 1])
            if before.endswith("（") and after.startswith("）"):
                out.append((match.start(), match.end(), f"（{match.group(1)}）", "K8", {"engineA": f"（{match.group(1)}）"}))
        for match in re.finditer(r"[︵︶]", text):
            out.append((match.start(), match.end(), match.group().translate(NORM), "K9", {}))
        for match in re.finditer(r"(?m)^(?:[-*+] )?\[(?=[0-9０-９])", text):
            at = match.end() - 1
            line_end = text.find("\n", at)
            line = text[at:line_end if line_end >= 0 else len(text)]
            k = bisect.bisect_left(s.offsets, at)
            if "]" in line or "］" in line or k >= len(s.offsets) or self.to_a[k] is None:
                continue
            if any(c in "[［" for c in self.a.gaps[self.to_a[k]]):
                continue
            out.append((at, at + 1, "", "K10", {"engineA": self.a.gaps[self.to_a[k]]}))
        return out


def pair_state(text: str, opener: str, closer: str) -> tuple[int, int]:
    """TEXT's OPENERs left open and CLOSERs with nothing open before them."""
    depth = unopened = 0
    for c in text.translate(NORM):
        if c == opener:
            depth += 1
        elif c == closer:
            if depth:
                depth -= 1
            else:
                unopened += 1
    return depth, unopened


def common_suffix(a: str, b: str) -> int:
    n = 0
    while n < len(a) and n < len(b) and a[-1 - n] == b[-1 - n]:
        n += 1
    return n


def common_prefix(a: str, b: str) -> int:
    n = 0
    while n < len(a) and n < len(b) and a[n] == b[n]:
        n += 1
    return n


class MarksSecond:
    """K12 and K13, on the text the first pass leaves."""

    def __init__(self, pd: PageData, neighbours: tuple[str | None, str | None]):
        self.pd = pd
        self.text = pd.text
        self.s = ra.stream(pd.text)
        self.a = ra.stream(pd.a_body)
        self.b = ra.stream(pd.b_body)
        self.to_a = ra.mapping(self.a.chars, self.s.chars)
        self.to_b = ra.mapping(self.b.chars, self.s.chars)
        self.neighbours = neighbours

    def short_of_one(self, close: str) -> int | None:
        """Where the page's one unclosed opening of CLOSE's kind is, when the
        page is short of exactly one and the next page does not close it."""
        opener = lint.CLOSERS[close]
        depth: list[int] = []
        unopened = 0
        for at, c in enumerate(self.text):
            if c == opener:
                depth.append(at)
            elif c == close:
                if depth:
                    depth.pop()
                else:
                    unopened += 1
        following = self.neighbours[1]
        if following is not None:
            level = 0
            for c in following:
                if c == opener:
                    level += 1
                elif c == close:
                    if level:
                        level -= 1
                    else:
                        return None
        return depth[0] if len(depth) == 1 and not unopened else None

    def plan(self) -> Plan:
        plan = Plan()
        text, s = self.text, self.s
        opened = {close: self.short_of_one(close) for close in ("）", "」")}
        # K13's sites: (start, end, new, engine A's gap, the brackets it
        # turns - their offsets on the page - and whether engine B read a
        # bracket there).
        corners: list[tuple[int, int, str, str, set[int], bool]] = []
        for k in range(len(s.chars) + 1):
            prev = k - 1
            if k < len(s.chars) and self.to_a[k] is None:
                continue
            if prev >= 0 and self.to_a[prev] is None:
                continue
            ia = self.to_a[k] if k < len(s.chars) else len(self.a.chars)
            if prev >= 0 and ia != self.to_a[prev] + 1:
                continue
            if prev < 0 and ia != 0:
                continue
            start = s.offsets[prev] + 1 if prev >= 0 else 0
            end = s.offsets[k] if k < len(s.chars) else len(text)
            span = text[start:end]
            gap = marks_of(self.a.gaps[ia]) if ia < len(self.a.gaps) else ""
            sealed = marks_of(span)
            if sealed and len(sealed) == len(gap) and any(c in "（）" for c in sealed) \
                    and not any(c in "（）" for c in gap):
                if all(x == y or (x, y) in (("（", "「"), ("）", "」")) for x, y in zip(sealed, gap)):
                    read = ra.engine_between(self.b, self.to_b, prev, k) if prev >= 0 and k < len(s.chars) else None
                    new = span.translate(str.maketrans({"（": "「", "）": "」"}))
                    if new != span:
                        turned = {start + i for i, c in enumerate(span) if c in "（）"}
                        b_bracket = read is not None and any(c in "（）()︵︶" for c in read)
                        corners.append((start, end, new, self.a.gaps[ia], turned, b_bracket))
                    continue
            for close in ("）", "」"):
                where = opened[close]
                if where is None or where >= start:
                    continue
                if close in gap and close not in sealed and subsequence(sealed, gap.replace(close, "", 1)):
                    new = gap if not span.strip() or sealed == gap.replace(close, "", 1) else None
                    if new is None:
                        continue
                    new = with_structure(split_structure(span), new, "")
                    plan.edits.append(re_.Edit(self.pd.scan, start, end, new, rule="K12", evidence={
                        "before": span, "engineA": self.a.gaps[ia], "opened": where}))
                    opened[close] = None
                    break
        self.corner_quotes(corners, plan)
        return plan

    def corner_quotes(self, corners: Sequence[tuple[int, int, str, str, set[int], bool]], plan: Plan) -> None:
        """K13 on the sites CORNERS: a bracket turns into engine A's quote
        only with its partner on the page (the bracket that closes or opens
        it), where engine A read the quote too and engine B read no bracket;
        a bracket whose partner the page does not hold turns alone.  A pair
        that would be turned on one side only is a question: the two sides
        are read differently."""
        partner: dict[int, int] = {}
        depth: list[int] = []
        for at, c in enumerate(self.text):
            if c == "（":
                depth.append(at)
            elif c == "）" and depth:
                opener = depth.pop()
                partner[opener], partner[at] = at, opener
        live = [not b_bracket for *_, b_bracket in corners]
        changed = True
        while changed:
            changed = False
            turning = set().union(*(site[4] for site, ok in zip(corners, live) if ok)) if any(live) else set()
            for i, site in enumerate(corners):
                if live[i] and any(at in partner and partner[at] not in turning for at in site[4]):
                    live[i] = False
                    changed = True
        for (start, end, new, gap, turned, b_bracket), ok in zip(corners, live):
            if ok:
                plan.edits.append(re_.Edit(self.pd.scan, start, end, new, rule="K13", evidence={
                    "before": self.text[start:end], "engineA": gap}))
            elif not b_bracket:
                plan.questions.append(question(
                    "Q-P", self.pd.scan, "K13", self.text, start, end,
                    "engine A read a corner quote where the page holds a bracket, but not at the bracket's "
                    "partner (engine B read a bracket there, or engine A's marks differ)", engineA=gap))


# --- K-seq -------------------------------------------------------------------

@dataclass
class Figure:
    """A figure engine A read: its page, the index of engine A's character
    after it, its kind (`bracket`, `heading` - opening a heading of the page -
    or `line`), its value and whether a dot follows it."""
    page: int
    index: int
    style: str
    value: int
    dot: bool


BRACKETED = re.compile(r"[（(]\s*([0-9０-９]{1,3})\s*[)）]")
TRAILING_FIGURE = re.compile(r"(?:^|\n)[ \t]*([0-9０-９]{1,3})[ \t]*([.．])?[ \t]*$")
LINE_BREAK_FIGURE = re.compile(r"\n[ \t]*([0-9０-９]{1,3})[ \t]*([.．])?[ \t]*$")


def engine_a_figures(pd: PageData) -> list[Figure]:
    """Engine A's figures on one page, in its reading order."""
    a, s = ra.stream(pd.a_body), ra.stream(pd.text)
    to_a = ra.mapping(a.chars, s.chars)
    a_to_s = {j: k for k, j in enumerate(to_a) if j is not None}
    lines = lines_of(pd.text)
    out = []
    for k, gap in enumerate(a.gaps):
        for match in BRACKETED.finditer(gap):
            out.append(Figure(pd.scan, k, "bracket", figure_value(match.group(1)), False))
        if BRACKETED.search(gap):
            continue
        # A line's figure: after a line break in the gap, or opening the page.
        match = LINE_BREAK_FIGURE.search(gap) or (TRAILING_FIGURE.fullmatch(gap.lstrip("\n")) if k == 0 else None)
        if not match:
            continue
        at = next((a_to_s[j] for j in range(k, len(a.chars)) if j in a_to_s), None)
        style = "line"
        if at is not None:
            line = lines[pd.text.count("\n", 0, s.offsets[at])]
            if lint.HEADING.match(line.text):
                style = "heading"
        out.append(Figure(pd.scan, k, style, figure_value(match.group(1)), bool(match.group(2))))
    return out


def contents_numbers(book: Any, model: Mapping[str, Any], texts: Mapping[int, str]) -> dict[int, list[tuple[str, int]]]:
    """For each body page the contents map a line of theirs to: the contents
    line's title and the figure engine A read opening that contents line."""
    out: dict[int, list[tuple[str, int]]] = {}
    for run in (model.get("contents") or {}).get("runs") or []:
        for entry in run.get("entries") or []:
            target, page = entry.get("matchedPage"), entry.get("page")
            if target is None or page not in texts:
                continue
            pd = page_data(book, model, page, texts[page])
            s, a = ra.stream(pd.text), ra.stream(pd.a_body)
            to_a = ra.mapping(a.chars, s.chars)
            line = next((l for l in lines_of(pd.text) if pp.CJK(l.text) == entry["text"]), None)
            if line is None:
                continue
            ks = [k for k, o in enumerate(s.offsets) if line.start <= o < line.end and to_a[k] is not None]
            if not ks:
                continue
            match = TRAILING_FIGURE.search(a.gaps[to_a[ks[0]]])
            if match:
                out.setdefault(target, []).append((entry["text"], figure_value(match.group(1))))
    return out


def dot_missing(figure: Mapping[str, Any], page: int, sequence: Sequence[Figure]) -> bool:
    """Whether FIGURE (a figure a rule writes opening a line or a heading)
    is read without the dot that every figure of its kind beside it on its
    page carries."""
    index = next((i for i, f in enumerate(sequence) if f.page == page and f.index == figure.get("aIndex")), None)
    if index is None:
        return False
    own = sequence[index]
    if own.style not in ("line", "heading") or own.dot:
        return False
    before = next((f for f in reversed(sequence[:index]) if f.style == own.style), None)
    after = next((f for f in sequence[index + 1:] if f.style == own.style), None)
    same_page = [f for f in (before, after) if f is not None and f.page == page]
    return bool(same_page) and all(f.dot for f in same_page)


def sequence_problem(figure: Mapping[str, Any], page: int, title: str, sequence: Sequence[Figure],
                     contents: Mapping[int, list[tuple[str, int]]]) -> str | None:
    """K-seq for one figure a rule writes (its evidence FIGURE: value,
    style, the engine A character after it, the stand-ins it replaces): why
    it is not settled, or None.  Settled: 1; the number engine B read as CJK
    numerals there; one more than engine A's figure of its kind before it,
    or one less than the one after it; a heading's number that the contents
    give its title."""
    value = figure["figure"]
    numerals = "".join(c for c in figure.get("standIns") or "" if c in NUMERALS)
    index = next((i for i, f in enumerate(sequence) if f.page == page and f.index == figure.get("aIndex")), None)
    own = sequence[index] if index is not None else None
    style = own.style if own else figure.get("style")
    before = next((f for f in reversed(sequence[:index]) if f.style == style), None) if index is not None else None
    after = next((f for f in sequence[index + 1:] if f.style == style), None) if index is not None else None
    if dot_missing(figure, page, sequence):
        return f"figure {value} is read without the dot the figures beside it carry"
    # The page holding the figure's own value in CJK numerals, and nothing
    # else, is a reading of the print in the other script (一般 read 1般 is
    # one too): 1, and the numerals' agreement, hold for either script, so
    # only the figures around it or the contents settle it - a 1 by the 2
    # after it (a list that starts there).
    script_only = bool(numerals) and numerals == (figure.get("standIns") or "") \
        and rm.numeral_value(numerals) == value
    if not script_only and (value == 1 or (numerals and rm.numeral_value(numerals) == value)):
        return None
    if script_only and value == 1 and after is not None and after.value == 2:
        return None
    if before is not None and before.value == value - 1:
        return None
    if after is not None and after.value == value + 1 and (before is None or before.value < value):
        return None
    if style == "heading":
        for text, number in contents.get(page, []):
            if number == value and rm.entry_match(pp.variant_fold(text), pp.variant_fold(title)) >= rm.CONTENTS_SIMILARITY:
                return None
    return (f"figure {value} does not go on from engine A's figure of its kind before it "
            f"({before.value if before else 'none'}) or lead to the one after it "
            f"({after.value if after else 'none'})" + (", and the contents give its title no such number"
                                                      if style == "heading" else ""))


def marks(book: Any, model: Mapping[str, Any], texts: Mapping[int, str], order: Sequence[int],
          apply: Any, facts: BookFacts | None = None) -> Plan:
    """The mark rules over the pages ORDER: the first pass is proposed for
    the whole book, its figures checked (K-seq), what passes is applied
    through APPLY (edits -> None; the ledger), and the second pass runs on
    the texts that leaves (read again from TEXTS, which APPLY updates).
    Returns the second pass's edits and every question."""
    facts = facts or book_facts(book, model)
    plan = Plan()
    first: dict[int, list[re_.Edit]] = {}
    sequence: list[Figure] = []
    for scan in order:
        pd = page_data(book, model, scan, texts[scan])
        page_plan = Marks(pd, facts).plan()
        first[scan] = page_plan.edits
        plan.questions.extend(page_plan.questions)
        sequence.extend(engine_a_figures(pd))
    # A figure a rule writes in brackets that engine A read bare (engine B's
    # bracket glyphs round it) belongs to the bracketed figures' list.
    by_place = {(f.page, f.index): f for f in sequence}
    for scan in order:
        for edit in first[scan]:
            found = by_place.get((scan, edit.evidence.get("aIndex")))
            if found is not None and edit.evidence.get("style") == "bracket":
                found.style = "bracket"
    contents = contents_numbers(book, model, texts)
    refused: set[int] = set()
    for scan in order:
        for edit in first[scan]:
            if edit.evidence.get("figure") is None:
                continue
            line_end = texts[scan].find("\n", edit.end)
            title = pp.CJK(texts[scan][edit.end:line_end if line_end >= 0 else len(texts[scan])])
            why = sequence_problem(edit.evidence, scan, title, sequence, contents)
            if why:
                refused.add(id(edit))
                # On a contents page, the dot the figures beside it carry is
                # the book's numbering: the answer reads a colon-like mark
                # after the figure by it (decide_print).
                style = {"numberStyle": "."} if rm.page_entry(model, scan).get("contents") \
                    and dot_missing(edit.evidence, scan, sequence) else {}
                plan.questions.append(question("Q-P", scan, "K-seq", texts[scan], edit.start, edit.end, why,
                                               engineA=edit.evidence.get("engineA"), proposed=edit.after,
                                               proposedRule=edit.rule, **style))
    apply([edit for scan in order for edit in first[scan] if id(edit) not in refused])
    for scan in order:
        pd = page_data(book, model, scan, texts[scan])
        second = MarksSecond(pd, neighbour_texts(book, texts, scan)).plan()
        plan.edits.extend(second.edits)
        plan.questions.extend(second.questions)
        plan.questions.extend(left_standins(pd, facts, [(e.start, e.end) for e in second.edits]))
    return plan


def left_standins(pd: PageData, facts: BookFacts, taken: Sequence[tuple[int, int]]) -> list[dict[str, Any]]:
    """K14: each stand-in glyph of the book (M-7) that the page still holds
    where engine A read no character, on the text the first pass leaves -
    what no rule settled (MARK-STANDIN's sites): a print question (Q-P) over
    the gap between the nearest characters the page and engine A share.
    Bounded: the gap holds at most STANDIN_RUN characters engine A did not
    read, engine A read at most one character between the anchors (a glyph
    it read otherwise), and it touches no edit of the second pass (TAKEN).
    A heading or list line that holds nothing but stand-ins is left to the
    structure stages: an answer of marks alone would leave its marker
    empty.  One question a gap."""
    text = pd.text
    s, a, b = ra.stream(text), ra.stream(pd.a_body), ra.stream(pd.b_body)
    to_a, to_b = ra.mapping(a.chars, s.chars), ra.mapping(b.chars, s.chars)
    standins = facts.standins()
    out: list[dict[str, Any]] = []
    done: set[tuple[int, int]] = set()
    for k, c in enumerate(s.chars):
        if c not in standins or to_a[k] is not None:
            continue
        lo = k - 1
        while lo >= 0 and to_a[lo] is None:
            lo -= 1
        hi = k + 1
        while hi < len(s.chars) and to_a[hi] is None:
            hi += 1
        if (lo, hi) in done:
            continue
        done.add((lo, hi))
        if hi - lo - 1 > rm.STANDIN_RUN:
            continue
        a_lo = to_a[lo] if lo >= 0 else -1
        a_hi = to_a[hi] if hi < len(s.chars) else len(a.chars)
        if a_hi - a_lo - 1 > 1:
            continue
        start = s.offsets[lo] + 1 if lo >= 0 else 0
        end = s.offsets[hi] if hi < len(s.chars) else len(text)
        if any(re_.overlaps((start, end), t) or t[0] == t[1] and start <= t[0] <= end for t in taken):
            continue
        line_start = text.rfind("\n", 0, s.offsets[k]) + 1
        line_end = text.find("\n", s.offsets[k])
        line = text[line_start:line_end if line_end >= 0 else len(text)]
        if lint.HEADING.match(line) or re.match(r"\s*[-*+]\s", line):
            if all(x in standins for x in pp.CJK(line)):
                continue
        read = ra.engine_between(b, to_b, lo, hi) if lo >= 0 and hi < len(s.chars) else None
        glyphs = "".join(s.chars[j] for j in range(lo + 1, hi))
        other = a.chars[a_lo + 1] if a_hi - a_lo == 2 else None
        out.append(question("Q-P", pd.scan, "K14", text, start, end,
                            f"the page holds {glyphs!r}, engine B's stand-in(s) of this book, where engine A read "
                            + (f"{other!r}" if other else "no character") + "; no rule settled it",
                            engineA=a.gaps[a_hi] if a_hi < len(a.gaps) else "", engineB=read, characters=glyphs))
    return out


def neighbour_texts(book: Any, texts: Mapping[int, str], scan: int) -> tuple[str | None, str | None]:
    """The texts of the book's marker pages just before and after SCAN: as
    under repair when among TEXTS, else as sealed."""
    markers = [s for s in sorted(book.pages) if book.pages[s].marker]
    if scan not in markers:
        return None, None
    k = markers.index(scan)
    return (lint.neighbour_text(book, texts, markers[k - 1] if k else None),
            lint.neighbour_text(book, texts, markers[k + 1] if k + 1 < len(markers) else None))


# --- spacing -------------------------------------------------------------------

DATE = re.compile(rm.DATE_SHAPE.pattern)


def starts_with_date(line: str) -> bool:
    return bool(DATE.match(lint.LINE_PREFIX.sub("", line).strip()))


def has_date(line: str) -> bool:
    return bool(DATE.search(lint.LINE_PREFIX.sub("", line)))


def a_blocks_of(pd: PageData) -> list[int]:
    """For each character of engine A's body stream, the index of the block
    it is in (the body is the blocks joined by line breaks)."""
    starts, at = [], 0
    for block in pd.a_blocks:
        starts.append(at)
        at += len(block["text"]) + 1
    a = ra.stream(pd.a_body)
    return [bisect.bisect_right(starts, offset) - 1 for offset in a.offsets]


class Spacing:
    """P5 on one page."""

    def __init__(self, pd: PageData):
        self.pd = pd
        self.text = pd.text
        self.s = ra.stream(pd.text)
        self.a = ra.stream(pd.a_body)
        self.to_a = ra.mapping(self.a.chars, self.s.chars)
        self.block_of = a_blocks_of(pd) if pd.a_blocks and pp.CJK(pd.a_body) else []

    def aligned(self, line: Line) -> list[int]:
        """Engine A's indices of the line's characters it shares."""
        out = []
        for k in range(bisect.bisect_left(self.s.offsets, line.start), bisect.bisect_left(self.s.offsets, line.end)):
            if self.to_a[k] is not None:
                out.append(self.to_a[k])
        return out

    def one_block(self, heading: Line, line: Line) -> bool:
        """Whether engine A read the heading and the line after it as one
        block: the line's first character engine A shares is in a block that
        also holds the heading's (or, for a heading engine A shares no
        character of, holds the heading's figures and characters before it)."""
        if not self.block_of:
            return False
        after = self.aligned(line)
        if not after:
            return False
        block = self.block_of[after[0]]
        mine = self.aligned(heading)
        if mine:
            return any(self.block_of[j] == block for j in mine)
        text = self.pd.a_blocks[block]["text"] if 0 <= block < len(self.pd.a_blocks) else ""
        lead_at = self.a.offsets[after[0]] - sum(len(b["text"]) + 1 for b in self.pd.a_blocks[:block])
        return bool(lint.line_core(text[:max(0, lead_at)]))

    def plan(self) -> Plan:
        plan = Plan()
        lines = lines_of(self.text)
        for first, second in zip(lines, lines[1:]):
            if not first.text.strip() or not second.text.strip():
                continue
            one, two = lint.HEADING.match(first.text), lint.HEADING.match(second.text)
            if not (one or two):
                continue
            if one and not two and self.one_block(first, second) and not has_date(first.text) \
                    and not starts_with_date(second.text):
                # A heading engine A read in one block with the line after
                # it, no date between them: the heading printed over two
                # lines, or a run-in lead (the heading stage settles which),
                # not a heading without its blank line.  A date line ends a
                # heading's block.
                continue
            plan.edits.append(re_.Edit(self.pd.scan, first.end, first.end, "\n", rule="P5", evidence={
                "heading": first.text if one else second.text, "where": "after" if one else "before"}))
        return plan


def spacing(book: Any, model: Mapping[str, Any], texts: Mapping[int, str], order: Sequence[int]) -> Plan:
    """P5 over the pages ORDER."""
    plan = Plan()
    for scan in order:
        plan.edits.extend(Spacing(page_data(book, model, scan, texts[scan])).plan().edits)
    return plan
