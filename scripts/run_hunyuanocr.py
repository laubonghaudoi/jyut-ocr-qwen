#!/usr/bin/env python3
"""Run HunyuanOCR as a SECOND, independent OCR draft engine.

Why a second engine rather than a replacement: every stage of the proofreading
pipeline shares one model lineage, so when the draft and the reader are wrong the
same way they agree and nothing escalates. A draft from a different vendor,
architecture and training set is the only cheap source of genuine independence.

Measured on this project's test page against human-adjudicated ground truth:
HunyuanOCR 6/6, PaddleOCR-VL 4/6, the local Qwen writer 3/6 - the differences
being variant forms (輙/輒, 弑/弒) that no prompt rule can settle because only
the printed glyph decides.

Punctuation: whether it writes a book's marks, and in what shape, depends on how
the book prints them, as it does for PaddleOCR-VL.  Measured over the drafts of
six books: on one it wrote 9,324 。 and 3,578 ，; on one printed with circles
and no commas it wrote more ， (2,234) than 。 (1,292); on one it wrote the
full-cell vertical commas as the character 丶 (1,754 times, against 104 ，); on
one it wrote 36 。 in 344 pages and a printed ▲ as 厶; on a book of figure
tables, 4,089 、 between the figures and not one 。 or ，; on one, none at all.  Its
marks are a reading to weigh against the page, never the page's punctuation,
which the reading model takes from the crop.  Each record counts the sentence
marks written on its page (`sentenceMarks`).

Output is the same sealed JSON/TXT pair as the other OCR runners, so downstream
stages treat the two drafts identically.

Unlike the layout-based engines this model reads a whole page at once, so there
are no per-block bounding boxes. Records say so explicitly rather than inventing
coordinates: `boundingBox` is the full page and `blockLabel` is "whole-page".
Crop-based adjudication should use a layout engine's draft, not this one.
"""

from __future__ import annotations

import argparse
import base64
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
import time
from typing import Any, Mapping, Sequence
import urllib.error
import urllib.request

SCHEMA_VERSION = 2
REPORT_SCHEMA_VERSION = 1
ENGINE = "HunyuanOCR"
TEXT_AUTHORITY = "draft-only-not-text-authority"

# The model card's own document-parsing prompt. Kept verbatim: the published
# sampling settings and prompt are what its reported accuracy was measured with.
DOC_PARSE_PROMPT = (
    "提取文档图片中正文的所有信息用markdown格式表示，其中页眉、页脚部分忽略，"
    "表格用html格式表达，文档中公式用latex格式表示，按照阅读顺序组织进行解析。"
)

OCR_PROFILE: dict[str, Any] = {
    "engine": ENGINE,
    "prompt": DOC_PARSE_PROMPT,
    "recognitionLevel": "vlm-whole-page",
    "usesLanguageCorrection": False,
    "temperature": 0.0,
    "topP": 1.0,
    "repetitionPenalty": 1.08,
    "readingOrder": "model-resolved-whole-page",
    "boundingBoxConvention": "none-whole-page-only",
}
# The profile used to say "emitsSentencePunctuation": False, a claim about the
# engine that the drafts contradict (see the module docstring).  What the engine
# wrote is counted per page instead: `sentenceMarks`, these marks as written.
SENTENCE_MARKS = frozenset("。，、；：？！")

PAGE_TOKEN = re.compile(r"(?P<first>[1-9][0-9]*)(?:-(?P<last>[1-9][0-9]*))?\Z")
READY_TIMEOUT = 600.0


class ConfigurationError(ValueError):
    """A command-line or filesystem configuration is unsafe or invalid."""


class PageOCRFailure(RuntimeError):
    """The engine rejected one page while the server remains usable."""


@dataclass(frozen=True)
class ToolIdentity:
    runner_file: Path
    model_sha256: str
    mmproj_sha256: str
    combined_sha256: str


@dataclass(frozen=True)
class PageInput:
    scan_page: int
    render_file: Path
    render_sha256: str
    json_output: Path
    text_output: Path


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any, *, pretty: bool = False) -> bytes:
    if pretty:
        text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True,
                          separators=(",", ": "))
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"))
    return text.encode("utf-8")


def profile_sha256(profile: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(profile))


def render_path(directory: Path, scan_page: int) -> Path:
    return directory / f"page-{scan_page:04d}.png"


def output_paths(directory: Path, scan_page: int) -> tuple[Path, Path]:
    stem = f"page-{scan_page:04d}"
    return directory / f"{stem}.json", directory / f"{stem}.txt"


def path_is_within(candidate: Path, directory: Path) -> bool:
    try:
        candidate.relative_to(directory)
    except ValueError:
        return False
    return True


def text_from_lines(lines: Sequence[Mapping[str, Any]]) -> bytes:
    return ("\n".join(str(line["text"]) for line in lines) + "\n").encode("utf-8")


def parse_pages_expression(expression: str) -> list[int]:
    pages: set[int] = set()
    for token in expression.split(","):
        token = token.strip()
        if not token:
            continue
        match = PAGE_TOKEN.match(token)
        if match is None:
            raise ConfigurationError(f"invalid page selector: {token!r}")
        first = int(match.group("first"))
        last = int(match.group("last") or first)
        if last < first:
            raise ConfigurationError(f"descending page range: {token!r}")
        pages.update(range(first, last + 1))
    if not pages:
        raise ConfigurationError("no pages were selected")
    return sorted(pages)


def rendered_pages(render_directory: Path) -> list[int]:
    """Every scan page that has a page-NNNN.png render; the default selection."""
    pages: list[int] = []
    for path in render_directory.glob("page-*.png"):
        match = re.fullmatch(r"page-(\d{4})\.png", path.name)
        if match:
            pages.append(int(match.group(1)))
    return sorted(pages)


def selected_pages(arguments: argparse.Namespace, render_directory: Path) -> tuple[list[int], str]:
    if arguments.pages is not None:
        if arguments.last_page is not None:
            raise ConfigurationError("--last-page cannot be combined with --pages")
        return parse_pages_expression(arguments.pages), "explicit-pages"
    if arguments.first_page is None and arguments.last_page is None:
        pages = rendered_pages(render_directory)
        if not pages:
            raise ConfigurationError(f"no page-NNNN.png renders in {render_directory}")
        return pages, "all-renders"
    if arguments.first_page is None:
        raise ConfigurationError("--last-page needs --first-page")
    if arguments.last_page is None:
        pages = rendered_pages(render_directory)
        if not pages:
            raise ConfigurationError(f"no page-NNNN.png renders in {render_directory}")
        arguments.last_page = pages[-1]
    if arguments.last_page < arguments.first_page:
        raise ConfigurationError("--last-page must be at least --first-page")
    return list(range(arguments.first_page, arguments.last_page + 1)), "page-range"


def build_tool_identity(model: Path, mmproj: Path) -> ToolIdentity:
    runner = Path(__file__).resolve()
    for label, path in (("model", model), ("mmproj", mmproj)):
        if not path.is_file():
            raise ConfigurationError(f"missing {label} weights: {path}")
    model_hash, mmproj_hash = sha256_file(model), sha256_file(mmproj)
    combined = hashlib.sha256()
    combined.update(b"run_hunyuanocr.py\0")
    combined.update(runner.read_bytes())
    combined.update(b"\0model\0" + model_hash.encode())
    combined.update(b"\0mmproj\0" + mmproj_hash.encode())
    return ToolIdentity(runner, model_hash, mmproj_hash, combined.hexdigest())


class HunyuanServer:
    """An OpenAI-compatible llama.cpp server, started here or already running."""

    def __init__(self, endpoint: str | None, binary: Path | None,
                 model: Path, mmproj: Path, port: int, ctx: int):
        self.process: subprocess.Popen[bytes] | None = None
        if endpoint:
            self.base = endpoint.rstrip("/")
            return
        if binary is None or not binary.is_file():
            raise ConfigurationError(
                "no --endpoint given and llama-server binary not found; "
                "pass --llama-server or HUNYUAN_LLAMA_SERVER")
        self.base = f"http://127.0.0.1:{port}"
        self.process = subprocess.Popen(
            [str(binary), "--model", str(model), "--mmproj", str(mmproj),
             "--host", "127.0.0.1", "--port", str(port), "--alias", "hunyuanocr",
             "--ctx-size", str(ctx), "--n-gpu-layers", "99", "--log-disable"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            # llama-server holds the model on the GPU; it must not outlive this runner.
            preexec_fn=die_with_parent())
        deadline = time.monotonic() + READY_TIMEOUT
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise ConfigurationError(
                    f"llama-server exited with code {self.process.returncode}; "
                    "the GPU may be occupied - run this inside run_ocr_phase.py")
            if self._healthy():
                return
            time.sleep(2)
        self.close()
        raise ConfigurationError(f"llama-server did not become ready in {READY_TIMEOUT:.0f}s")

    def _healthy(self) -> bool:
        try:
            with urllib.request.urlopen(self.base + "/v1/models", timeout=5) as r:
                return 200 <= r.status < 300
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def ocr(self, render: Path, max_tokens: int, timeout: float) -> str:
        b64 = base64.b64encode(render.read_bytes()).decode()
        body = {
            "model": "hunyuanocr",
            "max_tokens": max_tokens,
            "temperature": OCR_PROFILE["temperature"],
            "top_p": OCR_PROFILE["topP"],
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
                {"type": "text", "text": DOC_PARSE_PROMPT}]}],
        }
        request = urllib.request.Request(
            self.base + "/v1/chat/completions", json.dumps(body).encode(),
            {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            raise PageOCRFailure(f"HTTP {error.code}: {error.read().decode()[:200]}") from error
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            raise PageOCRFailure(f"endpoint unreachable: {error}") from error
        choice = payload["choices"][0]
        text = (choice["message"].get("content") or "").strip()
        if not text:
            raise PageOCRFailure(f"empty output (finish_reason={choice.get('finish_reason')})")
        return text

    def close(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=30)


def lines_from_text(text: str) -> list[dict[str, Any]]:
    """One record per non-empty line. No boxes: this engine reads whole pages."""
    out = []
    for line in text.splitlines():
        line = line.rstrip()
        if not line.strip():
            continue
        out.append({
            "text": line,
            "confidence": 0.0,          # the engine reports none; do not invent one
            "boundingBox": [0.0, 0.0, 1.0, 1.0],
            "blockLabel": "whole-page",
        })
    return out or [{"text": text.strip(), "confidence": 0.0,
                    "boundingBox": [0.0, 0.0, 1.0, 1.0], "blockLabel": "whole-page"}]


def build_record(page: PageInput, lines: list[dict[str, Any]], text_bytes: bytes,
                 tool: ToolIdentity, profile: Mapping[str, Any]) -> dict[str, Any]:
    record = {
        "schemaVersion": SCHEMA_VERSION,
        "scanPage": page.scan_page,
        "status": "complete",
        "renderFile": str(page.render_file),
        "generatedAt": utc_now(),
        "engine": profile["engine"],
        "recognitionLevel": profile["recognitionLevel"],
        "usesLanguageCorrection": profile["usesLanguageCorrection"],
        # Measured on this page, not assumed for the engine.
        "sentenceMarks": sum(1 for c in text_bytes.decode("utf-8") if c in SENTENCE_MARKS),
        "textAuthority": TEXT_AUTHORITY,
        "lines": lines,
        "provenance": {
            "renderSha256": page.render_sha256,
            "toolSha256": tool.combined_sha256,
            "ocrProfileSha256": profile_sha256(profile),
            "textSha256": sha256_bytes(text_bytes),
        },
    }
    record["provenance"]["jsonPayloadSha256"] = sha256_bytes(
        canonical_json_bytes(record, pretty=True))
    return record


def completion_is_current(page: PageInput, tool: ToolIdentity,
                          profile: Mapping[str, Any]) -> tuple[bool, str]:
    if not (page.json_output.is_file() and page.text_output.is_file()):
        return False, "no existing output"
    try:
        raw = page.json_output.read_bytes()
        text_bytes = page.text_output.read_bytes()
        record = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return False, f"unreadable: {error}"
    if record.get("schemaVersion") != SCHEMA_VERSION:
        return False, "legacy schema"
    if raw != canonical_json_bytes(record, pretty=True):
        return False, "not canonical or edited"
    if text_from_lines(record.get("lines") or []) != text_bytes:
        return False, "TXT does not match JSON lines"
    provenance = record.get("provenance") or {}
    expected = {
        "renderSha256": page.render_sha256,
        "toolSha256": tool.combined_sha256,
        "ocrProfileSha256": profile_sha256(profile),
        "textSha256": sha256_bytes(text_bytes),
    }
    for key, value in expected.items():
        if provenance.get(key) != value:
            return False, f"provenance {key} differs"
    sealed = provenance.get("jsonPayloadSha256")
    unsealed = json.loads(json.dumps(record, ensure_ascii=False))
    del unsealed["provenance"]["jsonPayloadSha256"]
    if sha256_bytes(canonical_json_bytes(unsealed, pretty=True)) != sealed:
        return False, "payload seal does not match"
    return True, "current"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("render_directory", type=Path)
    p.add_argument("output_directory", type=Path)
    sel = p.add_mutually_exclusive_group(required=False)
    sel.add_argument("--pages", help="comma-separated pages/ranges, e.g. 1,3-5")
    sel.add_argument("--first-page", type=int)
    p.add_argument("--last-page", type=int)
    p.add_argument("--model", type=Path,
                   default=Path(os.environ.get("HUNYUAN_MODEL", "")) or None)
    p.add_argument("--mmproj", type=Path,
                   default=Path(os.environ.get("HUNYUAN_MMPROJ", "")) or None)
    p.add_argument("--llama-server", type=Path,
                   default=Path(os.environ.get("HUNYUAN_LLAMA_SERVER", "")) or None)
    p.add_argument("--endpoint", default=os.environ.get("HUNYUAN_ENDPOINT"),
                   help="use an already-running server instead of starting one")
    p.add_argument("--port", type=int, default=8095)
    p.add_argument("--ctx-size", type=int, default=16384)
    p.add_argument("--max-tokens", type=int, default=8000)
    p.add_argument("--timeout", type=float, default=1200.0)
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--report", type=Path)
    return p


from _phase_budget import (  # noqa: E402  (scripts/ is sys.path[0])
    EXIT_INCOMPLETE, Budget, die_with_parent, exit_on_sigterm)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    exit_on_sigterm()
    started_at, started = utc_now(), time.monotonic()
    try:
        renders = arguments.render_directory.expanduser().resolve()
        pages, selection_mode = selected_pages(arguments, renders)
        output = arguments.output_directory.expanduser().resolve()
        if not renders.is_dir():
            raise ConfigurationError(f"render directory does not exist: {renders}")
        output.mkdir(parents=True, exist_ok=True)
        report_path = (arguments.report.expanduser().resolve() if arguments.report
                       else output.parent / "hunyuanocr-run.json")
        if path_is_within(report_path, output):
            raise ConfigurationError("run report must be outside the OCR output directory")
        if not arguments.endpoint:
            if arguments.model is None or arguments.mmproj is None:
                raise ConfigurationError(
                    "need --model and --mmproj (or HUNYUAN_MODEL / HUNYUAN_MMPROJ), "
                    "or --endpoint for an already-running server")
        tool = build_tool_identity(
            arguments.model or Path(__file__), arguments.mmproj or Path(__file__))
        profile = dict(OCR_PROFILE)
    except ConfigurationError as error:
        print(f"ERROR {error}", file=sys.stderr)
        return 2

    results: list[dict[str, Any]] = []
    pending: list[PageInput] = []
    skipped = blocked = 0

    for scan_page in pages:
        render = render_path(renders, scan_page).resolve()
        json_out, text_out = output_paths(output, scan_page)
        if not render.is_file():
            results.append({"scanPage": scan_page, "status": "failed",
                            "error": "render file is missing"})
            blocked += 1
            continue
        page = PageInput(scan_page, render, sha256_file(render), json_out, text_out)
        current, reason = completion_is_current(page, tool, profile)
        exists = os.path.lexists(json_out) or os.path.lexists(text_out)
        if current and not arguments.overwrite:
            skipped += 1
            results.append({"scanPage": scan_page, "status": "skipped-current"})
            continue
        if exists and not arguments.overwrite:
            blocked += 1
            results.append({"scanPage": scan_page, "status": "blocked",
                            "error": f"existing output rejected: {reason}; use --overwrite"})
            continue
        pending.append(page)

    completed = failed = deferred = 0
    budget = Budget()
    server: HunyuanServer | None = None
    try:
        if pending:
            try:
                server = HunyuanServer(arguments.endpoint, arguments.llama_server,
                                       arguments.model or Path(), arguments.mmproj or Path(),
                                       arguments.port, arguments.ctx_size)
            except ConfigurationError as error:
                print(f"ERROR {error}", file=sys.stderr)
                for page in pending:
                    failed += 1
                    results.append({"scanPage": page.scan_page, "status": "failed",
                                    "error": str(error)})
                pending = []

        for index, page in enumerate(pending):
            assert server is not None
            if not budget.allows_next_page():
                # Out of time for this call; the next call resumes these pages.
                for later in pending[index:]:
                    deferred += 1
                    results.append({"scanPage": later.scan_page, "status": "deferred"})
                print(f"  time budget reached: {deferred} page(s) left for the next call",
                      flush=True)
                break
            t0 = time.monotonic()
            page_limit, capped = budget.page_timeout(arguments.timeout)
            try:
                text = server.ocr(page.render_file, arguments.max_tokens, page_limit)
                lines = lines_from_text(text)
                text_bytes = text_from_lines(lines)
                record = build_record(page, lines, text_bytes, tool, profile)
                json_bytes = canonical_json_bytes(record, pretty=True)
                with tempfile.TemporaryDirectory(dir=str(page.json_output.parent)) as staging:
                    sj, st = Path(staging) / "p.json", Path(staging) / "p.txt"
                    sj.write_bytes(json_bytes)
                    st.write_bytes(text_bytes)
                    os.replace(st, page.text_output)   # JSON is the completion record: last
                    os.replace(sj, page.json_output)
                completed += 1
                budget.record(time.monotonic() - t0)
                budget.sealed(page.scan_page)
                seconds = round(time.monotonic() - t0, 2)
                results.append({"scanPage": page.scan_page, "status": "completed",
                                "renderSha256": page.render_sha256,
                                "chars": len(text), "seconds": seconds})
                print(f"  page {page.scan_page:04d}: {len(text)} chars in {seconds}s", flush=True)
            except PageOCRFailure as error:
                if capped and (budget.remaining() or 0.0) <= 1.0:
                    # The budget, not the page, ran out: leave it for the next call.
                    for later in pending[index:]:
                        deferred += 1
                        results.append({"scanPage": later.scan_page, "status": "deferred"})
                    print(f"  time budget reached during page {page.scan_page:04d}: "
                          f"{deferred} page(s) left for the next call", flush=True)
                    break
                failed += 1
                results.append({"scanPage": page.scan_page, "status": "failed",
                                "error": str(error)})
                print(f"  page {page.scan_page:04d}: FAILED {error}", file=sys.stderr)
    finally:
        if server is not None:
            server.close()

    results.sort(key=lambda r: r["scanPage"])
    report = {
        "reportSchemaVersion": REPORT_SCHEMA_VERSION,
        "startedAt": started_at, "finishedAt": utc_now(),
        "durationSeconds": round(time.monotonic() - started, 2),
        "selectionMode": selection_mode,
        "renderDirectory": str(renders), "outputDirectory": str(output),
        "textAuthority": TEXT_AUTHORITY,
        "tool": {"runner": str(tool.runner_file), "toolSha256": tool.combined_sha256,
                 "modelSha256": tool.model_sha256, "mmprojSha256": tool.mmproj_sha256},
        "ocrProfile": profile, "ocrProfileSha256": profile_sha256(profile),
        "counts": {"requested": len(pages), "completed": completed,
                   "skippedCurrent": skipped, "blocked": blocked, "failed": failed,
                   "deferred": deferred},
        "pages": results,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_bytes(canonical_json_bytes(report, pretty=True))
    print(f"  requested {len(pages)} | completed {completed} | skipped {skipped} | "
          f"blocked {blocked} | failed {failed} | deferred {deferred}", flush=True)
    print(f"  report: {report_path}", flush=True)
    # Pages left over after progress: call again (failed pages are retried then
    # too).  Pages left over with no progress: calling again would do exactly
    # the same, so stop the loop with an error the agent has to read.
    if deferred and completed:
        return EXIT_INCOMPLETE
    if deferred:
        print("ERROR the time budget ran out before a single page was sealed "
              "(starting the server used it up, or this page is stuck). Keep the "
              "budget below the tool call's time limit - raise both together, or "
              "lower --restore-reserve if the server restarts quickly here; if one "
              "page never finishes, it is stuck: run it alone to see why.",
              file=sys.stderr)
        return 1
    if failed or blocked:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
