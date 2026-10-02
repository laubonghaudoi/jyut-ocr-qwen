#!/usr/bin/env python3
"""Finish a proofread book in one command: assemble its sealed pages, repair
the book, take out the page markers, and write the doubt list.

    python3 scripts/finish_book.py BOOK

BOOK is the book's folder: the one that holds phase 3's sealed pages, both
engines' drafts, the renders, book-profile.json and the page manifest
(survey_pdf.py's).  Each is found by the book's layout (proofread/,
ocr-paddle/, ocr-hunyuan/, renders/, book-profile.json, page-manifest.json),
by what the profile (`sources`) and the page manifest (`render_file`) name,
or by the files themselves (the one folder of sealed pages; the one folder of
each engine's drafts); --proofread, --renders, --ocr-a, --ocr-b, --profile
and --page-manifest name one when the book lays them out otherwise.

The chain, in order.  Every step can be run again: a step whose output is
current is kept, and a step that was stopped goes on where it stopped.

1. assemble.  Every page the page manifest expects must be sealed by phase 3
   (complete, its seal intact, sealed on the manifest's render: exit 3
   otherwise).  write_assembly_inputs() writes the sealed texts, verbatim, as
   one segment with canonical page markers (assembled/segments/), the ordered
   segment manifest, the page list (page-sources.json) and a byte copy of the
   page manifest, and assemble_ocr_segments.py writes
   assembled/combined-annotated.md and its receipt.  All of it is built in a
   partial folder and renamed into place.  An assembly that still matches
   the sealed pages (the page list's hashes, a replay of the segments, each
   page's text) is kept; one that does not is moved aside
   (assembled.stale-<time>/), never deleted.
2. repair.  repair_book.py BOOK --output BOOK/repaired, with its questions to
   the model (--no-model: none; each question becomes a doubt).  A finished
   repair of the same inputs, code and options is kept; any other earlier
   repair folder is resumed (--resume: an answer already given is not asked
   again).
3. finalize.  finalize_page_markers.py with the boundaries.json the repair
   wrote turns repaired/combined-repaired.md into BOOK/final.md, which must
   then hold no page marker; the final audit (audit_ocr_markdown.py --mode
   final) runs on it, and its errors are doubts, not a failure.
4. doubts.  BOOK/doubts.md: a short list, by kind and page, of what the
   pipeline could not settle - the research queue (proper names no glyph can
   settle), phase 3's doubts, the repair's doubts, the defect counters still
   hit after the repair, the final audit's errors - ranked: a count of every
   kind, then what most likely changes the text first (the characters, then
   the marks, the structure, the tables, the format), a doubt whose flagged
   text is the running head's (the repair's book model: its stems, suffixes,
   the page's folio) folded last with no detail; and finish/doubts.json with
   every item (`noise` marks the folded ones).  doubts.md names no image: it
   is for the person who reads the book against the PDF.

final.md and doubts.md are the person's once written: when the command runs
again and either is not what it last wrote there (the user's corrections,
ticks in the doubt list, or a file this command never wrote), that file is
moved aside to final.edited-<time>.md / doubts.edited-<time>.md, never
overwritten, and the RESULT line names the copy.  finish/written.json keeps
the SHA-256 of what it wrote.  Nothing the command reads may lie in
assembled/, which it moves aside when stale (exit 2).

What an agent sees is one line and two paths.  stdout is exactly
`[finish] RESULT exit=N STATE finish_book.py: ...`, then `final.md: PATH` and
`doubts.md: PATH` when they are written.  Every step's own output goes to
BOOK/finish/finish-book.log, which also gets `[finish] step K of 4: ...`
lines, and `WARNING ...` lines (counted in the RESULT line) for what the
agent must pass on; scripts/wait_for_run.py BOOK LOG reads them while the run
goes on (LOG is the file this command's stdout goes to) and reads the RESULT
line when it ends.  A second run on the same book is refused before it
writes anything there.  Nothing is printed or written for anyone to look at a
page image: the pipeline's questions and doubts.md stand in for that.

Exit codes:
    0  done: final.md and doubts.md are written
    1  a step failed: the assembly or the repair did not verify (repair exit
       4 or 5), finalize refused, or page markers are left - read
       finish/finish-book.log; the same command fails the same way
    2  wrong arguments, or the book's inputs are missing, ambiguous or fail
       verification (a sealed page edited after sealing, a sealed page the
       manifest does not know, another finish_book.py on the same book)
    3  not ready: pages the manifest expects are not sealed yet (phase 3 has
       not finished them) - run proofread_pages.py on them first
    4  stopped (SIGTERM, SIGINT) - run the same command again; nothing done
       is lost (the model's answers still on the wire are not waited for:
       they are asked again)
    6  the model could not be asked (repair_book.py exit 6) - the answers
       already given are kept; run the same command again once the server is
       up, or with --no-model
"""

from __future__ import annotations

import argparse
import contextlib
from dataclasses import dataclass, field
import datetime as _dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sys
import time
from typing import Any, Callable, Iterator, Mapping, Sequence

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

EXIT_DONE, EXIT_FAILED, EXIT_USAGE, EXIT_NOT_READY, EXIT_STOPPED, EXIT_MODEL = 0, 1, 2, 3, 4, 6
STATE = {EXIT_DONE: "DONE", EXIT_FAILED: "FAILED", EXIT_USAGE: "FAILED", EXIT_NOT_READY: "NOT READY",
         EXIT_STOPPED: "STOPPED", EXIT_MODEL: "STOPPED"}

# What the command writes, under BOOK.
FINAL = "final.md"
DOUBTS = "doubts.md"
FINISH_DIR = "finish"                      # its own files
LOG_NAME = "finish-book.log"
REPORT_NAME = "finish-report.json"
DOUBTS_JSON = "doubts.json"
AUDIT_NAME = "final-audit.json"
WRITTEN_NAME = "written.json"              # the SHA-256 of each final.md and doubts.md it wrote
WRITTEN_KEPT = 50                          # how many of them it remembers, per file
LOCK_NAME = ".lock"
ASSEMBLED = "assembled"
PARTIAL = ".assembled.partial"
REPAIRED = "repaired"
STEPS = 4
RESULT_PREFIX = "[finish] RESULT"
STEP_PREFIX = "[finish] step"
TOOL = "finish_book.py"

# The engines' names in their drafts' JSON (run_paddleocr_vl.py, run_hunyuanocr.py).
ENGINE_A_NAME = "PaddleOCR-VL"
ENGINE_B_NAME = "HunyuanOCR"
SEGMENT_NAME = "segments/s01-p{start:04d}-{end:04d}.md"
# doubts.md: detail lines shown per kind; the rest by page only.
SHOWN_PER_KIND = 10
DETAIL_CHARS = 220


class FinishError(Exception):
    """A step cannot go on: CODE is the exit code, the message says why."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


class Stopped(BaseException):
    """SIGTERM or SIGINT (a BaseException: no tool's `except Exception` keeps it)."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=TOOL, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("book", type=Path, help="the book's folder (phase 3's sealed pages, drafts, renders, profile)")
    for name, what in (("proofread", "phase 3's sealed pages"), ("renders", "the page renders"),
                       ("ocr-a", "engine A's drafts (PaddleOCR-VL)"), ("ocr-b", "engine B's drafts (HunyuanOCR)"),
                       ("profile", "book-profile.json"), ("page-manifest", "survey_pdf.py's page-manifest.json")):
        parser.add_argument(f"--{name}", type=Path, help=f"{what} (default: found in the book's folder)")
    parser.add_argument("--no-model", action="store_true",
                        help="repair without asking the model: every question becomes a doubt in doubts.md")
    parser.add_argument("--endpoint", help="the model server's chat endpoint (default: repair_book.py's, phase 3's)")
    parser.add_argument("--model", help="the model's name (default: repair_book.py's, phase 3's)")
    parser.add_argument("--max-inflight", type=int,
                        help="requests on the wire at once: the server's lanes (default: repair_book.py's)")
    parser.add_argument("--timeout", type=float, help="seconds one model request may take (default: repair_book.py's)")
    parser.add_argument("--workers", type=int, default=min(6, os.cpu_count() or 1),
                        help="CPU processes for the repair's book model and counters")
    return parser


# --- where the inputs are -------------------------------------------------------------------

@dataclass
class Inputs:
    book: Path
    proofread: Path
    renders: Path
    ocr_a: Path
    ocr_b: Path
    profile: Path | None
    page_manifest: Path
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, str | None]:
        return {name: (str(getattr(self, name)) if getattr(self, name) is not None else None)
                for name in ("proofread", "renders", "ocr_a", "ocr_b", "profile", "page_manifest")}


PAGE_FILE = re.compile(r"page-(\d{4,})\.(md|json|txt|png)")


def _page_numbers(folder: Path, suffix: str) -> list[int]:
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    out = []
    for name in names:
        match = PAGE_FILE.fullmatch(name)
        if match and match.group(2) == suffix:
            out.append(int(match.group(1)))
    return sorted(out)


def _is_sealed_folder(folder: Path) -> bool:
    """Whether FOLDER holds phase 3's sealed pages: page-NNNN.md beside a
    page-NNNN.json that carries a Markdown seal."""
    for scan in _page_numbers(folder, "md")[:3]:
        try:
            record = json.loads((folder / f"page-{scan:04d}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(record, dict) and (record.get("provenance") or {}).get("markdownSha256"):
            return True
    return False


def _draft_engine(folder: Path) -> str | None:
    """The engine that wrote the drafts in FOLDER (their JSON's `engine`)."""
    for scan in _page_numbers(folder, "json")[:3]:
        try:
            record = json.loads((folder / f"page-{scan:04d}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(record, dict) and isinstance(record.get("engine"), str) and _page_numbers(folder, "txt"):
            return record["engine"]
    return None


def _subfolders(book: Path) -> list[Path]:
    try:
        return sorted(p for p in book.iterdir() if p.is_dir() and not p.name.startswith("."))
    except OSError:
        return []


def _one(found: Sequence[Path], what: str, switch: str) -> Path:
    if len(found) == 1:
        return found[0]
    if not found:
        raise FinishError(EXIT_USAGE, f"no {what} found in the book's folder - name it with {switch}")
    raise FinishError(EXIT_USAGE, f"more than one folder holds {what} ({', '.join(p.name for p in found)}) - "
                                  f"name the one phase 3 used with {switch}")


def _given(path: Path | None) -> Path | None:
    return Path(os.path.realpath(os.path.expanduser(str(path)))) if path is not None else None


def resolve_inputs(book: Path, arguments: argparse.Namespace) -> Inputs:
    """Where each input is: as given, else the book's layout, else what the
    profile and the page manifest name, else the one folder that holds it."""
    book = _given(book)
    assert book is not None
    if not book.is_dir():
        raise FinishError(EXIT_USAGE, f"{book} is not a folder")
    notes: list[str] = []

    proofread = _given(arguments.proofread)
    if proofread is None:
        if _is_sealed_folder(book / "proofread"):
            proofread = book / "proofread"
        else:
            proofread = _one([p for p in _subfolders(book) if _is_sealed_folder(p)], "phase 3's sealed pages",
                             "--proofread")
    if not _page_numbers(proofread, "md"):
        raise FinishError(EXIT_USAGE, f"no sealed pages in {proofread}")

    profile = _given(arguments.profile)
    if profile is None and (book / "book-profile.json").is_file():
        profile = book / "book-profile.json"
    sources: dict[str, Any] = {}
    if profile is not None:
        try:
            data = json.loads(profile.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise FinishError(EXIT_USAGE, f"{profile}: unreadable: {error}") from error
        sources = (data.get("sources") or {}) if isinstance(data, dict) else {}
    else:
        notes.append("no book-profile.json found: the repair runs without the book profile")

    def named(key: str) -> Path | None:
        """What the profile's `sources` names (where the profile was made)."""
        value = sources.get(key)
        return Path(os.path.realpath(value)) if isinstance(value, str) and value else None

    def inside(path: Path | None) -> bool:
        return path is not None and (path == book or book in path.parents)

    def drafts(given: Path | None, key: str, default: str, engine: str, switch: str) -> Path:
        """The book's own folder first (a book copied elsewhere keeps its
        profile's old paths), then the one the profile names in the book,
        then the one folder of the book with this engine's drafts, then the
        profile's folder outside the book."""
        if given is not None:
            return given
        if _page_numbers(book / default, "txt"):
            return book / default
        source = named(key)
        if inside(source) and _page_numbers(source, "txt"):
            return source
        found = [p for p in _subfolders(book) if _draft_engine(p) == engine]
        if not found and source is not None and _page_numbers(source, "txt"):
            return source
        return _one(found, f"{engine}'s drafts", switch)

    ocr_a = drafts(_given(arguments.ocr_a), "draftA", "ocr-paddle", ENGINE_A_NAME, "--ocr-a")
    ocr_b = drafts(_given(arguments.ocr_b), "draftB", "ocr-hunyuan", ENGINE_B_NAME, "--ocr-b")
    if ocr_a == ocr_b:
        raise FinishError(EXIT_USAGE, f"engine A's and engine B's drafts are the same folder {ocr_a}")

    manifest = _given(arguments.page_manifest)
    if manifest is None:
        candidates = [book / "page-manifest.json", book / "renders" / "page-manifest.json"]
        if inside(named("renders")):
            candidates.append(named("renders").parent / "page-manifest.json")
        manifest = next((Path(os.path.realpath(c)) for c in candidates if c.is_file()), None)
        if manifest is None:
            raise FinishError(EXIT_USAGE, "no page-manifest.json (survey_pdf.py's) found - name it with "
                                          "--page-manifest")

    renders = _given(arguments.renders)
    if renders is None:
        candidates = []
        try:
            from _ocr_markdown import load_page_manifest
            first = load_page_manifest(manifest).pages[0]
            candidates.append(first.render_path.parent)
        except Exception:  # noqa: BLE001 - verified with its own message below
            pass
        if inside(named("renders")):
            candidates.append(named("renders"))
        candidates += [book / "renders", book / "renders" / "renders"]
        renders = next((Path(os.path.realpath(c)) for c in candidates if _page_numbers(c, "png")), None)
        if renders is None:
            raise FinishError(EXIT_USAGE, "no folder of page renders (page-NNNN.png) found - name it with --renders")
    # assembled/ is moved aside whole when it no longer matches the sealed
    # pages (and .assembled.partial/ is deleted): an input there would go
    # with it.
    for switch, path in (("--proofread", proofread), ("--renders", renders), ("--ocr-a", ocr_a),
                         ("--ocr-b", ocr_b), ("--profile", profile), ("--page-manifest", manifest)):
        for own in (book / ASSEMBLED, book / PARTIAL):
            if path is not None and (path == own or own in path.parents):
                raise FinishError(EXIT_USAGE, f"{switch} {path} is in {own.name}/, which {TOOL} writes and moves "
                                              f"aside - move it out (or rename {own.name}/) and name it with {switch}")
    return Inputs(book, proofread, renders, ocr_a, ocr_b, profile, manifest, notes)


# --- the sealed pages -------------------------------------------------------------------------

@dataclass
class Sealed:
    """The book as phase 3 sealed it: the manifest's bytes, marker policy and
    render hashes; each sealed page's text, record and page-list row."""
    manifest_bytes: bytes
    expected: int
    marker: dict[int, bool]
    texts: dict[int, str]
    records: dict[int, dict[str, Any]]
    rows: list[dict[str, Any]]
    source_pdf: str | None

    def marker_pages(self) -> list[int]:
        return [scan for scan in sorted(self.marker) if self.marker[scan]]


def _compress(pages: Sequence[int], comma: str = ", ", dash: str = "-") -> str:
    """1, 2, 3, 5 -> "1-3, 5" (doubts.md: "1–3、5")."""
    pages = sorted(set(pages))
    runs: list[str] = []
    start = previous = None
    for page in pages + [None]:  # type: ignore[list-item]
        if page is not None and previous is not None and page == previous + 1:
            previous = page
            continue
        if start is not None:
            runs.append(str(start) if start == previous else f"{start}{dash}{previous}")
        start = previous = page
    return comma.join(runs)


def _pages(pages: Sequence[int]) -> str:
    return _compress(pages, "、", "–")


def read_sealed(inputs: Inputs, log: "Log") -> Sealed:
    """Verify phase 3's sealed pages against their seals and the page
    manifest.  NOT READY (exit 3) when a page the manifest expects is missing,
    incomplete or sealed on another render; exit 2 when a seal is broken or a
    sealed page is not the manifest's."""
    import proofread_pages as pp
    import _repair_inputs as ri
    from _ocr_markdown import load_page_manifest

    try:
        manifest_bytes = inputs.page_manifest.read_bytes()
        manifest = load_page_manifest(inputs.page_manifest)
        source_pdf = json.loads(manifest_bytes.decode("utf-8")).get("source_pdf")
    except (OSError, ValueError) as error:
        raise FinishError(EXIT_USAGE, f"{inputs.page_manifest}: {error}") from error
    marker = {record.scan_page: record.marker_expected for record in manifest.pages}
    render_sha = {record.scan_page: record.render_sha256 for record in manifest.pages}
    if sorted(marker) != list(range(1, manifest.expected_scan_pages + 1)):
        raise FinishError(EXIT_USAGE, f"{inputs.page_manifest}: its pages are not 1-{manifest.expected_scan_pages}")
    sealed = _page_numbers(inputs.proofread, "md")
    stray = [scan for scan in sealed if scan not in marker]
    if stray:
        raise FinishError(EXIT_USAGE, f"sealed pages {_compress(stray)} in {inputs.proofread} are not in the page "
                                      f"manifest's {manifest.expected_scan_pages} pages - move them out, or name "
                                      "the manifest they belong to (--page-manifest)")
    missing, incomplete, other_render, broken = [], [], [], []
    texts: dict[int, str] = {}
    records: dict[int, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    for scan in sorted(marker):
        md_path = inputs.proofread / f"page-{scan:04d}.md"
        json_path = inputs.proofread / f"page-{scan:04d}.json"
        if not md_path.is_file():
            if marker[scan]:
                missing.append(scan)
            continue
        if not json_path.is_file():
            incomplete.append(scan)         # repair_book.py reads every page-NNNN.md it finds
            continue
        md_bytes, json_bytes = md_path.read_bytes(), json_path.read_bytes()
        try:
            record = json.loads(json_bytes.decode("utf-8"))
        except (UnicodeError, ValueError):
            broken.append(f"page {scan}: sealed JSON unreadable")
            continue
        if not isinstance(record, dict) or record.get("status") != "complete":
            incomplete.append(scan)
            continue
        problems = ri.seal_problems(scan, md_bytes, json_bytes)
        if problems:
            broken.extend(problems)
            continue
        if marker[scan] and (record.get("provenance") or {}).get("renderSha256") != render_sha[scan]:
            other_render.append(scan)
            continue
        text = md_bytes.decode("utf-8")
        texts[scan], records[scan] = text, record
        rows.append({
            "scanPage": scan,
            "markdownPath": _relative(md_path, inputs.book),
            "markdownSha256": pp.sha256_bytes(md_bytes),
            "jsonSha256": pp.sha256_bytes(json_bytes),
            "sealChecks": {"canonicalJson": True, "markdownSeal": True, "payloadSeal": True,
                           "renderMatchesPageManifest": True, "statusComplete": True, "scanPage": True},
            "markerExpected": marker[scan],
            "includedInAssembly": marker[scan],
            "excludedText": None if marker[scan] else text,
            "auditorClean": record.get("auditorClean"),
            "doubts": record.get("doubts") or [],
            "needsResearch": record.get("needsResearch") or [],
            "mode": record.get("mode"),
            "generatedAt": record.get("generatedAt"),
            "chars": len(text),
        })
    if broken:
        raise FinishError(EXIT_USAGE, "sealed pages fail their seals (edited after sealing?): "
                                      + "; ".join(broken[:10]) + (f"; and {len(broken) - 10} more" if len(broken) > 10
                                                                  else ""))
    not_ready = sorted(set(missing + incomplete + other_render))
    if not_ready:
        parts = []
        if missing:
            parts.append(f"not sealed: {_compress(missing)}")
        if incomplete:
            parts.append(f"not complete: {_compress(incomplete)}")
        if other_render:
            parts.append(f"sealed on another render than the manifest's: {_compress(other_render)}")
        raise FinishError(EXIT_NOT_READY, f"{len(not_ready)} of {manifest.expected_scan_pages} pages are not ready "
                                          f"({'; '.join(parts)}) - run proofread_pages.py on them first "
                                          "(--overwrite for pages sealed on another render)")
    # The drafts phase 3 read: engine A's text is sealed in each page's
    # provenance (draftSha256).  Other drafts would repair against the wrong
    # readings; said, not refused (a draft rewritten byte for byte elsewhere
    # still matches).
    checked = [scan for scan in sorted(records) if (records[scan].get("provenance") or {}).get("draftSha256")][:5]
    differing = []
    for scan in checked:
        try:
            if pp.sha256_file(inputs.ocr_a / f"page-{scan:04d}.txt") != records[scan]["provenance"]["draftSha256"]:
                differing.append(scan)
        except OSError:
            differing.append(scan)
    if checked and len(differing) == len(checked):
        log.warning(f"engine A's drafts in {inputs.ocr_a} are not the ones phase 3 sealed pages "
                    f"{_compress(differing)} against (draftSha256) - name the right folder with --ocr-a")
        inputs.notes.append(f"engine A's drafts differ from the sealed pages' draftSha256 ({inputs.ocr_a})")
    return Sealed(manifest_bytes, manifest.expected_scan_pages, marker, texts, records, rows,
                  source_pdf if isinstance(source_pdf, str) else None)


def _relative(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path.resolve())


# --- step 1: the assembly -----------------------------------------------------------------------

def segment_text(sealed: Sealed) -> str:
    """The annotated book as one segment: each marker page as a canonical
    `<!-- page_NNN -->` line, a blank line, the sealed text as sealed but for
    its outer whitespace, and a blank line (the frame repair_book.py builds
    and reads back)."""
    order = sealed.marker_pages()
    parts = [f"<!-- page_{scan:03d} -->\n\n{sealed.texts[scan].strip()}\n\n" for scan in order]
    text = "".join(parts)
    return text[:-1] if text.endswith("\n\n") else text


def write_assembly_inputs(folder: Path, sealed: Sealed, book: Path) -> dict[str, Any]:
    """What assemble_ocr_segments.py assembles, written into FOLDER (which
    must not exist): segments/ (the whole book as one segment), a byte copy of
    the page manifest, ordered-segments.json and page-sources.json (every
    sealed page with its hashes, the checks it passed, whether it is in the
    assembly, and its doubts).  Returns the ordered segment manifest."""
    import proofread_pages as pp

    (folder / "segments").mkdir(parents=True)
    (folder / "page-manifest.json").write_bytes(sealed.manifest_bytes)
    body = segment_text(sealed).encode("utf-8")
    relative = SEGMENT_NAME.format(start=1, end=sealed.expected)
    (folder / relative).write_bytes(body)
    ordered = {
        "schema_version": 1,
        "separator_utf8": "\n",
        "scan_start": 1,
        "scan_end": sealed.expected,
        "page_manifest": {"path": "page-manifest.json", "sha256": pp.sha256_bytes(sealed.manifest_bytes)},
        "segments": [{"path": relative, "sha256": pp.sha256_bytes(body), "scan_start": 1,
                      "scan_end": sealed.expected}],
    }
    (folder / "ordered-segments.json").write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n",
                                                  encoding="utf-8")
    sources = {"tool": TOOL, "schemaVersion": 1, "book": str(book), "pages": sealed.rows}
    (folder / "page-sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2) + "\n",
                                              encoding="utf-8")
    return ordered


def assembly_problems(folder: Path, sealed: Sealed, log: "Log") -> list[str]:
    """Why the assembly in FOLDER is not the sealed pages' (empty: it is):
    its page manifest copy, its page list's hashes, a replay of its segments
    against combined-annotated.md, and each assembled page's text."""
    import _repair_inputs as ri

    problems = []
    try:
        if (folder / "page-manifest.json").read_bytes() != sealed.manifest_bytes:
            problems.append("its page manifest is not the book's")
        listed = json.loads((folder / "page-sources.json").read_text(encoding="utf-8"))
        rows = {row.get("scanPage"): row for row in listed.get("pages") or [] if isinstance(row, dict)}
    except (OSError, ValueError, AttributeError) as error:
        return [f"unreadable: {error}"]
    current = {row["scanPage"]: row for row in sealed.rows}
    if sorted(rows) != sorted(current):
        problems.append("its page list is not the sealed pages")
    changed = [scan for scan, row in current.items() if scan in rows and any(
        rows[scan].get(key) != row[key] for key in ("markdownSha256", "jsonSha256", "markerExpected"))]
    if changed:
        problems.append(f"pages sealed again since: {_compress(changed)}")
    if problems:
        return problems
    code, said = _call(log, _module("assemble_ocr_segments").main,
                       [str(folder / "ordered-segments.json"), "--output", str(folder / "combined-annotated.md")])
    if code != 0:
        return [f"its segments do not replay to combined-annotated.md: {said}"]
    try:
        assembly = ri.parse_assembly((folder / "combined-annotated.md").read_text(encoding="utf-8"))
    except (OSError, ri.InputError) as error:
        return [f"combined-annotated.md: {error}"]
    if assembly.order != sealed.marker_pages():
        return ["its page markers are not the marker pages"]
    differing = [scan for scan in assembly.order if assembly.bodies[scan] != sealed.texts[scan].strip()]
    if differing:
        return [f"assembled text differs from the sealed page on pages {_compress(differing)}"]
    return []


def assemble(book: Path, sealed: Sealed, log: "Log") -> dict[str, Any]:
    folder = book / ASSEMBLED
    if folder.exists():
        problems = assembly_problems(folder, sealed, log)
        if not problems:
            return {"status": "kept", "why": "the assembly matches the sealed pages"}
        stamp = _dt.datetime.now().strftime('%Y%m%dT%H%M%S')
        aside = book / f"{ASSEMBLED}.stale-{stamp}"
        number = 1
        while aside.exists():
            number += 1
            aside = book / f"{ASSEMBLED}.stale-{stamp}-{number}"
        folder.rename(aside)
        log.line(f"the assembly is stale ({'; '.join(problems)}): moved to {aside.name}")
    partial = book / PARTIAL
    if partial.exists():
        shutil.rmtree(partial)
    write_assembly_inputs(partial, sealed, book)
    code, said = _call(log, _module("assemble_ocr_segments").main,
                       [str(partial / "ordered-segments.json"), "--output", str(partial / "combined-annotated.md"),
                        "--write", "--receipt", str(partial / "segment-assembly-receipt.json")])
    if code != 0:
        raise FinishError(EXIT_FAILED, f"assemble_ocr_segments.py exit {code}: {said}")
    problems = assembly_problems(partial, sealed, log)
    if problems:
        raise FinishError(EXIT_FAILED, f"the new assembly does not verify: {'; '.join(problems)}")
    partial.rename(folder)
    return {"status": "written", "pages": len(sealed.marker_pages())}


# --- step 2: the repair -----------------------------------------------------------------------

def repair_argv(book: Path, inputs: Inputs, arguments: argparse.Namespace, resume: bool) -> list[str]:
    assembled = book / ASSEMBLED
    argv = [str(book), "--output", str(book / REPAIRED),
            "--assembled", str(assembled / "combined-annotated.md"),
            "--page-sources", str(assembled / "page-sources.json"),
            "--page-manifest", str(assembled / "page-manifest.json"),
            "--proofread", str(inputs.proofread), "--renders", str(inputs.renders),
            "--ocr-a", str(inputs.ocr_a), "--ocr-b", str(inputs.ocr_b),
            "--workers", str(max(1, arguments.workers))]
    if inputs.profile is not None:
        argv += ["--profile", str(inputs.profile)]
    if arguments.no_model:
        argv.append("--no-model")
    for name in ("endpoint", "model", "max_inflight", "timeout"):
        value = getattr(arguments, name)
        if value is not None:
            argv += [f"--{name.replace('_', '-')}", str(value)]
    if resume:
        argv.append("--resume")
    return argv


def repair_current(book: Path, arguments: argparse.Namespace) -> tuple[bool, str]:
    """Whether BOOK/repaired is a finished repair of the inputs as they are
    now, by this code, with these options (then it is kept)."""
    import proofread_pages as pp
    import repair_book

    folder = book / REPAIRED
    try:
        report = json.loads((folder / "repair-report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False, "no finished repair"
    run = report.get("arguments") or {}
    if report.get("status") != "finished" or report.get("exitStatus") != 0:
        return False, f"the last repair did not finish (status {report.get('status')}, exit {report.get('exitStatus')})"
    if run.get("pages") or run.get("planOnly") or run.get("off") or bool(run.get("noModel")) != arguments.no_model:
        return False, "the last repair ran with other options"
    if (report.get("code") or {}).get("sha256") != repair_book.code_identity()["sha256"]:
        return False, "the repair code changed since"
    for path, digest in ((report.get("inputs") or {}).get("sha256") or {}).items():
        try:
            if pp.sha256_file(Path(path)) != digest:
                return False, f"an input changed since: {path}"
        except OSError:
            return False, f"an input is gone: {path}"
    for name in ("combined-repaired.md", "boundaries.json"):
        try:
            if pp.sha256_file(folder / name) != (report.get("outputs") or {}).get(name):
                return False, f"{name} is not the one the repair wrote"
        except OSError:
            return False, f"no {name}"
    return True, "the repair is current"


REPAIR_EXITS = {2: "its inputs failed verification", 3: "its output folder exists and is not a repair's",
                4: "boundaries.json fails the finalize contract", 5: "its log replay differs from its output",
                6: "the model could not be asked"}


def repair(book: Path, inputs: Inputs, arguments: argparse.Namespace, client: Any,
           log: "Log") -> dict[str, Any]:
    folder = book / REPAIRED
    current, why = repair_current(book, arguments)
    if current:
        return {"status": "kept", "why": why}
    resume = folder.exists()
    if resume:
        log.line(f"the earlier repair is resumed ({why}); answers already given are not asked again")
    import repair_book
    code, said = _call(log, lambda argv: repair_book.main(argv, client=client),
                       repair_argv(book, inputs, arguments, resume))
    if code == EXIT_MODEL:
        answers = _count_lines(folder / "answers.jsonl")
        raise FinishError(EXIT_MODEL, f"the model could not be asked; {answers} answer(s) kept in "
                                      f"{REPAIRED}/answers.jsonl - run the same command again once the server "
                                      "is up (or add --no-model)")
    if code != 0:
        raise FinishError(EXIT_FAILED if code in (4, 5) else EXIT_USAGE,
                          f"repair_book.py exit {code}: {REPAIR_EXITS.get(code, 'failed')} ({said})")
    return {"status": "resumed" if resume else "written"}


def _count_lines(path: Path) -> int:
    try:
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    except OSError:
        return 0


# --- step 3: the final text -------------------------------------------------------------------

def finalize(book: Path, sealed: Sealed, log: "Log") -> dict[str, Any]:
    from _ocr_markdown import find_page_markers, split_lines

    repaired = book / REPAIRED
    finish = book / FINISH_DIR
    temporary = finish / f".{FINAL}.tmp"
    temporary.unlink(missing_ok=True)
    # The pages the manifest leaves out have no marker, on purpose.
    left_out = [scan for scan in sorted(sealed.marker) if not sealed.marker[scan]]
    skip = ["--skip-pages", ",".join(map(str, left_out))] if left_out else []
    code, said = _call(log, _module("finalize_page_markers").main,
                       [str(repaired / "combined-repaired.md"), "--boundary-manifest",
                        str(repaired / "boundaries.json"), "--output", str(temporary), "--write", "--summary-only",
                        *skip])
    if code != 0 or not temporary.is_file():
        raise FinishError(EXIT_FAILED, f"finalize_page_markers.py exit {code}: {said}")
    text = temporary.read_text(encoding="utf-8")
    markers, malformed = find_page_markers(split_lines(text))
    if markers or malformed or "<!-- page_" in text:
        raise FinishError(EXIT_FAILED, f"page markers are left in the final text ({len(markers)} markers, "
                                       f"{len(malformed)} malformed)")
    new = temporary.read_bytes()
    kept = keep_edited(book, FINAL, new, log)
    # Remembered before the move: a stop between the two leaves final.md one
    # of this command's own, never a false "edited" one.
    remember_written(book, FINAL, new)
    changed = _replace_if_changed(temporary, book / FINAL)
    audit = finish / AUDIT_NAME
    audit.unlink(missing_ok=True)       # an earlier run's report must not stand for this one
    code, _ = _call(log, _module("audit_ocr_markdown").main,
                    [str(book / FINAL), "--mode", "final", "--boundary-manifest", str(repaired / "boundaries.json"),
                     "--annotated-source", str(repaired / "combined-repaired.md"), "--summary-only",
                     "--json-report", str(audit)])
    try:
        errors = int(json.loads(audit.read_text(encoding="utf-8"))["counts"]["errors"])
    except (OSError, ValueError, KeyError, TypeError):
        errors = None
        log.warning(f"the final audit wrote no report (exit {code})")
    return {"status": "written" if changed else "unchanged", "characters": len(text), "auditErrors": errors,
            "auditExit": code, **({"keptAs": kept} if kept else {})}


def _replace_if_changed(source: Path, target: Path) -> bool:
    """Move SOURCE onto TARGET unless TARGET already holds the same bytes."""
    if target.is_file() and target.read_bytes() == source.read_bytes():
        source.unlink()
        return False
    os.replace(source, target)
    return True


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def written_before(book: Path) -> dict[str, list[str]]:
    """finish/written.json: for final.md and doubts.md, the SHA-256 of each
    version this command wrote (the last WRITTEN_KEPT)."""
    try:
        data = json.loads((book / FINISH_DIR / WRITTEN_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {name: [s for s in shas if isinstance(s, str)] for name, shas in data.items() if isinstance(shas, list)}


def remember_written(book: Path, name: str, data: bytes) -> None:
    written = written_before(book)
    digest = _sha256(data)
    written[name] = ([s for s in written.get(name, []) if s != digest] + [digest])[-WRITTEN_KEPT:]
    _write_if_changed(book / FINISH_DIR / WRITTEN_NAME, json.dumps(written, indent=1, sort_keys=True) + "\n")


def keep_edited(book: Path, name: str, new: bytes, log: "Log") -> str | None:
    """Before BOOK/NAME is written with NEW: a NAME that holds bytes this
    command did not write there (the user's corrections or ticks after the
    run, or a file it never wrote) is moved aside to <stem>.edited-<time>
    <suffix> beside it, never overwritten.  Returns the copy's name, or None
    when there is nothing to keep."""
    path = book / name
    try:
        current = path.read_bytes()
    except FileNotFoundError:
        return None
    if current == new or _sha256(current) in written_before(book).get(name, []):
        return None
    stem, suffix = os.path.splitext(name)
    stamp = _dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    aside = book / f"{stem}.edited-{stamp}{suffix}"
    number = 1
    while aside.exists():
        number += 1
        aside = book / f"{stem}.edited-{stamp}-{number}{suffix}"
    path.rename(aside)
    log.warning(f"{name} was not the one {TOOL} last wrote (edited after the run, or not its own): kept as "
                f"{aside.name}; the new {name} does not hold those changes")
    return aside.name


# --- step 4: the doubt list ------------------------------------------------------------------

@dataclass
class Item:
    section: str
    kind: str
    page: int | None
    detail: str
    source: str
    noise: bool = False
    # The detail as its step wrote it, before _clip: what band_noise reads
    # (a doubt of several spots can name body text past the clipped part).
    full: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"section": self.section, "kind": self.kind, "page": self.page, "detail": self.detail,
                "source": self.source, "noise": self.noise}


# The sections of doubts.md, in order: what most likely changes the text
# first (the research queue, then the characters), then the marks, the
# structure, the tables, the format; the running head's and the folios'
# noise folded last.
SECTIONS = (
    ("research", "要查資料嘅專名"),
    ("text", "字：最可能要改"),
    ("marks", "標點"),
    ("structure", "分頁、標題同目錄"),
    ("tables", "表格同圖"),
    ("format", "格式同步驟"),
    ("noise", "書眉、頁碼嘅雜訊（摺埋）"),
)
# Each kind: its section and what it means, in a few words - in each
# section in the order doubts.md lists them, what most likely changes the
# text first (a character both engines read and the text lost before a
# character only one engine read; a model's answer the guards refused before
# a phase-3 reading kept).
KINDS: dict[str, tuple[str, str]] = {
    # the research queue
    "research-front-matter": ("research", "題名頁、題字頁嘅專名（題字者、書名、印章）"),
    "research-glyph": ("research", "淨靠字形定唔到嘅專名（人名、地名、官職）"),
    # characters
    "TEXT-LOST": ("text", "兩個引擎都讀到嘅字唔見咗"),
    "table-characters-lost": ("text", "表格有兩個引擎都讀到嘅字唔見咗"),
    "reading-dropped": ("text", "一個引擎讀到嘅幾個字喺輸出冇咗"),
    "look-refused": ("text", "問咗模型，答案過唔到檢查，冇改"),
    "look-not-asked": ("text", "有問題冇問模型（--no-model，或者切唔到裁圖）"),
    "verify-disagrees": ("text", "抽查：模型讀到嘅同機械改動唔一樣"),
    "conflict": ("text", "兩個改動撞埋同一段字，淨係做咗先嗰個"),
    "MARK-STANDIN": ("text", "可能係引擎 B 代標點嘅字"),
    "MARK-FIGURE-LOST": ("text", "引擎 A 讀到嘅數字唔見咗"),
    "arabic-figure-unwritten": ("text", "引擎 A 讀到嘅數字定咗要寫，但寫唔落佢個位"),
    "HEAD-NUMBER-LOST": ("text", "標題冇咗編號"),
    "TOC-NUMBER-LOST": ("text", "目錄項冇編號"),
    "FURN-HEAD": ("text", "可能仲有書眉留喺正文"),
    "FURN-SUFFIX": ("text", "可能仲有卷次後綴留喺正文"),
    "FURN-FOLIO": ("text", "可能仲有頁碼留喺正文"),
    "FURN-ANSWER": ("text", "書眉位嘅裁決答案"),
    "HEAD-FURNITURE": ("text", "標題其實係書眉或者頁碼"),
    "ANSWER-PROSE": ("text", "裁決答案似係一段話"),
    "nothing-unconfirmed": ("text", "裁決話冇字，但證實唔到，留咗引擎讀到嘅字"),
    "insertion-unjudged": ("text", "一兩個字淨係一個引擎讀到，冇裁決，留咗"),
    "insertion-partial": ("text", "裁決讀到嘅字少過引擎讀到嘅，留咗引擎讀法"),
    "deletion-refused": ("text", "裁決嘅答案會刪走幾個引擎讀到嘅字，冇收，留咗引擎讀法"),
    "neighbour-copy": ("text", "裁決嘅答案似係抄咗隔籬嘅字，冇收，留咗引擎讀法"),
    "extra-copy": ("text", "一段字可能放多咗一次"),
    "moved-placed-once": ("text", "兩個引擎喺唔同位置讀到嘅同一段字，淨係放咗一次"),
    "unsupported-reading": ("text", "一段淨係一個引擎讀到、自己重複嘅字丟咗"),
    "engine-a-loop-dropped": ("text", "引擎 A 一段讀法係循環，嗰度淨係用咗引擎 B"),
    "sealed-report": ("text", "舊版封存嘅頁，有未分類嘅疑問"),
    # marks
    "punctuation-partial": ("marks", "標點可能漏咗"),
    "punctuation-count-mismatch": ("marks", "標點數目同頁上數到嘅唔一致"),
    "doubled-count-mismatch": ("marks", "雙圈數目同頁上數到嘅唔一致"),
    "punctuation-unread": ("marks", "有幾個字之間嘅標點冇讀過"),
    "punctuation-left-bare": ("marks", "頁上有標點，但嗰段一個都冇加"),
    "punctuation-whole-page": ("marks", "成頁一次過加標點，冇逐段核對"),
    "MARK-UNBALANCED": ("marks", "括號或者引號唔成對"),
    "MARK-REVERSED": ("marks", "倒轉咗嘅括號「）（」"),
    "MARK-SHAPE": ("marks", "括號形狀可疑"),
    # structure
    "unit-not-in-scan": ("structure", "目錄有、正文搵唔到嘅篇"),
    "leaves-missing": ("structure", "頁碼跳咗，可能漏咗頁"),
    "HEAD-FRAGMENT": ("structure", "頁頂標題可能係上一頁未完嘅句"),
    "TOC-UNMATCHED": ("structure", "目錄項喺正文搵唔到"),
    "boundary-unverified": ("structure", "分頁位冇定案，當另起一段"),
    "heading-kind-unknown": ("structure", "認唔到係乜嘅標題，級數照舊"),
    "JOIN-UNRESOLVED": ("structure", "分頁位冇 label"),
    # tables and charts
    "table-marks-unread": ("tables", "表入面印咗嘅符號冇讀過"),
    "table-missing": ("tables", "表格唔見咗"),
    "table-disputed": ("tables", "表格版面有爭議"),
    "table-text-left-out": ("tables", "表格有字冇寫入"),
    "table-edge-text": ("tables", "表前後嘅字（可能係標題、附註，或者讀多咗）"),
    "table-grid-followed": ("tables", "兩個引擎嘅表格格仔唔對行，跟咗其中一個"),
    "table-grids-misaligned": ("tables", "兩個引擎嘅表格格仔唔對行，定唔到跟邊個"),
    "table-unread-confirmed": ("tables", "表入面有兩個引擎都冇讀到、淨係裁決讀到嘅字"),
    "table-orientation-undecided": ("tables", "表嘅方向定唔到"),
    "table-rebuild-refused": ("tables", "表重建唔收"),
    "table-rebuilt-unvouched": ("tables", "重建嘅表冇第二個讀法證實"),
    "cell-direction-undecided": ("tables", "表格一格字嘅讀向定唔到"),
    "table-continuation-merged": ("tables", "跨頁表併咗做一張（接口要核）"),
    "table-continuation-undecided": ("tables", "似係跨頁表，但定唔到係咪同一張，冇併"),
    "table-continuation-unaligned": ("tables", "跨頁表欄數唔同、對唔到格，冇併"),
    "table-continuation-cell-joined": ("tables", "被頁切斷嘅一格字駁返埋"),
    "table-continuation-blocked": ("tables", "跨頁表接唔到（其中一頁冇寫成表）"),
    "chart-lost": ("tables", "分類圖可能漏咗名目或者註"),
    "chart-refused": ("tables", "似係分類圖，但讀唔到"),
    "chart-withdrawn": ("tables", "分類圖讀咗但收返，照舊做法"),
    "chart-unwitnessed": ("tables", "分類圖有字淨係模型讀到"),
    "chart-degenerate": ("tables", "分類圖自己重複"),
    "chart-uncertain": ("tables", "分類圖有模型自己話存疑嘅位"),
    "chart-position-unknown": ("tables", "分類圖擺咗喺頁尾（原位搵唔返）"),
    "chart-review": ("tables", "分類圖要人覆核"),
    # format and the steps' own
    "formatter-rejected": ("format", "格式化步驟被拒，嗰頁用咗退返嘅版本"),
    "structure-rejected": ("format", "結構步驟被拒，嗰頁用咗退返嘅版本"),
    "final-audit": ("format", "final.md 結構檢查錯誤"),
    "AUDIT-ANNOTATED": ("format", "拼書稿結構檢查錯誤"),
    "gate-failed": ("format", "本書量唔到，一類修書規則冇做"),
    "detector-unmatched": ("format", "自動檢查見到問題，但冇規則處理到"),
}
# Counters that are said elsewhere, or only report a distribution.
COUNTERS_LEFT_OUT = {"JOIN-UNVERIFIED", "HEAD-LEVELS", "PARA-DISAGREE", "AUDIT-FINAL"}
# What the running head's band may hold besides its stems and suffixes: the
# folio's numerals (a zero read as a square).
BAND_NUMERALS = frozenset("〇一二三四五六七八九十百廿卅口")


@dataclass
class Band:
    """The running head as the repair's book model measured it: its stems,
    its run suffixes, and each page's folio - what a doubt's flagged text
    is when it is only noise."""
    stems: list[str] = field(default_factory=list)
    suffixes: list[str] = field(default_factory=list)
    folios: dict[int, int] = field(default_factory=dict)

    @classmethod
    def of(cls, book: Path) -> "Band":
        try:
            model = json.loads((book / REPAIRED / "book-model.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        folios = {}
        for key, entry in (model.get("pages") or {}).items():
            if isinstance(entry, dict) and isinstance(entry.get("folio"), int):
                folios[int(key)] = entry["folio"]
        return cls(stems=[s for s in model.get("stems") or [] if isinstance(s, str)],
                   suffixes=sorted({r.get("suffix") for r in model.get("suffixRuns") or [] if r.get("suffix")}),
                   folios=folios)

    def holds(self, text: str, page: int | None) -> bool:
        """Whether TEXT is the band's: copies of a stem (the model's
        positional match), run suffixes and numerals - with a stem copy or
        a suffix among them, or the numerals the page's folio."""
        import _repair_model as rm
        rest = _cjk(text)
        if not rest:
            return False
        found = False
        for stem in self.stems:
            for a, b in reversed(rm.stem_matches(rest, stem)):
                rest = rest[:a] + rest[b:]
                found = True
        for suffix in sorted(self.suffixes, key=len, reverse=True):
            if suffix in rest:
                rest = rest.replace(suffix, "")
                found = True
        if not all(c in BAND_NUMERALS for c in rest):
            return False
        if found:
            return True
        folio = self.folios.get(page) if page is not None else None
        return folio is not None and rm.numeral_value(rest.replace("口", "〇")) == folio

    def inside_stem(self, before: str, spot: str, after: str) -> bool:
        """Whether SPOT, between BEFORE and AFTER, lies inside a copy of a
        stem (an answer read at a character of the running head)."""
        import _repair_model as rm
        before, spot, after = _cjk(before), _cjk(spot) or "？", _cjk(after)
        probe = before + spot + after
        lo, hi = len(before), len(before) + len(spot)
        return any(a <= lo and hi <= b for stem in self.stems for a, b in rm.stem_matches(probe, stem))


# Where a doubt's detail names the text it is about (the forms the runner
# and the repair write).
FLAGGED = {
    "moved-placed-once": re.compile(r"PLACED ONCE: (\S+?) \("),
    "extra-copy": re.compile(r"(?:READ IT: |\| )(\S+?) \("),
    "deletion-refused": re.compile(r"\[A (.*?) / B (.*?)\]"),
    "structure-rejected": re.compile(r"deleted \d+ characters \(([^)…]*)|still deleted (\S+)"),
    "formatter-rejected": re.compile(r"deleted \d+ characters \(([^)…]*)|still deleted (\S+)"),
}
RESEARCH_SPOT = re.compile(r"「…(.*?)［？］(.*?)…」：引擎讀「(.*?)」／「(.*?)」")


def band_noise(item: Item, band: Band) -> bool:
    """Whether ITEM is the running head's noise: the text it flags is the
    band's (a head copy, a suffix, the page's folio - read into the body
    and settled by the repair's furniture rules, or never the body's), or,
    for a proper name, its place lies inside a copy of the head or both
    engines' readings there are the band's.  Evidence, not the kind: a
    reading-kept doubt about body text is never noise.  Read on the detail
    as its step wrote it, not the clipped one doubts.md shows: a doubt of
    several spots is noise only when every spot is."""
    detail = " ".join((item.full or item.detail).split())
    if item.kind == "research-glyph":
        found = RESEARCH_SPOT.search(detail)
        if not found:
            return False
        before, after, a, b = found.groups()
        readings = [r for r in (a, b) if _cjk(r)]
        return band.inside_stem(before, a or b, after) or (bool(readings) and all(band.holds(r, item.page)
                                                                                 for r in readings))
    pattern = FLAGGED.get(item.kind)
    if pattern is None:
        return False
    texts = [t for match in pattern.finditer(detail) for t in match.groups() if t and t.strip() != "-"]
    return bool(texts) and all(band.holds(t, item.page) for t in texts)


def _clip(text: str, size: int = DETAIL_CHARS) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= size else text[:size - 1] + "…"


IMAGE_NAME = re.compile(r"[^\s()（）\[\]'\"`,;]*\.(?:png|jpe?g|webp|tiff?)\b", re.I)


def _no_images(text: str) -> str:
    """TEXT with every image file name said as 裁圖: doubts.md names no image
    (finish/doubts.json keeps the detail as written)."""
    return IMAGE_NAME.sub("裁圖", text)


def _cjk(text: str) -> str:
    import proofread_pages as pp
    return pp.CJK(text)


def research_items(scan: int, record: Mapping[str, Any], final_cjk: str) -> list[Item]:
    items = []
    for flag in record.get("needsResearch") or []:
        if not isinstance(flag, dict):
            continue
        items.append(Item("research", "research-front-matter", scan,
                          _clip(f"「{flag.get('text', '')}」：{flag.get('why', '')}"), "phase3"))
    for a in record.get("adjudications") or []:
        if not isinstance(a, dict) or not a.get("needs_research"):
            continue
        before, after = a.get("context_before") or "", a.get("context_after") or ""
        resolved = a.get("resolved") or ""
        probe = _cjk(before)[-3:] + _cjk(resolved) + _cjk(after)[:3]
        gone = "；final.md 搵唔返呢段上下文（可能已經當書眉或者頁碼刪咗）" if probe and probe not in final_cjk else ""
        detail = (f"「…{before}［？］{after}…」：引擎讀「{a.get('draft_reading', '')}」／"
                  f"「{a.get('writer_reading', '')}」，流程寫咗「{resolved}」{gone}")
        items.append(Item("research", "research-glyph", scan, _clip(detail), "phase3", full=detail))
    return items


def collect_items(book: Path, sealed: Sealed) -> list[Item]:
    """Every doubt the pipeline left, research first, by page."""
    final_cjk = _cjk((book / FINAL).read_text(encoding="utf-8")) if (book / FINAL).is_file() else ""
    items: list[Item] = []
    for scan in sorted(sealed.records):
        record = sealed.records[scan]
        if not sealed.marker.get(scan, True):
            continue
        items.extend(research_items(scan, record, final_cjk))
        for doubt in record.get("doubts") or []:
            if not isinstance(doubt, dict):
                continue
            kind = str(doubt.get("kind") or "sealed-report")
            detail = str(doubt.get("detail", ""))
            items.append(Item(KINDS.get(kind, ("text", ""))[0], kind, scan, _clip(detail), "phase3", full=detail))
    repaired = book / REPAIRED
    try:
        doubts = json.loads((repaired / "doubts.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doubts = []
    for doubt in doubts if isinstance(doubts, list) else []:
        kind = str(doubt.get("kind"))
        detail = str(doubt.get("detail", ""))
        items.append(Item(KINDS.get(kind, ("format", ""))[0], kind, doubt.get("page"), _clip(detail), "repair",
                          full=detail))
    try:
        after = (json.loads((repaired / "lint.json").read_text(encoding="utf-8")).get("after") or {})
    except (OSError, ValueError, AttributeError):
        after = {}
    for name, hits in sorted((after.get("hits") or {}).items()):
        counter = (after.get("counters") or {}).get(name) or {}
        if name in COUNTERS_LEFT_OUT or counter.get("reportOnly") or not counter.get("count"):
            continue
        for hit in hits:
            text = hit.get("text") or hit.get("code") or ""
            items.append(Item(KINDS.get(name, ("format", ""))[0], name, hit.get("page"), _clip(text), "lint"))
    try:
        audit = json.loads((book / FINISH_DIR / AUDIT_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        audit = {}
    for error in audit.get("errors") or []:
        items.append(Item("format", "final-audit", None,
                          _clip(f"final.md 第 {error.get('line')} 行：{error.get('code')} {error.get('token') or ''}"),
                          "audit"))
    band = Band.of(book)
    for item in items:
        if band_noise(item, band):
            item.section, item.noise = "noise", True
    return items


def doubts_markdown(book: Path, sealed: Sealed, items: Sequence[Item]) -> str:
    """doubts.md: what the pipeline could not settle, for the person who reads
    the book against the PDF - what most likely changes the text first: a
    count of every kind, then by section and kind (SECTIONS, KINDS: in
    their order), with scan page numbers, at most SHOWN_PER_KIND lines of
    detail a kind, the rest by page; the running head's and the folios'
    noise (band_noise) folded last, counted by kind and page, no detail."""
    title = Path(sealed.source_pdf).stem if sealed.source_pdf else book.name
    pages_in = sealed.marker_pages()
    left_out = [scan for scan in sorted(sealed.marker) if not sealed.marker[scan]]
    with_pages = sorted({item.page for item in items if item.page is not None})
    order = {kind: n for n, kind in enumerate(KINDS)}

    def ranked(chosen: Sequence[Item]) -> list[str]:
        return sorted(dict.fromkeys(item.kind for item in chosen), key=lambda k: (order.get(k, len(order)), k))
    noise = [item for item in items if item.noise]
    out = [f"# 疑問清單：{title}", "",
           "呢份係 `final.md` 嘅疑問清單，由 `finish_book.py` 寫。頁碼係掃描頁，即係 PDF 第幾頁。",
           "",
           "冇人逐頁睇過 PDF：字由兩個 OCR 引擎讀、本機模型對住裁圖定；下面係流程自己定唔到、要人對住原書核嘅位。"
           "冇列出嚟嘅字唔代表一定啱（兩個引擎一齊讀錯嘅位冇任何訊號）。",
           "",
           "次序：最可能要改字嘅排先（要查資料嘅專名、字），跟住係標點、分頁同標題、表格、格式；"
           "每一段入面，最可能改到字嘅類排先。疑問講緊嘅字其實係書眉、卷次或者頁碼（修書已經當書眉處理，或者唔係正文）嘅，"
           "摺埋喺最尾，淨係寫數目同頁碼。",
           "",
           f"- 入書 {len(pages_in)} 頁（PDF 共 {sealed.expected} 頁）；疑問 {len(items)} 項，喺 {len(with_pages)} 頁"
           + (f"；其中 {len(noise)} 項係書眉、頁碼嘅雜訊，摺埋。" if noise else "。")]
    if left_out:
        out.append(f"- 冇入書嘅頁（page manifest 標咗唔要，例如空白頁、重複掃描）：第 {_pages(left_out)} 頁。")
    if not items:
        out += ["", "流程冇留低疑問。"]
        return "\n".join(out) + "\n"
    # Every kind with its count, in the list's order.
    out += ["", "## 每類幾多項", "", "| 段 | 類 | 項 | 頁 |", "|---|---|---|---|"]
    for section, heading in SECTIONS:
        chosen = [item for item in items if item.section == section]
        for kind in ranked(chosen):
            group = [item for item in chosen if item.kind == kind]
            pages = {item.page for item in group if item.page is not None}
            label = KINDS.get(kind, ("", ""))[1] or kind
            out.append(f"| {heading} | {label} | {len(group)} | {len(pages)} |")
    for section, heading in SECTIONS:
        chosen = [item for item in items if item.section == section]
        if not chosen:
            continue
        out += ["", f"## {heading}（{len(chosen)} 項）"]
        if section == "noise":
            out += ["", "疑問講緊嘅字（引擎讀法、搬咗位或者刪咗嘅字）全部係書眉嘅主幹、卷次或者頁碼數字，"
                    "或者個位喺書眉副本入面：唔影響正文，照類同頁碼列，詳情見 "
                    f"`{FINISH_DIR}/{DOUBTS_JSON}`。", ""]
            for kind in ranked(chosen):
                group = [item for item in chosen if item.kind == kind]
                pages = sorted({item.page for item in group if item.page is not None})
                where = f"，第 {_pages(pages)} 頁" if pages else ""
                out.append(f"- {KINDS.get(kind, ('', ''))[1] or kind}：{len(group)} 項{where}")
            continue
        for kind in ranked(chosen):
            group = [item for item in chosen if item.kind == kind]
            label = KINDS.get(kind, ("", ""))[1] or kind
            pages = sorted({item.page for item in group if item.page is not None})
            where = f"，第 {_pages(pages)} 頁" if pages else ""
            out += ["", f"### {label}（{len(group)} 項{where}）", ""]
            for item in group[:SHOWN_PER_KIND]:
                page = f"第 {item.page} 頁：" if item.page is not None else ""
                out.append(f"- {page}{_no_images(item.detail)}")
            if len(group) > SHOWN_PER_KIND:
                rest = sorted({item.page for item in group[SHOWN_PER_KIND:] if item.page is not None})
                on = f"，第 {_pages(rest)} 頁" if rest else ""
                out.append(f"- 仲有 {len(group) - SHOWN_PER_KIND} 項{on}（全部見 `{FINISH_DIR}/{DOUBTS_JSON}`）")
    return "\n".join(out) + "\n"


def write_doubts(book: Path, sealed: Sealed, log: "Log") -> dict[str, Any]:
    items = collect_items(book, sealed)
    finish = book / FINISH_DIR
    data = json.dumps([item.as_dict() for item in items], ensure_ascii=False, indent=1) + "\n"
    _write_if_changed(finish / DOUBTS_JSON, data)
    text = doubts_markdown(book, sealed, items)
    kept = keep_edited(book, DOUBTS, text.encode("utf-8"), log)
    remember_written(book, DOUBTS, text.encode("utf-8"))
    _write_if_changed(book / DOUBTS, text)
    pages = sorted({item.page for item in items if item.page is not None})
    return {"items": len(items), "pages": len(pages), "noise": sum(1 for i in items if i.noise),
            "bySection": {section: sum(1 for i in items if i.section == section) for section, _ in SECTIONS},
            **({"keptAs": kept} if kept else {})}


def _write_if_changed(path: Path, text: str) -> None:
    data = text.encode("utf-8")
    if path.is_file() and path.read_bytes() == data:
        return
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


# --- running the tools quietly ---------------------------------------------------------------

def _module(name: str) -> Any:
    import importlib
    return importlib.import_module(name)


class Log:
    """The book's log (finish/finish-book.log): the progress lines and every
    tool's output."""

    def __init__(self, handle: Any):
        self.handle = handle
        self.warnings = 0

    def line(self, text: str) -> None:
        self.handle.write(f"[finish] {text}\n")
        self.handle.flush()

    def warning(self, text: str) -> None:
        """A `WARNING ...` line as the tools write theirs, which
        wait_for_run.py shows (a `[finish] ` prefix would hide it); counted
        for the RESULT line."""
        self.warnings += 1
        self.handle.write(f"WARNING {text}\n")
        self.handle.flush()


def _call(log: Log, main: Callable[[list[str]], int], argv: list[str]) -> tuple[int, str]:
    """A tool's main() with ARGV, what it prints into the log; its exit code
    and the last line it printed."""
    import io
    kept = io.StringIO()

    class Tee(io.TextIOBase):
        def write(self, text: str) -> int:
            kept.write(text)
            log.handle.write(text)
            return len(text)

        def flush(self) -> None:
            log.handle.flush()
    tee = Tee()
    try:
        with contextlib.redirect_stdout(tee), contextlib.redirect_stderr(tee):
            code = main(argv)
    except SystemExit as exit_:
        code = exit_.code if isinstance(exit_.code, int) else 1
    log.handle.flush()
    lines = [line.strip() for line in kept.getvalue().splitlines() if line.strip()]
    return int(code or 0), _clip(lines[-1] if lines else "", 300)


@contextlib.contextmanager
def logging_to(path: Path) -> Iterator[tuple[Log, Any]]:
    """The log at PATH (appended), and where the RESULT line goes.  While the
    steps run, fd 1 and 2 - what the tools' own child processes print - go to
    the log too, and the RESULT line goes to the stdout this command was given
    (sys.stdout itself when that is no file, as in the offline checks).  When
    stdout already is PATH, nothing is moved."""
    sys.stdout.flush()
    sys.stderr.flush()
    handle = open(path, "a", encoding="utf-8")
    try:
        backed = sys.stdout.fileno() == 1
    except (AttributeError, OSError, ValueError):
        backed = False
    try:
        same = os.path.sameopenfile(1, handle.fileno())
    except OSError:
        same = False
    if same:
        try:
            yield Log(handle), sys.stdout
        finally:
            handle.close()
        return
    saved = os.dup(1), os.dup(2)
    result = os.fdopen(os.dup(saved[0]), "w", encoding="utf-8", buffering=1) if backed else sys.stdout
    os.dup2(handle.fileno(), 1)
    os.dup2(handle.fileno(), 2)
    try:
        yield Log(handle), result
    finally:
        with contextlib.suppress(Exception):
            sys.stdout.flush()
            sys.stderr.flush()
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        os.close(saved[0])
        os.close(saved[1])
        handle.close()
        if result is not sys.stdout:
            result.close()


@contextlib.contextmanager
def stop_on_signals() -> Iterator[None]:
    def stop(signum: int, _frame: Any) -> None:
        raise Stopped(signal.Signals(signum).name)
    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


@contextlib.contextmanager
def book_lock(folder: Path) -> Iterator[None]:
    """One finish_book.py at a time on a book.  Taken before anything is
    written into FOLDER: a refused run leaves the running one's log (where
    the wait reads its step) and report alone."""
    handle = open(folder / LOCK_NAME, "a")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        handle.close()
        raise FinishError(EXIT_USAGE, "another finish_book.py runs on this book - wait for it with "
                                      "wait_for_run.py, do not start another") from error
    try:
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


# --- the command -------------------------------------------------------------------------------

def main(argv: Sequence[str] | None = None, client: Any | None = None) -> int:
    """The command line; CLIENT stands in for phase 3's Client in the repair
    (the offline checks' stand-in model)."""
    arguments = build_parser().parse_args(argv)
    book = Path(os.path.realpath(os.path.expanduser(str(arguments.book))))
    if not book.is_dir():
        print(f"{RESULT_PREFIX} exit={EXIT_USAGE} FAILED {TOOL}: {book} is not a folder", flush=True)
        return EXIT_USAGE
    finish = book / FINISH_DIR
    finish.mkdir(exist_ok=True)
    lock = contextlib.ExitStack()
    try:
        lock.enter_context(book_lock(finish))
    except FinishError as error:
        print(f"{RESULT_PREFIX} exit={error.code} {STATE[error.code]} {TOOL}: {error}", flush=True)
        return error.code
    started = time.monotonic()
    report: dict[str, Any] = {"tool": TOOL, "schemaVersion": 1, "book": str(book), "startedAt": _now(),
                              "arguments": {"noModel": arguments.no_model}, "steps": {}}
    code, line, outputs = EXIT_DONE, "", []
    with lock, logging_to(finish / LOG_NAME) as (log, result_stream):
        log.line(f"{_now()} {TOOL} {' '.join(str(a) for a in (argv if argv is not None else sys.argv[1:]))}")
        try:
            with stop_on_signals():
                code, line, outputs = run(book, arguments, client, report, log)
        except FinishError as error:
            code, line = error.code, str(error)
        except Stopped as error:
            code, line = EXIT_STOPPED, f"stopped by {error} - run the same command again; nothing done is lost"
        except Exception as error:  # noqa: BLE001 - one line for the agent, the traceback in the log
            import traceback
            traceback.print_exc(file=log.handle)
            code, line = EXIT_FAILED, f"crashed: {type(error).__name__}: {_clip(str(error), 160)}"
        if code == EXIT_FAILED:
            line += f" - read {finish / LOG_NAME}"
        if log.warnings:
            line += f"; {log.warnings} WARNING line(s): grep -n WARNING {finish / LOG_NAME}"
        report.update(exitStatus=code, result=line, seconds=round(time.monotonic() - started, 1), finishedAt=_now())
        with contextlib.suppress(OSError):
            _write_if_changed(finish / REPORT_NAME, json.dumps(report, ensure_ascii=False, indent=1) + "\n")
        result = f"{RESULT_PREFIX} exit={code} {STATE.get(code, 'FAILED')} {TOOL}: {line}"
        log.line(result[len("[finish] "):])
        print(result, file=result_stream, flush=True)
        for output in outputs:
            print(output, file=result_stream, flush=True)
    return code


def run(book: Path, arguments: argparse.Namespace, client: Any, report: dict[str, Any],
        log: Log) -> tuple[int, str, list[str]]:
    inputs = resolve_inputs(book, arguments)
    report["inputs"] = inputs.as_dict()
    log.line(f"inputs: {json.dumps(inputs.as_dict(), ensure_ascii=False)}")
    for note in inputs.notes:
        log.warning(note)

    def step(number: int, key: str, what: str, action: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        log.line(f"step {number} of {STEPS}: {what}")
        mark = time.monotonic()
        result = action()
        result["seconds"] = round(time.monotonic() - mark, 1)
        report["steps"][key] = result
        log.line(f"step {number} of {STEPS} done: {json.dumps(result, ensure_ascii=False)}")
        return result

    sealed = read_sealed(inputs, log)
    step(1, "assemble", "assemble the sealed pages", lambda: assemble(book, sealed, log))
    step(2, "repair", "repair the book (repair_book.py, "
         + ("no model)" if arguments.no_model else "questions to the model)"),
         lambda: repair(book, inputs, arguments, client, log))
    finalized = step(3, "finalize", "final.md without page markers, and its audit", lambda: finalize(book, sealed, log))
    doubts = step(4, "doubts", "the doubt list, doubts.md", lambda: write_doubts(book, sealed, log))
    repair_report = json.loads((book / REPAIRED / "repair-report.json").read_text(encoding="utf-8"))
    counts = repair_report.get("counts") or {}
    questions = sum((counts.get("questions") or {}).values())
    answered = (counts.get("questionOutcomes") or {}).get("answered", 0)
    line = (f"{len(sealed.marker_pages())} pages in {FINAL} ({finalized['characters']} characters); "
            f"{doubts['items']} doubts on {doubts['pages']} pages in {DOUBTS}; repair {counts.get('edits', 0)} "
            f"edits, {questions} questions ({answered} answered by the model)")
    kept = [f"{name} as {result['keptAs']}" for name, result in ((FINAL, finalized), (DOUBTS, doubts))
            if result.get("keptAs")]
    if kept:
        line += f"; the edited {' and '.join(kept)} kept (not in the new files)"
    return EXIT_DONE, line, [f"{FINAL}: {book / FINAL}", f"{DOUBTS}: {book / DOUBTS}"]


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    status = main()
    if status == EXIT_STOPPED:
        # The RESULT line is out.  The repair's threads may still wait for
        # the model to answer requests already on the wire (up to --timeout
        # each), and the interpreter would join them before exiting; a stop
        # does not wait for them (they are asked again on the next run).
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(status)
    sys.exit(status)
