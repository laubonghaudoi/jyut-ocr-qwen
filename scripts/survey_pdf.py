#!/usr/bin/env python3
"""Phase 1: render a source PDF and seal a page manifest before any OCR runs.

This is the survey pass.  It produces the two artifacts every later phase reads
from disk rather than from conversation context:

    page-manifest.json   the sealed scan inventory (schema per audit_ocr_markdown)
    survey-report.json   render provenance, geometry stats and anomaly candidates

Why files and not context: a long book cannot be proofread inside one context
window, and an agent harness auto-compacts.  Phase 2 (OCR) and phase 3
(proofreading) must therefore be able to start from disk alone.

The manifest deliberately carries only what the audit schema defines.  Anomaly
candidates go in the survey report instead, because the skill requires a blank,
duplicate or rotated page to be confirmed against the page image before anything
is recorded as fact.  In particular this script never sets `marker_expected:
false` on its own: a low-ink page is a candidate for visual review, not a
verified blank.

Usage:
    python3 scripts/survey_pdf.py SOURCE.pdf OUTPUT_DIR [--dpi 300]
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

MANIFEST_NAME = "page-manifest.json"
REPORT_NAME = "survey-report.json"
RENDERS_DIRNAME = "renders"
DEFAULT_DPI = 300

# A page whose TEXT ink falls below this fraction is a BLANK CANDIDATE for
# visual review.  It is never treated as a verified blank, so this errs toward
# flagging: the sparsest genuinely typeset page measured 0.0065 and a blank
# ruled leaf measured 0.024, and those two cannot be separated by ink alone.
# Over-flagging costs a human glance; under-flagging cost three pages that
# failed the whole proofread phase before this was fixed.
BLANK_INK_FRACTION = 0.03
# Aspect ratio this far from the document median flags a spread candidate.
SPREAD_RATIO_TOLERANCE = 0.15


class SurveyError(RuntimeError):
    """The survey cannot proceed."""


@dataclass(frozen=True)
class PageFacts:
    scan_page: int
    render_file: Path
    render_sha256: str
    width: int
    height: int
    ink_fraction: float | None


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, indent=2, sort_keys=True, separators=(",", ": ")
    ).encode("utf-8")


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise SurveyError(f"{name} is required (install poppler-utils)")
    return path


def pdf_facts(pdf_path: Path) -> dict[str, Any]:
    """Page count and nominal page size straight from pdfinfo."""
    result = subprocess.run(
        [require_tool("pdfinfo"), str(pdf_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SurveyError(f"pdfinfo failed: {(result.stderr or '').strip()}")
    facts: dict[str, Any] = {}
    for line in result.stdout.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        facts[key.strip()] = value.strip()
    if "Pages" not in facts:
        raise SurveyError("pdfinfo did not report a page count")
    try:
        facts["_page_count"] = int(facts["Pages"])
    except ValueError as error:
        raise SurveyError(f"unreadable page count: {facts['Pages']}") from error
    if facts["_page_count"] < 1:
        raise SurveyError("PDF reports no pages")
    return facts


# Same selector grammar as the OCR runners, so `--pages 1,30,80-85` means the
# same thing in every phase.
PAGE_TOKEN = re.compile(r"\A(?P<first>\d+)(?:-(?P<last>\d+))?\Z")


def parse_page_selection(expression: str) -> list[int]:
    pages: set[int] = set()
    for token in expression.split(","):
        token = token.strip()
        if not token:
            continue
        match = PAGE_TOKEN.match(token)
        if match is None:
            raise SurveyError(f"invalid page selector: {token!r}")
        first = int(match.group("first"))
        last = int(match.group("last") or first)
        if last < first:
            raise SurveyError(f"descending page range: {token!r}")
        pages.update(range(first, last + 1))
    if not pages:
        raise SurveyError("no pages were selected")
    return sorted(pages)


def contiguous_runs(numbers: list[int]) -> list[tuple[int, int]]:
    """Group sorted page numbers into (first, last) runs.

    pdftoppm takes one range per call, so a scattered selection like
    1,2,30,31,80 costs three calls rather than one per page.
    """
    runs: list[tuple[int, int]] = []
    for number in sorted(set(numbers)):
        if runs and number == runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], number)
        else:
            runs.append((number, number))
    return runs


def render_pages(
    pdf_path: Path, renders_dir: Path, dpi: int, first: int, last: int
) -> None:
    """Render with one pdftoppm call, then normalise to fixed 4-digit names.

    pdftoppm pads to the width of the last page number, so a 344-page book gets
    3 digits and a 1200-page book gets 4.  Downstream runners expect exactly
    page-NNNN.png, so the names are normalised here rather than everywhere else.
    """
    renders_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(renders_dir)) as staging:
        prefix = Path(staging) / "page"
        result = subprocess.run(
            [
                require_tool("pdftoppm"),
                "-r",
                str(dpi),
                "-png",
                "-f",
                str(first),
                "-l",
                str(last),
                str(pdf_path),
                str(prefix),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise SurveyError(f"pdftoppm failed: {(result.stderr or '').strip()}")
        produced = sorted(Path(staging).glob("page-*.png"))
        if not produced:
            raise SurveyError("pdftoppm produced no output")
        pattern = re.compile(r"page-(\d+)\.png\Z")
        for item in produced:
            match = pattern.match(item.name)
            if match is None:
                raise SurveyError(f"unexpected render name: {item.name}")
            number = int(match.group(1))
            os.replace(item, renders_dir / f"page-{number:04d}.png")


RULE_COVERAGE = 0.5   # a row/column this inked is a printed rule, not text
INK_MARGIN = 45       # levels below this page's own paper before it counts as ink


def measure_page(render_file: Path) -> tuple[int, int, float | None]:
    """Pixel size and the fraction of the page carrying TEXT ink.

    Two corrections over a plain darkness count, both forced by real books.

    An absolute cutoff assumes white paper.  《廣東憲政籌備處報告書》 is scanned
    grey, so counting pixels under 230 made every page - including three blank
    ones - read as almost entirely ink, and the survey reported zero blank
    candidates for a book that has three.  Ink is contrast against the paper
    this page was actually scanned on.

    And ink is not text.  Those blank leaves still carry a printed border frame
    and column rules.  Rows and columns that are almost entirely inked are
    rules; what remains is text.
    """
    try:
        from PIL import Image
    except ImportError:
        return 0, 0, None
    with Image.open(render_file) as image:
        width, height = image.size
        grey = image.convert("L")
        # Downsample first: this measure only needs to be approximate, and it
        # keeps a 344-page survey to seconds rather than minutes.
        grey.thumbnail((400, 400))
        histogram = grey.histogram()
        if not sum(histogram):
            return width, height, 0.0
        paper = max(range(len(histogram)), key=lambda level: histogram[level])
        cutoff = paper - INK_MARGIN
        if cutoff <= 0:
            # Modal level already black: no usable contrast to measure.
            return width, height, None
        binary = grey.point(lambda level: 255 if level < cutoff else 0)
        small_width, small_height = binary.size
        rows = binary.tobytes()
        columns = binary.transpose(Image.ROTATE_90).tobytes()

    row_ink = [rows[y * small_width:(y + 1) * small_width].count(255)
               for y in range(small_height)]
    column_ink = [columns[x * small_height:(x + 1) * small_height].count(255)
                  for x in range(small_width)]
    rule_columns = sum(1 for ink in column_ink if ink >= small_height * RULE_COVERAGE)
    text_rows = [ink for ink in row_ink if ink < small_width * RULE_COVERAGE]
    if not text_rows:
        return width, height, 0.0
    # Every surviving row still crosses the rule columns; discount them.
    text_ink = sum(max(0, ink - rule_columns) for ink in text_rows)
    area = len(text_rows) * max(1, small_width - rule_columns)
    return width, height, text_ink / area


def build_manifest(
    pdf_path: Path, pdf_sha: str, pages: list[PageFacts], manifest_path: Path
) -> dict[str, Any]:
    records = []
    for page in pages:
        records.append(
            {
                "scan_page": page.scan_page,
                # Relative to the manifest's own directory, per the audit loader.
                "render_file": os.path.relpath(page.render_file, manifest_path.parent),
                "render_sha256": page.render_sha256,
            }
        )
    return {
        "source_pdf": str(pdf_path),
        "source_sha256": pdf_sha,
        "expected_scan_pages": len(pages),
        "generated_at": utc_now(),
        "pages": records,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("source_pdf", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    parser.add_argument(
        "--last-page",
        type=int,
        help="survey only pages 1..N (smoke tests); default is the whole document",
    )
    parser.add_argument(
        "--pages",
        help="survey an explicit set, e.g. 1,30,80-85. Calibration samples a long "
             "book at intervals rather than reading its first N pages, and a "
             "prefix is not a representative sample of anything.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="re-render pages that already exist",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        pdf_path = arguments.source_pdf.expanduser().resolve()
        if not pdf_path.is_file():
            raise SurveyError(f"source PDF does not exist: {pdf_path}")
        if arguments.dpi < 72:
            raise SurveyError("--dpi below 72 is too low for small CJK glyphs")
        output_directory = arguments.output_directory.expanduser().resolve()
        renders_dir = output_directory / RENDERS_DIRNAME
        output_directory.mkdir(parents=True, exist_ok=True)

        facts = pdf_facts(pdf_path)
        page_count = facts["_page_count"]
        if arguments.pages and arguments.last_page:
            raise SurveyError("--pages cannot be combined with --last-page")
        if arguments.pages:
            selected = sorted(parse_page_selection(arguments.pages))
            outside = [n for n in selected if n < 1 or n > page_count]
            if outside:
                raise SurveyError(
                    f"--pages {outside[:5]} outside the document's 1..{page_count}"
                )
            last_page = max(selected)
        else:
            last_page = arguments.last_page or page_count
            if last_page < 1 or last_page > page_count:
                raise SurveyError(
                    f"--last-page {last_page} outside the document's 1..{page_count}"
                )
            selected = list(range(1, last_page + 1))

        print(f"  source     : {pdf_path.name} ({page_count} pages)", flush=True)
        pdf_sha = sha256_file(pdf_path)
        print(f"  sha256     : {pdf_sha[:16]}…", flush=True)

        existing = {
            int(p.stem.split("-")[1])
            for p in renders_dir.glob("page-*.png")
            if p.stem.split("-")[-1].isdigit()
        } if renders_dir.is_dir() else set()
        wanted = set(selected)
        todo = sorted(wanted) if arguments.overwrite else sorted(wanted - existing)

        if todo:
            runs = contiguous_runs(todo)
            shown = ", ".join(f"{a}" if a == b else f"{a}-{b}" for a, b in runs[:6])
            if len(runs) > 6:
                shown += f", … {len(runs) - 6} more runs"
            print(f"  rendering  : {len(todo)} page(s) [{shown}] at {arguments.dpi} dpi",
                  flush=True)
            for first, last in runs:
                render_pages(pdf_path, renders_dir, arguments.dpi, first, last)
        else:
            print(f"  rendering  : all {len(wanted)} selected page(s) already present",
                  flush=True)

        pages: list[PageFacts] = []
        for scan_page in selected:
            render_file = renders_dir / f"page-{scan_page:04d}.png"
            if not render_file.is_file():
                raise SurveyError(f"render missing after rendering: {render_file}")
            width, height, ink = measure_page(render_file)
            pages.append(
                PageFacts(
                    scan_page=scan_page,
                    render_file=render_file,
                    render_sha256=sha256_file(render_file),
                    width=width,
                    height=height,
                    ink_fraction=ink,
                )
            )
            if scan_page % 50 == 0:
                print(f"  measured   : {scan_page}/{last_page}", flush=True)
    except SurveyError as error:
        print(f"ERROR {error}", file=sys.stderr)
        return 2

    manifest_path = output_directory / MANIFEST_NAME
    manifest = build_manifest(pdf_path, pdf_sha, pages, manifest_path)
    manifest_bytes = canonical_json_bytes(manifest)
    manifest_path.write_bytes(manifest_bytes)

    # Anomaly CANDIDATES. Every one needs confirming against the page image
    # before it becomes a manifest fact; nothing here sets marker_expected.
    ratios = [p.height / p.width for p in pages if p.width and p.height]
    median_ratio = sorted(ratios)[len(ratios) // 2] if ratios else 0.0
    blank_candidates = [
        p.scan_page
        for p in pages
        if p.ink_fraction is not None and p.ink_fraction < BLANK_INK_FRACTION
    ]
    spread_candidates = [
        p.scan_page
        for p in pages
        if p.width
        and p.height
        and median_ratio
        and abs((p.height / p.width) - median_ratio) / median_ratio
        > SPREAD_RATIO_TOLERANCE
    ]
    by_hash: dict[str, list[int]] = {}
    for page in pages:
        by_hash.setdefault(page.render_sha256, []).append(page.scan_page)
    duplicate_renders = [v for v in by_hash.values() if len(v) > 1]

    report = {
        "generated_at": utc_now(),
        "source_pdf": str(pdf_path),
        "source_sha256": pdf_sha,
        "pdf_page_count": page_count,
        "surveyed_pages": len(pages),
        "render": {
            "tool": "pdftoppm",
            "dpi": arguments.dpi,
            "format": "png",
            "directory": str(renders_dir),
            "name_pattern": "page-NNNN.png",
        },
        "pdf_info": {k: v for k, v in facts.items() if not k.startswith("_")},
        "geometry": {
            "median_height_over_width": round(median_ratio, 4),
            "distinct_sizes": sorted(
                {f"{p.width}x{p.height}" for p in pages if p.width}
            ),
        },
        "candidates_needing_visual_confirmation": {
            "note": "candidates only; confirm against the page image before "
            "recording any of these as fact (e.g. marker_expected=false)",
            "blank_pages": blank_candidates,
            "spread_pages": spread_candidates,
            "duplicate_renders": duplicate_renders,
        },
        "manifest": {
            "path": str(manifest_path),
            "sha256": sha256_bytes(manifest_bytes),
        },
    }
    report_path = output_directory / REPORT_NAME
    report_path.write_bytes(canonical_json_bytes(report))

    print(f"  manifest   : {manifest_path}", flush=True)
    print(f"  report     : {report_path}", flush=True)
    print(
        f"  candidates : {len(blank_candidates)} blank, "
        f"{len(spread_candidates)} spread, {len(duplicate_renders)} duplicate "
        "(all need visual confirmation)",
        flush=True,
    )
    if len(pages) != page_count:
        print(
            f"  NOTE surveyed {len(pages)} of {page_count} pages; this manifest "
            "does not describe the whole document",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
