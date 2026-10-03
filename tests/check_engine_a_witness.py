#!/usr/bin/env python3
"""Offline checks of the punctuation pass's two uses of engine A's marks as a
witness: --engine-a-confirms-first-answer and --census-skip-over-ceiling
(both on by default; --no-<switch> turns one off).

No model, no GPU, no corpus.  The punctuator is handed the merged characters
alone, so engine A's own marks are an independent reading of the same print.

- A first answer that keeps the characters, is outside the census by more
  than the tolerance, and wrote exactly engine A's marks at every gap of a
  stretch that is engine A's own reading is kept, and no retry is asked.  The
  pass says so (reason, firstAnswerKept) and the page keeps its
  punctuation-count-mismatch doubt.
- Where engine A's marks alone hold more places than the census ceiling of the
  stretch, the census is not asked: its count would be discarded.  The pass
  goes on as after a discarded census and says so (censusNotAsked).

The look-alikes each rule must leave alone are checked beside it: an answer
that differs from engine A at one gap, a stretch holding a character engine A
did not read, a stretch engine A read no mark in, engine A's single circle in
a book of doubled circles, an answer that drifted off its stretch, an answer
refused for its characters; engine A's marks at the ceiling and not above it,
a LaTeX delimiter's bracket, markup and note markers, which are no marks.

Each is checked on a whole page too (proofread_pages.main with the stand-in),
with what it seals: the pass's record, decisionChanges, the doubt, provenance
and the run report.

Usage:
    python3 tests/check_engine_a_witness.py
"""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
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


FIRST = ["--engine-a-confirms-first-answer"]
SKIP = ["--census-skip-over-ceiling"]
NO_FIRST = ["--no-engine-a-confirms-first-answer"]
NO_SKIP = ["--no-census-skip-over-ceiling"]
KEPT = " (first answer kept: its marks are engine A's)"


def equal(text: str) -> dict:
    return {"tag": "equal", "a": text, "b": text}


def witnessed(text_a: str, text_b: str | None = None, segments: list[dict] | None = None):
    """The merged text of a page engine A read as TEXT_A (engine B the same
    characters, or TEXT_B; or the merge SEGMENTS, each written as engine B's
    side), and a pass's witness over the whole of it: engine A's marks at its
    gaps and whether it is engine A's own stretch."""
    if segments is None:
        segments = pp.align_drafts(text_a, pp.CJK(text_a) if text_b is None else text_b)
        pieces = [seg["a"] or seg["b"] for seg in segments]
    else:
        pieces = [seg["b"] for seg in segments]
    span = "".join(pieces)
    found = pp.engine_a_witness(text_a, segments, pieces)
    if found is None:
        return span, None
    tied, own = found
    return span, (pp.gaps_of(tied, 0, len(span)), pp.engine_a_stretch(own, 0, len(span)))


def written(span: str, gaps) -> str:
    """SPAN with the marks GAPS at its gaps."""
    return "".join(gap + char for gap, char in zip(gaps, span)) + gaps[len(span)]


class Arguments:
    max_tokens = 100

    def __init__(self, first: bool = True, skip: bool = True, profile: dict | None = None) -> None:
        self.engine_a_confirms_first_answer, self.census_skip_over_ceiling = first, skip
        self.profile_data = profile


class Answers:
    """Stands in for the model: a census, then the answers in turn."""

    def __init__(self, census, answers: list[str]) -> None:
        self.census, self.answers, self.kinds = census, list(answers), []

    def ask_answering(self, system, prompt, crop, max_tokens, kind=None):
        self.kinds.append(kind)
        if kind == "census":
            return f"符號：{self.census}\n形狀：略", {}
        return self.answers.pop(0), {}


def part(span: str, witness, census, answers: list[str], arguments: Arguments | None = None, **more):
    client = Answers(census, answers)
    out, record, _ = pp.punctuate_part(client, arguments or Arguments(), None, span, "", 60.0,
                                       witness=witness, **more)
    return out, record, client.kinds


# --- Engine A's marks as a witness.
A = "天地玄黃，宇宙洪荒。日月盈昃，辰宿列張。"
span, witness = witnessed(A)
check("witness: engine A's marks at the merged text's gaps, and its own stretch",
      (span, written(span, witness[0]), witness[1]), (pp.CJK(A), A, True))
check("witness: vertical forms and ASCII brackets are the vocabulary's brackets",
      witnessed("天︵地︶玄(黃)")[1][0], ["", "（", "）", "（", "）"])
# Markup in engine A's gaps is no print: a LaTeX delimiter's bracket, an HTML
# tag (and what its attributes hold).  A note marker is no mark of the vocabulary.
noted = "天地，玄黃\\(^{①}宇宙<a title=\"(x)\"></a>洪荒②。"
check("witness: a LaTeX delimiter, an HTML tag and a note marker are no marks",
      written(*witnessed(noted)[0:1], witnessed(noted)[1][0]), "天地，玄黃宇宙洪荒。")
segments = pp.align_drafts(noted, pp.CJK(noted))
check("... where engine A's marks as the partial rescue ties them count the delimiter's bracket (unchanged)",
      "".join(pp.gaps_of(pp.engine_marks_merged(noted, segments, [seg["a"] for seg in segments]))), "，（）（。")
check("witness: the brackets of printed text inside LaTeX or markup stay marks (a gap's closing marks first)",
      witnessed("天地$^{①}(2)$玄黃<sup>(3)</sup>宇宙")[1][0], ["", "", "）（", "", "）（", "", ""])
check("witness: none when the segments do not spell engine A's text",
      witnessed("天地，玄黃", segments=[equal("天地玄")])[1], None)

# A stretch of engine A's own reading: every character in an exact place, consecutive.
own = pp.engine_a_witness("天地玄黃", [equal("天地玄黃")], ["天地玄黃"])[1]
check("own stretch: engine A's characters in place", (own, pp.engine_a_stretch(own, 0, 4), pp.engine_a_stretch(own, 1, 2)),
      ([0, 1, 2, 3], True, True))
check("own stretch: not an empty one, nor one past the text", (pp.engine_a_stretch(own, 0, 0), pp.engine_a_stretch(own, 2, 3)),
      (False, False))
inserted = [equal("天地"), {"tag": "insert", "a": "", "b": "乙"}, equal("玄黃")]
own = pp.engine_a_witness("天地：玄黃", inserted, [seg["b"] for seg in inserted])[1]
check("own stretch: not with a character only engine B read in it; beside it, yes",
      (own, pp.engine_a_stretch(own, 0, 5), pp.engine_a_stretch(own, 0, 2), pp.engine_a_stretch(own, 3, 2)),
      ([0, 1, None, 2, 3], False, True, True))
replaced = [equal("甲乙"), {"tag": "replace", "a": "丙", "b": "戊己"}, equal("丁")]
own = pp.engine_a_witness("甲乙丙，丁", replaced, [seg["b"] for seg in replaced])[1]
check("own stretch: not with a replacement of another length in it",
      (own, pp.engine_a_stretch(own, 0, 5), pp.engine_a_stretch(own, 4, 1)), ([0, 1, None, None, 3], False, True))
substituted = [equal("甲乙"), {"tag": "replace", "a": "丙", "b": "戊"}, equal("丁")]
own = pp.engine_a_witness("甲乙丙，丁", substituted, [seg["b"] for seg in substituted])[1]
check("own stretch: a one-for-one substitution keeps its place", (own, pp.engine_a_stretch(own, 0, 4)),
      ([0, 1, 2, 3], True))
left_out = [equal("天地"), {"tag": "delete", "a": "日月", "b": ""}, equal("玄黃")]
tied, own = pp.engine_a_witness("天地日，月玄黃", left_out, [seg["b"] for seg in left_out])
check("own stretch: not across characters of engine A's the merge left out (their marks are dropped)",
      (own, "".join(pp.gaps_of(tied)), pp.engine_a_stretch(own, 0, 4), pp.engine_a_stretch(own, 2, 2)),
      ([0, 1, 4, 5], "", False, True))

# The comparison, gap by gap.
check("equal: the same marks at every gap", pp.first_answer_confirmed(span, A, witness, False), True)
check("equal: not when one gap differs (a mark of another kind)",
      pp.first_answer_confirmed(span, A.replace("，", "、", 1), witness, False), False)
check("equal: not when the answer has a mark more", pp.first_answer_confirmed(span, A.replace("宇", "「宇"), witness, False),
      False)
check("equal: not when the answer has a mark less", pp.first_answer_confirmed(span, A[:-1], witness, False), False)
check("equal: not when a mark stands at another gap",
      pp.first_answer_confirmed(span, "天地玄，黃宇宙洪荒。日月盈昃，辰宿列張。", witness, False), False)
check("equal: not on other characters", pp.first_answer_confirmed(span, A.replace("玄", "元"), witness, False), False)
check("equal: never without a witness", pp.first_answer_confirmed(span, A, None, False), False)
check("equal: never where the stretch is not engine A's own",
      pp.first_answer_confirmed(span, A, (witness[0], False), False), False)
check("equal: never where engine A read no mark",
      pp.first_answer_confirmed(span, span, ([""] * (len(span) + 1), True), False), False)
check("equal: a book of doubled circles - engine A's single circle is no witness",
      pp.first_answer_confirmed(span, A, witness, True), False)
commas = A.replace("。", "，")
check("... its other marks are", pp.first_answer_confirmed(span, commas, witnessed(commas)[1], True), True)
circles = A.replace("。", "。。")
check("... nor is a doubled circle a single one",
      (pp.first_answer_confirmed(span, A, witnessed(circles)[1], False),
       pp.first_answer_confirmed(span, circles, witnessed(circles)[1], True)), (False, True))
titled = "天地《玄黃》宇宙︵洪荒︶。"
t_span, t_witness = witnessed(titled)
check("equal: brackets by the vocabulary's form, whatever form engine A wrote",
      pp.first_answer_confirmed(t_span, "天地《玄黃》宇宙（洪荒）。", t_witness, False), True)
check("equal: 〈〉 is not 《》", pp.first_answer_confirmed(t_span, "天地〈玄黃〉宇宙（洪荒）。", t_witness, False), False)
check("equal: the three bullets are one shape, a run of leader dots one mark",
      pp.first_answer_confirmed("天地玄黃", "⦿天地……玄黃。", witnessed("●天地…………玄黃。")[1], False), True)
# What is no mark of the vocabulary is not compared: a figure, a note marker.
dated = "天地玄黃（1997），宇宙洪荒②。日月盈昃，辰宿列張。"
d_span, d_witness = witnessed(dated)
check("equal: figures and note markers are not compared",
      (pp.first_answer_confirmed(d_span, dated.replace("1997", "").replace("②", ""), d_witness, False),
       pp.first_answer_confirmed(d_span, dated.replace("②", "⑦"), d_witness, False)), (True, True))

# --- The pass: a first answer refused on the count alone.
out, record, kinds = part(span, witness, 9, [A])
check("first answer equal to engine A's marks: kept, no retry asked",
      (out, record["ok"], kinds), (A, True, ["census", "punctuate"]))
check("... the pass says so", (record["reason"], record["firstAnswerKept"], "firstAnswer" in record, record["census"],
                               record["places"], record["firstAnswerMarks"]),
      ("4 places marked but 9 counted on the page" + KEPT, "engine-a-marks", False, 9, 4, 4))
doubts = pp.punctuation_doubts([dict(record, block=3, range=[0, len(span)])])
check("... and the count is still a doubt, as for a kept answer outside the tolerance",
      [(d["kind"], d["detail"]) for d in doubts],
      [("punctuation-count-mismatch", "PUNCTUATION COUNT MISMATCH: block 3: census counted 9 places, the pass kept 4 "
                                      "(the first answer, kept with no retry: its marks are engine A's)")])
other = A.replace("，", "、", 1)
out, record, kinds = part(span, witness, 9, [other, A.replace("洪", "，洪")])
check("first answer differing from engine A at one gap: asked again, as before",
      (out, record["ok"], kinds, record["reason"], record["firstAnswer"], "firstAnswerKept" in record),
      (A.replace("洪", "，洪"), True, ["census", "punctuate", "punctuate-retry"],
       "4 places marked but 9 counted on the page (after retry)", other, False))
check("... its doubt as before",
      [d["detail"] for d in pp.punctuation_doubts([dict(record, block=3, range=[0, len(span)])])],
      ["PUNCTUATION COUNT MISMATCH: block 3: census counted 9 places, a retry kept 5 "
       "(first answer refused: 4 places marked but 9 counted on the page)"])
retried = (A, True, ["census", "punctuate", "punctuate-retry"], "4 places marked but 9 counted on the page (after retry)")


def outcome(*arguments, **more):
    out, record, kinds = part(*arguments, **more)
    return out, record["ok"], kinds, record["reason"]


check("switch off: asked again", outcome(span, witness, 9, [A, A], Arguments(first=False)), retried)
check("no witness (the segments do not spell engine A's text): asked again", outcome(span, None, 9, [A, A]), retried)
check("a stretch that is not engine A's own: asked again", outcome(span, (witness[0], False), 9, [A, A]), retried)
check("a book of doubled circles: asked again",
      outcome(span, witness, 9, [A, A], Arguments(profile={"notation": {"doubled": True}})), retried)
check("... its commas alone are witnessed",
      outcome(span, witnessed(commas)[1], 9, [commas], Arguments(profile={"notation": {"doubled": True}})),
      (commas, True, ["census", "punctuate"], "4 places marked but 9 counted on the page" + KEPT))
check("the census counted doubled circles here: asked again",
      outcome(span, witness, "9\n雙圈：1", [A, A])[2], ["census", "punctuate", "punctuate-retry"])
check("engine A read no mark and the answer wrote none: asked again",
      outcome(span, ([""] * (len(span) + 1), True), 9, [span, A]),
      (A, True, ["census", "punctuate", "punctuate-retry"], "0 places marked but 9 counted on the page (after retry)"))
out, record, kinds = part(span, witness, 5, [A])
check("within the tolerance: kept as before, nothing recorded",
      (out, record["reason"], "firstAnswerKept" in record, kinds), (A, "", False, ["census", "punctuate"]))
dropped = A.replace("玄", "")
check("refused for its characters, whatever its marks: asked again",
      outcome(span, witness, 9, [dropped, A]),
      (A, True, ["census", "punctuate", "punctuate-retry"], "characters changed (after retry)"))
# An answer kept as written: what it wrote that is no mark stands, as in any kept answer.
out, record, kinds = part(d_span, d_witness, 10, [dated.replace("②", "")])
check("kept as written", (out, record["firstAnswerKept"], kinds),
      (dated.replace("②", ""), "engine-a-marks", ["census", "punctuate"]))
# Nothing else about the pass changes: a kept first answer whose doubled circles
# stray from the census's count is asked about their shape, as any kept answer is.
pairs = commas.replace("，", "。。")
single = pairs.replace("。。", "。")
for char in "地宙月宿":
    single = single.replace(char, char + "、")
out, record, kinds = part(span, witnessed(pairs)[1], "9\n雙圈：0", [pairs, single])
check("a kept first answer still gets the shape question of its doubled circles",
      (out, kinds, record["firstAnswerKept"], record["shapeRetry"], record["places"]),
      (single, ["census", "punctuate", "punctuate-shape"], "engine-a-marks", {"doubled": 0, "marks": 8, "kept": True}, 8))
# An answer that reads another stretch of its block than its own (realigned) is
# no reading of the stretch engine A's marks are given for.
BLOCK = "天地玄黃宇宙洪荒日月盈昃辰宿列張寒來暑往秋收冬藏"
tile_witness = (["", "", "", "", "，", "", "", "", "。", "", "", "", "，", "", "", "", "。"], True)
drifted = "天地玄黃，宇宙洪荒。日月盈昃，辰宿"
out, record, kinds = part(BLOCK[:16], tile_witness, 9, [drifted, drifted], block=(BLOCK, 0, 16, 4))
check("an answer realigned onto another stretch: asked again",
      (kinds, record["ok"], "firstAnswerKept" in record), (["census", "punctuate", "punctuate-retry"], False, False))
out, record, kinds = part(BLOCK[:16], tile_witness, 9, [A], block=(BLOCK, 0, 16, 4))
check("... on its own stretch of the block: kept", (out, kinds, record["firstAnswerKept"]),
      (A, ["census", "punctuate"], "engine-a-marks"))
# ... or that wrote another form of a character (realigned on its own stretch,
# its marks seated on the merged characters): it did not keep the characters as written.
told = "天地玄黃，宇宙洪荒。告日月盈，辰宿列張。"
t_span, t_witness = witnessed(told)
form = told.replace("告", "吿")
out, record, kinds = part(t_span, t_witness, 9, [form, told], block=(t_span, 0, len(t_span), 0))
check("an answer that wrote another form of a character: asked again, though its marks are engine A's",
      (pp.first_answer_confirmed(t_span, pp.seat_marks(form, t_span), t_witness, False), out, kinds,
       "firstAnswerKept" in record),
      (True, told, ["census", "punctuate", "punctuate-retry"], False))

# --- The pass: the census not asked.
DENSE = "甲，乙，丙，丁，戊。"
d_span, d_witness = witnessed(DENSE)
check("ceiling of five characters", pp.census_ceiling(Arguments(), 5), 4)
out, record, kinds = part(d_span, d_witness, 3, [DENSE])
check("engine A's marks above the ceiling: no census call",
      (out, kinds, record["ok"], record["census"], record["reason"]), (DENSE, ["punctuate"], True, None, ""))
check("... the pass says it was not asked and why", record["censusNotAsked"],
      {"rule": "engine-a-over-ceiling", "engineAPlaces": 5, "ceiling": 4})
check("... and no doubt, as with any unknown census",
      pp.punctuation_doubts([dict(record, block=0, range=[0, 5])]), [])
# Engine A's places are counted on the span with its marks written in, as an
# answer's are: single circles at neighbouring gaps are not one doubled
# circle, bullets at each item are as many bullets, a run of leader dots at
# each entry one mark each (the review's probes: the joined gaps counted 3,
# 1 and 0 here).  A leader run that opens the text is still not counted
# (punctuation_counts starts with previous = "", which is in LEADER_MARKS).
for name, text, places in (("circles", "甲。乙。丙。丁。戊。", 5), ("bullets", "●甲●乙●丙●丁●戊", 5),
                           ("leaders", "甲……乙……丙……丁……戊……", 5)):
    c_span, c_witness = witnessed(text)
    c_out, c_record, c_kinds = part(c_span, c_witness, 3, [text])
    check(f"engine A's places counted as written ({name}): no census call, {places} places",
          (c_kinds, c_record.get("censusNotAsked")), (["punctuate"], {"rule": "engine-a-over-ceiling",
                                                                       "engineAPlaces": places, "ceiling": 4}))
# One mark of engine A's is no witness: an answer with the same one mark is
# held to the count (the review's probe of a lazy answer).
l_span, l_witness = witnessed("天地玄黃宇宙洪荒日月盈昃辰宿列張。")
check("equal: never where engine A read one mark only",
      pp.first_answer_confirmed(l_span, "天地玄黃宇宙洪荒日月盈昃辰宿列張。", l_witness, False), False)
l_out, l_record, l_kinds = part(l_span, l_witness, 6, ["天地玄黃宇宙洪荒日月盈昃辰宿列張。", "天地玄黃，宇宙洪荒。日月盈昃，辰宿列張。"])
check("... the pass asks again", (l_kinds, "firstAnswerKept" in l_record),
      (["census", "punctuate", "punctuate-retry"], False))
asked_out, asked, asked_kinds = part(d_span, d_witness, 7, [DENSE], Arguments(skip=False))
check("switch off: the census is asked, and above the ceiling discarded",
      (asked_kinds, asked["census"], "censusNotAsked" in asked), (["census", "punctuate"], None, False))
check("the pass is the one after a discarded census",
      (out, {key: value for key, value in record.items() if key != "censusNotAsked"}), (asked_out, asked))
below = "甲，乙，丙，丁戊。"
out, record, kinds = part(*witnessed(below), 4, [below])
check("engine A's marks at the ceiling, not above: the census is asked",
      (kinds, record["census"], "censusNotAsked" in record), (["census", "punctuate"], 4, False))
marker = "甲，乙，丙，丁\\(^{①}戊②。"
out, record, kinds = part(*witnessed(marker), 4, ["甲，乙，丙，丁戊。"])
check("a LaTeX delimiter's bracket and note markers are not counted: asked", kinds, ["census", "punctuate"])
pairs = "甲。。乙。。丙，丁戊"
check("a doubled circle is one place, as the census counts it: asked",
      part(*witnessed(pairs), 3, [pairs])[2], ["census", "punctuate"])
check("no witness: asked", part(d_span, None, 7, [DENSE])[2], ["census", "punctuate"])
check("a profile's denser print raises the ceiling: asked",
      part(d_span, d_witness, 5, [DENSE], Arguments(profile={"notation": {"maxMarksPerCharacter": 1.0}}))[2],
      ["census", "punctuate"])
# Both rules in one pass are independent: with no census there is no count to refuse on.
out, record, kinds = part(d_span, d_witness, 3, [DENSE], Arguments(first=True, skip=True))
check("census not asked: no count, so nothing for the first-answer rule to keep",
      ("firstAnswerKept" in record, record["reason"]), (False, ""))


# --- Pages.
BOX = [0.3, 0.1, 0.4, 0.8]


def run(text_a: str, model: stand_in.StandIn, extra=()):
    """A one-page made-up book whose engines read the same characters:
    (record, page text, report, the kinds of call asked)."""
    with stand_in.book({1: ([stand_in.block(text_a, BOX)], pp.CJK(text_a))}) as root:
        record, markdown = stand_in.run(root, model, extra=list(extra))[1]
        report = json.loads((root / "report.json").read_text(encoding="utf-8"))
    return record, markdown.strip(), report, [kind for kind in model.kinds() if kind.startswith(("census", "punctuate"))]


def answering(*answers: str):
    """A punctuator that gives ANSWERS in turn."""
    left = list(answers)
    return lambda text: left.pop(0)


PAGE = "天地玄黃，宇宙洪荒。日月盈昃，辰宿列張。寒來暑往，秋收冬藏。"
record, text, report, kinds = run(PAGE, stand_in.StandIn(census=12, punctuate=answering(PAGE)))
passes = record["punctuationPasses"]
check("page: the first answer kept, no retry asked", (text, kinds), (PAGE, ["census", "punctuate"]))
check("page: the pass's record", [(p["ok"], p["reason"], p.get("firstAnswerKept"), p["census"], p["places"]) for p in passes],
      [(True, "6 places marked but 12 counted on the page" + KEPT, "engine-a-marks", 12, 6)])
check("page: sealed in decisionChanges",
      [(c["decision"], c["rule"], c["switch"], c["block"], c["before"], c["after"], c["evidence"])
       for c in record["decisionChanges"]],
      [("engineAConfirmsFirstAnswer", "first-answer-engine-a-marks", "--engine-a-confirms-first-answer", 0, None, PAGE,
        {"range": [0, 24], "census": 12, "places": 6})])
check("page: the count stays a doubt", [d["kind"] for d in record["doubts"]], ["punctuation-count-mismatch"])
check("page: provenance and report",
      (record["provenance"].get("engineAConfirmsFirstAnswer"), record["provenance"].get("censusSkipOverCeiling"),
       report["engineAConfirmsFirstAnswer"], report["censusSkipOverCeiling"], report["pages"][0]["firstAnswersKept"],
       report["pages"][0]["censusNotAsked"], report["decisionChanges"]),
      ("on", "on", {"firstAnswersKept": 1}, {"censusNotAsked": 0}, 1, 0, {"engineAConfirmsFirstAnswer": 1}))
same = run(PAGE, stand_in.StandIn(census=12, punctuate=answering(PAGE)), extra=FIRST + SKIP)
check("page: the switches' own names are the default",
      stand_in.settled({1: (same[0], same[1])}), stand_in.settled({1: (record, text)}))
RETRY = PAGE.replace("秋", "、秋")
record, text, report, kinds = run(PAGE, stand_in.StandIn(census=12, punctuate=answering(PAGE, RETRY)), extra=NO_FIRST)
check("page, off: asked again and the retry kept, as before",
      (text, kinds, [(p["reason"], p.get("firstAnswer"), "firstAnswerKept" in p) for p in record["punctuationPasses"]],
       record["decisionChanges"]),
      (RETRY, ["census", "punctuate", "punctuate-retry"],
       [("6 places marked but 12 counted on the page (after retry)", PAGE, False)], []))
check("page, off: not in provenance or the report",
      ("engineAConfirmsFirstAnswer" in record["provenance"], record["provenance"].get("censusSkipOverCeiling"),
       "engineAConfirmsFirstAnswer" in report, "firstAnswersKept" in report["pages"][0]), (False, "on", False, False))
OTHER = PAGE.replace("，", "、", 1)
record, text, report, kinds = run(PAGE, stand_in.StandIn(census=12, punctuate=answering(OTHER, RETRY)))
check("page: a first answer that differs from engine A at one gap is asked again",
      (text, kinds, [p.get("firstAnswer") for p in record["punctuationPasses"]], record["decisionChanges"],
       report["engineAConfirmsFirstAnswer"]),
      (RETRY, ["census", "punctuate", "punctuate-retry"], [OTHER], [], {"firstAnswersKept": 0}))
# Engine B read a character engine A did not: the stretch is not engine A's own.
with stand_in.book({1: ([stand_in.block(PAGE, BOX)], pp.CJK(PAGE)[:8] + "乙" + pp.CJK(PAGE)[8:])}) as root:
    model = stand_in.StandIn(census=12, punctuate=lambda span: written(span, witnessed(PAGE, span)[1][0]))
    record, _ = stand_in.run(root, model, extra=["--no-insertion-crop"])[1]
check("page: a block holding a character only engine B read is asked again, though its marks are engine A's",
      ([c for c in pp.CJK(record["punctuationPasses"][0].get("firstAnswer", "")) if c == "乙"],
       [kind for kind in model.kinds() if kind.startswith("punctuate")],
       [c["decision"] for c in record["decisionChanges"] if c["decision"] == "engineAConfirmsFirstAnswer"]),
      (["乙"], ["punctuate", "punctuate-retry"], []))

LIST = "天，地，玄，黃，宇，宙，洪，荒，日，月。"
record, text, report, kinds = run(LIST, stand_in.StandIn(census=3, punctuate=answering(LIST)))
check("page: engine A's marks above the ceiling - no census call", (text, kinds), (LIST, ["punctuate"]))
check("page: the pass's record",
      [(p["ok"], p["census"], p["reason"], p["censusNotAsked"]) for p in record["punctuationPasses"]],
      [(True, None, "", {"rule": "engine-a-over-ceiling", "engineAPlaces": 10, "ceiling": 7})])
check("page: sealed in decisionChanges",
      [(c["decision"], c["rule"], c["switch"], c["block"], c["before"], c["after"], c["evidence"])
       for c in record["decisionChanges"]],
      [("censusSkipOverCeiling", "census-not-asked", "--census-skip-over-ceiling", 0, None, LIST,
        {"range": [0, 10], "engineAPlaces": 10, "ceiling": 7})])
check("page: no doubt, and the report counts it",
      ([d["kind"] for d in record["doubts"]], report["censusSkipOverCeiling"], report["pages"][0]["censusNotAsked"]),
      ([], {"censusNotAsked": 1}, 1))
off_record, off_text, off_report, off_kinds = run(LIST, stand_in.StandIn(census=9, punctuate=answering(LIST)), extra=NO_SKIP)
check("page, off: the census is asked (and above the ceiling discarded): the same page",
      (off_text, off_kinds, [(p["census"], "censusNotAsked" in p) for p in off_record["punctuationPasses"]],
       off_record["decisionChanges"], "censusSkipOverCeiling" in off_record["provenance"],
       "censusSkipOverCeiling" in off_report),
      (LIST, ["census", "punctuate"], [(None, False)], [], False, False))
SPARSE = "天，地，玄，黃，宇，宙，洪荒日月。"
record, text, report, kinds = run(SPARSE, stand_in.StandIn(census=7, punctuate=answering(SPARSE)))
check("page: engine A's marks at the ceiling - the census is asked",
      (text, kinds, [(p["census"], "censusNotAsked" in p) for p in record["punctuationPasses"]], record["decisionChanges"]),
      (SPARSE, ["census", "punctuate"], [(7, False)], []))


# --- Sealed only when on; a book is decided one way throughout.
both_on = pp.decision_provenance(SimpleNamespace(prefer_engine="A", fallback_engine="A",
                                                 engine_a_confirms_first_answer=True, census_skip_over_ceiling=True))
both_off = pp.decision_provenance(SimpleNamespace(prefer_engine="A", fallback_engine="A"))
check("sealed when on, and not at all when off",
      ([both_on.get(key) for key in ("engineAConfirmsFirstAnswer", "censusSkipOverCeiling")],
       [key in both_off for key in ("engineAConfirmsFirstAnswer", "censusSkipOverCeiling")]),
      (["on", "on"], [False, False]))
first_only = pp.decision_provenance(SimpleNamespace(prefer_engine="A", fallback_engine="A",
                                                    engine_a_confirms_first_answer=True))
with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "page-0001.json"
    job = SimpleNamespace(out_json=out, out_md=out.with_suffix(".md"))
    current = []
    for sealed_with, run_with in ((both_on, both_off), (both_off, both_on), (both_on, first_only), (both_on, both_on),
                                  (both_off, both_off)):
        record = {"schemaVersion": pp.SCHEMA_VERSION, "status": "complete", "scanPage": 1,
                  "provenance": {**sealed_with, "markdownSha256": pp.sha256_bytes("天地玄黃".encode("utf-8"))}}
        record["provenance"]["jsonPayloadSha256"] = pp.sha256_bytes(pp.canonical_json_bytes(record))
        out.with_suffix(".md").write_text("天地玄黃", encoding="utf-8")
        out.write_bytes(pp.canonical_json_bytes(record))
        current.append(pp.validate_completion(job, run_with))
check("a resume takes a sealed page as current only under the same setting", [found[0] for found in current],
      [False, False, False, True, True])
check("... and says which switches resume it as it was sealed",
      (current[1][1], current[2][1]),
      ("provenance engineAConfirmsFirstAnswer, censusSkipOverCeiling differ: sealed with "
       "--engine-a-confirms-first-answer, --census-skip-over-ceiling off, this run has them on (resume with "
       "--no-engine-a-confirms-first-answer --no-census-skip-over-ceiling)",
       "provenance censusSkipOverCeiling differs: sealed with --census-skip-over-ceiling on, this run has it off"))
parse = lambda *extra: (lambda a: (a.engine_a_confirms_first_answer, a.census_skip_over_ceiling))(  # noqa: E731
    pp.build_parser().parse_args(["r", "a", "o", *extra]))
check("parsing: both on by default and by name, each off with its --no- switch",
      (parse(), parse(*FIRST, *SKIP), parse(*NO_FIRST), parse(*NO_SKIP)),
      ((True, True), (True, True), (False, True), (True, False)))

# A book begun with the switches one way is not resumed the other way: the run
# does not start (round4_split), and names the switch.
model = stand_in.StandIn(census=0)
real, store = pp.Client, os.environ.get(stand_in._pair_cache.PATH_ENV)
pp.Client = lambda *args, **kwargs: model
try:
    with stand_in.book({n: ([stand_in.block(PAGE, BOX)], pp.CJK(PAGE)) for n in (1, 2)}) as root:
        os.environ[stand_in._pair_cache.PATH_ENV] = str(root / "pair-class.jsonl")
        base = [str(root / "renders"), str(root / "a"), str(root / "out"), "--draft2-directory", str(root / "b"),
                "--prefer-engine", "A", "--endpoint", stand_in.CLOSED_ENDPOINT, "--report", str(root / "r.json")]

        def started(*extra: str) -> tuple[int, str]:
            said = io.StringIO()
            with contextlib.redirect_stderr(said), contextlib.redirect_stdout(io.StringIO()):
                status = pp.main([*base, *extra])
            return status, "\n".join(line for line in said.getvalue().splitlines() if line.startswith("ERROR"))

        check("a book begun with a switch off", started("--pages", "1", *NO_SKIP), (0, ""))
        status, said = started("--pages", "2")
        check("... is not resumed with it on: the run does not start, and says how to resume",
              (status, said.startswith(f"ERROR resume with --no-census-skip-over-ceiling: 1 sealed page(s) in "
                                       f"{root / 'out'} (1) were decided with --census-skip-over-ceiling off")),
              (2, True))
        check("... and resumes with it off", started("--pages", "1-2", *NO_SKIP), (0, ""))
finally:
    pp.Client = real
    if store is None:
        os.environ.pop(stand_in._pair_cache.PATH_ENV, None)
    else:
        os.environ[stand_in._pair_cache.PATH_ENV] = store

print(f"{'FAIL' if failures else 'ok'}: {failures} failure(s)")
sys.exit(1 if failures else 0)
