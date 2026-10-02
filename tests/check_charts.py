#!/usr/bin/env python3
"""Offline checks of the chart step: a printed chart engine A looped on, read
blind as a tree, checked, cut out of both engines' readings and put back.

No model, no GPU.  Made-up pages run through proofread_pages.main() with a
stand-in model (tests/stand_in.py) whose answer to the chart question is set
per check.  Where the calibration corpus is on this machine, the measured page
(廣東法政學堂講義 p.6, a brace chart of the sciences) is checked too: the
trigger over every saved engine-A page, the cut, the checks with the person's
reading of the chart standing in for the model's, and a whole page run scored
against the case's goldens; without the corpus those checks are skipped.

Usage:
    python3 tests/check_charts.py
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import proofread_pages as pp  # noqa: E402
import run_regression as rr  # noqa: E402
import stand_in  # noqa: E402

# --- a made-up page: prose, a chart printed below it, prose beside the chart --
P1 = "天地玄黃宇宙洪荒日月盈昃辰宿列張寒來暑往秋收冬藏閏餘成歲律呂調陽"
P2 = "右圖所示雲騰致雨露結為霜金生麗水玉出崑岡"
CHART = """\
- 萬物
  - 飛禽（羽翔者也）
    - 鳳凰
    - 雁羣
  - 走獸（四足者也）
    - 麒麟
    - 虎豹"""
# Engine B reads the chart row by row across its columns, and misses 凰.
B_CHART = ["萬物", "飛禽羽翔走獸四足", "者也者也", "鳳雁羣麒麟虎豹"]
# Engine A's layout calls the lower half one table - the prose beside the chart
# as a cell, a few names, and a cell its recogniser looped on.
LOOP = ("<table><tr><td>" + P2 + "</td><td>萬物</td></tr><tr><td>飛禽走獸</td><td>"
        + "走獸四足者" * 60 + "</td></tr></table>")
UPPER, LOWER = [0.3, 0.05, 0.6, 0.4], [0.1, 0.5, 0.8, 0.45]


def page(b_chart=B_CHART, loop_label="table", regions=None):
    blocks = [stand_in.block(P1, UPPER), stand_in.block(LOOP, LOWER, label=loop_label)]
    text_b = "\n".join([P1, *b_chart, P2])
    return {1: (blocks, text_b, regions)} if regions is not None else {1: (blocks, text_b)}


def kinds(record: dict) -> list[str]:
    return sorted(d["kind"] for d in record["doubts"])


def run_page(pages, model, extra=()):
    with stand_in.book(pages) as root:
        out = stand_in.run(root, model, extra=extra)[1]
        crops = sorted(p.name for p in (root / "out").glob("*-chart-*.png"))
    return (*out, crops)


def check_parse() -> None:
    parsed = pp.parse_chart("```markdown\n" + CHART + "\n存疑：雁羣掛喺飛禽定走獸睇唔清\n```")
    assert (parsed["form"], len(parsed["edges"]), parsed["notes"]) == ("list", 6, ["羽翔者也", "四足者也"]), parsed
    assert parsed["uncertain"] == ["雁羣掛喺飛禽定走獸睇唔清"] and "存疑" not in parsed["markdown"], parsed
    assert parsed["nodes"][:3] == ["萬物", "飛禽", "鳳凰"] and not parsed["notChart"], parsed
    mermaid = "```mermaid\ngraph TD\n  a[萬物] --> b[飛禽（羽翔者也）]\n  a --> c[走獸]\n  b --> d[鳳凰]\n  c --> d\n```"
    parsed = pp.parse_chart(mermaid)
    assert parsed["form"] == "mermaid" and ["走獸", "鳳凰"] in parsed["edges"], parsed
    assert parsed["markdown"].startswith("```mermaid"), parsed
    for answer in ("非圖", "非圖。呢個係普通表格。"):
        assert pp.parse_chart(answer)["notChart"], answer
    flat = pp.parse_chart("萬物飛禽走獸")
    assert not flat["notChart"] and not flat["edges"], flat
    print("parse_chart: nested list or Mermaid, 存疑 lines kept off the page, 「非圖」")


def check_candidates() -> None:
    blocks = [{"text": P1, "label": "text", "box": UPPER}, {"text": LOOP, "label": "table", "box": LOWER}]
    draft, draft2 = P1 + "\n" + LOOP, "\n".join([P1, *B_CHART, P2])
    assert pp.chart_candidates(blocks, [], draft, draft2) == [(1, None)]
    assert pp.chart_candidates(blocks, [], draft, None) == []
    # A loop labelled as text is not a chart: the quarantine keeps it.
    prose = [blocks[0], dict(blocks[1], label="vertical_text")]
    assert pp.chart_candidates(prose, [], draft, draft2) == []
    # ... unless it lies in a text-less region the layout labelled a chart.
    region = {"label": "chart", "box": [0.05, 0.45, 0.9, 0.52], "order": -1}
    assert pp.chart_candidates(prose, [region], draft, draft2) == [(1, region)]
    assert pp.chart_candidates(prose, [dict(region, label="seal")], draft, draft2) == []
    # A long table engine B reads just as often is no loop, and no chart.
    assert pp.chart_candidates(blocks, [], draft, draft + "\n" + LOOP) == []
    print("chart_candidates: a looped non-prose block, or one in a chart region; not prose, not a witnessed table")


def check_cut() -> None:
    lines = [P1, *B_CHART, P2]
    assert pp.chart_run(lines, CHART) == (21, 1, 4), pp.chart_run(lines, CHART)
    assert pp.chart_run([P1, P2], CHART) == (0, -1, -2)
    blocks = [{"text": P1, "label": "text", "box": UPPER}, {"text": LOOP, "label": "table", "box": LOWER}]
    cut = pp.cut_chart(blocks, 1, "\n".join(lines), CHART)
    assert cut["engineBLines"] == B_CHART and cut["draft2"] == P1 + "\n" + P2, cut
    assert cut["cutAt"] == len(P1) and cut["salvagedCells"] == [P2] and cut["cellsLeftOut"] == 3, cut
    assert [(b["label"], b["layoutIndex"]) for b in cut["blocks"]] == [("text", 0), ("chart-region", 1)], cut["blocks"]
    assert cut["blocks"][1]["box"] == LOWER and cut["draft"] == P1 + "\n" + P2
    # Engine B read the chart first: the region's block goes before the prose.
    cut = pp.cut_chart(blocks, 1, "\n".join([*B_CHART, P2, P1]), CHART)
    assert cut["cutAt"] == 0 and [b["label"] for b in cut["blocks"]] == ["chart-region", "text"], cut["blocks"]
    # Text engine A read in another block is not the chart's: a heading made
    # of the chart's names, when engine B read none of the chart, is not cut.
    head = "飛禽走獸"
    with_head = [{"text": head, "label": "paragraph_title", "box": [0.4, 0.0, 0.2, 0.04]}, *blocks]
    assert pp.chart_run([head, P1, P2], CHART) == (4, 0, 0)
    cut = pp.cut_chart(with_head, 2, "\n".join([head, P1, P2]), CHART)
    assert cut["engineBLines"] == [] and cut["cutAt"] is None, cut["engineBLines"]
    assert cut["engineBOutside"] == {"otherBlocks": len(head + P1), "regionProse": 0}, cut["engineBOutside"]
    assert [b["label"] for b in cut["blocks"]] == ["paragraph_title", "text", "chart-region"]
    # A line of the prose beside the chart that names nodes and runs on into
    # the passage on engine B's next line, as engine A's cell reads it, stays prose.
    lead = "鳳凰麒麟之類"
    region = "<table><tr><td>" + lead + P2 + "</td><td>萬物</td></tr><tr><td>" + "走獸四足者" * 60 + "</td></tr></table>"
    lines = [P1, *B_CHART[:3], lead, P2]
    assert pp.chart_run(lines, CHART)[1:] == (1, 4)
    cut = pp.cut_chart([blocks[0], dict(blocks[1], text=region)], 1, "\n".join(lines), CHART)
    assert cut["engineBLines"] == B_CHART[:3] and cut["salvagedCells"] == [lead + P2], cut["engineBLines"]
    assert cut["engineBOutside"] == {"otherBlocks": len(P1), "regionProse": len(lead + P2)}, cut["engineBOutside"]
    print("cut_chart: engine B's chart lines out, the prose cell kept, the block where engine B read the chart; "
          "not text engine A read outside the chart")


def check_repeated_cells() -> None:
    # The recogniser repeats the prose cell (as it repeated one note in five
    # cells on the measured page); engine B read the prose once.
    looped = ("<table><tr><td>" + P2 + "</td><td>萬物</td></tr><tr><td>" + P2 + "</td><td>"
              + "走獸四足者" * 60 + "</td></tr></table>")
    cells = pp.chart_cells(looped)
    assert pp.salvage_cells(cells, P1 + P2) == ([P2], [{"text": P2, "repeats": 0}])
    # Printed twice and read twice by engine B: two stretches, both cells kept.
    assert pp.salvage_cells([P2, P2], P1 + P2 + P2) == ([P2, P2], [])
    # A cell that repeats part of a kept one and holds a stretch of its own is kept.
    assert pp.salvage_cells([P2[:10], P2], P1 + P2)[0] == [P2[:10], P2]
    blocks = [stand_in.block(P1, UPPER), stand_in.block(looped, LOWER, label="table")]
    witnessed = [*B_CHART[:3], "鳳凰雁羣麒麟虎豹"]
    record, markdown, _ = run_page({1: (blocks, "\n".join([P1, *witnessed, P2]))},
                                   stand_in.StandIn(census=0, chart=CHART))
    assert markdown == P1 + "\n\n" + CHART + "\n\n" + P2, markdown
    [chart] = record["charts"]
    assert chart["salvagedCells"] == [P2] and chart["repeatedCells"] == [{"text": P2, "repeats": 0}], chart
    assert chart["cellsLeftOut"] == 3 and record["auditorClean"], (chart["cellsLeftOut"], kinds(record))
    print("repeated cells: a cell the loop repeated is kept once, as engine B read it, and recorded")


def check_checks() -> None:
    parsed = pp.parse_chart(CHART)
    page_a, page_b = P1 + "\n" + LOOP, "\n".join([P1, *B_CHART, P2])
    checked = pp.chart_checks(parsed, LOOP, "\n".join(B_CHART), page_a, page_b, P1 + P2)
    assert (checked["unwitnessed"], checked["unwitnessedNodes"], checked["lost"]) == ("凰", ["鳳凰"], ""), checked
    assert not checked["degenerate"] and pp.chart_refusal(checked, False) is None
    # 羣 written 群 (an OpenCC allograph pair) is written back as engine B
    # printed it.
    variant = pp.parse_chart(CHART.replace("雁羣", "雁群"))
    assert pp.classify_pair(None, "群", "羣") == "variant"
    checked = pp.chart_checks(variant, LOOP, "\n".join(B_CHART), page_a, page_b, P1 + P2)
    assert [(m["written"], m["printed"], m["readBy"]) for m in checked["mappedVariants"]] == [("群", "羣", "B")], checked
    assert "雁羣" in checked["markdown"] and "群" not in checked["markdown"] and checked["unwitnessed"] == "凰"
    kept = pp.chart_checks(variant, LOOP, "\n".join(B_CHART), page_a, page_b, P1 + P2, variants=False)
    assert kept["mappedVariants"] == [] and kept["unwitnessed"] == "凰群", kept
    # Characters both engines read there that the chart leaves out.
    short = pp.parse_chart("- 萬物\n  - 飛禽\n  - 走獸")
    checked = pp.chart_checks(short, LOOP, "\n".join(B_CHART), page_a, page_b, P1 + P2)
    assert checked["lost"] == "四足者" and pp.chart_refusal(checked, False) is None, checked
    # A looped answer is refused only when it also loses what both engines read.
    loop = pp.parse_chart("- 萬物\n" + "  - 飛禽\n    - 鴻雁\n" * 30)
    checked = pp.chart_checks(loop, LOOP, "\n".join(B_CHART), page_a, page_b, P1 + P2)
    assert checked["degenerate"] and checked["lost"], checked
    assert "repeats itself" in pp.chart_refusal(checked, False)
    assert "no tree" in pp.chart_refusal(None, False) and "cut off" in pp.chart_refusal(checked, True)
    # chart_step asks whether the answer was cut (no_answer_cut), not merely
    # degraded: an empty reply that finished on its own holds no tree.
    empty, cut = {"degraded": True, "rungsAsked": 1, "rungsCutOff": 0}, {"degraded": True, "rungsAsked": 4, "rungsCutOff": 4}
    assert "no tree" in pp.chart_refusal(None, pp.no_answer_cut(pp.no_answer("\n", empty)))
    assert "cut off" in pp.chart_refusal(None, pp.no_answer_cut(pp.no_answer("- 萬物", cut)))
    print("chart_checks: unwitnessed, lost and variant characters; refused only degenerate and uncorroborated")


def check_position() -> None:
    resolved = "甲乙丙丁戊己庚辛"
    text = "## 甲乙\n\n丙丁。。戊己「庚辛」"
    at, how = pp.chart_position(text, resolved, 4)
    assert how == "after" and text[:at] == "## 甲乙\n\n丙丁。。", (at, how)
    assert pp.insert_chart(text, at, "- 圖") == "## 甲乙\n\n丙丁。。\n\n- 圖\n\n戊己「庚辛」"
    # The character before is gone (furniture the formatter removed): before the one after.
    at, how = pp.chart_position("## 甲乙\n\n丙丁。。「戊己」", "甲乙丙丁某戊己", 5)
    assert how == "before" and at == len("## 甲乙\n\n丙丁。。"), (at, how)
    at, how = pp.chart_position("甲乙\n\n## 丙丁", "甲乙某丙丁", 3)
    assert how == "before" and at == len("甲乙\n\n"), (at, how)
    # Neither is on the page: the end, with a doubt.
    assert pp.chart_position("甲乙", "甲乙某丙丁", 3) == (2, "end")
    # Never inside a table, a heading or open markup: to its end ("after") or
    # its start ("before").
    chart = "- 圖\n  - 子"
    for text, resolved, offset, out_of, want in (
            ("前文。\n\n| 甲 | 乙 |\n| --- | --- |\n| 丙 | 丁 |\n\n後文。", "前文甲乙丙丁後文", 6, "table",
             "前文。\n\n| 甲 | 乙 |\n| --- | --- |\n| 丙 | 丁 |\n\n" + chart + "\n\n後文。"),
            ("前文。\n\n<table><tr><td>甲</td><td>乙</td></tr></table>\n\n後文。", "前文甲乙後文", 3, "table",
             "前文。\n\n<table><tr><td>甲</td><td>乙</td></tr></table>\n\n" + chart + "\n\n後文。"),
            ("前文。\n\n| 甲 | 乙 |\n| --- | --- |\n| 丙 | 丁 |", "前文某甲乙丙丁", 3, "table",
             "前文。\n\n" + chart + "\n\n| 甲 | 乙 |\n| --- | --- |\n| 丙 | 丁 |"),
            ("**甲乙**\n\n丙丁", "甲乙丙丁", 1, "markup", "**甲乙**\n\n" + chart + "\n\n丙丁"),
            ("甲<u>乙丙</u>丁。\n\n戊", "甲乙丙丁戊", 2, "markup", "甲<u>乙丙</u>丁。\n\n" + chart + "\n\n戊"),
            ("## 甲乙丙\n\n丁戊", "甲乙丙丁戊", 2, "heading", "## 甲乙丙\n\n" + chart + "\n\n丁戊"),
            # Prose is split where the chart was read, as before.
            ("甲乙。丙丁。", "甲乙丙丁", 2, None, "甲乙。\n\n" + chart + "\n\n丙丁。")):
        at, how = pp.chart_position(text, resolved, offset)
        at, moved = pp.chart_block_edge(text, at, how)
        assert moved == out_of and pp.insert_chart(text, at, chart) == want, (text, moved, at)
    print("chart_position: after the character before it and its marks, else before the next, else the end; "
          "never inside a table, a heading or open markup")


def check_page() -> None:
    model = stand_in.StandIn(census=0, chart=CHART)
    record, markdown, crops = run_page(page(), model)
    assert record["mode"] == "merge", record["mode"]
    assert markdown == P1 + "\n\n" + CHART + "\n\n" + P2, markdown
    assert crops == ["page-0001-chart-01.png"] and model.kinds().count("chart") == 1, (crops, model.kinds())
    [chart] = record["charts"]
    assert (chart["status"], chart["block"], chart["label"], chart["form"]) == ("placed", 1, "table", "list"), chart
    assert (chart["engineBLines"], chart["salvagedCells"], chart["unwitnessed"]) == (B_CHART, [P2], "凰"), chart
    assert chart["placement"]["placed"] == "after" and chart["placement"]["from"] == "engine B's reading", chart
    # D9: a check doubts it (凰, which no engine read), so it is a review item.
    assert kinds(record) == ["chart-unwitnessed"], kinds(record)
    assert record["engineALoopsDropped"] == [] and record["engineCoverage"]["engineB"] == len(
        "".join([P1, *B_CHART, P2])), record["engineCoverage"]
    [change] = [c for c in record["decisionChanges"] if c["decision"] == "chart"]
    assert (change["rule"], change["switch"], change["after"]) == ("chart-read", "--no-charts", CHART), change
    # Without the chart step the quarantine writes engine B's chart lines there.
    assert change["before"] == "".join(B_CHART) and change["mergedOffset"] == len(P1), change
    assert change["evidence"]["doubts"] == ["chart-unwitnessed"], change
    assert record["provenance"]["charts"] == "on" and record["provenance"]["chartReview"] == "doubt"
    # A chart every character of which an engine read raises no doubt (D9) ...
    witnessed = [*B_CHART[:3], "鳳凰雁羣麒麟虎豹"]
    record, markdown, _ = run_page(page(witnessed), stand_in.StandIn(census=0, chart=CHART))
    assert kinds(record) == [] and record["auditorClean"], kinds(record)
    # ... unless every chart is a review item (--no-chart-review-by-doubt).
    record, markdown, _ = run_page(page(witnessed), stand_in.StandIn(census=0, chart=CHART),
                                   ["--no-chart-review-by-doubt"])
    assert kinds(record) == ["chart-review"] and record["provenance"]["chartReview"] == "every", kinds(record)
    # A chart that repeats itself but loses nothing both engines read is
    # placed (not refused) and doubted, so D9 makes it a review item.
    looped = CHART + "\n" + "  - 飛禽（羽翔者也）\n    - 鳳凰\n" * 30
    record, markdown, _ = run_page(page(witnessed), stand_in.StandIn(census=0, chart=looped))
    [chart] = record["charts"]
    assert chart["status"] == "placed" and chart["degenerate"] and chart["lost"] == "", chart
    assert kinds(record) == ["chart-degenerate"] and not record["auditorClean"], kinds(record)
    [change] = [c for c in record["decisionChanges"] if c["decision"] == "chart"]
    assert change["evidence"]["doubts"] == ["chart-degenerate"], change["evidence"]
    print("page: the chart read, cut out, merged around and put back where engine B read it; D9 doubts")


def check_uncertain_and_variants() -> None:
    answer = CHART.replace("雁羣", "雁群") + "\n存疑：雁羣掛喺邊枝睇唔清"
    record, markdown, _ = run_page(page(), stand_in.StandIn(census=0, chart=answer))
    assert "存疑" not in markdown and "雁羣" in markdown and "群" not in markdown, markdown
    assert kinds(record) == ["chart-uncertain", "chart-unwitnessed"], kinds(record)
    rules = [(c["rule"], c["before"], c["after"]) for c in record["decisionChanges"] if c["decision"] == "chart"]
    assert rules[1] == ("chart-variant-mapped", "群", "羣") and rules[0][0] == "chart-read", rules
    record, markdown, _ = run_page(page(), stand_in.StandIn(census=0, chart=answer), ["--no-chart-variants"])
    assert "雁群" in markdown and record["charts"][0]["unwitnessed"] == "凰群", record["charts"][0]
    assert [c["rule"] for c in record["decisionChanges"] if c["decision"] == "chart"] == ["chart-read"]
    print("page: 存疑 lines are doubts, not text; a variant goes back to the printed form unless switched off")


def comparable(record: dict) -> dict:
    """A seal without what differs between two runs of the same text: time,
    where the book was written, calls, the switches' provenance, the chart
    question's own record."""
    return {k: v for k, v in record.items()
            if k not in ("generatedAt", "seconds", "renderFile", "calls", "provenance", "charts")}


def check_old_path() -> None:
    old_record, old_md, _ = run_page(page(), stand_in.StandIn(census=0, chart=CHART), ["--no-charts"])
    assert old_record["charts"] == [] and old_record["engineALoopsDropped"], old_record["engineALoopsDropped"]
    assert old_record["provenance"]["charts"] == "off"
    # 「非圖」: the region goes down the old path, the merge's inputs untouched.
    record, markdown, _ = run_page(page(), stand_in.StandIn(census=0, chart="非圖"))
    assert markdown == old_md and comparable(record) == comparable(old_record), markdown
    assert [c["status"] for c in record["charts"]] == ["not-a-chart"], record["charts"]
    # A looped answer, twice: refused, a chart-refused doubt, the old path.
    looped = "- 萬物\n" + "  - 飛禽\n    - 鴻雁\n" * 30
    model = stand_in.StandIn(census=0, chart=looped)
    record, markdown, _ = run_page(page(), model)
    assert model.kinds().count("chart") == 1 and model.kinds().count("chart-retry") == 1, model.kinds()
    assert markdown == old_md and record["charts"][0]["status"] == "refused", record["charts"]
    assert len(record["charts"][0]["refusals"]) == 2 and "chart-refused" in kinds(record), kinds(record)
    assert sorted(set(kinds(record)) - {"chart-refused"}) == kinds(old_record)
    # Refused, then read on the retry: placed, the refusal kept.
    record, markdown, _ = run_page(page(), stand_in.StandIn(census=0, chart=[looped, CHART]))
    assert record["charts"][0]["status"] == "placed" and len(record["charts"][0]["refusals"]) == 1
    assert markdown == P1 + "\n\n" + CHART + "\n\n" + P2, markdown
    print("old path: --no-charts, 「非圖」 and a refused chart leave the page as it was, the refusal a doubt")


def check_region() -> None:
    # A text block (not a table) the layout found inside a text-less chart
    # region, looping: the chart step, with the region's box in the crop.
    region = stand_in.region([0.05, 0.45, 0.9, 0.52])
    record, markdown, _ = run_page(page(loop_label="vertical_text", regions=[region]),
                                   stand_in.StandIn(census=0, chart=CHART))
    [chart] = record["charts"]
    assert chart["status"] == "placed" and chart["region"]["label"] == "chart", chart
    assert chart["box"] == [0.05, 0.45, 0.9, 0.52], chart["box"]
    assert markdown == P1 + "\n\n" + CHART + "\n\n" + P2, markdown
    # Without the region it is prose that looped: the quarantine, no chart question.
    model = stand_in.StandIn(census=0, chart=CHART)
    record, _, _ = run_page(page(loop_label="vertical_text"), model)
    assert record["charts"] == [] and "chart" not in model.kinds() and record["engineALoopsDropped"]
    print("region: a looped text block in a text-less chart region is read as a chart")


def check_precedence() -> None:
    # A looped chart and a looped list over an empty area on one page: the
    # chart step takes the chart, and the quarantine the other loop, which
    # keeps its layout index (two looped blocks sent the page whole before).
    listed = "".join(f"卷{n}" for n in "一二三四五六七八九十") * 30
    blocks = [stand_in.block(P1, UPPER), stand_in.block(LOOP, LOWER, label="table"),
              stand_in.block(listed, [0.0, 0.5, 0.08, 0.45], label="vertical_text")]
    pages = {1: (blocks, "\n".join([P1, *B_CHART, P2]))}
    record, markdown, _ = run_page(pages, stand_in.StandIn(census=0, chart=CHART))
    assert record["mode"] == "merge" and [c["status"] for c in record["charts"]] == ["placed"], record["mode"]
    assert [d["block"] for d in record["engineALoopsDropped"]] == [2], record["engineALoopsDropped"]
    assert markdown == P1 + "\n\n" + CHART + "\n\n" + P2, markdown
    record, _, _ = run_page(pages, stand_in.StandIn(census=0, chart=CHART), ["--no-charts"])
    assert record["mode"].startswith("merge-order-conflict") and record["engineALoopsDropped"] == [], record["mode"]
    print("precedence: the chart step takes the chart, the quarantine a loop that is not one")


def check_order_conflict_window_before_chart() -> None:
    # An order conflict that keeps engine A's text, with a table block before
    # the chart that engine B contradicts (a cell read the other way round):
    # the table's text comes from engine B's lines (window_merge), four
    # characters longer than engine A's.  The chart goes where its block
    # stands in the merged text, after the prose, not four characters inside
    # it (it split 律呂調陽 off the prose on the merge commit, when the
    # order-conflict offset was engine A's own).
    first, second, third = "甲乙丙丁戊己庚辛", "壬癸子丑寅卯辰巳", "青赤黃白黑紫綠藍"
    table = f"<table><tr><td>{first}{second}</td></tr><tr><td>{third}</td></tr></table>"
    blocks = [stand_in.block(table, [0.1, 0.0, 0.8, 0.04], label="table"),
              stand_in.block(P1, UPPER), stand_in.block(LOOP, LOWER, label="table")]
    text_b = "\n".join([third, second, first + "午未申酉", P1[::-1], *B_CHART, P2])
    record, markdown, _ = run_page({1: (blocks, text_b)}, stand_in.StandIn(census=0, chart=CHART))
    [chart] = record["charts"]
    assert record["mode"] == "merge-order-conflict" and chart["status"] == "placed", record["mode"]
    assert record["tablesRebuilt"][0]["from"].startswith("grid refused"), record["tablesRebuilt"]
    assert chart["placement"]["context"].startswith("閏餘成歲律呂調陽|"), chart["placement"]
    assert markdown.endswith(P1 + "\n\n" + CHART + "\n\n" + P2), markdown
    print("order conflict: a chart after a table read from engine B's lines stands after the prose")


def check_placement_fallbacks() -> None:
    # Engine B read none of the chart: nothing is cut from its reading, and the
    # chart goes where the region's block stands in engine A's reading.
    record, markdown, _ = run_page(page(b_chart=[]), stand_in.StandIn(census=0, chart=CHART))
    [chart] = record["charts"]
    assert chart["engineBLines"] == [] and chart["engineBCutAt"] is None, chart
    assert chart["placement"]["from"] == "engine A's blocks" and chart["placement"]["mergedOffset"] == len(P1)
    assert markdown == P1 + "\n\n" + CHART + "\n\n" + P2, markdown
    # Engine B read the prose in another order: an order conflict that keeps
    # engine A's text, the chart at its block's place there.
    blocks = [stand_in.block(P1, UPPER), stand_in.block(LOOP, LOWER, label="table")]
    record, markdown, _ = run_page({1: (blocks, "\n".join([P1[::-1], *B_CHART, P2]))},
                                   stand_in.StandIn(census=0, chart=CHART))
    assert record["mode"] == "merge-order-conflict" and record["charts"][0]["status"] == "placed", record["mode"]
    assert markdown == P1 + "\n\n" + CHART + "\n\n" + P2, markdown
    # Engine B read none of the chart but a heading made of its names, which
    # engine A read as a block of its own: nothing is cut, the page in order.
    head = "飛禽走獸"
    blocks = [stand_in.block(head, [0.4, 0.0, 0.2, 0.04], label="paragraph_title"),
              stand_in.block(P1, UPPER), stand_in.block(LOOP, LOWER, label="table")]
    record, markdown, _ = run_page({1: (blocks, "\n".join([head, P1, P2]))}, stand_in.StandIn(census=0, chart=CHART))
    [chart] = record["charts"]
    assert record["mode"] == "merge" and chart["engineBLines"] == [] and chart["engineBCutAt"] is None, chart
    assert markdown == head + "\n" + P1 + "\n\n" + CHART + "\n\n" + P2, markdown
    # A prose line beside the chart that engine A read with the passage after
    # it: the chart goes before the passage, not inside it.
    lead = "鳳凰麒麟之類"
    region = "<table><tr><td>" + lead + P2 + "</td><td>萬物</td></tr><tr><td>" + "走獸四足者" * 60 + "</td></tr></table>"
    blocks = [stand_in.block(P1 * 2, UPPER), stand_in.block(region, LOWER, label="table")]
    record, markdown, _ = run_page({1: (blocks, "\n".join([P1 * 2, *B_CHART[:3], lead, P2]))},
                                   stand_in.StandIn(census=0, chart=CHART))
    assert record["charts"][0]["engineBLines"] == B_CHART[:3], record["charts"][0]["engineBLines"]
    assert markdown == P1 * 2 + "\n\n" + CHART + "\n\n" + lead + P2, markdown
    print("placement: where engine A's block stands when engine B read none of the chart, or the page is one "
          "engine's; engine A's other text and a prose cell's passage are not cut as the chart")


def check_order_test() -> None:
    # Engine B read the prose beside the chart with a different character
    # every few, so no cell of the region is kept: its reading is the
    # region's, out of the order test, and on the page after the chart.
    variant = "右圖所示云騰致雨露結爲霜金生麗水玉出昆岡"
    blocks = [stand_in.block(P1, UPPER), stand_in.block(LOOP, LOWER, label="table")]
    record, markdown, _ = run_page({1: (blocks, "\n".join([P1, *B_CHART, variant]))},
                                   stand_in.StandIn(census=0, chart=CHART))
    [chart] = record["charts"]
    assert record["mode"] == "merge" and chart["salvagedCells"] == [], (record["mode"], chart["salvagedCells"])
    assert chart["engineBRegionReading"] == variant, chart["engineBRegionReading"]
    assert markdown == P1 + "\n\n" + CHART + "\n\n" + variant, markdown
    record, _, _ = run_page(page(), stand_in.StandIn(census=0, chart=CHART))
    assert record["charts"][0]["engineBRegionReading"] == "", record["charts"][0]
    # Engine B's reading shares no 4-gram with engine A's region: the page with
    # the chart cut out reads in another order, where without the chart step
    # it merges.  The chart is withdrawn and the page goes the old way.
    unlike = "".join(c if i % 3 else "某" for i, c in enumerate(P2))
    pages = {1: (blocks, "\n".join([P1, *B_CHART, unlike]))}
    old_record, old_md, _ = run_page(pages, stand_in.StandIn(census=0, chart=CHART), ["--no-charts"])
    record, markdown, _ = run_page(pages, stand_in.StandIn(census=0, chart=CHART))
    [chart] = record["charts"]
    assert chart["status"] == "withdrawn" and chart["withdrawn"] == {
        "agreement": 0.615, "agreementWithoutChart": 1.0}, chart.get("withdrawn")
    assert markdown == old_md and record["mode"] == old_record["mode"] == "merge", markdown
    assert kinds(record) == sorted(kinds(old_record) + ["chart-withdrawn"]), kinds(record)
    assert [c for c in record["decisionChanges"] if c["decision"] == "chart"] == [], record["decisionChanges"]
    same = ("auditorClean", "auditorReport", "doubts")
    assert {k: v for k, v in comparable(record).items() if k not in same} == {
        k: v for k, v in comparable(old_record).items() if k not in same}
    print("order test: engine B's reading of the region is left out of it; a chart that would make an order "
          "conflict of a page that merges without it is withdrawn")


def check_chart_only() -> None:
    # A page that holds only the chart: engine A's block is the chart and its
    # loop, engine B read only the chart.  Nothing is left to merge or format.
    only = "<table><tr><td>萬物</td></tr><tr><td>飛禽走獸</td><td>" + "走獸四足者" * 60 + "</td></tr></table>"
    model = stand_in.StandIn(census=0, chart=CHART)
    record, markdown, _ = run_page({1: ([stand_in.block(only, LOWER, label="table")], "\n".join(B_CHART))}, model)
    assert markdown == CHART and record["mode"] == "merge", (markdown, record["mode"])
    assert kinds(record) == ["chart-unwitnessed"], kinds(record)
    assert record["charts"][0]["placement"]["placed"] == "page", record["charts"][0]["placement"]
    assert "format" not in model.kinds(), model.kinds()
    print("a page that is only its chart: the chart is the page, no format call, no position doubt")


def check_after_table() -> None:
    # Engine B read the chart just after a table, which the formatter writes
    # as a Markdown table: the chart goes after the table, not into its last row.
    table_a = "<table><tr><td>金銀</td><td>銅鐵</td></tr><tr><td>錫鉛</td><td>汞硫</td></tr></table>"
    table_md = "| 金銀 | 銅鐵 |\n| --- | --- |\n| 錫鉛 | 汞硫 |"
    blocks = [stand_in.block(P1, UPPER), stand_in.block(table_a, [0.3, 0.3, 0.6, 0.1], label="table"),
              stand_in.block(LOOP, LOWER, label="table")]
    witnessed = [*B_CHART[:3], "鳳凰雁羣麒麟虎豹"]
    text_b = "\n".join([P1, "金銀銅鐵", "錫鉛汞硫", *witnessed, P2])

    def formatter(text: str, kind: str) -> str:
        return text.replace("金銀銅鐵錫鉛汞硫", "\n" + table_md + "\n")

    record, markdown, _ = run_page({1: (blocks, text_b)}, stand_in.StandIn(census=0, chart=CHART,
                                                                          formatter=formatter))
    assert markdown == "\n\n".join([P1, table_md, CHART, P2]), markdown
    [chart] = record["charts"]
    assert (chart["placement"]["placed"], chart["placement"]["outOf"]) == ("after", "table"), chart["placement"]
    [change] = [c for c in record["decisionChanges"] if c["decision"] == "chart"]
    assert change["evidence"]["outOf"] == "table", change["evidence"]
    print("after a table: the chart goes after the table, not into its last row")


def check_two_charts() -> None:
    p3 = "寸陰是競資父事君曰嚴與敬孝當竭力忠則盡命臨深履薄"
    chart2 = "- 草木\n  - 喬木（高者也）\n    - 松柏\n  - 灌木（低者也）\n    - 荊棘"
    b_chart2 = ["草木", "喬木高者灌木低者", "也也", "松柏荊棘"]
    loop2 = "<table><tr><td>" + p3 + "</td><td>" + "灌木低者也" * 60 + "</td></tr></table>"
    blocks = [stand_in.block(P1, UPPER), stand_in.block(LOOP, LOWER, label="table"),
              stand_in.block(loop2, [0.1, 0.1, 0.1, 0.3], label="table")]
    text_b = "\n".join([P1, *B_CHART, P2, *b_chart2, p3])
    record, markdown, crops = run_page({1: (blocks, text_b)}, stand_in.StandIn(census=0, chart=[CHART, chart2]))
    assert [c["status"] for c in record["charts"]] == ["placed", "placed"], record["charts"]
    assert markdown == "\n\n".join([P1, CHART, P2, chart2, p3]), markdown
    assert crops == ["page-0001-chart-01.png", "page-0001-chart-02.png"], crops
    print("two charts on a page: each read, cut and put back")


# --- the measured page ----------------------------------------------------------
CORPUS = Path.home() / "Documents/GitHub/jyut-ocr-corpus"
BOOK = CORPUS / "faatzing"
GOLDEN_TREE = rr.GOLDEN / "faatzing" / "page-0006-tree.md"


def draw_spread(path: Path, fold: tuple[int, int] = (480, 520), prose: tuple[int, int] = (120, 220),
                rules: bool = True, chart: tuple[int, ...] = (300, 360, 620, 700, 780)) -> None:
    """A made-up render of 1000 x 1400: two half-leaves with a fold strip
    between them (two rules, unless RULES is false, and a title the height of
    the lower half), a chart of sparse columns in the lower half (CHART, their
    left edges), and at its left end prose columns - glyphs 30 px square
    with 6 px between - behind a frame rule."""
    from PIL import Image, ImageDraw
    image = Image.new("L", (1000, 1400), 255)
    draw = ImageDraw.Draw(image)
    top, bottom = 700, 1330
    draw.rectangle((100, top, 106, bottom), fill=0)                       # the frame rule
    for x in range(prose[0], prose[1], 45):                              # prose columns
        for y in range(top + 10, bottom - 60, 36):
            draw.rectangle((x, y, x + 30, y + 30), fill=0)
    for x in chart:                                                      # the chart's columns
        for y in (top + 20, top + 300, top + 520):
            draw.rectangle((x, y, x + 30, y + 60), fill=0)
    if rules:
        draw.rectangle((fold[0], top, fold[0] + 4, bottom), fill=0)      # the fold's rules
        draw.rectangle((fold[1] - 4, top, fold[1], bottom), fill=0)
    draw.rectangle((fold[0] + 12, top, fold[1] - 12, bottom), fill=0)    # its title
    image.save(path)


def check_fold_and_prose_box() -> None:
    """The fold between two leaves, from the book's layout (fold_band), cut
    out of a chart's crop (fold_cut, proposed decision D25); the prose a chart's
    region keeps given its own box (prose_box).  Shapes measured on the
    lecture book's chart (a brace chart across the fold, the title printed
    down the fold read as a second root; the region's prose cropped as a
    strip 7 px wide)."""
    import json as _json
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        paths = []
        for n in range(4):
            lines = [{"text": "天地玄黃宇宙洪荒", "boundingBox": [0.55, 0.1, 0.3, 0.4], "blockLabel": "text"},
                     {"text": "某某講義", "boundingBox": [0.49, 0.1, 0.02, 0.1], "blockLabel": "text"},
                     {"text": "日月盈昃辰宿列張", "boundingBox": [0.1, 0.1, 0.3, 0.4], "blockLabel": "text"},
                     {"text": "第一册", "boundingBox": [0.95, 0.5, 0.02, 0.1], "blockLabel": "footer"}]
            if n == 3:
                lines = lines[:1] + lines[2:]
            path = tmp / f"page-{n + 1:04d}.json"
            path.write_text(_json.dumps({"lines": lines}, ensure_ascii=False), encoding="utf-8")
            paths.append(path)
        found = pp.fold_band(paths)
        assert found == {"band": [0.49, 0.51], "labelWidth": 0.02, "labels": 3, "pages": 3}, found
        assert pp.fold_band(paths[2:]) is None, "a label on too few pages is no fold"
        render = tmp / "page-0001.png"
        draw_spread(render)
        region = [0.1, 0.5, 0.8, 0.45]
        fold = {"band": [0.47, 0.53], "labelWidth": 0.02}
        crop, cut = pp.fold_cut(render, region, fold)
        assert cut is not None and cut["cut"] == [0.48, 0.521] and cut["pixels"] == 41, cut
        assert cut["rules"] == [[0.48, 0.485], [0.516, 0.521]], cut
        from PIL import Image
        with Image.open(io.BytesIO(crop)) as image:
            whole = pp.crop_block(render, region, pad=0.012)
            with Image.open(io.BytesIO(whole)) as full:
                # 41 px narrower, then enlarged for the encoder (upscale_crop).
                ratio = (image.width / image.height) / ((full.width - 41) / full.height)
                assert abs(ratio - 1) < 0.01, (image.size, full.size)
        assert pp.fold_cut(render, region, None) == (None, None)
        assert pp.fold_cut(render, [0.55, 0.5, 0.35, 0.45], fold) == (None, None), "no fold in the box"
        # The band is where to look; the fold's rules say where it is.  A
        # column of the chart's own text centred in the band, beside the
        # fold (the shape of the measured page scanned a few pixels further
        # over), is kept: the cut runs from rule to rule.
        draw_spread(render, chart=(300, 360, 445, 620, 700, 780))
        crop, cut = pp.fold_cut(render, region, {"band": [0.44, 0.53], "labelWidth": 0.02})
        assert cut is not None and cut["cut"] == [0.48, 0.521], cut
        # A crop that shows no rules shows no fold: nothing is cut.
        draw_spread(render, rules=False)
        assert pp.fold_cut(render, region, fold) == (None, None), "no rules, no cut"
        draw_spread(render)
        box = pp.prose_box(render, region)
        assert box is not None and 0.11 <= box[0] <= 0.12 and 0.24 <= box[0] + box[2] <= 0.26, box
        draw_spread(render, prose=(0, 0))
        assert pp.prose_box(render, region) is None, "no prose at either end"
    print("fold and prose: the fold's band from the layout, cut out of a chart crop; the prose's own box")


def check_fold_page() -> None:
    """A chart across the fold of a book whose layout shows the fold: the
    chart is read on a crop with the fold cut out, told so, and the change is
    sealed (D25); --no-fold-cut reads the crop as it stands."""
    pages = {}
    for n in (1, 2, 3):
        blocks = [stand_in.block(P1, [0.55, 0.05, 0.35, 0.4]), stand_in.block("某某講義", [0.49, 0.05, 0.02, 0.1]),
                  stand_in.block(P1[::-1], [0.1, 0.05, 0.35, 0.4])]
        if n == 1:
            blocks.append(stand_in.block(LOOP, LOWER, label="table"))
        text_b = "\n".join([P1, "某某講義", P1[::-1]] + ([*B_CHART, P2] if n == 1 else []))
        pages[n] = (blocks, text_b)
    for extra in ((), ("--no-fold-cut",)):
        model = stand_in.StandIn(census=0, chart=CHART)
        with stand_in.book(pages) as root:
            draw_spread(root / "renders" / "page-0001.png")
            record, markdown = stand_in.run(root, model, pages="1", extra=extra)[1]
            report = json.loads((root / "report.json").read_text(encoding="utf-8"))
        [chart] = record["charts"]
        asked = [user for kind, user in model.calls if kind == "chart"]
        changes = [c for c in record["decisionChanges"] if c["decision"] == "D25"]
        if not extra:
            assert chart["status"] == "placed" and chart["foldCut"]["band"] == [0.49, 0.51], chart.get("foldCut")
            assert asked and asked[0].startswith(pp.CHART_FOLD_NOTE), asked
            assert len(changes) == 1 and changes[0]["after"] == CHART and changes[0]["before"] is None, changes
            assert record["provenance"]["foldCut"] == "band 0.49-0.51", record["provenance"]["foldCut"]
            assert report["foldBand"]["band"] == [0.49, 0.51], report["foldBand"]
        else:
            assert "foldCut" not in chart and not asked[0].startswith(pp.CHART_FOLD_NOTE) and not changes
            assert record["provenance"]["foldCut"] == "off"
    print("fold page: the chart read with the fold cut out and sealed (D25); off, as it stands")


def corpus_page() -> tuple[list, str, str] | None:
    if not (BOOK / "ocr-paddle" / "page-0006.json").is_file() or not (BOOK / "ocr-hunyuan").is_dir():
        return None
    blocks = pp.load_blocks(BOOK / "ocr-paddle" / "page-0006.json")
    draft = (BOOK / "ocr-paddle" / "page-0006.txt").read_text(encoding="utf-8").strip()
    draft2 = pp.strip_grounding((BOOK / "ocr-hunyuan" / "page-0006.txt").read_text(encoding="utf-8")).strip()
    return blocks, draft, draft2


def check_corpus_trigger() -> None:
    fired, tables = [], 0
    for book in sorted(p for p in CORPUS.iterdir() if (p / "ocr-paddle").is_dir() and not p.is_symlink()):
        for path in sorted((book / "ocr-paddle").glob("page-*.json")):
            other = book / "ocr-hunyuan" / path.with_suffix(".txt").name
            if not other.is_file():
                continue
            blocks = pp.load_blocks(path)
            tables += sum(1 for b in blocks if b["label"] in pp.CHART_LABELS)
            draft = path.with_suffix(".txt").read_text(encoding="utf-8").strip()
            draft2 = pp.strip_grounding(other.read_text(encoding="utf-8")).strip()
            fired += [(book.name, path.stem, index) for index, _ in
                      pp.chart_candidates(blocks, pp.load_regions(path), draft, draft2)]
    assert fired == [("faatzing", "page-0006", 3)], fired
    print(f"corpus: the trigger fires on one of {tables} non-prose blocks, the brace chart")


def check_corpus_cut_and_checks(blocks: list, draft: str, draft2: str) -> None:
    golden = GOLDEN_TREE.read_text(encoding="utf-8")
    parsed = pp.parse_chart(golden)
    assert (parsed["form"], len(parsed["edges"]), len(parsed["notes"])) == ("list", 27, 12), parsed["form"]
    cut = pp.cut_chart(blocks, 3, draft2, parsed["markdown"])
    assert (cut["score"], cut["engineBLineRange"]) == (211, [4, 22]), (cut["score"], cut["engineBLineRange"])
    # The upper leaf engine A read as other blocks is not the chart's; no prose
    # cell runs on into the cut.
    assert cut["engineBOutside"] == {"otherBlocks": 475, "regionProse": 0}, cut["engineBOutside"]
    assert [len(pp.CJK(c)) for c in cut["salvagedCells"]] == [88], cut["salvagedCells"]
    assert pp.CJK(cut["salvagedCells"][0]).startswith("右圖所列") and cut["cellsLeftOut"] == 23
    rest = cut["draft"]
    checked = pp.chart_checks(parsed, blocks[3]["text"], "\n".join(cut["engineBLines"]), draft, draft2, rest)
    assert (checked["unwitnessed"], checked["unwitnessedNodes"], checked["lost"]) == ("天", ["天文學"], ""), checked
    variant = pp.chart_checks(pp.parse_chart(golden.replace("敎", "教")), blocks[3]["text"],
                              "\n".join(cut["engineBLines"]), draft, draft2, rest)
    assert [(m["written"], m["printed"]) for m in variant["mappedVariants"]] == [("教", "敎")], variant
    # A node left out is seen when engine A read its characters there and
    # nowhere else: 道 of 道德學; 天文學, which neither engine read whole, is not.
    for node, lost in (("道德學", "道"), ("天文學", "")):
        dropped = pp.parse_chart(golden.replace(f"      - {node}\n", ""))
        dropped_cut = pp.cut_chart(blocks, 3, draft2, dropped["markdown"])
        checked = pp.chart_checks(dropped, blocks[3]["text"], "\n".join(dropped_cut["engineBLines"]),
                                  draft, draft2, dropped_cut["draft"])
        assert checked["lost"] == lost, (node, checked["lost"])
    looped = pp.parse_chart("- 科學\n" + "  - 物理學\n    - 狹義心理學術生學\n" * 30)
    loop_cut = pp.cut_chart(blocks, 3, draft2, looped["markdown"])
    refused = pp.chart_refusal(pp.chart_checks(looped, blocks[3]["text"], "\n".join(loop_cut["engineBLines"]),
                                               draft, draft2, loop_cut["draft"]), False)
    assert refused and "repeats itself" in refused, refused
    segments = pp.align_drafts(cut["draft"], cut["draft2"])
    agreed = sum(len(x["a"]) for x in segments if x["tag"] == "equal")
    agreement = agreed / max(len(pp.CJK(cut["draft"])), len(pp.CJK(cut["draft2"])))
    assert agreement > pp.READING_ORDER_AGREEMENT and round(agreement, 3) == 0.949, agreement
    pieces = [x["a"] if x["tag"] == "equal" else (x["a"] or x["b"]) for x in segments]
    spans = pp.block_spans(cut["blocks"], segments, pieces, cut["draft"])
    assert spans is not None and pp.CJK(spans[-1]).startswith("右圖所列"), spans
    assert cut["blocks"][-1]["label"] == "chart-region", cut["blocks"][-1]["label"]
    print("corpus p.6: cut to engine B's 19 chart lines, the prose cell kept, merged at 0.949; checks as measured")


def check_corpus_fold(blocks: list, draft2: str) -> None:
    """The measured page: the book's fold from its layout, cut out of the
    chart's crop, and the region's prose given its own box, so a character
    of it is cropped as a column (it was a strip 7 px wide)."""
    found = pp.fold_band(sorted((BOOK / "ocr-paddle").glob("page-*.json")))
    assert found == {"band": [0.4804, 0.5208], "labelWidth": 0.0231, "labels": 89, "pages": 66}, found
    render = BOOK / "renders" / "page-0006.png"
    crop, cut = pp.fold_cut(render, blocks[3]["box"], found)
    assert crop and cut["cut"] == [0.4875, 0.5172] and cut["pixels"] == 76, cut
    # The page scanned 7 px further right: the chart's text column left of the
    # fold (px 1206-1235 here) then has its centre in the band, and cutting
    # every column centred there took it out with the fold (114 px); the
    # fold's rules keep the cut to the strip.
    from PIL import Image
    with tempfile.TemporaryDirectory() as tmp, Image.open(render) as image:
        shifted = Image.new(image.mode, image.size, 255)
        shifted.paste(image.crop((0, 0, image.width - 7, image.height)), (7, 0))
        shifted.save(Path(tmp) / "shifted.png")
        crop, cut = pp.fold_cut(Path(tmp) / "shifted.png", blocks[3]["box"], found)
    assert crop and cut["cut"] == [0.4902, 0.52] and cut["pixels"] == 76, cut
    box = pp.prose_box(render, blocks[3]["box"])
    assert box is not None and 0.169 <= box[0] <= 0.171 and 0.244 <= box[0] + box[2] <= 0.246, box
    cell = pp.cut_chart(blocks, 3, draft2, pp.parse_chart(GOLDEN_TREE.read_text(encoding="utf-8"))["markdown"]
                        )["salvagedCells"][0]
    text = pp.CJK(cell)
    from PIL import Image
    # Cut from the whole region the crop is one of the chart's columns, 45 px
    # wide, not the prose's: it was a strip 7 px wide (28 x 5064 enlarged) until
    # crop_glyph dropped ink columns narrower than the text (text_columns).
    for where, size in ((blocks[3]["box"], (180, 5064)), (box, None)):
        glyph = pp.crop_glyph(render, {"text": text, "box": where}, text.index("而已") + 1, 1)
        with Image.open(io.BytesIO(glyph)) as image:
            if size:
                assert image.size == size, image.size
            else:
                assert image.width >= 200 and image.height < 3000, image.size
    print("corpus p.6: the fold from the book's layout, cut out of the chart's crop; the prose cropped as a column")


def check_corpus_page() -> None:
    """The whole page, with the person's reading of the chart as the answer:
    scored against the case's goldens."""
    golden = GOLDEN_TREE.read_text(encoding="utf-8")
    case = json.loads((rr.CASES / "faatzing.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out"
        for answer, want in ((golden, "pass"), (golden.replace("      - 文學（敎育學歷史學美術學等皆屬焉）\n", "")
                                                + "      - 文學（敎育學歷史學美術學等皆屬焉）\n", "pass")):
            shutil.rmtree(out, ignore_errors=True)
            model = stand_in.StandIn(census=0, chart=answer)
            real = pp.Client
            pp.Client = lambda *args, **kwargs: model
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    status = pp.main([str(BOOK / "renders"), str(BOOK / "ocr-paddle"), str(out),
                                      "--draft2-directory", str(BOOK / "ocr-hunyuan"),
                                      "--profile", str(BOOK / "book-profile.json"), "--pages", "6",
                                      "--report", str(Path(tmp) / "report.json")])
            finally:
                pp.Client = real
            assert status == 0, status
            record = json.loads((out / "page-0006.json").read_text(encoding="utf-8"))
            assert record["mode"] == "merge" and record["charts"][0]["unwitnessed"] == "天", record["mode"]
            assert "extra-copy" not in kinds(record) and "punctuation-whole-page" not in kinds(record), kinds(record)
            results = {a["id"]: rr.check(a, out) for a in case["assertions"]}
            assert results["tree-6-h2"][0] == want, results["tree-6-h2"][1]
            page_metrics = results["golden-6-h1"][2]
            assert page_metrics["skippedLines"] >= 27, page_metrics["skippedLines"]
    print("corpus p.6: the page merges, the chart passes golden_tree (either parent of 文學, D10), "
          "and golden_page skips its lines")


if __name__ == "__main__":
    check_parse()
    check_candidates()
    check_cut()
    check_repeated_cells()
    check_checks()
    check_position()
    check_page()
    check_uncertain_and_variants()
    check_old_path()
    check_region()
    check_precedence()
    check_placement_fallbacks()
    check_order_conflict_window_before_chart()
    check_order_test()
    check_chart_only()
    check_after_table()
    check_two_charts()
    check_fold_and_prose_box()
    check_fold_page()
    found = corpus_page()
    if found is None:
        print("corpus not on this machine: the measured page's checks skipped")
    else:
        check_corpus_trigger()
        check_corpus_cut_and_checks(*found)
        check_corpus_fold(found[0], found[2])
        check_corpus_page()
    print("all chart checks passed")
