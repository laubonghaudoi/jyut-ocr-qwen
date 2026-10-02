#!/usr/bin/env python3
"""Offline check of the book repair tool's book model (scripts/_repair_model.py):
each entry learned from a made-up book (tests/repair_fixture.py), and each
gate failing where the book does not show what it measures.

No model, no GPU, no corpus.  The made-up book prints a running head in the
outer column (right on odd scans, left on even), a run suffix under it and
the folio at its foot; contents on scans 2-3; two runs, each opened by a
divider that prints the suffix in display type; the second run skips two
leaves; paragraphs indented two cells, headings three.

- M-1/M-2/M-2b: the band per parity from the folio blocks; the stem from the
  profile, or - with no profile head - the band's shared core; a misread
  head block still matches the stem, and its misread is learned.  On
  contents pages of short blocks, a line in the parity's folio strip on a
  scan whose own head lies further out, and lines under a number block
  spanning several columns, are not the band's.  Nor are a line of the body
  that reads like the head (phase 3's furniture_band takes it by its text),
  a numeral block at the far side of the page, or the stem set in display
  type (with what lies in its column).
- M-3/M-4: the suffix runs; the folio offset per run, a jump where leaves
  are missing (and the folios it skips); a folio engine A misread as
  Arabic figures on one page does not move the fit.
- M-5: the dividers are the pages printing the suffix in display type; a
  page of the run holding the suffix as an ordinary body block is not one.
- M-6: the contents pages, their lines mapped in order onto the titles, and
  the contents word; a list page that maps nothing is not contents.
- M-7: engine B's mark aliases, and a glyph it writes for engine A's
  bracketed figure on four pages is a figure stand-in, while a character
  engine A skipped once is not, and neither is a CJK numeral engine B reads
  for engine A's figure on four pages.
- M-8: a band column that no block marks (engine A read the band into a body
  block) and that sits off the parity's folio strip is set aside by the rows
  the band fills on the other pages of its parity; a stamp printed below the
  text's foot is not the frame's foot; thin rules across a page, more of
  them than columns, are no columns.
- M-8/M-8b: 40 cells a column, the frame, the paragraph indent at 2 cells;
  a book that indents no paragraph fails M-8b, and so does one that opens
  its paragraphs flush but lowers a few quotations; with a one-cell indent
  no column top is both flush and indented.
- Failing gates: no folio blocks (M-1), no notation (M-10), no running head
  anywhere (M-2).

Usage:
    python3 tests/check_repair_model.py
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import offline  # noqa: E402,F401
import repair_fixture as fx  # noqa: E402

sys.path.insert(0, str(HERE.parent / "scripts"))
import _repair_inputs as ri  # noqa: E402
import _repair_model as rm  # noqa: E402


FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    print(f"{'ok  ' if condition else 'FAIL'} {message}")
    if not condition:
        FAILURES.append(message)


def pp_cjk(text: str) -> str:
    return fx.pp.CJK(text)


def learn(root: Path, spec, **kwargs) -> dict:
    fx.write_book(root, spec, **kwargs)
    return rm.learn(ri.load_book(ri.InputPaths.resolve(root, {})))


def figure_standins(spec) -> None:
    """Engine A reads （1） after a paragraph's third character on four
    pages, where engine B reads 丁 between two bracket strokes; on four
    other pages engine A reads （5） where engine B reads the numeral 五 (the
    figure in the other script); on one page engine B reads a character 竹
    that engine A skipped."""
    for scans, figure, glyph in (((6, 8, 10, 14), "1", "丁"), ((7, 12, 17, 19), "5", "五")):
        for scan in scans:
            columns = fx.layout(spec[scan])["columns"]
            k = next(i for i, c in enumerate(columns) if c["label"] == "vertical_text")
            text = columns[k]["text"]
            cut = sum(1 for _ in text[:3])
            spec[scan]["aMarks"] = {k: text[:cut] + f"（{figure}）" + text[cut:]}
            spec[scan]["bEdits"] = [(text[:cut].replace("，", "丶").replace("。", "口"),
                                     text[:cut].replace("，", "丶").replace("。", "口") + f"一{glyph}一")]
    columns = fx.layout(spec[11])["columns"]
    k = next(i for i, c in enumerate(columns) if c["label"] == "vertical_text")
    text = columns[k]["text"][:4].replace("，", "丶").replace("。", "口")
    spec[11]["bEdits"] = [(text, text + "竹")]


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        spec = fx.make_spec()
        spec[9]["aFolio"] = "11"                       # engine A reads 五 as Arabic figures
        spec[16]["aHeadless"] = True                   # engine A misses the head here
        spec[8]["items"].append(("line", "甲編"))       # the suffix as an ordinary body line
        figure_standins(spec)
        model = learn(tmp / "book", spec)
        gates = model["gates"]
        check(all(gates[g]["passed"] for g in ("M-1", "M-2", "M-3", "M-4", "M-6", "M-8", "M-8b", "M-10")),
              f"every gate passes on the made-up book: {[g for g, v in gates.items() if not v['passed']]} failed")
        parities = model["band"]["parities"]
        check(parities["odd"]["side"] == "right" and parities["even"]["side"] == "left",
              "M-1: the band is the right column on odd scans, the left on even")
        band7 = [b["text"] for b in model["pages"]["7"]["band"]]
        check(band7 == [fx.HEAD, "甲編", "三"], f"M-1: a page's band holds its head, suffix and folio (got {band7})")
        check(model["stems"] == [fx.HEAD] and model["stemMethod"] == "profile", "M-2: the stem is the profile's head")
        runs = [(r["suffix"], r["first"], r["last"]) for r in model["suffixRuns"]]
        check(runs == [(fx.CONTENTS_WORD, 2, 4), ("甲編", 5, 12), ("乙編", 13, 20)], f"M-3: the suffix runs ({runs})")
        offsets = [[s["offset"] for s in r["stretches"]] for r in model["folio"]["runs"]]
        check(offsets == [[1], [4], [12, 10]], f"M-4: the folio offsets per run, with the jump ({offsets})")
        jumps = model["folio"]["jumps"]
        check(len(jumps) == 1 and jumps[0]["kind"] == "leaves-missing" and
              (jumps[0]["missingFrom"], jumps[0]["missingTo"]) == (5, 6) and jumps[0]["before"] == 17,
              f"M-4: the jump skips folios 5-6 before scan 17 ({jumps})")
        check(model["pages"]["9"]["folio"] == 5 and model["pages"]["18"]["folio"] == 8,
              "M-4: a page's expected folio, also where engine A misread it and after the jump")
        check(model["pages"]["16"]["suffix"] == "乙編" and model["pages"]["16"]["folio"] == 4,
              "a page whose head engine A missed keeps its run and folio (engine B read them)")
        check([d["page"] for d in model["dividers"]] == [5, 13],
              f"M-5: the dividers are the display-type pages; the body line on scan 8 is not one "
              f"({model['dividers']})")
        check(model["contentsPages"] == [2, 3], f"M-6: the contents pages ({model['contentsPages']})")
        entries = [e for r in model["contents"]["runs"] for e in r["entries"] if e.get("matchedPage")]
        check([(e["text"], e["matchedPage"]) for e in entries][:2] == [("春日遊記", 5), ("秋夜讀書", 7)]
              and len(entries) == 7 and model["contents"]["runs"][0]["contentsWord"] == fx.CONTENTS_WORD,
              "M-6: every contents entry maps, in order, onto its title; the contents word is the run's suffix")
        standins = model["standIns"]
        check({"丶", "口"} <= set(standins["markAliases"]["B"]),
              f"M-7a: engine B's mark aliases, as phase 3 measures them ({standins['markAliases']})")
        check("丁" in standins["figure"] and "竹" not in rm.standin_glyphs(model),
              f"M-7b: 丁 is a figure stand-in, 竹 (a character engine A skipped) is not ({standins['figure']})")
        check("五" not in standins["figure"] and "五" in standins["numeralsAtFigures"],
              f"M-7b: the numeral 五 engine B reads where engine A read （5） is the figure in the other script, "
              f"not a stand-in ({standins['figure']}, {standins.get('numeralsAtFigures')})")
        geometry = model["geometry"]
        check(geometry["cellsPerColumn"] == 40 and geometry["indent"]["k"] == 2 and geometry["indent"]["between"] == 0,
              f"M-8/M-8b: 40 cells a column, paragraphs at 2 cells ({geometry['cellsPerColumn']}, {geometry['indent']})")
        columns = model["pages"]["6"]["geometry"]["columns"]
        tops = [round(c["topCells"]) for c in columns]
        check(tops[0] == 0 and tops.count(2) == 2 and all(t in (0, 2) for t in tops),
              f"M-8: scan 6 opens flush (a paragraph running on) and starts two paragraphs ({tops})")
        check(abs(model["glyph"] - fx.PITCH) <= 2, f"M-9: the body glyph is the cell ({model['glyph']})")
        check("。" in model["sentenceFinal"], "M-10: the sentence-final marks the book prints")

        # Scan 12 prints its band a column inward from the other even scans,
        # and engine A read none of it as a block of its own (it read the
        # band into a body block): no block marks it and the parity's folio
        # strip misses it.  Its column fills the rows the band fills on the
        # other pages, so it is the band's, not the page's last text column.
        spec = fx.make_spec()
        spec[12].update(bandX=110, aHeadless=True, aNoFolio=True)
        model = learn(tmp / "band-by-rows", spec)
        columns = model["pages"]["12"]["geometry"]["columns"]
        check(model["geometry"]["bandByRows"] == [12] and min(c["x0"] for c in columns) > 130
              and model["geometry"]["bandRows"].get("even"),
              f"M-8: a band column no block marks, off the parity's folio strip, is set aside by the rows the band "
              f"fills ({model['geometry']['bandByRows']}, leftmost column at {min(c['x0'] for c in columns)})")
        # Its look-alike: scan 12 printed with no band, its last column a short
        # paragraph that starts at the band's top row and ends above the
        # folio's rows - a text column, not the band's.
        spec = fx.make_spec()
        spec[12].update(suffix=None, folio=None)
        spec[12]["items"].append(("para", fx.paragraph(1203, 10), False))
        model = learn(tmp / "band-rows-text", spec)
        check(12 not in model["geometry"]["bandByRows"],
              f"M-8: a short text column at the band's side that ends above the folio's rows is no band "
              f"({model['geometry']['bandByRows']})")

        # A stamp printed over scan 6's text column and below the frame's
        # foot: the frame's foot stays at the text's, so a full column is
        # full.  Scan 8 crossed by thin rules between and beside its
        # columns, more of them than columns: no rule is a column.
        spec = fx.make_spec()
        spec[6]["stamp"] = (fx.FIRST_COLUMN_X - 3 * fx.COLUMN_STEP - 12, 700, 24, 300)
        spec[8]["rules"] = [(fx.FIRST_COLUMN_X - fx.COLUMN_STEP // 2 - n * fx.COLUMN_STEP + d, 400, 700, 3)
                            for n in range(10) for d in (-8, 0, 8)]
        model = learn(tmp / "stamp-rules", spec)
        foot = model["pages"]["6"]["geometry"]["frameFoot"]
        drawn_foot = fx.FRAME_TOP + fx.CELLS * fx.PITCH
        check(abs(foot - drawn_foot) < fx.PITCH / 2,
              f"M-8: a stamp below the text's foot is not the frame's foot ({foot}, the text's {drawn_foot})")
        columns8 = model["pages"]["8"]["geometry"]["columns"]
        drawn = len(fx.layout(spec[8])["columns"])
        check(len(columns8) == drawn and min(c["x1"] - c["x0"] for c in columns8) > 8,
              f"M-8: thin rules across a page are no columns ({len(columns8)} columns for {drawn} drawn)")

        model = learn(tmp / "no-head-profile", fx.make_spec(), profile={"notation": {"marks": ["。"]}})
        check(model["stems"] == [fx.HEAD] and model["stemMethod"] == "band core",
              f"M-2: with no head in the profile the stem is the band's shared core ({model['stems']})")

        spec = fx.make_spec()
        for page in spec.values():
            page["folio"] = None
        model = learn(tmp / "no-folio", spec, profile={"layout": {"runningHeads": [fx.HEAD]}})
        check(not model["gates"]["M-1"]["passed"] and not model["gates"]["M-10"]["passed"],
              "M-1 fails with no folio blocks; M-10 fails with no notation")
        spec = fx.make_spec()
        for page in spec.values():
            page["suffix"] = None
            page["folio"] = None
        model = learn(tmp / "no-head", spec, profile={"notation": {"marks": ["。"]}})
        check(not model["gates"]["M-2"]["passed"] and not model["gates"]["M-3"]["passed"],
              "M-2 and M-3 fail on a book that prints no running head")
        spec = fx.make_spec()
        for page in spec.values():
            page["items"] = [(i[0], i[1], True) if i[0] == "para" else i for i in page["items"]]
        model = learn(tmp / "flat", spec)
        check(model["gates"]["M-8"]["passed"] and not model["gates"]["M-8b"]["passed"],
              "M-8b fails on a book that indents no paragraph (its headings set lower are no indent)")
        # The same book with five quotations lowered two cells: a cluster of
        # full columns at 2 cells, but its paragraphs still open flush.
        for scan in (6, 8, 10, 14, 16):
            items = spec[scan]["items"]
            second = [n for n, item in enumerate(items) if item[0] == "para"][1]
            items[second] = ("para", items[second][1], False)
        model = learn(tmp / "flat-quotes", spec)
        opened = model["gates"]["M-8b"].get("paragraphsOpen")
        check(model["geometry"]["indent"]["fullAtK"] >= 3 and not model["gates"]["M-8b"]["passed"],
              f"M-8b fails on a book whose paragraphs open flush, though it lowers a few quotations two cells "
              f"({opened})")
        check(rm.indent_class(0.42, 1) == "between" and rm.indent_class(0.2, 1) == "flush"
              and rm.indent_class(1.1, 1) == "paragraph" and rm.indent_class(1.2, 2) == "between"
              and rm.indent_class(3.0, 2) == "above",
              "M-8b: with a one-cell indent a top that is under the flush limit and near the indent is `between`, "
              "never flush and a paragraph's at once")

        # Contents pages of short blocks only.  Scan 3 sits a column off the
        # other odd scans: its head lies further out and its first contents
        # line in the odd scans' folio strip, and engine A read no folio on
        # it.  On scan 2 engine A read the figures printed at the foot of
        # four contents columns as one number block.
        shifted = fx.make_spec()
        shifted[3].update(bandX=770, firstX=718, aNoFolio=True)
        shifted[2]["aFolioBox"] = (300, 1000, 160, 16)
        shifted[2]["aFolio"] = "1234"
        model = learn(tmp / "shifted-contents", shifted)
        band2 = [b["text"] for b in model["pages"]["2"]["band"]]
        band3 = [b["text"] for b in model["pages"]["3"]["band"]]
        check(band3 == [fx.HEAD, fx.CONTENTS_WORD],
              f"M-1: a contents line in the parity's folio strip, on a scan whose own head lies further out, "
              f"is not the band's ({band3})")
        check(all(pp_cjk(t) in (fx.HEAD, fx.CONTENTS_WORD, "") for t in band2),
              f"M-1: a number block spanning four columns marks no column: the contents lines under it are "
              f"not the band's ({band2})")
        runs = [(r["suffix"], r["first"], r["last"]) for r in model["suffixRuns"]]
        check(runs[:1] == [(fx.CONTENTS_WORD, 2, 4)],
              f"M-3: the contents word's run keeps its pages when contents lines stay out of the band ({runs})")

        short = rm.stem_matches("我們研究文學的方法又說文學", "文學史")
        long_ = rm.stem_matches("甲丙丁戊己庚說", "甲乙丙丁戊己庚")
        check(short == [] and long_ == [(0, 6)],
              f"M-2: a three-character stem's copy needs all three characters (a body word it begins with is "
              f"none), while a seven-character stem read with one character dropped still matches "
              f"({short}, {long_})")

        values = {text: rm.numeral_value(text) for text in ("一百零三", "一〇三", "二十五", "十", "一千零五十", "三三")}
        check(values == {"一百零三": 103, "一〇三": 103, "二十五": 25, "十": 10, "一千零五十": 1050, "三三": 33},
              f"M-4: a folio's value, a zero holding an empty place too ({values})")

        # A line of the body that reads like the head (phase 3's
        # furniture_band takes it by its text), and a numeral block labelled
        # number at the far side of the page: neither is where this book
        # prints its running head or its folio.
        placed = fx.make_spec()
        placed[10]["items"].insert(1, ("line", fx.HEAD))
        placed[9]["extraBlocks"] = [{"text": "五", "boundingBox": fx.box_of(60, 120, 16, 16), "blockLabel": "number"}]
        model = learn(tmp / "placed", placed)
        band10 = [b["text"] for b in model["pages"]["10"]["band"]]
        band9 = [b["text"] for b in model["pages"]["9"]["band"]]
        check(band10.count(fx.HEAD) == 1 and band9.count("五") == 1 and "五" == fx.numeral(5),
              f"M-1: a body line that reads like the head, and a numeral block at the far side of the page, are "
              f"not the band's; the page's own head and folio are ({band10}, {band9})")

        # Display type: a block holding the stem at twice the glyph of the
        # stem's other copies (a title page that prints the book's title,
        # which is its running head) leaves the band, with a block taken for
        # lying in its column.
        bands = {scan: [{"block": 0, "text": fx.HEAD, "label": "header", "box": [0.9, 0.1, 0.02, 0.1],
                         "why": "furniture_band: running head"}] for scan in (2, 3, 4, 5)}
        bands[6] = [{"block": 0, "text": fx.HEAD, "label": "paragraph_title", "box": [0.5, 0.2, 0.04, 0.2],
                     "why": "furniture_band: head's size, furniture text"},
                    {"block": 1, "text": "甲", "label": "text", "box": [0.5, 0.45, 0.04, 0.05],
                     "why": "furniture_band: column of block 0"}]
        removed = rm.drop_display_heads(bands, [fx.HEAD], {scan: (1000, 1000) for scan in bands})
        check([(r["page"], r["block"], r["alsoRemoved"]) for r in removed] == [(6, 0, [1])] and not bands[6]
              and all(len(bands[scan]) == 1 for scan in (2, 3, 4, 5)),
              f"M-1: a stem in display type leaves the band with the block in its column; the running heads "
              f"stay ({removed})")

        misread_book = fx.make_spec()
        misread_book[9]["headRead"] = fx.HEAD[0] + "丈" + fx.HEAD[2:]
        model = learn(tmp / "misread-head", misread_book)
        check(model["stemMisreads"].get(fx.HEAD[1]) == {"丈": 1} and
              any(b["text"] == misread_book[9]["headRead"] for b in model["pages"]["9"]["band"]),
              f"M-2b: a head block read with one character wrong is the band's, and the misread is learned "
              f"({model['stemMisreads']})")
    print(f"{'FAIL' if FAILURES else 'ok  '} check_repair_model: {len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
