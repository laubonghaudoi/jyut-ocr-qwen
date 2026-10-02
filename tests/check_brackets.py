"""Checks for the bracket rule: numerals the other engine's brackets account for,
and the brackets the engines read written back into punctuated text.

Usage: python3 tests/check_brackets.py   (exits non-zero on the first failure)
"""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import proofread_pages as pp  # noqa: E402

failures = 0


def check(name: str, got, want) -> None:
    global failures
    if got != want:
        failures += 1
        print(f"FAIL {name}: got {got!r}, want {want!r}")
    else:
        print(f"ok   {name}")


# engine_gaps: characters as CJK() counts them, raw text between them.
chars, gaps = pp.engine_gaps("見者可知。（內便")
check("engine_gaps characters", chars, "見者可知內便")
check("engine_gaps gaps", gaps, ["", "", "", "", "。（", "", ""])
check("bracket kinds", pp.bracket_kinds("）。(︵"), ["）", "（", "（"])

# explain_by_brackets, on readings measured on one page (engine A printed every bracket).
check("insertion: B's 一 is A's opening bracket", pp.explain_by_brackets("", ["。（"], "一", 0), "")
check("B's 八七一 is A's （七）", pp.explain_by_brackets("七", ["（", "）"], "八七一", 0), "七")
check("B's 八一 is A's （一）", pp.explain_by_brackets("一", ["（", "）"], "八一", 0), "一")
check("B's 一二十七 is A's （二）十七", pp.explain_by_brackets("二十七", ["（", "）", "", ""], "一二十七", 0), "二十七")
check("B's 一八五一 is A's ）（五）", pp.explain_by_brackets("五", ["）（", "）"], "一八五一", 0), "五")
check("brackets leave 三 against 二", pp.explain_by_brackets("三", ["）（", "）"], "一一二一", 0), "二")
check("a 三 beside a bracket is not the bracket",
      pp.explain_by_brackets("三", ["（", "）"], "一一三", 0), None)
check("B printed the bracket itself: its 一 is not the bracket",
      pp.explain_by_brackets("", ["（"], "一", 1), None)
check("no bracket in A: nothing explained", pp.explain_by_brackets("", ["。"], "一", 0), None)
check("a quote mark is not a bracket", pp.explain_by_brackets("", ["」"], "一", 0), None)
check("more numerals than brackets: not explained", pp.explain_by_brackets("", ["（"], "一一", 0), None)


def segments_for(a_text: str, b_text: str):
    segs = pp.fuse_numeral_runs(pp.align_drafts(a_text, b_text))
    a_starts, b_starts, a_at, b_at = [], [], 0, 0
    for seg in segs:
        a_starts.append(a_at)
        b_starts.append(b_at)
        a_at += len(seg["a"])
        b_at += len(seg["b"])
    return segs, a_starts, b_starts


# bracket_explanation on a line of engine A and engine B text from that page.
A = "貨物一空。見者可知。（內便只有空架）（三）八十五號瑞記"
B = "貨物一空見者可知一內便只有空架一一二一八十五號瑞記"
segs, a_starts, b_starts = segments_for(A, B)
settled = [pp.bracket_explanation(s, a, b, pp.engine_gaps(A), pp.engine_gaps(B))
           for s, a, b in zip(segs, a_starts, b_starts) if s["tag"] != "equal"]
check("insertion settled for engine A", settled[0], ("A", ""))
check("bracketed 三 reduced to 三 against 二", (settled[1][0], settled[1][1]["a"], settled[1][1]["b"]),
      ("reduced", "三", "二"))
check("reduced question keeps the engines' readings", settled[1][1]["bracketReduced"],
      {"engineA": "三", "engineB": "一一二一"})
# The other way round: engine B printed the brackets, engine A read strokes.
segs, a_starts, b_starts = segments_for("列入一括爲", "列入）括爲")
seg = next(s for s in segs if s["tag"] != "equal")
i = segs.index(seg)
check("engine B's bracket settles engine A's 一",
      pp.bracket_explanation(seg, a_starts[i], b_starts[i], pp.engine_gaps("列入一括爲"), pp.engine_gaps("列入）括爲")),
      ("B", ""))
check("characters that are not where the segment says: left alone",
      pp.bracket_explanation({"a": "", "b": "一"}, 3, 0, pp.engine_gaps("甲乙丙"), pp.engine_gaps("丁")), None)

# engine_brackets_merged: brackets placed in the merged text.
segs = pp.align_drafts("甲（乙）丙", "甲乙丙")
check("brackets of agreed text", pp.engine_brackets_merged(pp.engine_gaps("甲（乙）丙"), "a", segs, [s["a"] for s in segs]),
      [(1, "（"), (2, "）")])
segs = pp.align_drafts("壽（一兩間", "壽一兩間")
pieces = ["" if s["tag"] != "equal" else s["a"] for s in segs]
check("bracket beside a disagreement resolved to nothing",
      pp.engine_brackets_merged(pp.engine_gaps("壽（一兩間"), "a", segs, pieces), [(1, "（")])
check("segments that do not spell the engine's text", pp.engine_brackets_merged(pp.engine_gaps("甲乙"), "a", segs, pieces), None)

# place_brackets: written in, kept, moved, left alone.
span = "德壽兩間係棺材舖正合"
check("brackets written in",
      pp.place_brackets("德壽。兩間係棺材舖。正合", span, {(2, "（"): 1, (8, "）"): 1}),
      ("德壽。（兩間係棺材舖。）正合", 2, 0))
check("the punctuator's own bracket at the place is kept",
      pp.place_brackets("德壽。（兩間係棺材舖。正合", span, {(2, "（"): 1, (8, "）"): 1}),
      ("德壽。（兩間係棺材舖。）正合", 1, 0))
check("a bracket one character off is moved",
      pp.place_brackets("德壽。兩（間係棺材舖。）正合", span, {(2, "（"): 1, (8, "）"): 1}),
      ("德壽。（兩間係棺材舖。）正合", 1, 1))
check("a bracket far from any the engines read is kept",
      pp.place_brackets("德壽兩間係棺（材舖正合", span, {(8, "）"): 1}),
      ("德壽兩間係棺（材舖）正合", 1, 0))
check("closing before opening in one gap",
      pp.place_brackets("空架三八", "空架三八", {(2, "）"): 1, (2, "（"): 1, (3, "）"): 1}),
      ("空架）（三）八", 3, 0))
check("ASCII brackets count as brackets",
      pp.place_brackets("字(卽數碼)此", "字卽數碼此", {(1, "（"): 1, (4, "）"): 1}),
      ("字(卽數碼)此", 0, 0))
check("text whose characters are not the span: unchanged",
      pp.place_brackets("甲乙", "甲丙", {(1, "（"): 1}), ("甲乙", 0, 0))

sys.exit(1 if failures else 0)
