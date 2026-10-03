#!/usr/bin/env python3
"""Engine B's second look: read again, from a crop, the blocks its page reading left out.

Why this exists
---------------
HunyuanOCR reads a whole page with its document-parsing prompt, which tells it
to leave out headers and footers.  On a book with footnotes it often takes the
notes for a footer and stops after the body.  Measured on a 609-page modern
book (2026-10-02): on 81 pages its text held nothing of 208 blocks that engine
A (the layout engine) read - 195 footnotes, 7 paragraphs, 3 captions, 2 tables
- so about 3.7% of the book's characters, and every figure, page range and
Western name in those notes, rested on one engine.  The merge has nothing to
compare such text with, and what both engines read is the only evidence the
later stages accept for a figure or a Latin word.

Shown the block alone, the same engine with the same prompt reads it: of 26
such blocks cropped from engine A's boxes, 26 were read (25 with engine A's
characters to 0.9 or better; the table of one page, 559 characters, to 0.98),
and 292 of engine A's 300 figures and Latin words stood in the reading as
well; a crop takes 0.1 to 3 seconds.

What it does
------------
Run it after BOTH engines have read the book (it needs engine A's blocks):

    python3 scripts/run_ocr_phase.py -- \\
        python3 scripts/run_hunyuanocr_second_look.py RENDERS OCR_A_DIR OCR_B_DIR

For each page it takes engine A's blocks that are not page furniture and
measures how much of each stands in engine B's page text (the share of the
block's 4-character pieces, counting characters, letters and figures only).  A
block of which engine B holds under UNREAD_SHARE is unread.  Unread blocks next
to each other in engine A's order are read as one crop (their boxes' union,
when that covers no block engine B did read), and the reading is put into
engine B's page text as lines of its own, after the last line engine B wrote
for an earlier block.  The page's JSON says which lines came this way
(`blockLabel` "second-look", the crop's box) and keeps a `secondLook` record
(the blocks, the crops, engine A's draft the choice was made on), and its TXT
and seal are rewritten together, so the page is still the runner's sealed pair
and every later stage reads it as engine B's text.

What is not asked for, and what is not kept.  A block whose whole text stands
as a block of its own on RECURRING_PAGES or more pages of the book is a running
head or a title the book repeats: engine B left it out on purpose, and a
running head put into its text would reach the merge as body text both engines
read.  A reading far longer than the blocks it was asked for (a loop), or one
that holds under ALIKE_SHARE of engine A's text of them (grounding boxes, a
neighbour's lines, a failed reading), is not a second reading of those blocks
and is not kept.  A line of a reading that engine B's page text already holds
is left out: the block was read after all, in other forms than engine A's (a
variant character in a two-character title makes it look unread).
Pages are checked once: a page whose record holds a `secondLook` made on the
same engine A draft by this script is skipped, and one made on another draft is
done again from engine B's own lines.  The time budget, the exit codes (0 done,
75 call again, 1 failed, 2 configuration) and the report follow the runners.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Any, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_hunyuanocr as hy  # noqa: E402
from _phase_budget import EXIT_INCOMPLETE, Budget, exit_on_sigterm  # noqa: E402

SCHEMA_VERSION = 1
SECOND_LOOK_LABEL = "second-look"
# Engine A's labels for a block that is page furniture or no text: never asked
# for (phase 3 drops furniture; a picture has no text to read).
FURNITURE_LABELS = frozenset({"header", "footer", "number", "seal", "image", "figure", "chart"})
# A block is unread when engine B's page text holds under this share of its
# pieces.  A guard against the two readings' small differences (a variant
# form, a misread character break a few pieces), not a measure of quality:
# the unread blocks of the measured book had a share of 0, the read ones 0.9+.
UNREAD_SHARE = 0.2
PIECE = 4
# The crop's margin round the blocks' box, as a share of the page's height.
CROP_PAD = 0.004
# A reading this many times longer than the blocks' own text (plus a floor for
# short blocks) is a loop, not a reading.
LOOP_FACTOR = 3
LOOP_FLOOR = 200
# A reading is a second reading of the blocks when it holds at least this
# share of engine A's pieces of them; a line of it is already in engine B's
# page text when the text holds at least this share of the line's pieces.
ALIKE_SHARE = 0.5
# A block's whole text standing as a block of its own on this many pages is
# the book's running head or a title it repeats.
RECURRING_PAGES = 3

_MARKUP = re.compile(r"\$[^$\n]{0,200}\$|</?[A-Za-z][^<>\n]{0,80}>|\\[A-Za-z]+")


def key_text(text: str) -> str:
    """TEXT as the string the two readings are compared on: its characters,
    letters and figures, markup and marks left out."""
    return "".join(c for c in _MARKUP.sub(" ", text) if c.isalnum()).casefold()


def pieces(key: str) -> list[str]:
    if len(key) >= PIECE:
        return [key[i:i + PIECE] for i in range(len(key) - PIECE + 1)]
    return [key] if len(key) >= 2 else []


def share_read(block_key: str, page_key: str) -> float | None:
    """The share of the block's pieces engine B's page text holds; None for a
    block too short to tell."""
    parts = pieces(block_key)
    if not parts:
        return None
    return sum(part in page_key for part in parts) / len(parts)


def overlap(a: Sequence[float], b: Sequence[float]) -> float:
    """The share of box B ([x, y, width, height]) that box A covers."""
    width = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    height = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    area = b[2] * b[3]
    return max(width, 0.0) * max(height, 0.0) / area if area > 0 else 0.0


def union(boxes: Sequence[Sequence[float]]) -> list[float]:
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes)
    y1 = max(b[1] + b[3] for b in boxes)
    return [x0, y0, x1 - x0, y1 - y0]


def unread_groups(blocks: Sequence[Mapping[str, Any]], page_text: str,
                  recurring: frozenset[str] = frozenset()) -> list[dict[str, Any]]:
    """Engine A's blocks that engine B's PAGE_TEXT does not hold, as groups to
    read in one crop each: {"blocks": [indices], "box": [x, y, w, h], "text":
    engine A's text of them}.  Unread blocks that follow one another are one
    group when their boxes' union covers no block engine B read.  A block
    whose text is one of RECURRING (the book's repeated blocks) is no
    candidate."""
    page_key = key_text(page_text)
    state: list[bool | None] = []   # True unread, False read, None not a candidate
    for block in blocks:
        box = block.get("boundingBox")
        key = key_text(str(block.get("text") or ""))
        if block.get("blockLabel") in FURNITURE_LABELS or not isinstance(box, list) or len(box) != 4 \
                or key in recurring:
            state.append(None)
            continue
        share = share_read(key, page_key)
        state.append(None if share is None else share < UNREAD_SHARE)
    read_boxes = [blocks[k]["boundingBox"] for k, unread in enumerate(state) if unread is False]
    groups: list[list[int]] = []
    for k, unread in enumerate(state):
        if not unread:
            continue
        previous = groups[-1] if groups else None
        # The candidates between this block and the group's last are all
        # unread (furniture and too-short blocks between them do not part them).
        joined = previous is not None and not any(state[j] is False for j in range(previous[-1] + 1, k))
        if joined:
            box = union([blocks[j]["boundingBox"] for j in previous + [k]])
            joined = not any(overlap(box, other) > 0.1 for other in read_boxes)
        if joined:
            previous.append(k)
        else:
            groups.append([k])
    return [{"blocks": group, "box": [round(v, 6) for v in union([blocks[j]["boundingBox"] for j in group])],
             "text": "\n".join(str(blocks[j].get("text") or "") for j in group)} for group in groups]


def recurring_blocks(directory: Path) -> frozenset[str]:
    """The texts that stand as a block of their own on RECURRING_PAGES or more
    pages of engine A's drafts in DIRECTORY (the whole book, whatever pages are
    selected)."""
    seen: dict[str, int] = {}
    for path in sorted(directory.glob("page-*.json")):
        try:
            blocks = json.loads(path.read_bytes().decode("utf-8")).get("lines") or []
        except (OSError, UnicodeError, ValueError):
            continue
        for key in {key_text(str(block.get("text") or "")) for block in blocks}:
            if key:
                seen[key] = seen.get(key, 0) + 1
    return frozenset(key for key, pages in seen.items() if pages >= RECURRING_PAGES)


def kept_lines(text: str, group_text: str, page_text: str) -> tuple[list[str], str | None]:
    """The lines of a crop's reading TEXT to put into engine B's page text,
    and, when none is kept, why: the reading must be a reading of the blocks
    (GROUP_TEXT, engine A's), and a line engine B's PAGE_TEXT already holds
    is left out."""
    if len(text) > LOOP_FACTOR * len(group_text) + LOOP_FLOOR:
        return [], f"a reading of {len(text)} characters for blocks of {len(group_text)}"
    alike = share_read(key_text(group_text), key_text(text))
    if alike is not None and alike < ALIKE_SHARE:
        return [], f"the reading holds {alike:.2f} of engine A's text of the blocks"
    page_key = key_text(page_text)
    lines = []
    for line in text.splitlines():
        held = share_read(key_text(line), page_key)
        if line.strip() and not (held is not None and held >= ALIKE_SHARE):
            lines.append(line.rstrip())
    return lines, None if lines else "engine B's page text holds the reading already"


def insertion_line(lines: Sequence[Mapping[str, Any]], blocks: Sequence[Mapping[str, Any]], first_block: int) -> int:
    """Where a reading of the blocks from FIRST_BLOCK on goes among engine B's
    LINES: after the last line that holds the text of an earlier block of
    engine A (0 when no line does)."""
    earlier = [set(pieces(key_text(str(block.get("text") or "")))) for block in blocks[:first_block]]
    place = 0
    for n, line in enumerate(lines):
        parts = pieces(key_text(str(line.get("text") or "")))
        if parts and any(sum(part in block for part in parts) * 2 >= len(parts) for block in earlier):
            place = n + 1
    return place


def own_lines(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The lines of engine B's own page reading (an earlier second look's
    lines taken out)."""
    return [dict(line) for line in record.get("lines") or [] if line.get("blockLabel") != SECOND_LOOK_LABEL]


def reseal(record: dict[str, Any], lines: list[dict[str, Any]], second_look: Mapping[str, Any]) -> tuple[bytes, bytes]:
    """RECORD with LINES and the SECOND_LOOK field, sealed as the runner
    seals a page: (JSON bytes, TXT bytes)."""
    text_bytes = hy.text_from_lines(lines)
    record = json.loads(json.dumps(record, ensure_ascii=False))
    record["lines"] = lines
    record["sentenceMarks"] = sum(1 for c in text_bytes.decode("utf-8") if c in hy.SENTENCE_MARKS)
    record["secondLook"] = dict(second_look)
    record["provenance"]["textSha256"] = hy.sha256_bytes(text_bytes)
    record["provenance"].pop("jsonPayloadSha256", None)
    record["provenance"]["jsonPayloadSha256"] = hy.sha256_bytes(hy.canonical_json_bytes(record, pretty=True))
    return hy.canonical_json_bytes(record, pretty=True), text_bytes


def write_pair(json_path: Path, text_path: Path, json_bytes: bytes, text_bytes: bytes) -> None:
    with tempfile.TemporaryDirectory(dir=str(json_path.parent)) as staging:
        sj, st = Path(staging) / "p.json", Path(staging) / "p.txt"
        sj.write_bytes(json_bytes)
        st.write_bytes(text_bytes)
        os.replace(st, text_path)   # JSON is the completion record: last
        os.replace(sj, json_path)


def tool_sha256(model: Path | None, mmproj: Path | None) -> str:
    combined = hashlib.sha256()
    combined.update(b"run_hunyuanocr_second_look.py\0" + Path(__file__).resolve().read_bytes())
    for label, path in (("model", model), ("mmproj", mmproj)):
        if path is not None and path.is_file():
            combined.update(f"\0{label}\0".encode() + hy.sha256_file(path).encode())
    return combined.hexdigest()


def crop_png(render: Path, box: Sequence[float], directory: Path) -> Path:
    from PIL import Image
    with Image.open(render) as image:
        width, height = image.size
        pad = CROP_PAD * height
        x0, y0 = max(0, int(box[0] * width - pad)), max(0, int(box[1] * height - pad))
        x1 = min(width, int((box[0] + box[2]) * width + pad) + 1)
        y1 = min(height, int((box[1] + box[3]) * height + pad) + 1)
        out = directory / "crop.png"
        image.crop((x0, y0, x1, y1)).convert("RGB").save(out)
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("render_directory", type=Path)
    p.add_argument("engine_a_directory", type=Path, help="engine A's drafts (page-NNNN.json with its blocks)")
    p.add_argument("output_directory", type=Path, help="engine B's drafts, rewritten in place")
    sel = p.add_mutually_exclusive_group(required=False)
    sel.add_argument("--pages", help="comma-separated pages/ranges, e.g. 1,3-5")
    sel.add_argument("--first-page", type=int)
    p.add_argument("--last-page", type=int)
    p.add_argument("--model", type=Path, default=Path(os.environ.get("HUNYUAN_MODEL", "")) or None)
    p.add_argument("--mmproj", type=Path, default=Path(os.environ.get("HUNYUAN_MMPROJ", "")) or None)
    p.add_argument("--llama-server", type=Path, default=Path(os.environ.get("HUNYUAN_LLAMA_SERVER", "")) or None)
    p.add_argument("--endpoint", default=os.environ.get("HUNYUAN_ENDPOINT"),
                   help="use an already-running server instead of starting one")
    p.add_argument("--port", type=int, default=8095)
    p.add_argument("--ctx-size", type=int, default=16384)
    p.add_argument("--max-tokens", type=int, default=8000)
    p.add_argument("--timeout", type=float, default=1200.0)
    p.add_argument("--report", type=Path)
    return p


def main(argv: Sequence[str] | None = None, server: Any | None = None) -> int:
    """SERVER, for the offline check: an object with ocr(path, max_tokens,
    timeout) and close(), used instead of starting llama-server."""
    arguments = build_parser().parse_args(argv)
    exit_on_sigterm()
    started_at, started = hy.utc_now(), time.monotonic()
    try:
        renders = arguments.render_directory.expanduser().resolve()
        drafts_a = arguments.engine_a_directory.expanduser().resolve()
        output = arguments.output_directory.expanduser().resolve()
        for label, path in (("render", renders), ("engine A draft", drafts_a), ("engine B draft", output)):
            if not path.is_dir():
                raise hy.ConfigurationError(f"{label} directory does not exist: {path}")
        pages, selection_mode = hy.selected_pages(arguments, renders)
        report_path = (arguments.report.expanduser().resolve() if arguments.report
                       else output.parent / "hunyuanocr-second-look.json")
        if hy.path_is_within(report_path, output):
            raise hy.ConfigurationError("run report must be outside the OCR output directory")
        if server is None and not arguments.endpoint and (arguments.model is None or arguments.mmproj is None):
            raise hy.ConfigurationError("need --model and --mmproj (or HUNYUAN_MODEL / HUNYUAN_MMPROJ), "
                                        "or --endpoint for an already-running server")
        tool = tool_sha256(arguments.model, arguments.mmproj)
    except hy.ConfigurationError as error:
        print(f"ERROR {error}", file=sys.stderr)
        return 2

    results: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    skipped = blocked = 0
    recurring = recurring_blocks(drafts_a)
    for scan_page in pages:
        json_b, text_b = hy.output_paths(output, scan_page)
        json_a = drafts_a / f"page-{scan_page:04d}.json"
        render = hy.render_path(renders, scan_page)
        try:
            raw_a = json_a.read_bytes()
            blocks = json.loads(raw_a.decode("utf-8")).get("lines") or []
            record = json.loads(json_b.read_bytes().decode("utf-8"))
            if hy.text_from_lines(record.get("lines") or []) != text_b.read_bytes():
                raise ValueError("engine B's TXT does not match its JSON lines")
            if not render.is_file():
                raise ValueError("render file is missing")
        except (OSError, UnicodeError, ValueError) as error:
            # Both engines must have read the page first.
            blocked += 1
            results.append({"scanPage": scan_page, "status": "blocked", "error": str(error)[:200]})
            continue
        draft_a = hy.sha256_bytes(raw_a)
        earlier = record.get("secondLook") or {}
        if earlier.get("toolSha256") == tool and earlier.get("engineADraftSha256") == draft_a:
            skipped += 1
            results.append({"scanPage": scan_page, "status": "skipped-current"})
            continue
        lines = own_lines(record)
        groups = unread_groups(blocks, hy.text_from_lines(lines).decode("utf-8"), recurring)
        pending.append({"scanPage": scan_page, "record": record, "lines": lines, "blocks": blocks, "groups": groups,
                        "render": render, "json": json_b, "text": text_b, "draftA": draft_a})

    completed = failed = deferred = reread = 0
    budget = Budget()
    own_server = server is None
    try:
        if own_server and any(page["groups"] for page in pending):
            try:
                server = hy.HunyuanServer(arguments.endpoint, arguments.llama_server, arguments.model or Path(),
                                          arguments.mmproj or Path(), arguments.port, arguments.ctx_size)
            except hy.ConfigurationError as error:
                print(f"ERROR {error}", file=sys.stderr)
                for page in pending:
                    failed += 1
                    results.append({"scanPage": page["scanPage"], "status": "failed", "error": str(error)})
                pending = []
        for index, page in enumerate(pending):
            if page["groups"] and not budget.allows_next_page():
                for later in pending[index:]:
                    deferred += 1
                    results.append({"scanPage": later["scanPage"], "status": "deferred"})
                print(f"  time budget reached: {deferred} page(s) left for the next call", flush=True)
                break
            t0 = time.monotonic()
            lines = list(page["lines"])
            done: list[dict[str, Any]] = []
            try:
                # Later groups first, so that a place found among engine B's own
                # lines stays right while readings go in.
                placed: list[tuple[int, int, list[dict[str, Any]]]] = []
                for order, group in enumerate(page["groups"]):
                    page_limit, _ = budget.page_timeout(arguments.timeout)
                    with tempfile.TemporaryDirectory() as staging:
                        crop = crop_png(page["render"], group["box"], Path(staging))
                        entry = {"blocks": group["blocks"], "box": group["box"]}
                        try:
                            text = server.ocr(crop, arguments.max_tokens, page_limit)
                        except hy.PageOCRFailure as error:
                            left = budget.remaining()
                            if left is not None and left <= 1.0:
                                raise
                            entry["error"] = str(error)[:200]
                            done.append(entry)
                            continue
                    kept, why = kept_lines(text, group["text"], hy.text_from_lines(page["lines"]).decode("utf-8"))
                    entry["chars"] = len(text)
                    if not kept:
                        entry["notKept"] = why
                        done.append(entry)
                        continue
                    new = [{"text": line, "confidence": 0.0, "boundingBox": group["box"],
                            "blockLabel": SECOND_LOOK_LABEL} for line in kept]
                    entry["lines"] = len(new)
                    done.append(entry)
                    placed.append((insertion_line(page["lines"], page["blocks"], group["blocks"][0]), order, new))
                    reread += 1
                for place, _, new in sorted(placed, key=lambda item: (item[0], item[1]), reverse=True):
                    lines[place:place] = new
                second_look = {"schemaVersion": SCHEMA_VERSION, "toolSha256": tool, "engineADraftSha256": page["draftA"],
                               "unreadShare": UNREAD_SHARE, "groups": done}
                json_bytes, text_bytes = reseal(page["record"], lines, second_look)
                write_pair(page["json"], page["text"], json_bytes, text_bytes)
                completed += 1
                if page["groups"]:
                    budget.record(time.monotonic() - t0)
                budget.sealed(page["scanPage"])
                seconds = round(time.monotonic() - t0, 2)
                results.append({"scanPage": page["scanPage"], "status": "completed", "groups": len(done),
                                "blocks": sum(len(g["blocks"]) for g in done),
                                "errors": sum(1 for g in done if g.get("error")),
                                "notKept": sum(1 for g in done if g.get("notKept")), "seconds": seconds})
                if done:
                    print(f"  page {page['scanPage']:04d}: {sum(len(g['blocks']) for g in done)} block(s) in "
                          f"{len(done)} crop(s), {seconds}s", flush=True)
            except hy.PageOCRFailure:
                # The budget ran out during a crop: the page is left as it was.
                for later in pending[index:]:
                    deferred += 1
                    results.append({"scanPage": later["scanPage"], "status": "deferred"})
                print(f"  time budget reached during page {page['scanPage']:04d}: "
                      f"{deferred} page(s) left for the next call", flush=True)
                break
    finally:
        if own_server and server is not None:
            server.close()

    results.sort(key=lambda r: r["scanPage"])
    report = {
        "reportSchemaVersion": SCHEMA_VERSION, "startedAt": started_at, "finishedAt": hy.utc_now(),
        "durationSeconds": round(time.monotonic() - started, 2), "selectionMode": selection_mode,
        "renderDirectory": str(renders), "engineADirectory": str(drafts_a), "outputDirectory": str(output),
        "toolSha256": tool, "unreadShare": UNREAD_SHARE,
        "counts": {"requested": len(pages), "completed": completed, "skippedCurrent": skipped, "blocked": blocked,
                   "failed": failed, "deferred": deferred, "cropsRead": reread,
                   "pagesWithUnreadBlocks": sum(1 for r in results if r.get("groups"))},
        "pages": results,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_bytes(hy.canonical_json_bytes(report, pretty=True))
    print(f"  requested {len(pages)} | completed {completed} | skipped {skipped} | blocked {blocked} | "
          f"failed {failed} | deferred {deferred} | crops read {reread}", flush=True)
    print(f"  report: {report_path}", flush=True)
    if deferred and completed:
        return EXIT_INCOMPLETE
    if deferred:
        print("ERROR the time budget ran out before a single page was done (starting the server used it up). "
              "Raise the budget together with the tool call's time limit.", file=sys.stderr)
        return 1
    return 1 if failed or blocked else 0


if __name__ == "__main__":
    sys.exit(main())
