#!/usr/bin/env python3
"""Checks for the 裁決 crop of a disputed spot in a vertical block (crop_glyph): it reaches
as far above the spot as below it, and it shows the whole of the longer reading - past a
column's foot into the next column, and back from the block's end; --no-whole-run-crop
keeps the geometry before (whole_run False, set_crop_geometry).  The crop is cut from the
columns of text (text_columns), not from a rule or a sideline beside them; the column groups
a block's punctuation passes are cut in and the edges a boundary crop shows (column_layout)
take every ink column, as before that cut, unless --text-column-layout.

No model, no GPU, no corpus: a drawn page of three columns of ten glyphs each, some
drawn in red, and the crop is searched for the red ones.  The shapes are the ones
measured on a lecture page: the spot's crop started one character below the disputed
者 (the estimate drifts down as well as up), and the crop of 26 characters engine B read
where engine A read the block's last four showed only the last seven of them.

Usage: python3 tests/check_crops.py   (exits non-zero on the first failure)
"""
from __future__ import annotations

import io
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import proofread_pages as pp  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

failures = 0


def check(name: str, got, want) -> None:
    global failures
    if got != want:
        failures += 1
        print(f"FAIL {name}: got {got!r}, want {want!r}")
    else:
        print(f"ok   {name}")


TEXT = "天地玄黃宇宙洪荒日月盈昃辰宿列張寒來暑往秋收冬藏閏餘成歲律呂"   # 30: three columns of ten
COLUMNS = (700, 600, 500)          # right to left
PITCH, TOP = 50, 140
BLOCK = {"text": TEXT, "box": [480 / 1000, 120 / 1400, 280 / 1000, 560 / 1400], "label": "text"}


def page(red: set[int], characters: int = len(TEXT)) -> Path:
    """The drawn page: character k of TEXT at column k // 10, row k % 10, red when in RED;
    the first CHARACTERS of them."""
    image = Image.new("RGB", (1000, 1400), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    for k in range(characters):
        x, top = COLUMNS[k // 10], TOP + (k % 10) * PITCH
        fill = (255, 0, 0) if k in red else (0, 0, 0)
        for bar in (0, 18, 36):
            draw.rectangle((x, top + bar, x + 40, top + bar + 3), fill=fill)
        draw.rectangle((x + 18, top, x + 21, top + 39), fill=fill)
    path = Path(tempfile.mkdtemp()) / "page.png"
    image.save(path)
    return path


def shown_one(index: int, run: int, k: int, whole_run: bool | None = None) -> bool:
    """Whether the crop at INDEX for RUN characters shows character K, drawn red (red is
    never a scaled grey)."""
    png = pp.crop_glyph(page({k}), BLOCK, index, run, whole_run=whole_run)
    crop = Image.open(io.BytesIO(png)).convert("RGB")
    r, g, _ = (band.tobytes() for band in crop.split())
    # Most of the glyph, not a sliver at the crop's edge.
    return sum(1 for x, y in zip(r, g) if x - y > 100) > 0.5 * red_pixels()


_RED = {}


def red_pixels() -> int:
    """The red pixels of one whole glyph, as the crop scales it (measured on a crop
    that shows it whole)."""
    if "n" not in _RED:
        png = pp.crop_glyph(page({5}), BLOCK, 5, 1)
        crop = Image.open(io.BytesIO(png)).convert("RGB")
        r, g, _ = (band.tobytes() for band in crop.split())
        _RED["n"] = sum(1 for x, y in zip(r, g) if x - y > 100)
    return _RED["n"]


def shown_in(png: bytes | None) -> bool:
    """Whether the crop PNG shows most of one red glyph."""
    if not png:
        return False
    with Image.open(io.BytesIO(png)) as opened:
        crop = opened.convert("RGB")
    r, g, _ = (band.tobytes() for band in crop.split())
    return sum(1 for x, y in zip(r, g) if x - y > 100) > 0.5 * red_pixels()


check("the drawn block's columns are measured", len(pp.measure_columns(page(set()), BLOCK["box"]) or []), 3)
# As far above as below: eight characters either way of a one-character spot.
check("reach above: the character eight above the spot is shown, nine above is not",
      [shown_one(9, 1, k) for k in (1, 0)], [True, False])
check("reach below: eight below is shown, nine below is not", [shown_one(0, 1, k) for k in (8, 9)], [True, False])
check("a one-character spot stays in its column", shown_one(5, 1, 15), False)
# A run past its column's foot goes on at the head of the next column.
check("a run past the column's foot: the next column's head is shown", shown_one(8, 4, 11), True)
# A run past the block's end was read before the spot: the crop goes back to show it.
check("a run past the block's end: the whole run is shown",
      [shown_one(27, 12, k) for k in (18, 20, 29)], [True, True, True])
check("... and not more than the run and its reach", shown_one(27, 12, 5), False)

# --no-whole-run-crop: the geometry before, for measuring it - the spot's own column, four
# above and eight below the run, clamped at the column's foot.
check("before: four above the spot, not five", [shown_one(9, 1, k, whole_run=False) for k in (5, 4)], [True, False])
check("before: a run past the column's foot stays in its column",
      [shown_one(8, 4, k, whole_run=False) for k in (9, 11)], [True, False])
check("before: a run past the block's end is not moved back", shown_one(27, 12, 18, whole_run=False), False)
pp.set_crop_geometry(whole_run=False)
check("the run's setting is the default (set_crop_geometry)", shown_one(8, 4, 11), False)
pp.set_crop_geometry()
check("... and back", shown_one(8, 4, 11), True)


# Only crop_glyph takes the columns of text (text_columns).  The layout the census and
# punctuate calls are cut by (block_tiles, column_reach) and the edges a boundary crop
# shows (edge_region) take every ink column, as before the text-column cut, unless
# --text-column-layout.  The shape is the block whose columns the cut changed on a
# magazine page where a real run regressed (a price block: two columns of text, and
# five thin runs of ink beside them, 13-38 px against 183-200 px of text, seven ink
# columns in all): here two columns of ten glyphs, solid rules 3, 5 and 8 px wide left
# of the first and 3 and 5 px wide left of the second.
PRICED_TEXT = TEXT[:20]
PRICED_BLOCK = {"text": PRICED_TEXT, "box": [560 / 1000, 120 / 1400, 200 / 1000, 560 / 1400], "label": "text"}
PRICED_RULES = ((690, 3), (682, 5), (670, 8), (590, 3), (582, 5))


def priced_page(red: set[int]) -> Path:
    path = page(red, characters=len(PRICED_TEXT))
    with Image.open(path) as opened:
        image = opened.convert("RGB")
    draw = ImageDraw.Draw(image)
    for x, width in PRICED_RULES:
        draw.rectangle((x, TOP, x + width - 1, TOP + 10 * PITCH - 11), fill=(0, 0, 0))
    image.save(path)
    return path


def tile_ranges(render: Path, block: dict, limit: int = 10) -> list[tuple[int, int]] | None:
    """block_tiles' text ranges for BLOCK cut in groups of LIMIT characters at most."""
    tiles = pp.block_tiles(render, block, len(pp.CJK(str(block["text"]))), limit=limit)
    return [(start, end) for _, start, end in tiles] if tiles else None


priced = priced_page(set())
EVERY_INK_COLUMN = [(700, 741), (690, 693), (682, 687), (670, 678), (600, 641), (590, 593), (582, 587)]
check("a priced block: measure_columns is every ink column, the rules too",
      [(x0, x1) for x0, x1, _, _ in pp.measure_columns(priced, PRICED_BLOCK["box"]) or []], EVERY_INK_COLUMN)
check("... and with TEXT_ONLY its two columns of text",
      [(x0, x1) for x0, x1, _, _ in pp.measure_columns(priced, PRICED_BLOCK["box"], text_only=True) or []],
      [(700, 741), (600, 641)])
check("a priced block: the layout is every ink column, three characters each, as before the cut",
      [(x0, x1, count) for x0, x1, _, _, count in pp.column_layout(priced, PRICED_BLOCK) or []],
      [(x0, x1, 3) for x0, x1 in EVERY_INK_COLUMN])
check("a priced block: its column groups and a column's reach, as before the cut",
      (tile_ranges(priced, PRICED_BLOCK), pp.column_reach(priced, PRICED_BLOCK, 20)),
      ([(0, 9), (9, 18), (18, 20)], 3))
check("a priced block: the edges a boundary crop shows, as before the cut",
      [pp.edge_region(priced, PRICED_BLOCK, end, 1, (1000, 1400)) for end in (False, True)],
      [(687, 140, 753, 630), (580, 140, 588, 1400)])
check("a priced block: the crop of a spot is its column of text, not a rule",
      [shown_in(pp.crop_glyph(priced_page({k}), PRICED_BLOCK, k, 1)) for k in (5, 12)], [True, True])


# Thin runs of ink beside each column - a dashed rule, a sideline, specks of the scan -
# hold no text, even where they outnumber the columns and are the median ink run (the
# shape measured on a book page, measure_columns): here two dashed rules 2 px wide to the
# right of each of the three columns.
def ruled_page(red: set[int]) -> Path:
    path = page(red)
    with Image.open(path) as opened:
        image = opened.convert("RGB")
    draw = ImageDraw.Draw(image)
    for x in COLUMNS:
        for rule in (x + 47, x + 53):
            for top in range(TOP, TOP + 10 * PITCH, 10):
                draw.rectangle((rule, top, rule + 1, top + 5), fill=(0, 0, 0))
    image.save(path)
    return path


ruled = pp.measure_columns(ruled_page(set()), BLOCK["box"], text_only=True) or []
check("a ruled block: its three columns of text are measured, not the rules beside them",
      [(x0 - 480, x1 - 480) for x0, x1, _, _ in ruled], [(220, 261), (120, 161), (20, 61)])
png = pp.crop_glyph(ruled_page({12}), BLOCK, 12, 1)
with Image.open(io.BytesIO(png)) as crop:
    shown = crop.convert("RGB")
r, g, _ = (band.tobytes() for band in shown.split())
check("a ruled block: the crop of a spot is its column, not a rule beside it",
      (shown.width >= 41, sum(1 for x, y in zip(r, g) if x - y > 100) > 0.5 * red_pixels()), (True, True))


# The same ruled block where the paragraph ends two characters into a fourth column.  Its
# ink, averaged over the whole block's height, is thin: only the glyphs' middle stroke
# passes, 4 px of their 41, as thin as the rules.  Measured on its own rows it is as wide
# as the text, and it is a column of text: the crop of a spot in it shows that column,
# not the foot of the column before.
SHORT_TEXT = TEXT + "調陽"
SHORT_BLOCK = {"text": SHORT_TEXT, "box": [380 / 1000, 120 / 1400, 380 / 1000, 560 / 1400], "label": "text"}


def short_page(red: set[int]) -> Path:
    path = ruled_page(red - {30, 31})
    with Image.open(path) as opened:
        image = opened.convert("RGB")
    draw = ImageDraw.Draw(image)
    for k in (30, 31):
        top = TOP + (k - 30) * PITCH
        fill = (255, 0, 0) if k in red else (0, 0, 0)
        for bar in (0, 18, 36):
            draw.rectangle((400, top + bar, 440, top + bar + 3), fill=fill)
        draw.rectangle((418, top, 421, top + 39), fill=fill)
    for rule in (447, 453):
        for top in range(TOP, TOP + 10 * PITCH, 10):
            draw.rectangle((rule, top, rule + 1, top + 5), fill=(0, 0, 0))
    image.save(path)
    return path


short = pp.measure_columns(short_page(set()), SHORT_BLOCK["box"], text_only=True) or []
check("a short last column: measured as a column of text, as wide as the others",
      [(x0 - 380, x1 - 380) for x0, x1, _, _ in short], [(320, 361), (220, 261), (120, 161), (20, 61)])
png = pp.crop_glyph(short_page({31}), SHORT_BLOCK, 31, 1)
with Image.open(io.BytesIO(png)) as crop:
    shown = crop.convert("RGB")
r, g, _ = (band.tobytes() for band in shown.split())
check("a short last column: the crop of a spot in it shows it",
      sum(1 for x, y in zip(r, g) if x - y > 100) > 0.5 * red_pixels(), True)


# --text-column-layout (off): the layout takes the columns of text crop_glyph takes, so
# each column group's crop shows the columns its text holds.  Without it the rules
# count as characters: the priced block's first group above is a column and two rules
# for nine characters, its last a rule for two.  (Measured on a book page: a block of
# six columns with a sideline beside most, the first group's crop three columns for
# four columns' worth of text.)
check("--text-column-layout is off by default",
      (pp.TEXT_COLUMN_LAYOUT, pp.build_parser().parse_args(["r", "a", "o"]).text_column_layout,
       pp.build_parser().parse_args(["r", "a", "o", "--text-column-layout"]).text_column_layout),
      (False, False, True))
pp.set_column_layout(text_only=True)
check("--text-column-layout: the priced block's layout is its two columns of text",
      [(x0, x1, count) for x0, x1, _, _, count in pp.column_layout(priced, PRICED_BLOCK) or []],
      [(700, 741, 10), (600, 641, 10)])
check("--text-column-layout: a column group is a column of text, and a column's reach its ten characters",
      (tile_ranges(priced, PRICED_BLOCK), pp.column_reach(priced, PRICED_BLOCK, 20)), ([(0, 10), (10, 20)], 10))
foot = pp.edge_region(priced, PRICED_BLOCK, True, 1, (1000, 1400))
check("--text-column-layout: the block's end edge is the foot of its last column of text, not a rule",
      (foot[0] < 600 < 641 < foot[2], foot[1] < TOP + 9 * PITCH), (True, True))
pp.set_column_layout()
check("... and off again", len(pp.column_layout(priced, PRICED_BLOCK) or []), 7)

# Sealed only when on (textColumnLayout), and a key a resume compares when absent: a page
# sealed with the switch is not current for a run without it, nor the reverse.
on = pp.decision_provenance(SimpleNamespace(prefer_engine="A", fallback_engine="A", text_column_layout=True))
off = pp.decision_provenance(SimpleNamespace(prefer_engine="A", fallback_engine="A"))
check("--text-column-layout: sealed as on, and not at all when off",
      (on.get("textColumnLayout"), "textColumnLayout" in off), ("on", False))
with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "page-0001.json"
    job = SimpleNamespace(out_json=out, out_md=out.with_suffix(".md"))
    current = []
    for sealed_with, run_with in ((on, off), (off, on), (on, on), (off, off)):
        record = {"schemaVersion": pp.SCHEMA_VERSION, "status": "complete", "scanPage": 1,
                  "provenance": {**sealed_with, "markdownSha256": pp.sha256_bytes("天地玄黃".encode("utf-8"))}}
        record["provenance"]["jsonPayloadSha256"] = pp.sha256_bytes(pp.canonical_json_bytes(record))
        out.with_suffix(".md").write_text("天地玄黃", encoding="utf-8")
        out.write_bytes(pp.canonical_json_bytes(record))
        current.append(pp.validate_completion(job, run_with)[0])
check("--text-column-layout: a resume takes a sealed page as current only under the same setting",
      current, [False, False, True, True])


# The measured pages, where the calibration corpus is on this machine.
CORPUS = Path.home() / "Documents/GitHub/jyut-ocr-corpus"


def corpus_block(book: str, page: int, index: int) -> tuple[Path, dict] | None:
    render = CORPUS / book / "renders" / f"page-{page:04d}.png"
    layout = CORPUS / book / "ocr-paddle" / f"page-{page:04d}.json"
    if not render.is_file() or not layout.is_file():
        return None
    return render, pp.load_blocks(layout)[index]


# caangung-4 p.2, where a real run regressed after the text-column cut went in: its price
# block is the one block of the page the cut changes, and the page's layout is as before.
found = corpus_block("caangung-4", 2, 19)
if found is None:
    print("corpus not on this machine: the magazine page's check skipped")
else:
    render, block = found
    check("magazine page: the price block is laid out on its 7 ink columns, as before; crop_glyph takes its 2",
          (len(pp.column_layout(render, block) or []),
           len(pp.measure_columns(render, block["box"], text_only=True) or [])), (7, 2))

# canzungsiling p.397, the page a 488-page book lost: the disputed spot's crop was a strip
# 4 px wide beside a column (16 x 7,500 enlarged) and is its column, the character in the
# middle; the block's two column groups are cut as before (on its 12 ink columns, sidelines
# too), and on its 6 columns of text with --text-column-layout.
found = corpus_block("canzungsiling", 397, 4)
if found is None:
    print("corpus not on this machine: the lost page's check skipped")
else:
    render, block = found
    spot = pp.CJK(str(block["text"])).index("纔能舒") + 3
    with Image.open(io.BytesIO(pp.crop_glyph(render, block, spot, 1) or b"")) as crop:
        check("lost page: the disputed spot's crop is its column", crop.size, (460, 4400))
    check("lost page: the block's column groups, as before", tile_ranges(render, block, pp.TILE_CHARACTERS), [(0, 147), (147, 220)])
    pp.set_column_layout(text_only=True)
    check("lost page: with --text-column-layout, on its columns of text", tile_ranges(render, block, pp.TILE_CHARACTERS),
          [(0, 146), (146, 220)])
    pp.set_column_layout()

sys.exit(1 if failures else 0)
