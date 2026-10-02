#!/usr/bin/env python3
"""Automatic defect counters for an assembled book (CPU, no model).

The counters of the book repair design: running heads, volume labels and
folios left in the text, engine B's stand-in glyphs, reversed and unbalanced
brackets, figures engine A printed that the text lost, headings that are
furniture or lost their number, contents entries without a number, page-top
fragments, unlabelled page boundaries, audit errors, paragraph counts that
the print's indents contradict, adjudicator answers that are prose, and
characters both engines read that the text lost.

Every counter reads the book model (_repair_model.py): a counter whose model
gate failed is not measured on that book and says so, rather than counting
against a guess.  Each hit names its page, line and text, so the counters
serve three uses: the repair tool counts them before and after
(repair_book.py), a benchmark scores a run by them, and a seal gate can turn
each hit into a doubt.

Usage:
    python3 scripts/_book_lint.py BOOK [--text FILE | --pages-dir DIR]
        [--model book-model.json] [--pages SPEC] [--boundaries boundaries.json]
        [--final final.md] [--json OUT] [--workers N] [--fail-on COUNTER,...]

Exit status: 0; 1 when a counter named by --fail-on counts anything; 2 when
the inputs fail verification or --fail-on names no counter.  A counter
named by --fail-on that is not measured on the book (its gate failed) does
not fail the run, and is named on stderr.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proofread_pages as pp  # noqa: E402
import _repair_align as ra  # noqa: E402
import _repair_inputs as ri  # noqa: E402
import _repair_model as rm  # noqa: E402


COUNTERS = (
    "FURN-HEAD", "FURN-SUFFIX", "FURN-FOLIO", "FURN-ANSWER",
    "MARK-STANDIN", "MARK-REVERSED", "MARK-UNBALANCED", "MARK-SHAPE", "MARK-FIGURE-LOST",
    "HEAD-FURNITURE", "HEAD-LEVELS", "HEAD-NUMBER-LOST", "TOC-NUMBER-LOST", "TOC-UNMATCHED",
    "HEAD-FRAGMENT", "JOIN-UNRESOLVED", "JOIN-UNVERIFIED", "AUDIT-ANNOTATED", "AUDIT-FINAL",
    "PARA-DISAGREE", "ANSWER-PROSE", "TEXT-LOST",
)
# Counters that describe the book rather than count defects: a histogram,
# and a measure that points where to look.
REPORT_ONLY = frozenset({"HEAD-LEVELS", "PARA-DISAGREE"})

HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+")
LINE_PREFIX = re.compile(r"^\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+|>\s*)?")
FIGURE_START = re.compile(r"^\s*(?:[-*+]\s+)?(?:#{1,6}\s+)?[\[［(（]?\s*[0-9０-９]")
BRACKETED_FIGURE = re.compile(r"[（(]\s*([0-9０-９]{1,3})\s*[)）]")
LINE_FIGURE = re.compile(r"\n[ \t]*[\[［(（]?[ \t]*([0-9０-９]{1,3})")
SHAPE = re.compile(r"[\[\]︵︶]|（[^（）\n]{1,3}[、，]）")
# The words of phase 3's own prompts (裁決's fixed last line and its
# instructions): an answer holding them is the adjudicator's reasoning.
PROMPT_WORDS = ("定案", "判定", "構件", "候選")
BRACKETS = {"（": "）", "「": "」", "『": "』"}
CLOSERS = {v: k for k, v in BRACKETS.items()}


def line_core(line: str) -> str:
    """A line's CJK and figures, without Markdown markers and marks."""
    rest = LINE_PREFIX.sub("", line)
    return "".join(c for c in rest if pp.CJK(c) or c.isdigit())


def folio_forms(value: int | None) -> set[str]:
    """How a folio VALUE may be printed: its digit-by-digit CJK form, Arabic
    figures, and every piece of either."""
    if not value:
        return set()
    digits = "〇一二三四五六七八九"
    forms = {"".join(digits[int(c)] for c in str(value)), str(value)}
    out = set()
    for form in forms:
        out.update(form[i:j] for i in range(len(form)) for j in range(i + 1, len(form) + 1))
    return out


def numeral_only(core: str) -> bool:
    return bool(core) and all(rm.is_numeral_char(c) or c == "口" for c in core) and len(core) <= 4


def head_line(core: str, stems: Sequence[str], suffixes: Sequence[str]) -> bool:
    """F1's shape: at most one stray numeral, a stem copy, optionally a run
    suffix, optionally folio figures - the whole line."""
    for skip in (0, 1):
        if skip and not (core and rm.is_numeral_char(core[0])):
            continue
        rest = core[skip:]
        for stem in stems:
            match = next(iter(rm.stem_matches(rest, stem)), None)
            if not match or match[0] != 0:
                continue
            tail = rest[match[1]:]
            for suffix in sorted(suffixes, key=len, reverse=True):
                if suffix and tail.startswith(suffix):
                    tail = tail[len(suffix):]
                    break
            if not tail or numeral_only(tail):
                return True
    return False


def hit(page: int, line: int | None, text: str, **detail: Any) -> dict[str, Any]:
    return {"page": page, "line": line, "text": text, **detail}


def sentence_finished(text: str, finals: str) -> bool:
    stripped = text.rstrip()
    return bool(stripped) and stripped[-1] in finals


def last_line(text: str) -> str:
    rows = [line for line in text.split("\n") if line.strip()]
    return rows[-1] if rows else ""


def locate_rows(lines: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> list[int | None]:
    """Each contents row's line (1-based) in LINES, or None when it is gone:
    in order, the next line whose characters are the row's, or the row's
    with at most CONTENTS_LEADING_DROP characters more or fewer at its start
    (a figure's stand-ins written or taken away)."""
    out: list[int | None] = []
    at = 0
    cores = [pp.CJK(line) for line in lines]
    for row in rows:
        text = row.get("text") or ""
        found = None
        for n in range(at, len(lines)):
            core = cores[n]
            if core and text and (core == text or (core.endswith(text) or text.endswith(core))
                                  and abs(len(core) - len(text)) <= rm.CONTENTS_LEADING_DROP):
                found = n
                break
        out.append(found + 1 if found is not None else None)
        if found is not None:
            at = found + 1
    return out


def lint_page(job: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Every per-page counter on one page (JOB: the page's text and inputs,
    the model's page entry and the book-wide facts)."""
    scan = job["scan"]
    text = job["text"]
    entry = job["entry"]
    facts = job["facts"]
    stems, suffixes = facts["stems"], facts["suffixes"]
    finals = facts["finals"]
    out: dict[str, list[dict[str, Any]]] = {name: [] for name in COUNTERS}
    lines = text.split("\n")
    nonempty = [n for n, line in enumerate(lines, 1) if line.strip()]
    edges = set(nonempty[:2] + nonempty[-2:])
    band_text = "".join(pp.CJK(b["text"]) for b in entry.get("band") or [])
    page_suffix = entry.get("suffix")
    divider = entry.get("divider")
    contents = entry.get("contents")
    folio = folio_forms(entry.get("folio"))
    band_numbers = {line_core(b["text"]) for b in entry.get("band") or [] if b.get("label") == "number"}
    a_body = job["a_body"]
    body_stream = pp.CJK(a_body)
    head_lines: set[int] = set()

    # A line of the head's shape that engine A read in its body (outside the
    # band) is printed there - a title that holds the stem - not furniture;
    # so is one engine A read backwards (a page printed right to left).
    printed = Counter(line_core(b) for b in a_body.split("\n"))
    for n, line in enumerate(lines, 1):
        core = line_core(line)
        if not core:
            continue
        heading = HEADING.match(line)
        if stems and head_line(core, stems, suffixes):
            seen = core if printed[core] > 0 else core[::-1] if printed[core[::-1]] > 0 else None
            if seen is not None:
                printed[seen] -= 1
                head_lines.add(n)
                continue
            out["FURN-HEAD"].append(hit(scan, n, line, shape="head line"))
            head_lines.add(n)
            if heading:
                out["HEAD-FURNITURE"].append(hit(scan, n, line, shape="head line"))
            continue
        if core in suffixes:
            if contents and core == facts.get("contentsWord"):
                out["FURN-HEAD"].append(hit(scan, n, line, shape="contents word"))
            elif not (divider and core == page_suffix):
                out["FURN-SUFFIX"].append(hit(scan, n, line, shape="suffix line"))
            else:
                continue
            head_lines.add(n)
            if heading:
                out["HEAD-FURNITURE"].append(hit(scan, n, line, shape="suffix"))
            continue
        if numeral_only(core) and n in edges and (core.replace("口", "〇") in folio or core in band_numbers):
            out["FURN-FOLIO"].append(hit(scan, n, line, folio=entry.get("folio")))
            if heading:
                out["HEAD-FURNITURE"].append(hit(scan, n, line, shape="folio"))

    # Inline copies: stems and the page's suffix inside lines, beyond what
    # engine A read in its body (outside the band).
    for stem in stems:
        sealed_inline = [(n, lines[n - 1]) for n in range(1, len(lines) + 1) if n not in head_lines
                         for _ in rm.stem_matches(line_core(lines[n - 1]), stem)]
        extra = len(sealed_inline) - len(rm.stem_matches(body_stream, stem))
        for n, line in sealed_inline[:max(0, extra)]:
            out["FURN-HEAD"].append(hit(scan, n, line, shape="inline head"))
    if page_suffix and not divider:
        sealed_inline = [(n, lines[n - 1]) for n in range(1, len(lines) + 1) if n not in head_lines
                         for _ in range(line_core(lines[n - 1]).count(page_suffix))]
        extra = len(sealed_inline) - body_stream.count(page_suffix)
        for n, line in sealed_inline[:max(0, extra)]:
            out["FURN-SUFFIX"].append(hit(scan, n, line, shape="inline suffix"))

    alignment = ra.align_page(text, a_body, job["b_body"])
    sealed = alignment.sealed

    def line_at(offset: int) -> int:
        return text.count("\n", 0, offset) + 1

    # Answers sealed at a band spot, and answers that are prose.
    for record in job["adjudications"]:
        answer = pp.CJK(str(record.get("resolved") or ""))
        if not answer or answer not in sealed.chars:
            continue
        a_read = pp.CJK(str(record.get("draft_reading") or ""))
        b_read = pp.CJK(str(record.get("writer_reading") or ""))
        if len(answer) > max(len(a_read), len(b_read)) + 2 or any(w in str(record.get("resolved")) for w in PROMPT_WORDS):
            out["ANSWER-PROSE"].append(hit(scan, None, str(record.get("resolved")), engineA=a_read, engineB=b_read))
        if record.get("resolved_from") not in ("adjudicator", "engine-A-default", "moved-kept-once") or not stems:
            continue
        before = pp.CJK(str(record.get("context_before") or ""))
        after = pp.CJK(str(record.get("context_after") or ""))
        band_before = any(rm.stem_matches(before, s) for s in stems) or bool(page_suffix and page_suffix in before)
        band_after = any(rm.stem_matches(after, s) for s in stems) or bool(page_suffix and page_suffix in after)
        if not (band_before or band_after):
            continue
        b_spans = "".join(s.get("read", "") + (s.get("suffix") or "") + s.get("numeralsBefore", "")
                          + (s.get("numeralsAfter") or "") for s in entry.get("headSpansB") or [])
        a_ok = not a_read or a_read in band_text or a_read.replace("口", "〇") in folio or a_read in suffixes
        b_ok = (not b_read or b_read.replace("口", "〇") in folio or b_read in b_spans
                or b_read in suffixes)
        body = after[:3] if band_before else before[-3:]
        if body:
            where = sealed.chars.find(answer + body) if band_before else sealed.chars.find(body + answer)
            at = where if band_before or where < 0 else where + len(body)
        else:
            # The answer is at the page's start (end) with only the band beside it.
            at = 0 if not band_before and sealed.chars.startswith(answer) else \
                len(sealed.chars) - len(answer) if band_before and sealed.chars.endswith(answer) else -1
        if at < 0:
            continue
        if a_ok and b_ok:
            out["FURN-ANSWER"].append(hit(scan, line_at(sealed.offsets[at]), answer, engineA=a_read,
                                          engineB=b_read, shape="answer at a band spot"))
        elif answer.replace("口", "〇") in folio and a_read and not a_ok:
            # A folio figure written where engine A read a body character.
            out["FURN-ANSWER"].append(hit(scan, line_at(sealed.offsets[at]), answer, engineA=a_read,
                                          engineB=b_read, shape="folio for a body character"))

    # Stand-ins engine A did not read.
    glyphs = set(facts["standins"])
    for k, c in enumerate(sealed.chars):
        if c in glyphs and alignment.sealed_to_a[k] is None:
            out["MARK-STANDIN"].append(hit(scan, line_at(sealed.offsets[k]), c))

    # Reversed brackets engine A did not print.
    for match in re.finditer(r"）（", text):
        o = match.start()
        before_k = max((k for k, off in enumerate(sealed.offsets) if off < o), default=None)
        after_k = next((k for k, off in enumerate(sealed.offsets) if off >= match.end()), None)
        printed = False
        if before_k is not None and after_k is not None:
            gap = ra.engine_between(alignment.a, alignment.sealed_to_a, before_k, after_k)
            printed = gap is not None and "）（" in gap.replace(")", "）").replace("(", "（")
        if not printed:
            out["MARK-REVERSED"].append(hit(scan, line_at(o), text[max(0, o - 3):o + 5]))

    for match in SHAPE.finditer(text):
        out["MARK-SHAPE"].append(hit(scan, line_at(match.start()), match.group()))
    # A bracket where engine A read a quote at the same gap, and no bracket.
    for k in range(1, len(sealed.chars)):
        gap = sealed.gaps[k]
        if not any(c in "（）" for c in gap) or not ra.adjacent_in(alignment.sealed_to_a, k - 1, k):
            continue
        a_gap = alignment.a.gaps[alignment.sealed_to_a[k]]
        if any(c in "（）()" for c in a_gap):
            continue
        if ("（" in gap and any(c in "「『" for c in a_gap)) or ("）" in gap and any(c in "」』" for c in a_gap)):
            out["MARK-SHAPE"].append(hit(scan, line_at(sealed.offsets[k]), gap.strip(), engineA=a_gap.strip(),
                                         shape="bracket for a quote"))

    # Figures engine A printed at a line's start or in brackets that the
    # sealed text lost there.
    a = alignment.a
    for k, gap in enumerate(a.gaps):
        # Each figure once, by where its digits start in the gap (a
        # bracketed figure at a line's start is both kinds).
        found = {m.start(1): m.group(1) for m in BRACKETED_FIGURE.finditer(gap)}
        lead = 0 if k else 1
        found.update({m.start(1) - lead: m.group(1) for m in LINE_FIGURE.finditer(gap if k else "\n" + gap)})
        figures = [found[at] for at in sorted(found)]
        if not figures:
            continue
        lo = alignment.a_to_sealed[k - 1] if k > 0 else None
        hi = alignment.a_to_sealed[k] if k < len(a.chars) else None
        if hi is None or (k > 0 and lo is None):
            continue
        start = sealed.offsets[lo] + 1 if lo is not None else text.rfind("\n", 0, sealed.offsets[hi]) + 1
        held = text[start:sealed.offsets[hi]].translate(ra.FULLWIDTH_DIGITS)
        for figure in figures:
            if figure.translate(ra.FULLWIDTH_DIGITS) not in held:
                out["MARK-FIGURE-LOST"].append(hit(scan, line_at(sealed.offsets[hi]), figure,
                                                   engineA=gap.strip()))
                line = lines[line_at(sealed.offsets[hi]) - 1]
                if HEADING.match(line) and not re.search(r"[0-9０-９]", line):
                    out["HEAD-NUMBER-LOST"].append(hit(scan, line_at(sealed.offsets[hi]), line, figure=figure))

    # Contents entries without a number.  A row is the contents line the
    # book model read (on the sealed page); the text counted may have lost
    # or changed lines since, so each row is found again by its characters.
    for row, number in zip(job["contents_rows"], locate_rows(lines, job["contents_rows"])):
        if number is None:
            continue
        line = lines[number - 1]
        if row.get("matchedPage") is not None and not FIGURE_START.match(line):
            out["TOC-NUMBER-LOST"].append(hit(scan, number, line))
        if row.get("matchedPage") is None and not row.get("inText") and not HEADING.match(line) \
                and number not in head_lines and not any(line_core(line).startswith(s) for s in suffixes):
            out["TOC-UNMATCHED"].append(hit(scan, number, line))

    # A page-top heading that finishes the previous page's sentence.
    if nonempty:
        first = lines[nonempty[0] - 1]
        previous = job["previous_text"]
        geometry = entry.get("geometry") or {}
        k_cells = facts.get("k")
        flush = None
        if geometry.get("columns") and k_cells:
            flush = rm.indent_class(geometry["columns"][0]["topCells"], k_cells) == "flush"
        prev_last = last_line(previous) if previous is not None else ""
        prev_geometry = job.get("previous_geometry") or {}
        prev_full = None
        if prev_geometry.get("columns"):
            prev_full = prev_geometry["columns"][-1]["shortCells"] < 0.9
        unfinished = previous is not None and bool(prev_last) and not HEADING.match(prev_last) \
            and not sentence_finished(prev_last, finals)
        # Text: the heading ends a sentence; print: its column is flush and the
        # previous page's last column is full.  Either, with the previous page
        # unfinished; an indent that says it is set as a heading overrules.
        if HEADING.match(first) and nonempty[0] not in head_lines and unfinished and flush is not False and \
                (sentence_finished(first, "。！？") or (flush and prev_full and len(line_core(first)) >= 4)):
            out["HEAD-FRAGMENT"].append(hit(scan, nonempty[0], first))

    # Paragraphs the indents contradict.
    geometry = entry.get("geometry") or {}
    if facts.get("indentGate") and geometry.get("columns") and not contents and not divider:
        k_cells = facts["k"]
        indented = sum(1 for c in geometry["columns"] if rm.indent_class(c["topCells"], k_cells) == "paragraph")
        blocks = [b for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]
        paragraphs = [b for b in blocks if not HEADING.match(b) and not re.match(r"\s*(?:[-*+]|\d+[.)])\s", b)]
        starts = len(paragraphs)
        if paragraphs and rm.indent_class(geometry["columns"][0]["topCells"], k_cells) == "flush" \
                and blocks and blocks[0] is paragraphs[0]:
            starts -= 1
        if indented != starts:
            out["PARA-DISAGREE"].append(hit(scan, None, "", indentedColumns=indented, paragraphStarts=starts))

    # Characters both engines read (outside the band) that the text lost.
    lost = Counter()
    a_chars = alignment.a.chars
    for tag, i1, i2, j1, j2 in ra.opcodes(a_chars, alignment.b.chars):
        if tag == "equal":
            for i in range(i1, i2):
                if alignment.a_to_sealed[i] is None:
                    lost[a_chars[i]] += 1
    explained = Counter(job.get("explained") or {})
    for char, n in (lost - explained).items():
        for _ in range(n):
            out["TEXT-LOST"].append(hit(scan, None, char))
    return out


def unbalanced_pages(texts: Mapping[int, str], order: Sequence[int],
                     neighbours: Mapping[int, tuple[str | None, str | None]] | None = None) -> list[dict[str, Any]]:
    """Pages whose brackets and quotes do not balance, a page turn aware: an
    opening left open at a page's end may close at the next page's start.
    NEIGHBOURS gives, per page, the texts of the book's marker pages before
    and after it where those are not in ORDER (a subset of the book)."""
    def tally(text: str) -> tuple[dict[str, int], dict[str, int]]:
        opened: dict[str, int] = {k: 0 for k in BRACKETS}
        unopened: dict[str, int] = {k: 0 for k in BRACKETS}
        for c in text:
            if c in BRACKETS:
                opened[c] += 1
            elif c in CLOSERS:
                key = CLOSERS[c]
                if opened[key]:
                    opened[key] -= 1
                else:
                    unopened[key] += 1
        return opened, unopened

    state = {scan: tally(texts[scan]) for scan in order}
    none = {key: 0 for key in BRACKETS}
    out = []
    for scan in order:
        opened, unopened = state[scan]
        before, after = (neighbours or {}).get(scan, (None, None))
        previous = tally(before)[0] if before is not None else none
        following = tally(after)[1] if after is not None else none
        bad = [key for key in BRACKETS if unopened[key] > previous[key] or opened[key] > following[key]]
        if bad:
            out.append(hit(scan, None, "".join(bad), open={k: opened[k] for k in bad},
                           unopened={k: unopened[k] for k in bad}))
    return out


def neighbour_text(book: Any, texts: Mapping[int, str], scan: int | None) -> str | None:
    """A marker page's text: as counted (TEXTS) when it is among them, else
    as sealed (a page outside a subset); None for no page."""
    if scan is None:
        return None
    return texts[scan] if scan in texts else book.pages[scan].sealed_text


def neighbours(book: Any, texts: Mapping[int, str], order: Sequence[int]) -> dict[int, tuple[str | None, str | None]]:
    """Per page of ORDER, the texts of the book's marker pages just before
    and just after it."""
    markers = [scan for scan in sorted(book.pages) if book.pages[scan].marker]
    out = {}
    for k, scan in enumerate(markers):
        if scan in order:
            out[scan] = (neighbour_text(book, texts, markers[k - 1] if k else None),
                         neighbour_text(book, texts, markers[k + 1] if k + 1 < len(markers) else None))
    return out


def page_jobs(book: Any, model: Mapping[str, Any], texts: Mapping[int, str], order: Sequence[int],
              explained: Mapping[int, Mapping[str, int]] | None = None) -> list[dict[str, Any]]:
    geometry = model.get("geometry") or {}
    facts = {
        "stems": list(model.get("stems") or []) if rm.gate(model, "M-2") else [],
        "suffixes": sorted({r["suffix"] for r in model.get("suffixRuns") or []}) if rm.gate(model, "M-3") else [],
        "contentsWord": next((r.get("contentsWord") for r in (model.get("contents") or {}).get("runs") or []
                              if r.get("contentsWord")), None),
        "finals": "".join(model.get("sentenceFinal") or "。！？"),
        "standins": sorted(rm.standin_glyphs(model)),
        "k": (geometry.get("indent") or {}).get("k"),
        "indentGate": rm.gate(model, "M-8b"),
    }
    markers = [scan for scan in sorted(book.pages) if book.pages[scan].marker]
    before_of = {b: a for a, b in zip(markers, markers[1:])}
    rows_by_page: dict[int, list[dict[str, Any]]] = {}
    for run in (model.get("contents") or {}).get("runs") or []:
        for row in run["entries"]:
            rows_by_page.setdefault(row["page"], []).append(row)
    jobs = []
    for k, scan in enumerate(order):
        page = book.pages[scan]
        entry = rm.page_entry(model, scan)
        a_body, b_body = rm.body_streams(page, entry.get("band") or [], entry.get("headSpansB") or [])
        jobs.append({
            "scan": scan, "text": texts[scan], "entry": entry, "facts": facts,
            "a_body": a_body, "b_body": b_body,
            "adjudications": [a for a in page.record.get("adjudications") or [] if isinstance(a, dict)],
            "contents_rows": rows_by_page.get(scan, []),
            "previous_text": neighbour_text(book, texts, before_of.get(scan)),
            "previous_geometry": rm.page_entry(model, before_of[scan]).get("geometry") if scan in before_of else None,
            "explained": dict((explained or {}).get(scan) or {}),
        })
    return jobs


def lint_book(book: Any, model: Mapping[str, Any], texts: Mapping[int, str] | None = None,
              combined: str | None = None, boundaries: Mapping[int, str] | None = None,
              evidence: Mapping[str, Any] | None = None, final: str | None = None,
              explained: Mapping[int, Mapping[str, int]] | None = None, workers: int = 1) -> dict[str, Any]:
    """Every counter over BOOK's marker pages (a _repair_inputs.Book), on
    TEXTS (page -> text; default the sealed pages).  COMBINED is the
    annotated book for the audit (default composed from TEXTS); BOUNDARIES a
    boundary manifest; EVIDENCE boundary-evidence.json; FINAL a finalized
    book; EXPLAINED, per page, characters a question's answer removed."""
    order = [scan for scan in book.assembly.order if scan in book.pages]
    texts = dict(texts) if texts is not None else {scan: book.pages[scan].sealed_text for scan in order}
    jobs = page_jobs(book, model, texts, order, explained)
    if workers > 1 and len(jobs) > 8:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(lint_page, jobs, chunksize=4))
    else:
        results = [lint_page(job) for job in jobs]
    hits: dict[str, list[dict[str, Any]]] = {name: [] for name in COUNTERS}
    for result in results:
        for name, found in result.items():
            hits[name].extend(found)
    hits["MARK-UNBALANCED"] = unbalanced_pages(texts, order, neighbours(book, texts, order))

    levels: Counter = Counter()
    for scan in order:
        for line in texts[scan].split("\n"):
            match = HEADING.match(line)
            if match:
                levels[len(match.group(1))] += 1

    not_measured: dict[str, str] = {}
    if not rm.gate(model, "M-2"):
        for name in ("FURN-HEAD", "FURN-ANSWER"):
            not_measured[name] = "gate M-2 (stems) failed"
    if not rm.gate(model, "M-3"):
        not_measured["FURN-SUFFIX"] = "gate M-3 (run suffixes) failed"
    if not rm.gate(model, "M-4"):
        not_measured["FURN-FOLIO"] = "gate M-4 (folio sequence) failed"
    if not rm.gate(model, "M-6"):
        not_measured["TOC-NUMBER-LOST"] = not_measured["TOC-UNMATCHED"] = "gate M-6 (contents pages) failed"
    if not rm.gate(model, "M-8b"):
        not_measured["PARA-DISAGREE"] = "gate M-8b (indent clusters) failed"

    labelled = dict(boundaries or {})
    hits["JOIN-UNRESOLVED"] = [hit(scan, None, "") for scan in book.assembly.order if scan not in labelled]
    if evidence is not None:
        rows = evidence.get("boundaries") if isinstance(evidence, dict) else None
        hits["JOIN-UNVERIFIED"] = [hit(int(key), None, "", rule=row.get("rule"))
                                   for key, row in (rows or {}).items() if not row.get("verified")]
    else:
        not_measured["JOIN-UNVERIFIED"] = "no boundary evidence"

    if combined is None:
        combined = book.assembly.compose(texts)
    import audit_ocr_markdown as audit
    expected = book.expected_count
    skip = set(range(1, (expected or 0) + 1)) - set(book.assembly.order) if expected else set()
    result = audit.audit_text(combined, mode="annotated", expected_count=expected, skip_pages=skip,
                              boundary_contract=dict(labelled) if labelled else None)
    hits["AUDIT-ANNOTATED"] = [hit(None, issue.line, issue.code) for issue in result.issues
                               if issue.severity == "error"]
    if final is not None:
        final_result = audit.audit_text(final, mode="final")
        hits["AUDIT-FINAL"] = [hit(None, issue.line, issue.code) for issue in final_result.issues
                               if issue.severity == "error"]
    else:
        not_measured["AUDIT-FINAL"] = "no finalized book"
    for name in not_measured:
        hits[name] = []

    counters = {}
    for name in COUNTERS:
        entry: dict[str, Any] = {"count": len(hits[name])}
        if name in not_measured:
            entry = {"count": None, "notMeasured": not_measured[name]}
        if name == "HEAD-LEVELS":
            entry = {"count": sum(levels.values()), "levels": {"#" * n: levels[n] for n in sorted(levels)}}
        if name in ("AUDIT-ANNOTATED", "AUDIT-FINAL") and name not in not_measured:
            entry["codes"] = dict(Counter(h["text"] for h in hits[name]).most_common())
        if name == "MARK-STANDIN" and name not in not_measured:
            entry["glyphs"] = dict(Counter(h["text"] for h in hits[name]).most_common())
        if name in REPORT_ONLY:
            entry["reportOnly"] = True
        counters[name] = entry
    return {"pages": len(order), "counters": counters, "hits": hits}


def summary(result: Mapping[str, Any]) -> dict[str, Any]:
    return {name: entry.get("count") for name, entry in result["counters"].items()}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("book", type=Path)
    parser.add_argument("--text", type=Path, help="an annotated book to count (default: the sealed pages)")
    parser.add_argument("--pages-dir", type=Path, help="a folder of page-NNNN.md to count instead")
    parser.add_argument("--model", type=Path, help="book-model.json (default: learned now)")
    parser.add_argument("--pages", help="only these scan pages, e.g. 1-9,17")
    parser.add_argument("--boundaries", type=Path, help="boundaries.json")
    parser.add_argument("--evidence", type=Path, help="boundary-evidence.json")
    parser.add_argument("--final", type=Path, help="a finalized book for AUDIT-FINAL")
    parser.add_argument("--json", type=Path, help="write the counters and every hit here")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--fail-on", default="", help="comma-separated counters that fail the run when above 0")
    arguments = parser.parse_args(argv)
    fail_on = [name.strip() for name in arguments.fail_on.split(",") if name.strip()]
    unknown = [name for name in fail_on if name not in COUNTERS]
    if unknown:
        # A misspelt counter would count nothing and never fail the run.
        print(f"--fail-on: no counter {', '.join(unknown)} (the counters: {', '.join(COUNTERS)})", file=sys.stderr)
        return 2
    from _ocr_markdown import load_boundary_manifest, parse_page_spec
    pages = parse_page_spec([arguments.pages]) if arguments.pages else None
    paths = ri.InputPaths.resolve(arguments.book, {})
    try:
        book = ri.load_book(paths, pages)
    except ri.InputError as error:
        print(f"inputs: {error}", file=sys.stderr)
        return 2
    model = json.loads(arguments.model.read_text(encoding="utf-8")) if arguments.model \
        else rm.learn(book, workers=arguments.workers)
    texts = None
    combined = None
    if arguments.text:
        combined = arguments.text.read_text(encoding="utf-8")
        parsed = ri.parse_assembly(combined)
        texts = {scan: parsed.bodies[scan] for scan in parsed.order if scan in book.pages}
    elif arguments.pages_dir:
        texts = {scan: (arguments.pages_dir / f"{ri.page_stem(scan)}.md").read_text(encoding="utf-8")
                 for scan in book.assembly.order}
    boundaries = load_boundary_manifest(arguments.boundaries) if arguments.boundaries else None
    evidence = json.loads(arguments.evidence.read_text(encoding="utf-8")) if arguments.evidence else None
    final = arguments.final.read_text(encoding="utf-8") if arguments.final else None
    result = lint_book(book, model, texts, combined, boundaries, evidence, final, workers=arguments.workers)
    for name, entry in result["counters"].items():
        count = entry.get("count")
        print(f"{name:18} {'-' if count is None else count}"
              + (f"  ({entry['notMeasured']})" if entry.get("notMeasured") else ""))
    if arguments.json:
        arguments.json.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    for name in fail_on:
        if result["counters"][name].get("count") is None:
            print(f"--fail-on {name}: not measured on this book ({result['counters'][name].get('notMeasured')})",
                  file=sys.stderr)
    failing = [name for name in fail_on if result["counters"][name].get("count")]
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
