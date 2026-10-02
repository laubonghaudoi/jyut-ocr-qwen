#!/usr/bin/env python3
"""Run both OCR engines on a book in ONE call, and build the draft the moment engine B is done.

Why this exists
---------------
Measured on a 609-page book (2026-09-30), the two engines ran one after the other,
each under its own run_ocr_phase.py hand-over: engine A (PaddleOCR-VL) took 75 min
with the GPU at 36-38% - its native backend decodes one layout block at a time
through a Python loop, so one CPU core sits at 100% while the GPU waits - and
engine B (HunyuanOCR) then took 30 min at about 80% GPU.  The draft the user
reads first is engine B's text alone (build_draft.py), yet it waited for both.

With the LLM server stopped, the card holds both engines at once (measured: A
14.5-17.6 GB, B about 5 GB, of 32.6 GB), so this script starts the two runners
side by side and runs build_draft.py as soon as B's runner exits 0, while A goes
on.  Under run_ocr_phase.py that is ONE hand-over: one release of the server,
one time budget both runners share (OCR_PHASE_DEADLINE and OCR_PHASE_PROGRESS
pass through to them), one restore.  It runs only what the runners run: each
gets the command line it would get alone, and the two processes share nothing
but the card.  Whether that leaves every page's text the same as from two
separate calls is the measurement that gates this script (HANDOFF §0: diff both
engines' TXT against solo runs before it is the default).

Usage, on a machine where the server has to be stopped (SKILL.md 〈安全並行〉):

    python3 scripts/run_ocr_phase.py -- python3 scripts/run_ocr_engines.py BOOK

BOOK is the book folder: renders/ in (or --renders), ocr-paddle/ and
ocr-hunyuan/ out (--ocr-a, --ocr-b), the runners' reports beside them
(paddleocr-vl-run.json, hunyuanocr-run.json) and draft.md, which build_draft.py
also copies beside the book's PDF (its lines are repeated at the end of this
script's output, so `tail` shows them after a long run).  The runners' own
settings come from the machine config (PADDLEOCR_PYTHON, HUNYUAN_*; env.sh) or
from --engine-a-args / --engine-b-args; --pages, --first-page/--last-page and
--overwrite go to both runners.  --a-lanes N runs engine A as N processes on
interleaved pages, each with its own report (paddleocr-vl-run.laneK.json); two
of them do not fit the card without a VRAM cap in the environment (FLAGS_* of
Paddle) and the gain is unmeasured, so the default is 1.

Exit codes: 0 both runners done; 75 a runner left pages for the next call (the
budget ran out: run the SAME command again, sealed pages are kept); 1 a runner
failed (read its lines above; do not just repeat); 2 nothing ran (bad arguments,
or every runner refused its configuration); 128+N stopped by signal N, after
passing SIGTERM on to the runners.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import time
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _phase_budget import DEADLINE_ENV, EXIT_INCOMPLETE, die_with_parent  # noqa: E402

RENDERS_DIRNAME = "renders"
OCR_A_DIRNAME = "ocr-paddle"
OCR_B_DIRNAME = "ocr-hunyuan"
RUNNER_A = "run_paddleocr_vl.py"
RUNNER_B = "run_hunyuanocr.py"
REPORT_A = "paddleocr-vl-run.json"
REPORT_B = "hunyuanocr-run.json"
DRAFT_SCRIPT = "build_draft.py"
DRAFT_NAME = "draft.md"
# After a signal is passed on, how long the runners get to close their GPU
# children before they are killed.  run_ocr_phase.py kills THIS process 10 s
# after its own SIGTERM, and a killed parent takes the runners with it
# (die_with_parent), so this stays well under that.
STOP_GRACE = 7.0
POLL = 0.5
PAGE_TOKEN = re.compile(r"\A([1-9][0-9]*)(?:-([1-9][0-9]*))?\Z")

RESULT_MEANING = {
    0: "DONE - both engines are done",
    EXIT_INCOMPLETE: "INCOMPLETE - time budget spent, finished pages are sealed: run the SAME "
                     "command again",
    1: "FAILED - read the runners' summary and ERROR lines above; do not just repeat",
    2: "CONFIGURATION ERROR - nothing was run",
}


class Engine:
    """One runner process and what became of it."""

    def __init__(self, label: str, name: str, command: list[str], report: Path) -> None:
        self.label, self.name, self.command, self.report = label, name, command, report
        self.process: subprocess.Popen | None = None
        self.code: int | None = None
        self.started = 0.0

    @property
    def running(self) -> bool:
        return self.process is not None and self.code is None


def say(message: str, *, error: bool = False) -> None:
    """Print without letting a closed stdout end the run (the harness may be gone)."""
    try:
        print(message, file=sys.stderr if error else sys.stdout, flush=True)
    except (OSError, ValueError):
        pass


def parse_pages(expression: str) -> list[int]:
    """The runners' selector grammar: 1,3-5."""
    pages: set[int] = set()
    for token in expression.split(","):
        token = token.strip()
        if not token:
            continue
        match = PAGE_TOKEN.match(token)
        if match is None:
            raise ValueError(f"invalid page selector: {token!r}")
        first, last = int(match.group(1)), int(match.group(2) or match.group(1))
        if last < first:
            raise ValueError(f"descending page range: {token!r}")
        pages.update(range(first, last + 1))
    if not pages:
        raise ValueError("no pages were selected")
    return sorted(pages)


def pages_expression(pages: list[int]) -> str:
    """Sorted pages as the shortest 1,3-5 expression."""
    runs: list[list[int]] = []
    for page in sorted(set(pages)):
        if runs and page == runs[-1][1] + 1:
            runs[-1][1] = page
        else:
            runs.append([page, page])
    return ",".join(f"{a}" if a == b else f"{a}-{b}" for a, b in runs)


def rendered_pages(renders: Path) -> list[int]:
    pages = []
    for path in renders.glob("page-*.png"):
        match = re.fullmatch(r"page-(\d{4,})\.png", path.name)
        if match:
            pages.append(int(match.group(1)))
    return sorted(pages)


def report_counts(path: Path) -> dict[str, Any] | None:
    try:
        counts = json.loads(path.read_text(encoding="utf-8")).get("counts")
    except (OSError, UnicodeError, json.JSONDecodeError, AttributeError):
        return None
    return counts if isinstance(counts, dict) else None


def counts_line(counts: dict[str, Any] | None) -> str:
    if counts is None:
        return "no run report"
    return " | ".join(f"{name} {counts.get(key, '?')}" for name, key in (
        ("requested", "requested"), ("completed", "completed"), ("skipped", "skippedCurrent"),
        ("blocked", "blocked"), ("failed", "failed"), ("deferred", "deferred")))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("book", type=Path, help="the book folder (renders/ in; ocr-paddle/, "
                                                 "ocr-hunyuan/, the run reports and draft.md out)")
    parser.add_argument("--renders", type=Path, help=f"the renders (default BOOK/{RENDERS_DIRNAME})")
    parser.add_argument("--ocr-a", type=Path, help=f"engine A's output (default BOOK/{OCR_A_DIRNAME})")
    parser.add_argument("--ocr-b", type=Path, help=f"engine B's output (default BOOK/{OCR_B_DIRNAME})")
    parser.add_argument("--no-engine-a", action="store_true", help="run engine B only")
    parser.add_argument("--no-engine-b", action="store_true", help="run engine A only (no draft)")
    parser.add_argument("--no-draft", action="store_true",
                        help="do not run build_draft.py when engine B is done")
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--pages", help="pages for both runners, e.g. 1,3-5 (default: every render)")
    selector.add_argument("--first-page", type=int)
    parser.add_argument("--last-page", type=int)
    parser.add_argument("--overwrite", action="store_true", help="passed to both runners")
    parser.add_argument("--engine-a-args", default="", help="extra options for run_paddleocr_vl.py, "
                                                            "one shell word list")
    parser.add_argument("--engine-b-args", default="", help="extra options for run_hunyuanocr.py")
    parser.add_argument("--a-lanes", type=int, default=1,
                        help="engine A processes on interleaved pages (default 1; more needs a "
                             "VRAM cap in the environment and is unmeasured)")
    parser.add_argument("--scripts-dir", type=Path, help=argparse.SUPPRESS)  # stand-ins, in checks
    return parser


def plan_engines(arguments: argparse.Namespace, book: Path, renders: Path,
                 scripts: Path) -> list[Engine]:
    ocr_a = (arguments.ocr_a or book / OCR_A_DIRNAME).expanduser().resolve()
    ocr_b = (arguments.ocr_b or book / OCR_B_DIRNAME).expanduser().resolve()
    common: list[str] = []
    if arguments.pages:
        common += ["--pages", arguments.pages]
    if arguments.first_page is not None:
        common += ["--first-page", str(arguments.first_page)]
    if arguments.last_page is not None:
        common += ["--last-page", str(arguments.last_page)]
    if arguments.overwrite:
        common.append("--overwrite")
    engines: list[Engine] = []
    if not arguments.no_engine_b:
        engines.append(Engine("B", RUNNER_B, [
            sys.executable, str(scripts / RUNNER_B), str(renders), str(ocr_b),
            "--report", str(book / REPORT_B), *common, *shlex.split(arguments.engine_b_args)],
            book / REPORT_B))
    if not arguments.no_engine_a:
        lanes = max(1, arguments.a_lanes)
        if lanes == 1:
            engines.append(Engine("A", RUNNER_A, [
                sys.executable, str(scripts / RUNNER_A), str(renders), str(ocr_a),
                "--report", str(book / REPORT_A), *common, *shlex.split(arguments.engine_a_args)],
                book / REPORT_A))
        else:
            if arguments.pages:
                pages = parse_pages(arguments.pages)
            else:
                pages = rendered_pages(renders)
                if arguments.first_page is not None:
                    pages = [p for p in pages if p >= arguments.first_page]
                if arguments.last_page is not None:
                    pages = [p for p in pages if p <= arguments.last_page]
            if not pages:
                raise ValueError(f"no page-NNNN.png renders to share out in {renders}")
            for lane in range(lanes):
                mine = pages[lane::lanes]
                if not mine:
                    continue
                report = book / f"paddleocr-vl-run.lane{lane + 1}.json"
                engines.append(Engine(f"A{lane + 1}", RUNNER_A, [
                    sys.executable, str(scripts / RUNNER_A), str(renders), str(ocr_a),
                    "--report", str(report), "--pages", pages_expression(mine),
                    *(["--overwrite"] if arguments.overwrite else []),
                    *shlex.split(arguments.engine_a_args)], report))
    return engines


def build_draft(scripts: Path, book: Path, ocr_b: Path | None) -> list[str]:
    """Run build_draft.py; its lines (the draft, the copy beside the PDF) are returned to be
    shown again at the end.  It never fails this run: a draft not written is said, not raised."""
    command = [sys.executable, str(scripts / DRAFT_SCRIPT), str(book)]
    if ocr_b is not None:
        command += ["--ocr-dir", str(ocr_b)]
    say(f"[ocr-engines] engine B is done; building the draft: {shlex.join(command)}")
    try:
        done = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              check=False, timeout=1800)
    except (OSError, subprocess.TimeoutExpired) as error:
        lines = [f"draft: build_draft.py could not run ({error}); run it by hand: {shlex.join(command)}"]
        say("[ocr-engines] " + lines[0], error=True)
        return lines
    lines = [line for line in (done.stdout + done.stderr).splitlines() if line.strip()]
    if done.returncode != 0:
        lines.append(f"draft: build_draft.py exit {done.returncode} - the pipeline goes on without it")
    for line in lines:
        say(f"[ocr-engines] {line}", error=done.returncode != 0)
    return lines


def draft_due(engine: Engine, book: Path) -> bool:
    """Build the draft once engine B has sealed pages in this call, or when there is no draft
    yet (a draft that failed to build last time); a call that only skipped sealed pages
    would otherwise rebuild and re-deliver the same draft every time."""
    if not (book / DRAFT_NAME).is_file():
        return True
    counts = report_counts(engine.report)
    return counts is None or bool(counts.get("completed"))


def result_code(codes: list[int]) -> int:
    if codes and all(code == 2 for code in codes):
        return 2
    if any(code not in (0, EXIT_INCOMPLETE) for code in codes):
        return 1
    if any(code == EXIT_INCOMPLETE for code in codes):
        return EXIT_INCOMPLETE
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    book = arguments.book.expanduser().resolve()
    renders = (arguments.renders or book / RENDERS_DIRNAME).expanduser().resolve()
    scripts = (arguments.scripts_dir or Path(__file__).parent).expanduser().resolve()
    if arguments.no_engine_a and arguments.no_engine_b:
        say("ERROR --no-engine-a with --no-engine-b leaves nothing to run", error=True)
        return 2
    if not renders.is_dir():
        say(f"ERROR render directory does not exist: {renders}", error=True)
        return 2
    if arguments.last_page is not None and arguments.first_page is None and arguments.pages is None:
        say("ERROR --last-page needs --first-page", error=True)
        return 2
    try:
        engines = plan_engines(arguments, book, renders, scripts)
    except ValueError as error:
        say(f"ERROR {error}", error=True)
        return 2
    ocr_b_given = arguments.ocr_b.expanduser().resolve() if arguments.ocr_b else None

    deadline = os.environ.get(DEADLINE_ENV, "").strip()
    if deadline:
        try:
            say(f"[ocr-engines] time budget: the runners stop starting pages in "
                f"{float(deadline) - time.time():.0f}s")
        except ValueError:
            pass

    state: dict[str, Any] = {"signal": None, "at": 0.0}

    def on_signal(signum: int, _frame: object) -> None:
        if state["signal"] is not None:
            return
        state["signal"], state["at"] = signum, time.monotonic()
        say(f"\n[ocr-engines] caught signal {signum}; stopping the runners", error=True)
        for engine in engines:
            if engine.running:
                try:
                    engine.process.terminate()
                except OSError:
                    pass

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, on_signal)

    for engine in engines:
        if state["signal"] is not None:
            engine.code = 128 + int(state["signal"])
            continue
        say(f"[ocr-engines] starting engine {engine.label}: {shlex.join(engine.command)}")
        engine.started = time.monotonic()
        try:
            # The runners must not outlive this process: if it is killed, they go
            # with it, and their GPU children with them (the runners' own rule).
            engine.process = subprocess.Popen(engine.command, stdin=subprocess.DEVNULL,
                                              preexec_fn=die_with_parent())
        except OSError as error:
            say(f"ERROR engine {engine.label} could not start: {error}", error=True)
            engine.code = 2

    draft_lines: list[str] = []
    killed = False
    while any(engine.running for engine in engines):
        for engine in engines:
            if not engine.running:
                continue
            code = engine.process.poll()
            if code is None:
                continue
            engine.code = code
            say(f"[ocr-engines] engine {engine.label} ({engine.name}) exit {code} after "
                f"{time.monotonic() - engine.started:.0f}s")
            if (engine.label == "B" and code == 0 and not arguments.no_draft
                    and state["signal"] is None and draft_due(engine, book)):
                draft_lines = build_draft(scripts, book, ocr_b_given)
        if state["signal"] is not None and not killed and time.monotonic() - state["at"] > STOP_GRACE:
            killed = True
            for engine in engines:
                if engine.running:
                    say(f"[ocr-engines] engine {engine.label} did not stop in {STOP_GRACE:.0f}s; "
                        "killing it", error=True)
                    try:
                        engine.process.kill()
                    except OSError:
                        pass
        time.sleep(POLL)

    for engine in engines:
        say(f"[ocr-engines] engine {engine.label} ({engine.name}): exit {engine.code} - "
            f"{counts_line(report_counts(engine.report))}")
    for line in draft_lines:
        say(f"[ocr-engines] {line}")
    if state["signal"] is not None:
        code = 128 + int(state["signal"])
        say(f"[ocr-engines] RESULT exit={code} STOPPED by signal {state['signal']}; sealed pages "
            "are kept")
        return code
    code = result_code([engine.code if engine.code is not None else 1 for engine in engines])
    say(f"[ocr-engines] RESULT exit={code} {RESULT_MEANING.get(code, 'see above')}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
