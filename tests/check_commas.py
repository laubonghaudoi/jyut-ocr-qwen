#!/usr/bin/env python3
"""Checks for a comma that is a minority shape on its page (minority_commas): each is re-read
on a small crop of its own place, one gap at a time, and only that gap changes.

No model, no GPU, no corpus.  The shape is the one measured on a page printed with
circles: the punctuator read a broken circle as ， in one block and a printing speck as ，
in another; each block's shapes were then a subset of the other's, so the old re-read
("a shape in exactly one block") fired on neither, and the page kept both commas.

Usage: python3 tests/check_commas.py   (exits non-zero on the first failure)
"""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
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


CIRCLES = "天地玄黃。宇宙洪荒。。"
BOTH = "日月，盈昃。辰宿列張。。"
check("one block of circles, two with a comma among circles, thirteen of circles: both comma blocks",
      pp.minority_commas([CIRCLES, BOTH, BOTH] + [CIRCLES] * 13), [1, 2])
check("... where the old test (a shape in exactly one block) fired on neither",
      [i for i, mine in enumerate(set(c for c in t if c in "。，") for t in [CIRCLES, BOTH, BOTH] + [CIRCLES] * 13)
       if mine - set().union(*(set(c for c in t if c in "。，") for j, t in
                               enumerate([CIRCLES, BOTH, BOTH] + [CIRCLES] * 13) if j != i))], [])
check("a page where most blocks carry both: nothing", pp.minority_commas([BOTH] * 5 + [CIRCLES]), [])
check("a page of commas: nothing", pp.minority_commas(["甲，乙，丙。", "丁，戊，己。", "庚，辛。"]), [])
check("one comma block on a page of three: re-read", pp.minority_commas([CIRCLES, BOTH, CIRCLES]), [1])
check("commas more than a tenth of the marks: nothing",
      pp.minority_commas(["甲，乙，丙，丁，戊。", CIRCLES, CIRCLES, CIRCLES]), [])
check("no marks at all: nothing", pp.minority_commas(["天地玄黃", "宇宙洪荒"]), [])
check("the counts the re-read is told", pp.minority_commas([CIRCLES, BOTH, CIRCLES], counts=True), (3, 1, 1, 9))
check("where the commas are", pp.comma_gaps("甲，乙丙，丁。"), [1, 3])
check("a comma's gap rewritten", [pp.replace_gap("甲，乙丙，丁。", 3, mark) for mark in ("。。", "")],
      ["甲，乙丙。。丁。", "甲，乙丙丁。"])
check("the re-read's answer", [pp.parse_gap_answer(a) for a in ("構件…\n符號：。。", "符號：無", "符號：，", "睇唔清")],
      ["。。", "", "，", None])

# A page of seven blocks printed with circles: the punctuator wrote ， after the third
# character of blocks 1 and 4 (a broken circle, a speck).  Each comma is asked about on
# its own; the answers are circles, and nothing else on the page changes.
TEXTS = ["天地玄黃宇宙洪荒日月盈昃", "辰宿列張寒來暑往秋收冬藏", "閏餘成歲律呂調陽雲騰致雨",
         "露結為霜金生麗水玉出崑岡", "劍號巨闕珠稱夜光果珍李柰", "菜重芥薑海鹹河淡鱗潛羽翔",
         "龍師火帝鳥官人皇始制文字"]
COMMA_AT = {1, 4}


def punctuate(span: str) -> str:
    """Circles after the sixth and (doubled) the last character; the misread ，."""
    k = next(i for i, t in enumerate(TEXTS) if t == span)
    comma = "，" if k in COMMA_AT else ""
    return span[:3] + comma + span[3:6] + "。" + span[6:] + "。。"


def page(gap):
    blocks = [stand_in.block(t, [0.85 - 0.12 * i, 0.1, 0.06, 0.6]) for i, t in enumerate(TEXTS)]
    model = stand_in.StandIn(census=2, punctuate=punctuate, gap=gap)
    with stand_in.book({1: (blocks, "".join(TEXTS))}) as root:
        record, markdown = stand_in.run(root, model)[1]
    return record, markdown, model


record, markdown, model = page("。")
check("page: each minority comma is asked about once, on its own",
      [kind for kind in model.kinds() if kind in ("gap-recheck", "shape-recheck")], ["gap-recheck"] * 2)
want = [t[:3] + ("。" if i in COMMA_AT else "") + t[3:6] + "。" + t[6:] + "。。" for i, t in enumerate(TEXTS)]
check("page: the commas are circles, every other mark as written", pp.CJK(markdown), "".join(TEXTS))
check("page: marks as the page prints them", [line for line in markdown.split("\n") if line.strip()], want)
check("page: each pass records the gap it changed",
      [(p["block"], p.get("gapRechecks")) for p in record["punctuationPasses"] if p.get("gapRechecks")],
      [(1, [{"gap": 3, "before": "，", "after": "。"}]), (4, [{"gap": 3, "before": "，", "after": "。"}])])
record, markdown, model = page("，")
check("page: a comma the crop shows is kept",
      [line for line in markdown.split("\n") if line.strip()][1], TEXTS[1][:3] + "，" + TEXTS[1][3:6] + "。"
      + TEXTS[1][6:] + "。。")
record, markdown, model = page(None)
check("page: an answer that names no mark changes nothing",
      [line for line in markdown.split("\n") if line.strip()][4], TEXTS[4][:3] + "，" + TEXTS[4][3:6] + "。"
      + TEXTS[4][6:] + "。。")

sys.exit(1 if failures else 0)
