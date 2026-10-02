#!/usr/bin/env python3
"""Offline checks of switch C4, --folio-furniture (off by default).

No model, no GPU, no corpus.  Text one engine read and the other did not - a
numeral, or at most two characters - that would go to 裁決 is written as
nothing when it sits in the page's running-head band: the folios (blocks the
layout labelled number that read numerals or figures), the blocks whose own
text is the book's furniture with a second piece of evidence (the profile's
running head at its size; a header or footer label; a head's type size; a
folio's column or row), and short thin blocks no longer than such a block in
its column or row (furniture_band).  A folio extends the band nowhere.  The
place is engine A's stream's, not the text around it: engine A's own text is
in the blocks it read it in; text only engine B read is in the block its
place falls in, or between the two blocks engine A passes between there.
Between a band block and a body block it may be either's, and it is the
band's only where engine A read the same characters in the page's folio block
and engine B did not read them there (folio_copies).  A question not asked
takes the page's budget it would have taken (--max-adjudications).

The pages are made up, in the shapes the offline study of sealed pages
measured (the folio a side column prints below the running head, which engine
A read in its own block and engine B after the head; the folio engine B read
after the head at the page's end; a leaf folio between the two copies of the
running head at the fold) and the shapes it must leave alone:

- a heading at the start of the body, outside the band, that engine A read
  short (the page's band is the head column at the other edge);
- a section heading at the start of the body that the layout labelled header,
  which engine B read short: a label is no evidence alone;
- a list numeral at the head of a column on a page with no furniture blocks;
- a list numeral at the head of the first body column right after the head
  column, which engine A did not read - the place the study never saw, where
  the band's edge alone cannot tell the folio from the body;
- the same place where engine A read the folio as figures: its folio block
  holds no character, which vouches for nothing (a reprint's own page number
  is figures too);
- the last character of the body right before the running foot;
- the same two where the character is the folio's figure and engine B read
  the folio at its own place too (no second copy of it);
- body text near the top of a page whose running head and folio are a row;
- the first body column, and an article heading, printed under a folio in the
  top margin (the folio's column crosses the body);
- a heading centred above the body in the column of a folio centred at the
  foot of a horizontal page.

Where a spot written as nothing leaves a block the running head alone, which
the page then drops whole, its entry says so (blocksDropped).  And the switch's
own edges: a folio of three figures (a numeral, any length); a volume mark in a
wide running head's row; a folio read away from the head, which the page must
not report dropped; the band's size limits and the head's type size; the
budget, D24's included; --no-adjudicate, where it does nothing; and resume, a
page sealed with it not current for a run without it, nor the reverse.

Usage:
    python3 tests/check_folio_furniture.py
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import proofread_pages as pp  # noqa: E402
import stand_in  # noqa: E402

failures = 0


def check(name: str, got, want) -> None:
    global failures
    if got != want:
        failures += 1
        print(f"FAIL {name}: got {got!r}, want {want!r}")
    else:
        print(f"ok   {name}")


HEAD = "某書卷上"
BODY = ["天地玄黃宇宙洪荒", "日月盈昃辰宿列張", "寒來暑往秋收冬藏"]
Block = stand_in.block

# page -> (engine A's blocks, engine B's text), each page a shape.
PAGES = {
    # The folio printed below the running head in a side column: engine A read
    # it as its own number block and first, engine B after the head.
    1: ([Block("三", [0.74, 0.68, 0.03, 0.02], "number"),
         Block(HEAD, [0.74, 0.18, 0.03, 0.20], "header"),
         Block(BODY[0], [0.60, 0.10, 0.10, 0.68], "vertical_text"),
         Block(BODY[1], [0.45, 0.10, 0.10, 0.68], "vertical_text")],
        HEAD + "三" + BODY[0] + BODY[1]),
    # Engine A read the folio as figures (no character), engine B as numerals
    # after the head, before the first body column: either's, by place.
    2: ([Block("12", [0.74, 0.68, 0.03, 0.02], "number"),
         Block(HEAD, [0.74, 0.18, 0.03, 0.20], "header"),
         Block(BODY[0], [0.60, 0.10, 0.10, 0.68], "vertical_text"),
         Block(BODY[1], [0.45, 0.10, 0.10, 0.68], "vertical_text")],
        HEAD + "十二" + BODY[0] + BODY[1]),
    # The first body column opens with a list numeral engine A did not read;
    # the folio is engine A's number block's, read alike by both.
    3: ([Block("三", [0.74, 0.68, 0.03, 0.02], "number"),
         Block(HEAD, [0.74, 0.18, 0.03, 0.20], "header"),
         Block(BODY[0], [0.60, 0.10, 0.10, 0.68], "vertical_text"),
         Block(BODY[1], [0.45, 0.10, 0.10, 0.68], "vertical_text")],
        "三" + HEAD + "一" + BODY[0] + BODY[1]),
    # A horizontal page: the body's last character, which engine A did not
    # read, right before the running foot and the folio.
    4: ([Block(BODY[0], [0.10, 0.10, 0.80, 0.05], "text"),
         Block(BODY[1][:-1], [0.10, 0.80, 0.80, 0.05], "text"),
         Block(HEAD, [0.10, 0.92, 0.30, 0.03], "footer"),
         Block("七", [0.85, 0.92, 0.05, 0.03], "number")],
        BODY[0] + BODY[1] + HEAD + "七"),
    # A horizontal page with its running head and folio as a row at the top:
    # the body's first line, below it, holds a character only engine B read
    # and one only engine A read.
    5: ([Block(HEAD, [0.10, 0.03, 0.30, 0.03], "header"),
         Block("七", [0.85, 0.03, 0.05, 0.03], "number"),
         Block("天地玄宇之宙洪荒", [0.10, 0.10, 0.80, 0.05], "text"),
         Block(BODY[1], [0.10, 0.20, 0.80, 0.05], "text")],
        HEAD + "七" + "天地玄黃宇宙洪荒" + BODY[1]),
    # A heading at the start of the body at the page's right edge, which
    # engine A read short; the head column and a folio engine A read as a mark
    # at the left edge, and the folio engine B read after the head.
    6: ([Block("第集", [0.75, 0.14, 0.06, 0.14], "doc_title"),
         Block(BODY[0], [0.62, 0.10, 0.10, 0.68], "vertical_text"),
         Block(BODY[1], [0.45, 0.10, 0.10, 0.68], "vertical_text"),
         Block(HEAD, [0.19, 0.14, 0.03, 0.21], "vertical_text"),
         Block(".", [0.184, 0.63, 0.032, 0.017], "number")],
        "第一集" + BODY[0] + BODY[1] + HEAD + "一"),
    # No header, footer or number block: a list numeral at a column's head.
    7: ([Block(BODY[0], [0.60, 0.10, 0.10, 0.68], "vertical_text"),
         Block(BODY[1], [0.45, 0.10, 0.10, 0.68], "vertical_text")],
        BODY[0] + "一" + BODY[1]),
}
# A section heading at the start of the body, which the layout labelled
# header, at the page's right edge; engine B did not read its last character.
# The running foot and the folio are at the left edge.
PAGES[9] = ([Block("第五節某地之事", [0.80, 0.17, 0.03, 0.19], "header"),
             Block(BODY[0], [0.62, 0.10, 0.10, 0.68], "vertical_text"),
             Block(BODY[1], [0.45, 0.10, 0.10, 0.68], "vertical_text"),
             Block(HEAD, [0.16, 0.18, 0.023, 0.12], "footer"),
             Block("八九", [0.158, 0.62, 0.022, 0.03], "number")],
            "第五節某地之" + BODY[0] + BODY[1] + HEAD + "八九")
# The first body column printed right under the folio in the top margin (the
# running head is a row across the top, not one the profile measured); engine
# B did not read a character of it, and the numeral of an article heading
# below the next folio.
PAGES[10] = ([Block("35", [0.837, 0.159, 0.031, 0.02], "number"),
              Block("定他的軍事總策略如下", [0.844, 0.205, 0.032, 0.195], "vertical_text"),
              Block(BODY[0], [0.573, 0.239, 0.262, 0.647], "vertical_text"),
              Block("期四第刊月", [0.259, 0.16, 0.525, 0.021], "header")],
             "定他的事總策略如下" + BODY[0] + "期四第刊月")
PAGES[11] = ([Block("59", [0.829, 0.164, 0.032, 0.018], "number"),
              Block("第九條", [0.843, 0.212, 0.033, 0.075], "vertical_text"),
              Block(BODY[1], [0.789, 0.262, 0.089, 0.632], "vertical_text")],
             "第條" + BODY[1])
# A horizontal page: a heading centred above the body, a folio centred at the
# foot; engine B did not read the heading's numeral.
PAGES[12] = ([Block("卷一", [0.47, 0.08, 0.06, 0.03], "paragraph_title"),
              Block(BODY[0] + BODY[1], [0.10, 0.15, 0.80, 0.10], "text"),
              Block(BODY[2], [0.10, 0.30, 0.80, 0.05], "text"),
              Block("一", [0.48, 0.95, 0.04, 0.02], "number")],
             "卷" + BODY[0] + BODY[1] + BODY[2] + "一")
# Page 3 with the folio 一: engine B read the folio where engine A did, and
# the list numeral 一 opening the first body column, which engine A did not
# read - the same characters as the folio, but no second copy of it.
PAGES[13] = ([Block("一", [0.74, 0.68, 0.03, 0.02], "number"),
              Block(HEAD, [0.74, 0.18, 0.03, 0.20], "header"),
              Block(BODY[0], [0.60, 0.10, 0.10, 0.68], "vertical_text"),
              Block(BODY[1], [0.45, 0.10, 0.10, 0.68], "vertical_text")],
             "一" + HEAD + "一" + BODY[0] + BODY[1])
# Page 4 with the body's last character the folio's figure: engine A did not
# read it, engine B read it and the folio after the running foot.
PAGES[14] = ([Block(BODY[0], [0.10, 0.10, 0.80, 0.05], "text"),
              Block("共計人數凡", [0.10, 0.80, 0.80, 0.05], "text"),
              Block(HEAD, [0.10, 0.92, 0.30, 0.03], "footer"),
              Block("七", [0.85, 0.92, 0.05, 0.03], "number")],
             BODY[0] + "共計人數凡七" + HEAD + "七")
# A folio engine B read before the running head at the page's start, which
# engine A did not read at all: written as nothing, the head block's text is
# the running head alone and the page drops it whole.
PAGES[16] = ([Block(HEAD, [0.74, 0.18, 0.03, 0.20], "header"),
              Block(BODY[0], [0.60, 0.10, 0.10, 0.68], "vertical_text"),
              Block(BODY[1], [0.45, 0.10, 0.10, 0.68], "vertical_text")],
             "十三" + HEAD + BODY[0] + BODY[1])
# A folio of three figures engine A read in its own block and engine B not at
# all: a numeral, taken whatever its length.
PAGES[17] = ([Block("一二五", [0.74, 0.66, 0.03, 0.04], "number"),
              Block(HEAD, [0.74, 0.18, 0.03, 0.20], "header"),
              Block(BODY[0], [0.60, 0.10, 0.10, 0.68], "vertical_text"),
              Block(BODY[1], [0.45, 0.10, 0.10, 0.68], "vertical_text")],
             HEAD + BODY[0] + BODY[1])
# A horizontal page with its running head a row at the top and a volume mark
# beside it in that row (not a folio): a numeral of the mark engine B did not
# read.
PAGES[18] = ([Block(HEAD, [0.10, 0.03, 0.30, 0.03], "header"),
              Block("第三冊", [0.50, 0.03, 0.08, 0.03], "text"),
              Block(BODY[0], [0.10, 0.10, 0.80, 0.05], "text"),
              Block(BODY[1], [0.10, 0.20, 0.80, 0.05], "text")],
             HEAD + "第冊" + BODY[0] + BODY[1])
# A folio of three figures read after the body in engine A's stream, away
# from the running head: nothing but the switch says it is not text, and the
# page must not report it dropped.
PAGES[19] = ([Block(HEAD, [0.74, 0.18, 0.03, 0.20], "header"),
              Block(BODY[0], [0.60, 0.10, 0.10, 0.68], "vertical_text"),
              Block(BODY[1], [0.45, 0.10, 0.10, 0.68], "vertical_text"),
              Block("一二五", [0.74, 0.66, 0.03, 0.04], "number")],
             HEAD + BODY[0] + BODY[1])
# The fold between two leaves, where the book prints its running head twice
# (measured by the profile) and the leaf folios beside it: one only engine B
# read between the two copies, and one between the second copy and the left
# leaf's body, on a page with no folio block.
FOLD = {8: ([Block(BODY[0], [0.60, 0.10, 0.10, 0.30], "vertical_text"),
             Block(HEAD, [0.52, 0.17, 0.017, 0.09], "paragraph_title"),
             Block(HEAD, [0.46, 0.17, 0.017, 0.09], "paragraph_title"),
             Block(BODY[1], [0.30, 0.10, 0.10, 0.30], "vertical_text")],
            BODY[0] + HEAD + "四" + HEAD + "五" + BODY[1])}


# The budget: page 1's two folio questions, then a body disagreement (張/帳)
# the budget may leave unasked.
BUDGET = {15: ([Block("三", [0.74, 0.68, 0.03, 0.02], "number"),
                Block(HEAD, [0.74, 0.18, 0.03, 0.20], "header"),
                Block(BODY[0], [0.60, 0.10, 0.10, 0.68], "vertical_text"),
                Block(BODY[1], [0.45, 0.10, 0.10, 0.68], "vertical_text")],
               HEAD + "三" + BODY[0] + "日月盈昃辰宿列帳")}


# D24's budget: a folio question, two questions 裁決 answers 算 for engine A's
# 筍 (engine B a rare codepoint), and 筍 in text only engine A read, which the
# preference for engine A writes and D24 asks about while the budget lasts.
PROPAGATION = {21: ([Block("三", [0.74, 0.68, 0.03, 0.02], "number"),
                     Block(HEAD, [0.74, 0.18, 0.03, 0.20], "header"),
                     Block("天地玄筍宇宙洪荒", [0.60, 0.10, 0.10, 0.68], "vertical_text"),
                     Block("日月筍昃辰宿列張", [0.45, 0.10, 0.10, 0.68], "vertical_text"),
                     Block("寒來暑往筍甲乙收冬藏", [0.30, 0.10, 0.10, 0.68], "vertical_text")],
                    HEAD + "天地玄\U0002E155宇宙洪荒日月\U0002E155昃辰宿列張寒來暑往收冬藏")}


def run(pages, profile, extra=()):
    """Every page with 裁決 answering that the reading one engine read is printed."""
    model = stand_in.StandIn(census=0, judge=lambda a, b: a or b)
    with stand_in.book(pages, profile=profile) as root:
        out = stand_in.run(root, model, pages=",".join(str(p) for p in sorted(pages)), extra=extra)
        report = __import__("json").loads((root / "report.json").read_text(encoding="utf-8"))
    return out, report


def asked(record):
    return [(a["draft_reading"], a["writer_reading"]) for a in record["adjudications"]]


def c4(record):
    return [(c["engineA"], c["engineB"], c["before"], c["beforeBy"], c["after"], c["evidence"]["readBy"],
             c["evidence"]["blocks"], "folioCopy" in c["evidence"])
            for c in record["decisionChanges"] if c["decision"] == "C4"]


def main() -> int:
    # The band on its own.
    blocks = [{"text": "三", "box": [0.74, 0.68, 0.03, 0.02], "label": "number"},
              {"text": "第三", "box": [0.742, 0.40, 0.026, 0.05], "label": "vertical_text"},
              {"text": HEAD, "box": [0.74, 0.18, 0.03, 0.20], "label": "doc_title"},
              {"text": BODY[0], "box": [0.60, 0.10, 0.10, 0.68], "label": "vertical_text"},
              {"text": BODY[0] * 6, "box": [0.74, 0.10, 0.03, 0.68], "label": "vertical_text"}]
    none = SimpleNamespace(profile_data={})
    heads = SimpleNamespace(profile_data={"layout": {"runningHeads": [HEAD]}})
    check("band: a folio extends the band nowhere: the blocks in its column are not the band's",
          pp.furniture_band(blocks, [], none), {0: "folio"})
    check("band: the running head's column: short thin blocks no longer than it; not the body, nor a long "
          "block there", pp.furniture_band(blocks, [HEAD], heads),
          {0: "folio", 2: "running head", 1: "column of block 2"})
    # Text that is the book's furniture, with a second piece of evidence: a
    # folio's column (not the text alone).
    beside = [{"text": "三", "box": [0.74, 0.68, 0.03, 0.02], "label": "number"},
              {"text": HEAD + "一集", "box": [0.74, 0.18, 0.03, 0.20], "label": "vertical_text"},
              {"text": HEAD + "一集", "box": [0.30, 0.18, 0.03, 0.20], "label": "vertical_text"}]
    check("band: furniture text in a folio's column is an anchor; the same text elsewhere is not",
          pp.furniture_band(beside, [HEAD], heads), {0: "folio", 1: "column of block 0, furniture text"})
    # The first body column printed under the folio in the top margin, the
    # running head a row across the top: the folio's column is not the band.
    corner = [{"text": "35", "box": [0.837, 0.159, 0.031, 0.02], "label": "number"},
              {"text": "定他的軍事總策略如下", "box": [0.844, 0.205, 0.032, 0.195], "label": "vertical_text"},
              {"text": "期四第刊月", "box": [0.259, 0.16, 0.525, 0.021], "label": "header"}]
    check("band: a body column under a folio in the top margin is not the band's",
          pp.furniture_band(corner, [], none), {0: "folio"})
    # A wide running head's row: a short block beside it joins; a body line
    # below it does not.
    row = [{"text": HEAD, "box": [0.10, 0.03, 0.30, 0.03], "label": "header"},
           {"text": "第三冊", "box": [0.50, 0.03, 0.08, 0.03], "label": "text"},
           {"text": BODY[0], "box": [0.10, 0.10, 0.80, 0.05], "label": "text"}]
    check("band: the row of a wide running head", pp.furniture_band(row, [HEAD], heads),
          {0: "running head", 1: "row of block 0"})
    # What joins a column is short: no longer than the anchor, and thin.
    long = [{"text": HEAD, "box": [0.30, 0.10, 0.40, 0.50], "label": "header"},
            {"text": "第三", "box": [0.30, 0.10, 0.30, 0.70], "label": "text"},
            {"text": "第一二三四五", "box": [0.35, 0.65, 0.05, 0.10], "label": "text"},
            {"text": "第三", "box": [0.35, 0.65, 0.05, 0.10], "label": "text"}]
    check("band: not a block wider or taller than a margin's, nor one longer than the anchor",
          pp.furniture_band(long, [HEAD], heads), {0: "running head", 3: "column of block 0"})
    # A profile that measured its head's type size: a block reading the head
    # far larger (a title) is no anchor; the head with its volume beside it at
    # the head's size is.
    sized = SimpleNamespace(profile_data={"layout": {"runningHeads": [HEAD], "runningHeadGlyph": {HEAD: 0.02}}})
    titles = [{"text": HEAD, "box": [0.74, 0.18, 0.03, 0.08], "label": "vertical_text"},
              {"text": HEAD, "box": [0.50, 0.10, 0.06, 0.30], "label": "paragraph_title"},
              {"text": HEAD + "一集", "box": [0.20, 0.18, 0.03, 0.12], "label": "vertical_text"},
              {"text": HEAD + "一集", "box": [0.10, 0.10, 0.06, 0.45], "label": "paragraph_title"}]
    check("band: the head's type size: a head at it, the head with a volume at it; not the same text as a title",
          pp.furniture_band(titles, [HEAD], sized), {0: "running head", 2: "head's size, furniture text"})
    # A label is not evidence alone: a section heading labelled header, a
    # signature labelled number; a header block reading the running head with
    # a character or two beside it is.
    labelled = [{"text": "第五節某地之事", "box": [0.80, 0.17, 0.03, 0.19], "label": "header"},
                {"text": "某甲序", "box": [0.44, 0.41, 0.03, 0.06], "label": "number"},
                {"text": HEAD + "一集", "box": [0.16, 0.18, 0.023, 0.14], "label": "header"},
                {"text": BODY[0], "box": [0.60, 0.10, 0.10, 0.68], "label": "vertical_text"}]
    check("band: a heading labelled header, a signature labelled number: not anchors",
          pp.furniture_band(labelled, [HEAD], heads), {2: "label header, furniture text"})
    check("band: a block read as the profile's running head is an anchor",
          pp.furniture_band(blocks, [HEAD], heads)[2], "running head")
    check("band: no anchor, no band", pp.furniture_band(blocks[1:], [], none), {})
    check("folio_copies: the same characters only; figures or a mark vouch for nothing",
          ([pp.folio_copies([{"text": t, "label": "number"}], r) for t, r in
            (("12", "十二"), ("三", "三"), ("三", "一"), (".", "一"), ("三", ""))]), [[], [0], [], [], []])

    # The running head a profile measured: the band's anchor on the pages
    # that print one.
    profile = {"preferEngine": "adjudicate", "layout": {"runningHeads": [HEAD]}}
    off, report_off = run(PAGES, profile)
    on, report_on = run(PAGES, profile, ["--folio-furniture"])
    fold_profile = {"preferEngine": "adjudicate", "layout": {"runningHeads": [HEAD]}}
    fold_off, _ = run(FOLD, fold_profile)
    fold_on, _ = run(FOLD, fold_profile, ["--folio-furniture"])

    check("switch off: every one-sided reading asked, as before",
          {p: asked(off[p][0]) for p in PAGES},
          {1: [("三", ""), ("", "三")], 2: [("", "十二")], 3: [("", "一")], 4: [("", "張")],
           5: [("", "黃"), ("之", "")], 6: [("", "一"), ("", "一")], 7: [("", "一")], 9: [("事", "")],
           10: [("軍", "")], 11: [("九", "")], 12: [("一", "")], 13: [("", "一")], 14: [("", "七")],
           16: [("", "十三")], 17: [("一二五", "")], 18: [("三", "")], 19: [("一二五", "")]})
    check("switch off: no C4 entry, no provenance key, run report off",
          ([c4(off[p][0]) for p in PAGES], ["folioFurniture" in off[p][0]["provenance"] for p in PAGES],
           report_off["folioFurniture"], report_off["folioFurnitureResolved"]),
          ([[]] * len(PAGES), [False] * len(PAGES), "off", 0))

    # The measured shapes: not asked, written as nothing.
    check("folio in its own block, and its copy engine B read after the head: neither asked",
          (asked(on[1][0]), c4(on[1][0])),
          ([], [("三", "", None, "adjudicate", "", "A", [0], False),
                ("", "三", None, "adjudicate", "", "B", [1, 2], True)]))
    check("... and the page's text has no folio", ("三" in pp.CJK(on[1][1]), BODY[0] + BODY[1] in pp.CJK(on[1][1])),
          (False, True))
    check("the folio engine B read after the head, at the page's end (a folio engine A read as a mark)",
          c4(on[6][0]), [("", "一", None, "adjudicate", "", "B", [3], False)])
    check("a folio before the running head: not asked; its entry says the head block then went whole",
          (asked(on[16][0]), c4(on[16][0]),
           [c["evidence"].get("blocksDropped") for c in on[16][0]["decisionChanges"] if c["decision"] == "C4"]),
          ([], [("", "十三", None, "adjudicate", "", "B", [0], False)], [[{"block": 0, "text": HEAD}]]))
    # Without the learned running head (--no-learned-heads): the learned head
    # (the default) leaves the head block out whatever C4 does.
    unlearned, _ = run({16: PAGES[16]}, profile, ["--no-learned-heads"])
    check("... where with the switch off (and --no-learned-heads) the folio 裁決 kept left the head in the text; "
          "the learned running head leaves it out",
          (HEAD in pp.CJK(unlearned[16][1]), HEAD in pp.CJK(off[16][1]), HEAD in pp.CJK(on[16][1])),
          (True, False, False))
    check("a folio of three figures in its own block: not asked",
          (asked(on[17][0]), c4(on[17][0])), ([], [("一二五", "", None, "adjudicate", "", "A", [0], False)]))
    check("a folio read away from the running head: not asked, not reported dropped, the page clean",
          (asked(on[19][0]), c4(on[19][0]), on[19][0]["readingsDropped"], on[19][0]["doubts"]),
          ([], [("一二五", "", None, "adjudicate", "", "A", [3], False)], [], []))
    check("a volume mark in the running head's row: its numeral not asked",
          (asked(on[18][0]), c4(on[18][0])), ([], [("三", "", None, "adjudicate", "", "A", [1], False)]))
    check("fold: a leaf folio between the running head's two copies, not asked",
          c4(fold_on[8][0]), [("", "四", None, "adjudicate", "", "B", [1, 2], False)])

    # What it must leave alone: asked as before.
    check("a list numeral opening the first body column after the head column: asked",
          (asked(on[3][0]), c4(on[3][0]), "一" + BODY[0] in pp.CJK(on[3][1])), ([("", "一")], [], True))
    check("a list numeral opening the body that is the folio's figure, the folio read by both: asked",
          (asked(on[13][0]), c4(on[13][0])), ([("", "一")], []))
    check("the body's last character before the running foot, the folio's figure read by both: asked",
          (asked(on[14][0]), c4(on[14][0])), ([("", "七")], []))
    check("numerals engine B read between the head column and the body, the folio read as figures: asked",
          (asked(on[2][0]), c4(on[2][0])), ([("", "十二")], []))
    check("the body's last character before the running foot: asked",
          (asked(on[4][0]), c4(on[4][0])), ([("", "張")], []))
    check("body text near the top, below a running head row: asked",
          (asked(on[5][0]), c4(on[5][0])), ([("", "黃"), ("之", "")], []))
    check("a heading at the start of the body, outside the band: asked",
          asked(on[6][0]), [("", "一")])
    check("a section heading at the start of the body the layout labelled header: asked",
          (asked(on[9][0]), c4(on[9][0]), "第五節某地之事" in pp.CJK(on[9][1])), ([("事", "")], [], True))
    check("the first body column under a folio in the top margin: asked, its text whole",
          (asked(on[10][0]), c4(on[10][0]), "定他的軍事總策略如下" in pp.CJK(on[10][1])), ([("軍", "")], [], True))
    check("an article heading's numeral under a folio in the top margin: asked, the heading whole",
          (asked(on[11][0]), c4(on[11][0]), "第九條" in pp.CJK(on[11][1])), ([("九", "")], [], True))
    check("a heading above the body in the column of a folio centred at the foot: asked, the heading whole",
          (asked(on[12][0]), c4(on[12][0]), pp.CJK(on[12][1]).startswith("卷一")), ([("一", "")], [], True))
    check("a list numeral at a column's head on a page with no furniture blocks: asked",
          (asked(on[7][0]), c4(on[7][0])), ([("", "一")], []))
    check("fold: a leaf folio between the running head and the body, with no folio block: asked",
          (asked(fold_off[8][0]), asked(fold_on[8][0])), ([("", "四"), ("", "五")], [("", "五")]))
    check("every page it leaves alone: the same text as with the switch off",
          [p for p in (2, 3, 4, 5, 7, 9, 10, 11, 12, 13, 14) if on[p][1] != off[p][1]], [])

    # The budget (--max-adjudications): a question not asked takes the budget
    # it would have taken, so the rest of the page is decided as with the
    # switch off; with the budget spent before it, it is written as off.
    budget = {}
    for most in ("2", "1"):
        for label, extra in (("off", []), ("on", ["--folio-furniture"])):
            got, _ = run(BUDGET, profile, ["--max-adjudications", most, *extra])
            record = got[15][0]
            budget[most, label] = (asked(record), [(d["engineA"], d["engineB"], d["resolved"], d["resolved_by"])
                                                   for d in record["engineDisagreements"]
                                                   if not d["resolved_by"].startswith("folio-furniture")],
                                   c4(record), [c["decision"] for c in record["decisionChanges"]], got[15][1])
    check("budget 2: the two folio questions not asked; the body's disagreement unasked as with the switch off",
          (budget["2", "on"][0], budget["2", "on"][1] == budget["2", "off"][1], budget["2", "on"][3]),
          ([], True, ["C4", "C4"]))
    check("budget 2: ... and the text is the switch off's but for the folios",
          pp.CJK(budget["2", "on"][4]), pp.CJK(budget["2", "off"][4]).replace("三", ""))
    check("budget 1: the first folio question not asked; the second, the budget spent, written as with it off",
          (budget["1", "on"][0], budget["1", "on"][1] == budget["1", "off"][1],
           [entry[:2] for entry in budget["1", "on"][2]], pp.CJK(budget["1", "on"][4]).count("三")),
          ([], True, [("三", "")], 1))

    # D24 propagates a verdict with the budget the questions left: a question
    # not asked leaves it as asked would.
    propagated = {}
    for most in ("3", "4"):
        for label, extra in (("off", []), ("on", ["--folio-furniture"])):
            model = stand_in.StandIn(census=0, judge=lambda a, b: "算" if b == "\U0002E155" else a or b)
            with stand_in.book(PROPAGATION, profile={"preferEngine": "A", "layout": {"runningHeads": [HEAD]}}) as root:
                got = stand_in.run(root, model, pages="21", extra=["--max-adjudications", most, *extra])
            record = got[21][0]
            propagated[most, label] = ([a.get("askedFor") for a in record["adjudications"] if a.get("askedFor")],
                                       pp.CJK(got[21][1]))
    check("D24's budget: spent by the questions, a question not asked included; left, as with it off",
          [(propagated[most, "on"][0], propagated[most, "on"][1] == propagated[most, "off"][1].replace("三", "", 1))
           for most in ("3", "4")], [([], True), (["D24"], True)])

    # With --no-adjudicate nothing is asked, and the switch does nothing.
    still = {label: run({1: PAGES[1]}, profile, ["--no-adjudicate", *extra])
             for label, extra in (("off", []), ("on", ["--folio-furniture"]))}
    check("--no-adjudicate: the switch writes nothing as furniture; the page as with it off",
          (c4(still["on"][0][1][0]), still["on"][1]["folioFurnitureResolved"],
           still["on"][0][1][1] == still["off"][0][1][1]), ([], 0, True))

    check("switch on: sealed in provenance, counted in the run report",
          ([on[p][0]["provenance"].get("folioFurniture") for p in PAGES], report_on["folioFurniture"],
           report_on["folioFurnitureResolved"], report_on["decisionChanges"].get("C4")),
          (["on"] * len(PAGES), "on", 7, 7))
    check("switch on: each written as nothing is a disagreement settled as furniture",
          sorted(d["resolved_by"] for p in PAGES for d in on[p][0]["engineDisagreements"]
                 if d["resolved_by"].startswith("folio-furniture")),
          ["folio-furniture-A", "folio-furniture-A", "folio-furniture-A", "folio-furniture-A", "folio-furniture-B",
           "folio-furniture-B", "folio-furniture-B"])
    check("furniture_text: a running head, and one with at most two characters beside it; not a heading",
          [pp.furniture_text(t, [HEAD], frozenset()) for t in (HEAD, HEAD + "一集", HEAD + "第一集", "第五節某地之事", "")],
          [True, True, False, False, False])
    check("folio_copies: not where engine B read the folio's characters at its place too",
          [pp.folio_copies([{"text": "三", "label": "number"}], "三", lambda k: there) for there in ("", "三", "四")],
          [[0], [], [0]])
    # Resume: a page sealed with the switch is not current for a run without
    # it, nor the reverse.
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "page-0001.json"
        markdown = BODY[0]
        with_it = pp.decision_provenance(SimpleNamespace(prefer_engine="A", fallback_engine="A",
                                                         folio_furniture=True))
        without = pp.decision_provenance(SimpleNamespace(prefer_engine="A", fallback_engine="A"))
        job = SimpleNamespace(out_json=out, out_md=out.with_suffix(".md"))
        results = []
        for sealed_with, run_with in ((with_it, without), (without, with_it), (with_it, with_it), (without, without)):
            record = {"schemaVersion": pp.SCHEMA_VERSION, "status": "complete", "scanPage": 1,
                      "provenance": {**sealed_with, "markdownSha256": pp.sha256_bytes(markdown.encode("utf-8"))}}
            record["provenance"]["jsonPayloadSha256"] = pp.sha256_bytes(pp.canonical_json_bytes(record))
            out.with_suffix(".md").write_text(markdown, encoding="utf-8")
            out.write_bytes(pp.canonical_json_bytes(record))
            results.append(pp.validate_completion(job, run_with)[0])
    check("resume: a page is current only for a run with the same setting", results, [False, False, True, True])
    print(f"{'FAIL' if failures else 'ok  '} {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
