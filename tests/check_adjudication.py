"""Checks for how a 裁決 verdict becomes the text: the answer 無 (or 冇, 空) is the
character when an engine read that character, and "no character here" otherwise.
And for the tie-break read (--tie-break): the blind transcription's reading at the
spot picks an engine, and is never written itself.

Usage: python3 tests/check_adjudication.py   (exits non-zero on the first failure)
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


class Verdict:
    """Stands in for the model: every call answers with the same verdict text."""

    def __init__(self, text: str) -> None:
        self.text = text

    def ask_answering(self, system, prompt, crop, max_tokens, kind=None):
        return self.text, {}


def judge(a: str, b: str, answer: str) -> tuple[str, str]:
    seg = {"a": a, "b": b, "before": "口用其破壞", "after": "論滿人漢人"}
    piece, record, _ = pp.adjudicate_segment(Verdict(f"構件：略\n判定：{answer}\n定案：{answer}\nRESEARCH: no"),
                                             None, seg, 16000)
    return piece, record["resolved_from"]


# The measured case: engine A read 無 (無論), engine B read 爾, and 裁決 answered 無.
check("無 is the character when an engine read 無", judge("無", "爾", "無"), ("無", "adjudicator"))
check("冇 is the character when an engine read 冇", judge("有", "冇", "冇"), ("冇", "adjudicator"))
# The bracket case the empty answer exists for: one engine read a bracket as 一.
check("無 is no character when neither engine read 無", judge("", "一", "無"), ("", "adjudicator-empty"))
check("無 is no character against two other readings", judge("二", "一", "無"), ("", "adjudicator-empty"))
check("無字 is always no character", judge("", "一", "無字"), ("", "adjudicator-empty"))
check("an ordinary answer is unchanged", judge("其", "萬", "甚"), ("甚", "adjudicator"))
# "Nothing printed" where both engines read ordinary text would delete a character.
check("無 against two ordinary readings is no verdict", judge("懍遵", "懷違", "無"), ("懍遵", "adjudicator-invalid"))


# An answer that leaves out more than a couple of characters one engine read - a third
# reading, or "nothing printed" - is a partial view, not a verdict: that reading is kept.
# Measured: engine B's 26-character column against engine A's four-character fold label,
# answered with the column's last seven (the crop showed only those); a table header
# answered with one of its four characters; two table cells engine B read answered 無.
COLUMN = "於今日之中國姑從畧焉俟乎閱者諸君之自求之而自得之耳"
check("a third reading that is part of a longer one keeps the longer",
      judge("法學通論", COLUMN, "求之而自得之耳"), (COLUMN, "adjudicator-deletion-refused"))
check("one of four characters engine A read keeps the four", judge("用敎授要", "", "敎"),
      ("用敎授要", "adjudicator-deletion-refused"))
check("nothing printed where engine B read six characters keeps them", judge("", "二册二角八分", "無"),
      ("二册二角八分", "adjudicator-deletion-refused"))
check("... and what 裁決 wrote is sealed", pp.adjudicate_segment(
    Verdict("定案：求之而自得之耳"), None, {"a": "法學通論", "b": COLUMN, "before": "", "after": ""}, 16000)[1]
      ["answered"], "求之而自得之耳")
check("two characters answered away: 裁決's answer stands", judge("", "甲乙", "無"), ("", "adjudicator-empty"))
check("a third reading as long as the readings stands", judge("甲乙丙", "丁戊己", "庚辛壬"), ("庚辛壬", "adjudicator"))
check("a numeral question may answer 無 (strokes and brackets read as figures)", judge("", "一一一", "無"),
      ("", "adjudicator-empty"))
check("an answer that is engine A's reading stands", judge("法學通論", COLUMN, "法學通論"),
      ("法學通論", "adjudicator"))
# Proposed decision D16 off (--no-answer-deletion-guard): the answer as written, as before.
check("the guard off: the part 裁決 wrote stands", pp.adjudicate_segment(
    Verdict("定案：求之而自得之耳"), None, {"a": "法學通論", "b": COLUMN, "before": "", "after": "",
                                     "deletionGuard": False}, 16000)[1]["resolved_from"], "adjudicator")
check("the guard off: nothing printed stands", pp.adjudicate_segment(
    Verdict("定案：無"), None, {"a": "", "b": "二册二角八分", "before": "", "after": "", "deletionGuard": False},
    16000)[:2][0], "")


def judge_furniture(a: str, b: str, answer: str, sides: list[str]) -> tuple[str, str]:
    seg = {"a": a, "b": b, "before": "", "after": "停交易等字樣", "furnitureSides": sides}
    piece, record, _ = pp.adjudicate_segment(Verdict(f"定案：{answer}"), None, seg, 16000)
    return piece, record["resolved_from"]


check("a running head only engine B read may be answered away",
      judge_furniture("", "某某叛國史八六", "無", ["b"]), ("", "adjudicator-empty"))
check("the book's furniture: running head and folio figures leave nothing",
      pp.furniture_leftover("某某叛國史八六", set(), ["某某叛國史"]), 0)
# A folio of three figures (past the book's 99th page) beside the head, before or after
# it, is the folio however long; a figure misread (engine B's 口 for 〇) is left over.
# Measured on cangwingming, where engine B read these at the page's start and engine A
# nothing: pp.306 (二五〇 read 二五口), 312, 320 (the head misread) and three more.
HEAD = ["陳炯明叛國史"]
for reading, left in (("陳炯明叛國史二五口", 1), ("陳炯明叛國史二五六", 0), ("陳炯朗叛國史二六四", 0),
                      ("陳炯明叛國史一八七", 0), ("二三六陳炯明叛國史", 0), ("陳炯明叛國史二口四", 1)):
    check(f"... {reading}: the folio beside the head is furniture", pp.furniture_leftover(reading, set(), HEAD), left)
    check(f"... {reading}: answered 無, it goes", pp.adjudicate_segment(
        Verdict("定案：無"), None, {"a": "", "b": reading, "before": "", "after": "陳氏正作",
                                    "furnitureSides": ["b"] if pp.furniture_leftover(reading, set(), HEAD)
                                    <= pp.INSERTION_LIMIT else []}, 16000)[1]["resolved_from"],
          "adjudicator-empty")
check("... figures not beside the head are not its folio",
      pp.furniture_leftover("陳炯明叛國史陳氏二五〇", set(), HEAD), 5)
check("... nor text after the folio", pp.furniture_leftover("陳炯明叛國史八六陳氏正作", set(), HEAD), 4)
check("... a figure misread passed over, when figures stand beyond it",
      [pp.folio_figures(text, at, step) for text, at, step in (
          ("一四口陳炯明叛國史", 2, -1), ("陳炯明叛國史一口二外校", 6, 1), ("陳炯明叛國史二五口", 6, 1),
          ("陳炯明叛國史第二章", 6, 1), ("三口陳炯明叛國史", 1, -1))],
      [[1, 0], [6, 8], [6, 7], [], []])
# Where the alignment, or a run placed once (D2), left the folio alone beside the head in
# engine B's reading (cangwingming pp.158, 196, 202: the head went to engine A's site), the
# reading is taken where engine B read it.
for stream, span, left in (("陳炯明叛國史一口二外校內圖書", (6, 9), 1), ("一四口陳炯明叛國史心語也雖然", (0, 3), 1),
                           ("一四六陳炯明叛國史遣將助戰", (0, 4), 0), ("二口四陳炯明叛國史下野有利", (0, 3), 1)):
    check(f"... {stream[span[0]:span[1]]} beside the head in the engine's reading is its folio",
          pp.furniture_leftover(stream, set(), HEAD, span), left)
# cangwingming p.246: 吿之 after the head, which engine A did not read, is not the folio: the
# reading stays with the guard (a person looks).
check("... text beside the head and folio is not", pp.furniture_leftover(
    "一九口陳炯明叛國史吿之言如蒙察", set(), HEAD, (0, 11)), 3)
check("... nor text beside the head", pp.furniture_leftover("陳炯明叛國史外校內圖書儀", set(), HEAD, (6, 9)), 3)
check("... a sentence is not furniture", pp.furniture_leftover("於今日之中國姑從", set(), ["某某叛國史"]), 8)
check("... recurring n-grams are", pp.furniture_leftover("廣州大典第二十九輯", {"廣州大典第二十九"}, []), 1)


def judge_fused(a: str, b: str, agreed: list[str], answer: str) -> tuple[str, str]:
    seg = {"a": a, "b": b, "agreed": agreed, "before": "光緒二十年歲入", "after": "兩又"}
    piece, record, _ = pp.adjudicate_segment(Verdict(f"構件：略\n定案：{answer}\nRESEARCH: no"),
                                             None, seg, 16000)
    return piece, record["resolved_from"]


check("無 on a fused numeral run keeps the digits both engines read",
      judge_fused("一九〇五", "一九五", ["一九", "五"], "無"), ("一九五", "adjudicator-empty"))


def tie_break(a: str, b: str, transcript: str, fallback: str = "A") -> tuple[str, str, str]:
    seg = {"a": a, "b": b, "before": "日萬國博覽會開會", "after": "有日本人設人類"}
    piece, record, _ = pp.blind_read_segment(Verdict(transcript), None, seg, 16000, fallback_engine=fallback)
    return piece, record["winner"], record["resolved_from"]


# Measured: engine A read 末, engine B read 未, and the blind read had 未.
check("a blind read matching B writes B", tie_break("末", "未", "日萬國博覽會開會未有日本人設人類"),
      ("未", "B", "blind-read"))
check("a blind read matching A writes A", tie_break("末", "未", "萬國博覽會開會末有日本"),
      ("末", "A", "blind-read"))
# A third reading is not written: the preferred engine stands.
check("a third reading keeps engine A", tie_break("鐘", "釐", "日萬國博覽會開會毫有日本人設人類"),
      ("鐘", "neither", "blind-read-unmatched-engine-A"))
check("a third reading keeps engine B when B is preferred",
      tie_break("鐘", "釐", "日萬國博覽會開會毫有日本人設人類", fallback="B"),
      ("釐", "neither", "blind-read-unmatched-engine-B"))
check("a transcription that cannot be placed keeps engine A", tie_break("末", "未", "無關嘅字"),
      ("末", "undecided", "blind-read-unlocated-engine-A"))
# Punctuation in the engines' readings does not stop a match.
check("marks in a reading do not stop a match", tie_break("末，", "未。", "日萬國博覽會開會未有日本人設人類"),
      ("未。", "B", "blind-read"))
check("an empty reading at a placed spot is a third reading, not unlocated",
      tie_break("末", "未", "日萬國博覽會開會有日本人設人類"), ("末", "neither", "blind-read-unmatched-engine-A"))
# Which spots may be read blind at all.
for name, a, b, kind, want in (
        ("a like-for-like substitution on a glyph crop", "末", "未", "glyph", True),
        ("a numeral substitution on a band crop", "二", "三", "band", True),
        ("one side empty", "", "未", "glyph", False),
        ("one side longer (a 〇 only one engine read)", "一九〇五", "一九五", "glyph", False),
        ("a whole table", "八", "二", "table", False),
        ("a whole horizontal block", "末", "未", "block", False),
        ("the whole page", "末", "未", "page", False),
        ("a rare codepoint", "\U0002B53F", "尊", "glyph", False)):
    check(f"tie-break eligible: {name}", pp.tie_break_eligible({"a": a, "b": b}, kind), want)
check("the spot is found with only one side of context", pp.locate_reading(
    "開會未", {"a": "末", "b": "未", "before": "萬國博覽會開會", "after": ""}), "未")
# A spot the crop does not show: the transcription starts right after it (measured: a
# crop that began one character below the disputed 者, whose empty reading at the head
# of the transcription went to 裁決 as a third reading, and 裁決 wrote the crop's first
# character).  Off the crop, not an empty reading.
EDGE = {"a": "者", "b": "著", "before": "爲總論各論二編", "after": "殆居多數總論以說"}
check("a spot before the transcription's first character is not located",
      (pp.locate_reading("殆居多數總論以說明", EDGE), pp.locate_spot("殆居多數總論以說明", EDGE)),
      (None, (None, "edge")))
check("... nor one after its last", pp.locate_spot("爲總論各論二編", EDGE), (None, "edge"))
check("... but one side of context and the spot on the crop is placed",
      pp.locate_spot("二編著殆居多數", EDGE), ("著", "placed"))
check("a transcription with no context found is unanchored", pp.locate_spot("某某某", EDGE), (None, "unanchored"))


class Answers:
    """Stands in for the model: the blind read's transcription, then 裁決's verdict."""

    def __init__(self, blind: str, verdict: str) -> None:
        self.blind, self.verdict, self.kinds = blind, verdict, []

    def ask_answering(self, system, prompt, crop, max_tokens, kind=None):
        self.kinds.append(kind)
        text = self.blind if system == pp.BLIND_SYSTEM else f"構件：略\n定案：{self.verdict}\nRESEARCH: no"
        return text, {"prompt_tokens": 1, "completion_tokens": 1, "reasoning_tokens": 0}


def tie_break_v2(a: str, b: str, transcript: str, verdict: str = "未", unmatched: str = "judge"):
    seg = {"a": a, "b": b, "before": "日萬國博覽會開會", "after": "有日本人設人類"}
    client = Answers(transcript, verdict)
    piece, record, metrics = pp.blind_read_segment(client, None, seg, 16000, fallback_engine="A",
                                                   unmatched=unmatched)
    return piece, record.get("tieBreakPath"), record["resolved_from"], client.kinds


# Tie-breaker v2 (D12): a blind reading that matches neither engine goes on to 裁決.
check("v2: a third reading goes on to 裁決, whose answer stands",
      tie_break_v2("鐘", "釐", "日萬國博覽會開會毫有日本人設人類", verdict="釐"),
      ("釐", "unmatched-judge", "adjudicator", ["blind-read", "adjudicate"]))
check("v2: a reading that cannot be placed too",
      tie_break_v2("末", "未", "無關嘅字")[1:], ("unlocated-judge", "adjudicator", ["blind-read", "adjudicate"]))
check("v2: a reading that matches an engine settles it alone",
      tie_break_v2("末", "未", "日萬國博覽會開會未有日本人設人類"), ("未", "matched-B", "blind-read", ["blind-read"]))
client = Answers("殆居多數總論以說明", "殆")
piece, record, _ = pp.blind_read_segment(client, None, EDGE, 16000, fallback_engine="A", unmatched="judge")
check("v2: a spot off the crop is not asked of 裁決 on the same crop: the fallback engine",
      (piece, record["tieBreakPath"], record["resolved_from"], client.kinds),
      ("者", "off-crop-engine-A", "blind-read-off-crop-engine-A", ["blind-read"]))
check("v1: the fallback engine, recorded as such",
      tie_break_v2("鐘", "釐", "日萬國博覽會開會毫有日本人設人類", unmatched="fallback"),
      ("鐘", "unmatched-engine-A", "blind-read-unmatched-engine-A", ["blind-read"]))

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stand_in  # noqa: E402

BODY = "萬國博覽會開會末有日本人設人類館"


def page(profile: dict, extra: list[str], blind: str):
    model = stand_in.StandIn(census=0, judge=lambda a, b: "未", blind=blind)
    with stand_in.book({1: ([stand_in.block(BODY, [0.3, 0.1, 0.4, 0.8])], BODY.replace("末", "未"))},
                       profile=profile) as root:
        record, markdown = stand_in.run(root, model, extra=["--tie-break", *extra])[1]
    return record, markdown, model


third = "萬國博覽會開會毫有日本人設人類館"
record, markdown, model = page({"preferEngine": "adjudicate"}, [], third)
check("page, no preference: the unmatched spot goes to 裁決 (v2)",
      (pp.CJK(markdown), [a["tieBreakPath"] for a in record["adjudications"]]), (BODY.replace("末", "未"),
                                                                                  ["unmatched-judge"]))
check("page: sealed for D12", [(c["decision"], c["before"], c["after"], c["evidence"]["tieBreakPath"])
                               for c in record["decisionChanges"]], [("D12", "末", "未", "unmatched-judge")])
check("page: provenance", record["provenance"]["tieBreak"], "v2")
record, markdown, model = page({"preferEngine": "adjudicate"}, ["--no-tie-break-v2"], third)
check("--no-tie-break-v2: the fallback engine, as v1", (pp.CJK(markdown), record["decisionChanges"],
                                                         record["provenance"]["tieBreak"]), (BODY, [], "on"))
record, markdown, model = page({"preferEngine": "A"}, [], third)
check("page, a preference: the preferred engine, as v1, nothing sealed",
      (pp.CJK(markdown), [a["tieBreakPath"] for a in record["adjudications"]], record["decisionChanges"]),
      (BODY, ["unmatched-engine-A"], []))


def extra_page(extra_b: str, profile: dict, extra: tuple[str, ...] | list[str] = ()):
    """A page where engine B read EXTRA_B, five characters engine A did not, and 裁決
    answers that nothing is printed there."""
    model = stand_in.StandIn(census=0, judge=lambda a, b: "無")
    with stand_in.book({1: ([stand_in.block(BODY, [0.3, 0.1, 0.4, 0.8])], BODY[:8] + extra_b + BODY[8:])},
                       profile=profile) as root:
        return stand_in.run(root, model, extra=extra)[1]


record, markdown = extra_page("亞洲各國人", {"preferEngine": "adjudicate"})
check("page: five characters engine B read, answered away, are kept, with a doubt",
      (pp.CJK(markdown), [a["resolved_from"] for a in record["adjudications"]], [d["kind"] for d in record["doubts"]]),
      (BODY[:8] + "亞洲各國人" + BODY[8:], ["adjudicator-deletion-refused"], ["deletion-refused"]))
check("page: the refusal sealed as a D16 change, the guard on in the provenance",
      ([(c["decision"], c["rule"], c["switch"], c["before"], c["beforeBy"], c["after"], c["mergedOffset"],
         c["evidence"]) for c in record["decisionChanges"]],
       record["provenance"]["answerDeletionGuard"], record["provenance"]["wholeRunCrop"]),
      ([("D16", "answer-deletion-guard", "--no-answer-deletion-guard", "", "adjudicator-empty", "亞洲各國人", 8,
         {"keptEngine": "B", "readingCharacters": 5, "answeredCharacters": 0, "limit": 2, "furnitureSides": []})],
       "on", "on"))
record, markdown = extra_page("亞洲各國人", {"preferEngine": "adjudicate"}, ["--no-answer-deletion-guard",
                                                                         "--no-whole-run-crop"])
# The merge-time guard (readings_dropped) still sees the five characters go: a
# doubt, the text as 裁決 answered.
check("page, --no-answer-deletion-guard: 裁決's answer written, as before, and sealed off",
      (pp.CJK(markdown), [a["resolved_from"] for a in record["adjudications"]], [d["kind"] for d in record["doubts"]],
       [(d["engine"], d["text"], d["by"]) for d in record["readingsDropped"]],
       record["decisionChanges"], record["provenance"]["answerDeletionGuard"], record["provenance"]["wholeRunCrop"]),
      (BODY, ["adjudicator-empty"], ["reading-dropped"], [("B", "亞洲各國人", ["adjudicator-empty"])], [], "off", "off"))
record, markdown = extra_page("亞洲各國人", {"preferEngine": "adjudicate"}, ["--no-answer-deletion-guard",
                                                                         "--no-whole-run-crop",
                                                                         "--no-merge-loss-guard"])
check("page, --no-answer-deletion-guard --no-merge-loss-guard: no doubt at all, as before",
      (pp.CJK(markdown), record["doubts"], record["readingsDropped"], record["provenance"]["mergeLossGuard"]),
      (BODY, [], [], "off"))
pp.set_crop_geometry()
record, markdown = extra_page("亞洲各國人", {"preferEngine": "adjudicate", "layout": {"runningHeads": ["亞洲各國人"]}})
check("page: the same five characters as the book's running head are answered away",
      (pp.CJK(markdown), [a["resolved_from"] for a in record["adjudications"]], record["doubts"]),
      (BODY, ["adjudicator-empty"], []))


LONG = BODY + "列亞洲各地人民之風俗器物以供衆覽焉"


def head_page(head_and_folio: str, extra: list[str] | tuple[str, ...] = ()):
    """A page where engine B read the book's running head and its folio before the
    body, engine A read only the body, and 裁決 answers that nothing is printed there."""
    model = stand_in.StandIn(census=0, judge=lambda a, b: "無")
    with stand_in.book({1: ([stand_in.block(LONG, [0.3, 0.1, 0.4, 0.8])], head_and_folio + LONG)},
                       profile={"preferEngine": "adjudicate", "layout": {"runningHeads": HEAD}}) as root:
        return stand_in.run(root, model, extra=extra)[1]


# cangwingming pp.306, 312, 320: the head and a three-figure folio only engine B read.  At
# 60e461e each was kept over 裁決's 無 and written into the body (deletion-refused).
# With the learned running head (--learned-heads, the default) a reading that is all
# the learned head - the title, or the title one character off, and a folio - is
# left out before 裁決; one with a character that is no folio's is still asked and
# answered away.  The page's text is the same either way.
for reading, learned in (("陳炯明叛國史二五口", False), ("陳炯明叛國史二五六", True), ("陳炯朗叛國史二六四", True)):
    record, markdown = head_page(reading, ["--no-learned-heads"])
    check(f"page, --no-learned-heads: the head and folio {reading} only engine B read are answered away",
          (pp.CJK(markdown), [a["resolved_from"] for a in record["adjudications"]], record["doubts"],
           record["auditorClean"]), (LONG, ["adjudicator-empty"], [], True))
    record, markdown = head_page(reading)
    check(f"page: the head and folio {reading} only engine B read are "
          + ("left out as the learned head" if learned else "answered away"),
          (pp.CJK(markdown), [a["resolved_from"] for a in record["adjudications"]],
           [c["rule"] for c in record["decisionChanges"] if c["decision"] == "learnedHeads"], record["doubts"],
           record["auditorClean"]),
          (LONG, [] if learned else ["adjudicator-empty"], ["learned-head-reading"] if learned else [], [], True))
# cangwingming p.196: engine A read the head and the folio 一四〇 after the text, engine B
# 一四口 and the head before it; the head is placed once at engine A's site (D2) and the
# folio engine B read is left alone at the page's start.
model = stand_in.StandIn(census=0, judge=lambda a, b: "無")
with stand_in.book({1: ([stand_in.block(LONG, [0.3, 0.1, 0.4, 0.8]),
                         stand_in.block(HEAD[0], [0.05, 0.1, 0.03, 0.3]),
                         stand_in.block("一四〇", [0.05, 0.85, 0.03, 0.05])], "一四口" + HEAD[0] + LONG)},
                   profile={"preferEngine": "adjudicate", "layout": {"runningHeads": HEAD}}) as root:
    record, markdown = stand_in.run(root, model)[1]
check("page: the folio engine B read beside the head, left alone by the alignment, is answered away",
      ("一四口" in pp.CJK(markdown), [(a["writer_reading"], a["resolved_from"]) for a in record["adjudications"]
                                      if a["writer_reading"]], [d["kind"] for d in record["doubts"]]),
      (False, [("一四口", "adjudicator-empty")], ["moved-placed-once"]))

sys.exit(1 if failures else 0)
