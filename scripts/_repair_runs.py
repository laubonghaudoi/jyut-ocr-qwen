"""The book repair tool's text-run rules (scripts/repair_book.py, stage
`runs`): the digits, Latin letters and kana both engines read between two
characters that the page lacks, the marks a refused first answer and engine
A agree on, the marks both engines read in a table's cells that the page
lacks, and the contents numbers an earlier stage moved against both
engines' reading.

Why the stage exists (measured on a 609-page modern academic book,
2026-10-01): phase 3 merges the engines on CJK characters only
(proofread_pages.CJK), so a year, a page range, a volume number, a Latin
name or a kana title that both engines read stands in the page only where
the punctuator wrote it from the crop.  Of the text runs both engines read
identically, 5,455 gaps on 476 pages lacked them in the sealed pages; 122
of 122 such runs drawn at random matched the print on the page image, and
every error found under agreement was a note number (a circled figure),
which this stage never writes.

The unit is the gap between two consecutive CJK characters of the page
(_repair_align: gaps[k] is the raw text before character k), and the
evidence is two independent readings of that gap: engine A's between the
two characters it aligns to, adjacent in its text, and engine B's likewise.
Each rule compares the gaps as tokens (text runs, marks by class, cell and
row boundaries of a table; line breaks, spaces and engine markup set aside;
a gap's text does not open a line, so a hyphen inside a line is a mark and
not a list marker).  Two readings agree when their tokens are the same, or
when the characters they hold are (fused: one engine wraps a title in
emphasis markers, and the point before it then ends the run).

What is written: a run as engine A spells it; a mark of the page stays as
it is and where it is; a mark the page lacks is written only beside a run
it shares engine A's line with, or in a table's cell (N5), in engine A's
glyph - an ASCII mark in its ordinary full-width form, unless it stands in
Western text (written()).

Rules, in the order they run (the first two applied before the rest; all
three steps pass the page-edge check, edge_safe):
- N4 the contents stage (S11) wrote an entry's number at the head of its
  line, taken from the end of the line before it, or dropped the bracket
  opening an item (with the line's list marker or trailing spaces, when it
  took those too), or the heading marker of a title block.  Where engine A
  (and engine B where it is aligned there) reads the number at the end of
  the line before, after other print of that line - a number on a line of
  its own is the entry's own - and the number has its place there (the page
  holds it, or N1 will write it: _lands), the number goes from the head;
  where they read the bracket at the line's head, it is put back; where
  engine A labels the block a title or engine B writes a heading there, the
  marker is put back at the level the levels stage gave the unit titles
  sealed at that level.
- R1 a punctuation pass whose retry was kept over a first answer refused on
  the count: its first answer stands on the page exactly once (its
  characters), and in a gap of that stretch the first answer and engine A
  write the same marks and runs (by class) while the page differs (and
  engine B, where it is aligned there, agrees with them): the page's gap
  becomes engine A's.  A refused first answer is the model's reading of the
  crop; engine A is an independent witness that never saw it, and its
  glyphs are the print's where the two differ in shape.  Not at an outer
  gap of the stretch where engine A ends its line and the page does not
  (the page's gap then holds the next block's marks too), nor over the
  page's markup, nor a figure opening a line.
- N1 both engines hold the same text runs in the gap and the page holds
  none.  The page's marks are matched to engine A's, each to a mark of its
  own class (of its coarse class only where engine A holds none of that
  class).  T1, every mark of engine A stands on the page: each run goes in
  at its place among them; a connector the page holds beyond them goes only
  when a run of the gap itself holds that connector and engine B reads no
  such mark (the hyphen left of 119-140).  T2, engine A holds marks the page
  lacks: the page's marks stay, and each stretch between two of them that
  holds a run on engine A's line becomes engine A's, runs and marks
  (stretches); a stretch of marks alone is left; the result must be the
  same whether the page's marks are matched from the left or from the
  right.  A bracket written this way that finds no partner on its line once
  the page's edits stand is withheld (unpaired).  A run on the far side of
  a line break in engine A goes on that side on the page; a run with no mark
  beside it is not put on a side of a page break engine A does not give,
  and a run on a line of its own in engine A is not joined to another line.
  The rows of a table that phase 3 moved into an earlier page's table (the
  seal's tableStitch) are read on the page whose engines read them, in its
  text before the move, and written where the rows stand now (_moved_rows).
- N5 a gap inside a table of the page (table_spans: a Markdown table from
  its label row and rule, an HTML table from its opening tag to its closing
  one) beside a character that lies in an engine A block the punctuator
  never read (its label in proofread_pages.FURNITURE_LABELS: a table
  block; cell_gap, per side of the gap), where the page holds neither a
  mark nor a run and both engines hold the same tokens, marks alone or
  marks with runs: the gap becomes the engines' - marks and runs in engine
  A's order and glyphs (written), the page's cell boundaries, spaces and
  breaks where they are, the cell boundaries matched one to one
  (stretches; a gap that N1 weaves is written once, whole, and named N5
  when it holds a mark N1 leaves - N1 again where the bracket guard
  withheld every such mark).  Phase 3 runs no punctuation pass on a table
  block: its cells hold engine A's marks, none, or the （） the structure
  pass's lock lets it add, so an empty gap of such a cell where both
  engines read marks is lost print, whereas in running text - and in a
  page table the structure pass built from a text block that had its own
  pass - an empty gap may be the punctuator's reading of the crop and
  stays.  Measured on the 609-page book (2026-10-02): where engine A's
  grid was refused, the structure pass rebuilt the table from the bare
  merged characters with punctuation locked, and 30 pages' cells were
  sealed with 29 of the 1,040 marks engine A read there; the rule wrote
  723 marks in 645 gaps on 18 pages, and 30 of 30 of its edits drawn at
  random matched the print on the page image; the one page table built
  from a punctuated text block (scan 606) gets no edit.  Not on a page
  punctuated whole (unread_marks), nor in a table rebuilt from its crop
  (unread_tables): there an empty gap may be the model's reading.  Not
  where engine A holds a star, a character a renderer reads as markup
  (RENDERER_MARKS) or one that prints nothing, nor a note marker; the
  bracket guard (unpaired) holds for these marks too, over all the edits
  of the page together, so the two brackets of a pair written in two gaps
  of one row stand - not across a cell boundary, nor around a gap between
  them where engine A read brackets the page will not hold.  The marks
  the rule found and could not write are one doubt a page
  (`run-no-place`, with their count).
- N3 the page's marks in the gap are the engines' agreed marks in another
  order (an emptied bracket pair written `）（`), both engines writing the
  whole gap alike: the gap is rewritten in their order, with the runs, each
  mark a mark of the page (its own shapes stay).
- N2 one or more whole lines of no CJK character (a Western-language
  bibliography entry, an English footnote) that both engines read alike
  between the same two characters: written as paragraphs of their own at
  the page's one line break there, lines engine B reads as one line joined;
  where the engines cut the gap into the same lines and differ in some,
  the others are written.  A bracket the page holds there that is one of
  the lines' own goes.  A page sealed empty where both engines read such
  text alike: every line of it.
Never written: a note number in any form (circled, superscript in LaTeX or
HTML, a plain figure beside one, a figure of its own opening a line, a
short figure right after the mark that ends a sentence - the engines agree
on the wrong value too often), the page's whole folio on a line of its own,
an edit that would change the kind of a page's first or last line, glue
two runs across a `join` or break the finalize contract there, a line that
would become a list item or table row, a gap a model answer wrote into or
took text from.  A run only one engine read (one doubt a page for the gaps
engine B is not aligned at), a gap where the engines differ, an agreed run
with no clean place, a stretch whose marks could not be restored and a
heading that could not be put back are doubts (`run-one-engine`,
`run-engines-differ`, `run-no-place`, `retry-marks-unverified`,
`heading-kind-unknown`; none for a gap of marks alone in running text,
which no rule writes); the note numbers of a page that the engines read
and the page lacks or writes with another value are one doubt per page
(`note-markers-unverified`), and so are the marks of a page's table cells
that N5 found and could not write (`run-no-place`, with their count).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Callable, Iterable, Mapping, Sequence

import proofread_pages as pp
import _ocr_markdown as om
import _tables
import _repair_align as ra
import _repair_edits as re_
import _repair_joins as rj
import _repair_rules as rr
import _repair_structure as rs


# --- tokens ---------------------------------------------------------------------

RUN, MARK, BREAK, CELL, ROW, MARKER, MARKUP, SPACE, STRUCT, OTHER = (
    "run", "mark", "break", "cell", "row", "marker", "markup", "space", "struct", "other")

# Letters and figures of a text run: ASCII and full-width digits and
# letters, Latin with diacritics, Greek, Cyrillic, kana, hangul, Roman
# numerals.
ALNUM = ("0-9A-Za-z\u00c0-\u02af\u0370-\u03ff\u0400-\u04ff\u1e00-\u1eff"
         "\u3041-\u3096\u3099-\u309f\u30a0-\u30fa\u30fc-\u30ff\u31f0-\u31ff\uff66-\uff9f"
         "\uac00-\ud7af\u2160-\u217f\uff10-\uff19\uff21-\uff3a\uff41-\uff5a")
LATIN = "A-Za-z\u00c0-\u02af\u0370-\u03ff\u0400-\u04ff\u1e00-\u1eff\uff21-\uff3a\uff41-\uff5a"
# A run: letters and figures, joined by a connector (a hyphen, slash, wave,
# colon, apostrophe, or a point or comma that a letter or figure follows,
# with one space allowed after the point or comma), or by one space before
# a Latin word; a percent sign may end it.
WORD = rf"[{ALNUM}]+"
RUN_RE = re.compile(
    rf"{WORD}(?:"
    rf"[-\u2010/~\uff5e\u301c'\u2019]{WORD}"              # a hyphen, slash, wave or apostrophe joins anything
    rf"|[:\uff1a](?=[0-9\uff10-\uff19]){WORD}"              # a colon between figures (17:2)
    rf"|\.(?=[0-9])[0-9]+"                                 # a decimal point
    rf"|,(?=[0-9]{{3}}(?![0-9]))[0-9]{{3}}"                 # a thousands comma (2,100)
    rf"|(?<=[{LATIN}])[.,] ?(?=[{ALNUM}]){WORD}"            # a point or comma after a letter (E. J., Press, 1962)
    rf"| (?=[{LATIN}]){WORD}"                               # a space before a Latin word
    rf")*[%\uff05]?")
# Note markers: circled and parenthesised figures, superscript and subscript
# digits.
MARKER_RE = re.compile(r"[\u2460-\u24ff\u2776-\u2793\u3220-\u3229\u3251-\u325f\u3280-\u3289\u32b1-\u32bf"
                       r"\u2070-\u2079\u00b9\u00b2\u00b3\u2080-\u2089\u2020\u2021]")
# A superscript or subscript in HTML form: a note marker.
SUP_RE = re.compile(r"<(sup|sub)>([^<\n]{0,40})</\1>", re.I)
# A Markdown rule: a line of three or more of one of - * _.
RULE_RE = re.compile(r"[ \t]*([-*_])(?:[ \t]*\1){2,}[ \t]*(?=\n|$)")
LATEX_RE = re.compile(r"\$[^$\n]{0,200}\$")
SUPERSCRIPT_RE = re.compile(r"\^\{[^}\n]{0,40}\}|\t?extcircled\{[^}\n]{0,40}\}|\\textcircled\{[^}\n]{0,40}\}")
COMMAND_RE = re.compile(r"\\[A-Za-z]+|[{}]")
HTML_ROW_RE = re.compile(r"</t[dh]>\s*</tr>\s*(?:</?t(?:body|head)>\s*)*(?:<tr[^>]*>\s*)?<t[dh][^>]*>", re.I)
HTML_CELL_RE = re.compile(r"</t[dh]>\s*<t[dh][^>]*>", re.I)
HTML_CELL_END_RE = re.compile(r"</t[dh]>(?:\s*</tr>)?(?:\s*</t(?:body|head)>)?(?:\s*</table>)?", re.I)
HTML_CELL_START_RE = re.compile(r"(?:<table[^>]*>\s*)?(?:<t(?:body|head)>\s*)?(?:</caption>\s*)?(?:<tr[^>]*>\s*)?<t[dh][^>]*>",
                                re.I)
BR_RE = re.compile(r"<br\s*/?>", re.I)
TAG_RE = re.compile(r"</?[A-Za-z][^<>\n]{0,60}>")
PAGE_ROW_RE = re.compile(r"[ \t]*\|[ \t]*\n(?:[ \t]*\|?[ \t:|-]*\|[ \t]*\n)?[ \t]*\|[ \t]*")
PAGE_CELL_RE = re.compile(r"[ \t]*\|[ \t]*")
STRUCT_RE = re.compile(r"[ \t]*(?:#{1,6}[ \t]+|[-*+][ \t]+|>[ \t]*)+")
LEADER_RE = re.compile(r"\u2026+|\u22ef+|\.{2,}|\u00b7{2,}|\u30fb{2,}|\u2022{2,}")
DASH_RE = re.compile(r"[\u2014\u2015\u2500\u2013\u2012]+")
SPACE_RE = re.compile(r"[ \t\u3000]+")

# Mark classes: the forms of one printed mark that the engines and the
# punctuator write (width, vertical presentation, the shape of a title or
# square bracket).
_CLASSES = {
    "open-round": "\uff08(\ufe35", "close-round": "\uff09)\ufe36",
    "open-square": "\u3014\uff3b[\u3010\u3016", "close-square": "\u3015\uff3d]\u3011\u3017",
    "open-title": "\u300a\u3008<", "close-title": "\u300b\u3009>",
    "open-quote": "\u300c\u300e\ufe41\ufe43\u201c\u2018", "close-quote": "\u300d\u300f\ufe42\ufe44\u201d\u2019",
    "comma": "\uff0c,", "stop": "\u3002\uff0e.", "enum": "\u3001", "semi": "\uff1b;", "colon": "\uff1a:\ufe30",
    "question": "\uff1f?", "bang": "\uff01!", "dot": "\u00b7\u2022\u30fb", "wave": "~\uff5e\u301c",
    "star": "*\uff0a\u203b", "amp": "&\uff06", "hyphen": "-\u2010", "slash": "/\uff0f",
}
MARK_CLASS = {c: name for name, chars in _CLASSES.items() for c in chars}
# A connector a run carries, which the page may hold alone when the run
# was dropped ('-。' for '119-140。').
CONNECTOR_CLASSES = frozenset({"hyphen", "colon", "comma", "stop", "slash", "wave", "dot"})
OPEN_CLASSES = frozenset({"open-round", "open-square", "open-title", "open-quote"})
CLOSE_CLASSES = frozenset({"close-round", "close-square", "close-title", "close-quote"})
RUN_FOLD = str.maketrans({**{chr(0xff10 + k): str(k) for k in range(10)},
                          **{chr(0xff21 + k): chr(0x41 + k) for k in range(26)},
                          **{chr(0xff41 + k): chr(0x61 + k) for k in range(26)},
                          "\uff5e": "~", "\u301c": "~", "\uff0e": ".", "\uff0c": ",", "\uff1a": ":", "\u2019": "'",
                          "\u2010": "-", "\uff05": "%", " ": None})
# The largest gap (in tokens) a rule weaves; a longer one is a table or a
# block of its own, and a doubt.
TOKEN_LIMIT = 80
# Engine A's labels for a block of a page's furniture.
FURNITURE_LABELS = frozenset({"header", "footer", "number", "aside_text", "seal"})
# A run of this many digits or fewer that opens a line in engine A is a
# footnote's own number or an item's, not body print.
LINE_FIGURE_DIGITS = 4


@dataclass
class Token:
    kind: str
    raw: str
    start: int
    end: int
    cls: str = ""

    @property
    def key(self) -> tuple[str, str] | None:
        """What the token compares as; None for a token set aside."""
        if self.kind == RUN:
            return (RUN, self.raw.translate(RUN_FOLD))
        if self.kind in (MARK, MARKER, OTHER):
            return (self.kind, self.cls)
        if self.kind in (CELL, ROW):
            return (self.kind, "")
        return None


def _marker_value(text: str) -> str:
    """A note marker's figures: circled or superscript digits folded to
    ASCII (NFKC), other marks left out."""
    import unicodedata
    folded = unicodedata.normalize("NFKC", text)
    return "".join(c for c in folded if c.isdigit()) or folded.strip()


def tokens(text: str, side: str, line_start: bool = False) -> list[Token]:
    """TEXT as tokens; SIDE is "page", "a" or "b" (the engine's markup is
    read as such, the page's Markdown as structure).  LINE_START: TEXT opens
    a line (a gap's text follows a character, and does not, unless it is the
    page's or the engine's first)."""
    out: list[Token] = []
    at = 0
    n = len(text)
    while at < n:
        c = text[at]
        # Structure at a line's start: the page's heading, bullet and quote
        # markers and its rules; engine B's heading markers.
        if line_start and side != "a":
            m = RULE_RE.match(text, at)
            if m:
                out.append(Token(STRUCT if side == "page" else MARKUP, m.group(), at, m.end()))
                at = m.end()
                line_start = False
                continue
            m = STRUCT_RE.match(text, at)
            if m and m.end() > at:
                out.append(Token(STRUCT if side == "page" else MARKUP, m.group(), at, m.end()))
                at = m.end()
                line_start = False
                continue
        line_start = False
        if c == "\n":
            out.append(Token(BREAK, c, at, at + 1))
            at += 1
            line_start = True
            continue
        if side == "a" and text.startswith("\\n", at):
            out.append(Token(BREAK, "\\n", at, at + 2))
            at += 2
            line_start = True
            continue
        m = SPACE_RE.match(text, at)
        if m:
            out.append(Token(SPACE, m.group(), at, m.end()))
            at = m.end()
            continue
        if side != "page" or c == "$":
            m = LATEX_RE.match(text, at)
            if m:
                inner = COMMAND_RE.sub("", m.group()[1:-1]).replace("^", "").strip()
                if not inner:
                    out.append(Token(MARKUP, m.group(), at, m.end()))
                elif MARKER_RE.search(inner) or re.fullmatch(r"[(\uff08]?[0-9]{1,3}[)\uff09]?", inner) \
                        or re.fullmatch(r"[*\u2217]", inner):
                    out.append(Token(MARKER, m.group(), at, m.end(), _marker_value(inner)))
                else:
                    out.append(Token(OTHER, m.group(), at, m.end(), "latex"))
                at = m.end()
                continue
        m = SUPERSCRIPT_RE.match(text, at)
        if m:
            out.append(Token(MARKER, m.group(), at, m.end(), _marker_value(m.group())))
            at = m.end()
            continue
        if c == "\\" or c in "{}":
            m = COMMAND_RE.match(text, at)
            if m:
                out.append(Token(OTHER if m.group() not in ("{", "}") and side != "page" else MARKUP,
                                 m.group(), at, m.end(), "latex"))
                at = m.end()
                continue
        if c == "<":
            m = SUP_RE.match(text, at)
            if m:
                out.append(Token(MARKER, m.group(), at, m.end(), _marker_value(m.group(2))))
                at = m.end()
                continue
            m = HTML_ROW_RE.match(text, at)
            if m:
                out.append(Token(ROW, m.group(), at, m.end()))
                at = m.end()
                continue
            m = HTML_CELL_RE.match(text, at)
            if m:
                out.append(Token(CELL, m.group(), at, m.end()))
                at = m.end()
                continue
            m = HTML_CELL_END_RE.match(text, at) or HTML_CELL_START_RE.match(text, at)
            if m:
                out.append(Token(CELL, m.group(), at, m.end()))
                at = m.end()
                continue
            m = BR_RE.match(text, at)
            if m:
                out.append(Token(BREAK, m.group(), at, m.end()))
                at = m.end()
                line_start = True
                continue
            m = TAG_RE.match(text, at)
            if m:
                out.append(Token(MARKUP, m.group(), at, m.end()))
                at = m.end()
                continue
        if c == "|" or (c in " \t" and "|" in text[at:at + 3]):
            m = PAGE_ROW_RE.match(text, at)
            if m:
                out.append(Token(ROW, m.group(), at, m.end()))
                at = m.end()
                line_start = True
                continue
            m = PAGE_CELL_RE.match(text, at)
            if m:
                out.append(Token(CELL, m.group(), at, m.end()))
                at = m.end()
                continue
        m = MARKER_RE.match(text, at)
        if m:
            out.append(Token(MARKER, m.group(), at, m.end(), _marker_value(m.group())))
            at = m.end()
            continue
        m = RUN_RE.match(text, at)
        if m:
            out.append(Token(RUN, m.group(), at, m.end()))
            at = m.end()
            continue
        m = LEADER_RE.match(text, at)
        if m:
            out.append(Token(MARK, m.group(), at, m.end(), "leader"))
            at = m.end()
            continue
        m = DASH_RE.match(text, at)
        if m:
            out.append(Token(MARK, m.group(), at, m.end(), "dash"))
            at = m.end()
            continue
        if side == "b" and c in "*_":
            out.append(Token(MARKUP, c, at, at + 1))
            at += 1
            continue
        if c == "#":
            out.append(Token(MARKUP if side == "b" else MARK, c, at, at + 1, "hash"))
            at += 1
            continue
        out.append(Token(MARK, c, at, at + 1, MARK_CLASS.get(c, c)))
        at += 1
    return out


def keys(toks: Sequence[Token], cells: bool = True) -> list[tuple[str, str]]:
    """The comparable tokens of TOKS: runs, marks by class, markers and
    unknown markup; cell and row boundaries when CELLS."""
    return [t.key for t in toks if t.key is not None and (cells or t.kind not in (CELL, ROW))]


def coarse(key: tuple[str, str]) -> tuple[str, str]:
    """A mark's key with the opening and closing shapes as one class each
    (the page writes 〈 where the engines have 《)."""
    kind, cls = key
    if kind == MARK:
        if cls in OPEN_CLASSES:
            return (MARK, "open")
        if cls in CLOSE_CLASSES:
            return (MARK, "close")
    return key


# A connector as a mark, in the form a run holds it in (RUN_FOLD).
_FUSED_MARK = {"comma": ",", "stop": ".", "colon": ":", "hyphen": "-", "slash": "/", "wave": "~"}


def fused(toks: Sequence[Token]) -> str:
    """The print of TOKS as one string: each run folded, each mark by its
    class - a connector as the character a run would hold it as - and two
    runs with no mark between them kept apart; spaces, breaks, markup and
    table boundaries left out.  Two readings that hold the same characters
    and cut them into runs differently are equal: one engine wraps a title
    in emphasis markers, and the point before it then ends the run."""
    out: list[str] = []
    last_run = False
    for t in toks:
        if t.kind == RUN:
            out.append(("\x03" if last_run else "") + t.raw.translate(RUN_FOLD))
            last_run = True
        elif t.kind == MARK:
            out.append("'" if t.raw in ("'", "\u2018", "\u2019") else _FUSED_MARK.get(t.cls) or f"\x01{t.cls}\x01")
            last_run = False
        elif t.kind in (MARKER, OTHER):
            out.append(f"\x02{t.kind}:{t.cls}\x02")
            last_run = False
    return "".join(out)


def agree(a: Sequence[Token], b: Sequence[Token]) -> bool:
    """Whether two readings of a gap hold the same print (table boundaries
    aside)."""
    return keys(a, cells=False) == keys(b, cells=False) or fused(a) == fused(b)


# What two readings of Western text may differ in and still be one reading
# of the print: a hyphen between two letters (a word one engine keeps
# hyphenated at the printed line's end and the other joins - Conten-tious /
# Contentious, Pre-ss / Press on the modern book's notes and bibliography) and
# an apostrophe's form (fused folds the curly ones).  Not a hyphen between
# figures: 91-104 is a range and 91104 a number.
_LOOSE_HYPHEN = re.compile(r"(?<=[^\W\d_])-(?=[^\W\d_])")


def loose(toks: Sequence[Token]) -> str:
    """The print of TOKS as fused() gives it, with the hyphens inside words out."""
    return _LOOSE_HYPHEN.sub("", fused(toks))


def nearly(a: Sequence[Token], b: Sequence[Token]) -> bool:
    """Whether two readings that do not agree() differ in hyphens inside words
    or in the form of an apostrophe only (loose).  Such a gap is written as
    engine A reads it, with a doubt naming both readings: on the modern book
    one such hyphen kept the whole of a 44-run footnote and a 176-run
    bibliography page out, while every other run of them agreed."""
    return runs_of(a) != [] and runs_of(b) != [] and loose(a) == loose(b)


def runs_of(toks: Sequence[Token]) -> list[Token]:
    return [t for t in toks if t.kind == RUN]


def show(text: str, limit: int = 60) -> str:
    text = text.replace("\n", "\u23ce").replace("\t", " ")
    return text if len(text) <= limit else text[:limit - 1] + "\u2026"


# --- the page as the stage reads it ---------------------------------------------------

@dataclass
class Gap:
    """One gap of the page: between page characters K-1 and K (K = 0 is the
    page's leading edge, K = len(chars) its trailing edge), its span in the
    page text, and what each side holds there (None: the engine is not
    aligned to adjacent characters there)."""
    k: int
    start: int
    end: int
    page: list[Token]
    a: list[Token] | None
    b: list[Token] | None
    a_raw: str | None
    b_raw: str | None
    a_index: int | None
    # Set by weave(): the offsets, in the text it returns, of the brackets
    # it wrote from the engines (the page's own are not listed).
    wrote: list[int] = field(default_factory=list)
    # "start" or "end" when the gap is the page's leading or trailing edge.
    edge: str = ""
    # Set by weave(): how many marks of the page it left out as a run's own.
    dropped: int = 0
    # N5: the spans of the page's tables whose marks no model read
    # (unread_tables), and whether the character before the gap and the one
    # after it lie in an engine A block the punctuator never read (`bare`),
    # both set by cell_gap() where the gap is one whose marks the rule
    # writes; stretches() then writes a stretch of marks alone that lies in
    # one of them beside such a character, lists in `cells` the offsets (in
    # the text written) of the marks it wrote that N1 leaves, and counts in
    # `cell_lost` the marks of such stretches it could not write.
    tables: Sequence[tuple[int, int]] = ()
    bare: tuple[bool, bool] = (False, False)
    cells: list[int] = field(default_factory=list)
    cell_lost: int = 0


class PageRuns:
    """A page's text, the engines' bodies and their alignment, read once."""

    def __init__(self, pd: rr.PageData, folio_forms: set[str]):
        self.pd = pd
        self.scan = pd.scan
        self.text = pd.text
        self.align = ra.align_page(pd.text, pd.a_body, pd.b_body)
        self.s = self.align.sealed
        self.a = self.align.a
        self.b = self.align.b
        self.to_a = self.align.sealed_to_a
        self.to_b = self.align.sealed_to_b
        self.folio_forms = folio_forms
        # The folio whole, in each form (folio_forms holds every piece too).
        longest = max((len(form) for form in folio_forms), default=0)
        self.folio_whole = {form for form in folio_forms if len(form) == longest}
        self._block_of = rr.a_blocks_of(pd) if pd.a_blocks and pp.CJK(pd.a_body) else []
        # N5: the page's tables whose marks no model read from the image.
        self.tables = unread_tables(self)

    def span(self, k: int) -> tuple[int, int]:
        start = 0 if k == 0 else self.s.offsets[k - 1] + 1
        end = self.s.offsets[k] if k < len(self.s.offsets) else len(self.text)
        return start, end

    def _engine_gap(self, stream: ra.Stream, to: Sequence[int | None], k: int) -> tuple[str | None, int | None]:
        """What the engine holds in the page's gap K, when the page
        characters on both sides are aligned to adjacent characters of the
        engine (an edge: to the engine's first or last character)."""
        n = len(self.s.chars)
        if not stream.chars:
            return None, None
        if k == 0:
            j = to[0] if n else None
            if j != 0:
                return None, None
            return stream.text[:stream.offsets[0]], 0
        if k == n:
            j = to[n - 1]
            if j is None or j != len(stream.chars) - 1:
                return None, None
            return stream.text[stream.offsets[j] + 1:], j + 1
        i, j = to[k - 1], to[k]
        if i is None or j is None or j != i + 1:
            return None, None
        return stream.text[stream.offsets[i] + 1:stream.offsets[j]], j

    def gap(self, k: int) -> Gap:
        start, end = self.span(k)
        a_raw, ia = self._engine_gap(self.a, self.to_a, k)
        b_raw, _ = self._engine_gap(self.b, self.to_b, k)
        return Gap(k, start, end, tokens(self.text[start:end], "page", k == 0),
                   tokens(a_raw, "a", k == 0) if a_raw is not None else None,
                   tokens(b_raw, "b", k == 0) if b_raw is not None else None, a_raw, b_raw, ia,
                   edge="start" if k == 0 else "end" if k == len(self.s.chars) else "")

    def gaps(self) -> Iterable[Gap]:
        for k in range(len(self.s.chars) + 1):
            yield self.gap(k)

    def context(self, k: int, width: int = 4) -> tuple[str, str]:
        return self.s.chars[max(0, k - width):k], self.s.chars[k:k + width]

    def a_block(self, k: int) -> Mapping[str, Any] | None:
        """Engine A's block holding the engine character the page character
        K aligns to; None where K aligns to none or the blocks are not known."""
        j = self.to_a[k] if 0 <= k < len(self.to_a) else None
        if j is None or not self._block_of or j >= len(self._block_of):
            return None
        block = self._block_of[j]
        return self.pd.a_blocks[block] if 0 <= block < len(self.pd.a_blocks) else None

    def a_label(self, k: int) -> str | None:
        """Engine A's block label of the block holding the engine character
        the page character K aligns to."""
        block = self.a_block(k)
        return block.get("label") if block is not None else None

    def line_span(self, offset: int) -> tuple[int, int]:
        start = self.text.rfind("\n", 0, offset) + 1
        end = self.text.find("\n", offset)
        return start, (len(self.text) if end < 0 else end)


def table_spans(text: str) -> list[tuple[int, int]]:
    """The spans of TEXT's tables as the skill reads them
    (_tables.find_tables): a Markdown table from its label row and rule to
    its last row, an HTML table from its opening tag to its closing one.  A
    line that merely holds a pipe is no table."""
    return [(table.start, table.end) for table in _tables.find_tables(text)]


def unread_marks(record: Mapping[str, Any]) -> bool:
    """Whether phase 3 punctuated the page block by block (the seal's
    record), so that a block it gave no pass (an engine A table block,
    proofread_pages.FURNITURE_LABELS) holds engine A's marks, none, or the
    （） the structure pass's lock lets it add.  Not on a page punctuated
    whole (the seal's doubt `punctuation-whole-page`): there the formatter
    wrote the tables' marks from the page image, and an empty gap may be its
    reading, as in running text.  A seal with no `doubts` key is an older
    one that recorded none: phase 3 derives the whole-page doubt for it at
    read time (proofread_pages.rederive_doubts) and this stage does not, so
    the page is taken as read unless its punctuationPasses show the block
    passes (a page with passes was not punctuated whole).  A table rebuilt
    from its crop is set aside per table (unread_tables)."""
    doubts = record.get("doubts")
    if doubts is None:
        return bool(record.get("punctuationPasses"))
    return not any(isinstance(d, Mapping) and d.get("kind") == "punctuation-whole-page" for d in doubts)


def unread_tables(page: PageRuns) -> list[tuple[int, int]]:
    """N5: the spans of PAGE's tables whose marks no model read from the
    image - none on a page not punctuated block by block (unread_marks), and
    not a table that holds a character of a block the structure pass
    rebuilt from its crop (the seal's tablesRebuilt, outcome accepted: its
    block and the blocks of its region, by engine A's layout index): the
    rebuilt table holds the brackets and commas the model saw there, so an
    empty gap of it may be that reading.  The other tables of such a page
    are read as any (one rebuilt table used to switch the rule off for the
    whole page).  A rebuilt block that no table character aligns to names
    no table (a page character aligned to no block has no label either, and
    cell_gap keeps the rule off it)."""
    if not unread_marks(page.pd.record):
        return []
    spans = table_spans(page.text)
    rebuilt = {index for r in page.pd.record.get("tablesRebuilt") or [] if isinstance(r, Mapping)
               and r.get("outcome") == "accepted"
               for index in (r.get("block"), *(r.get("region") or [])) if isinstance(index, int)}
    if not rebuilt:
        return spans

    def of_rebuilt(k: int) -> bool:
        block = page.a_block(k)
        return block is not None and block.get("index") in rebuilt

    return [(start, end) for start, end in spans
            if not any(of_rebuilt(k) for k in range(bisect_left(page.s.offsets, start), bisect_left(page.s.offsets, end)))]


@dataclass
class Mask:
    """Per page: which characters of the text as it stands a model answer
    wrote, and the places where an answer took text away."""
    flags: dict[int, list[bool]]
    cuts: dict[int, list[int]]


def question_mask(ledger: re_.Ledger) -> Mask:
    """What the model's answers wrote and removed (the records that carry a
    question), on the text as it stands: a rule of this stage writes nowhere
    an answer did."""
    texts = dict(ledger.original)
    flags = {page: [False] * len(text) for page, text in texts.items()}
    cuts: dict[int, list[int]] = {page: [] for page in texts}
    for record in ledger.records:
        page = record["page"]
        text = texts[page]
        offset, before, after = record["offset"], record["before"], record["after"]
        if text[offset:offset + len(before)] != before:
            # Not the ledger's own history (a replay would have failed): mark
            # the whole page, so nothing is written on it.
            flags[page] = [True] * len(ledger.texts[page])
            continue
        texts[page] = text[:offset] + after + text[offset + len(before):]
        asked = bool(record.get("question"))
        flags[page] = flags[page][:offset] + [asked] * len(after) + flags[page][offset + len(before):]
        delta = len(after) - len(before)
        cuts[page] = [c if c <= offset else c + delta if c >= offset + len(before) else offset + len(after)
                      for c in cuts[page]]
        if asked and len(after) < len(before):
            kept = next((i for i in range(len(after)) if after[i] != before[i]), len(after))
            cuts[page].append(offset + kept)
    return Mask(flags, cuts)


def written_in(mask: Mask, page: int, start: int, end: int) -> bool:
    """Whether a model answer wrote a character of PAGE's text[START:END],
    or took text away there."""
    flags = mask.flags.get(page) or []
    return any(flags[start:min(end, len(flags))]) or any(start <= c <= end for c in mask.cuts.get(page) or ())


# --- weaving runs into a gap (N1, N3) ----------------------------------------------------

def line_figure(text: str) -> bool:
    """Whether TEXT begins with a figure of its own: one to four digits that
    end it or stand before a space (`18`, `18 Fernand Braudel`)."""
    return re.match(rf"[0-9\uff10-\uff19]{{1,{LINE_FIGURE_DIGITS}}}(?: |$)", text) is not None


def line_initial_figure(a_toks: Sequence[Token], run: Token, edge_start: bool = False) -> bool:
    """Whether RUN opens a line of engine A's text with a figure of its own
    (line_figure), after a break - or at the engine's text start when the
    gap is the page's leading edge - with nothing but opening brackets
    before it on the line: a footnote's or item's own number, which this
    stage never writes."""
    if not line_figure(run.raw):
        return False
    before = [t for t in a_toks if t.end <= run.start and t.kind not in (SPACE, MARKUP)]
    while before and before[-1].kind == MARK and before[-1].cls in OPEN_CLASSES:
        before.pop()
    if not before:
        return edge_start
    return before[-1].kind == BREAK


def note_like(a_toks: Sequence[Token]) -> bool:
    """Whether engine A's gap ends with a figure of one to three digits right
    after the mark that ends a sentence (and the bracket or quote closing
    it): the place of a note number, which the engines may have read as
    plain figures both."""
    items = [t for t in a_toks if t.kind not in (MARKUP,)]
    while items and items[-1].kind in (SPACE, BREAK):
        items.pop()
    if len(items) < 2 or items[-1].kind != RUN or not re.fullmatch(r"[0-9\uff10-\uff19]{1,3}", items[-1].raw):
        return False
    before = items[:-1]
    while before and before[-1].kind == MARK and before[-1].cls in CLOSE_CLASSES:
        before.pop()
    return bool(before) and before[-1].kind == MARK and before[-1].cls in ("stop", "question", "bang") \
        and before[-1].raw not in ".\uff0e"


def _carried(mark: Token, a_runs: Sequence[Token], a_marks: Sequence[Token], b_toks: Sequence[Token] | None) -> bool:
    """Whether MARK, a mark of the page with no counterpart among engine A's,
    is what is left of a run: a connector that one of the gap's runs itself
    holds (the hyphen of 119-140, the colon of 1989：2), and that engine B
    does not read as a mark of the gap either."""
    if mark.kind != MARK or mark.cls not in CONNECTOR_CLASSES:
        return False
    forms = _CLASSES.get(mark.cls, "")
    if not any(c in run.raw for run in a_runs for c in forms):
        return False
    count = sum(1 for t in a_marks if t.kind == MARK and t.cls == mark.cls)
    return b_toks is None or sum(1 for t in b_toks if t.kind == MARK and t.cls == mark.cls) <= count


def _match(a_marks: Sequence[Token], p_marks: Sequence[Token], a_runs: Sequence[Token], b_toks: Sequence[Token] | None,
           leftmost: bool = True) -> tuple[dict[int, int], set[int]] | None:
    """The page's marks matched to engine A's, in order: each to the first
    (LEFTMOST) or last engine mark still free of its own class - of its
    coarse class (any opening, any closing bracket) only where engine A
    holds none of the page's class in the gap.  Returns engine mark ->
    page mark and the page marks set aside as a run's own (_carried); None
    when another page mark has no counterpart."""
    matched: dict[int, int] = {}
    remnants: set[int] = set()
    free = list(range(len(a_marks))) if leftmost else list(range(len(a_marks) - 1, -1, -1))
    for pi in (range(len(p_marks)) if leftmost else range(len(p_marks) - 1, -1, -1)):
        pt = p_marks[pi]
        exact = any(t.key == pt.key for t in a_marks)
        j = next((j for j in free if (a_marks[j].key == pt.key if exact else coarse(a_marks[j].key) == coarse(pt.key))),
                 None)
        if j is not None:
            matched[j] = pi
            free = free[free.index(j) + 1:]
        elif _carried(pt, a_runs, a_marks, b_toks):
            remnants.add(pi)
        else:
            return None
    return matched, remnants


def weave(gap: Gap) -> tuple[str, str, list[str]] | tuple[None, str, list[str]]:
    """The gap's new text with the engines' agreed runs woven in: (text,
    tier, runs), or (None, why, runs) when the gap has no clean place.  The
    caller has checked that engine A and engine B agree on the gap's runs
    and marks and that the page holds no run there.  Sets gap.wrote (the
    brackets written from the engines) and gap.dropped (the page's marks
    left out as a run's own)."""
    a_toks, p_toks = gap.a or [], gap.page
    a_runs = runs_of(a_toks)
    a_marks = [t for t in a_toks if t.kind in (MARK, CELL, ROW)]
    p_marks = [t for t in p_toks if t.kind in (MARK, CELL, ROW)]
    names = [t.raw for t in a_runs]
    gap.wrote, gap.dropped, gap.cells, gap.cell_lost = [], 0, [], 0
    if any(t.kind in (MARKER, OTHER) for t in a_toks) or any(t.kind in (MARKER, OTHER) for t in p_toks):
        return None, "a note marker or unknown markup stands in the gap", names
    if any(line_initial_figure(a_toks, run, gap.k == 0) for run in a_runs):
        return None, "a figure opens a line in engine A", names
    if note_like(a_toks):
        return None, "a short figure right after a sentence's end may be a note number", names
    a_lines = _lines_of(a_toks)
    if len(a_lines) > 1 and (any(runs_of(line) for line in a_lines[1:-1])
                             or (gap.edge == "end" and any(runs_of(line) for line in a_lines[1:]))
                             or (gap.edge == "start" and any(runs_of(line) for line in a_lines[:-1]))):
        return None, "a run stands on a line of its own in engine A", names
    found = _match(a_marks, p_marks, a_runs, gap.b)
    if found is None:
        return None, "the page's marks are not the engines'", names
    matched, remnants = found
    tier = "T1" if len(matched) == len(a_marks) else "T2"
    if tier == "T2":
        if remnants:
            return None, "the page's marks are not the engines'", names
        new, why, names = stretches(gap, a_marks, p_marks, matched, names)
        # The place is unique when the page's marks matched from the other
        # end give the same text.
        other = _match(a_marks, p_marks, a_runs, gap.b, leftmost=False)
        if new is not None and other is not None and other[0] != matched:
            wrote, cells, lost = list(gap.wrote), list(gap.cells), gap.cell_lost
            again = stretches(gap, a_marks, p_marks, other[0], names)[0]
            gap.wrote, gap.cells, gap.cell_lost = wrote, cells, lost
            if again != new:
                return None, "the run's place among the page's marks is not unique", names
        return new, why, names
    # T1: every mark of the engines stands on the page.  Each run goes after
    # the engine mark before it (its page match) or before the one after it;
    # on the page side of a break where engine A breaks the line beside it.
    if not a_marks and any(t.kind in (BREAK, STRUCT) for t in p_toks) and not any(t.kind == BREAK for t in a_toks):
        return None, "the run's place among the page's marks is not unique", names
    # A connector the page holds as a run's own stays in the page's form: the
    # run is written with it in place of engine A's glyph for it.
    spelled = [run.raw for run in a_runs]
    done = [0] * len(spelled)
    for pi in sorted(remnants):
        forms = _CLASSES.get(p_marks[pi].cls, "")
        for n, text in enumerate(spelled):
            hit = next((i for i in range(done[n], len(text)) if text[i] in forms), None)
            if hit is not None:
                spelled[n] = text[:hit] + p_marks[pi].raw + text[hit + 1:]
                done[n] = hit + len(p_marks[pi].raw)
                break
    positions: list[tuple[int, str]] = []   # (offset in the gap text, run text)
    for run, run_text in zip(a_runs, spelled):
        prev = max((idx for idx, t in enumerate(a_marks) if t.end <= run.start), default=None)
        nxt = min((idx for idx, t in enumerate(a_marks) if t.start >= run.end), default=None)
        between_prev = [t for t in a_toks if (prev is None or t.start >= a_marks[prev].end) and t.end <= run.start]
        break_before = any(t.kind == BREAK for t in between_prev)
        if prev is not None:
            anchor = p_marks[matched[prev]]
            at = anchor.end
            if break_before:
                # Past the page's break and the structure that opens the next line.
                for t in p_toks:
                    if t.start >= anchor.end and t.kind in (SPACE, BREAK, STRUCT):
                        at = t.end
                    elif t.start >= anchor.end:
                        break
        elif nxt is not None:
            anchor = p_marks[matched[nxt]]
            between_next = [t for t in a_toks if t.start >= run.end and t.end <= a_marks[nxt].start]
            # Before the anchor: before the page's break too where engine A
            # breaks the line after the run, else after it, before its spaces.
            apart = (SPACE, BREAK, STRUCT) if any(t.kind == BREAK for t in between_next) else (SPACE,)
            at = anchor.start
            for t in reversed(p_toks):
                if t.end <= anchor.start and t.kind in apart:
                    at = t.start
                elif t.end <= anchor.start:
                    break
        else:
            at = 0
            if break_before:
                for t in p_toks:
                    if t.kind in (SPACE, BREAK, STRUCT):
                        at = t.end
                    else:
                        break
        positions.append((at, run_text))
    if len({at for at, _ in positions}) != len(positions):
        if remnants:
            return None, "two runs share one place on the page", names
        # Two runs with no mark between them: written as engine A has them.
        new, why, names = stretches(gap, a_marks, p_marks, matched, names)
        return new, ("T1" if new is not None else why), names
    # Build the text: the page's tokens, the runs' own marks dropped, runs
    # inserted.
    drop = {p_marks[pi].start for pi in remnants}
    inserts = dict(positions)
    gap_text = "".join(t.raw for t in p_toks)
    out: list[str] = []
    for offset in range(len(gap_text) + 1):
        if offset in inserts:
            run_text = inserts[offset]
            # A space between a run and a table cell's pipe.
            before_c = out[-1] if out else ""
            after_c = gap_text[offset:offset + 1]
            if before_c == "|" and not run_text.startswith(" "):
                out.append(" ")
            out.append(run_text)
            if after_c == "|" and not run_text.endswith(" "):
                out.append(" ")
        if offset < len(gap_text):
            if offset in drop:
                continue
            out.append(gap_text[offset])
    gap.dropped = len(remnants)
    return "".join(out), tier, names


def written(part: Sequence[Token], full_round: bool = False) -> tuple[str, list[int]]:
    """A stretch of engine A's gap as this stage writes it, and the offsets
    of the brackets in it: each run as spelled, each mark as engine A wrote
    it - an ASCII mark in its ordinary full-width form (rr.NORM) unless it
    stands in Western text: beside a run of Latin letters, or, a bracket,
    inside a stretch that holds a run of several Latin words (and not where
    the page writes the gap's round brackets full-width, FULL_ROUND: a pair
    keeps one form).  A space stands between two runs, and where engine A
    has one between two tokens of Western text."""
    items = [t for t in part if t.kind in (RUN, MARK)]
    latin = [t.kind == RUN and re.search(rf"[{LATIN}]", t.raw) is not None for t in items]
    prose = any(t.kind == RUN and re.search(rf"[{LATIN}] +[{LATIN}]", t.raw) for t in items)
    forms: list[str] = []
    western: list[bool] = []
    for i, t in enumerate(items):
        if t.kind == RUN:
            forms.append(t.raw)
            western.append(latin[i])
            continue
        raw = t.raw
        ascii_mark = len(raw) == 1 and ord(raw) < 128
        inner = 0 < i < len(items) - 1
        beside = (i > 0 and latin[i - 1]) or (i + 1 < len(items) and latin[i + 1])
        if ascii_mark and raw in "()[]":
            keep = prose and inner and not (full_round and raw in "()")
        else:
            keep = ascii_mark and (beside or (prose and inner))
        if ascii_mark and not keep:
            raw = raw.translate(rr.NORM)
        forms.append(raw)
        western.append(ascii_mark and keep)
    out: list[str] = []
    brackets: list[int] = []
    at = 0
    for i, t in enumerate(items):
        if i:
            previous = items[i - 1]
            spaced = any(x.kind == SPACE for x in part if previous.end <= x.start and x.end <= t.start)
            if (previous.kind == RUN and t.kind == RUN) or (spaced and western[i - 1] and western[i]):
                out.append(" ")
                at += 1
        if t.kind == MARK and (MARK_CLASS.get(forms[i]) in OPEN_CLASSES or MARK_CLASS.get(forms[i]) in CLOSE_CLASSES):
            brackets.append(at)
        out.append(forms[i])
        at += len(forms[i])
    return "".join(out), brackets


def _stretch(a_part: Sequence[Token], p_part: Sequence[Token], edge: str = "",
             full_round: bool = False, whole: bool = False) -> tuple[str, list[int], list[int]] | None:
    """One stretch of a gap between two marks the page shares with the
    engines (or the gap's edge): the page's spaces, breaks and structure,
    with what engine A holds on each of its lines there that has a run -
    the run and the marks beside it on that line; a line of marks alone is
    left as the page has it, unless the stretch lies in a table cell (N5,
    WHOLE): its marks are written too, and the offsets of those marks (the
    ones N1 leaves) are the third item returned, after the text and the
    offsets of its brackets.  Before the page's line break goes engine A's
    line before its own, after it the line that follows; so too about the
    page's spaces where a table cell holds nothing else there and engine A
    breaks the line (the print wraps in the cell: the second title's
    opening bracket goes after the space, not before it - a made-up page,
    check_repair_runs cell_checks), and where engine A has a line between
    them with marks of its own the stretch is left as the page has it (none
    of the page's spaces is that line's).  None when a run's side of the
    page's break is not given (in a table cell, a mark's), and at a page's
    EDGE ("start", "end") when engine A has the run on a line of its own
    beyond the page's first or last line."""
    p_raw = "".join(t.raw for t in p_part)
    lines = _lines_of(a_part)

    def wanted(line: Sequence[Token]) -> bool:
        return bool(runs_of(line)) or (whole and any(t.kind == MARK for t in line))

    def cell_marks(line: Sequence[Token], text: str) -> list[int]:
        # The marks N1 leaves: those of a line with no run (written() spells
        # such a line as its marks alone).
        if runs_of(line) or not whole:
            return []
        return [t.start for t in tokens(text, "page") if t.kind == MARK]

    if not any(wanted(line) for line in lines):
        return p_raw, [], []
    if len(lines) > 1 and edge == "end" and any(runs_of(line) for line in lines[1:]):
        return None
    if len(lines) > 1 and edge == "start" and any(runs_of(line) for line in lines[:-1]):
        return None
    spaces_only = whole and bool(p_part) and all(t.kind == SPACE for t in p_part)
    if not any(t.kind in (BREAK, STRUCT) for t in p_part) and not (spaces_only and len(lines) > 1):
        out = ""
        brackets: list[int] = []
        cells: list[int] = []
        for line in lines:
            if not wanted(line):
                continue
            text, at = written(line, full_round)
            if out and text and re.match(rf"[{ALNUM}]", text) and re.search(rf"[{ALNUM}]$", out):
                out += " "
            brackets.extend(len(out) + offset for offset in at)
            cells.extend(len(out) + offset for offset in cell_marks(line, text))
            out += text
        return out + p_raw, brackets, cells
    if any(wanted(line) for line in lines[1:-1]):
        return (p_raw, [], []) if spaces_only else None
    if len(lines) < 2:
        return None
    head, head_brackets = written(lines[0], full_round) if wanted(lines[0]) else ("", [])
    tail, tail_brackets = written(lines[-1], full_round) if wanted(lines[-1]) else ("", [])
    shift = len(head) + len(p_raw)
    return (head + p_raw + tail, head_brackets + [shift + at for at in tail_brackets],
            cell_marks(lines[0], head) + [shift + at for at in cell_marks(lines[-1], tail)])


def stretches(gap: Gap, a_marks: Sequence[Token], p_marks: Sequence[Token], matched: Mapping[int, int],
              names: list[str]) -> tuple[str | None, str, list[str]]:
    """T2: every mark of the page is one of the engines', and the engines
    hold more (the punctuator read the page without its runs, and left out
    marks that stand beside them).  The page's marks stay; a stretch between
    two of them that holds a run becomes the engines' - runs and marks in
    engine A's order (_stretch, written) - and a stretch of marks alone is
    left as the page has it - but written where the stretch lies in a table
    whose marks N5 writes (gap.tables, gap.bare, _in_table; gap.cells lists
    the offsets of those marks, gap.cell_lost counts the ones of such a
    stretch that could not be written).  The brackets written are listed in
    gap.wrote (text_runs withholds one that finds no partner on its line)."""
    a_toks, p_toks = gap.a or [], gap.page
    if any(t.kind in (CELL, ROW) and j not in matched for j, t in enumerate(a_marks)):
        return None, "the page's marks are not the engines'", names
    pairs = sorted(matched.items())
    full_round = any(t.kind == MARK and t.raw in "\uff08\uff09" for t in p_marks)
    out: list[str] = []
    wrote: list[int] = []
    cells: list[int] = []
    a_at = p_at = 0
    size = lost = 0
    for n in range(len(pairs) + 1):
        a_mark = a_marks[pairs[n][0]] if n < len(pairs) else None
        p_mark = p_marks[pairs[n][1]] if n < len(pairs) else None
        a_part = [t for t in a_toks if t.start >= a_at and (a_mark is None or t.end <= a_mark.start)]
        p_part = [t for t in p_toks if t.start >= p_at and (p_mark is None or t.end <= p_mark.start)]
        edge = gap.edge if (gap.edge == "start" and n == 0) or (gap.edge == "end" and n == len(pairs)) else ""
        whole = _in_table(gap, n == 0, n == len(pairs), p_at)
        # The marks of the stretch that N5 is to write: those of engine A's
        # lines there with no run.
        found = sum(1 for line in _lines_of(a_part) if not runs_of(line) for t in line if t.kind == MARK) if whole else 0
        piece = _stretch(a_part, p_part, edge, full_round, whole)
        if piece is None and whole:
            # The marks' side of the page's line break is not given: the
            # stretch as N1 alone writes it.
            piece = _stretch(a_part, p_part, edge, full_round)
        if piece is None:
            return None, "the run's place among the page's marks is not unique", names
        text, brackets, marks = piece
        lost += found - len(marks)
        if text.strip() and text != "".join(t.raw for t in p_part):
            # A space between what is written and a table cell's pipe.
            if out and out[-1].endswith("|") and not text.startswith(" "):
                text, brackets, marks = " " + text, [at + 1 for at in brackets], [at + 1 for at in marks]
            if p_mark is not None and p_mark.raw.startswith("|") and not text.endswith(" "):
                text += " "
        wrote.extend(size + at for at in brackets)
        cells.extend(size + at for at in marks)
        out.append(text)
        size += len(text)
        if a_mark is not None and p_mark is not None:
            out.append(p_mark.raw)
            size += len(p_mark.raw)
            a_at, p_at = a_mark.end, p_mark.end
    gap.wrote, gap.cells, gap.cell_lost = wrote, cells, lost
    return "".join(out), "T2", names


def _in_table(gap: Gap, first: bool, last: bool, at: int) -> bool:
    """N5: whether a stretch of GAP lies in one of the page's tables
    (gap.tables; none where the rule does not hold for the gap) beside a
    character of a block the punctuator never read (gap.bare): the gap's
    FIRST stretch with the character before the gap, its LAST with the
    character after it - at a page's edge there is none, and what stands
    beyond the page's first or last character is not a cell's - and a
    stretch between two cell boundaries where it stands (AT, its offset in
    the gap's text), when both characters are such."""
    if not gap.tables:
        return False

    def inside(offset: int) -> bool:
        return any(start <= offset < end for start, end in gap.tables)

    before, after = gap.bare
    if first and (gap.edge == "start" or not inside(gap.start - 1) or not before):
        return False
    if last and (gap.edge == "end" or not inside(gap.end) or not after):
        return False
    return first or last or (inside(gap.start + at) and before and after)


# Marks a renderer reads as markup, not print: a table's note sign or
# emphasis (`*`, `_`, a backtick, `#`), a link or a strike (`[`, `]`, `~`),
# a tag or an escape (`<`, `>`, a backslash).
RENDERER_MARKS = frozenset("*_`#~[]\\<>")


def unprintable(text: str) -> bool:
    """Whether TEXT holds a character that prints nothing (Unicode category
    Z: a space of some width; C: a control, a format character such as a
    zero-width space)."""
    import unicodedata
    return any(unicodedata.category(c)[0] in "ZC" for c in text)


def cell_gap(page: PageRuns, gap: Gap) -> bool:
    """N5: whether GAP is one whose marks the rule writes - the page has
    tables whose marks no model read (page.tables) and holds in the gap
    nothing but cell boundaries, spaces and breaks; a character beside the
    gap lies in an engine A block the punctuator never read (its label in
    proofread_pages.FURNITURE_LABELS: a table block; gap.bare, per side -
    the structure pass builds a page table from a punctuated text block too,
    and an empty gap of that table may be the punctuator's reading: scan 606
    of the 609-page book, whose 366 table characters are in a `text` block
    with a pass of 11 marks); both engines hold the same tokens there,
    engine A a mark among them, and neither a note marker or unknown markup
    nor a star or a character a renderer reads as markup (RENDERER_MARKS)
    nor one that prints nothing (unprintable).  Sets gap.tables and
    gap.bare, by which stretches() writes the marks of the stretches that
    lie in a table."""
    if not page.tables or gap.a is None or gap.b is None:
        return False
    if any(t.kind not in (CELL, ROW, SPACE, BREAK, STRUCT) for t in gap.page):
        return False
    marks = [t for t in gap.a if t.kind == MARK]
    if not marks or any(_markup(t) or t.cls == "star" or set(t.raw) & RENDERER_MARKS or unprintable(t.raw) for t in marks) \
            or any(t.kind in (MARKER, OTHER) for t in gap.a + gap.b) or not agree(gap.a, gap.b):
        return False

    def bare(k: int) -> bool:
        return 0 <= k < len(page.s.chars) and page.a_label(k) in pp.FURNITURE_LABELS

    gap.bare = (bare(gap.k - 1), bare(gap.k))
    if not any(gap.bare):
        return False
    gap.tables = page.tables
    return True


CELL_BOUNDARY_RE = re.compile(r"\||</t[dh]>", re.I)


def brackets_of(toks: Sequence[Token]) -> int:
    """How many brackets (marks of an opening or closing class) TOKS hold."""
    return sum(1 for t in toks if t.kind == MARK and (t.cls in OPEN_CLASSES or t.cls in CLOSE_CLASSES))


def unpaired(text: str, edits: Sequence[re_.Edit], wrote: dict[int, list[int]],
             lacking: Sequence[tuple[int, int, int]] = (), cells: dict[int, list[int]] | None = None) -> None:
    """Withhold each bracket this stage would write that has no partner on
    its line once all of the page's EDITS stand (WROTE: per edit, by id, the
    offsets in its text of the brackets written from the engines): a
    bracket whose partner the page lacks would open or close nothing.  Two
    brackets with a cell boundary between them (a pipe, `</td>`) are no
    pair, nor are two whose span encloses a gap of LACKING (per gap of the
    page: its span in TEXT and how many brackets engine A holds there) in
    which the page with its edits holds fewer brackets than engine A: where
    the engines differ between two titles of a cell, or the page breaks the
    line where engine A does not, the gap between the titles is not written,
    and the outer brackets would show one title where the print has two
    (made-up pages, check_repair_runs cell_checks; on the 609-page book no
    pair of the stage's output enclosed such a gap, measured 2026-10-02).
    Both brackets of such a pair are withheld where they are this stage's.
    The edit keeps the rest and names what was withheld; CELLS (per edit,
    the offsets of the marks N5 writes) follows its text."""
    if not any(wrote.get(id(e)) for e in edits):
        return
    ordered = sorted(edits, key=lambda e: (e.start, e.end))

    def shifted(offset: int, within: bool) -> int:
        # The offset in the trial of a page offset: past the edits before it
        # (WITHIN: an edit that ends there is inside the span measured).
        return offset + sum(len(e.after) - (e.end - e.start) for e in ordered
                            if (e.end <= offset if within else e.start < offset))

    while True:
        pieces: list[str] = []
        ours: dict[int, tuple[re_.Edit, int]] = {}
        at = size = 0
        for edit in ordered:
            pieces.append(text[at:edit.start])
            size += edit.start - at
            for offset in wrote.get(id(edit), ()):
                ours[size + offset] = (edit, offset)
            pieces.append(edit.after)
            size += len(edit.after)
            at = edit.end
        pieces.append(text[at:])
        trial = "".join(pieces)
        gaps = []
        for start, end, held in lacking:
            span = (shifted(start, False), shifted(end, True))
            if brackets_of(tokens(trial[span[0]:span[1]], "page")) < held:
                gaps.append(span)
        alone: list[int] = []
        start = 0
        for line in trial.split("\n"):
            stack: list[tuple[str, int]] = []
            i = 0
            while i < len(line):
                boundary = CELL_BOUNDARY_RE.match(line, i)
                if boundary:
                    alone.extend(at_ for _, at_ in stack)
                    stack.clear()
                    i = boundary.end()
                    continue
                c = line[i]
                cls = MARK_CLASS.get(c)
                if cls in OPEN_CLASSES:
                    stack.append((cls, start + i))
                elif cls in CLOSE_CLASSES:
                    want = "open-" + cls[len("close-"):]
                    j = next((n for n in range(len(stack) - 1, -1, -1) if stack[n][0] == want), None)
                    if j is None:
                        alone.append(start + i)
                    else:
                        alone.extend(at_ for _, at_ in stack[j + 1:])
                        opened = stack[j][1]
                        if any(opened < gap_start and gap_end <= start + i for gap_start, gap_end in gaps):
                            alone.extend((opened, start + i))
                        del stack[j:]
                i += 1
            alone.extend(at_ for _, at_ in stack)
            start += len(line) + 1
        drop: dict[int, list[int]] = {}
        for position in alone:
            if position in ours:
                edit, offset = ours[position]
                drop.setdefault(id(edit), []).append(offset)
        if not drop:
            return
        for edit in edits:
            offsets = sorted(set(drop.get(id(edit), ())))
            if not offsets:
                continue
            withheld = [edit.after[o] for o in offsets]
            after = "".join(c for o, c in enumerate(edit.after) if o not in offsets)
            for listed in (wrote, cells or {}):
                if id(edit) in listed:
                    kept = [o for o in listed[id(edit)] if o not in offsets]
                    listed[id(edit)] = [o - sum(1 for x in offsets if x < o) for o in kept]
            edit.after = after
            edit.evidence = {**edit.evidence, "withheld": list(edit.evidence.get("withheld") or []) + withheld}


def permuted(gap: Gap) -> str | None:
    """N3: the page's marks are the engines' marks in another order, and the
    page holds no run, no break and no structure: the gap in engine A's
    order - each mark a mark of the page, of its own class or, failing that,
    of its coarse class (the page's own shapes stay), the runs as engine A
    spells them, a space between two runs.  None when the page's marks are
    not a permutation."""
    a_toks, p_toks = gap.a or [], gap.page
    if any(t.kind in (BREAK, STRUCT, CELL, ROW, MARKER, OTHER) or _markup(t) for t in p_toks) \
            or any(t.kind in (MARKER, OTHER, CELL, ROW) for t in a_toks):
        return None
    a_marks = [t for t in a_toks if t.kind == MARK]
    p_marks = [t for t in p_toks if t.kind == MARK]
    if not a_marks or sorted(coarse(t.key) for t in a_marks) != sorted(coarse(t.key) for t in p_marks):
        return None
    if [coarse(t.key) for t in a_marks] == [coarse(t.key) for t in p_marks]:
        return None
    left = list(p_marks)
    glyph: dict[int, str] = {}
    for exact in (True, False):
        for t in a_marks:
            if id(t) in glyph:
                continue
            k = next((i for i, pt in enumerate(left) if (pt.key == t.key if exact else coarse(pt.key) == coarse(t.key))),
                     None)
            if k is not None:
                glyph[id(t)] = left.pop(k).raw
    out: list[str] = []
    after_run = False
    for t in a_toks:
        if t.kind == RUN:
            out.append((" " if after_run else "") + t.raw)
            after_run = True
        elif t.kind == MARK:
            out.append(glyph[id(t)])
            after_run = False
    return "".join(out)


# --- whole lines of no CJK character (N2) ------------------------------------------------

def _lines_of(toks: Sequence[Token]) -> list[list[Token]]:
    """TOKS cut at the line breaks."""
    segments: list[list[Token]] = [[]]
    for t in toks:
        if t.kind == BREAK:
            segments.append([])
        else:
            segments[-1].append(t)
    return segments


def text_lines(a_toks: Sequence[Token]) -> list[list[Token]]:
    """The segments of engine A's gap between breaks that hold a text run of
    letters and at least six letters or figures in all: whole lines of
    Western text (an entry of a bibliography, an English footnote)."""
    segments = _lines_of(a_toks)
    out = []
    # The first and last segments share a line with the characters on either
    # side of the gap: they are woven, not inserted whole.
    for seg in segments[1:-1]:
        runs = runs_of(seg)
        letters = sum(len(re.findall(rf"[{LATIN}]", t.raw)) for t in runs)
        figures = sum(len(re.findall(rf"[{ALNUM}]", t.raw)) for t in runs)
        if runs and letters >= 3 and figures >= 6 and not any(t.kind in (CELL, ROW, MARKER, OTHER) for t in seg):
            out.append(seg)
    return out


def paragraphs(lines: Sequence[Sequence[Token]], b_toks: Sequence[Token]) -> list[str]:
    """The whole LINES of engine A as the paragraphs written: engine A cuts
    a line where the print wraps it, so consecutive lines that engine B
    reads as one line are one paragraph, joined by a space; where engine
    B's lines do not say (they do not add up to engine A's), each line is
    its own."""
    own = [line_text(seg) for seg in lines]
    out: list[str] = []
    at = 0
    for b_line in text_lines(b_toks):
        want = fused(b_line)
        taken: list[Token] = []
        start = at
        while at < len(lines) and len(fused(taken)) < len(want):
            taken.extend(lines[at])
            at += 1
        if fused(taken) != want:
            return own
        out.append(" ".join(own[start:at]))
    return out if at == len(lines) else own


def line_text(seg: Sequence[Token]) -> str:
    text = "".join(" " if t.kind == SPACE else "" if t.kind == MARKUP else t.raw for t in seg)
    return re.sub(r"[ \t]+", " ", text).strip()


# --- the first answers of retried punctuation passes (R1) --------------------------------------

COUNT_REFUSAL = re.compile(r"\d+ (?:places marked|marks written) but \d+ counted")


def retry_passes(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The sealed punctuation passes whose kept retry followed a first answer
    refused on the count, with the first answer whole."""
    out = []
    for n, p in enumerate(record.get("punctuationPasses") or []):
        if not isinstance(p, dict) or not p.get("ok"):
            continue
        answer = p.get("firstAnswer")
        if not isinstance(answer, str) or not answer or len(answer) >= 2000:
            continue
        if not COUNT_REFUSAL.search(str(p.get("reason") or "")):
            continue
        out.append({"index": n, **p})
    return out


def _lead_part(toks: Sequence[Token]) -> list[Token]:
    """The tokens after the last break or structure (a line's own lead)."""
    last = max((i for i, t in enumerate(toks) if t.kind in (BREAK, STRUCT)), default=-1)
    return list(toks[last + 1:])


def _trail_part(toks: Sequence[Token]) -> list[Token]:
    """The tokens before the first break or structure (a line's own tail)."""
    first = next((i for i, t in enumerate(toks) if t.kind in (BREAK, STRUCT, CELL, ROW)), len(toks))
    return list(toks[:first])


# --- the stage -----------------------------------------------------------------------------

@dataclass
class Setting:
    book: Any
    model: Mapping[str, Any]
    facts: rr.BookFacts
    order: list[int]
    texts: Mapping[int, str]
    mask: Mask
    folio_forms: dict[int, set[str]] = field(default_factory=dict)

    def page(self, scan: int, text: str | None = None) -> PageRuns:
        """SCAN as the stage reads it: its text as it stands, or TEXT."""
        pd = rr.page_data(self.book, self.model, scan, self.texts[scan] if text is None else text)
        if scan not in self.folio_forms:
            import _book_lint as lint
            self.folio_forms[scan] = lint.folio_forms(pd.entry.get("folio"))
        return PageRuns(pd, self.folio_forms[scan])


TITLE_LABELS = ("doc_title", "paragraph_title", "title", "abstract", "figure_title")


def unit_levels(records: Sequence[Mapping[str, Any]]) -> dict[int, int]:
    """Sealed heading level -> the level the levels stage gave the book's
    unit titles sealed at that level, where it gave them all one."""
    seen: dict[int, set[int]] = {}
    for record in records:
        evidence = record.get("evidence") or {}
        if record.get("stage") == "levels" and evidence.get("kind") == "unit" \
                and re.fullmatch(r"#{1,6}", record["before"]) and re.fullmatch(r"#{1,6}", record["after"]):
            seen.setdefault(len(record["before"]), set()).add(len(record["after"]))
    return {level: next(iter(to)) for level, to in seen.items() if len(to) == 1}


def s11_undone(setting: Setting, records: Sequence[Mapping[str, Any]], plan: rr.Plan) -> None:
    """N4 over the pages: each S11 entry edit still standing on its page as
    a whole line, undone where the engines contradict it."""
    by_page: dict[int, list[Mapping[str, Any]]] = {}
    for record in records:
        if record.get("rule") == "S11" and (record.get("evidence") or {}).get("kind") == "entry":
            by_page.setdefault(record["page"], []).append(record)
    levels = unit_levels(records)
    for scan in setting.order:
        if scan not in by_page:
            continue
        page = setting.page(scan)
        text = page.text
        lines: list[tuple[int, int, str]] = []
        at = 0
        for line in text.split("\n"):
            lines.append((at, at + len(line), line))
            at += len(line) + 1
        # A record's line is found by its text: the lines of one text go with
        # the records that wrote it, in order, when there are as many.
        written_by: dict[str, list[Mapping[str, Any]]] = {}
        for record in by_page[scan]:
            written_by.setdefault(record["after"], []).append(record)
        for after, group in written_by.items():
            found = [(start, end) for start, end, line in lines if line == after]
            if len(found) != len(group) or "\n" in after:
                continue
            for record, (start, end) in zip(group, found):
                before = record["before"]
                if "\n" in before:
                    continue
                ks = list(range(bisect_left(page.s.offsets, start), bisect_left(page.s.offsets, end)))
                if not ks:
                    continue
                k0 = ks[0]
                ia, ib = page.to_a[k0], page.to_b[k0]
                a_lead = page.a.gaps[ia] if ia is not None else None
                b_lead = page.b.gaps[ib] if ib is not None else None
                both = "both engines read" if b_lead is not None else "engine A reads"
                new = None
                why = None
                number = (record.get("evidence") or {}).get("number")
                m = re.match(r"^([0-9]{1,3})([.\uff0e,\uff0c\u3002\u3001]?)[ \t]+", after)
                if m and number is not None and int(m.group(1)) == number:
                    digits = m.group(1)
                    if _ends_line_before(a_lead, digits, ia == 0) \
                            and (b_lead is None or _ends_line_before(b_lead, digits, ib == 0)):
                        # The number goes only where N1 will write it at the
                        # end of the line before: it is moved, never lost.
                        candidate = after[m.end():]
                        if _lands(setting, scan, text[:start] + candidate + text[end:], start, digits):
                            new = candidate
                            why = f"{both} the number at the end of the line before, none at this line's head"
                        else:
                            plan.doubts.append(("run-no-place", scan, (
                                f"a contents number at the head of its line that {both[:-5]} read at the end of the line "
                                f"before, left where it is (no clean place for it there): {show(after, 40)}")[:220],
                                {"runs": [digits]}))
                            continue
                if new is None:
                    d = next((i for i in range(min(len(before), len(after))) if before[i] != after[i]), None)
                    if d is not None and len(before) == len(after) + 1 and before[:d] + before[d + 1:] == after \
                            and before[d] in rs.OPENERS and _opens(a_lead, b_lead, before[d]):
                        new = before
                        why = f"{both} the bracket opening the line"
                if new is None:
                    # The bracket dropped with the line's list marker, or with
                    # the spaces that ended the line: the bracket alone is put
                    # back.
                    lead = STRUCT_RE.match(before)
                    core = before[lead.end() if lead else 0:].rstrip()
                    if core[:1] in rs.OPENERS and core[1:] == after.rstrip() and _opens(a_lead, b_lead, core[0]):
                        new = core[0] + after
                        why = f"{both} the bracket opening the line"
                if new is None:
                    hm = rs.HEADING.match(before)
                    if hm and after.strip() == before[hm.end():].strip():
                        label = page.a_label(k0)
                        a_title = label in TITLE_LABELS
                        b_heading = b_lead is not None and re.search(r"#{1,6}[ \t]+$", b_lead) is not None
                        if a_title or b_heading:
                            # At the level the levels stage gave the unit
                            # titles sealed at this one; the headings that
                            # open the book (none stands before them: its
                            # title page) keep the level they were sealed at.
                            level = len(before) - len(before.lstrip("#"))
                            opens = not any(rs.HEADING.match(line) for _, line_end, line in lines if line_end <= start) \
                                and not any(rs.HEADING.match(line) for earlier in setting.order[:setting.order.index(scan)]
                                            for line in setting.texts[earlier].split("\n"))
                            new = "#" * (level if opens else levels.get(level, level)) + before[level:]
                            why = " and ".join(reason for reason, holds in (
                                (f"engine A labels the block {label!r}", a_title),
                                ("engine B writes a heading there", b_heading)) if holds)
                if new is None or new == after:
                    continue
                plan.edits.append(re_.Edit(scan, start, end, new, rule="N4", evidence={
                    "before": after, "undoes": record.get("id"), "why": why,
                    "engineA": show(a_lead or "", 80), "engineB": show(b_lead or "", 80)}))


def _lands(setting: Setting, scan: int, trial: str, start: int, digits: str) -> bool:
    """Whether, on SCAN's text TRIAL (a contents number taken from the head
    of the line at START), the gap before that line holds DIGITS already,
    or N1 writes them there."""
    page = setting.page(scan, trial)
    gap = page.gap(bisect_left(page.s.offsets, start))
    if digits in [t.raw.translate(RUN_FOLD) for t in runs_of(gap.page)]:
        return True
    edits = _page_runs(setting, page, rr.Plan(), inside=(start - 1, start))
    return any(digits in [str(name).translate(RUN_FOLD) for name in (edit.evidence.get("runs") or [])]
               and not written_in(setting.mask, scan, edit.start, min(edit.end, start)) for edit in edits)


def _ends_line_before(lead: str | None, digits: str, first: bool) -> bool:
    """Whether LEAD - an engine's text between the character before a line
    and the line's first character (FIRST: there is none before, the lead
    opens the engine's text) - holds DIGITS at the end of the line before,
    after other print of that line, and no figure at this line's head: the
    page number that ends the entry before.  A number on a line of its own
    (an entry's number printed above or beside its title) is not that."""
    if lead is None or re.search(r"\n[ \t#*>-]*[0-9]", lead):
        return False
    m = re.search(rf"(?<![0-9]){re.escape(digits)}[ \t]*\n[ \t#*>-]*$", lead)
    if not m:
        return False
    before = lead[:m.start()]
    return not rs.markup_only(before.rsplit("\n", 1)[-1]) or ("\n" not in before and not first)


def _opens(a_lead: str | None, b_lead: str | None, bracket: str) -> bool:
    """Whether engine A reads BRACKET's class opening the line (after its
    last line break before the line's first character), and engine B too
    where it is aligned there."""
    cls = MARK_CLASS.get(bracket, bracket)
    a_has = a_lead is not None and any(t.kind == MARK and t.cls == cls for t in _lead_part(tokens(a_lead, "a")))
    b_has = b_lead is not None and any(t.kind == MARK and t.cls == cls for t in _lead_part(tokens(b_lead, "b")))
    return a_has and (b_lead is None or b_has)


def bisect_left(values: Sequence[int], x: int) -> int:
    import bisect
    return bisect.bisect_left(values, x)


def _markup(t: Token) -> bool:
    """A token of the page that is its own markup, not print (emphasis
    markers, a tag)."""
    return t.kind == MARKUP or (t.kind == MARK and t.raw in "*_`#")


def retry_marks(setting: Setting, plan: rr.Plan) -> None:
    """R1 over the pages (the module's docstring)."""
    for scan in setting.order:
        record = setting.book.pages[scan].record
        passes = retry_passes(record)
        if not passes:
            continue
        page = setting.page(scan)
        text, s = page.text, page.s
        taken: list[tuple[int, int]] = []
        for p in passes:
            fa = ra.stream(p["firstAnswer"])
            if len(fa.chars) < 4 or s.chars.count(fa.chars) != 1:
                continue
            i0 = s.chars.index(fa.chars)
            n = len(fa.chars)
            left = 0   # gaps of the stretch that differ from engine A's and stay
            for j in range(n + 1):
                k = i0 + j
                fa_toks = tokens(fa.gaps[j], "page", j == 0)
                uneven = False
                if j == 0 or j == n:
                    # The stretch's outer gaps: the part on the stretch's own
                    # line, on each side cut at its line break.
                    if (j == 0 and k == 0) or (j == n and k >= len(s.chars)):
                        continue
                    start, end = page.span(k)
                    p_all = tokens(text[start:end], "page")
                    ia = page.to_a[k] if j == 0 else page.to_a[k - 1]
                    ib = page.to_b[k] if j == 0 else page.to_b[k - 1]
                    if j == n:
                        ia = ia + 1 if ia is not None and ia + 1 < len(page.a.gaps) else None
                        ib = ib + 1 if ib is not None and ib + 1 < len(page.b.gaps) else None
                    a_all = tokens(page.a.gaps[ia], "a") if ia is not None else None
                    b_all = tokens(page.b.gaps[ib], "b") if ib is not None else None
                    cut = _lead_part if j == 0 else _trail_part
                    p_part = cut(p_all)
                    a_part = cut(a_all) if a_all is not None else None
                    b_part = cut(b_all) if b_all is not None else None
                    if j == 0:
                        sub_start, sub_end = start + (p_part[0].start if p_part else end - start), end
                    else:
                        sub_start, sub_end = start, start + (p_part[-1].end if p_part else 0)
                    # Engine A ends its line in the gap and the page does not
                    # (or the reverse): what stands beyond the break on one
                    # side stands in the part on the other.
                    uneven = a_all is not None and any(t.kind == BREAK for t in a_all) \
                        != any(t.kind in (BREAK, STRUCT, CELL, ROW) for t in p_all)
                else:
                    gap = page.gap(k)
                    sub_start, sub_end = gap.start, gap.end
                    a_part, b_part, p_part = gap.a, gap.b, gap.page
                if a_part is None:
                    continue
                fa_keys, a_keys, p_keys = keys(fa_toks), keys(a_part), keys(p_part)
                if fa_keys != a_keys or fa_keys == p_keys:
                    # Marks the kept retry wrote that neither the first
                    # answer nor engine A holds stay, and are counted.
                    marks = [[key for key in side if key[0] == MARK] for side in (p_keys, fa_keys, a_keys)]
                    left += marks[0] != marks[1] and marks[0] != marks[2] and not uneven
                    continue
                if any(kind in (MARKER, OTHER) for kind, _ in fa_keys + p_keys):
                    continue
                if any(t.kind in (BREAK, STRUCT, CELL, ROW) for t in p_part):
                    continue
                p_runs = [key for key in p_keys if key[0] == RUN]
                why = None
                if uneven:
                    why = "engine A's line ends here and the page's does not"
                elif any(_markup(t) for t in p_part):
                    why = "the page holds markup here"
                elif p_runs and p_runs != [key for key in fa_keys if key[0] == RUN]:
                    why = "the page holds print the first answer lacks"
                elif b_part is not None and keys(b_part) != fa_keys:
                    why = "engine B reads the gap otherwise"
                elif j == 0 and any(line_figure(t.raw) for t in runs_of(a_part)[:1]):
                    why = "a figure opens the line"
                elif written_in(setting.mask, scan, sub_start, sub_end):
                    why = "a model answer wrote here"
                if why is not None:
                    plan.doubts.append(("retry-marks-unverified", scan,
                                        _retry_detail(page, k, fa, j, a_part, b_part, p_part, why),
                                        {"pass": p["index"], "block": p.get("block")}))
                    continue
                if any(re_.overlaps((sub_start, sub_end), t) for t in taken):
                    continue
                # The gap as engine A wrote it: the first answer holds the
                # same runs and marks, and the engine's glyphs are the print's.
                new = written(a_part)[0]
                if new == text[sub_start:sub_end]:
                    continue
                taken.append((sub_start, sub_end))
                plan.edits.append(re_.Edit(scan, sub_start, sub_end, new, rule="R1", evidence={
                    "before": text[sub_start:sub_end], "firstAnswer": show(fa.gaps[j], 120),
                    "engineA": show("".join(t.raw for t in a_part), 120),
                    "engineB": show("".join(t.raw for t in b_part), 120) if b_part is not None else None,
                    "pass": p["index"], "block": p.get("block"), "range": p.get("range"),
                    "reason": p.get("reason")}))
            if left:
                before, after = s.chars[max(0, i0 - 0):i0 + 4], s.chars[max(i0, i0 + n - 4):i0 + n]
                plan.doubts.append(("retry-marks-unverified", scan,
                                    f"{left} gap(s) of a retried stretch ({before}\u2026{after}) hold marks that are neither "
                                    f"the first answer's nor engine A's", {"pass": p["index"], "block": p.get("block"),
                                                                           "gaps": left}))


def _retry_detail(page: PageRuns, k: int, fa: ra.Stream, j: int, a_part: Sequence[Token], b_part: Sequence[Token] | None,
                  p_part: Sequence[Token], why: str) -> str:
    before, after = page.context(k)
    return (f"{why}: {before}\u2038{after}\u3000first answer\u300c{show(fa.gaps[j], 30)}\u300dA\u300c"
            f"{show(''.join(t.raw for t in a_part), 30)}\u300dB\u300c"
            f"{show(''.join(t.raw for t in b_part), 30) if b_part is not None else '-'}\u300d"
            f"page\u300c{show(''.join(t.raw for t in p_part), 30)}\u300d")[:220]


def _gap_detail(page: PageRuns, gap: Gap, why: str | None = None) -> str:
    """A doubt's text: the reason first (it is not to be cut off), then the
    place and each side's reading of the gap."""
    before, after = page.context(gap.k)
    text = (f"{before}\u2038{after}\u3000A\u300c{show(gap.a_raw, 45) if gap.a_raw is not None else '-'}\u300d"
            f"B\u300c{show(gap.b_raw, 45) if gap.b_raw is not None else '-'}\u300d"
            f"page\u300c{show(page.text[gap.start:gap.end], 45)}\u300d")
    return (f"{why}: {text}" if why else text)[:220]


@dataclass
class Tally:
    """A page's note markers the engines read: lacking on the page, or of
    another value."""
    lacking: list[str] = field(default_factory=list)
    differing: list[str] = field(default_factory=list)
    # The runs engine A alone read where engine B is not aligned: (place, runs).
    alone: list[tuple[str, list[str]]] = field(default_factory=list)
    # N5: the gaps of a table whose marks both engines read and the page
    # lacks, where the marks could not be written (place, engine A's text),
    # how many marks those gaps hold, and how many of the rule's marks the
    # bracket guard withheld.
    cells: list[str] = field(default_factory=list)
    cell_marks: int = 0
    withheld: int = 0


def _markers(toks: Sequence[Token] | None) -> list[str]:
    return [t.cls for t in (toks or []) if t.kind == MARKER]


def _head(toks: Sequence[Token] | None) -> list[Token] | None:
    """The tokens before the first break, when there is one."""
    if toks is None:
        return None
    first = next((i for i, t in enumerate(toks) if t.kind == BREAK), None)
    return list(toks[:first]) if first is not None else None


def head_gap(gap: Gap) -> Gap | None:
    """The part of GAP on the line of the character before it: up to the
    page's first line break, with engine A's and engine B's text up to
    theirs.  A note marker that opens the next line (the next footnote's
    number) then stands outside it.  None when the page or engine A has no
    break in the gap."""
    p_head, a_head = _head(gap.page), _head(gap.a)
    if p_head is None or a_head is None:
        return None
    b_head = _head(gap.b) if gap.b is not None else None
    if gap.b is not None and b_head is None:
        b_head = list(gap.b)
    end = gap.start + (p_head[-1].end if p_head else 0)
    a_raw = "".join(t.raw for t in a_head)
    b_raw = "".join(t.raw for t in b_head) if b_head is not None else None
    return Gap(gap.k, gap.start, end, p_head, a_head, b_head, a_raw, b_raw, gap.a_index)


def text_runs(setting: Setting, plan: rr.Plan) -> None:
    """N1, N5, N3 and N2 over the pages: the edits proposed (not yet applied)
    and the doubts, added to PLAN."""
    for scan in setting.order:
        page = setting.page(scan)
        if not page.s.chars:
            _blank_page(setting, page, plan)
        else:
            plan.edits.extend(_page_runs(setting, page, plan))
        _moved_rows(setting, scan, plan)


def _page_runs(setting: Setting, page: PageRuns, plan: rr.Plan, inside: tuple[int, int] | None = None) -> list[re_.Edit]:
    """One page's gaps: the edits proposed, the doubts added to PLAN.  With
    INSIDE (a span of the page's text), only the gaps that touch it are
    read, and no gap is taken for one a model answer wrote (the caller
    checks that where the text stands now)."""
    scan = page.scan
    text = page.text
    tally = Tally()
    found: list[re_.Edit] = []
    wrote: dict[int, list[int]] = {}
    cells: dict[int, list[int]] = {}
    # The gaps where engine A holds brackets, for the pairing guard (unpaired).
    lacking: list[tuple[int, int, int]] = []

    def answered(start: int, end: int) -> bool:
        return inside is None and written_in(setting.mask, scan, start, end)

    def woven(gap: Gap, new: str, tier: str, names: Sequence[str]) -> None:
        # N5 where the text written holds a mark of a table cell that N1 leaves.
        if gap.cells:
            edit = _edit(scan, gap, new, "N5", "cell marks, runs" if names else "cell marks", names)
            cells[id(edit)] = list(gap.cells)
        else:
            edit = _edit(scan, gap, new, "N1", tier, names)
        wrote[id(edit)] = list(gap.wrote)
        found.append(edit)

    def unwritten(gap: Gap, new: str | None) -> None:
        # N5: the marks of a table gap the rule holds for (cell_gap) that it
        # could not write - the whole gap (its cell boundaries are not the
        # engines' one to one), or a stretch of it (stretches, _stretch).
        count = sum(1 for t in gap.a or [] if t.kind == MARK) if new is None else gap.cell_lost
        if count:
            tally.cells.append(f"{page.context(gap.k)[0]}\u2038{show(gap.a_raw or '', 16)}")
            tally.cell_marks += count

    for gap in page.gaps():
        if inside is not None and not (gap.end > inside[0] and gap.start < inside[1]):
            continue
        if gap.a is not None and brackets_of(gap.a):
            lacking.append((gap.start, gap.end, brackets_of(gap.a)))
        if gap.a is None:
            # Engine B alone: a run the page lacks, with no engine A witness.
            if gap.b is not None and runs_of(gap.b) and not runs_of(gap.page) and not _markers(gap.b) \
                    and not _is_folio(page, gap, gap.b):
                plan.doubts.append(("run-one-engine", scan, _gap_detail(page, gap, "engine B alone"),
                                    {"engine": "B", "runs": [t.raw for t in runs_of(gap.b)]}))
            continue
        a_runs = runs_of(gap.a)
        p_runs = runs_of(gap.page)
        a_mk, b_mk, p_mk = _markers(gap.a), _markers(gap.b), _markers(gap.page)
        if a_mk or b_mk or p_mk:
            # Note markers: tallied for the page, never written.
            if (a_mk or b_mk) and not p_mk:
                value = a_mk[0] if a_mk else b_mk[0]
                if not b_mk or not a_mk or a_mk == b_mk:
                    tally.lacking.append(f"{page.context(gap.k)[0]}\u2038{value}")
            elif a_mk and b_mk and a_mk == b_mk and p_mk != a_mk:
                tally.differing.append(f"{page.context(gap.k)[0]}\u2038{'/'.join(a_mk)}\u2260{'/'.join(p_mk)}")
            # The marker opens the next line (the next footnote's
            # number): the part of the gap on this line is read on its own.
            head = head_gap(gap)
            if head is None or _markers(head.a) or _markers(head.b) or _markers(head.page) \
                    or not runs_of(head.a):
                continue
            gap = head
            a_runs = runs_of(gap.a)
            p_runs = runs_of(gap.page)
        lines = text_lines(gap.a) if len(gap.a) <= 5 * TOKEN_LIMIT else []
        if lines:
            _whole_lines(page, gap, lines, plan, found, answered)
            continue
        if len(gap.a) > TOKEN_LIMIT:
            if a_runs and not p_runs:
                plan.doubts.append(("run-no-place", scan, _gap_detail(page, gap, "the gap is too long to weave"), {}))
            continue
        if not a_runs:
            if gap.b is not None and runs_of(gap.b) and not p_runs and not _is_folio(page, gap, gap.b):
                plan.doubts.append(("run-one-engine", scan, _gap_detail(page, gap, "engine A reads none"),
                                    {"engine": "B", "runs": [t.raw for t in runs_of(gap.b)]}))
            elif cell_gap(page, gap) and not answered(gap.start, gap.end):
                # N5, marks alone: written where their place is given, and
                # counted for the page's one doubt where it is not.
                new, tier, names = weave(gap)
                if new is not None and gap.cells and new != text[gap.start:gap.end]:
                    woven(gap, new, tier, names)
                unwritten(gap, new)
            continue
        if p_runs:
            if [t.key for t in p_runs] == [t.key for t in a_runs] or fused(gap.page) == fused(gap.a):
                continue
            if gap.b is not None and agree(gap.a, gap.b):
                plan.doubts.append(("run-no-place", scan, _gap_detail(page, gap, "the page holds another run"),
                                    {"runs": [t.raw for t in a_runs], "pageRuns": [t.raw for t in p_runs]}))
            continue
        if _is_folio(page, gap, gap.a):
            continue
        if gap.b is None:
            # One doubt for the page (below): engine B may hold none of a
            # page's notes, and each of their runs is such a gap.
            tally.alone.append((f"{page.context(gap.k)[0]}\u2038{show(gap.a_raw or '', 24)}", [t.raw for t in a_runs]))
            continue
        near = not agree(gap.a, gap.b) and nearly(gap.a, gap.b)
        if near:
            # Written as engine A reads it (below); the two readings on record.
            plan.doubts.append(("run-engines-differ", scan,
                                _gap_detail(page, gap, "hyphens or apostrophes apart; written as engine A reads it"),
                                {"engineA": [t.raw for t in a_runs], "engineB": [t.raw for t in runs_of(gap.b)],
                                 "written": "A"}))
        elif not agree(gap.a, gap.b):
            b_runs = runs_of(gap.b)
            if not b_runs:
                plan.doubts.append(("run-one-engine", scan, _gap_detail(page, gap, "engine B reads none"),
                                    {"engine": "A", "runs": [t.raw for t in a_runs]}))
                continue
            if [t.key for t in b_runs] == [t.key for t in a_runs] and not any(
                    t.kind == OTHER for t in gap.a + gap.b):
                # The runs agree, the marks about them do not: the runs
                # may still be woven where the page's marks are all of one
                # engine's (T1, no mark of the page left out), not otherwise.
                names = [t.raw for t in a_runs]
                why = "the engines' marks about the run differ"
                if answered(gap.start, gap.end):
                    why = "a model answer wrote here"
                elif any(line_initial_figure(gap.a, run, gap.k == 0) for run in a_runs):
                    why = "a figure opens a line in engine A"
                else:
                    new, tier, names = weave(gap)
                    if new is not None and tier == "T1" and not gap.dropped and new != text[gap.start:gap.end]:
                        woven(gap, new, tier + " (engine B's marks differ)", names)
                        continue
                    on_b = Gap(gap.k, gap.start, gap.end, gap.page, gap.b, gap.a, gap.b_raw, gap.a_raw, gap.a_index,
                               edge=gap.edge)
                    new, tier, names = weave(on_b)
                    if new is not None and tier == "T1" and not on_b.dropped and new != text[gap.start:gap.end]:
                        woven(on_b, new, tier + " (on engine B's marks)", names)
                        continue
                plan.doubts.append(("run-no-place", scan, _gap_detail(page, gap, why), {"runs": names}))
                continue
            plan.doubts.append(("run-engines-differ", scan, _gap_detail(page, gap),
                                {"engineA": [t.raw for t in a_runs], "engineB": [t.raw for t in b_runs]}))
            continue
        if answered(gap.start, gap.end):
            plan.doubts.append(("run-no-place", scan, _gap_detail(page, gap, "a model answer wrote here"),
                                {"runs": [t.raw for t in a_runs]}))
            continue
        # N5: in a table, the marks of the gap are written with its runs.
        in_cell = cell_gap(page, gap)
        new, tier, names = weave(gap)
        if in_cell:
            unwritten(gap, new)
        if new is None:
            rewritten = permuted(gap)
            if rewritten is not None:
                found.append(_edit(scan, gap, rewritten, "N3", "marks reordered", names))
                continue
            plan.doubts.append(("run-no-place", scan, _gap_detail(page, gap, tier), {"runs": names}))
            continue
        if new != text[gap.start:gap.end]:
            woven(gap, new, tier, names)
    proposed = {key: len(offsets) for key, offsets in cells.items()}
    unpaired(text, found, wrote, lacking, cells)
    for edit in found:
        if edit.rule != "N5":
            continue
        # N5 names the edit for the marks of a cell that N1 leaves; where the
        # bracket guard withheld every one of them, what is left is N1's (its
        # runs with the marks beside them), or nothing of the print (a space
        # put beside a pipe for a mark withheld): the gap stays as it is.
        tally.withheld += proposed[id(edit)] - len(cells[id(edit)])
        if not cells[id(edit)]:
            if edit.evidence.get("runs"):
                edit.rule, edit.evidence = "N1", {**edit.evidence, "tier": "T2"}
            else:
                edit.after = text[edit.start:edit.end]
    if tally.alone:
        places = "; ".join(place for place, _ in tally.alone)
        plan.doubts.append(("run-one-engine", scan,
                            f"engine B is not aligned at {len(tally.alone)} place(s) where engine A reads a run: {places}"[:220],
                            {"engine": "A", "runs": [run for _, names in tally.alone for run in names],
                             "places": len(tally.alone)}))
    if tally.lacking or tally.differing:
        parts = []
        if tally.lacking:
            parts.append(f"{len(tally.lacking)} the page lacks ({'; '.join(tally.lacking[:3])})")
        if tally.differing:
            parts.append(f"{len(tally.differing)} of another value ({'; '.join(tally.differing[:3])})")
        plan.doubts.append(("note-markers-unverified", scan, ("note markers the engines read: " + ", ".join(parts))[:220],
                            {"lacking": len(tally.lacking), "differing": len(tally.differing)}))
    if tally.cells or tally.withheld:
        # N5: one doubt a page for the marks it found and could not write.
        parts = []
        if tally.cells:
            parts.append(f"{tally.cell_marks} in {len(tally.cells)} gap(s) with no place for them "
                         f"({'; '.join(tally.cells[:3])})")
        if tally.withheld:
            parts.append(f"{tally.withheld} bracket(s) withheld, no partner on the line or in the cell")
        plan.doubts.append(("run-no-place", scan,
                            ("table marks both engines read that the page lacks, not written: " + ", ".join(parts))[:220],
                            {"marks": tally.cell_marks + tally.withheld, "gaps": len(tally.cells), "withheld": tally.withheld}))
    return found


def _moved_rows(setting: Setting, scan: int, plan: rr.Plan) -> None:
    """The rows of SCAN's table that phase 3 moved into an earlier page's
    table (the seal's tableStitch: the page's text before the move, the rows
    moved and the page that holds them now).  The engines read them on SCAN,
    so they are read there: the page's text as it stood before the move
    against SCAN's engines, the gaps that touch the rows.  Each edit is made
    on the page that holds the rows now, where the lines it touches stand
    there once and unchanged; one that cannot be is a doubt - the edits of
    marks alone (N5) one doubt a page, with the count of their marks (the
    stitch re-rendered the rows of scans 527, 528 and 536 of the 609-page
    book into scan 522's HTML table, and the 44 marks their 44 edits held
    found no place there and left no trace, measured 2026-10-02)."""
    stitch = setting.book.pages[scan].record.get("tableStitch")
    if not isinstance(stitch, dict):
        return
    before, part = stitch.get("before"), stitch.get("continuation")
    if not isinstance(before, str) or not isinstance(part, dict):
        return
    moved, host = part.get("moved"), (part.get("head") or {}).get("page")
    if not isinstance(moved, str) or not moved.strip() or host == scan or host not in setting.texts:
        return
    at = before.find(moved)
    if at < 0 or before.find(moved, at + 1) >= 0:
        return
    block = (at, at + len(moved))
    page = setting.page(scan, before)
    if not page.s.chars:
        return
    trial = rr.Plan()
    edits = _page_runs(setting, page, trial, inside=block)
    for kind, _, detail, fields in trial.doubts:
        plan.doubts.append((kind, scan, detail, {**fields, "movedTo": host}))
    host_text = setting.texts[host]
    unplaced: list[str] = []   # why, per edit of marks alone that found no place
    marks = 0
    for edit in edits:
        placed = _on_host(setting, scan, host, before, block, host_text, edit)
        if isinstance(placed, str):
            names = list(edit.evidence.get("runs") or edit.evidence.get("lines") or [])
            if names:
                plan.doubts.append(("run-no-place", scan,
                                    f"rows moved into page {host}'s table: {placed}; runs {names}"[:220], {"movedTo": host}))
            else:
                unplaced.append(placed)
                marks += len([t for t in tokens(edit.after, "page") if t.kind == MARK]) \
                    - len([t for t in tokens(before[edit.start:edit.end], "page") if t.kind == MARK])
        else:
            plan.edits.extend(placed)
    if unplaced:
        plan.doubts.append(("run-no-place", scan,
                            f"rows moved into page {host}'s table: {marks} table mark(s) both engines read that the rows lack, "
                            f"in {len(unplaced)} gap(s), not written: {'; '.join(sorted(set(unplaced)))}"[:220],
                            {"movedTo": host, "marks": marks, "gaps": len(unplaced)}))


def _on_host(setting: Setting, scan: int, host: int, before: str, block: tuple[int, int], host_text: str,
             edit: re_.Edit) -> list[re_.Edit] | str:
    """EDIT, proposed on SCAN's text BEFORE its rows moved, as edits of the
    page HOST that holds the rows now; else why not.  An edit that changes
    two lines which do not stand together on the host (the move drops the
    rule under the continuation's first row, which the gap between its
    first two rows holds) is made line by line, all of it or none."""
    old, new = before[edit.start:edit.end], edit.after
    placed = _host_edit(setting, scan, host, before, block, host_text, edit, edit.start, old, new)
    if not isinstance(placed, str):
        return [placed]
    if "\n" not in old or old.count("\n") != new.count("\n"):
        return placed
    parts: list[re_.Edit] = []
    at = edit.start
    for old_line, new_line in zip(old.split("\n"), new.split("\n")):
        if old_line != new_line:
            part = _host_edit(setting, scan, host, before, block, host_text, edit, at, old_line, new_line)
            if isinstance(part, str):
                return part
            parts.append(part)
        at += len(old_line) + 1
    return parts


def _host_edit(setting: Setting, scan: int, host: int, before: str, block: tuple[int, int], host_text: str,
               edit: re_.Edit, at: int, old: str, new: str) -> re_.Edit | str:
    """BEFORE's text OLD at AT becoming NEW (EDIT, or a line of it), as an
    edit of the page HOST; else why not."""
    lead = 0
    while lead < min(len(old), len(new)) and old[lead] == new[lead]:
        lead += 1
    trail = 0
    while trail < min(len(old), len(new)) - lead and old[len(old) - 1 - trail] == new[len(new) - 1 - trail]:
        trail += 1
    start, end, after = at + lead, at + len(old) - trail, new[lead:len(new) - trail]
    line_start = before.rfind("\n", 0, start) + 1
    line_end = before.find("\n", end)
    line_end = len(before) if line_end < 0 else line_end
    if line_start < block[0] or line_end > block[1]:
        return "the place is not in the rows moved"
    lines = before[line_start:line_end]
    here = host_text.find(lines)
    if here < 0 or host_text.find(lines, here + 1) >= 0:
        return "the rows do not stand there once and unchanged"
    if (here and host_text[here - 1] != "\n") \
            or (here + len(lines) < len(host_text) and host_text[here + len(lines)] != "\n"):
        return "the rows do not stand there once and unchanged"
    host_start = here + start - line_start
    host_end = host_start + end - start
    if written_in(setting.mask, host, host_start, host_end):
        return "a model answer wrote here"
    return re_.Edit(host, host_start, host_end, after, rule=edit.rule, evidence={
        **edit.evidence, "before": host_text[host_start:host_end], "movedFrom": scan})


def _is_folio(page: PageRuns, gap: Gap, toks: Sequence[Token] | None) -> bool:
    """Whether the runs of TOKS (an engine's reading of GAP, a page's edge)
    are the page's folio: one run, the folio whole, alone on a line beyond
    the page's first or last line of text.  A figure joined to text is
    text."""
    runs = runs_of(toks or [])
    if not gap.edge or len(runs) != 1 or runs[0].raw.translate(RUN_FOLD) not in page.folio_whole:
        return False
    lines = _lines_of(toks or [])
    at = next(n for n, line in enumerate(lines) if any(t is runs[0] for t in line))
    alone = not any(t.kind in (RUN, MARK) and t is not runs[0] for t in lines[at])
    return alone and (at > 0 if gap.edge == "end" else at < len(lines) - 1)


def _edit(scan: int, gap: Gap, new: str, rule: str, tier: str, names: Sequence[str]) -> re_.Edit:
    return re_.Edit(scan, gap.start, gap.end, new, rule=rule, evidence={
        "before": "".join(t.raw for t in gap.page), "tier": tier, "runs": list(names),
        "engineA": show(gap.a_raw or "", 160), "engineB": show(gap.b_raw or "", 160), "aIndex": gap.a_index})


def _whole_lines(page: PageRuns, gap: Gap, lines: Sequence[Sequence[Token]], plan: rr.Plan, found: list[re_.Edit],
                 answered: Callable[[int, int], bool]) -> None:
    """N2 on one gap: the whole lines of engine A's gap, when engine B
    reads them alike and the page holds no run in the gap; the edit goes to
    FOUND."""
    scan = page.scan
    # A line engine A read in a block of the page's furniture is not text.
    furniture = [str(b.get("text") or "") for b in page.pd.a_blocks if b.get("label") in FURNITURE_LABELS]
    lines = [seg for seg in lines if not any("".join(t.raw for t in seg).strip() in text for text in furniture)]
    if not lines:
        return
    texts = [line_text(seg) for seg in lines]
    if runs_of(gap.page):
        if fused(gap.page) != fused(gap.a) and gap.b is not None and agree(gap.a, gap.b):
            plan.doubts.append(("run-no-place", scan, _gap_detail(page, gap, "the page holds another run"), {"lines": texts}))
        return
    if gap.b is None or not runs_of(gap.b):
        plan.doubts.append(("run-one-engine", scan, _gap_detail(page, gap, "a whole line engine B did not read"),
                            {"engine": "A", "lines": texts}))
        return
    whole = list(lines)
    if not agree(gap.a, gap.b):
        # Line by line: where both engines cut the gap into the same lines
        # and differ in some of the whole lines only, the others are written.
        a_lines, b_lines = _lines_of(gap.a), _lines_of(gap.b)
        at = {id(seg[0]): n for n, seg in enumerate(a_lines) if seg}
        apart = [n for n in range(len(a_lines)) if loose(a_lines[n]) != loose(b_lines[n])] \
            if len(a_lines) == len(b_lines) else None
        numbers = [at[id(seg[0])] for seg in whole]
        if apart is not None:
            # Lines that differ in hyphens or apostrophes only are written as
            # engine A reads them (nearly), the two readings on record.
            near = [n for n in range(len(a_lines)) if n not in apart and fused(a_lines[n]) != fused(b_lines[n])]
            if near:
                plan.doubts.append(("run-engines-differ", scan,
                                    _gap_detail(page, gap, f"{len(near)} whole line(s) hyphens or apostrophes apart; "
                                                           "written as engine A reads them"),
                                    {"engineA": [line_text(a_lines[n]) for n in near],
                                     "engineB": [line_text(b_lines[n]) for n in near], "written": "A"}))
        if apart is None or len(apart) >= len(whole) or any(n not in numbers for n in apart):
            plan.doubts.append(("run-engines-differ", scan, _gap_detail(page, gap, "whole lines"),
                                {"engineA": texts, "engineB": show("".join(t.raw for t in gap.b), 200)}))
            return
        if apart:
            plan.doubts.append(("run-engines-differ", scan,
                                _gap_detail(page, gap, f"{len(apart)} of {len(whole)} whole lines, left out"),
                                {"engineA": [line_text(a_lines[n]) for n in apart],
                                 "engineB": [line_text(b_lines[n]) for n in apart]}))
            lines = [seg for seg, n in zip(whole, numbers) if n not in apart]
            texts = [line_text(seg) for seg in lines]
    if answered(gap.start, gap.end):
        plan.doubts.append(("run-no-place", scan, _gap_detail(page, gap, "a model answer wrote here"), {"lines": texts}))
        return
    p_toks = gap.page
    breaks = [n for n, t in enumerate(p_toks) if t.kind == BREAK]
    why = None
    if not breaks or any(t.kind in (CELL, ROW) for t in p_toks) \
            or any(t.kind not in (BREAK, SPACE) for t in p_toks[breaks[0]:breaks[-1]]):
        # One run of line breaks on the page is the lines' place; with more,
        # which one is not given.
        why = "no single line break on the page to put the lines at"
    elif len(whole) != len(_lines_of(gap.a)) - 2:
        # Engine A holds other lines between: the lines' order among what the
        # page holds there is not given.
        why = "other lines stand among them in engine A"
    elif any(om.LIST_ITEM_RE.match(t) or t.startswith(("#", "<", "|", ">")) or line_figure(t) for t in texts):
        why = "a line would read as Markdown structure, or opens with a figure of its own"
    elif any(t.kind == STRUCT and re.search(r"[-*+]", t.raw) for t in p_toks[breaks[-1]:]) \
            and om.LIST_ITEM_RE.match(page.text[slice(*page.line_span(max(0, gap.start - 1)))]):
        why = "the lines would stand between two items of a list"
    if why is not None:
        plan.doubts.append(("run-no-place", scan, _gap_detail(page, gap, why), {"lines": texts}))
        return
    gap_text = page.text[gap.start:gap.end]
    # The rest of the gap (the marks and runs on the lines either side of the
    # whole lines) is woven first; the whole lines go in at the page's first
    # break of the woven text.
    inside = {id(t) for seg in whole for t in seg}
    rest = [t for t in gap.a if id(t) not in inside]
    base = gap_text
    tier = "lines"
    if not runs_of(rest):
        # A mark of the page that the engines do not hold outside the whole
        # lines, of a class the lines written hold, is one of theirs: the
        # punctuator saw it in the crop and had no line to put it on.  It
        # goes, now that the line stands with its own.
        outside = [coarse(t.key) for t in rest if t.kind == MARK]
        theirs: dict[tuple[str, str], int] = {}
        for seg in lines:
            for t in seg:
                if t.kind == MARK:
                    theirs[coarse(t.key)] = theirs.get(coarse(t.key), 0) + 1
        gone: list[Token] = []
        i = 0
        for t in gap.page:
            if t.kind != MARK:
                continue
            key = coarse(t.key)
            j = next((n for n in range(i, len(outside)) if outside[n] == key), None)
            if j is not None:
                i = j + 1
            elif theirs.get(key):
                theirs[key] -= 1
                gone.append(t)
        if gone:
            base = "".join(t.raw for t in gap.page if not any(t is g for g in gone))
            tier = "lines, the page's marks of theirs dropped"
    if runs_of(rest):
        woven, tier, _names = weave(Gap(gap.k, gap.start, gap.end, gap.page, rest, gap.b, gap.a_raw, gap.b_raw, gap.a_index,
                                        edge=gap.edge))
        if woven is None:
            plan.doubts.append(("run-no-place", scan, _gap_detail(page, gap, f"runs beside the whole lines: {tier}"),
                                {"lines": texts}))
            return
        base = woven
        tier = f"lines, {tier}"
    cut = base.find("\n")
    if cut < 0:
        plan.doubts.append(("run-no-place", scan, _gap_detail(page, gap, "no line break on the page to put the lines at"),
                            {"lines": texts}))
        return
    head = base[:cut].rstrip(" \t")
    tail = base[cut:].lstrip("\n")
    texts = paragraphs(lines, gap.b)
    new = head + "\n\n" + "\n\n".join(texts) + "\n\n" + tail
    found.append(re_.Edit(scan, gap.start, gap.end, new, rule="N2", evidence={
        "before": gap_text, "tier": tier, "lines": texts, "engineA": show(gap.a_raw or "", 160),
        "engineB": show("".join(t.raw for t in gap.b), 160), "aIndex": gap.a_index}))


def _blank_page(setting: Setting, page: PageRuns, plan: rr.Plan) -> None:
    """A marker page sealed with no character: the engines' text of no CJK
    character - every line of it that holds a run, but the folio on a line
    of its own - written when they agree, else a doubt."""
    scan = page.scan
    a_text, b_text = page.pd.a_body, page.pd.b_body
    if pp.CJK(a_text) or pp.CJK(b_text) or page.text.strip():
        return
    a_toks, b_toks = tokens(a_text, "a", True), tokens(b_text, "b", True)
    lines = [line for line in _lines_of(a_toks) if runs_of(line)
             and not (len(runs_of(line)) == 1 and not any(t.kind == MARK for t in line)
                      and runs_of(line)[0].raw.translate(RUN_FOLD) in page.folio_whole)]
    if not lines:
        return
    texts = [line_text(seg) for seg in lines]
    if not runs_of(b_toks):
        plan.doubts.append(("run-one-engine", scan, f"a page sealed empty where engine A reads: {show(' / '.join(texts), 160)}",
                            {"engine": "A", "lines": texts}))
        return
    if not agree(a_toks, b_toks) or any(t.kind in (MARKER, OTHER, CELL, ROW) for t in a_toks + b_toks):
        plan.doubts.append(("run-engines-differ", scan,
                            f"a page sealed empty; A: {show(' / '.join(texts), 90)}; B: {show(line_text(b_toks), 90)}",
                            {"engineA": texts, "engineB": show(b_text, 200)}))
        return
    if any(om.LIST_ITEM_RE.match(t) or t.startswith(("#", "<", "|", ">")) for t in texts):
        plan.doubts.append(("run-no-place", scan, f"a page sealed empty: a line would read as Markdown structure: "
                                                   f"{show(' / '.join(texts), 150)}"[:220], {"lines": texts}))
        return
    new = "\n\n".join(texts) + "\n"
    plan.edits.append(re_.Edit(scan, 0, len(page.text), new, rule="N2", evidence={
        "before": page.text, "lines": texts, "engineB": show(b_text, 200), "aIndex": 0}))


# --- the contract at the page edges --------------------------------------------------------

def _nonblank(text: str) -> list[str]:
    return [line for line in text.split("\n") if line.strip()]


def _glued(last: Sequence[str], first: Sequence[str]) -> bool:
    """Whether a `join` of a page ending LAST with one opening FIRST would
    run two text runs together."""
    return bool(last and first) and re.search(rf"[{ALNUM}%\uff05]$", last[-1].rstrip()) is not None \
        and re.match(rf"[{ALNUM}]", first[0].lstrip()) is not None


def edge_safe(book: Any, texts: Mapping[int, str], order: Sequence[int], labels: Mapping[int, str] | None,
              edits: Sequence[re_.Edit], plan: rr.Plan) -> list[re_.Edit]:
    """EDITS without those that would change the kind of a page's first or
    last line (the joins stage labelled each boundary by it), break the
    finalize contract at a boundary, or glue two text runs across a `join`:
    the edits on the line concerned are withheld, each as a doubt.  Only
    what the edits themselves bring about counts.  A heading N4 puts back
    is meant to change its line's kind: it is withheld only where the
    boundary beside it is a `join`, which would run the heading into the
    other page's text."""
    kept = list(edits)
    if not kept:
        return kept
    known = set(rj.contract_problems(book.assembly.compose(dict(texts)), labels)) if labels else set()
    for _ in range(8):
        trial = re_.Ledger({scan: texts[scan] for scan in order})
        trial.apply("runs", kept)
        after = trial.texts
        bad: dict[tuple[int, str], str] = {}
        kind_only: set[tuple[int, str]] = set()
        for scan in order:
            was, now = _nonblank(texts[scan]), _nonblank(after[scan])
            if was and now:
                for which, n in (("first", 0), ("last", -1)):
                    if rj.kind_of(was[n]) != rj.kind_of(now[n]):
                        bad[(scan, which)] = f"the page's {which} line would change kind"
                        kind_only.add((scan, which))
        if labels:
            for problem in rj.contract_problems(book.assembly.compose(after), labels):
                m = re.search(r"boundary (\d+)", problem)
                if m and problem not in known and int(m.group(1)) in order:
                    scan = int(m.group(1))
                    bad[(scan, "first")] = problem
                    kind_only.discard((scan, "first"))
                    if order.index(scan):
                        bad[(order[order.index(scan) - 1], "last")] = problem
                        kind_only.discard((order[order.index(scan) - 1], "last"))
            for n, scan in enumerate(order):
                if n and labels.get(scan) == "join":
                    prev = order[n - 1]
                    if _glued(_nonblank(after[prev]), _nonblank(after[scan])) \
                            and not _glued(_nonblank(texts[prev]), _nonblank(texts[scan])):
                        bad[(scan, "first")] = bad[(prev, "last")] = "a join would glue two text runs"
                        kind_only -= {(scan, "first"), (prev, "last")}

        def joined(scan: int, which: str) -> bool:
            """Whether the boundary beside the page's WHICH line is a `join`
            (not known without the labels: taken for one)."""
            if not labels:
                return True
            at = order.index(scan)
            beside = scan if which == "first" else order[at + 1] if at + 1 < len(order) else None
            return beside is not None and labels.get(beside) == "join"

        still = []
        for edit in kept:
            heading = edit.rule == "N4" and edit.after.startswith("#")
            why = next((bad[(edit.page, which)] for which in _edges(texts[edit.page], edit)
                        if (edit.page, which) in bad
                        and not (heading and (edit.page, which) in kind_only and not joined(edit.page, which))), None)
            if why is None:
                still.append(edit)
                continue
            kind = "retry-marks-unverified" if edit.rule == "R1" else \
                "heading-kind-unknown" if edit.rule == "N4" and edit.after.startswith("#") else "run-no-place"
            what = list(edit.evidence.get("runs") or edit.evidence.get("lines") or []) or show(edit.after, 40)
            plan.doubts.append((kind, edit.page, f"withheld at the page's edge ({edit.rule}): {why}; {what}"[:220], {}))
        if len(still) == len(kept):
            # Nothing of ours to withhold on a line concerned.
            return kept
        kept = still
    return kept


def _edges(text: str, edit: re_.Edit) -> list[str]:
    """Which of the page's edge lines ("first", "last") EDIT touches."""
    lines = [(m.start(), m.end()) for m in re.finditer(r"[^\n]*", text) if text[m.start():m.end()].strip()]
    if not lines:
        return ["first", "last"]
    return [which for which, hit in (("first", edit.start <= lines[0][1]), ("last", edit.end >= lines[-1][0])) if hit]


def runs(book: Any, model: Mapping[str, Any], ledger: re_.Ledger, order: Sequence[int],
         apply: Callable[[Sequence[re_.Edit]], None], facts: rr.BookFacts | None = None,
         labels: Mapping[int, str] | None = None) -> rr.Plan:
    """The stage: N4 and R1 applied through APPLY, then N1, N5, N3 and N2
    proposed on the text they leave (and checked against the finalize
    contract at the page edges)."""
    facts = facts or rr.book_facts(book, model)
    setting = Setting(book, model, facts, list(order), ledger.texts, question_mask(ledger))
    plan = rr.Plan()
    for propose in (lambda part: s11_undone(setting, ledger.records, part), lambda part: retry_marks(setting, part)):
        part = rr.Plan()
        propose(part)
        plan.doubts.extend(part.doubts)
        apply(edge_safe(book, ledger.texts, list(order), labels, part.edits, plan))
        setting.mask = question_mask(ledger)
    text_runs(setting, plan)
    plan.edits = edge_safe(book, ledger.texts, list(order), labels, plan.edits, plan)
    return plan
