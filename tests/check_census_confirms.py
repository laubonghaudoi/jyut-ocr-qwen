#!/usr/bin/env python3
"""Offline checks of switch C1, --census-confirms-engine-a (off by default).

No model, no GPU, no corpus.  A tile whose census counted marks, no doubled
circle and no leader dot, where engine A's marks hold exactly that many places
(a run of dashes one) and each has a sure place in the merged text, keeps
engine A's marks and its punctuate call is not made.  The shapes are the ones
the user's rulings of the replay showed (made-up text here):

- a printed dash engine A read, which the mark vocabulary left out;
- a mark beside a character only engine B read (甲：丙 against 甲乙丙), which
  may belong on either side of it: no sure place, the punctuator is asked;
- a numbered item's head 。(2) that engine A read between two characters where
  engine B read characters: 。（…）, not 。）…（, both in the kept tile and in
  the bracket rule;
- two passes' copies of one mark at a tile's edge: written once.

Each is checked on a whole page too (proofread_pages.main with the stand-in),
with what it seals in decisionChanges: the helpers alone passed while the
page's wiring of them could be taken out (the review of the switch took out
the ordered bracket rule, the tile-edge join, the bracket rule's entries and
the dashes in a re-read pass's recount, one at a time, and every check still
passed).

Usage:
    python3 tests/check_census_confirms.py
"""

from __future__ import annotations

import json
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


def kept_text(text_a: str, segments: list[dict], start: int = 0, length: int | None = None):
    """The merged text's stretch with engine A's marks as a kept tile writes
    them, and whether every mark there has a sure place."""
    pieces = [seg["b"] for seg in segments]
    merged = "".join(pieces)
    (after, before), unsure = pp.engine_marks_kept(text_a, segments, pieces)
    length = len(merged) - start if length is None else length
    gaps = pp.gaps_of((after, before), start, length)
    span = merged[start:start + length]
    text = "".join(gaps[k] + span[k] for k in range(length)) + gaps[length]
    return text, not any(start + g in unsure for g in range(length + 1)), gaps, span


def equal(text: str) -> dict:
    return {"tag": "equal", "a": text, "b": text}


# The marks of a gap, parted by where they go.
check("gap: print parts it", pp.gap_sides("。(2)"), ("。（", "）", True))
check("gap: an opening mark and what follows it go after", pp.gap_sides("（）"), ("", "（）", False))
check("gap: a circle then a quote", pp.gap_sides("。「"), ("。", "「", False))
check("gap: closing marks go before", pp.gap_sides("」。"), ("」。", "", False))
check("gap: a dash is a mark", pp.gap_sides("，——"), ("，——", "", False))
check("gap: markup is not print", pp.gap_sides("<td>。</td>"), ("。", "", False))
check("dash runs", pp.dash_runs("甲——乙—丙"), 2)

# A printed dash engine A read: kept, and one place.
text, sure, gaps, span = kept_text("天地——玄黃，宇宙", [equal("天地玄黃宇宙")])
check("dash kept in the tile", (text, sure), ("天地——玄黃，宇宙", True))
check("dash counted as one place", pp.engine_a_confirmed(span, (gaps, sure), 2, 0, 0), ("天地——玄黃，宇宙", 2))
check("census without the dash: not confirmed", pp.engine_a_confirmed(span, (gaps, sure), 1, 0, 0), None)
# Before the switch engine A's marks (the vocabulary) left the dash out.
check("engine_marks_merged leaves the dash out",
      pp.gaps_of(pp.engine_marks_merged("天地——玄黃，宇宙", [equal("天地玄黃宇宙")], ["天地玄黃宇宙"])),
      ["", "", "", "", "，", "", ""])

# A mark beside a character only engine B read: no sure place.
segments = [equal("天地玄黃"), {"tag": "insert", "a": "", "b": "黃"}, equal("宇宙")]
text, sure, gaps, span = kept_text("天地玄黃：宇宙", segments)
check("a mark beside a character engine A did not read is not sure", sure, False)
check("not confirmed there, whatever the census", pp.engine_a_confirmed(span, (gaps, sure), 1, 0, 0), None)
# A stretch away from it is sure: a tile there may still keep engine A's marks
# (one whose edge touches the gaps in doubt may not).
beside = [equal("天地玄黃"), {"tag": "insert", "a": "", "b": "黃"}, equal("宇宙洪")]
check("a tile away from it is sure", kept_text("天地玄黃：宇宙，洪", beside, start=6)[:2], ("宙，洪", True))
check("a tile whose edge touches it is not", kept_text("天地玄黃：宇宙，洪", beside, start=5)[:2], ("宇宙，洪", False))
# Characters of engine A's the merge left out (a running foot) change nothing.
text, sure, _, _ = kept_text("天地。日月玄黃", [equal("天地"), {"tag": "delete", "a": "日月", "b": ""}, equal("玄黃")])
check("a mark before a stretch the merge left out is sure", (text, sure), ("天地。玄黃", True))
# A mark tied to a character with no exact place is dropped, and not sure.
text, sure, _, _ = kept_text("甲乙丙，丁", [equal("甲乙"), {"tag": "replace", "a": "丙", "b": "戊己"}, equal("丁")])
check("a mark on a character of another length is not sure", (text, sure), ("甲乙戊己丁", False))

# A numbered item's head: engine A read 。(2) where engine B read three characters.
head = [equal("天地"), {"tag": "insert", "a": "", "b": "一二一"}, equal("玄黃")]
text, sure, gaps, span = kept_text("天地。(2)玄黃，", head)
check("numbered head: the brackets around what engine B read", (text, sure), ("天地。（一二一）玄黃，", True))
before = pp.engine_marks_merged("天地。(2)玄黃，", head, [seg["b"] for seg in head])
check("before: anchored_marks wrote the pair reversed",
      "".join(g + c for g, c in zip(pp.gaps_of(before), "天地一二一玄黃")) + pp.gaps_of(before)[-1],
      "天地。）一二一（玄黃，")
stream = pp.engine_gaps("天地。(2)玄黃，")
check("bracket rule, ordered: （ before what engine B read, ） after it",
      pp.engine_brackets_merged(stream, "a", head, [seg["b"] for seg in head], ordered=True), [(2, "（"), (5, "）")])
check("bracket rule as before: both before the next character",
      pp.engine_brackets_merged(stream, "a", head, [seg["b"] for seg in head]), [(5, "（"), (5, "）")])
bare = "天地。一二一玄黃，"
check("bracket rule writes the pair in order",
      pp.place_brackets(bare, "天地一二一玄黃", {(2, "（"): 1, (5, "）"): 1})[0], "天地。（一二一）玄黃，")
check("before: the pair came out reversed",
      pp.place_brackets(bare, "天地一二一玄黃", {(5, "（"): 1, (5, "）"): 1})[0], "天地。一二一）（玄黃，")
check("a kept tile agrees with the ordered bracket rule",
      pp.place_brackets("天地。（一二一）玄黃，", "天地一二一玄黃", {(2, "（"): 1, (5, "）"): 1}),
      ("天地。（一二一）玄黃，", 0, 0))
check("gap changes: one per gap, a moved bracket two",
      pp.gap_changes("天地。一二一）（玄", "天地。（一二一）玄"), [(2, "。", "。（"), (5, "）（", "）")])
check("gap changes: none", pp.gap_changes("天地。（一二一）玄", "天地。（一二一）玄"), [])
check("gap changes: other characters, the whole text", pp.gap_changes("天地。", "天玄。"), [(0, "天地。", "天玄。")])

# The gate's other conditions.
_, _, gaps, span = kept_text("天地，玄黃。", [equal("天地玄黃")])
check("confirmed", pp.engine_a_confirmed(span, (gaps, True), 2, 0, 0), ("天地，玄黃。", 2))
check("a doubled circle counted: asked", pp.engine_a_confirmed(span, (gaps, True), 2, 1, 0), None)
check("no doubled count taken: asked", pp.engine_a_confirmed(span, (gaps, True), 2, None, 0), None)
check("leader dots counted: asked", pp.engine_a_confirmed(span, (gaps, True), 2, 0, 1), None)
check("leader dots not measured: asked", pp.engine_a_confirmed(span, (gaps, True), 2, 0, None), None)
check("another count: asked", pp.engine_a_confirmed(span, (gaps, True), 3, 0, 0), None)
check("switch off: asked", pp.engine_a_confirmed(span, None, 2, 0, 0), None)

# Two passes' copies of one mark at a tile's edge.
check("edge: one circle", pp.tile_edge_join("。", "。"), "")
check("edge: another mark stays", pp.tile_edge_join("。", "「"), "「")
check("edge: a doubled circle against one", pp.tile_edge_join("。", "。。"), "。")
parts = [("甲乙。", 0, 2, 0, 2), ("。丙丁，", 2, 4, 2, 4)]
records = [{"engineAKept": True}, {"marks": 2, "places": 2}]
check("edge joined where a pass kept engine A's marks", pp.tile_edges_joined(parts, records), [(2, "。。", "。")])
check("the later pass's text and count", (parts[1][0], records[1]["marks"], records[1]["edgeMarksDropped"]),
      ("丙丁，", 1, "。"))
parts = [("甲乙。", 0, 2, 0, 2), ("。丙丁，", 2, 4, 2, 4)]
check("two punctuator passes: as before", (pp.tile_edges_joined(parts, [{}, {}]), parts[1][0]), ([], "。丙丁，"))


# punctuate_part: the census is asked, the punctuate call is not.
class Arguments:
    max_tokens = 100
    profile_data = None


real_leader_count = pp.leader_count
# The dot runs measured on the crop: none (a blank made-up crop measures nothing).
pp.leader_count = lambda crop: 0
try:
    def part(census: str, kept):
        model = stand_in.StandIn(census=census, punctuate=lambda text: "天地。玄黃。")
        out, record, _ = pp.punctuate_part(model, Arguments(), None, "天地玄黃", "", 60.0, kept=kept)
        return out, record.get("engineAKept"), model.kinds()

    check("confirmed: engine A's marks, no punctuate call", part("2\n雙圈：0", (gaps, True)),
          ("天地，玄黃。", True, ["census"]))
    check("another count: the punctuator answers", part("3\n雙圈：0", (gaps, True))[1:],
          (None, ["census", "punctuate"]))
    check("switch off: the punctuator answers", part("2\n雙圈：0", None), ("天地。玄黃。", None, ["census", "punctuate"]))

    # A page, with and without the switch.
    def page(extra):
        blocks = [stand_in.block("天地，玄黃。宇宙洪荒——日月盈昃。", [0.3, 0.1, 0.4, 0.8])]
        with stand_in.book({1: (blocks, "天地玄黃宇宙洪荒日月盈昃")}) as root:
            model = stand_in.StandIn(census="4\n雙圈：0", punctuate=lambda text: text + "。")
            record, markdown = stand_in.run(root, model, extra=extra)[1]
            report = json.loads((root / "report.json").read_text(encoding="utf-8"))
        return record, markdown, model.kinds(), report

    record, markdown, kinds, report = page(["--census-confirms-engine-a"])
    check("page: engine A's marks and dash", markdown.strip(), "天地，玄黃。宇宙洪荒——日月盈昃。")
    check("page: no punctuate call", "punctuate" in kinds, False)
    check("page: the pass says so", [(p["engineAKept"], p["places"], p["dashes"]) for p in record["punctuationPasses"]],
          [(True, 4, 1)])
    check("page: sealed in decisionChanges",
          [(c["decision"], c["rule"], c["before"], c["after"]) for c in record["decisionChanges"]],
          [("C1", "census-confirms-engine-a", None, "天地，玄黃。宇宙洪荒——日月盈昃。")])
    check("page: provenance", record["provenance"].get("censusConfirmsEngineA"), "on")
    check("page: clean", record["doubts"], [])
    check("run report", (report["censusConfirmsEngineA"], report["punctuationKeptFromEngineA"],
                         report["decisionChanges"]), ("on", 1, {"C1": 1}))
    record, markdown, kinds, report = page([])
    check("page, switch off: the punctuator answers", ("punctuate" in kinds, markdown.strip()),
          (True, "天地玄黃宇宙洪荒日月盈昃。"))
    check("page, switch off: not in provenance", "censusConfirmsEngineA" in record["provenance"], False)
    check("run report, switch off", (report["censusConfirmsEngineA"], report["punctuationKeptFromEngineA"]),
          ("off", 0))

    # A block with two numbered heads engine A read 。(1) and 。(2), where
    # engine B read characters (裁決 takes them) and the punctuator answers
    # (the census is not engine A's count): the ordered bracket rule on a page,
    # one decisionChanges entry per gap it changed.
    HEADS_A = "天地。(1)玄黃。宇宙洪荒日月盈昃。(2)辰宿列張。"
    HEADS_B = "天地一丨一玄黃宇宙洪荒日月盈昃一二一辰宿列張"

    def heads_page(extra):
        blocks = [stand_in.block(HEADS_A, [0.3, 0.1, 0.4, 0.8])]
        with stand_in.book({1: (blocks, HEADS_B)}) as root:
            model = stand_in.StandIn(census="4\n雙圈：0", judge=lambda a, b: b or a or "無",
                                     punctuate=lambda text: "天地。一丨一玄黃。宇宙洪荒日月盈昃。一二一辰宿列張。")
            record, markdown = stand_in.run(root, model, extra=extra)[1]
            report = json.loads((root / "report.json").read_text(encoding="utf-8"))
        c1 = [(c["rule"], c["mergedOffset"], c["contextBefore"], c["contextAfter"], c["before"], c["after"])
              for c in record["decisionChanges"] if c["decision"] == "C1"]
        return markdown.strip(), c1, report["decisionChanges"].get("C1", 0)

    markdown, c1, counted = heads_page(["--census-confirms-engine-a"])
    check("page, numbered heads: brackets in written order", markdown,
          "天地。（一丨一）玄黃。宇宙洪荒日月盈昃。（一二一）辰宿列張。")
    check("page, numbered heads: one entry per gap changed", c1,
          [("brackets-in-written-order", 2, "天地", "一丨一玄", "。", "。（"),
           ("brackets-in-written-order", 5, "地一丨一", "玄黃宇宙", "）（", "）"),
           ("brackets-in-written-order", 15, "日月盈昃", "一二一辰", "。", "。（"),
           ("brackets-in-written-order", 18, "昃一二一", "辰宿列張", "）（", "）")])
    check("page, numbered heads: counted in the run report", counted, 4)
    markdown, c1, counted = heads_page([])
    check("page, numbered heads, switch off: as before", (markdown, c1, counted),
          ("天地。一丨一）（玄黃。宇宙洪荒日月盈昃。一二一）（辰宿列張。", [], 0))

    class TileModel(stand_in.StandIn):
        """StandIn whose census answers a made-up tile's crop (c1_page's
        TILES) with that tile's count, and any other crop with CENSUS."""

        def __init__(self, censuses, **kwargs):
            super().__init__(**kwargs)
            self.censuses = censuses

        def ask_answering(self, system, user_text, image_bytes, max_tokens, kind="other"):
            if system.startswith(pp.CENSUS_SYSTEM.split("\n")[0]) and image_bytes in self.censuses:
                self.calls.append((kind, user_text))
                self.systems.append(system)
                return (f"符號：{self.censuses[image_bytes]}\n雙圈：0\n形狀：略",
                        {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0})
            return super().ask_answering(system, user_text, image_bytes, max_tokens, kind)

    def c1_page(text_a: str, text_b: str, answers: dict, tiles=None, census: str = "4\n雙圈：0",
                extra=("--census-confirms-engine-a",)):
        """A one-block page, 裁決 taking engine B's reading, the punctuator
        answering each stretch from ANSWERS.  TILES cuts the block: (start,
        end, census) each, the census answered for that tile's crop.  Returns
        the record, the Markdown, the calls made and the run report."""
        real_tiles = pp.block_tiles
        if tiles:
            pp.block_tiles = lambda render, block, n, limit=pp.TILE_CHARACTERS: [
                (f"tile {k}".encode(), lo, hi) for k, (lo, hi, _) in enumerate(tiles)]
        try:
            blocks = [stand_in.block(text_a, [0.3, 0.1, 0.4, 0.8])]
            with stand_in.book({1: (blocks, text_b)}) as root:
                model = TileModel({f"tile {k}".encode(): n for k, (_, _, n) in enumerate(tiles or [])},
                                  census=census, judge=lambda a, b: b or a or "無",
                                  punctuate=lambda span: answers.get(span, span))
                record, markdown = stand_in.run(root, model, extra=list(extra))[1]
                report = json.loads((root / "report.json").read_text(encoding="utf-8"))
        finally:
            pp.block_tiles = real_tiles
        return record, markdown.strip(), model.kinds(), report

    def c1_entries(record):
        return [(c["rule"], c["mergedOffset"], c["before"], c["after"])
                for c in record["decisionChanges"] if c["decision"] == "C1"]

    # A tile that keeps engine A's marks, a numbered head among them: the
    # stretch is one change (census-confirms-engine-a, before null).  The old
    # bracket placement run on engine A's brackets writes a second （ before 宇,
    # a text neither run writes, which was sealed as a second change.
    record, markdown, kinds, report = c1_page("天地玄黃。(2)宇宙洪荒。", "天地玄黃一二一宇宙洪荒", {})
    check("page, kept numbered head: engine A's brackets in written order", (markdown, "punctuate" in kinds),
          ("天地玄黃。（一二一）宇宙洪荒。", False))
    check("page, kept numbered head: one change, the stretch kept", c1_entries(record),
          [("census-confirms-engine-a", 0, None, "天地玄黃。（一二一）宇宙洪荒。")])
    check("page, kept numbered head: counted once", report["decisionChanges"], {"C1": 1})
    # One block in two tiles: the first keeps engine A's marks (its census
    # is engine A's count), the second is answered (its census is not).  The
    # bracket rule's changes in the kept stretch are that stretch's entry;
    # the answered stretch's are recorded gap by gap.
    record, markdown, kinds, report = c1_page(
        HEADS_A, HEADS_B, {"宇宙洪荒日月盈昃一二一辰宿列張": "宇宙洪荒日月盈昃。一二一辰宿列張。"},
        tiles=[(0, 7, "4"), (7, 22, "2")])
    check("page, a kept tile and an answered one: the text", markdown,
          "天地。（一丨一）玄黃。宇宙洪荒日月盈昃。（一二一）辰宿列張。")
    check("page, a kept tile and an answered one: the entries", c1_entries(record),
          [("census-confirms-engine-a", 0, None, "天地。（一丨一）玄黃。"),
           ("brackets-in-written-order", 15, "。", "。（"), ("brackets-in-written-order", 18, "）（", "）")])

    # The page-level wiring the checks above leave out.  A tile that keeps
    # engine A's 。 at its end, and the next tile's answer opening with the
    # same 。 (its crop shows the head of the next column): written once.
    record, markdown, kinds, report = c1_page(
        "天地玄黃。宇宙洪荒。", "天地玄黃宇宙洪荒", {"宇宙洪荒": "。宇宙洪荒。"}, tiles=[(0, 4, "1"), (4, 8, "2")])
    check("page, tile edge: one circle", markdown, "天地玄黃。宇宙洪荒。")
    check("page, tile edge: the entries", c1_entries(record),
          [("census-confirms-engine-a", 0, None, "天地玄黃。"), ("tile-edge-mark-once", 4, None, "。")])
    check("page, tile edge: the answered pass's count",
          [(p["range"], p.get("engineAKept"), p["marks"], p["places"], p.get("edgeMarksDropped"))
           for p in record["punctuationPasses"]],
          [([0, 4], True, 1, 1, None), ([4, 8], None, 1, 1, "。")])
    check("page, tile edge: the run report", (report["decisionChanges"], report["punctuationKeptFromEngineA"]),
          ({"C1": 2}, 1))

    # A kept block whose comma is re-read (a minority shape on a page of
    # circles): the recount keeps the dash, as the census counted it.
    TEXTS = ["天地。玄黃。宇宙。洪荒。", "日月——盈昃，辰宿。列張。", "寒來。暑往。秋收。冬藏。"]
    blocks = [stand_in.block(t, [0.85 - 0.12 * i, 0.1, 0.06, 0.6]) for i, t in enumerate(TEXTS)]
    with stand_in.book({1: (blocks, "".join(pp.CJK(t) for t in TEXTS))}) as root:
        model = stand_in.StandIn(census="4\n雙圈：0", gap="。")
        record, markdown = stand_in.run(root, model, extra=["--census-confirms-engine-a"])[1]
    check("page, a kept comma re-read: the text", [line for line in markdown.split("\n") if line.strip()],
          ["天地。玄黃。宇宙。洪荒。", "日月——盈昃。辰宿。列張。", "寒來。暑往。秋收。冬藏。"])
    check("page, a kept comma re-read: no punctuate call, one re-read",
          [k for k in model.kinds() if k.startswith("punct") or k.endswith("recheck")], ["gap-recheck"])
    check("page, a kept comma re-read: the dash still counted",
          [(p["block"], p["engineAKept"], p.get("marksBeforeRecheck"), p["marks"], p["places"])
           for p in record["punctuationPasses"]],
          [(0, True, None, 4, 4), (1, True, 4, 4, 4), (2, True, None, 4, 4)])
    check("page, a kept comma re-read: clean", record["doubts"], [])
finally:
    pp.leader_count = real_leader_count

# Resume: a page sealed with the switch is not current for a run without it, nor the reverse.
with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "page-0001.json"
    markdown = "天地玄黃"
    on = pp.decision_provenance(SimpleNamespace(prefer_engine="A", fallback_engine="A", census_confirms_engine_a=True))
    off = pp.decision_provenance(SimpleNamespace(prefer_engine="A", fallback_engine="A"))
    job = SimpleNamespace(out_json=out, out_md=out.with_suffix(".md"))
    results = []
    for sealed_with, run_with in ((on, off), (off, on), (on, on), (off, off)):
        record = {"schemaVersion": pp.SCHEMA_VERSION, "status": "complete", "scanPage": 1,
                  "provenance": {**sealed_with, "markdownSha256": pp.sha256_bytes(markdown.encode("utf-8"))}}
        record["provenance"]["jsonPayloadSha256"] = pp.sha256_bytes(pp.canonical_json_bytes(record))
        out.with_suffix(".md").write_text(markdown, encoding="utf-8")
        out.write_bytes(pp.canonical_json_bytes(record))
        results.append(pp.validate_completion(job, run_with)[0])
check("resume: current only under the same setting", results, [False, False, True, True])

print(f"\n{'FAIL' if failures else 'ok'}: {failures} failure(s)")
sys.exit(1 if failures else 0)
