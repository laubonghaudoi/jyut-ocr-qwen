#!/usr/bin/env python3
"""The first of three deliveries: the book as engine B read it, unproofread.

The user no longer waits for the end of phase 3 to see the book.  They get it
three times (SKILL.md, 分三次交付):

1. draft.md, this script, as soon as both OCR engines are done: engine B's
   text, page after page, no model asked.  Seconds, not hours.
2. proofreading.md, scripts/build_progress.py, rebuilt while phase 3 runs:
   the pages sealed so far as proofread, every other page as in the draft.
3. final.md and doubts.md, scripts/finish_book.py (SKILL.md 〈做完之後〉), once
   phase 3 has sealed the book: assembled, repaired and finalized.

Why engine B's text and not engine A's: engine A reads the columns of a
vertical page out of order.  Measured on the golden pages: 75.8% CER for
engine A's text against 5.8% for engine B's.

What the draft is:

- the pages in scan order, as the page manifest lists them; a page the
  manifest marks with no marker expected (a blank or duplicate scan) or as
  blank is left out (without a manifest, the pages found in the OCR and
  render folders; none found anywhere: not a book folder, nothing written);
- each page's text as engine B wrote it (ocr-hunyuan/page-NNNN.txt), without
  its grounding boxes (proofread_pages.strip_grounding, as phase 3 reads it);
- running heads and folios taken off conservatively (EdgeFurniture): the
  book profile does not exist yet, so what is furniture is learned from
  engine B's own text - stretches that recur at the page edges across the
  book, and folios that follow the page sequence;
- no page markers; a page break is a paragraph break;
- a page with no engine B file is a visible gap line naming its scan page,
  and so is a page engine B read nothing on (a leaf the manifest does not
  call blank: a plate, or a page the engine failed on);
- where engine B looped - wrote one stretch back to back until its tokens ran
  out, a page of thousands of one character - the stretch is written once and
  its repeats are a visible gap line naming the scan page (cut_loops);
- a short header, in Cantonese, saying it is unproofread OCR and when it was
  built.

It never stops the pipeline: a page it cannot read is a gap, a manifest it
cannot read means the pages found on disk, and the file is written atomically
(temp file, then rename), so a reader never sees half of it.  Exit 0 when the
draft is written, 1 only when nothing could be written; the next step of the
pipeline runs either way.

Usage:
    python3 scripts/build_draft.py BOOK [--ocr-dir ocr-hunyuan] [--manifest page-manifest.json]
        [--output draft.md]

Relative paths are taken inside BOOK.  One line is printed: the file, the
page counts, the running heads learned.
"""

from __future__ import annotations

import argparse
from collections import Counter
import contextlib
from dataclasses import dataclass, field
from datetime import datetime
import difflib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Iterable, Mapping, Sequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import proofread_pages as pp  # noqa: E402

DRAFT_NAME = "draft.md"
OCR_DIRNAME = "ocr-hunyuan"
MANIFEST_NAME = "page-manifest.json"
RENDERS_DIRNAME = "renders"
PAGE_FILE = re.compile(r"page-(\d{4,})\.(?:txt|png)")

# --- running heads -----------------------------------------------------------
#
# Measured on engine B's drafts of the calibration corpus (seven books): in
# four of them engine B writes a page as one or two lines (1.1 to 2.2 on
# average), the running head and the folio glued to the text at the start or
# the end of the page.  A test
# on whole lines finds nothing there, so what is learned is a stretch at the
# page's edge, and what is taken off is that stretch where a page starts or
# ends with it.
#
# A stretch is learned with every run of numerals in it read as one mark
# (NUMERAL): a book printing its volume in its head, or a folio beside it,
# otherwise splits one head into as many stretches as it has volumes or
# hundreds of pages, and a stretch that takes in the folio's first figure
# (the head, then 一 on every page from 100 to 199) is then learned as the
# head.  A stretch neither starts nor ends with the mark: numerals at a
# head's ends are the folio's, which the folio rules take off.
#
# Folded, a date or a numbered article opening many pages (民國十一年二月
# 十五日, 第三條...) is one stretch too, and it is text.  The numerals of a
# head name a part of the book - a volume, a chapter - that runs over many
# pages; those of a date or an article name that page's text alone.  So a
# page counts towards a stretch holding the mark only when the stretch reads
# the same, numerals and all, on another page too (learn_heads).  Measured on
# the corpus's engine B drafts (nine books): every draft the same as without
# this rule, byte for byte; on made-up books (tests/check_deliveries.py)
# without it a date or an article opening one page in six is cut from each.
NUMERAL = "\ue000"
# A stretch is the book's furniture when it opens or closes this share of the
# pages that have text, and EDGE_MIN_PAGES at least.  Body text does not
# recur at the very edge of the page.  Measured on the corpus: what
# learn_heads keeps at 5% is three books' running heads (one of them a
# reprint series' name) and nothing else, the other four books keeping
# none; unfolded, the head of a book printing its volume in it stands on 5.5%
# to 9.7% of the book's pages, volume by volume.
EDGE_SHARE = 0.05
EDGE_MIN_PAGES = 5
# A head is 4 to 40 characters: shorter recurs by chance (a two-character
# word at the edge), longer is not a margin's line (MARGIN_FURNITURE_LIMIT).
HEAD_MIN = 4
HEAD_MAX = pp.MARGIN_FURNITURE_LIMIT
# Beside the characters (pp.CJK), only these may stand inside a head.
HEAD_INNER = frozenset("·・ ")
# Where the head ends: a stretch that goes on with the same character on this
# share of the pages it stands on is not the whole head (its own characters
# follow it nearly always; what follows its end - the text, the folio, a
# figure misread beside it - varies).  Of the stretches over the floor the
# commonest whole one is the head, and any stretch holding it or held by it is
# not another head (learn_heads).
EXTEND_SHARE = 0.8
# A head misread by a character or two is still the head when it is this long
# and this like it (pp.is_running_head's similarity), with its inner end - the
# character next to the text - read the same, so a stretch that runs a
# character into the text is not taken for it.
FUZZY_MIN = 8
FUZZY_RATIO = 0.8

# --- folios ------------------------------------------------------------------
#
# A folio between a head and the page's edge is furniture by its place.  One
# on the text side of the head, or a line holding only a numeral, could be
# text: it is taken off only when its value follows the page sequence - two
# other pages within FOLIO_WINDOW scan pages carry a folio at the same offset
# from their scan page (one printed page per scan, or two leaves per scan).
FOLIO_MAX = 6
FOLIO_WINDOW = 10
FOLIO_SUPPORT = 2
FOLIO_SLOPES = (1, 2)
DIGIT_VALUES = {**{c: i for i, c in enumerate("〇一二三四五六七八九")}, "零": 0, "○": 0, "◯": 0,
                **{str(i): i for i in range(10)}, **{chr(0xFF10 + i): i for i in range(10)}}
FOLIO_UNITS = {"十": 10, "百": 100, "千": 1000}
FOLIO_CHARS = frozenset(DIGIT_VALUES) | frozenset(FOLIO_UNITS)
# What may wrap a folio printed as a line of its own: "- 12 -", "（一二）", "第十二頁".
FOLIO_LINE = re.compile(r"^[\s\-—－–·•()（）\[\]〔〕【】]*第?(?P<folio>[^\s\-—－–·•()（）\[\]〔〕【】第頁页]{1,%d})[頁页]?"
                        r"[\s\-—－–·•()（）\[\]〔〕【】]*$" % FOLIO_MAX)
# The heading marker engine B sometimes writes before a margin's line.
HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+")

# --- engine B's loops ----------------------------------------------------------
#
# Engine B sometimes does not stop: from some point on a page it writes one
# stretch back to back until its tokens run out.  Measured on engine B's
# drafts of the calibration corpus (1,279 distinct page files, eight books):
# 18 pages hold a stretch of LOOP_MIN_COPIES or more copies of a unit of at
# most LOOP_PERIOD_MAX characters that holds text, LOOP_MIN_CHARS characters
# or more in all - each 3,958 to 12,517 characters, the unit one character (a
# page of 口) up to a table row of 150, every one running to the file's end,
# its last copy cut short - and the longest such repetition under
# LOOP_MIN_CHARS is 120 characters: one table cell printed ten times over,
# which is text.  Copied, a loop is thousands of characters of noise the user
# scrolls through; cut, the unit stays once (the engine read it) and a gap
# line says what was not copied.  A unit of markup alone (empty table cells:
# 90 characters at most in engine B's drafts) holds no text to lose and may
# be a table's printed shape: kept.
LOOP_PERIOD_MAX = 200
LOOP_MIN_COPIES = 5
LOOP_MIN_CHARS = 1000
LOOP = re.compile(r"(.{1,%d}?)\1{%d,}" % (LOOP_PERIOD_MAX, LOOP_MIN_COPIES - 1), re.DOTALL)
MARKUP = re.compile(r"<[^<>]*>")
# How much of the unit the gap line quotes.
LOOP_SHOWN = 12

HEADER_DRAFT = ("> **未校對草稿**：呢份係 OCR 引擎直接讀出嚟嘅文字，未經校對——錯字、漏字、字序錯、符號錯都會有；"
                "書眉同頁碼係按全書重複出現嘅字粗略刪咗，頁同頁之間淨係分段。校對完嘅定稿係 `final.md`。")
GAP_LINE = "〔掃描第 {page} 頁：冇 OCR 文字〕"
EMPTY_LINE = "〔掃描第 {page} 頁：OCR 冇讀到字〕"
LOOP_LINE = "〔掃描第 {page} 頁：OCR 喺呢度將「{unit}」再重複咗 {repeats} 次，冇抄{rest}〕"
# Said when nothing follows the loop: the engine never read past it.
LOOP_TO_END = "；之後 OCR 冇再讀落去，呢頁其餘嘅字要睇原書"


@dataclass
class Loop:
    """A stretch engine B wrote back to back (find_loops)."""
    unit: str
    copies: int                      # whole copies; the draft keeps the first
    to_end: bool                     # nothing follows it on the page


@dataclass
class DraftPage:
    scan_page: int
    text: str | None                 # None: no engine B text for the page
    cuts: list[str] = field(default_factory=list)   # what was taken off as furniture
    read_nothing: bool = False       # engine B's file holds no text
    loops: list[Loop] = field(default_factory=list)  # its loops, each cut to a gap line


@dataclass
class DraftBook:
    book: Path
    pages: list[DraftPage]
    skipped: list[int]
    heads: list[str]
    note: str | None                 # why the pages are not the manifest's


# --- pages -----------------------------------------------------------------

def inside(book: Path, path: Path | str) -> Path:
    """PATH, relative paths taken inside BOOK."""
    path = Path(os.path.expanduser(str(path)))
    return path if path.is_absolute() else book / path


def found_pages(*directories: Path) -> list[int]:
    pages: set[int] = set()
    for directory in directories:
        with contextlib.suppress(OSError):
            for name in os.listdir(directory):
                match = PAGE_FILE.fullmatch(name)
                if match:
                    pages.add(int(match.group(1)))
    return sorted(pages)


def skipped_by_manifest(record: Mapping) -> bool:
    """A page the manifest says carries no text of its own: no marker expected
    (release-gate.md: a scan checked on its image as blank, a duplicate or the
    like), or blank.  A scan marked `relation: exact_duplicate` is not
    left out by that alone: the label can stand on both scans of a pair, and
    the finished book keeps every scan whose marker is expected - the draft
    would lose a page the book has."""
    return record.get("marker_expected") is False or record.get("content") == "blank"


def book_pages(book: Path, manifest: Path, ocr: Path) -> tuple[list[int], list[int], str | None]:
    """(the pages in scan order, the pages the manifest leaves out, a note when
    the manifest could not be read and the pages are those found on disk)."""
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        records = data["pages"]
        if not isinstance(records, list):
            raise TypeError("its pages are not a list")
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        why = "missing" if isinstance(error, FileNotFoundError) else f"unreadable: {error}"
        return (found_pages(ocr, book / RENDERS_DIRNAME), [],
                f"no page manifest ({manifest.name} {why}); the pages found in {ocr.name}/ and renders/")
    pages: dict[int, bool] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        number = record.get("scan_page")
        if isinstance(number, int) and not isinstance(number, bool) and number > 0 and number not in pages:
            pages[number] = skipped_by_manifest(record)
    if not pages:
        return (found_pages(ocr, book / RENDERS_DIRNAME), [],
                f"no page manifest ({manifest.name} lists no scan page); the pages found in {ocr.name}/ and renders/")
    return ([page for page in sorted(pages) if not pages[page]],
            [page for page in sorted(pages) if pages[page]], None)


def engine_b_lines(ocr: Path, page: int) -> list[str] | None:
    """Engine B's text of PAGE as lines, without its grounding boxes, blank
    lines at the ends dropped; None when there is no file to read."""
    try:
        raw = (ocr / f"page-{page:04d}.txt").read_bytes()
    except OSError:
        return None
    text = raw.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in pp.strip_grounding(text).split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def find_loops(text: str) -> list[tuple[int, int, str]]:
    """(start, end, unit) of each loop in TEXT: a unit of at most
    LOOP_PERIOD_MAX characters, holding text outside markup, back to back
    LOOP_MIN_COPIES times or more and LOOP_MIN_CHARS characters or more in
    all.  A last copy cut short is part of the loop only where nothing but
    blank follows it (the engine's tokens ran out in the middle of it); text
    after it is the page's."""
    if len(text) < LOOP_MIN_CHARS:
        return []
    found = []
    at = 0
    while True:
        match = LOOP.search(text, at)
        if match is None:
            return found
        start, end, unit = match.start(), match.end(), match.group(1)
        if not holds_text(unit):
            at = end                  # markup alone: no stretch of it holds text
            continue
        if end - start < LOOP_MIN_CHARS:
            # The shortest unit repeating here may not be the loop's: a loop
            # can start with a run of one character.  Look again one on.
            at = start + 1
            continue
        tail = 0
        while tail < len(unit) - 1 and end + tail < len(text) and text[end + tail] == unit[tail]:
            tail += 1
        if tail and not text[end + tail:].strip():
            end += tail
        found.append((start, end, unit))
        at = end


def from_tag(unit: str) -> str:
    """A loop's UNIT read from its first < on, where a tag starts.  A unit
    is any rotation of the stretch that repeats - it starts where the loop
    does, taking in a tag's closing > of the text before it - and read from
    a tag's start its tags are whole."""
    at = unit.find("<")
    return unit[at:] + unit[:at] if at > 0 else unit


def holds_text(unit: str) -> bool:
    """Whether a loop's UNIT holds anything but markup."""
    return bool(MARKUP.sub("", from_tag(unit)).strip())


def loop_line(page: int, loop: Loop) -> str:
    shown_unit = " ".join(MARKUP.sub(" ", from_tag(loop.unit)).split())
    if len(shown_unit) > LOOP_SHOWN:
        shown_unit = shown_unit[:LOOP_SHOWN] + "…"
    return LOOP_LINE.format(page=page, unit=shown_unit, repeats=loop.copies - 1,
                            rest=LOOP_TO_END if loop.to_end else "")


def cut_loops(page: int, lines: Sequence[str]) -> tuple[list[str], list[Loop]]:
    """PAGE's lines with each loop (find_loops) cut: its unit kept once where
    the loop starts, then a gap line (LOOP_LINE) as a paragraph of its own,
    then the text after the loop, if any.  Lines with no loop come back as
    they are."""
    text = "\n".join(lines)
    found = find_loops(text)
    if not found:
        return list(lines), []
    pieces: list[str] = []
    loops: list[Loop] = []
    at = 0
    for start, end, unit in found:
        loop = Loop(unit, (end - start) // len(unit), not text[end:].strip())
        pieces += [text[at:start + len(unit)].strip("\n").rstrip(), loop_line(page, loop)]
        loops.append(loop)
        at = end
    pieces.append(text[at:].strip("\n").rstrip())
    return "\n\n".join(piece for piece in pieces if piece.strip()).split("\n"), loops


# --- running heads and folios ---------------------------------------------------

def is_head_char(c: str) -> bool:
    return bool(pp.CJK(c))


def edge_text(line: str) -> tuple[str, str]:
    """(the heading marker, the rest) of a line, the rest stripped."""
    match = HEADING.match(line)
    marker = match.group(0) if match else ""
    return marker, line[len(marker):].strip()


def folio_lengths(text: str, start: bool) -> list[int]:
    """The lengths of the folios TEXT can open (START) or close with, longest
    first: numerals, and at most one character that is not one - a figure
    misread - with figures beyond it towards the edge and two figures at
    least (pp.folio_figures)."""
    lengths = []
    for size in range(1, min(FOLIO_MAX, len(text)) + 1):
        piece = text[:size] if start else text[len(text) - size:]
        if folio_value(piece, outward_from_head=not start) is not None:
            lengths.append(size)
    return sorted(lengths, reverse=True)


def folio_value(piece: str, outward_from_head: bool = True) -> frozenset[int] | None:
    """The values PIECE can stand for as a folio, in its reading order; None
    when it is not one.  OUTWARD_FROM_HEAD: whether PIECE's first character
    is the one next to the head (a folio closing a page after its head), which
    places the misread figure: it must have figures beyond it towards the
    page's edge."""
    if not piece or any(c.isspace() for c in piece):
        return None
    misread = [i for i, c in enumerate(piece) if c not in FOLIO_CHARS]
    figures = len(piece) - len(misread)
    if len(misread) > 1 or (misread and figures < 2):
        return None
    if misread:
        beyond = piece[misread[0] + 1:] if outward_from_head else piece[:misread[0]]
        if not beyond:
            return None
    if any(c in FOLIO_UNITS for c in piece):
        return None if misread else _unit_value(piece)
    values = [0]
    for c in piece:
        digits = range(10) if c not in DIGIT_VALUES else (DIGIT_VALUES[c],)
        values = [value * 10 + digit for value in values for digit in digits]
    return frozenset(values)


def _unit_value(piece: str) -> frozenset[int] | None:
    """九十三, 一百零七, 十二: numerals written with units."""
    total, digit, last_unit = 0, None, 10 ** 9
    for c in piece:
        if c in FOLIO_UNITS:
            unit = FOLIO_UNITS[c]
            if unit >= last_unit:
                return None
            total += (1 if digit is None else digit) * unit
            digit, last_unit = None, unit
        elif c in DIGIT_VALUES:
            if digit not in (None, 0):
                return None         # two figures in a row: not a numeral with units
            digit = DIGIT_VALUES[c]
        else:
            return None
    return frozenset({total + (digit or 0)})


def folded(text: str) -> tuple[str, list[int]]:
    """TEXT with each run of numerals read as NUMERAL, and where each of its
    characters starts in TEXT (with len(TEXT) at the end)."""
    out: list[str] = []
    starts: list[int] = []
    index = 0
    while index < len(text):
        starts.append(index)
        if text[index] in FOLIO_CHARS:
            while index < len(text) and text[index] in FOLIO_CHARS:
                index += 1
            out.append(NUMERAL)
        else:
            out.append(text[index])
            index += 1
    starts.append(len(text))
    return "".join(out), starts


def literal(head: str) -> int:
    """How many characters of HEAD are characters, not the numeral mark."""
    return sum(1 for c in head if c != NUMERAL)


def edge_stretches(text: str, start: bool) -> Iterable[tuple[str, str]]:
    """The stretches of HEAD_MIN to HEAD_MAX characters TEXT, folded, opens
    (START) or closes with, as long as they hold only characters, numeral
    marks and HEAD_INNER, and neither start nor end with a mark: each folded,
    and as TEXT has it."""
    folds, starts = folded(text)
    for size in range(1, min(HEAD_MAX, len(folds)) + 1):
        c = folds[size - 1] if start else folds[len(folds) - size]
        if not (is_head_char(c) or c == NUMERAL or (c in HEAD_INNER and size > 1)):
            break
        stretch = folds[:size] if start else folds[len(folds) - size:]
        if is_head_char(stretch[0]) and is_head_char(stretch[-1]) and literal(stretch) >= HEAD_MIN:
            yield stretch, (text[:starts[size]] if start else text[starts[len(folds) - size]:])


def numerals_at(text: str, start: bool) -> int:
    """How many numerals TEXT opens (START) or closes with."""
    size = 0
    while size < len(text) and (text[size] if start else text[len(text) - 1 - size]) in FOLIO_CHARS:
        size += 1
    return size


def edge_lines(lines: Sequence[str]) -> list[tuple[str, bool]]:
    """The lines a page opens and closes with, past a line holding only a
    folio, each with whether it is the start."""
    filled = [line for line in lines if line.strip()]
    first = next((line for line in filled if lone_folio(line) is None), None)
    last = next((line for line in reversed(filled) if lone_folio(line) is None), None)
    return [(line, start) for line, start in ((first, True), (last, False)) if line is not None]


def learn_heads(pages: Mapping[int, Sequence[str] | None]) -> list[str]:
    """The book's running heads, folded (NUMERAL for a run of numerals),
    longest first: of the stretches that open or close EDGE_SHARE of the pages
    with text (EDGE_MIN_PAGES at least), each counted once a page and past a
    folio at the edge - one holding NUMERAL only on the pages where it reads
    the same, numerals and all, as on another page - the commonest that no
    longer one goes on from on EXTEND_SHARE of the pages it stands on (all of
    them); then the next commonest that neither holds nor is held by a head
    already taken, and so on."""
    found: list[dict[str, set[str]]] = []      # a page's stretches, each with its readings
    readings: Counter = Counter()              # (stretch, reading) -> pages
    for lines in pages.values():
        if not lines:
            continue
        seen: dict[str, set[str]] = {}
        for line, start in edge_lines(lines):
            text = edge_text(line)[1]
            # Past the numerals at the edge only: a figure misread
            # (folio_value) lets a folio run into the head, whose end would
            # then be learned without its last characters.
            past = numerals_at(text, start)
            for stretch, reading in edge_stretches(text[past:] if start else text[:len(text) - past], start):
                seen.setdefault(stretch, set()).add(reading)
        found.append(seen)
        readings.update((stretch, reading) for stretch, read_as in seen.items() if NUMERAL in stretch
                        for reading in read_as)
    counts: Counter = Counter()                # the pages a stretch stands on
    kept: Counter = Counter()                  # of them, those where its numerals recur
    for seen in found:
        counts.update(seen.keys())
        kept.update(stretch for stretch, read_as in seen.items()
                     if NUMERAL not in stretch or any(readings[stretch, reading] > 1 for reading in read_as))
    floor = max(EDGE_MIN_PAGES, math.ceil(EDGE_SHARE * len(found)))
    common = {stretch: count for stretch, count in kept.items() if count >= floor}
    # Where a head ends is judged on every page a stretch stands on, its
    # numerals recurring or not: a head followed by its chapter's number is
    # not cut short before the number where that number is read once only,
    # and a stretch followed by a date on most of its pages does not end
    # there - nor is the date learned - so it is no head.
    longer = {stretch: count for stretch, count in counts.items() if count >= floor}
    heads: list[str] = []
    for stretch in sorted(common, key=lambda s: (-common[s], -len(s), s)):
        if any(head in stretch or stretch in head for head in heads):
            continue
        if any(len(other) > len(stretch) and stretch in other and count >= EXTEND_SHARE * counts[stretch]
               for other, count in longer.items()):
            continue
        heads.append(stretch)
    return sorted(heads, key=lambda s: (-len(s), s))


def head_at(text: str, at: int, heads: Sequence[str], start: bool) -> int | None:
    """How many characters of TEXT, from AT towards the text (START: AT is
    where they begin; else AT is where they end), are one of the folded
    HEADS: the longest exact copy, else the likest misread copy (FUZZY_MIN,
    FUZZY_RATIO, the inner end read the same)."""
    folds, starts = folded(text)
    if at not in starts:
        return None                  # inside a run of numerals
    at = starts.index(at)

    def raw(size: int) -> int:
        return starts[at + size] - starts[at] if start else starts[at] - starts[at - size]

    for head in heads:
        piece = folds[at:at + len(head)] if start else folds[max(0, at - len(head)):at]
        if piece == head:
            return raw(len(head))
    best: tuple[float, int] | None = None
    for head in heads:
        if literal(head) < FUZZY_MIN:
            continue
        for size in (len(head), len(head) - 1, len(head) + 1):
            piece = folds[at:at + size] if start else folds[max(0, at - size):at]
            if len(piece) != size or not all(is_head_char(c) or c == NUMERAL or c in HEAD_INNER for c in piece):
                continue
            if (piece[-1] != head[-1]) if start else (piece[0] != head[0]):
                continue
            ratio = difflib.SequenceMatcher(None, piece, head, autojunk=False).ratio()
            if ratio >= FUZZY_RATIO and (best is None or ratio > best[0]):
                best = (ratio, size)
    return raw(best[1]) if best else None


def shown(head: str) -> str:
    """A folded head as the report line prints it."""
    return head.replace(NUMERAL, "#")


@dataclass
class Edge:
    """What a page's start or end holds of the book's furniture."""
    line: int                        # the line the head is on
    head: int = 0                    # characters of the head and the folio outside it
    outer: frozenset[int] | None = None   # that folio's values
    inner: str = ""                  # the numerals on the text side of the head, in text order
    inner_line: int | None = None    # or a line of its own there holding a folio
    lone: int | None = None          # a line at the edge holding only a numeral
    lone_value: frozenset[int] | None = None


def find_edge(lines: list[str], heads: Sequence[str], start: bool) -> Edge | None:
    """The furniture at one end of a page, before the page sequence is known."""
    order = range(len(lines)) if start else range(len(lines) - 1, -1, -1)
    order = [i for i in order if lines[i].strip()]
    if not order:
        return None
    edge = Edge(order[0])
    value = lone_folio(lines[order[0]])
    if value is not None:
        edge.lone, edge.lone_value = order[0], value
        if len(order) == 1:
            return edge
        edge.line = order[1]
    text = edge_text(lines[edge.line])[1]
    for past in [*folio_lengths(text, start), 0]:
        at = past if start else len(text) - past
        size = head_at(text, at, heads, start)
        if size is None:
            continue
        piece = text[:past] if start else text[len(text) - past:]
        edge.head = past + size
        edge.outer = folio_value(piece, outward_from_head=not start) if past else None
        rest = text[edge.head:] if start else text[:len(text) - edge.head]
        edge.inner = inner_numerals(rest, start)
        if not rest.strip():
            following = [i for i in order if (i > edge.line if start else i < edge.line)]
            if following and lone_folio(lines[following[0]]) is not None:
                edge.inner_line = following[0]
        return edge
    return edge if edge.lone is not None else None


def inner_numerals(rest: str, start: bool) -> str:
    """The run of folio characters REST opens (START) or closes with, with one
    misread figure at most (folio_value), in text order."""
    rest = rest.strip()
    run = ""
    for size in range(1, min(FOLIO_MAX, len(rest)) + 1):
        piece = rest[:size] if start else rest[len(rest) - size:]
        if all(c in FOLIO_CHARS for c in piece) or folio_value(piece, outward_from_head=start) is not None:
            run = piece
    return run


def lone_folio(line: str) -> frozenset[int] | None:
    """The values of a line that holds only a folio numeral, or None."""
    match = FOLIO_LINE.match(edge_text(line)[1])
    if not match or any(c not in FOLIO_CHARS for c in match.group("folio")):
        return None
    return folio_value(match.group("folio"))


def supported(page: int, values: frozenset[int] | None, evidence: Mapping[int, list[int]]) -> bool:
    """Whether VALUES as PAGE's folio follows the page sequence: under one
    slope, FOLIO_SUPPORT other pages within FOLIO_WINDOW carry a folio at the
    same offset from their scan page."""
    if not values:
        return False
    for slope in FOLIO_SLOPES:
        offsets = {slope * page - value for value in values}
        near = {other for other in range(page - FOLIO_WINDOW, page + FOLIO_WINDOW + 1) if other != page
                for value in evidence.get(other, ()) if slope * other - value in offsets}
        if len(near) >= FOLIO_SUPPORT:
            return True
    return False


class EdgeFurniture:
    """The book's running heads and folios, learned from engine B's pages."""

    def __init__(self, pages: Mapping[int, Sequence[str] | None]):
        self.heads = learn_heads(pages)
        self.edges: dict[int, list[tuple[Edge, bool]]] = {}
        # Folios whose value is certain (one reading, no misread figure): the
        # evidence the others are checked against.
        self.evidence: dict[int, list[int]] = {}
        for page, lines in pages.items():
            if not lines:
                continue
            found = []
            for start in (True, False):
                edge = find_edge(list(lines), self.heads, start)
                if edge is None:
                    continue
                found.append((edge, start))
                values = [edge.outer, edge.lone_value]
                if edge.inner:
                    values.append(folio_value(edge.inner, outward_from_head=start))
                if edge.inner_line is not None:
                    values.append(lone_folio(lines[edge.inner_line]))
                self.evidence.setdefault(page, []).extend(
                    next(iter(v)) for v in values if v is not None and len(v) == 1)
            self.edges[page] = found

    def strip(self, page: int, lines: Sequence[str]) -> tuple[list[str], list[str]]:
        """PAGE's lines with its furniture taken off, and what was taken off.
        What each edge takes off is counted on the lines as engine B wrote
        them, then taken off at once: a page of one line may lose a head at
        both ends, never the same characters twice."""
        lines = list(lines)
        cuts: list[str] = []
        drop: set[int] = set()
        trim: dict[int, list[int]] = {}         # line -> [from its start, from its end]
        for edge, start in self.edges.get(page, []):
            if edge.lone is not None and supported(page, edge.lone_value, self.evidence):
                cuts.append(lines[edge.lone].strip())
                drop.add(edge.lone)
            if not edge.head:
                continue
            text = edge_text(lines[edge.line])[1]
            rest = text[edge.head:] if start else text[:len(text) - edge.head]
            size = edge.head
            folio = self.inner_folio(page, edge.inner, start)
            if folio:
                size += len(rest) - len(rest.lstrip() if start else rest.rstrip()) + len(folio)
            cuts.append(text[:size] if start else text[len(text) - size:])
            trim.setdefault(edge.line, [0, 0])[0 if start else 1] = size
            if not rest.strip() and edge.inner_line is not None and \
                    supported(page, lone_folio(lines[edge.inner_line]), self.evidence):
                cuts.append(lines[edge.inner_line].strip())
                drop.add(edge.inner_line)
        for index, (head, tail) in trim.items():
            marker, text = edge_text(lines[index])
            if head + tail >= len(text):
                drop.add(index)
            else:
                lines[index] = marker + text[head:len(text) - tail].strip()
        kept = [line for index, line in enumerate(lines) if index not in drop]
        while kept and not kept[0].strip():
            kept.pop(0)
        while kept and not kept[-1].strip():
            kept.pop()
        return kept, cuts

    def inner_folio(self, page: int, run: str, start: bool) -> str:
        """The longest piece of RUN, from the head's side, that is PAGE's folio
        by the page sequence; "" when none is."""
        for size in range(len(run), 0, -1):
            piece = run[:size] if start else run[len(run) - size:]
            if supported(page, folio_value(piece, outward_from_head=start), self.evidence):
                return piece
        return ""


# --- the draft -----------------------------------------------------------------

def draft_book(book: Path, ocr: Path | str = OCR_DIRNAME, manifest: Path | str = MANIFEST_NAME) -> DraftBook:
    """Every page of BOOK as the draft writes it."""
    book = Path(book)
    ocr, manifest = inside(book, ocr), inside(book, manifest)
    pages, skipped, note = book_pages(book, manifest, ocr)
    if not pages and not skipped:
        # Not a book folder (the proofread folder passed for it, a typo): a
        # file of no page there would be a delivery of nothing, in the
        # wrong place.
        raise FileNotFoundError(f"no page found in {book}: no page manifest listing one, no page in "
                                f"{ocr.name}/ or {RENDERS_DIRNAME}/ - is it the book folder?")
    read: dict[int, list[str] | None] = {}
    loops: dict[int, list[Loop]] = {}
    for page in pages:
        lines = engine_b_lines(ocr, page)
        if lines is not None:
            # Before the furniture is learned: a loop at a page's edge is no
            # stretch the book prints there.
            lines, loops[page] = cut_loops(page, lines)
        read[page] = lines
    furniture = EdgeFurniture(read)
    out = []
    for page in pages:
        lines = read[page]
        if lines is None:
            out.append(DraftPage(page, None))
            continue
        kept, cuts = furniture.strip(page, lines)
        out.append(DraftPage(page, "\n".join(kept), cuts, read_nothing=not lines, loops=loops[page]))
    return DraftBook(book, out, skipped, furniture.heads, note)


def text_block(text: str) -> str | None:
    """A page's text as it goes into a delivery: None when it has none."""
    text = text.strip("\n")
    return text if text.strip() else None


def draft_block(page: DraftPage) -> str | None:
    """A page as the draft writes it: its text, or the line saying why there
    is none (no engine B file, or nothing read); None for a page whose text
    was all furniture."""
    if page.text is None:
        return GAP_LINE.format(page=page.scan_page)
    if page.read_nothing:
        return EMPTY_LINE.format(page=page.scan_page)
    return text_block(page.text)


def built_at(now: datetime | None = None) -> str:
    """The local time a delivery is built, to the minute, with its offset."""
    now = (now or datetime.now()).astimezone()
    return f"{now:%Y-%m-%d %H:%M} UTC{now.isoformat(timespec='minutes')[-6:]}"


def join_pages(blocks: Iterable[str | None]) -> str:
    return "\n\n".join(block for block in blocks if block is not None)


def render_draft(draft: DraftBook, when: str) -> str:
    missing = sum(1 for page in draft.pages if page.text is None)
    counts = f"共 {len(draft.pages)} 頁"
    if draft.skipped:
        counts += f"（略過 {len(draft.skipped)} 頁空白或者重複嘅掃描）"
    if missing:
        counts += f"，{missing} 頁冇 OCR 文字"
    looped = sum(1 for page in draft.pages if page.loops)
    if looped:
        counts += f"，{looped} 頁 OCR 不停重複同一段字，重複嘅部分冇抄"
    header = f"{HEADER_DRAFT}\n>\n> 建立時間：{when}；{counts}。\n"
    body = join_pages(draft_block(page) for page in draft.pages)
    return header + ("\n" + body + "\n" if body else "")


def atomic_write(path: Path, text: str) -> None:
    """Write TEXT to PATH through a temporary file beside it and a rename, so a
    reader sees the old file or the new one, never half of one."""
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(text.encode("utf-8"))
            out.flush()
            os.fsync(out.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("book", type=Path, help="the book folder (renders/, page-manifest.json, ocr-hunyuan/)")
    parser.add_argument("--ocr-dir", default=OCR_DIRNAME, help=f"engine B's pages (default {OCR_DIRNAME})")
    parser.add_argument("--manifest", default=MANIFEST_NAME, help=f"the page manifest (default {MANIFEST_NAME})")
    parser.add_argument("--output", default=DRAFT_NAME, help=f"the draft (default {DRAFT_NAME})")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    began = time.monotonic()
    book = Path(os.path.abspath(os.path.expanduser(str(arguments.book))))
    output = inside(book, arguments.output)
    try:
        draft = draft_book(book, arguments.ocr_dir, arguments.manifest)
        atomic_write(output, render_draft(draft, built_at()))
    except Exception as error:  # noqa: BLE001 - the draft never stops the pipeline
        print(f"[draft] NOT WRITTEN {output}: {type(error).__name__}: {error} - go on with the next step",
              flush=True)
        return 1
    missing = [page.scan_page for page in draft.pages if page.text is None]
    nothing = [page.scan_page for page in draft.pages if page.read_nothing]
    looped = [page.scan_page for page in draft.pages if page.loops]
    cleaned = sum(1 for page in draft.pages if page.cuts)
    heads = ", ".join(f"'{shown(head)}'" for head in draft.heads[:3]) + (" …" if len(draft.heads) > 3 else "")
    print(f"[draft] wrote {output}: {len(draft.pages)} pages, {len(draft.skipped)} left out by the manifest, "
          f"{len(missing)} with no OCR text{f' {missing[:10]}' if missing else ''}, "
          f"{len(nothing)} read as nothing{f' {nothing[:10]}' if nothing else ''}, "
          f"{len(looped)} with an OCR loop cut to a gap line{f' {looped[:10]}' if looped else ''}; "
          f"{len(draft.heads)} running head(s) learned{f' ({heads})' if heads else ''}, furniture taken off "
          f"{cleaned} page(s)" + (f"; {draft.note}" if draft.note else "")
          + f" ({time.monotonic() - began:.1f}s)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
