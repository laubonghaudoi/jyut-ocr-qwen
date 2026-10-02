"""Render measurements for the book repair tool (scripts/repair_book.py): the
ink columns of a page with its running-head band masked, their tops and feet,
the glyph pitch, and the text frame.  CPU only, no model.

measure_page() works on one render; the book model (_repair_model.py) turns
the pages' measurements into the book's cells per column, its frame and its
paragraph-indent clusters, each with the gate it passed or failed.  Nothing
here assumes a number of cells, a resolution or an indent: the pitch comes
from the ink's own period, the frame from the columns that run longest, and a
page whose columns are not taller than wide is measured as not vertical.

Pixel limits are fractions of the page's typical column width, the one size
every page shows (a speck of dust is a few pixels at any resolution; a glyph
is a column wide).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence


# A column's ink run: rows holding ink are split where a blank stretch is
# longer than this share of the column's width (a gap inside one glyph is
# shorter), and a run is kept when it is at least this tall and holds at least
# RUN_MASS column-widths of ink pixels - specks and scanner dust are neither.
RUN_GAP = 0.1
RUN_HEIGHT = 0.1
RUN_MASS = 1.0
# An x-profile run narrower than this share of the typical column is a sliver
# (a rule, a stray mark's edge), and two runs closer than this share are one
# column split by a thin gap inside a glyph (ink_columns' limits).
SLIVER = 0.4
SPLIT = 0.25
# A column's x-profile threshold: a share of the page's typical full column's
# ink, so a short column (a paragraph's last few characters) still counts.
PROFILE_SHARE = 0.02
# The pitch search: the glyph period of a long column lies between these
# shares of its height (between 8 and 80 cells a column).
PITCH_RANGE = (1 / 80, 1 / 8)
# A column is long when it is at least this share of the page's tallest.
LONG_COLUMN = 0.8


def page_ink(render: Path) -> Any:
    """The render's ink as a boolean array: darker than the paper (its modal
    level) by more than 60 levels, phase 3's ink_of rule.  None when the
    render cannot be read."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(render) as image:
            gray = np.asarray(image.convert("L"))
    except Exception:  # noqa: BLE001 - an unreadable render is measured as nothing
        return None
    hist = np.bincount(gray.ravel(), minlength=256)
    background = int(hist.argmax())
    return gray < background - 60


def mask(ink: Any, boxes: Sequence[Sequence[float]], pad: float = 0.004) -> Any:
    """INK with each normalised box (x, y, w, h) blanked, padded by PAD of
    the page's width and height."""
    height, width = ink.shape
    out = ink.copy()
    for x, y, w, h in boxes:
        x0 = max(0, int((x - pad) * width))
        x1 = min(width, int((x + w + pad) * width) + 1)
        y0 = max(0, int((y - pad) * height))
        y1 = min(height, int((y + h + pad) * height) + 1)
        if x1 > x0 and y1 > y0:
            out[y0:y1, x0:x1] = False
    return out


def _runs(flags: Any) -> list[tuple[int, int]]:
    import numpy as np
    edges = np.flatnonzero(np.diff(np.concatenate([[0], flags.astype(np.int8), [0]])))
    return [(int(a), int(b)) for a, b in zip(edges[::2], edges[1::2])]


def ink_width(runs: Sequence[Sequence[int]], xprof: Any) -> int:
    """The typical width of the x-profile's RUNS, weighted by their ink: the
    width at which half the ink lies in narrower runs.  Text columns hold
    the ink; a page crossed by many thin rules or specks has more of those
    than of columns, and a plain median of the widths would be a sliver's."""
    import numpy as np
    sized = sorted((b - a, float(np.sum(xprof[a:b]))) for a, b in runs)
    total = sum(mass for _, mass in sized)
    if total <= 0:
        return sized[len(sized) // 2][0]
    seen = 0.0
    for width, mass in sized:
        seen += mass
        if seen >= total / 2:
            return width
    return sized[-1][0]


def ink_columns(ink: Any) -> list[dict[str, Any]]:
    """Every ink column of INK, right to left: its x range, its top and foot
    (the first and last ink run that is not a speck), its runs and its ink."""
    import numpy as np
    height, width = ink.shape
    xprof = ink.sum(axis=0)
    if not xprof.any():
        return []
    strong = np.sort(xprof[xprof > 0])[-max(1, width // 20):]
    threshold = max(2.0, PROFILE_SHARE * float(np.median(strong)))
    runs = _runs(xprof > threshold)
    if not runs:
        return []
    widths = sorted(b - a for a, b in runs)
    typical = widths[len(widths) // 2]
    merged: list[list[int]] = []
    for a, b in runs:
        if merged and a - merged[-1][1] < SPLIT * typical:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    # A sliver is narrow against the columns that hold the ink: a page crossed
    # by many thin rules or specks has more of them than of columns, and the
    # plain median width that the merge uses is then a sliver's.
    typical = ink_width(merged, xprof)
    out = []
    for a, b in merged:
        if b - a < SLIVER * typical:
            continue
        yprof = ink[:, a:b].sum(axis=1)
        rows = _runs(yprof >= max(2, int(0.05 * (b - a))))
        kept: list[list[int]] = []
        for top, foot in rows:
            if kept and top - kept[-1][1] <= RUN_GAP * typical:
                kept[-1][1] = foot
            else:
                kept.append([top, foot])
        kept = [[t, f] for t, f in kept
                if f - t >= RUN_HEIGHT * typical and int(yprof[t:f].sum()) >= RUN_MASS * typical]
        if not kept:
            continue
        out.append({"x0": a, "x1": b, "top": kept[0][0], "foot": kept[-1][1],
                    "runs": kept, "ink": int(yprof.sum())})
    out.sort(key=lambda c: -c["x0"])
    return out


def column_pitch(ink: Any, column: dict[str, Any]) -> int | None:
    """The glyph period of one column: the first strong peak of its row
    profile's autocorrelation (a glyph's own blank rows make the period's
    multiples peak too; the first of them above half the strongest is the
    period)."""
    import numpy as np
    top, foot = column["top"], column["foot"]
    rows = ink[top:foot, column["x0"]:column["x1"]].any(axis=1).astype(float)
    n = len(rows)
    lo, hi = max(2, int(n * PITCH_RANGE[0])), int(n * PITCH_RANGE[1])
    if hi <= lo + 2:
        return None
    rows -= rows.mean()
    spectrum = np.fft.rfft(rows, 2 * n)
    corr = np.fft.irfft(spectrum * np.conj(spectrum))[:n]
    window = corr[lo:hi]
    if window.max() <= 0:
        return None
    peaks = [k for k in range(1, len(window) - 1)
             if window[k] >= window[k - 1] and window[k] >= window[k + 1] and window[k] > 0.5 * window.max()]
    return lo + (peaks[0] if peaks else int(window.argmax()))


def measure_page(render: Path, band_boxes: Sequence[Sequence[float]] = (),
                 band_strip: tuple[float, float] | None = None,
                 band_side: str | None = None) -> dict[str, Any] | None:
    """One page's columns with its band masked: BAND_BOXES (normalised boxes
    of the band's blocks) are blanked, and an ink column whose centre lies in
    BAND_STRIP (a normalised x range, the band's column on this page) is set
    aside as the band's when it is outermost on BAND_SIDE ("right" or
    "left"): a column in the strip with a body column further out is body
    text that happens to lie there.  None when the render cannot be read."""
    ink = page_ink(render)
    if ink is None:
        return None
    height, width = ink.shape
    ink = mask(ink, band_boxes)
    columns = ink_columns(ink)
    in_strip = [bool(band_strip) and band_strip[0] <= (c["x0"] + c["x1"]) / 2 / width <= band_strip[1]
                for c in columns]
    # Columns run right to left: the outer edge is the start of the list on
    # the right, its end on the left.
    order = range(len(columns)) if band_side != "left" else range(len(columns) - 1, -1, -1)
    band_at: set[int] = set()
    for k in order:
        if not in_strip[k]:
            if band_side in ("right", "left"):
                break
            continue
        band_at.add(k)
    body = [c for k, c in enumerate(columns) if k not in band_at]
    band = [c for k, c in enumerate(columns) if k in band_at]
    tall =[c for c in body if c["foot"] - c["top"] > 2 * (c["x1"] - c["x0"])]
    vertical = bool(body) and len(tall) >= 0.5 * len(body)
    pitches = []
    if body:
        longest = max(c["foot"] - c["top"] for c in body)
        for column in body:
            if column["foot"] - column["top"] >= LONG_COLUMN * longest:
                pitch = column_pitch(ink, column)
                if pitch:
                    pitches.append(pitch)
    return {
        "width": width, "height": height, "vertical": vertical,
        "columns": [{k: c[k] for k in ("x0", "x1", "top", "foot", "ink")} for c in body],
        "bandColumns": [{k: c[k] for k in ("x0", "x1", "top", "foot")} for c in band],
        "pitches": pitches,
    }


def frame_of(columns: Sequence[dict[str, Any]], pitch: float, cells: int | None = None) -> dict[str, float] | None:
    """The text frame's top and foot, fitted as lines across the page (a
    skewed scan tilts both) to the long columns that start and end at the
    frame, refitted three times keeping the columns within 0.6 pitch of the
    line.  The edge is the highest top (lowest foot) of the long columns;
    given the book's CELLS per column, it may instead be the highest top
    (lowest foot) that two long columns share, whichever pair spans CELLS
    best: one run of ink past the rest (a stamp under the text) is no edge,
    and neither is the paragraph indent a page's flush columns stand above.
    Needs three long columns; None otherwise."""
    import numpy as np
    if not columns:
        return None
    longest = max(c["foot"] - c["top"] for c in columns)
    long_ = [c for c in columns if c["foot"] - c["top"] >= LONG_COLUMN * longest]
    if len(long_) < 3:
        return None
    xs = np.array([(c["x0"] + c["x1"]) / 2 for c in long_], float)
    tops = np.array([c["top"] for c in long_], float)
    feet = -np.array([c["foot"] for c in long_], float)

    def anchors(values: Any) -> list[float]:
        ordered = np.sort(values)
        out = [float(ordered[0])]
        shared = next((v for v in ordered if np.sum(np.abs(values - v) <= 0.75 * pitch) >= 2), None)
        if shared is not None and float(shared) not in out:
            out.append(float(shared))
        return out

    def fit(values: Any, anchor: float) -> tuple[float, float]:
        keep = np.abs(values - anchor) <= 0.75 * pitch
        slope, intercept = 0.0, float(np.median(values[keep]))
        for _ in range(3):
            if keep.sum() >= 3:
                slope, intercept = (float(v) for v in np.polyfit(xs[keep], values[keep], 1))
            else:
                slope, intercept = 0.0, float(np.median(values[keep]))
            keep = np.abs(values - (intercept + slope * xs)) <= 0.6 * pitch
            if not keep.any():
                keep = np.abs(values - anchor) <= 0.75 * pitch
        return slope, intercept

    pairs = [(t, f) for t in anchors(tops) for f in anchors(feet)]
    if cells:
        pairs.sort(key=lambda pair: abs((-pair[1] - pair[0]) / pitch - cells))
    top_slope, top_at = fit(tops, pairs[0][0])
    foot_slope, foot_at = fit(feet, pairs[0][1])
    return {"topSlope": top_slope, "topIntercept": top_at, "footSlope": -foot_slope, "footIntercept": -foot_at}


def frame_at(frame: dict[str, float], x: float) -> tuple[float, float]:
    """The frame's top and foot at pixel column X."""
    return (frame["topIntercept"] + frame["topSlope"] * x, frame["footIntercept"] + frame["footSlope"] * x)
