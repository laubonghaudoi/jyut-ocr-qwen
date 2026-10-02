"""The book repair tool's questions to the model (scripts/repair_book.py).

A rule that finds a site it cannot settle plans a question
(_repair_rules.question): the page, the site as the rule saw the page (its
offsets, its text and eight characters of context either side) and why.
This module asks it, one crop and one question each, with phase 3's Client
(its endpoint, model, effort - xhigh by default - and effort ladder, its
max_tokens and its in-flight cap), and turns each answer that passes the
guards into offset edits; an answer a guard refuses is a doubt, never an
edit.

The kinds (the Client's call kind in brackets):
- Q-G which character (`repair-glyph`): a red box round the place between
  two characters the page and engine A share; asked blind first (no
  candidates), and only when the blind answer is neither engine's reading
  nor an acceptable variant of one, a second time with both readings as
  candidates (phase 3's 裁決 question).  The second answer is written only
  when it names a candidate, or says the print is damaged (印壞: read by
  meaning, the user's rule).
- Q-P what is printed between two anchors (`repair-print`): two red lines,
  the answer replaces the page's text between the anchors, its Markdown
  structure (line breaks, heading and list markers) kept.  A question about
  a list's number that carries the mark its list numbers with
  (numberStyle) reads a colon-like mark after the figure as that mark; a
  unit's or a contents entry's number (S4, S11) is written with a space
  before its title.
- Q-L copy a line or a column (`repair-line`): the answer is written
  character by character; a character that differs from both engines' and
  the page's at its place (a character read elsewhere on the line does not
  count) is written only when the answer marks it damaged or a glyph
  question on its cell agrees (a follow-up Q-G) - or, where that question
  reads a third character, when a second round on the same crop with the
  two readings as candidates names one (that one is written); where a
  title's end is unclear (S9), the copy of the title says where it ends.
  A line of a page printed right to left takes its cells from its own row
  of ink (line_cells), not from its block's box.
- Q-Y layout (`repair-layout`): a heading or a paragraph's run-in lead;
  the same paragraph or a new one at a line break.
- Q-B page boundary (`repair-boundary`): the previous page's last column
  and the next page's first, side by side; continued or a new paragraph.

The site: a question's offsets are into the page as the rule saw it, and
edits applied since (the rest of its stage, later stages) may have moved
it.  It is found in the page's history (the sealed text and the log's
records, one by one): the latest state that holds the site's text at its
offsets with the same context, mapped forward through the records applied
after it.  A record that overlaps it made the question moot: a `conflict`
doubt.  The anchors are the nearest characters outside the site that the
page and engine A share: the crop is cut from their cells (engine A's block,
its columns measured on the render) and each engine's reading between them
is what the guards compare an answer with.

Crops are cut from the render, never from a crop cut before: the running
head's band (the book model's M-1 blocks) is painted with the page's paper,
unless the question is about the band (the furniture rules' questions);
each piece has 30 % of a column's width either side; a gap that crosses a
column break is shown as the column pieces side by side, in reading order,
paper between (boundary_crop's composition), a column it runs into cut from
its head (what is printed above the first glyph engine A read there: a
contents entry's number set over its title); the crop is enlarged to a
short side of 700 px (upscale_crop), the marks are drawn 2 px wide after
that, and a thin crop is padded with its paper (fit_media_aspect).

Where a mark goes comes from engine A's cells (block_cells): a block's
columns of text measured on the render with the band painted out,
everything engine A read split among them so each column's content fills
its ink (a figure group a cell, each kind of mark the share of a cell the
block shows, fit by least squares), and each column's units matched in
order to its runs of ink - so a figure engine A read, a full stop set close
under its character, glyphs that touch and uneven spacing do not move a
tick off its glyph.  Measured on real pages of a scanned book: counting
CJK characters alone put a tick above a printed figure instead of after
it, and a box a whole cell below its glyph at a column's foot.

The answer is the reply's last line, in the form the question names
(`定案：`, `印刷：` or `答：`), parsed strictly; a trailing RESEARCH line of
the 裁決 system prompt is set aside.  無 and the other EMPTY_VERDICTS mean
nothing is printed there - unless an engine read that very character
there.  睇唔清 is an answer too: nothing is settled (a doubt).

Guards (a refused answer is a `look-refused` doubt, never an edit):
- G1 format: no answer line, or the reply was cut off or degraded after the
  effort ladder.
- G2 length or prose: a Q-G answer longer than the characters asked about
  (one, or what the page and the engines hold there); a Q-P or Q-L answer
  longer than the longest engine reading there (or the contents' number
  the question expects) plus 2; an answer holding
  the questions' own words (定案, 印刷, 紅框 ...) that neither engine nor the
  page holds there.
- G3 neighbour copy: a Q-G answer that is a character within two of the
  place, which neither engine read at the place.
- G4 band: an answer made only of the running head's characters (the band
  blocks, the stems, the page's suffix and folio) at a place next to the
  band, which neither engine read at the place; any character in the
  answer to a question about the marks a furniture deletion left (the
  question `follows` it: engine A read the running head into the body
  there, so the deleted text is an engine's reading at the place).
- G5 no new character: a Q-P answer holding a CJK character that no engine
  read between the anchors or at them, and that the page does not hold
  there - unless the question says an engine lost a character there
  (lostCharacter); nor one that leaves out a character both engines read
  there (a deletion the question was not about), or holds fewer characters
  than the page and both engines each hold there (they read one glyph two
  ways), or leaves out a mark the page and engine A both hold between the
  anchors (the full stop before a unit's number: no fix the surveys of a
  real book verified deletes such a mark).  A copy
  (Q-L) with no character, or one leaving out a character the one engine
  that read the line read, is refused the same way.  An answer to K14 (a
  stand-in no rule settled) holds a printed unit for each stand-in glyph
  and each mark the page and engine A share there: it says what a stand-in
  is, it does not delete one - engine A read nothing at the stand-in, so
  its neighbour's cell may stand on the ink of the mark it did not read,
  and that mark falls outside the red lines (on a real book 9 of 34 such
  crops).
- G6 contradiction: a figure that does not go on from the figures of its
  kind the page holds before and after it (K-seq's test on the written
  text), or that is not the contents' number of the unit or entry it opens
  (a figure that is, the contents place: its neighbours may be questions of
  the same round, not yet written); 一 as a numeral where neither engine
  read 一.
- G7 conflict: two answers that edit overlapping text - the first question
  (in plan order) wins, the other is a `conflict` doubt.  Questions about
  the same site are asked once.

A boundary answered 續文 where the next page's first line is a heading
joins it into the previous page's sentence: written only when the heading
is what engine A read first on the page (a heading set at the page's top
that engine A reads elsewhere is a doubt, the boundary left unverified).

The cache: each call's answer is kept by the SHA-256 of its system prompt,
its question and its crop, with the model, effort, max_tokens and
temperature it was asked with, in answers.jsonl in the output folder,
written as each answer comes; a resumed run (--resume) reuses an answer
asked the same way and asks nothing again.
"""

from __future__ import annotations

import bisect
from collections import Counter
import concurrent.futures as cf
from dataclasses import dataclass, field
import difflib
import hashlib
import io
import json
import math
from pathlib import Path
import re
import threading
import time
from typing import Any, Callable, Mapping, Sequence

import proofread_pages as pp
import _book_lint as lint
import _repair_align as ra
import _repair_edits as re_
import _repair_joins as rj
import _repair_model as rm
import _repair_rules as rr
import _repair_structure as rs


# The kinds of question, and the Client's call kind each is asked as
# (proofread_pages.CALL_KINDS names them: the call ledger counts them).
CALL_KIND = {
    "Q-G": "repair-glyph",
    "Q-P": "repair-print",
    "Q-L": "repair-line",
    "Q-Y": "repair-layout",
    "Q-B": "repair-boundary",
}
ANSWERS_NAME = "answers.jsonl"
CROPS = "crops"

# Crops: characters of reach round the place (the design's +-2 cells for a
# glyph, 3 for print), a column's width either side, the boundary's cells.
GLYPH_REACH = 2
PRINT_REACH = 3
COLUMN_MARGIN = 0.3
BOUNDARY_CELLS = 6
RED = (220, 0, 0)
BLUE = (0, 70, 230)
MARK_WIDTH = 2
# Characters of the page named in a question either side of its place.
CONTEXT = 4
# How far (in pitches) an anchor's estimated cell is moved onto the ink of
# its glyph (PageImage.snap): on a real page (a book whose marks take room) a
# one-stroke 一 was moved onto the next character a pitch away at 0.6.
SNAP_REACH = 0.35
# The tallest run of ink (in pitches) snap takes for one glyph's: a pitch is
# a glyph and the space after it, so a run half a cell taller than that holds
# two glyphs, or a glyph and a dash's stroke, run together.
GLYPH_RUN = 1.5
# A place next to the band (G4): this many characters from the body's first
# or last, or its cells this many pitches from a band block.
BAND_NEAR = 2
# A run of inked columns at least this share of a line's row wide is a
# glyph of the line (line_cells): on a real title page the glyphs were half
# the row wide and more, the specks and strokes beside them a fifth.
GLYPH_WIDTH = 0.3
# The head of a column a crop runs into (PageImage.head_above): runs of ink
# above the column's first glyph engine A read, each at most HEAD_GAP
# pitches above the one below it, at most HEAD_REACH pitches up.  On a real
# contents page an entry's number stood 1.3 pitches above its title's first
# glyph, outside engine A's block: a crop from the block's top left it out,
# and the model said nothing was printed there.
HEAD_GAP = 2.0
HEAD_REACH = 4.0
# A run of ink under this many pitches tall is a speck or a stray dot, not
# print the head holds (on the same page, specks above a number engine A
# had read moved a crop that needed no more).
HEAD_RUN = 0.3

# The system prompt of every question but the glyph's (which is phase 3's
# 裁決 prompt, ADJUDICATE_SYSTEM).
REPAIR_SYSTEM = """你係古籍排印鑑定員。畀你一張書頁裁圖同一條問題，裁圖上用紅色（有時仲有藍色）嘅線或者框標住要睇嘅位。

淨係照圖上印咗嘅嘢答：
- 唔好估，唔好改字，唔好補字，唔好將字改做通行字形，唔好照文意加標點。
- 圖上睇唔清，就照直答睇唔清。

先簡短講你見到乜，最後一行照問題要求嘅格式寫答案；嗰行淨係寫答案，唔好加解釋。"""

VERTICAL = "直排：由上至下、由右至左讀"
ACROSS_RTL = "橫排：由右至左讀"
PIECES_NOTE = "裁圖由幾段拼成，中間隔住空白，由右至左讀：右邊嗰段先讀。"
DAMAGED = "印壞"
DAMAGED_TAG = re.compile(r"[（(]\s*印壞\s*[)）]")
NEITHER_TAG = re.compile(r"[（(]\s*兩個候選皆非\s*[)）]")
UNSURE = frozenset({"睇唔清", "看不清", "唔清楚", "不清楚"})
# Words of the questions themselves: an answer holding one that the page and
# the engines do not hold there is reasoning, not print (G2).
PROMPT_WORDS = tuple(lint.PROMPT_WORDS) + ("印刷", "紅框", "紅線", "藍線", "裁圖", "引擎", "阿拉伯數字",
                                           "漢字數字", "破折號", "標點", "冇嘢", "答案", "由上至下")
# Marks that close what comes before them: in an answer they stay on the
# line of the character before the anchors' gap when the gap holds a line
# break (the page's own marks before a break are kept there, as K2 keeps
# them).
CLOSING = frozenset("。，、；：？！」』）》〉…")


def glyph_user(cells: str, before: str, after: str, across: bool = False) -> str:
    """The first, blind glyph question (Q-G): no candidates."""
    if across:
        where = "（橫排：由右至左讀）"
        above = f"框右邊印住「{before}」" if before else "框右邊冇字"
        below = f"框左邊印住「{after}」" if after else "框左邊冇字"
    else:
        where = f"（{VERTICAL}）"
        above = f"框上面印住「{before}」" if before else "框上面係欄頂"
        below = f"框下面印住「{after}」" if after else "框下面係欄尾"
    return (f"呢張裁圖係書頁嘅一段{where}。紅框框住{cells}，{above}，{below}。\n"
            "紅框入面印咗乜字？先寫構件，再判定。\n"
            "- 印壞咗、墨糊咗：寫文意需要嘅字，判定後面加「（印壞）」。\n"
            "- 框入面冇字（空位、格線、污點）：寫 `判定：無`。\n"
            "- 睇唔清：寫 `判定：睇唔清`。\n"
            "最後一行一模一樣寫：`定案：<框入面嘅字，或者無>`")


# Said before the context in the second glyph question (phase 3's 裁決
# question, adjudicate_prompt).
GLYPH_ROUND_TWO_NOTE = ("裁圖上紅框框住爭議位。印壞咗、墨糊咗嘅字，寫文意需要嘅字，"
                        "定案後面加「（印壞）」。框入面冇字就寫 `定案：無`。")


def print_user(before: str, after: str, pieces: int) -> str:
    """What is printed between two anchors (Q-P)."""
    above = f"上面係「{before}」最後一個字之後" if before else "上面係呢欄頂"
    below = f"下面係「{after}」第一個字之前" if after else "下面係呢欄尾"
    note = PIECES_NOTE if pieces > 1 else ""
    return (f"呢張裁圖係書頁嘅一段（{VERTICAL}）。{note}兩條紅線標住兩個位：{above}，{below}。\n"
            "兩條紅線之間印咗乜？由上至下逐樣講：漢字、數字（講明係阿拉伯數字定漢字數字）、括號、引號、"
            "破折號（一條直線）、點、其他標點。冇嘢就答「無」。唔好改字，唔好補字，印乜寫乜。\n"
            "最後一行淨係照抄印咗嘅嘢：阿拉伯數字寫 1 2 3，漢字數字寫一二三，睇唔清就寫睇唔清。\n"
            "最後一行一模一樣寫：`印刷：<由上至下照抄；冇嘢就寫無>`")


def line_user(lines: int, across: bool) -> str:
    """Copy a line or a column (Q-L)."""
    what = "一行" if across and lines == 1 else "幾行" if lines > 1 else "一欄"
    how = "呢頁係橫排，由右至左讀" if across else "由上至下"
    many = "幾行就逐行抄，行同行之間寫「／」。" if lines > 1 else ""
    return (f"照印逐字抄出紅框入面嗰{what}（{how}），連編號、括號、引號、破折號同標點；"
            "唔好改字、唔好補字、唔好調次序。印壞咗嘅字寫文意需要嘅字，喺嗰個字後面加「（印壞）」。"
            f"{many}睇唔清就寫睇唔清。\n"
            "最後一行一模一樣寫：`印刷：<照抄>`")


def title_end_user(entry: str) -> str:
    """Where a unit's title ends (Q-L for S9): a copy of the title alone."""
    return (f"紅框入面嗰欄開頭係一個篇題，目錄印做「{entry}」。照印逐字抄出呢個篇題，抄到篇題完為止，"
            "篇題之後嘅正文唔好抄；連編號、括號同標點，唔好改字、唔好補字。睇唔清就寫睇唔清。\n"
            "最後一行一模一樣寫：`印刷：<篇題照抄>`")


def heading_user(text: str) -> str:
    """A heading, or a paragraph's run-in lead (Q-Y)."""
    return (f"紅框框住嘅「{text}」：係獨立標題（字型大過正文，或者自己一欄，正文喺下一欄先開始），"
            "定係段落開頭（同正文一樣大細，正文喺同一欄隔一兩格就接落去）？睇唔清就寫 `答：睇唔清`。\n"
            "最後一行一模一樣寫：`答：標題` 或者 `答：段落開頭`")


def paragraph_user(before: str, after: str, k: float | None, lines: bool) -> str:
    """The same paragraph, or a new one, at a place (Q-Y)."""
    cells = f"{k:g}" if k else None
    blue = f"藍線係正文頂同頂格低{cells}個字嘅位置。" if lines and cells else ""
    new = f"新一欄頂格低{cells}個字開始" if cells else "新一欄比頂格低啲開始"
    return (f"呢張裁圖係書頁嘅一段（{VERTICAL}）。紅線標住「{before}」同「{after}」之間。{blue}\n"
            f"「{after}」係接住上文嘅同一段，定係另起一段（{new}）？睇唔清就寫 `答：睇唔清`。\n"
            "最後一行一模一樣寫：`答：同一段` 或者 `答：另起一段`")


def boundary_user(k: float | None, lines: bool) -> str:
    """A page boundary (Q-B)."""
    cells = f"{k:g}" if k else None
    blue = f"藍線係正文頂同正文底，紅線係頂格低{cells}個字嘅位置。" if lines and cells else ""
    return ("裁圖由兩段拼成，中間隔住一條空白：右邊係上一頁最後一欄嘅尾，左邊係下一頁第一欄嘅頭。"
            f"{blue}\n"
            "下一頁第一欄係上一頁最後一句嘅續文，定係另起一段？睇唔清就寫 `答：睇唔清`。\n"
            "最後一行一模一樣寫：`答：續文` 或者 `答：另起一段`")


# --- answers ---------------------------------------------------------------------

ANSWER_LINE = {
    "定案": re.compile(r"^[\s`*>#-]*定案\s*[：:]\s*(.*?)[\s`*]*$"),
    "印刷": re.compile(r"^[\s`*>#-]*印刷\s*[：:]\s*(.*?)[\s`*]*$"),
    "答": re.compile(r"^[\s`*>#-]*答\s*[：:]\s*(.*?)[\s`*]*$"),
}
LABEL = {"Q-G": "定案", "Q-P": "印刷", "Q-L": "印刷", "Q-Y": "答", "Q-B": "答"}


def answer_line(raw: str | None, label: str) -> str | None:
    """The value of the reply's last line in the form `LABEL：value`, or
    None when the last line (a RESEARCH line and code fences set aside) is
    not in that form."""
    lines = [line for line in (raw or "").strip().splitlines()
             if line.strip() and line.strip() != "```" and not pp.RESEARCH_LINE.match(line)]
    if not lines:
        return None
    match = ANSWER_LINE[label].match(lines[-1].strip())
    if not match:
        return None
    value = match.group(1).strip()
    if len(value) >= 2 and value[0] == "<" and value[-1] == ">":
        value = value[1:-1].strip()
    return value


DASH_RUN = rr.DASH_RUN
FULLWIDTH = str.maketrans("０１２３４５６７８９．", "0123456789.")


def normal_print(text: str) -> str:
    """An answer's print as the page writes it: white space out, brackets
    and ASCII marks full width (︵︶ are （）, the user's rule), a run of
    dash strokes `——` (two or more) or `—`, a dot the book's `·`, figures
    in ASCII."""
    text = "".join(c for c in text if not c.isspace())
    text = text.translate(rr.NORM).translate(FULLWIDTH)
    text = DASH_RUN.sub(lambda m: "——" if len(m.group()) >= 2 else "—", text)
    return "".join(rr.DOT if c in rr.DOT_READS else c for c in text)


@dataclass
class Parsed:
    """An answer as read: its value (None when the reply has no answer
    line), whether it says nothing is printed, whether it cannot tell, the
    characters it says are damaged, and the written form."""
    value: str | None
    empty: bool = False
    unsure: bool = False
    damaged: set[int] = field(default_factory=set)
    text: str = ""


def parse(kind: str, raw: str | None, readings: Sequence[str] = ()) -> Parsed:
    """KIND's answer in RAW.  READINGS: what the engines read at the place,
    so a 無 that is the character an engine read there is that character."""
    value = answer_line(raw, LABEL[kind])
    if value is None:
        return Parsed(None)
    bare = value.strip("「」\"'")
    if bare in UNSURE:
        return Parsed(value, unsure=True)
    if kind in ("Q-Y", "Q-B"):
        return Parsed(value, text=bare)
    cleaned = NEITHER_TAG.sub("", value)
    # A damaged character is the one just before its tag.
    damaged: set[int] = set()
    out = []
    at = 0
    for match in DAMAGED_TAG.finditer(cleaned):
        piece = cleaned[at:match.start()]
        out.append(piece)
        written = normal_print("".join(out)) if kind != "Q-G" else "".join(out).strip()
        if written:
            damaged.add(len(written) - 1)
        at = match.end()
    out.append(cleaned[at:])
    joined = "".join(out)
    if kind == "Q-G":
        # A full stop after the character is the sentence's, not the box's.
        written = "".join(c for c in joined.strip().rstrip("。．.").strip("「」\"'") if not c.isspace())
    else:
        written = normal_print(joined)
    if written in pp.EMPTY_VERDICTS and written not in {pp.CJK(r) for r in readings if r}:
        return Parsed(value, empty=True, damaged=damaged, text="")
    return Parsed(value, damaged=damaged, text=written)


# --- the site ----------------------------------------------------------------------

def page_history(ledger: re_.Ledger, page: int) -> tuple[list[str], list[dict[str, Any]]]:
    """The page's texts from the sealed one, one per record applied to it,
    and those records."""
    records = [r for r in ledger.records if r["page"] == page]
    states = [ledger.original[page]]
    for record in records:
        text = states[-1]
        offset = record["offset"]
        states.append(text[:offset] + record["after"] + text[offset + len(record["before"]):])
    return states, records


def holds(text: str, start: int, end: int, site: Mapping[str, Any]) -> bool:
    return (0 <= start <= end <= len(text) and text[start:end] == site.get("text")
            and pp.CJK(text[:start])[-8:] == site.get("before")
            and pp.CJK(text[end:])[:8] == site.get("after"))


def locate(question: Mapping[str, Any], ledger: re_.Ledger,
           histories: dict[int, tuple[list[str], list[dict[str, Any]]]]) -> tuple[int, int] | str:
    """The question's site in its page as it stands: (start, end), or why it
    cannot be placed ("conflict E0012" when a record applied after it was
    planned overlaps it)."""
    site = question.get("site")
    page = question.get("page")
    if not isinstance(site, Mapping) or page not in ledger.texts:
        return "the question names no site on a page under repair"
    if page not in histories:
        histories[page] = page_history(ledger, page)
    states, records = histories[page]
    start, end = site.get("start"), site.get("end")
    # A question planned beside a deletion of its own rule (the marks left
    # where a running head was deleted) names that deletion: it is what the
    # question follows, not an edit that made it moot.
    follows = question.get("follows") if isinstance(question.get("follows"), Mapping) else None
    if isinstance(start, int) and isinstance(end, int):
        for i in range(len(states) - 1, -1, -1):
            if not holds(states[i], start, end, site):
                continue
            s, e = start, end
            f = follows["start"] if follows and isinstance(follows.get("start"), int) else None
            for record in records[i:]:
                o, lb = record["offset"], len(record["before"])
                if f is not None and o == f and record["before"] == follows.get("text") \
                        and not record["after"] and s <= o and o + lb <= e:
                    e -= lb
                    f = None
                    continue
                if re_.overlaps((s, e), (o, o + lb)):
                    return f"conflict {record['id']}"
                if o + lb <= s:
                    shift = len(record["after"]) - lb
                    s, e = s + shift, e + shift
                    f = f + shift if f is not None else None
            return s, e
    text = ledger.texts[page]
    want = site.get("text") or ""
    stream = ra.stream(text)
    found = []
    places = range(len(text) + 1) if not want else [m.start() for m in re.finditer(re.escape(want), text)]
    for p in places:
        c = bisect.bisect_left(stream.offsets, p)
        e = bisect.bisect_left(stream.offsets, p + len(want))
        if stream.chars[max(0, c - 8):c] == site.get("before") and stream.chars[e:e + 8] == site.get("after"):
            found.append(p)
    if len(found) == 1 or (found and not want and found[-1] - found[0] == len(found) - 1
                           and not text[found[0]:found[-1]].strip()):
        return found[0], found[0] + len(want)
    return "the site is not in the page as it stands" if not found else "the site stands on the page more than once"


@dataclass
class Spot:
    """A located site: the page text, the site, the anchors (the nearest
    characters outside it that the page and engine A share; None at the
    page's edge), the gap between them, and what each engine read there."""
    page: int
    text: str
    start: int
    end: int
    reading: rs.PageReading
    kb: int | None
    ka: int | None
    gap_start: int
    gap_end: int
    a_read: str | None
    b_read: str | None
    a_wide: str
    b_wide: str

    @property
    def s(self) -> ra.Stream:
        return self.reading.s

    def jb(self) -> int | None:
        return self.reading.a_index(self.kb) if self.kb is not None else None

    def ja(self) -> int | None:
        return self.reading.a_index(self.ka) if self.ka is not None else None

    def gap(self) -> str:
        return self.text[self.gap_start:self.gap_end]

    def before(self, size: int = CONTEXT) -> str:
        if self.kb is None:
            return ""
        return self.s.chars[max(0, self.kb - size + 1):self.kb + 1]

    def after(self, size: int = CONTEXT) -> str:
        if self.ka is None:
            return ""
        return self.s.chars[self.ka:self.ka + size]

    def readings(self) -> list[str]:
        return [r for r in (self.a_read, self.b_read) if r is not None]

    def engine_chars(self) -> Counter:
        """Every CJK character an engine read between the anchors or at them."""
        return Counter(pp.CJK(self.a_wide)) | Counter(pp.CJK(self.b_wide))

    def both_read(self) -> Counter:
        """The CJK characters both engines read between the anchors."""
        if self.a_read is None or self.b_read is None:
            return Counter()
        return Counter(pp.variant_fold(pp.CJK(self.a_read))) & Counter(pp.variant_fold(pp.CJK(self.b_read)))

    def gap_chars(self) -> str:
        return pp.CJK(self.gap())

    def seen(self) -> int:
        """How many characters the page and both engines each hold between
        the anchors, whatever glyph each read (a glyph engine A reads one
        way and engine B and the page another, variants neither table
        joins, is one character all three saw): an answer holding fewer
        deletes one of them."""
        if self.a_read is None or self.b_read is None:
            return 0
        return min(len(pp.CJK(self.a_read)), len(pp.CJK(self.b_read)), len(self.gap_chars()))


def engine_between(stream: ra.Stream, to: Sequence[int | None], lo: int | None, hi: int | None,
                   wide: bool = False) -> str | None:
    """What an engine read between sealed characters LO and HI (None: the
    page's edge), from its nearest aligned characters outward; with WIDE,
    those characters too."""
    n = len(to)
    while lo is not None and lo >= 0 and to[lo] is None:
        lo -= 1
    while hi is not None and hi < n and to[hi] is None:
        hi += 1
    a_lo = stream.offsets[to[lo]] + (0 if wide else 1) if lo is not None and lo >= 0 else 0
    a_hi = stream.offsets[to[hi]] + (1 if wide else 0) if hi is not None and hi < n else len(stream.text)
    return stream.text[a_lo:a_hi] if a_lo <= a_hi else None


def make_spot(reading: rs.PageReading, page: int, start: int, end: int) -> Spot:
    s = reading.s
    to_a = reading.align.sealed_to_a
    i = bisect.bisect_left(s.offsets, start) - 1
    while i >= 0 and to_a[i] is None:
        i -= 1
    kb = i if i >= 0 else None
    i = bisect.bisect_left(s.offsets, end)
    while i < len(s.chars) and to_a[i] is None:
        i += 1
    ka = i if i < len(s.chars) else None
    gap_start = s.offsets[kb] + 1 if kb is not None else 0
    gap_end = s.offsets[ka] if ka is not None else len(reading.text)
    a, b = reading.align.a, reading.align.b
    to_b = reading.align.sealed_to_b
    a_read = engine_between(a, to_a, kb, ka)
    b_read = engine_between(b, to_b, kb, ka)
    a_wide = engine_between(a, to_a, kb, ka, wide=True) or ""
    b_wide = engine_between(b, to_b, kb, ka, wide=True) or ""
    return Spot(page, reading.text, start, end, reading, kb, ka, gap_start, gap_end, a_read, b_read,
                a_wide, b_wide)


# --- geometry and crops ------------------------------------------------------------

class PageImage:
    """A page's render and what the crops read of it: engine A's blocks'
    cells, the book model's band and page geometry."""

    def __init__(self, book: Any, model: Mapping[str, Any], page: int, reading: rs.PageReading):
        self.page = page
        self.render = book.pages[page].render
        self.size = rm.page_size(book.pages[page])
        entry = rm.page_entry(model, page)
        self.band = [b["box"] for b in entry.get("band") or [] if b.get("box")]
        self.geometry = entry.get("geometry") or {}
        self.blocks = reading.pd.a_blocks
        self.block_of = reading.block_of
        self.first: dict[int, int] = {}
        for j, b in enumerate(self.block_of):
            self.first.setdefault(b, j)
        self._images: dict[bool, Any] = {}
        self._cells: dict[int, list[dict[str, Any]] | None] = {}
        self._gray: Any = None
        self._grays: dict[str, Any] = {}
        self.paper = 255
        # The book's pitch: a page whose own frame gives another (a contents
        # page of short lines) has no frame the crops can draw.
        self.book_pitch = (model.get("geometry") or {}).get("pitchMedian")

    def image(self, mask: bool) -> Any:
        """The render in RGB, the band painted with the page's paper when
        MASK; None when it cannot be read."""
        if mask not in self._images:
            try:
                from PIL import Image, ImageDraw
                with Image.open(self.render) as opened:
                    plain = opened.convert("RGB")
            except Exception:  # noqa: BLE001 - an unreadable render cuts no crop
                self._images[mask] = None
                return None
            histogram = plain.convert("L").histogram()
            self.paper = max(range(256), key=lambda level: histogram[level])
            if mask and self.band:
                width, height = plain.size
                pen = ImageDraw.Draw(plain)
                for x, y, w, h in self.band:
                    pen.rectangle([max(0, int((x - 0.004) * width)), max(0, int((y - 0.004) * height)),
                                   min(width - 1, int((x + w + 0.004) * width) + 1),
                                   min(height - 1, int((y + h + 0.004) * height) + 1)],
                                  fill=(self.paper,) * 3)
            self._images[mask] = plain
        return self._images[mask]

    def cells(self, block: int) -> list[dict[str, Any]] | None:
        if block not in self._cells:
            self._cells[block] = (block_cells(self.render, self.blocks[block], self.size, self.pitch(),
                                              self.image(True))
                                  if 0 <= block < len(self.blocks) and self.size else None)
        return self._cells[block]

    def cell(self, j: int | None) -> dict[str, Any] | None:
        """The pixel cell of engine A's body character J."""
        if j is None or j < 0 or j >= len(self.block_of):
            return None
        b = self.block_of[j]
        cells = self.cells(b)
        local = j - self.first[b]
        return cells[local] if cells and 0 <= local < len(cells) else None

    def head_above(self, cell: Mapping[str, Any], mask: bool) -> float | None:
        """The top of the ink printed just above the first glyph engine A
        read in CELL's column (its measured top): run by run upward, each run
        at most HEAD_GAP pitches above the one below it, at most HEAD_REACH
        pitches up, on the render as the crop shows it (MASK: the band
        painted out) - a unit's number set at the head of its column over
        the title, which engine A read in no block.  None when nothing is
        printed there (a column set flush from the frame's top, an indented
        paragraph's first column, a page that cannot be read)."""
        if cell.get("across"):
            return None
        key = "masked" if mask else "plain"
        if key not in self._grays:
            image = self.image(mask)
            if image is None:
                return None
            import numpy as np
            self._grays[key] = np.asarray(image.convert("L"))
        gray = self._grays[key]
        pitch = cell["pitch"]
        height, width = gray.shape
        span = cell["right"] - cell["left"]
        x0, x1 = max(0, int(cell["left"] + 0.1 * span)), min(width, int(math.ceil(cell["right"] - 0.1 * span)))
        top = cell["top"]
        y0, y1 = max(0, int(top - HEAD_REACH * pitch)), min(height, int(top))
        if x1 <= x0 or y1 <= y0:
            return None
        rows = (gray[y0:y1, x0:x1] < self.paper - 60).sum(axis=1) >= 2
        runs: list[list[int]] = []
        for y, inked in enumerate(rows):
            if not inked:
                continue
            if runs and y - runs[-1][1] <= 0.1 * pitch:
                runs[-1][1] = y + 1
            else:
                runs.append([y, y + 1])
        found = None
        edge = top
        for a, b in reversed(runs):
            if b - a < HEAD_RUN * pitch:
                continue   # a speck, a stray dot
            if y0 + b < edge - HEAD_GAP * pitch:
                break
            edge = y0 + a
            found = edge
        return found

    def glyph_below_number(self, cell: Mapping[str, Any], snapped: Mapping[str, Any],
                           mask: bool) -> dict[str, Any] | None:
        """CELL, the first glyph engine A read in its column (SNAPPED as the
        crop would draw it), moved onto the first glyph below the ink engine
        A's box cut at its top: a run of ink that starts above the column's
        measured top and ends less than half a pitch below it - print set
        over the column (a unit's or a contents entry's number over its
        title), mostly outside the block, which engine A did not read and
        whose cut foot its cells were spread from.  On a real contents page
        the tick after the number was drawn above it, and the model answered
        that nothing was printed there.  The glyph: the next run at least
        half a pitch tall, at most HEAD_GAP pitches below that ink (runs as
        head_above reads them).  None where no ink is cut at the column's
        top (a column whose box holds its first glyph, a glyph the box cuts
        by less than half), where the cell is drawn below that ink already,
        or where no such glyph is there."""
        if cell.get("across"):
            return None
        key = "masked" if mask else "plain"
        if key not in self._grays:
            image = self.image(mask)
            if image is None:
                return None
            import numpy as np
            self._grays[key] = np.asarray(image.convert("L"))
        gray = self._grays[key]
        pitch, top = cell["pitch"], cell["top"]
        height, width = gray.shape
        span = cell["right"] - cell["left"]
        x0, x1 = max(0, int(cell["left"] + 0.1 * span)), min(width, int(math.ceil(cell["right"] - 0.1 * span)))
        y0 = max(0, int(top - HEAD_REACH * pitch))
        y1 = min(height, int(top + (HEAD_GAP + GLYPH_RUN) * pitch))
        if x1 <= x0 or y1 <= y0:
            return None
        rows = (gray[y0:y1, x0:x1] < self.paper - 60).sum(axis=1) >= 2
        runs: list[list[int]] = []
        for y, inked in enumerate(rows):
            if not inked:
                continue
            if runs and y - runs[-1][1] <= 0.1 * pitch:
                runs[-1][1] = y + 1
            else:
                runs.append([y, y + 1])
        spans = [(y0 + a, y0 + b) for a, b in runs]
        cut = next((r for r in spans if r[0] < top - 0.1 * pitch and r[1] > top), None)
        if cut is None or cut[1] >= top + 0.5 * pitch or snapped["y0"] > cut[1]:
            return None
        below = next((r for r in spans if r[0] >= cut[1] and r[1] - r[0] >= 0.5 * pitch), None)
        if below is None or below[0] - cut[1] > HEAD_GAP * pitch:
            return None
        return dict(snapped, y0=float(below[0]), y1=float(min(below[1], below[0] + pitch)), belowNumber=True)

    def framed(self) -> bool:
        """Whether the page's frame and pitch are the book's: its pitch
        within a quarter of the book's."""
        own = self.geometry.get("pitch")
        if not own or not self.geometry.get("frameTop"):
            return False
        return not self.book_pitch or 0.75 <= own / self.book_pitch <= 1.33

    def frame_top(self, x: float) -> float | None:
        g = self.geometry
        if not self.framed() or not self.size:
            return None
        return g["frameTop"] + (g.get("frameSlope") or 0.0) * (x - self.size[0] / 2)

    def pitch(self) -> float | None:
        return self.geometry.get("pitch") if self.framed() else self.book_pitch

    def snap(self, cell: dict[str, Any] | None) -> dict[str, Any] | None:
        """CELL moved onto its glyph's ink: the run of inked rows (in the
        middle half of its column, where a mark beside the glyph is not)
        at least half a pitch tall that is nearest the estimate, within
        SNAP_REACH of a pitch; the estimate itself where there is none (a
        glyph of one stroke, a page that cannot be read).  The estimate
        spreads what engine A read evenly down its columns (block_cells), so
        it drifts a little; a glyph a whole cell away is its neighbour.  A
        run is one glyph's ink only when it is at most GLYPH_RUN pitches tall
        and both its ends lie inside the rows searched: glyphs set close
        together, or a glyph and a dash's stroke, run together into one
        taller run, and on a real page such a run moved a cell a glyph up (a
        tick inside a dash, or between the two characters before the one it
        marks)."""
        if cell is None or cell["across"]:
            return cell
        if self._gray is None:
            image = self.image(False)
            if image is None:
                return cell
            import numpy as np
            self._gray = np.asarray(image.convert("L"))
        import numpy as np
        height, width = self._gray.shape
        pitch = cell["pitch"]
        span = cell["right"] - cell["left"]
        x0, x1 = int(cell["left"] + 0.25 * span), int(math.ceil(cell["right"] - 0.25 * span))
        y0, y1 = max(0, int(cell["y0"] - pitch)), min(height, int(math.ceil(cell["y1"] + pitch)))
        if x1 <= x0 or y1 <= y0:
            return cell
        rows = (self._gray[y0:y1, max(0, x0):min(width, x1)] < self.paper - 60).any(axis=1)
        runs: list[list[int]] = []
        for y, inked in enumerate(rows):
            if not inked:
                continue
            if runs and y - runs[-1][1] <= 0.2 * pitch:
                runs[-1][1] = y + 1
            else:
                runs.append([y, y + 1])
        centre = (cell["y0"] + cell["y1"]) / 2
        glyphs = [(a + y0, b + y0) for a, b in runs
                  if 0.5 * pitch <= b - a <= GLYPH_RUN * pitch and a > 0 and b < len(rows)]
        if not glyphs:
            return cell
        top, foot = min(glyphs, key=lambda r: abs((r[0] + r[1]) / 2 - centre))
        if abs((top + foot) / 2 - centre) > SNAP_REACH * pitch:
            return cell
        return dict(cell, y0=float(top), y1=float(foot), snapped=True)


# What engine A read, as the print sets it down a column: a CJK character,
# a group of figures, a dash stroke or a Latin letter takes a cell; a mark
# takes the share of a cell its kind takes in the block (fit_shares): a
# print may set its full stops in a cell of their own and its commas beside
# the character before them.
UNIT = re.compile(r"[0-9０-９]+|\S")
FULL_CELL = frozenset("—―─‒–-|｜")
MARK_KINDS = {"stop": frozenset("。．？！?!…"), "pause": frozenset("，、；：,;:·•・"),
              "paired": frozenset("「」『』（）《》〈〉()︵︶[]［］")}


def units_of(text: str) -> list[tuple[str, str]]:
    """TEXT's units in reading order: (unit, kind) - kind `whole` for a unit
    that takes a cell (a CJK character, a group of figures, a dash, a Latin
    letter), else its mark kind (MARK_KINDS, `other`)."""
    out = []
    for match in UNIT.finditer(text):
        unit = match.group()
        if pp.CJK(unit) or unit[0] in "0123456789０１２３４５６７８９" or unit in FULL_CELL \
                or (unit.isascii() and unit.isalpha()):
            out.append((unit, "whole"))
        else:
            out.append((unit, next((k for k, marks in MARK_KINDS.items() if unit in marks), "other")))
    return out


def text_columns_of(image: Any, box: Sequence[float]) -> list[tuple[int, int, int, int]] | None:
    """measure_columns on an image in memory (the render with its band
    painted out): the columns of text of a block's box, right to left, in
    page pixels."""
    width, height = image.size
    x, y, w, h = box
    left, top = int(x * width), int(y * height)
    region = image.convert("L").crop((left, top, int((x + w) * width), int((y + h) * height)))
    if region.width < 20 or region.height < 20:
        return None
    ink = pp.ink_of(region)
    columns = pp.text_columns(ink, pp.ink_columns(ink))
    return [(left + a, left + b, top + y0, top + y1) for a, b, y0, y1 in columns] or None


def partition(sizes: Sequence[float], rooms: Sequence[float], slack: float | None = 4.0) -> list[int] | None:
    """Where the units of SIZES (in reading order) split among columns of
    ROOMS cells, each column's units filling it as closely as they can (the
    least sum of squared misfits); the index each column starts at.  A
    column is looked for within SLACK cells (or a quarter of its room) of
    its room first, then anywhere.  None when there are fewer units than
    columns."""
    n, c = len(sizes), len(rooms)
    if n < c:
        return None
    total = [0.0]
    for size in sizes:
        total.append(total[-1] + size)
    inf = float("inf")
    # best[k][i]: the least misfit of the first k columns holding units[:i].
    best = [[inf] * (n + 1) for _ in range(c + 1)]
    back = [[0] * (n + 1) for _ in range(c + 1)]
    best[0][0] = 0.0
    for k in range(1, c + 1):
        room = rooms[k - 1]
        reach = None if slack is None else max(slack, 0.25 * room)
        for i in range(k, n - (c - k) + 1):
            lo, hi = k - 1, i
            if reach is not None:
                lo = max(lo, bisect.bisect_left(total, total[i] - room - reach))
                hi = min(hi, bisect.bisect_right(total, total[i] - room + reach))
            for j in range(lo, hi):
                if best[k - 1][j] == inf:
                    continue
                cost = best[k - 1][j] + (total[i] - total[j] - room) ** 2
                if cost < best[k][i]:
                    best[k][i], back[k][i] = cost, j
    if best[c][n] == inf:
        return partition(sizes, rooms, None) if slack is not None else None
    starts, i = [], n
    for k in range(c, 0, -1):
        i = back[k][i]
        starts.append(i)
    return starts[::-1]


def fit_shares(units: Sequence[tuple[str, str]], rooms: Sequence[float]) -> tuple[dict[str, float], list[int]] | None:
    """Each mark kind's share of a cell, and the columns' first units: the
    columns split by the shares (partition), the shares fit to the split by
    least squares (each column's room less its whole cells, over its marks
    of each kind; 0 to 1), three times from the block's average."""
    import numpy as np
    kinds = sorted({kind for _, kind in units} - {"whole"})
    whole = sum(1 for _, kind in units if kind == "whole")
    marks = len(units) - whole
    average = min(1.0, max(0.0, (sum(rooms) - whole) / marks)) if marks else 0.0
    shares = {kind: average for kind in kinds}
    starts = None
    for _ in range(3):
        sizes = [1.0 if kind == "whole" else shares[kind] for _, kind in units]
        found = partition(sizes, rooms)
        if found is None:
            return None
        starts = found
        if not kinds:
            break
        bounds = starts + [len(units)]
        rows, targets = [], []
        for k, room in enumerate(rooms):
            chunk = units[bounds[k]:bounds[k + 1]]
            rows.append([sum(1 for _, kind in chunk if kind == mark) for mark in kinds])
            targets.append(room - sum(1 for _, kind in chunk if kind == "whole"))
        solved, *_ = np.linalg.lstsq(np.array(rows, float), np.array(targets, float), rcond=None)
        fitted = {kind: float(min(1.0, max(0.0, value))) for kind, value in zip(kinds, solved)}
        if fitted == shares:
            break
        shares = fitted
    return shares, starts or []


def ink_runs(gray: Any, paper: int, x0: float, x1: float, top: float, foot: float,
             pitch: float) -> list[tuple[float, float, bool]]:
    """The runs of inked rows down the middle four fifths of a column (the
    rest may hold a neighbour's bleed; a glyph like 門 has no ink in its
    middle; a row is inked when an eighth of it is), a gap under a tenth
    of PITCH joined
    (a full stop set close under its character stands a fifth of a pitch
    below it on a real page), specks dropped: (top, foot, whether it is mark-like) in
    page pixels.  A run is mark-like when it is under half a pitch tall and
    its ink under half the column wide (a stroke of 一 or 二 is as wide as
    the column)."""
    height, width = gray.shape
    span = x1 - x0
    a, b = max(0, int(x0 + 0.1 * span)), min(width, int(math.ceil(x1 - 0.1 * span)))
    y0, y1 = max(0, int(top)), min(height, int(math.ceil(foot)))
    if b <= a or y1 <= y0:
        return []
    # A row is inked when an eighth of the band is: a stroke's end that
    # touches the next glyph is not, the two sides of 門 are.
    rows = (gray[y0:y1, a:b] < paper - 60).sum(axis=1) >= max(2, 0.125 * (b - a))
    runs: list[list[int]] = []
    for y, inked in enumerate(rows):
        if not inked:
            continue
        if runs and y - runs[-1][1] <= 0.1 * pitch:
            runs[-1][1] = y + 1
        else:
            runs.append([y, y + 1])
    left, right = max(0, int(x0)), min(width, int(math.ceil(x1)))
    out = []
    for r0, r1 in runs:
        if r1 - r0 < 0.05 * pitch:
            continue
        across = (gray[y0 + r0:y0 + r1, left:right] < paper - 60).any(axis=0).nonzero()[0]
        wide = (across[-1] - across[0] + 1) / max(1, right - left) if len(across) else 0.0
        out.append((float(y0 + r0), float(y0 + r1), r1 - r0 < 0.5 * pitch and wide < 0.5))
    return out


# The costs of aligning a column's units with its runs of ink (align_units),
# in pitches: a whole unit matched to no run, a run no unit explains, a mark
# matched to no run, and each pitch between where a unit's run stands and
# where an even spread of the column puts it.
MISSING_WHOLE, SKIPPED_RUN, MISSING_MARK, DRIFT = 2.5, 0.8, 0.3, 0.5


def align_units(kinds: Sequence[str], expected: Sequence[float], runs: Sequence[tuple[float, float, bool]],
                pitch: float) -> list[tuple[float, float] | None]:
    """Each unit's ink (the span of the runs it is matched to), or None: the
    units of a column in order (KINDS: `whole` or a mark kind) against its
    runs of ink in order (ink_runs) - a whole unit takes one to three runs
    (a glyph whose strokes stand apart), none of them mark-like when more
    than one, or two to five whole units share one run about as many
    glyphs tall (glyphs that touch), split evenly; a mark takes one run or none, a
    mark-like run first; a run no unit explains is skipped; EXPECTED (each
    unit's centre in an even spread) is a weak pull, so the order of the ink
    decides."""
    n, m = len(kinds), len(runs)
    inf = float("inf")
    best = [[inf] * (m + 1) for _ in range(n + 1)]
    back: list[list[tuple[int, int, str] | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    best[0][0] = 0.0

    def offer(i: int, r: int, cost: float, step: tuple[int, int, str]) -> None:
        if cost < best[i][r]:
            best[i][r], back[i][r] = cost, step

    for i in range(n + 1):
        for r in range(m + 1):
            here = best[i][r]
            if here == inf:
                continue
            if r < m:
                offer(i, r + 1, here + SKIPPED_RUN + 0.5 * (runs[r][1] - runs[r][0]) / pitch, (i, r, "skip"))
            if i == n:
                continue
            whole = kinds[i] == "whole"
            offer(i + 1, r, here + (MISSING_WHOLE if whole else MISSING_MARK), (i, r, "none"))
            for k in (1, 2, 3) if whole else (1,):
                if r + k > m:
                    break
                a, b = runs[r][0], runs[r + k - 1][1]
                h = (b - a) / pitch
                if k > 1 and any(runs[q + 1][0] - runs[q][1] > 0.45 * pitch or runs[q][2] or runs[q + 1][2]
                                 for q in range(r, r + k - 1)):
                    break
                fit = DRIFT * abs((a + b) / 2 - expected[i]) / pitch
                markish = runs[r][2] and k == 1
                if whole:
                    size = max(0.0, h - 1.25) * 4 + (0.5 if h < 0.25 else 0.0) + (1.0 if markish else 0.0)
                else:
                    size = 0.0 if markish else (2.0 if h > 0.7 else 0.6)
                offer(i + 1, r + k, here + fit + size, (i, r, f"take{k}"))
            if whole and r < m and not runs[r][2]:
                a, b = runs[r][0], runs[r][1]
                h = (b - a) / pitch
                for k in range(2, 6):
                    if i + k > n or kinds[i + k - 1] != "whole":
                        break
                    if abs(h - k) > 0.6:
                        continue
                    part = (b - a) / k
                    fit = sum(DRIFT * abs(a + (q + 0.5) * part - expected[i + q]) / pitch for q in range(k))
                    offer(i + k, r + 1, here + fit + 0.3 * (k - 1), (i, r, f"split{k}"))
    out: list[tuple[float, float] | None] = [None] * n
    i, r = n, m
    while (i, r) != (0, 0) and back[i][r] is not None:
        pi, pr, how = back[i][r]
        if how.startswith("take"):
            out[pi] = (runs[pr][0], runs[r - 1][1])
        elif how.startswith("split"):
            a, b = runs[pr][0], runs[pr][1]
            k = int(how[5:])
            part = (b - a) / k
            for q in range(k):
                out[pi + q] = (a + q * part, a + (q + 1) * part)
        i, r = pi, pr
    return out


def trim_to_glyphs(kinds: Sequence[str], inks: list[tuple[float, float] | None]) -> list[tuple[float, float] | None]:
    """A whole unit's ink more than a fifth taller than the column's median
    glyph, with a mark before or after it: the mark's ink joined to it (a
    full stop set close under its character) - cut to a glyph's height on
    the other side."""
    heights = sorted(b - a for (a, b), kind in ((ink, kind) for ink, kind in zip(inks, kinds) if ink)
                     if kind == "whole")
    if not heights:
        return inks
    glyph = heights[len(heights) // 2]
    out = list(inks)
    for i, (ink, kind) in enumerate(zip(inks, kinds)):
        if ink is None or kind != "whole" or ink[1] - ink[0] <= 1.2 * glyph:
            continue
        if i + 1 < len(kinds) and kinds[i + 1] != "whole":
            out[i] = (ink[0], ink[0] + glyph)
        elif i > 0 and kinds[i - 1] != "whole":
            out[i] = (ink[1] - glyph, ink[1])
    return out


def block_cells(render: Path, block: Mapping[str, Any], size: tuple[int, int],
                pitch: float | None = None, masked: Any = None) -> list[dict[str, Any]] | None:
    """The pixel cell of each CJK character of engine A's BLOCK, in its
    reading order.  A vertical block's columns are measured on the render as
    crop_glyph measures them (the columns of text) - on MASKED when given,
    the render with the running head's band painted out: a block whose box
    reaches into the band's column would take the head and the folio for
    its last column.  What engine A read (units_of) is split among the
    columns so each column's units fill its ink extent over the page's
    PITCH, each mark kind taking the share of a cell the block shows
    (fit_shares), and each column's units are spread over its own extent:
    a column's first and last characters stand at its ink's ends.  A
    horizontal block's characters run left to right across its box, as
    engine A reads them.  On MASKED each column's units are then matched to
    its runs of ink (align_units): a character's cell is its glyph's ink,
    where it has one.  Where the columns cannot be measured or split,
    from the box's shape as crop_band estimates them.  None for a block with
    no character."""
    n = len(pp.CJK(str(block["text"])))
    if n == 0 or not size:
        return None
    width, height = size
    x, y, w, h = block["box"]
    left, top, bw, bh = x * width, y * height, w * width, h * height
    if bw <= 0 or bh <= 0:
        return None
    # A box twice as tall as it is wide is a column, one twice as wide as
    # tall a line, whatever its ink says (block_is_vertical took a contents
    # line with its figure beside it for a line across); else the ink.
    across = bw > 2 * bh or (bh <= 2 * bw and pp.block_is_vertical(render, block["box"]) is False)
    if across:
        step = bw / n
        return [{"x0": left + i * step, "x1": left + (i + 1) * step, "y0": top, "y1": top + bh,
                 "column": 0, "top": top, "foot": top + bh, "left": left, "right": left + bw,
                 "pitch": step, "across": True} for i in range(n)]
    columns = (text_columns_of(masked, block["box"]) if masked is not None
               else pp.measure_columns(render, block["box"], text_only=True))
    cells: list[dict[str, Any]] = []
    units = units_of(str(block["text"]))
    if columns and units:
        extents = [max(bottom - t, 1) for _, _, t, bottom in columns]
        if not pitch:
            # Without the page's pitch: every unit a cell.
            pitch = sum(extents) / len(units)
        fitted = fit_shares(units, [e / pitch for e in extents])
        gray = None
        if fitted is not None and masked is not None:
            import numpy as np
            gray = np.asarray(masked.convert("L"))
            histogram = masked.convert("L").histogram()
            paper = max(range(256), key=lambda level: histogram[level])
        if fitted is not None:
            shares, starts = fitted
            bounds = starts + [len(units)]
            for c, (x0, x1, t, bottom) in enumerate(columns):
                chunk = units[bounds[c]:bounds[c + 1]]
                sizes = [1.0 if kind == "whole" else shares[kind] for _, kind in chunk]
                step = (bottom - t) / sum(sizes) if sum(sizes) else pitch
                spread, used = [], 0.0
                for size_of in sizes:
                    spread.append((t + used * step, t + (used + size_of) * step))
                    used += size_of
                inks: list[tuple[float, float] | None] = [None] * len(chunk)
                if gray is not None:
                    runs = ink_runs(gray, paper, x0, x1, t - 0.5 * step, bottom + 0.5 * step, step)
                    kinds = [kind for _, kind in chunk]
                    inks = trim_to_glyphs(kinds, align_units(kinds, [(a + b) / 2 for a, b in spread], runs, step))
                for (unit, _), (y0, y1), ink in zip(chunk, spread, inks):
                    if pp.CJK(unit):
                        if ink is not None:
                            y0, y1 = ink
                        cells.append({"x0": float(x0), "x1": float(x1), "y0": y0, "y1": y1,
                                      "column": c, "top": float(t), "foot": float(bottom), "left": float(x0),
                                      "right": float(x1), "pitch": step, "across": False,
                                      "inked": ink is not None})
    if len(cells) != n:
        per_side = max((bw * bh / n) ** 0.5, 1e-6)
        k = max(1, round(bw / per_side))
        per = math.ceil(n / k)
        step = bw / k
        cells = []
        for c in range(k):
            count = max(0, min(per, n - c * per))
            x0, x1 = left + bw - (c + 1) * step, left + bw - c * step
            for i in range(count):
                cells.append({"x0": x0, "x1": x1, "y0": top + i * bh / per, "y1": top + (i + 1) * bh / per,
                              "column": c, "top": top, "foot": top + bh, "left": x0, "right": x1,
                              "pitch": bh / per, "across": False})
    return cells[:n] or None


@dataclass
class Piece:
    """A rectangle of the page cut for a crop (page pixels)."""
    box: list[float]


@dataclass
class Mark:
    """A mark drawn on a piece: a box or a line (page pixels)."""
    piece: int
    shape: str   # "box" or "line"
    at: tuple[float, float, float, float]
    colour: tuple[int, int, int] = RED


def compose(image: Any, pieces: Sequence[Piece], marks: Sequence[Mark], paper: int,
            across: bool = False) -> bytes | None:
    """The crop: PIECES cut from IMAGE and set side by side in reading
    order (right to left; one above the other when ACROSS), a strip of paper
    between; enlarged (upscale_crop); the MARKS drawn 2 px wide; padded to
    the server's aspect limit (fit_media_aspect).  None when nothing can be
    cut."""
    from PIL import Image, ImageDraw
    width, height = image.size
    cut = []
    for piece in pieces:
        x0, y0, x1, y1 = piece.box
        box = (max(0, int(x0)), max(0, int(y0)), min(width, int(math.ceil(x1))), min(height, int(math.ceil(y1))))
        if box[2] - box[0] < 2 or box[3] - box[1] < 2:
            return None
        cut.append((box, image.crop(box)))
    if not cut:
        return None
    fill = (paper,) * 3
    offsets: list[tuple[int, int]] = []
    if len(cut) == 1:
        canvas = cut[0][1]
        offsets = [(0, 0)]
    elif not across:
        gap = max(8, min(c.width for _, c in cut) // 2)
        total = sum(c.width for _, c in cut) + gap * (len(cut) - 1)
        canvas = Image.new("RGB", (total, max(c.height for _, c in cut)), fill)
        at = total
        for _, c in cut:
            at -= c.width
            canvas.paste(c, (at, 0))
            offsets.append((at, 0))
            at -= gap
    else:
        gap = max(8, min(c.height for _, c in cut) // 4)
        total = sum(c.height for _, c in cut) + gap * (len(cut) - 1)
        canvas = Image.new("RGB", (max(c.width for _, c in cut), total), fill)
        at = 0
        for _, c in cut:
            canvas.paste(c, (0, at))
            offsets.append((0, at))
            at += c.height + gap
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG")
    enlarged = pp.upscale_crop(buffer.getvalue()) or buffer.getvalue()
    with Image.open(io.BytesIO(enlarged)) as opened:
        big = opened.convert("RGB")
    factor = big.width / canvas.width
    pen = ImageDraw.Draw(big)
    for mark in marks:
        (bx, by, _, _), _ = cut[mark.piece]
        ox, oy = offsets[mark.piece]
        x0, y0, x1, y1 = [((v - bx) + ox) * factor if k % 2 == 0 else ((v - by) + oy) * factor
                          for k, v in enumerate(mark.at)]
        if mark.shape == "box":
            pen.rectangle([min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)], outline=mark.colour,
                          width=MARK_WIDTH)
        else:
            pen.line([x0, y0, x1, y1], fill=mark.colour, width=MARK_WIDTH)
    buffer = io.BytesIO()
    big.save(buffer, format="PNG")
    return pp.fit_media_aspect(buffer.getvalue())


def column_key(cell: Mapping[str, Any]) -> tuple[float, float]:
    return (round(cell["left"]), round(cell["right"]))


def stretch(pim: PageImage, spot: Spot, reach: int, mask: bool = True) -> tuple[list[Piece], dict[str, Any]] | None:
    """The pieces of a crop from the anchor before to the anchor after (by
    engine A's cells), REACH characters beyond each, the columns between
    them whole; and the cells: before, after, and the columns' pieces.  A
    column the place runs into (after a column break, or at the page's
    start) is cut from its head: what is printed above the first glyph
    engine A read there (PageImage.head_above, on the render as MASK shows
    it) is between the anchors too."""
    jb, ja = spot.jb(), spot.ja()
    cb, ca = pim.cell(jb), pim.cell(ja)
    if cb is None and ca is None:
        return None
    if (cb and cb["across"]) or (ca and ca["across"]):
        return None
    # At the page's edge (no anchor on one side): what engine A read beyond
    # the other anchor, REACH characters of it.
    final = len(pim.block_of) - 1
    lo = jb if jb is not None else max(0, ja - reach)
    hi = ja if ja is not None else min(final, jb + reach)
    columns: list[tuple[tuple[float, float], list[dict[str, Any]]]] = []
    for j in range(lo, hi + 1):
        cell = pim.cell(j)
        if cell is None:
            continue
        key = column_key(cell)
        if columns and columns[-1][0] == key:
            columns[-1][1].append(cell)
        else:
            columns.append((key, [cell]))
    if not columns:
        return None
    pieces: list[Piece] = []
    for n, (_, cells) in enumerate(columns):
        first, last = cells[0], cells[-1]
        pitch = first["pitch"]
        margin = COLUMN_MARGIN * (first["right"] - first["left"])
        top = first["top"] - 0.5 * pitch
        foot = last["foot"] + 0.5 * pitch
        if n == 0 and cb is not None:
            top = max(top, first["y0"] - reach * pitch)
        if n == len(columns) - 1 and ca is not None:
            foot = min(foot, last["y1"] + reach * pitch)
        if cb is None and n == 0:
            top = first["top"] - pitch
        if ca is None and n == len(columns) - 1:
            foot = last["foot"] + pitch
        if n > 0 or cb is None:
            head = pim.head_above(first, mask)
            if head is not None:
                top = min(top, head - 0.5 * pitch)
        pieces.append(Piece([first["left"] - margin, top, first["right"] + margin, foot]))
    return pieces, {"before": cb, "after": ca, "columns": columns, "lo": lo, "hi": hi}


def piece_of(cells: Mapping[str, Any], cell: Mapping[str, Any] | None) -> int | None:
    if cell is None:
        return None
    key = column_key(cell)
    return next((n for n, (k, _) in enumerate(cells["columns"]) if k == key), None)


def tick(pieces: Sequence[Piece], n: int, y: float) -> Mark:
    x0, _, x1, _ = pieces[n].box
    return Mark(n, "line", (x0, y, x1, y))


def print_crop(pim: PageImage, spot: Spot, mask: bool, number: bool = False) -> tuple[bytes | None, int]:
    """Q-P's crop: the stretch from 3 cells before the anchor before to 3
    after the anchor after, red lines at the two places.  Its bytes and how
    many pieces it has.  For a question about a number expected before the
    anchor after (NUMBER: a unit's or a contents entry's), where that anchor
    heads a column the place runs into and stands on ink above engine A's
    block, the line goes above the glyph below that ink
    (PageImage.glyph_below_number): the number is between the lines."""
    found = stretch(pim, spot, PRINT_REACH, mask)
    image = pim.image(mask)
    if found is None or image is None:
        return None, 0
    pieces, cells = found
    marks = []
    cb, ca = pim.snap(cells["before"]), pim.snap(cells["after"])
    if number and ca is not None:
        n = piece_of(cells, ca)
        if n is not None and (n > 0 or cb is None) and cells["columns"][n][1][0] is cells["after"]:
            ca = pim.glyph_below_number(cells["after"], ca, mask) or ca
    if cb is not None:
        marks.append(tick(pieces, piece_of(cells, cb), cb["y1"]))
    else:
        first = cells["columns"][0][1][0]
        marks.append(tick(pieces, 0, first["top"] - 0.25 * first["pitch"]))
    if ca is not None:
        marks.append(tick(pieces, piece_of(cells, ca), ca["y0"]))
    else:
        last = cells["columns"][-1][1][-1]
        marks.append(tick(pieces, len(pieces) - 1, last["foot"] + 0.25 * last["pitch"]))
    return compose(image, pieces, marks, pim.paper), len(pieces)


def glyph_crop(pim: PageImage, spot: Spot, mask: bool) -> bytes | None:
    """Q-G's crop: the place in a red box - from the anchor before's ink to
    the anchor after's in their column, else over the cells of what engine A
    read between them in each column - two cells either side."""
    found = stretch(pim, spot, GLYPH_REACH, mask)
    image = pim.image(mask)
    if found is None or image is None:
        return None
    pieces, cells = found
    cb, ca = pim.snap(cells["before"]), pim.snap(cells["after"])
    jb, ja = spot.jb(), spot.ja()
    inner = [pim.cell(j) for j in range(jb + 1 if jb is not None else cells["lo"],
                                        ja if ja is not None else cells["hi"] + 1)]
    inner = [c for c in inner if c is not None]
    boxes = []
    for n, (key, column) in enumerate(cells["columns"]):
        first = column[0]
        pitch = first["pitch"]
        mine = [c for c in inner if column_key(c) == key]
        y0 = cb["y1"] if cb is not None and column_key(cb) == key else (mine[0]["y0"] if mine else None)
        y1 = ca["y0"] if ca is not None and column_key(ca) == key else (mine[-1]["y1"] if mine else None)
        if y0 is None and y1 is None:
            continue
        if y0 is None:
            y0 = first["top"] - 0.25 * pitch
        if y1 is None:
            y1 = column[-1]["foot"] + 0.25 * pitch if not mine else max(mine[-1]["y1"], y0 + pitch)
        if y1 - y0 < 0.4 * pitch and len(cells["columns"]) > 1:
            continue
        if y1 - y0 < 0.6 * pitch:
            middle = (y0 + y1) / 2
            y0, y1 = middle - 0.5 * pitch, middle + 0.5 * pitch
        span = first["right"] - first["left"]
        boxes.append(Mark(n, "box", (first["left"] - 0.1 * span, y0 - 0.1 * pitch, first["right"] + 0.1 * span,
                                     y1 + 0.1 * pitch)))
    if not boxes:
        first = cells["columns"][0][1][-1]
        boxes.append(Mark(0, "box", (first["left"], first["y1"] - 0.2 * first["pitch"], first["right"],
                                     first["y1"] + 0.8 * first["pitch"])))
    return compose(image, pieces, boxes, pim.paper)


def edge_crop(pim: PageImage, edge: str, cells: int, mask: bool) -> bytes | None:
    """F8's crop: the page's first body column (the rightmost the page's own
    measure finds) from above its head, or its last (the leftmost) to below
    its foot, with CELLS cells at that end in a red box - where the
    character both engines read beyond the page's text is printed.  From
    the page's measure, not engine A's cells: on a real page whose running
    head engine A read into its last block (no band found), the block's
    cells put the text's last characters in the head's column.  None on a
    page with no measured columns."""
    columns = pim.geometry.get("columns") or []
    pitch = pim.geometry.get("pitch") or pim.book_pitch
    image = pim.image(mask)
    if not columns or not pitch or image is None:
        return None
    column = max(columns, key=lambda c: c["x0"]) if edge == "head" else min(columns, key=lambda c: c["x0"])
    margin = COLUMN_MARGIN * (column["x1"] - column["x0"])
    x0, x1 = column["x0"] - margin, column["x1"] + margin
    if edge == "head":
        box = (column["x0"] - 2, column["top"] - 0.15 * pitch, column["x1"] + 2,
               column["top"] + (cells + 0.1) * pitch)
        piece = Piece([x0, box[1] - pitch, x1, box[3] + GLYPH_REACH * pitch])
    else:
        # A column's measured foot takes in the specks below its last glyph.
        box = (column["x0"] - 2, column["foot"] - (cells + 0.4) * pitch, column["x1"] + 2,
               column["foot"] + 0.15 * pitch)
        piece = Piece([x0, box[1] - GLYPH_REACH * pitch, x1, box[3] + pitch])
    return compose(image, [piece], [Mark(0, "box", box)], pim.paper)


def cell_crop(pim: PageImage, cell: Mapping[str, Any], mask: bool) -> bytes | None:
    """A glyph question's crop for one cell (a copied line's character): two
    cells either side along its line or column, the cell in a red box."""
    image = pim.image(mask)
    if image is None:
        return None
    pitch = cell["pitch"]
    if cell["across"]:
        piece = Piece([max(cell["left"], cell["x0"] - GLYPH_REACH * pitch) - 0.2 * pitch,
                       cell["y0"] - 0.3 * (cell["y1"] - cell["y0"]),
                       min(cell["right"], cell["x1"] + GLYPH_REACH * pitch) + 0.2 * pitch,
                       cell["y1"] + 0.3 * (cell["y1"] - cell["y0"])])
    else:
        margin = COLUMN_MARGIN * (cell["right"] - cell["left"])
        piece = Piece([cell["left"] - margin, max(cell["top"] - 0.5 * pitch, cell["y0"] - GLYPH_REACH * pitch),
                       cell["right"] + margin, min(cell["foot"] + 0.5 * pitch, cell["y1"] + GLYPH_REACH * pitch)])
    return compose(image, [piece], [Mark(0, "box", (cell["x0"], cell["y0"], cell["x1"], cell["y1"]))], pim.paper)


def region_crop(pim: PageImage, box: Sequence[float], mask: bool, pad: float = 0.02) -> bytes | None:
    """A region (page pixels) in a red box, with PAD of the page round it:
    a line's or a column's crop (Q-L)."""
    image = pim.image(mask)
    if image is None or not pim.size:
        return None
    width, height = pim.size
    x0, y0, x1, y1 = box
    piece = Piece([x0 - pad * width, y0 - pad * height, x1 + pad * width, y1 + pad * height])
    return compose(image, [piece], [Mark(0, "box", (x0, y0, x1, y1))], pim.paper)


def block_box(pim: PageImage, block: int) -> list[float] | None:
    if not pim.size or not (0 <= block < len(pim.blocks)):
        return None
    width, height = pim.size
    x, y, w, h = pim.blocks[block]["box"]
    return [x * width, y * height, (x + w) * width, (y + h) * height]


def site_cells(pim: PageImage, spot: Spot) -> list[dict[str, Any]]:
    """The cells of the site's characters engine A read."""
    out = []
    for k in spot.reading.chars_in(spot.start, spot.end):
        cell = pim.cell(spot.reading.a_index(k))
        if cell is not None:
            out.append(cell)
    return out


def frame_lines(pim: PageImage, piece: Piece, n: int, k: float | None) -> list[Mark]:
    """Blue lines across a piece at the frame's top and K cells below it."""
    x0, _, x1, _ = piece.box
    top = pim.frame_top((x0 + x1) / 2)
    pitch = pim.pitch()
    if top is None or not pitch:
        return []
    out = [Mark(n, "line", (x0, top, x1, top), BLUE)]
    if k:
        out.append(Mark(n, "line", (x0, top + k * pitch, x1, top + k * pitch), BLUE))
    return out


def full_column_piece(pim: PageImage, cell: Mapping[str, Any]) -> Piece:
    """A cell's column from above the frame's top to below its foot."""
    pitch = pim.pitch() or cell["pitch"]
    margin = COLUMN_MARGIN * (cell["right"] - cell["left"])
    top = pim.frame_top((cell["left"] + cell["right"]) / 2)
    foot = pim.geometry.get("frameFoot")
    top = min(cell["top"], top if top is not None else cell["top"]) - pitch
    foot = max(cell["foot"], foot if foot else cell["foot"]) + pitch
    return Piece([cell["left"] - margin, top, cell["right"] + margin, foot])


def heading_crop(pim: PageImage, spot: Spot, mask: bool) -> bytes | None:
    """Q-Y heading: the heading's column and the next, the frame's height,
    the heading's characters in a red box."""
    image = pim.image(mask)
    cells = site_cells(pim, spot)
    if image is None or not cells or cells[0]["across"]:
        return None
    first = cells[0]
    nxt = pim.cell(spot.ja())
    if nxt is None or column_key(nxt) == column_key(first):
        later = [pim.cell(j) for j in range((spot.ja() or 0), (spot.ja() or 0) + 60)]
        nxt = next((c for c in later if c is not None and column_key(c) != column_key(first)), None)
    a = full_column_piece(pim, first)
    pieces = [a]
    if nxt is not None and nxt["right"] <= first["left"] + 1:
        b = full_column_piece(pim, nxt)
        pieces = [Piece([b.box[0], min(a.box[1], b.box[1]), a.box[2], max(a.box[3], b.box[3])])]
    marks = []
    for column in {column_key(c) for c in cells}:
        inside = [c for c in cells if column_key(c) == column]
        marks.append(Mark(0, "box", (inside[0]["x0"] - 2, inside[0]["y0"] - 2, inside[-1]["x1"] + 2,
                                     inside[-1]["y1"] + 2)))
    return compose(image, pieces, marks, pim.paper)


def paragraph_crop(pim: PageImage, spot: Spot, k: float | None, mask: bool) -> tuple[bytes | None, bool]:
    """Q-Y paragraph: the columns of the characters either side of the
    place, the frame's height; red lines at the place, blue lines at the
    frame's top and K cells below it.  Its bytes and whether the blue lines
    are drawn."""
    image = pim.image(mask)
    cb, ca = pim.snap(pim.cell(spot.jb())), pim.snap(pim.cell(spot.ja()))
    if image is None or (cb is None and ca is None) or (cb or ca)["across"]:
        return None, False
    pieces: list[Piece] = []
    marks: list[Mark] = []
    keys: list[tuple[float, float]] = []
    for cell in (cb, ca):
        if cell is None or column_key(cell) in keys:
            continue
        keys.append(column_key(cell))
        pieces.append(full_column_piece(pim, cell))
    if cb is not None:
        marks.append(tick(pieces, keys.index(column_key(cb)), cb["y1"]))
    if ca is not None and (cb is None or column_key(ca) != column_key(cb)):
        marks.append(tick(pieces, keys.index(column_key(ca)), ca["y0"]))
    lines = []
    for n, piece in enumerate(pieces):
        lines += frame_lines(pim, piece, n, k)
    # The red marks over the blue: a flush column's top is the frame's.
    return compose(image, pieces, lines + marks, pim.paper), bool(lines)


# --- the questions -----------------------------------------------------------------

@dataclass
class Call:
    """One request: its role in the question (main, round2, check), its
    call kind, its prompts and crop, and the answer."""
    question: str
    role: str
    kind: str
    system: str
    user: str
    crop: bytes
    name: str
    raw: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    cached: bool = False
    seconds: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def hash(self) -> str:
        return call_hash(self.system, self.user, self.crop)

    def record(self) -> dict[str, Any]:
        return {"role": self.role, "kind": self.kind, "hash": self.hash, "crop": self.name,
                "cropSha256": pp.sha256_bytes(self.crop),
                "promptSha256": pp.sha256_bytes((self.system + "\0" + self.user).encode("utf-8")),
                "rawAnswer": self.raw, "cached": self.cached, "seconds": round(self.seconds, 2),
                "effort": self.metrics.get("effort"), "degraded": bool(self.metrics.get("degraded")),
                "finishReason": self.metrics.get("finish_reason"),
                "tokens": {"prompt": self.metrics.get("prompt_tokens", 0) or 0,
                           "completion": self.metrics.get("completion_tokens", 0) or 0}, **self.extra}


def call_hash(system: str, user: str, crop: bytes) -> str:
    return hashlib.sha256(system.encode("utf-8") + b"\0" + user.encode("utf-8") + b"\0" + crop).hexdigest()


@dataclass
class Job:
    """One question as it is asked: the question, its site, its calls and
    what came of it."""
    question: dict[str, Any]
    spot: Spot | None = None
    pim: PageImage | None = None
    calls: list[Call] = field(default_factory=list)
    edits: list[re_.Edit] = field(default_factory=list)
    doubts: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)
    status: str = "planned"
    guard: dict[str, Any] | None = None
    answer: Any = None
    label: dict[str, Any] | None = None
    pending: list[dict[str, Any]] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.question["id"]

    def main(self) -> Call | None:
        return next((c for c in self.calls if c.role == "main"), None)

    def refuse(self, guard: str, why: str, **fields: Any) -> None:
        self.status, self.guard = "refused", {"passed": False, "guard": guard, "why": why}
        self.edits = []
        self.doubts.append(("look-refused", f"{self.question.get('kind')} {self.id}: {guard} {why}",
                            {"guard": guard, **fields}))


def about_band(question: Mapping[str, Any]) -> bool:
    """Whether a question is about the running head's band (a furniture
    rule's): its crop keeps the band."""
    return str(question.get("rule") or "").startswith("F")


class Asker:
    """Asks calls with the Client, KEEPs each answer in answers.jsonl as it
    comes, and reuses an answer asked the same way (the cache).  LISTING
    (--no-model on a resumed run): the answers held are reused, nothing is
    asked, and every call no answer is held for is listed (`unasked`); the
    Client then only says how a call would be asked (its settings)."""

    def __init__(self, client: Any | None, output: Path, answers: Mapping[str, Mapping[str, Any]],
                 max_tokens: int, lanes: int, plan_only: bool = False, listing: bool = False):
        self.client = client
        self.output = output
        self.answers = dict(answers)
        self.max_tokens = max_tokens
        self.lanes = max(1, lanes)
        self.plan_only = plan_only
        self.listing = listing
        self.settings = {"model": getattr(client, "model", None), "effort": getattr(client, "effort", None),
                         "maxTokens": max_tokens, "temperature": getattr(client, "temperature", None)}
        self.lock = threading.Lock()
        self.calls: list[dict[str, Any]] = []
        self.asked = 0
        self.reused = 0
        self.crops: set[str] = set()
        # LISTING: each call no answer is held for, by its question and role
        # (a follow-up is offered again while its job waits; two questions
        # asked alike are two calls, as a run that asks makes them).
        self.unasked: dict[tuple[str, str], dict[str, Any]] = {}

    def save_crop(self, call: Call) -> None:
        path = self.output / call.name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file() or path.read_bytes() != call.crop:
            tmp = path.with_name(f".{path.name}.tmp")
            tmp.write_bytes(call.crop)
            tmp.replace(path)
        self.crops.add(call.name)

    def run(self, calls: Sequence[Call]) -> None:
        todo = []
        for call in calls:
            self.save_crop(call)
            kept = self.answers.get(call.hash)
            if kept is not None and kept.get("settings") == self.settings and kept.get("rawAnswer") is not None:
                call.raw = kept["rawAnswer"]
                call.metrics = dict(kept.get("metrics") or {})
                call.cached = True
                self.reused += 1
            else:
                todo.append(call)
        if self.listing:
            for call in todo:
                self.unasked.setdefault((call.question, call.role), {"question": call.question, "role": call.role,
                                                                     "kind": call.kind})
            return
        if self.plan_only or not todo or self.client is None:
            return
        ledger: list[dict[str, Any]] = []
        token = pp._CALL_LEDGER.set(ledger)
        pool = cf.ThreadPoolExecutor(max_workers=self.lanes)
        try:
            pp.in_context(pool, self.ask, todo)
        except BaseException as error:
            # A failed call lets the calls on the wire finish and keep their
            # answers.  A stop (KeyboardInterrupt, or a caller's own
            # BaseException for SIGTERM) does not wait for the model to
            # answer them: they are asked again on --resume.
            pool.shutdown(wait=isinstance(error, Exception), cancel_futures=True)
            raise
        else:
            pool.shutdown(wait=True)
        finally:
            pp._CALL_LEDGER.reset(token)
            self.calls.extend(ledger)

    def ask(self, call: Call) -> None:
        started = time.monotonic()
        text, metrics = self.client.ask_answering(call.system, call.user, call.crop, self.max_tokens,
                                                  kind=call.kind)
        call.raw = text or ""
        call.metrics = dict(metrics or {})
        call.seconds = time.monotonic() - started
        record = {"hash": call.hash, "kind": call.kind, "question": call.question, "role": call.role,
                  "rawAnswer": call.raw, "metrics": call.metrics, "settings": self.settings,
                  "answeredAt": pp.utc_now()}
        line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        with self.lock:
            with open(self.output / ANSWERS_NAME, "a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
            self.answers[call.hash] = record
            self.asked += 1


def load_answers(output: Path) -> dict[str, dict[str, Any]]:
    """The answers an earlier run in OUTPUT kept (answers.jsonl, and the
    calls of its questions.json), by call hash."""
    out: dict[str, dict[str, Any]] = {}
    try:
        records = json.loads((output / "questions.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        records = []
    for record in records if isinstance(records, list) else []:
        for call in (record.get("calls") or []) if isinstance(record, dict) else []:
            if isinstance(call, dict) and call.get("hash") and call.get("rawAnswer") is not None \
                    and call.get("settings"):
                out[call["hash"]] = {"rawAnswer": call["rawAnswer"], "metrics": call.get("metrics") or {},
                                     "settings": call["settings"]}
    try:
        lines = (output / ANSWERS_NAME).read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue   # a line cut off when a run stopped
        if isinstance(record, dict) and record.get("hash") and record.get("rawAnswer") is not None:
            out[record["hash"]] = record
    return out


@dataclass
class Env:
    """What the questions read and change: the book, its model, the ledger,
    the page readings, the rules' facts, the asker, and the boundaries the
    joins stage labelled (a Q-B answer settles one)."""
    book: Any
    model: Mapping[str, Any]
    ledger: re_.Ledger
    readings: rs.Readings
    facts: rr.BookFacts
    asker: Asker
    order: Sequence[int]
    boundaries: dict[int, str] | None = None
    evidence: dict[str, Any] | None = None

    def reading(self, page: int) -> rs.PageReading:
        return self.readings.get(page, self.ledger.texts[page])


# --- building the calls ----------------------------------------------------------------

def crop_name(job: Job, role: str) -> str:
    return f"{CROPS}/{job.id}-{role}.png"


def new_call(job: Job, role: str, system: str, user: str, crop: bytes, **extra: Any) -> Call:
    kind = CALL_KIND[extra.pop("as_kind", job.question["kind"])]
    return Call(job.id, role, kind, system, user, crop, crop_name(job, role), extra=extra)


def glyph_cells(spot: Spot) -> str:
    n = max(1, len(spot.gap_chars()), len(pp.CJK(spot.a_read or "")))
    return "一個字位" if n == 1 else f"{n}個字位"


def build(job: Job, env: Env) -> str | None:
    """The job's main call; why not, when it cannot be asked."""
    q = job.question
    kind, spot, pim = q["kind"], job.spot, job.pim
    mask = not about_band(q)
    if kind == "Q-G":
        if q.get("rule") == "F8":
            crop = edge_crop(pim, str(q.get("edge")), max(1, len(pp.CJK(spot.a_read or ""))), mask)
        else:
            crop = glyph_crop(pim, spot, mask)
        if crop is None:
            return "no crop: the place is not on engine A's cells"
        user = glyph_user(glyph_cells(spot), spot.before(), spot.after())
        job.calls.append(new_call(job, "main", pp.ADJUDICATE_SYSTEM, user, crop))
        return None
    if kind == "Q-P":
        crop, pieces = print_crop(pim, spot, mask, number=isinstance(q.get("contentsNumber"), int))
        if crop is None:
            return "no crop: the anchors are not on engine A's cells"
        job.calls.append(new_call(job, "main", REPAIR_SYSTEM, print_user(spot.before(), spot.after(), pieces), crop))
        return None
    if kind == "Q-L":
        return build_line(job, env, mask)
    if kind == "Q-Y":
        k = rj.Measure.of(env.model).k
        if q.get("rule") in ("S5", "S9"):
            crop = heading_crop(pim, spot, mask)
            if crop is None:
                return "no crop: the heading is not on engine A's cells"
            text = spot.text[spot.start:spot.end].strip().lstrip("#").strip()
            job.calls.append(new_call(job, "main", REPAIR_SYSTEM, heading_user(text), crop, template="heading"))
            return None
        if q.get("rule") in ("P1", "P7"):
            # The answer breaks the paragraph at the site's start (a line
            # break for P1, the run engine A's block opens for P7): the
            # question names and marks that place, not the characters
            # beyond the site (a P7 site runs on eight characters into the
            # block).
            junction = make_spot(spot.reading, spot.page, spot.start, spot.start)
            crop, lines = paragraph_crop(pim, junction, k, mask)
            if crop is None:
                return "no crop: the place is not on engine A's cells"
            user = paragraph_user(junction.before(6), junction.after(6), k, lines)
            job.calls.append(new_call(job, "main", REPAIR_SYSTEM, user, crop, template="paragraph"))
            return None
        return f"no layout question for rule {q.get('rule')}"
    if kind == "Q-B":
        return build_boundary(job, env)
    return f"unknown kind {kind}"


def build_line(job: Job, env: Env, mask: bool) -> str | None:
    q, spot, pim = job.question, job.spot, job.pim
    if q.get("rule") == "S9":
        cells = site_cells(pim, spot)
        if not cells or cells[0]["across"]:
            return "no crop: the title is not on engine A's cells"
        first = cells[0]
        piece = full_column_piece(pim, first)
        box = [first["left"] - 2, piece.box[1] + (pim.pitch() or first["pitch"]) * 0.5, first["right"] + 2,
               piece.box[3] - (pim.pitch() or first["pitch"]) * 0.5]
        crop = region_crop(pim, box, mask, pad=0.01)
        if crop is None:
            return "no crop"
        job.calls.append(new_call(job, "main", REPAIR_SYSTEM, title_end_user(str(q.get("entry") or "")), crop,
                                  template="title-end"))
        return None
    across, box, lines = line_region(job, env)
    if box is None:
        return "no crop: the line is not on engine A's blocks"
    crop = region_crop(pim, box, mask)
    if crop is None:
        return "no crop"
    job.calls.append(new_call(job, "main", REPAIR_SYSTEM, line_user(lines, across), crop, template="line"))
    return None


def s13_block(job: Job) -> tuple[int, int] | None:
    """The engine A block and the offset of its CJK characters where the
    rebuilt line (S13) was read backwards."""
    raw = job.question.get("aLine")
    if not raw:
        return None
    chars = pp.CJK(raw)
    for b, block in enumerate(job.pim.blocks):
        block_chars = pp.CJK(block["text"])
        at = block_chars.find(chars)
        if chars and at >= 0:
            return b, at
    return None


def line_band(pim: PageImage, block: int, raw: str) -> list[float] | None:
    """The region of the line RAW of engine A's horizontal BLOCK: its box
    cut to that line's row of ink, when the block's rows of ink are as many
    as its lines of text; else to its share of the box's height."""
    box = block_box(pim, block)
    if box is None:
        return None
    lines = [line for line in pim.blocks[block]["text"].split("\n") if pp.CJK(line)]
    index = next((i for i, line in enumerate(lines) if pp.CJK(raw) and pp.CJK(raw) in pp.CJK(line)), None)
    if index is None or len(lines) < 2:
        return box
    x0, y0, x1, y1 = box
    share = (y1 - y0) / len(lines)
    image = pim.image(True)
    if image is not None:
        import numpy as np
        gray = np.asarray(image.convert("L").crop((int(x0), int(y0), int(math.ceil(x1)), int(math.ceil(y1)))))
        rows = (gray < pim.paper - 60).sum(axis=1) > max(2, 0.002 * gray.shape[1])
        runs: list[list[int]] = []
        for y, inked in enumerate(rows):
            if not inked:
                continue
            if runs and y - runs[-1][1] <= 0.3 * share:
                runs[-1][1] = y + 1
            else:
                runs.append([y, y + 1])
        runs = [r for r in runs if r[1] - r[0] >= 0.2 * share]
        if len(runs) == len(lines):
            top, foot = runs[index]
            return [x0, y0 + top, x1, y0 + foot]
    return [x0, y0 + index * share, x1, y0 + (index + 1) * share]


def line_cells(pim: PageImage, block: int, raw: str) -> list[dict[str, Any]] | None:
    """The cells of the line RAW of engine A's horizontal BLOCK, left to
    right as engine A reads it: the line's own row (line_band), each
    character a stretch of the row's ink.  The row's glyphs are its runs of
    inked columns (inked by a twentieth of the row: a rule or a dotted line
    under the line is not; a gap under a fifth of the row joins the strokes
    of one glyph, 月's two sides) at least GLYPH_WIDTH of the row tall wide
    (a speck is not); where there are as many as the line has characters,
    or more and a run of that many is evenly spaced (a mark or a stamp
    beside the line), those are the cells; else the glyphs' width is split
    evenly.  block_cells spreads a block's characters over its whole box
    in one row: on a real title page, a block of two lines put a character
    of the second line's in the first line's row, and one of the first
    line's a cell off (a glyph question asked on the wrong character)."""
    n = len(pp.CJK(raw))
    band = line_band(pim, block, raw)
    image = pim.image(True)
    if not n or band is None or image is None:
        return None
    import numpy as np
    x0, y0, x1, y1 = band
    gray = np.asarray(image.convert("L").crop((int(x0), int(y0), int(math.ceil(x1)), int(math.ceil(y1)))))
    height = max(1, gray.shape[0])
    inked = (gray < pim.paper - 60).sum(axis=0) >= max(2.0, 0.05 * height)
    runs: list[list[int]] = []
    for x, on in enumerate(inked):
        if not on:
            continue
        if runs and x - runs[-1][1] <= 0.2 * height:
            runs[-1][1] = x + 1
        else:
            runs.append([x, x + 1])
    glyphs = [r for r in runs if r[1] - r[0] >= GLYPH_WIDTH * height] or runs
    if not glyphs:
        return None
    chosen = glyphs if len(glyphs) == n else None
    if chosen is None and len(glyphs) > n >= 3:
        # The evenly spaced run of N glyphs: the one whose spacing strays
        # least from its own median, within a quarter of it.
        best = None
        for k in range(len(glyphs) - n + 1):
            window = glyphs[k:k + n]
            centres = [(a + b) / 2 for a, b in window]
            gaps = sorted(y - x for x, y in zip(centres, centres[1:]))
            middle = gaps[len(gaps) // 2]
            stray = max(abs(g - middle) for g in gaps) / middle if middle > 0 else math.inf
            if stray <= 0.25 and (best is None or stray < best[0]):
                best = (stray, window)
        chosen = best[1] if best else None
    if chosen is not None:
        # A glyph's run leaves out the thin ends of its strokes: a little of
        # the row either side.
        pad = 0.08 * height
        spans = [(x0 + a - pad, x0 + b + pad) for a, b in chosen]
        left, right = spans[0][0], spans[-1][1]
        step = (right - left) / n
    else:
        left, right = x0 + glyphs[0][0], x0 + glyphs[-1][1]
        step = (right - left) / n
        spans = [(left + i * step, left + (i + 1) * step) for i in range(n)]
    return [{"x0": a, "x1": b, "y0": y0, "y1": y1, "column": 0, "top": y0, "foot": y1, "left": left,
             "right": right, "pitch": step, "across": True} for a, b in spans]


def line_region(job: Job, env: Env) -> tuple[bool, list[float] | None, int]:
    """The region a copied line or column stands in: engine A's blocks that
    hold the site's characters (its line's block for a page printed right
    to left, S13), whether it is printed across, and how many lines."""
    spot, pim = job.spot, job.pim
    site = spot.text[spot.start:spot.end]
    lines = max(1, len([line for line in site.split("\n") if pp.CJK(line)]))
    found = s13_block(job)
    if found is not None:
        return True, line_band(pim, found[0], job.question["aLine"]), lines
    blocks = sorted({spot.reading.block(k) for k in spot.reading.chars_in(spot.start, spot.end)} - {None})
    if not blocks:
        return False, None, lines
    boxes = [block_box(pim, b) for b in blocks]
    boxes = [b for b in boxes if b]
    if not boxes:
        return False, None, lines
    across = str(job.question.get("rule")) == "S13" or any(
        (pim.cells(b) or [{"across": False}])[0]["across"] for b in blocks)
    return across, [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes),
                    max(b[3] for b in boxes)], lines


def build_boundary(job: Job, env: Env) -> str | None:
    """Q-B: the previous page's last body column's foot and the next page's
    first column's head, band masked, side by side; the frame's foot on the
    first and its top on the second in blue, K cells below the top in
    red."""
    q = job.question
    scan = q["page"]
    prev = q.get("previousPage")
    if prev not in env.ledger.texts:
        return "the previous page is not under repair"
    k = rj.Measure.of(env.model).k
    parts = []
    lines = True
    for page, end in ((prev, True), (scan, False)):
        pim = PageImage(env.book, env.model, page, env.reading(page))
        image = pim.image(True)
        if image is None:
            return "no crop: a render cannot be read"
        columns = pim.geometry.get("columns") or []
        pitch = pim.pitch()
        if columns and pitch and pim.framed():
            c = columns[-1] if end else columns[0]
            margin = COLUMN_MARGIN * (c["x1"] - c["x0"])
            if end:
                foot = max(c["foot"], pim.geometry.get("frameFoot") or c["foot"])
                box = [c["x0"] - margin, c["foot"] - BOUNDARY_CELLS * pitch, c["x1"] + margin, foot + pitch]
            else:
                top = pim.frame_top((c["x0"] + c["x1"]) / 2)
                top = min(c["top"], top if top is not None else c["top"])
                box = [c["x0"] - margin, top - pitch, c["x1"] + margin, c["top"] + BOUNDARY_CELLS * pitch]
        else:
            lines = False
            blocks = [b for b in pim.blocks if pp.CJK(b["text"])]
            if not blocks or not pim.size:
                return "no crop: the page's columns are not measured and engine A read no block"
            block = dict(blocks[-1] if end else blocks[0])
            box = list(pp.edge_region(pim.render, block, end, BOUNDARY_CELLS, pim.size))
        parts.append((pim, image, Piece(box)))
    marks: list[Mark] = []
    head_pim, _, head_piece = parts[1]
    foot_pim, _, foot_piece = parts[0]
    if lines:
        marks = [Mark(1, m.shape, m.at, BLUE if n == 0 else RED)
                 for n, m in enumerate(frame_lines(head_pim, head_piece, 0, k))]
        foot = foot_pim.geometry.get("frameFoot")
        lines = len(marks) == 2 and bool(foot)
        if lines:
            x0, _, x1, _ = foot_piece.box
            marks.append(Mark(0, "line", (x0, foot, x1, foot), BLUE))
        else:
            # The question names the lines only when all three are drawn.
            marks = []
    crop = compose_pages(parts, marks)
    if crop is None:
        return "no crop"
    job.calls.append(new_call(job, "main", REPAIR_SYSTEM, boundary_user(k, lines), crop))
    return None


def compose_pages(parts: Sequence[tuple[PageImage, Any, Piece]], marks: Sequence[Mark]) -> bytes | None:
    """Pieces of two pages side by side, the first on the right, with the
    first page's paper between; MARKS by the piece's place in PARTS."""
    from PIL import Image
    images = []
    for pim, image, piece in parts:
        width, height = image.size
        x0, y0, x1, y1 = piece.box
        box = (max(0, int(x0)), max(0, int(y0)), min(width, int(math.ceil(x1))), min(height, int(math.ceil(y1))))
        if box[2] - box[0] < 2 or box[3] - box[1] < 2:
            return None
        images.append((box, image.crop(box)))
    paper = parts[0][0].paper
    gap = max(8, min(c.width for _, c in images) // 2)
    total = sum(c.width for _, c in images) + gap * (len(images) - 1)
    canvas = Image.new("RGB", (total, max(c.height for _, c in images)), (paper,) * 3)
    at = total
    shifted: list[Mark] = []
    places = []
    for (box, c) in images:
        at -= c.width
        canvas.paste(c, (at, 0))
        places.append((at, box))
        at -= gap
    for mark in marks:
        left, box = places[mark.piece]
        x0, y0, x1, y1 = mark.at
        shifted.append(Mark(0, mark.shape, (x0 - box[0] + left, y0 - box[1], x1 - box[0] + left, y1 - box[1]),
                            mark.colour))
    return compose(canvas, [Piece([0, 0, canvas.width, canvas.height])], shifted, paper)


def round_two(job: Job, env: Env, blind: str) -> None:
    """The second glyph question, with the engines' readings as
    candidates, on the same crop."""
    spot = job.spot
    main = job.main()
    seg = {"before": spot.before(8), "after": spot.after(8), "a": pp.CJK(spot.a_read or ""),
           "b": pp.CJK(spot.b_read or "")}
    user = pp.adjudicate_prompt(seg, note=GLYPH_ROUND_TWO_NOTE)
    job.calls.append(Call(job.id, "round2", main.kind, pp.ADJUDICATE_SYSTEM, user, main.crop, main.name,
                          extra={"blind": blind}))


# --- guards ------------------------------------------------------------------------------

def band_chars(model: Mapping[str, Any], page: int) -> set[str]:
    """The running head's characters on PAGE: its band blocks, the stems,
    its run's suffix and its folio's numerals."""
    entry = rm.page_entry(model, page)
    chars = set(pp.CJK("".join(str(b.get("text") or "") for b in entry.get("band") or [])))
    for stem in model.get("stems") or []:
        chars |= set(stem)
    if entry.get("suffix"):
        chars |= set(entry["suffix"])
    if entry.get("folio"):
        for form in lint.folio_forms(entry["folio"]):
            chars |= set(pp.CJK(form))
    return chars


def near_band(env: Env, spot: Spot, pim: PageImage | None) -> bool:
    """Whether the place is next to the band: within BAND_NEAR characters
    of the page body's first or last, or its cells within BAND_NEAR pitches
    of a band block."""
    s = spot.s
    before = bisect.bisect_left(s.offsets, spot.gap_start)
    after = len(s.chars) - bisect.bisect_left(s.offsets, spot.gap_end)
    if before <= BAND_NEAR or after <= BAND_NEAR:
        return True
    if pim is None or not pim.band or not pim.size:
        return False
    width, height = pim.size
    cells = [c for c in (pim.cell(spot.jb()), pim.cell(spot.ja())) if c]
    for cell in cells:
        reach = BAND_NEAR * cell["pitch"]
        for x, y, w, h in pim.band:
            bx0, by0, bx1, by1 = x * width, y * height, (x + w) * width, (y + h) * height
            if cell["x0"] - reach <= bx1 and bx0 <= cell["x1"] + reach and \
                    cell["y0"] - reach <= by1 and by0 <= cell["y1"] + reach:
                return True
    return False


def prose(answer: str, spot: Spot) -> str | None:
    """A question's own word in ANSWER that the engines and the page do not
    hold there (G2)."""
    held = (spot.a_wide or "") + (spot.b_wide or "") + spot.text[max(0, spot.gap_start - 20):spot.gap_end + 20]
    return next((w for w in PROMPT_WORDS if w in answer and w not in held), None)


def g4_band(env: Env, job: Job, answer: str) -> bool:
    chars = pp.CJK(answer)
    if not chars:
        return False
    spot = job.spot
    read = set(pp.CJK(spot.a_read or "")) | set(pp.CJK(spot.b_read or ""))
    band = band_chars(env.model, spot.page)
    return all(c in band for c in chars) and not all(c in read for c in chars) and near_band(env, spot, job.pim)


FIGURE_BRACKET = re.compile(r"（\s*([0-9]{1,3})\s*）")
FIGURE_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+([0-9]{1,3})(?=[.．、,，\s]|[^\x00-\x7f])", re.M)
FIGURE_LINE = re.compile(r"^(?:[ \t]*[-*+][ \t]+)?[ \t]*([0-9]{1,3})(?=[.．、,，\s]|[^\x00-\x7f])", re.M)
FIGURES = {"bracket": FIGURE_BRACKET, "heading": FIGURE_HEADING, "line": FIGURE_LINE}


def written_figures(texts: Sequence[str], style: str) -> list[int]:
    return [int(m.group(1)) for text in texts for m in FIGURES[style].finditer(text)]


def g6_figures(env: Env, job: Job, new_gap: str) -> str | None:
    """G6 on a figure the answer writes: K-seq's test against the figures of
    its kind the pages hold before and after it (bracketed, or opening a
    line), and the contents' number for a unit heading.  None when nothing
    contradicts it."""
    spot = job.spot
    q = job.question
    bracketed = FIGURE_BRACKET.search(new_gap)
    # The new gap's last line: the line the figure opens, when it opens one.
    cut = new_gap.rfind("\n")
    line_start = spot.gap_start + cut + 1 if cut >= 0 else spot.text.rfind("\n", 0, spot.gap_start) + 1
    head = (new_gap[cut + 1:] if cut >= 0 else spot.text[line_start:spot.gap_start] + new_gap)
    # With the page's character after the gap: a figure the answer writes
    # just before the anchor is followed by the title or text it opens, and
    # the figure patterns look for what follows it.
    head += spot.text[spot.gap_end:spot.gap_end + 1]
    style = "bracket"
    opening = None
    if not bracketed:
        for style in ("heading", "line"):
            opening = FIGURES[style].match(head)
            if opening:
                break
    if not (bracketed or opening):
        return None
    value = int((bracketed or opening).group(1))
    number = q.get("contentsNumber")
    if isinstance(number, int) and opening and value != number:
        return f"figure {value} is not the contents' number {number} of this unit"
    if isinstance(number, int) and opening:
        # The contents give the figure its place in the sequence; the
        # figures beside it may be questions of the same round, not yet
        # written.
        return None
    order = list(env.order)
    at = order.index(spot.page) if spot.page in order else -1
    before_pages = [env.ledger.texts[p] for p in order[:at]] + [spot.text[:spot.gap_start if bracketed
                                                                          else min(line_start, spot.gap_start)]]
    after_pages = [spot.text[spot.gap_end:]] + [env.ledger.texts[p] for p in order[at + 1:]]
    earlier = written_figures(before_pages, style)
    later = written_figures(after_pages, style)
    prev = earlier[-1] if earlier else None
    nxt = later[0] if later else None
    if value == 1 or prev == value - 1 or (nxt == value + 1 and (prev is None or prev < value)):
        return None
    if prev is None and nxt is None:
        return None
    return (f"figure {value} does not go on from the figure of its kind before it ({prev}) or lead to the one "
            f"after it ({nxt})")


def g6_one(spot: Spot, answer: str, question: Mapping[str, Any]) -> bool:
    """一 as a numeral where neither engine read 一."""
    if "一" not in answer:
        return False
    numeral = bool(re.search(r"[0-9０-９]", (spot.a_read or "") + (spot.b_read or ""))) or \
        str(question.get("rule")) in ("K1", "K2", "K-seq", "S4", "S11")
    return numeral and "一" not in (spot.a_wide or "") + (spot.b_wide or "")


def g5_new(spot: Spot, answer: str, question: Mapping[str, Any]) -> str | None:
    """A CJK character of ANSWER that no engine read between the anchors or
    at them, and the page does not hold there; or a character both engines
    read there that ANSWER leaves out."""
    allowed = set(pp.variant_fold("".join(spot.engine_chars()))) | set(pp.variant_fold(spot.gap_chars()))
    if not question.get("lostCharacter"):
        new = [c for c in pp.CJK(answer) if pp.variant_fold(c) not in allowed]
        if new:
            return f"{''.join(new)!r} is read by neither engine here"
    held = Counter(pp.variant_fold(spot.gap_chars())) & spot.both_read()
    left = held - Counter(pp.variant_fold(pp.CJK(answer)))
    if left:
        return f"{''.join(left.elements())!r}, read by both engines here, is left out"
    seen = spot.seen()
    if len(pp.CJK(answer)) < seen:
        return (f"the answer holds {len(pp.CJK(answer))} character(s) where the page and both engines each hold "
                f"{seen} (whatever glyph each read)")
    return None


def agreed_marks(spot: Spot, answer: str) -> str:
    """The marks the page holds between the anchors where engine A read
    them there too, that ANSWER leaves out: the page and engine A agree on
    them (a unit number's question reaches back to the full stop ending the
    paragraph before it; a question about the marks a deletion left takes
    in the full stop before them)."""
    def marks(text: str) -> Counter:
        return Counter(c for c in text if not pp.CJK(c) and not c.isalnum())
    agreed = marks(content_of(spot.gap())) & marks(normal_print(spot.a_read or ""))
    return "".join((agreed - marks(answer)).elements())


def standin_units(spot: Spot, standins: set[str]) -> int:
    """How many printed units an answer to K14 holds at least: one for each
    stand-in glyph the page holds between the anchors (the mark or the
    character it stands for), and one for each mark the page and engine A
    both hold there.  Engine A read no character at the stand-in, so the
    cell of the character beside it can stand on the ink of a mark engine A
    did not read (a quote set close to its character): the crop then shows
    that mark outside the red lines, and an answer of what is between them
    would delete the stand-in - the mark with it."""
    def marks(text: str) -> Counter:
        return Counter(c for c in text if not pp.CJK(c) and not c.isalnum())
    held = content_of(spot.gap())
    shared = marks(held) & marks(normal_print(spot.a_read or ""))
    return sum(1 for c in held if c in standins) + sum(shared.values())


def degraded(call: Call) -> bool:
    return bool(call.metrics.get("degraded")) or call.metrics.get("finish_reason") == "length"


def g1(job: Job, call: Call, parsed: Parsed) -> bool:
    """G1: no answer line, or a reply cut off after the ladder.  True when
    refused (the job says so)."""
    if degraded(call):
        job.refuse("G1", "the reply was cut off at the token budget on every effort", role=call.role)
        return True
    if parsed.value is None:
        job.refuse("G1", f"the reply has no `{LABEL[job.question['kind']]}：` answer line", role=call.role)
        return True
    if parsed.unsure:
        job.status, job.guard = "unsure", {"passed": False, "guard": "unsure", "why": "the model cannot tell"}
        job.doubts.append(("look-refused", f"{job.question['kind']} {job.id}: the model cannot tell ({parsed.value})",
                           {"guard": "unsure"}))
        return True
    return False


# --- deciding and applying ---------------------------------------------------------------

def question_edit(job: Job, start: int, end: int, after: str, answer: str, **evidence: Any) -> re_.Edit:
    main = job.main()
    return re_.Edit(job.spot.page, start, end, after, question=job.id, answer=answer, crop=main.name,
                    crop_sha256=pp.sha256_bytes(main.crop),
                    evidence={"kind": job.question["kind"], "rule": job.question.get("rule"), **evidence})


def trimmed(job: Job, start: int, old: str, new: str, answer: str, **evidence: Any) -> list[re_.Edit]:
    """One edit that writes NEW over OLD at START, their common start and
    end left alone; none when they are the same."""
    if old == new:
        return []
    p = 0
    while p < min(len(old), len(new)) and old[p] == new[p]:
        p += 1
    s = 0
    while s < min(len(old), len(new)) - p and old[len(old) - 1 - s] == new[len(new) - 1 - s]:
        s += 1
    return [question_edit(job, start + p, start + len(old) - s, new[p:len(new) - s], answer, **evidence)]


def matches_reading(answer: str, spot: Spot) -> bool:
    """Whether a glyph answer is an engine's reading there, or an
    acceptable variant of one."""
    folded = pp.variant_fold(answer)
    return any(folded == pp.variant_fold(pp.CJK(r)) for r in spot.readings())


def decide_glyph(job: Job, env: Env) -> None:
    spot = job.spot
    readings = spot.readings()
    main = job.main()
    parsed = parse("Q-G", main.raw, readings)
    job.answer = parsed.text
    if g1(job, main, parsed):
        return
    second = next((c for c in job.calls if c.role == "round2"), None)
    if second is None:
        if not guard_glyph(job, env, parsed.text):
            return
        if parsed.empty or not parsed.text:
            if any(not pp.CJK(r) for r in readings) or not readings:
                write_glyph(job, "", parsed.value)
                return
        elif matches_reading(parsed.text, spot):
            write_glyph(job, parsed.text, parsed.value)
            return
        # A blind answer that matches no engine: the second round.
        round_two(job, env, parsed.text)
        job.status = "asking"
        return
    two = parse("Q-G", second.raw, readings)
    if g1(job, second, two):
        return
    job.answer = two.text
    if not guard_glyph(job, env, two.text):
        return
    candidates = {pp.variant_fold(pp.CJK(r)) for r in readings}
    names = (two.empty and "" in candidates) or (not two.empty and pp.variant_fold(two.text) in candidates)
    if names or (two.damaged and two.text):
        write_glyph(job, two.text, two.value, round=2, damaged=bool(two.damaged))
        return
    job.refuse("round-2", "the answer with candidates names neither engine's reading and does not say the print "
               "is damaged", blind=parsed.text, answer=two.text)


def guard_glyph(job: Job, env: Env, answer: str) -> bool:
    spot = job.spot
    limit = max(1, len(spot.gap_chars()), len(pp.CJK(spot.a_read or "")), len(pp.CJK(spot.b_read or "")))
    if len(answer) > limit:
        job.refuse("G2", f"{answer!r} is longer than the {limit} character(s) asked about")
        return False
    word = prose(answer, spot)
    if word:
        job.refuse("G2", f"the answer holds the question's word {word!r}")
        return False
    read = set(pp.CJK(spot.a_read or "")) | set(pp.CJK(spot.b_read or ""))
    near: set[str] = set()
    if spot.kb is not None:
        near |= set(spot.s.chars[max(0, spot.kb - 1):spot.kb + 1])
    if spot.ka is not None:
        near |= set(spot.s.chars[spot.ka:spot.ka + 2])
    chars = pp.CJK(answer)
    if chars and all(c in near and c not in read for c in chars):
        job.refuse("G3", f"{answer!r} is a character beside the place that neither engine read there")
        return False
    if g4_band(env, job, answer):
        job.refuse("G4", f"{answer!r} is the running head's, at a place next to the band")
        return False
    if g6_one(spot, answer, job.question):
        job.refuse("G6", "一 as a numeral where neither engine read 一")
        return False
    return True


def write_glyph(job: Job, answer: str, raw: str | None, **evidence: Any) -> None:
    """A glyph answer over the characters between the anchors (from the
    first to the last), or where the site is when there are none."""
    spot = job.spot
    gap = spot.gap()
    at = [i for i, c in enumerate(gap) if pp.CJK(c)]
    if at:
        start, end = spot.gap_start + at[0], spot.gap_start + at[-1] + 1
        inner = spot.text[start:end]
        if any(not pp.CJK(c) for c in inner):
            job.refuse("apply", "marks stand between the characters asked about; a glyph answer cannot say "
                       "where they go")
            return
    else:
        start = end = min(max(spot.start, spot.gap_start), spot.gap_end)
    left = Counter(pp.variant_fold(spot.gap_chars())) & spot.both_read()
    lost = left - Counter(pp.variant_fold(answer))
    if lost:
        job.refuse("G5", f"{''.join(lost.elements())!r}, read by both engines here, would be deleted")
        return
    if len(pp.CJK(answer)) < spot.seen():
        job.refuse("G5", f"{answer!r} holds fewer characters than the page and both engines each hold here "
                   f"({spot.seen()})")
        return
    old = spot.text[start:end]
    job.status = "answered"
    job.guard = {"passed": True}
    if pp.variant_fold(old) == pp.variant_fold(answer):
        return
    job.edits = trimmed(job, start, old, answer, raw or answer, **evidence)


def split_lead(answer: str) -> tuple[str, str]:
    """An answer's leading run of closing marks (they stay before a line
    break), and the rest."""
    k = 0
    while k < len(answer) and answer[k] in CLOSING:
        k += 1
    return answer[:k], answer[k:]


def print_gap(gap: str, answer: str) -> str:
    """The gap between the anchors with ANSWER as its print, its line
    breaks and heading or list markers kept, the white space at its ends
    kept (a marker's own space is the marker's: the gap before a heading's
    first character ends with it).  Where the page holds print before its
    line breaks only, the answer stands there - unless the gap ends with a
    heading or list marker and the answer, past its closing marks, starts
    with a figure: the figure opens that heading or item (a unit's number
    after the full stop ending the paragraph before it).  Else the
    answer's closing marks go before the first break and the rest after the
    last marker (K2's with_structure)."""
    tokens = rr.split_structure(gap)
    lo, hi = 0, len(tokens)
    while lo < hi and tokens[lo][0] == "c" and tokens[lo][1] in " \t":
        lo += 1
    while hi > lo and tokens[hi - 1][0] == "c" and tokens[hi - 1][1] in " \t":
        hi -= 1
    head = "".join(t for _, t in tokens[:lo])
    tail = "".join(t for _, t in tokens[hi:])
    tokens = tokens[lo:hi]
    if not any(kind == "s" for kind, _ in tokens):
        return head + answer + tail
    first = next(i for i, (kind, _) in enumerate(tokens) if kind == "s")
    ahead = any(kind == "c" and not t.isspace() for kind, t in tokens[:first])
    behind = any(kind == "c" and not t.isspace() for kind, t in tokens[first:])
    lead, rest = split_lead(answer)
    opens = tokens[-1][0] == "s" and bool(MARKER_END.search(tokens[-1][1])) and rest[:1].isdigit()
    if ahead and not behind and not opens:
        new = answer + "".join(t for kind, t in tokens if kind == "s")
    elif behind and not ahead:
        new = rr.with_structure(tokens, "", answer)
    else:
        new = rr.with_structure(tokens, lead, rest)
    return head + new + tail


# A structure run that ends with a heading or list marker (its text follows).
MARKER_END = re.compile(r"[#*+-][ \t]*$")


def content_of(gap: str) -> str:
    """The print in a gap: its characters but white space and Markdown
    structure."""
    return normal_print("".join(t for kind, t in rr.split_structure(gap) if kind == "c"))


# A number's figure, and a colon-like mark after it, ending an answer.
COLON_AFTER_FIGURE = re.compile(r"(?<![0-9])([0-9]{1,3})[：:︰]$")
# The rules whose numbers are written `N[mark] title`, a space after the
# number (S4 a unit heading's, S11 a contents entry's).
SPACED_NUMBERS = ("S4", "S11")


def styled(question: Mapping[str, Any], answer: str) -> tuple[str, dict[str, Any]]:
    """ANSWER with a colon-like mark after its closing figure read as the
    mark the question's list numbers its entries with (numberStyle: the
    contents' group, or the figures beside it on a contents page, all carry
    it, and none a colon): a full stop with a speck of ink above it reads
    as a colon.  Where the list carries no one mark, the answer stands as
    read.  Also the evidence to log."""
    style = question.get("numberStyle")
    match = COLON_AFTER_FIGURE.search(answer)
    if not style or not match:
        return answer, {}
    return answer[:match.end(1)] + style, {"numberStyle": style, "read": answer}


def decide_print(job: Job, env: Env) -> None:
    spot = job.spot
    main = job.main()
    parsed = parse("Q-P", main.raw, spot.readings())
    job.answer = parsed.text
    if g1(job, main, parsed):
        return
    answer, style = styled(job.question, "" if parsed.empty else parsed.text)
    readings = [normal_print(r) for r in spot.readings()]
    # A unit's or a contents entry's number the question expects counts as
    # a reading of its length (a two-figure number where no engine read one).
    number = job.question.get("contentsNumber")
    expected = [len(str(number))] if isinstance(number, int) else []
    limit = max([len(r) for r in readings] + [len(content_of(spot.gap()))] + expected) + 2
    if len(answer) > limit:
        job.refuse("G2", f"{answer!r} is longer than the engines' readings here allow ({limit})")
        return
    word = prose(answer, spot)
    if word:
        job.refuse("G2", f"the answer holds the question's word {word!r}")
        return
    why = g5_new(spot, answer, job.question)
    if why:
        job.refuse("G5", why)
        return
    if job.question.get("follows") and any(pp.CJK(c) or c.isalnum() for c in answer):
        # The question asks whether the marks a furniture deletion left are
        # printed; characters in its answer are what was deleted, read
        # again (engine A read the running head into the body there, so G4
        # and G5 let them through).
        job.refuse("G4", f"{answer!r} writes characters where the question asks only about the marks left beside "
                   "deleted furniture")
        return
    left = agreed_marks(spot, answer) if job.question.get("purpose") != "verify" else ""
    if left:
        job.refuse("G5", f"{left!r}, which the page and engine A both hold between the anchors, is left out")
        return
    if job.question.get("rule") == "K14":
        need = standin_units(spot, env.facts.standins())
        if len(normal_print(answer)) < need:
            job.refuse("G5", f"{answer!r} leaves out a stand-in: K14's answer says what each of the {need} "
                       "stand-in glyph(s) and shared marks there is, and deletes none (a mark engine A did not "
                       "read may stand outside the red lines)")
            return
    if g4_band(env, job, answer):
        job.refuse("G4", f"{answer!r} is the running head's, at a place next to the band")
        return
    if g6_one(spot, answer, job.question) and "一" not in pp.CJK(spot.gap()):
        job.refuse("G6", "一 as a numeral where neither engine read 一")
        return
    gap = spot.gap()
    new = print_gap(gap, answer)
    if job.question.get("rule") in SPACED_NUMBERS and isinstance(job.question.get("contentsNumber"), int) \
            and re.search(r"(?:^|\n|[#\-*+] )[0-9]{1,3}[.．,，、。]?$", new) and pp.CJK(spot.text[spot.gap_end:spot.gap_end + 1]):
        # The number opens the entry or the heading, its title after it: as
        # S4 and S11 write it, a space between.
        new += " "
    if job.question.get("purpose") == "verify":
        job.status, job.guard = "answered", {"passed": True}
        if content_of(gap) != answer:
            job.doubts.append(("verify-disagrees", f"Q-P {job.id}: the print between the anchors reads {answer!r}, "
                               f"the page after edit {job.question.get('edit')} holds {content_of(gap)!r}",
                               {"edit": job.question.get("edit"), "answer": answer, "held": content_of(gap)}))
        return
    why = g6_figures(env, job, new)
    if why:
        job.refuse("G6", why)
        return
    job.status, job.guard = "answered", {"passed": True}
    if content_of(gap) == answer:
        return
    job.edits = trimmed(job, spot.gap_start, gap, new, answer, **style)


def decide_line(job: Job, env: Env) -> None:
    spot = job.spot
    main = job.main()
    parsed = parse("Q-L", main.raw, spot.readings())
    job.answer = parsed.text
    if g1(job, main, parsed):
        return
    if main.extra.get("template") == "title-end":
        title_end(job, env, parsed)
        return
    if job.status == "asking":
        finish_line(job, env, parsed)
        return
    plan_line(job, env, parsed)


def line_readings(job: Job, env: Env) -> tuple[str, str]:
    """What the engines read of the copied line or column: for a line of a
    page printed right to left (S13), engine A's line turned round and
    engine B's run that reads it forwards; else between the anchors."""
    spot = job.spot
    raw = job.question.get("aLine")
    if raw:
        forward = pp.CJK(raw)[::-1]
        b_chars = pp.CJK(spot.reading.pd.b_text)
        at = pp.variant_fold(b_chars).find(pp.variant_fold(forward))
        return forward, b_chars[at:at + len(forward)] if at >= 0 else ""
    return spot.a_read or "", spot.b_read or ""


def content_positions(text: str, start: int, end: int) -> list[tuple[int, str]]:
    """The printed characters of TEXT[start:end] (not white space or
    Markdown structure) with their offsets."""
    out = []
    at = start
    for kind, piece in rr.split_structure(text[start:end]):
        if kind == "c" and not piece.isspace():
            out.append((at, piece))
        at += len(piece)
    return out


def plan_line(job: Job, env: Env, parsed: Parsed) -> None:
    """Q-L character by character: each change the copy makes to the site's
    print (variants are equal), written when the characters it writes were
    read by an engine there (or are marked damaged), and when what it
    deletes is not what both engines read; a character neither engine nor
    the page holds is asked again as a glyph question on its cell."""
    spot = job.spot
    a_line, b_line = line_readings(job, env)
    site = content_positions(spot.text, spot.start, spot.end)
    old = "".join(c for _, c in site)
    # The copy's line breaks (／) are not written: the page's lines are its
    # Markdown structure.
    copy = parsed.text.replace("／", "")
    limit = max(len(normal_print(a_line)), len(normal_print(b_line)), len(old)) + 2
    if len(copy) > limit:
        job.refuse("G2", f"the copy is longer than the engines' readings allow ({limit})")
        return
    if pp.CJK(old) and not pp.CJK(copy):
        # A copy of a line in a red box that holds no character is no copy:
        # written, it would delete the line.
        job.refuse("G2", f"the copy of a printed line holds no character ({parsed.value!r})")
        return
    word = prose(copy, spot)
    if word:
        job.refuse("G2", f"the copy holds the question's word {word!r}")
        return
    read = set(pp.variant_fold(pp.CJK(a_line) + pp.CJK(b_line))) | set(rr.marks_of(a_line + b_line))
    # What each engine read at each of the site's places, where its reading
    # of the line has as many characters as the page's: a character the
    # copy writes in place of another was read there only when an engine
    # read it at that place - not anywhere on the line (a copy wrote 總, a
    # character of the same line, where the print has 編 and the engines 艦).
    at_place = [[pp.variant_fold(line[i]) for line in (pp.CJK(a_line), pp.CJK(b_line)) if len(line) == len(old)]
                for i in range(len(old))] if all(pp.CJK(c) for c in old) else None
    a_chars = Counter(pp.variant_fold(pp.CJK(a_line)))
    b_chars = Counter(pp.variant_fold(pp.CJK(b_line)))
    both = a_chars & b_chars
    # An engine that read nothing of the line does not gainsay the other:
    # where only one engine read it, the copy may change its glyphs (what
    # the question is for) but not leave its characters out.
    lone = (a_chars or b_chars) if not (a_chars and b_chars) else Counter()
    damaged = parsed.damaged
    matcher = difflib.SequenceMatcher(None, pp.variant_fold(old), pp.variant_fold(copy), autojunk=False)
    changes: list[dict[str, Any]] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        removed = old[i1:i2]
        written = copy[j1:j2]
        lost = Counter(pp.variant_fold(pp.CJK(removed))) - Counter(pp.variant_fold(pp.CJK(written)))
        if any(both[c] for c in lost):
            job.doubts.append(("look-refused", f"Q-L {job.id}: the copy leaves out {removed!r}, which both engines "
                               "read", {"guard": "G5", "removed": removed}))
            continue
        if len(pp.CJK(written)) < len(pp.CJK(removed)) and any(lone[c] for c in lost):
            job.doubts.append(("look-refused", f"Q-L {job.id}: the copy leaves out {removed!r}, which the one engine "
                               "that read the line read", {"guard": "G5", "removed": removed}))
            continue
        start = site[i1][0] if i1 < len(site) else (site[-1][0] + 1 if site else spot.start)
        end = site[i2 - 1][0] + 1 if i2 > i1 else start
        # Each written character's place among the page's (a like-for-like
        # change), where its cell is.
        same = op == "replace" and i2 - i1 == j2 - j1

        def read_there(c: str, place: int | None) -> bool:
            if place is not None and at_place is not None and at_place[place]:
                return pp.variant_fold(c) in at_place[place]
            return pp.variant_fold(c) in read
        unknown = [(j, c, i1 + (j - j1) if same else None) for j, c in enumerate(written, j1)
                   if pp.CJK(c) and not read_there(c, i1 + (j - j1) if same else None) and j not in damaged]
        changes.append({"start": start, "end": end, "old": removed, "new": written, "newStart": j1,
                        "unknown": unknown})
    job.answer = copy
    job.pending = changes
    asked = 0
    found = s13_block(job)
    n = len(pp.CJK(job.question.get("aLine") or ""))
    for change in changes:
        for j, c, place in change["unknown"]:
            cell = None
            if place is not None and found is not None and len(old) == n:
                # A line engine A read backwards: the page's place P is
                # engine A's character n-1-P of that line, in the line's own
                # row.
                b, _ = found
                cells = line_cells(job.pim, b, job.question["aLine"])
                index = n - 1 - place
                cell = cells[index] if cells and 0 <= index < len(cells) else None
            elif place is not None and found is None:
                ks = spot.reading.chars_in(site[place][0], site[place][0] + 1)
                cell = job.pim.cell(spot.reading.a_index(ks[0])) if ks else None
            crop = cell_crop(job.pim, cell, not about_band(job.question)) if cell is not None else None
            if crop is None:
                continue
            user = glyph_user("一個字位", pp.CJK(copy[max(0, j - CONTEXT):j]), pp.CJK(copy[j + 1:j + 1 + CONTEXT]),
                              across=bool(cell["across"]))
            asked += 1
            job.calls.append(new_call(job, f"check{asked}", pp.ADJUDICATE_SYSTEM, user, crop, as_kind="Q-G",
                                      position=j, character=c,
                                      page=site[place][1] if place is not None and place < len(site) else None,
                                      engines=sorted(set(at_place[place])) if place is not None and at_place
                                      and at_place[place] else [],
                                      before=pp.CJK(copy[max(0, j - CONTEXT):j]),
                                      after=pp.CJK(copy[j + 1:j + 1 + CONTEXT])))
    if not asked:
        finish_line(job, env, parsed)
        return
    job.status = "asking"


# Said before the context in a copied character's second glyph question: its
# candidates are the model's own two readings, not the engines'.
LINE_ROUND_TWO_NOTE = GLYPH_ROUND_TWO_NOTE + "呢度兩個候選係同一個字位讀咗兩次嘅結果：一次抄成行、一次淨睇呢格。"


def finish_line(job: Job, env: Env, parsed: Parsed) -> None:
    """Q-L's changes written: each character no engine read there written
    only where its glyph question agrees.  Where the glyph question reads
    another character (neither the page's nor an engine's there), the two
    readings are the candidates of a second glyph question on the same
    crop (phase 3's 裁決 question): the one it names is written - two of
    three readings agree - and the character it names is written in the
    copy's place.  The rest are doubts."""
    agreed: dict[int, str] = {}
    seconds = {c.extra.get("position"): c for c in job.calls if c.role.startswith("second")}
    asking = False
    for call in job.calls:
        if not call.role.startswith("check"):
            continue
        answer = parse("Q-G", call.raw)
        if degraded(call) or answer.value is None or answer.unsure or answer.empty or not pp.CJK(answer.text):
            continue
        position, character = call.extra["position"], call.extra.get("character", "")
        if pp.variant_fold(answer.text) == pp.variant_fold(character):
            agreed[position] = answer.text
            continue
        held = {pp.variant_fold(x) for x in [call.extra.get("page") or ""] + list(call.extra.get("engines") or [])}
        if len(pp.CJK(answer.text)) != 1 or pp.variant_fold(answer.text) in held:
            continue
        second = seconds.get(position)
        if second is None:
            seg = {"before": call.extra.get("before", ""), "after": call.extra.get("after", ""),
                   "a": character, "b": answer.text}
            job.calls.append(Call(job.id, f"second{call.role[5:]}", call.kind, pp.ADJUDICATE_SYSTEM,
                                  pp.adjudicate_prompt(seg, note=LINE_ROUND_TWO_NOTE), call.crop,
                                  crop_name(job, f"second{call.role[5:]}"),
                                  extra={"position": position, "candidates": [character, answer.text]}))
            asking = True
            continue
        if second.raw is None:
            asking = True
            continue
        two = parse("Q-G", second.raw)
        if degraded(second) or two.value is None or two.unsure or two.empty:
            continue
        named = next((x for x in (character, answer.text) if pp.variant_fold(x) == pp.variant_fold(two.text)), None)
        if named is not None:
            agreed[position] = named
    if asking:
        job.status = "asking"
        return
    edits: list[re_.Edit] = []
    for ch in job.pending:
        missing = [(j, c) for j, c, _ in ch["unknown"] if j not in agreed]
        if missing:
            job.doubts.append(("look-refused", f"Q-L {job.id}: the copy writes {''.join(c for _, c in missing)!r}, "
                               "which neither engine read there, not marked damaged and not confirmed by a glyph "
                               "question on its cell", {"guard": "Q-L-character", "new": ch["new"], "old": ch["old"]}))
            continue
        spot = job.spot
        new = "".join(agreed.get(j, c) for j, c in enumerate(ch["new"], ch["newStart"]))
        edits += trimmed(job, ch["start"], spot.text[ch["start"]:ch["end"]], new, job.answer,
                         confirmed=sorted(agreed) or None)
    job.status, job.guard = "answered", {"passed": True}
    job.edits = edits


def title_end(job: Job, env: Env, parsed: Parsed) -> None:
    """S9's title end: the copy of the title is the start of the site; the
    title becomes a heading of the question's level, the text after it its
    own paragraph."""
    spot = job.spot
    q = job.question
    title = pp.variant_fold(pp.CJK(parsed.text))
    ks = spot.reading.chars_in(spot.start, spot.end)
    chars = pp.variant_fold("".join(spot.s.chars[k] for k in ks))
    if not title or not chars.startswith(title):
        job.refuse("apply", "the copy of the title is not how the line starts", copy=parsed.text)
        return
    level = int(q.get("level") or 0)
    if not level:
        job.refuse("apply", "the question names no heading level")
        return
    end_k = ks[len(title) - 1]
    end = spot.s.offsets[end_k] + 1
    # Marks the copy writes after the title's last character stay with it.
    tail = normal_print(parsed.text)
    tail = tail[len(tail.rstrip("".join(CLOSING) + "）」』")):] if tail else ""
    while tail and end < len(spot.text) and spot.text[end] == tail[0]:
        end += 1
        tail = tail[1:]
    edits = []
    line_start = spot.text.rfind("\n", 0, spot.start) + 1
    lead = spot.text[line_start:spot.start]
    marker = "#" * level + " "
    if not lead.strip():
        edits.append(question_edit(job, spot.start, spot.start, marker, parsed.text, split="title start"))
    else:
        s, e = rs.break_span(spot.text, spot.start, line_start)
        edits.append(question_edit(job, s, e, "\n\n" + marker, parsed.text, split="title start"))
    line_end = spot.text.find("\n", end)
    line_end = len(spot.text) if line_end < 0 else line_end
    if spot.text[end:line_end].strip():
        s, e = rs.break_span(spot.text, end, line_start)
        edits.append(question_edit(job, s, e, "\n\n", parsed.text, split="title end"))
    job.status, job.guard = "answered", {"passed": True}
    job.edits = edits


def decide_layout(job: Job, env: Env) -> None:
    spot = job.spot
    main = job.main()
    parsed = parse("Q-Y", main.raw)
    job.answer = parsed.text
    if g1(job, main, parsed):
        return
    answer = parsed.text
    template = main.extra.get("template")
    rule = job.question.get("rule")
    wanted = ("標題", "段落開頭") if template == "heading" else ("同一段", "另起一段")
    if answer not in wanted:
        job.refuse("G1", f"{answer!r} is neither {wanted[0]} nor {wanted[1]}")
        return
    job.status, job.guard = "answered", {"passed": True}
    text = spot.text
    line_start = text.rfind("\n", 0, spot.start) + 1
    if template == "heading":
        if rule == "S5" and answer == "段落開頭":
            match = rs.HEADING.match(text[line_start:])
            if match is None:
                return
            edits = [question_edit(job, line_start + len(match.group("indent")), line_start + match.end(), "",
                                   answer, layout="run-in lead")]
            line_end = text.find("\n", line_start)
            line_end = len(text) if line_end < 0 else line_end
            rest = text[line_end:]
            gap = len(rest) - len(rest.lstrip("\n"))
            nxt = rest[gap:].split("\n", 1)[0]
            if gap and nxt.strip() and rj.ordinary(nxt) and not rj.LIST_NUMBER.match(nxt):
                edits.append(question_edit(job, line_end, line_end + gap, "", answer, layout="joined to its paragraph"))
            job.edits = edits
        elif rule == "S9" and answer == "標題":
            level = int(job.question.get("level") or 0)
            if not level:
                job.refuse("apply", "the question names no heading level")
                return
            marker = "#" * level + " "
            edits = []
            lead = text[line_start:spot.start]
            if not lead.strip():
                edits.append(question_edit(job, line_start + len(lead) - len(lead.lstrip()),
                                           line_start + len(lead) - len(lead.lstrip()), marker, answer,
                                           layout="heading"))
            else:
                s, e = rs.break_span(text, spot.start, line_start)
                edits.append(question_edit(job, s, e, "\n\n" + marker, answer, layout="heading"))
            line_end = text.find("\n", spot.end)
            line_end = len(text) if line_end < 0 else line_end
            if text[spot.end:line_end].strip():
                s, e = rs.break_span(text, spot.end, line_start)
                edits.append(question_edit(job, s, e, "\n\n", answer, layout="heading's end"))
            job.edits = edits
        return
    # The paragraph template: P1 a line break (the site), P7 a block's start.
    if rule == "P1":
        if answer == "另起一段":
            job.edits = [question_edit(job, spot.start, spot.end, "\n\n", answer, layout="new paragraph")]
        else:
            tail = text[line_start:spot.start].rstrip()
            head_at = spot.end
            while head_at < len(text) and text[head_at] in " \t":
                head_at += 1
            head = text[head_at:head_at + 1]
            glue = " " if tail[-1:].isascii() and tail[-1:].isalnum() and head.isascii() and head.isalnum() else ""
            job.edits = [question_edit(job, line_start + len(tail), head_at, glue, answer, layout="same paragraph")]
        return
    if answer == "另起一段":
        s, e = rs.break_span(text, spot.start, line_start)
        if s <= line_start:
            return
        job.edits = [question_edit(job, s, e, "\n\n", answer, layout="new paragraph")]


def opens_reading(reading: rs.PageReading, start: int, end: int) -> bool:
    """Whether the page's TEXT[start:end] is what engine A read first on the
    page: its first character is engine A's, and no character engine A read
    before it is one the page holds (a running head engine A read into its
    block, which the page no longer holds, may stand before it)."""
    ks = reading.chars_in(start, end)
    if not ks:
        return False
    j = reading.a_index(ks[0])
    if j is None:
        return False
    back = reading.align.a_to_sealed
    return all(back[i] is None for i in range(min(j, len(back))))


def decide_boundary(job: Job, env: Env) -> None:
    main = job.main()
    parsed = parse("Q-B", main.raw)
    job.answer = parsed.text
    if g1(job, main, parsed):
        return
    answer = parsed.text
    if answer not in ("續文", "另起一段"):
        job.refuse("G1", f"{answer!r} is neither 續文 nor 另起一段")
        return
    scan = job.question["page"]
    prev = job.question.get("previousPage")
    texts = env.ledger.texts
    tail, head = rj.last_line(texts[prev]), rj.first_line(texts[scan])
    kinds = (rj.kind_of(tail), rj.kind_of(head))
    edits: list[re_.Edit] = []
    if answer == "續文":
        if kinds[0] != "prose" or kinds[1] not in ("prose", "heading"):
            job.refuse("apply", f"the next page goes on from the previous, but a join cannot be written between "
                       f"a {kinds[0]} and a {kinds[1]} (finalize's contract)")
            return
        label = "join"
        if kinds[1] == "heading":
            text = texts[scan]
            start = text.find(head)
            match = rs.HEADING.match(head)
            if not opens_reading(env.reading(scan), start + match.end(), start + len(head)):
                # The crop shows the print going on at the column's head; a
                # heading the page sets first but engine A reads elsewhere
                # (a heading the formatter moved to the page's top) would
                # be joined into the middle of the previous page's sentence.
                job.refuse("apply", "the next page goes on from the previous, but its first line is a heading engine "
                           "A does not read at the head of the page: joined, it would stand inside the previous "
                           "page's sentence", heading=head)
                return
            edits.append(question_edit(job, start + len(match.group("indent")), start + match.end(), "", answer,
                                       layout="a heading that goes on from the previous page is text"))
    else:
        label = {"heading": "structural", "list": "list-new"}.get(kinds[1], "paragraph")
    job.status, job.guard = "answered", {"passed": True}
    job.edits = edits
    job.label = {"page": scan, "label": label, "answer": answer}


DECIDE: dict[str, Callable[[Job, Env], None]] = {
    "Q-G": decide_glyph, "Q-P": decide_print, "Q-L": decide_line, "Q-Y": decide_layout, "Q-B": decide_boundary,
}


# --- the round ------------------------------------------------------------------------------

@dataclass
class Outcome:
    """What a round of questions did: the log records written, the pages
    whose boundary an answer settled, and the questions by outcome."""
    records: list[dict[str, Any]] = field(default_factory=list)
    settled: set[int] = field(default_factory=set)
    counts: Counter = field(default_factory=Counter)


def verify_site(question: Mapping[str, Any], ledger: re_.Ledger) -> dict[str, Any] | None:
    """A --verify-sample question's site: the text its edit wrote, as the
    page held it just after the edit."""
    record = next((r for r in ledger.records if r["id"] == question.get("edit")), None)
    if record is None:
        return None
    page = record["page"]
    states, records = page_history(ledger, page)
    i = next(n for n, r in enumerate(records) if r["id"] == record["id"])
    text = states[i + 1]
    start, end = record["offset"], record["offset"] + len(record["after"])
    return {"line": text.count("\n", 0, start) + 1, "start": start, "end": end, "text": text[start:end],
            "before": pp.CJK(text[:start])[-8:], "after": pp.CJK(text[end:])[:8]}


def ask(questions: Sequence[dict[str, Any]], env: Env, stage: str = "questions") -> Outcome:
    """Ask QUESTIONS (planned, with their ids) and write what their answers
    settle: edits through the ledger (stage STAGE), doubts, and boundary
    labels.  Under plan-only the crops and prompts are made and nothing is
    asked."""
    outcome = Outcome()
    histories: dict[int, tuple[list[str], list[dict[str, Any]]]] = {}
    pims: dict[tuple[int, str], PageImage] = {}
    jobs: list[Job] = []
    seen: dict[tuple[str, int, int, int], str] = {}
    for question in questions:
        if question.get("status") not in (None, "planned"):
            continue
        job = Job(question)
        if question.get("purpose") == "verify" and not question.get("site"):
            site = verify_site(question, env.ledger)
            if site is not None:
                question["site"] = site
                question.setdefault("rule", "verify")
        where = locate(question, env.ledger, histories)
        if isinstance(where, str):
            if where.startswith("conflict"):
                job.status = "conflict"
                job.doubts.append(("conflict", f"{question.get('kind')} {question.get('id')}: the text it asks about "
                                   f"was changed by edit {where.split()[1]} after it was planned; the edit stands",
                                   {"record": where.split()[1]}))
            else:
                job.status = "not-asked"
                job.doubts.append(("look-not-asked", f"{question.get('kind')} {question.get('id')}: {where}", {}))
            jobs.append(job)
            continue
        start, end = where
        page = question["page"]
        reading = env.reading(page)
        job.spot = make_spot(reading, page, start, end)
        at_place = question.get("atPlace")
        if isinstance(at_place, Mapping):
            # The rule read what each engine read at the place (F8: the run
            # beyond the page's edge, not the band after it): those are the
            # readings the answer is weighed against, and the candidates.
            job.spot.a_read = job.spot.a_wide = str(at_place.get("a") or "")
            job.spot.b_read = job.spot.b_wide = str(at_place.get("b") or "")
        # A print or glyph question is about its gap between the anchors:
        # two such questions over one gap are one question.
        about = (job.spot.gap_start, job.spot.gap_end) if question["kind"] in ("Q-P", "Q-G") else (start, end)
        key = (question["kind"], page, *about, question.get("purpose"))
        if key in seen:
            job.status = "merged"
            question["mergedInto"] = seen[key]
            job.spot = None
            jobs.append(job)
            continue
        seen[key] = question["id"]
        pim_key = (page, env.ledger.texts[page])
        if pim_key not in pims:
            pims[pim_key] = PageImage(env.book, env.model, page, reading)
        job.pim = pims[pim_key]
        why = None
        try:
            why = build(job, env)
        except Exception as error:  # noqa: BLE001 - a crop that fails is a question not asked
            why = f"no crop: {type(error).__name__}: {error}"
        if why:
            job.status = "not-asked"
            job.doubts.append(("look-not-asked", f"{question['kind']} {question['id']}: {why}", {}))
        jobs.append(job)
    live = [job for job in jobs if job.calls and job.status == "planned"]
    env.asker.run([c for job in live for c in job.calls])
    if env.asker.plan_only:
        # A plan asks nothing and doubts nothing: a question it cannot place
        # or cut a crop for says why, and stays planned.
        for job in jobs:
            if job.status in ("not-asked", "conflict"):
                job.question["unaskable"] = job.doubts[0][1] if job.doubts else job.status
                job.doubts = []
            if job.status != "merged":
                job.status = "planned"
        return finish(jobs, env, outcome, stage)
    # The answers; a job that needs more (a second glyph round, a copied
    # character's glyph question, and that question's second round) asks
    # them together, round by round.
    for _ in range(3):
        for job in live:
            if job.status in ("planned", "asking") and all(c.raw is not None for c in job.calls):
                try:
                    DECIDE[job.question["kind"]](job, env)
                except Exception as error:  # noqa: BLE001 - one answer that cannot be read stops no other
                    job.refuse("error", f"the answer could not be applied: {type(error).__name__}: {error}")
        more = [c for job in live if job.status == "asking" for c in job.calls if c.raw is None]
        if not more:
            break
        env.asker.run(more)
    for job in live:
        if job.status == "asking" and env.asker.listing:
            # --no-model on a resumed run: the follow-up is a question not
            # asked, not an answer refused.
            roles = [c.role for c in job.calls if c.raw is None]
            job.status, job.edits = "not-asked", []
            job.doubts.append(("look-not-asked", f"{job.question['kind']} {job.id}: its follow-up call(s) "
                               f"{', '.join(roles)} hold no answer and --no-model asks none", {"roles": roles}))
        elif job.status == "asking":
            job.refuse("G1", "a follow-up question got no answer")
    return finish(jobs, env, outcome, stage)


def finish(jobs: Sequence[Job], env: Env, outcome: Outcome, stage: str) -> Outcome:
    """G7 and the writing: each job's edits, in plan order, unless one
    overlaps an edit of an earlier job (a `conflict` doubt); then the
    records."""
    taken: dict[int, list[tuple[int, int, str]]] = {}
    accepted: list[re_.Edit] = []
    for job in jobs:
        if not job.edits:
            continue
        clash = None
        for edit in job.edits:
            for (s, e, owner) in taken.get(edit.page, []):
                if re_.overlaps((edit.start, edit.end), (s, e)):
                    clash = owner
                    break
            if clash:
                break
        if clash:
            job.status = "conflict"
            job.guard = {"passed": False, "guard": "G7", "why": f"its edits overlap those of {clash}"}
            job.doubts.append(("conflict", f"{job.question['kind']} {job.id}: its answer edits text that {clash}'s "
                               "answer edits; the first question's answer was written", {"guard": "G7",
                                                                                          "applied": clash}))
            job.edits = []
            continue
        for edit in job.edits:
            taken.setdefault(edit.page, []).append((edit.start, edit.end, job.id))
        accepted.extend(job.edits)
    written = env.ledger.apply(stage, accepted) if accepted else []
    by_question: dict[str, list[str]] = {}
    for record in written:
        by_question.setdefault(record["question"], []).append(record["id"])
    for job in jobs:
        q = job.question
        for kind, detail, fields in job.doubts:
            env.ledger.doubt(kind, q.get("page"), detail, question=q.get("id"), stage=stage, **fields)
        if job.label is not None and env.boundaries is not None:
            page = job.label["page"]
            env.boundaries[page] = job.label["label"]
            evidence = (env.evidence or {}).setdefault(str(page), {})
            evidence.update({"label": job.label["label"], "rule": "Q-B", "verified": True, "question": job.id,
                             "answer": job.label["answer"]})
            evidence.pop("why", None)
            outcome.settled.add(page)
        main = job.main()
        q["status"] = job.status if job.status != "asking" else "refused"
        if job.spot is not None:
            q["located"] = {"start": job.spot.start, "end": job.spot.end, "gapStart": job.spot.gap_start,
                            "gapEnd": job.spot.gap_end, "engineA": job.spot.a_read, "engineB": job.spot.b_read}
        if main is not None:
            q["crop"] = main.name
            q["cropSha256"] = pp.sha256_bytes(main.crop)
            q["promptSha256"] = pp.sha256_bytes((main.system + "\0" + main.user).encode("utf-8"))
            q["hash"] = main.hash
            q["prompt"] = main.user
            q["rawAnswer"] = main.raw
            q["effort"] = main.metrics.get("effort")
        q["answer"] = job.answer
        q["guard"] = job.guard
        q["edits"] = by_question.get(job.id, [])
        q["calls"] = [dict(c.record(), settings=env.asker.settings,
                           metrics={k: v for k, v in c.metrics.items() if isinstance(v, (int, float, str, bool))
                                    or v is None}) for c in job.calls]
        q["tokens"] = {"prompt": sum(c.metrics.get("prompt_tokens", 0) or 0 for c in job.calls),
                       "completion": sum(c.metrics.get("completion_tokens", 0) or 0 for c in job.calls)}
        q["seconds"] = round(sum(c.seconds for c in job.calls), 2)
        if job.label is not None:
            q["boundary"] = job.label
        outcome.counts[q["status"]] += 1
    outcome.records = written
    return outcome
