#!/usr/bin/env python3
"""Wait quietly for a long step running in the background, then print one line.

Why this exists
---------------
The agent harness and the skill's long steps can share one local model server,
and every agent turn sends the whole conversation to that server again.
Measured on one book (the Qwen Code transcript and the run's own files, read
after the run): during a 99-minute book profile the agent took 84 turns of
about 110K prompt tokens each, most with no prefix-cache hit - 9.3M prompt
tokens, an estimated 30% of the server's time; phase 3 at 2 server lanes sealed
7 pages an hour while the agent took 73 turns beside it, and 17-21 pages an
hour with no agent (the server's queue was not recorded, so that the agent
caused all of the gap is not proven).

So the agent does not read logs and pages turn after turn while a step runs.
It calls this script again and again.  One call blocks for up to --timeout
seconds (default 570, under Qwen Code's 600 s cap on a shell call), looks at
files and /proc between sleeps, asks no model and opens no connection, and
prints ONE line: done or not, pages sealed out of how many, pages per hour,
failures, and the run report when done, with the WARNING lines the step
printed (they say what to do once it is done, and the agent no longer reads
the log).

    python3 scripts/wait_for_run.py OUTPUT LOG [--progress BOOK]

OUTPUT is what the step writes: proofread_pages.py's output directory,
book_profile.py's profile (also variant_vote.py's), an OCR runner's output
directory (run_paddleocr_vl.py or run_hunyuanocr.py, directly or under
run_ocr_phase.py), or finish_book.py's book folder.  LOG is the file the step's output goes to (`> LOG 2>&1`),
a new one for each launch.

With --progress BOOK, while it waits on phase 3 (proofread_pages.py) it
also rebuilds BOOK/proofreading.md (scripts/build_progress.py: the pages
sealed in OUTPUT as proofread, every other page as the draft) every
--progress-every seconds (default 300) and once more when it returns, and
its line ends with the file and the pages proofread.  The user reads that
file instead of waiting for the end of the book.  A progress file that cannot
be built is said on the line and changes nothing else: the exit code is the
step's.

The step is running while a process runs one of those scripts with OUTPUT as
the thing it writes - its arguments read with the script's own parser,
relative paths against the process's working directory, so a proofread run
that only reads a profile (--profile) is not the profile being built - or
while any process still writes LOG.  finish_book.py sends its steps' output to
its own log (BOOK/finish/finish-book.log), whose `[finish] step K of 4` lines
the running line shows; its RESULT line (in LOG, and in its own log) says how
it ended.  When none is left, the log's last lines
say how the step ended: its report line, the book profile's last step, the OCR
phase's RESULT line, an ERROR or a traceback.  With none of them the process
was killed or died, and the line says so; nothing here waits for a process
that is gone.  A book profile whose variant vote was due - by its arguments,
or by the variants note the profile itself carries when the wait never saw
them - ends only with the vote's line.  When a process of the step was seen writing another file than
LOG, that file is read instead; with no log at all nothing is guessed (exit 2),
since a finished step and a killed one then look alike.

Exit codes:
    0   done: the step finished and no page failed
    1   finished with failures: failed or blocked pages, an ERROR, a traceback,
        a variant vote whose calls all failed, a server not restored; or the
        step did not start (its parser refused the arguments, no such script
        or command).  Read the line, the report and the end of the log; do
        not just run it again
    2   cannot tell: this script's own arguments are wrong, or no process runs
        the step and LOG does not exist (a wrong path).  Check both paths; do
        not run the step again for this
    4   stopped before it finished: no process runs the step and the log has
        no last line of it (killed, interrupted or died), or an OCR call spent
        its time budget.  Run the SAME command again; sealed pages are kept
    75  still running when the wait ran out: call this script again
"""

from __future__ import annotations

import argparse
import contextlib
from dataclasses import dataclass
import importlib
import io
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable, Sequence

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

EXIT_DONE, EXIT_FAILED, EXIT_USAGE, EXIT_STOPPED, EXIT_RUNNING = 0, 1, 2, 4, 75
DEFAULT_TIMEOUT = 570.0
DEFAULT_INTERVAL = 15.0
# A process launched a moment ago may not be in /proc yet; nothing is called
# stopped within this many seconds of the wait's start.
START_GRACE = 10.0
# The end of the log that is read (a whole book's proofread log is well under this).
LOG_TAIL_BYTES = 4 << 20

# How often a wait on phase 3 rebuilds the progress file (--progress), in
# seconds; it is rebuilt once more when the wait returns.  A rebuild reads the
# book's sealed pages and engine B's (measured: 1.1 s for a 488-page book, all
# sealed), so the file is never more than a few minutes behind.
PROGRESS_EVERY = 300.0

# Script -> (kind of step, module, the argument naming what it writes).
SCRIPTS = {
    "proofread_pages.py": ("proofread", "proofread_pages", "output_directory"),
    "book_profile.py": ("profile", "book_profile", "profile"),
    "variant_vote.py": ("profile", "variant_vote", "profile"),
    "run_paddleocr_vl.py": ("ocr", "run_paddleocr_vl", "output_directory"),
    "run_hunyuanocr.py": ("ocr", "run_hunyuanocr", "output_directory"),
    "finish_book.py": ("finish", "finish_book", "book"),
}
LABEL = {"proofread": "proofread_pages.py", "ocr": "the OCR runner", "profile": "book_profile.py",
         "finish": "finish_book.py"}
# The file each runner seals beside page-NNNN.json, which it writes last.
SEAL_PARTNER = {"proofread": ".md", "ocr": ".txt"}

PAGE_SEAL = re.compile(r"page-(\d{4,})\.json")
PAGE_LINE = re.compile(r"^\s*page \d{4,}: ")
FAILED_LINE = re.compile(r"^\s*page \d{4,}: FAILED")
SUMMARY_LINE = re.compile(r"requested (\d+) \| completed (\d+) \| skipped (\d+) \| blocked (\d+) \| "
                          r"failed (\d+)(?: \| deferred (\d+))?")
ENDINGS = (
    ("phase", re.compile(r"^\[ocr-phase\] RESULT exit=(-?\d+)\s*(.*)$")),
    ("finish", re.compile(r"^\[finish\] RESULT exit=(-?\d+)\s*(.*)$")),
    ("report", re.compile(r"^\s*report: (.+?)\s*$")),
    ("error", re.compile(r"^\s*ERROR (.*)$")),
    ("profile", re.compile(r"^\s*profile: (.+?) \(([\d.]+)s\)\s*$")),
    ("vote", re.compile(r"^\s*(variant vote(?: \(dry run\))?: .*|variant vote off: .*)$")),
    ("vote-failed", re.compile(r"^\s*WARNING (variant vote: .*)$")),
    # The step did not start: its parser refused the arguments (argparse's
    # "PROG: error: ..."), Python found no such script, or the shell found no
    # such command.  The same command fails the same way.
    ("refused", re.compile(r"^(\S+\.py): error: (.*)$")),
    ("no-script", re.compile(r"^\S+: can't open file '(.+)': (\[Errno \d+\] .*)$")),
    ("no-command", re.compile(r"^\S*sh: (?:line \d+: |\d+: )?(.+?): (command not found|not found|"
                              r"No such file or directory|Permission denied)$")),
)
TRACEBACK_LINE = "Traceback (most recent call last):"
# A step's own warnings (proofread_pages.py: the profile's pair classes are
# stale, the engine preference no longer holds on the audit pages; the OCR
# phase's GPU warnings): each says what to do once the step is done.
WARNING_LINE = re.compile(r"^\s*WARNING (.*)$")
WARNINGS_SHOWN = 3
# finish_book.py: the line that starts a run in its own log (which it
# appends to), a step's line, and its exit codes that mean "run it again".
FINISH_START = re.compile(r"^\[finish\] \d{4}-\d{2}-\d{2}T")
FINISH_STEP = re.compile(r"^\[finish\] (step \d+ of \d+)(?: (done))?: ?(.*)$")
FINISH_AGAIN = (4, 6)
# The book profile's steps, each with the line book_profile.py prints when it
# is done; the variant vote follows once the profile is written.
PROFILE_STEPS = (
    ("probing", "aligning the two drafts"),
    ("layout:", "surveying the layout"),
    ("variants:", "classifying variant pairs"),
    ("engines:", "reading engine disagreements on crops"),
    ("notation:", "surveying the notation"),
)


@dataclass
class Step:
    """One process running the watched step."""
    pid: int
    script: str
    kind: str | None               # None: known only as a process writing LOG
    started: float                 # epoch seconds
    pages: list[int] | None        # the pages it was asked for; None when unknown
    overwrite: bool
    vote: bool                     # a book profile that runs the variant vote
    stdout: str | None = None      # the regular file its output goes to


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("output", type=Path,
                        help="what the step writes: proofread_pages.py's output directory, book_profile.py's "
                             "profile, an OCR runner's output directory, or finish_book.py's book folder")
    parser.add_argument("log", type=Path, help="the file the step's output goes to (> LOG 2>&1)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help=f"seconds to wait at most (default {DEFAULT_TIMEOUT:.0f}); keep it under the "
                             "harness's time limit for one shell call")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL,
                        help=f"seconds between checks (default {DEFAULT_INTERVAL:.0f})")
    parser.add_argument("--progress", type=Path, metavar="BOOK",
                        help="waiting on phase 3 (OUTPUT is proofread_pages.py's output folder): rebuild "
                             "BOOK/proofreading.md (scripts/build_progress.py) every --progress-every "
                             "seconds and when the wait returns, and end the line with it and the pages "
                             "proofread")
    parser.add_argument("--progress-every", type=float, default=PROGRESS_EVERY,
                        help=f"seconds between rebuilds of the progress file (default {PROGRESS_EVERY:.0f})")
    arguments = parser.parse_args(argv)
    if arguments.timeout < 0 or arguments.interval <= 0 or arguments.progress_every <= 0:
        parser.error("--timeout must be at least 0, --interval and --progress-every above 0")
    output = real(arguments.output)
    progress = (ProgressFile(real(arguments.progress), output, arguments.progress_every)
                if arguments.progress is not None else None)
    code, line = wait(output, real(arguments.log), arguments.timeout, arguments.interval,
                      progress.tick if progress else None)
    if progress is not None and code != EXIT_USAGE:
        line += progress.last_line()
    print(f"[wait] RESULT exit={code} {line}", flush=True)
    return code


class ProgressFile:
    """The progress file of a book whose phase 3 the wait watches
    (--progress): rebuilt every EVERY seconds while the step runs, and once
    more when the wait returns."""

    def __init__(self, book: Path, output: Path, every: float):
        self.book, self.output, self.every = book, output, every
        self.kind: str | None = None
        self.built: float = time.monotonic()      # the last call built it on return
        self.said = ""

    def tick(self, kind: str, running: bool) -> None:
        self.kind = kind
        if running and kind == "proofread" and time.monotonic() - self.built >= self.every:
            self.build()

    def build(self) -> None:
        self.built = time.monotonic()
        try:
            import build_progress   # noqa: PLC0415 - only a wait with --progress reads the pages
            made = build_progress.build(self.book, self.output)
            self.said = f"; progress file {made.path}: {made.proofread}/{made.total} pages proofread"
        except Exception as error:  # noqa: BLE001 - the progress file never changes the wait's answer
            self.said = f"; progress file NOT rebuilt ({type(error).__name__}: {clip(str(error))})"

    def last_line(self) -> str:
        """What the wait's line ends with: the file rebuilt now, for phase 3."""
        if self.kind != "proofread":
            return ""
        self.build()
        return self.said


def wait(output: Path, log: Path, timeout: float, interval: float,
         tick: Callable[[str, bool], None] | None = None) -> tuple[int, str]:
    """Wait for the step; TICK(kind, running) is called at each check."""
    began = time.monotonic()
    deadline = began + timeout
    seen: dict[int, Step] = {}
    while True:
        steps = find_steps(output, log)
        for step in steps:
            seen.setdefault(step.pid, step)
        known = list(seen.values())
        written = log_of(log, known)
        kind = kind_of(output, written, known)
        if tick is not None:
            tick(kind, bool(steps))
        if steps:
            if time.monotonic() >= deadline:
                line = running_line(output, written, kind, steps)
                if written != log and kind != "finish":
                    line += f" (its output goes to {written}, not {log})"
                return EXIT_RUNNING, line
        else:
            ending = step_ending(output, written, kind, known)
            if ending is not None:
                return ending
            if not known and time.monotonic() - began < min(START_GRACE, timeout):
                time.sleep(min(1.0, interval))
                continue
            if not written.is_file():
                # Without the log, a finished step and a killed one look alike;
                # saying "stopped" would have a finished step run again.
                return EXIT_USAGE, (f"CANNOT TELL: no process runs the step that writes {output}, and its log "
                                    f"{written} does not exist - pass the file its output went to")
            return EXIT_STOPPED, stopped_line(output, written, kind, known)
        time.sleep(max(0.0, min(interval, deadline - time.monotonic())))


# --- processes -------------------------------------------------------------

def find_steps(output: Path, log: Path) -> list[Step]:
    """Every live process that runs one of SCRIPTS writing OUTPUT, or whose
    output goes to LOG (a run whose arguments cannot be read is still not
    called stopped while it writes its log)."""
    steps = []
    me = os.getpid()
    boot = boot_time()
    try:
        pids = [int(entry.name) for entry in os.scandir("/proc") if entry.name.isdigit()]
    except OSError:
        return []
    names = tuple(name.encode() for name in SCRIPTS)
    for pid in pids:
        if pid == me:
            continue
        try:
            raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        except OSError:
            continue
        named = any(name in raw for name in names)
        writes_log = not named and writes_to(pid, log)
        if not (named or writes_log):
            continue
        status = process_status(pid, boot)
        if status is None or status[0] in "ZX":
            continue                # gone, or exited and not yet reaped
        argv = [part.decode("utf-8", "surrogateescape") for part in raw.rstrip(b"\0").split(b"\0")]
        step = read_step(pid, argv, status[1], output) if named else None
        if step is None and (writes_log or writes_to(pid, log)):
            script = next((os.path.basename(word) for word in argv if word.endswith(".py")),
                          os.path.basename(argv[0]) if argv else "?")
            step = Step(pid, script, None, status[1], None, False, False)
        if step is not None:
            steps.append(step)
    return steps


def writes_to(pid: int, log: Path) -> bool:
    """Whether the process's standard output or error is LOG."""
    for fd in (1, 2):
        try:
            target = os.readlink(f"/proc/{pid}/fd/{fd}")
        except OSError:
            continue
        if target.startswith("/") and os.path.realpath(target) == str(log):
            return True
    return False


def boot_time() -> float:
    """Epoch seconds at boot, to the hundredth (/proc/stat's btime is whole
    seconds, too coarse to tell a page sealed just before a run from one it
    sealed)."""
    try:
        return time.time() - float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return 0.0


def process_status(pid: int, boot: float) -> tuple[str, float] | None:
    """The process's state letter and start time (epoch seconds)."""
    try:
        raw = Path(f"/proc/{pid}/stat").read_text()
        fields = raw[raw.rindex(")") + 2:].split()
        return fields[0], boot + int(fields[19]) / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError):
        return None


def read_step(pid: int, argv: list[str], started: float, output: Path) -> Step | None:
    """ARGV read as the step that writes OUTPUT, or None.  The first argument
    that names one of SCRIPTS is the script (so run_ocr_phase.py's own command
    line counts as the runner it wraps); the rest is read by that script's own
    parser."""
    try:
        cwd = os.readlink(f"/proc/{pid}/cwd")
    except OSError:
        cwd = None
    for index, word in enumerate(argv):
        script = os.path.basename(word)
        if script not in SCRIPTS:
            continue
        kind, module_name, destination = SCRIPTS[script]
        try:
            module = importlib.import_module(module_name)
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                namespace, _ = module.build_parser().parse_known_args(argv[index + 1:])
        except (Exception, SystemExit):  # noqa: BLE001 - not a run of this script (an editor, a grep)
            return None
        if absolute(getattr(namespace, destination, None), cwd) != output:
            return None
        return Step(pid, script, kind, started, requested_pages(module, script, namespace, cwd),
                    bool(getattr(namespace, "overwrite", False)),
                    script == "book_profile.py" and not getattr(namespace, "no_variant_vote", False),
                    stdout_file(pid))
    return None


def requested_pages(module: Any, script: str, namespace: argparse.Namespace, cwd: str | None) -> list[int] | None:
    """The pages a proofread or OCR run was asked for, by its own selection."""
    if SCRIPTS[script][0] == "profile":
        return None
    renders = absolute(getattr(namespace, "render_directory", None), cwd)
    if renders is None:
        return None
    namespace.render_directory = renders
    try:
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            if script == "proofread_pages.py":
                return list(module.parse_pages(namespace, renders))
            return list(module.selected_pages(namespace, renders)[0])
    except Exception:  # noqa: BLE001 - the run itself reports a bad selection
        return None


def stdout_file(pid: int) -> str | None:
    try:
        target = os.readlink(f"/proc/{pid}/fd/1")
    except OSError:
        return None
    return os.path.realpath(target) if target.startswith("/") and os.path.isfile(target) else None


def absolute(value: Any, cwd: str | None) -> Path | None:
    if value is None:
        return None
    path = Path(os.path.expanduser(str(value)))
    if not path.is_absolute():
        if cwd is None:
            return None
        path = Path(cwd) / path
    return Path(os.path.realpath(path))


def real(path: Path) -> Path:
    return Path(os.path.realpath(os.path.expanduser(str(path))))


# --- files -----------------------------------------------------------------

def kind_of(output: Path, log: Path, known: list[Step]) -> str:
    kinds = [step.kind for step in known if step.kind]
    if kinds:
        return kinds[0]
    if output.is_file() or output.suffix == ".json":
        return "profile"
    if finish_log(output).is_file() or any(pattern.match(line) for line in read_log(log) or []
                                           for name, pattern in ENDINGS if name == "finish"):
        return "finish"
    if seals(output, "ocr"):
        return "ocr"
    if any(pattern.match(line) for line in read_log(log) or [] for name, pattern in ENDINGS if name == "phase"):
        return "ocr"
    return "proofread"


def log_of(log: Path, known: list[Step]) -> Path:
    """LOG, unless a process of the step was seen writing another file: then
    that file, whose last lines are the step's."""
    files = [step.stdout for step in known if step.stdout]
    return log if not files or str(log) in files else Path(files[0])


def seals(directory: Path, kind: str) -> dict[int, float]:
    """Sealed pages in DIRECTORY and their seal times: page-NNNN.json beside
    its partner file."""
    partner = SEAL_PARTNER.get(kind)
    if partner is None:
        return {}
    try:
        names = set(os.listdir(directory))
    except OSError:
        return {}
    out = {}
    for name in names:
        match = PAGE_SEAL.fullmatch(name)
        if match and f"page-{match.group(1)}{partner}" in names:
            try:
                out[int(match.group(1))] = os.stat(directory / name).st_mtime
            except OSError:
                pass
    return out


def read_log(log: Path) -> list[str] | None:
    try:
        with open(log, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - LOG_TAIL_BYTES))
            data = handle.read()
    except OSError:
        return None
    return data.decode("utf-8", "replace").splitlines()


def read_report(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    try:
        report = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return report if isinstance(report, dict) else {}


def wanted_pages(steps: list[Step]) -> set[int] | None:
    """The pages the runs were asked for together; None when any is unknown."""
    if not steps or any(step.pages is None for step in steps):
        return None
    return set().union(*(step.pages for step in steps))


# --- lines -----------------------------------------------------------------

def running_line(output: Path, log: Path, kind: str, steps: list[Step]) -> str:
    now = time.time()
    started = min(step.started for step in steps)
    script = next((step.script for step in steps if step.kind), steps[0].script)
    tail = f"running {duration(now - started)} - call wait_for_run.py again"
    lines = read_log(log) or []
    if kind == "profile":
        return f"RUNNING {script}: {profile_progress(output, lines, steps)}; {tail}"
    if kind == "finish":
        return f"RUNNING {script}: {finish_progress(output)}; {tail}"
    sealed = seals(output, kind)
    this_run = {page: when for page, when in sealed.items() if when >= started}
    counted = this_run if any(step.overwrite for step in steps) else sealed
    wanted = wanted_pages([step for step in steps if step.kind])
    progress = (f"{sum(1 for page in counted if page in wanted)}/{len(wanted)} pages sealed" if wanted is not None
                else f"{len(counted)} pages sealed")
    rate = len(this_run) / max((now - started) / 3600, 1e-9)
    failed = sum(1 for line in lines if FAILED_LINE.match(line))
    last = (f"last seal {duration(now - max(this_run.values()))} ago" if this_run
            else "no page sealed yet in this run")
    return (f"RUNNING {script}: {progress} ({len(this_run)} this run, {rate:.1f} pages/h), "
            f"{failed} failed, {last}; {tail}")


def profile_progress(output: Path, lines: list[str], steps: list[Step]) -> str:
    if any(step.script == "variant_vote.py" for step in steps):
        return "variant vote"
    vote = any(step.vote for step in steps)
    total = len(PROFILE_STEPS) + (1 if vote else 0)
    try:
        written = output.stat().st_mtime >= min(step.started for step in steps)
    except OSError:
        written = False
    done = [marker for marker, _ in PROFILE_STEPS if any(line.strip().startswith(marker) for line in lines)]
    missing = [(number, what) for number, (marker, what) in enumerate(PROFILE_STEPS, 1) if marker not in done]
    if vote and (written or not missing):
        return f"step {total} of {total} (variant vote; the profile is written)"
    number, what = missing[0] if missing else (len(PROFILE_STEPS), "writing the profile")
    return f"step {number} of {total} ({what})"


def finish_log(output: Path) -> Path:
    """finish_book.py's own log in the book folder OUTPUT."""
    return output / "finish" / "finish-book.log"


def finish_run_lines(output: Path) -> list[str]:
    """The lines of finish_book.py's last run in its own log (it appends)."""
    lines = read_log(finish_log(output)) or []
    start = max((index for index, line in enumerate(lines) if FINISH_START.match(line)), default=0)
    return lines[start:]


def finish_progress(output: Path) -> str:
    """Which step finish_book.py is on, from its own log; during the repair,
    how many model answers the repair folder holds."""
    steps = [match for match in map(FINISH_STEP.match, finish_run_lines(output)) if match]
    if not steps:
        return "starting"
    last = steps[-1]
    said = f"{last.group(1)} done" if last.group(2) else f"{last.group(1)} ({clip(last.group(3), 90)})"
    if not last.group(2) and "repair" in last.group(3):
        try:
            with open(output / "repaired" / "answers.jsonl", "rb") as handle:
                answers = sum(1 for line in handle if line.strip())
        except OSError:
            answers = 0
        said += f", {answers} model answer(s) in repaired/answers.jsonl"
    return said


def finish_ending(output: Path, match: re.Match, warned: str) -> tuple[int, str]:
    """The wait's line for finish_book.py's RESULT line MATCH."""
    code = int(match.group(1))
    said = re.sub(r"^(?:DONE|FAILED|STOPPED|NOT READY) finish_book\.py: ", "", match.group(2).strip())
    if code == 0:
        return EXIT_DONE, (f"DONE finish_book.py: {clip(said, 300)}; final text {output / 'final.md'}, doubt list "
                           f"{output / 'doubts.md'}{warned}")
    if code in FINISH_AGAIN:
        return EXIT_STOPPED, f"STOPPED finish_book.py: exit {code}: {clip(said, 300)}{warned}"
    if code == 3:
        return EXIT_FAILED, f"FAILED finish_book.py: not ready: {clip(said, 300)}{warned}"
    return EXIT_FAILED, f"FAILED finish_book.py: exit {code}: {clip(said, 300)}{warned}"


def step_ending(output: Path, log: Path, kind: str, known: list[Step]) -> tuple[int, str] | None:
    """How the step ended, from the last lines of its log; None when the log
    has no last line of it."""
    lines = read_log(log)
    if kind == "finish" and lines:
        # finish_book.py's own log holds its earlier runs too: only the last.
        start = max((index for index, line in enumerate(lines) if FINISH_START.match(line)), default=0)
        lines = lines[start:]
    if not lines:
        return None
    last_page = max((index for index, line in enumerate(lines) if PAGE_LINE.match(line)), default=-1)
    tail = lines[last_page + 1:]
    script = next((step.script for step in known if step.kind), LABEL[kind])
    events: list[tuple[int, str, Any]] = []
    for index, line in enumerate(tail):
        for name, pattern in ENDINGS:
            match = pattern.match(line)
            if match:
                events.append((index, name, match))
        if line.strip() == TRACEBACK_LINE:
            events.append((index, "traceback", None))
    if not events:
        return None
    summary = next((match for match in map(SUMMARY_LINE.search, reversed(tail)) if match), None)
    report = next((match.group(1) for _, name, match in reversed(events) if name == "report"), None)
    if not any(step.kind for step in known):
        # Ended before the wait saw it: an OCR runner's report names it.
        runner = (read_report(report).get("tool") or {}).get("runner")
        script = os.path.basename(runner) if isinstance(runner, str) and runner else script
    index, name, match = events[-1]
    if name == "traceback":
        exception = next((line.strip() for line in reversed(tail[index:]) if line.strip()), "")
        if exception.startswith("KeyboardInterrupt"):
            return EXIT_STOPPED, (f"STOPPED {script}: interrupted ({clip(exception)}); "
                                  f"{progress_on_disk(output, kind, known)} - run the SAME command again; "
                                  "sealed pages are kept")
        return EXIT_FAILED, f"FAILED {script}: it crashed: {clip(exception)} - read the end of {log}"
    if name == "error":
        return EXIT_FAILED, f"FAILED {script}: ERROR {clip(match.group(1))} - read {log}"
    if name in ("refused", "no-script", "no-command"):
        if name == "refused":
            script = match.group(1)
            why = f"it refused its arguments: {clip(match.group(2))} - fix the command (see its --help)"
        elif name == "no-script":
            script = os.path.basename(match.group(1))
            why = (f"python cannot open {clip(match.group(1))} ({clip(match.group(2))}) - fix the script's "
                   "path or the folder the command runs in")
        else:
            why = f"the shell says {clip(match.group(1))}: {match.group(2)} - fix the command"
        return EXIT_FAILED, (f"FAILED {script}: it did not start: {why}; the same command fails the same way, "
                             "do not just run it again")
    # The step ran to its end (or to its time budget): what it warned of too.
    if name == "finish":
        own = finish_run_lines(output)
        return finish_ending(output, match, warnings_said(own, finish_log(output)) if own else "")
    if name == "vote-failed":
        return EXIT_FAILED, (f"FAILED {script}: the profile is written, but {clip(match.group(1))} "
                             "(is the server up?)" + warnings_said(lines, log, match.group(1).strip()))
    warned = warnings_said(lines, log)
    if name == "phase":
        code = int(match.group(1))
        counts = finished_counts(summary, report, output, kind)
        if code == 0:
            return EXIT_DONE, f"DONE {script}: {counts}{warned}"
        if code == 75:
            return EXIT_STOPPED, (f"STOPPED {script}: the OCR call spent its time budget ({counts}) - run the "
                                  f"SAME command again; sealed pages are kept{warned}")
        return EXIT_FAILED, (f"FAILED {script}: run_ocr_phase.py exit {code} {clip(match.group(2))}; "
                             f"{counts}{warned}")
    if name == "report":
        counts = finished_counts(summary, report, output, kind)
        if summary and (int(summary.group(4)) or int(summary.group(5))):
            return EXIT_FAILED, (f"FAILED {script}: finished with failed or blocked pages: {counts} - read the "
                                 f"report's pages[] errors, do not just run it again{warned}")
        if summary and summary.group(6) and int(summary.group(6)):
            return EXIT_STOPPED, (f"STOPPED {script}: {summary.group(6)} page(s) left by the time budget; "
                                  f"{counts} - run the SAME command again; sealed pages are kept{warned}")
        return EXIT_DONE, f"DONE {script}: {counts}{warned}"
    profile = next((m for _, n, m in events if n == "profile"), None)
    written = (f"profile {profile.group(1)} written in {duration(float(profile.group(2)))}" if profile
               else None)
    if name == "vote":
        return EXIT_DONE, (f"DONE {script}: " + "; ".join(filter(None, (written, clip(match.group(1).strip()))))
                           + warned)
    if name == "profile":
        if any(step.vote for step in known) or vote_due(match.group(1), output):
            # The vote follows the profile and prints its line when it ends,
            # also when it rules nothing; none means it was killed or died.
            return EXIT_STOPPED, (f"STOPPED {script}: {written}, but the variant vote after it did not finish "
                                  "(no vote line in the log: killed or died) - run the SAME command again; "
                                  f"phase 3 needs the vote's rulings{warned}")
        # Nothing follows the profile when the vote is off.
        return EXIT_DONE, f"DONE {script}: {written} (no variant vote in the log){warned}"
    return None


def vote_due(profile: str, output: Path) -> bool:
    """Whether the book profile PROFILE (the path its log line names) was
    written by a run that votes on the variant pairs after it.

    A wait that saw the process knows from its arguments; one that did not (it
    started after the process ended, or knew it only as a writer of LOG) reads
    the profile itself, whose variants note book_profile.py sets to
    VARIANT_NOTE_VOTE when the vote is on.  A profile that cannot be read, or
    one from before the vote existed, says no vote, as before."""
    path = Path(profile) if os.path.isabs(profile) else output
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        note = (data.get("variants") or {}).get("note") if isinstance(data, dict) else None
        if note is None:
            return False
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            return note == importlib.import_module("book_profile").VARIANT_NOTE_VOTE
    except Exception:  # noqa: BLE001 - unreadable: no vote known to be due
        return False


def warnings_said(lines: list[str], log: Path, ending: str | None = None) -> str:
    """The step's WARNING lines, which the agent no longer reads in the log:
    how many, the first few (the head and the tail, where the advice is) and
    how to read them all; "" when there are none.  ENDING is a warning the
    line already says."""
    found = [match.group(1).strip() for match in map(WARNING_LINE.match, lines) if match]
    found = [text for text in found if text != ending]
    if not found:
        return ""
    distinct = list(dict.fromkeys(found))
    shown = "; ".join(f"'{clip_middle(text)}'" for text in distinct[:WARNINGS_SHOWN])
    more = f"; and {len(distinct) - WARNINGS_SHOWN} more" if len(distinct) > WARNINGS_SHOWN else ""
    return (f"; {len(found)} WARNING line(s) - read them before the next step "
            f"(grep -n WARNING {log}): {shown}{more}")


def finished_counts(summary: re.Match | None, report: str | None, output: Path, kind: str) -> str:
    """Pages sealed out of how many, pages per hour, failures and the report,
    from the run's summary line and report."""
    data = read_report(report)
    counts = data.get("counts") or {}
    if summary:
        requested, completed, skipped, blocked, failed = (int(summary.group(n)) for n in range(1, 6))
    elif counts:
        requested, completed, skipped, blocked, failed = (int(counts.get(key) or 0) for key in (
            "requested", "completed", "skippedCurrent", "blocked", "failed"))
    else:
        return f"{len(seals(output, kind))} pages sealed; no run report"
    seconds = data.get("wallSeconds") or data.get("durationSeconds")
    rate = f", {completed / (float(seconds) / 3600):.1f} pages/h" if seconds and completed else ""
    where = f"report {report}" if report else "no run report"
    return (f"{completed + skipped}/{requested} pages sealed ({completed} this run{rate}), "
            f"{failed} failed, {blocked} blocked; {where}")


def progress_on_disk(output: Path, kind: str, known: list[Step]) -> str:
    if kind == "finish":
        return f"its last step: {finish_progress(output)}"
    if kind == "profile":
        if not output.is_file():
            return "no profile written"
        if known and output.stat().st_mtime < min(step.started for step in known):
            return f"{output.name} is from an earlier run"
        return f"{output.name} exists"
    sealed = seals(output, kind)
    if any(step.overwrite for step in known):
        started = min(step.started for step in known)
        sealed = {page: when for page, when in sealed.items() if when >= started}
    wanted = wanted_pages([step for step in known if step.kind])
    if wanted is not None:
        return f"{sum(1 for page in sealed if page in wanted)}/{len(wanted)} pages sealed"
    return f"{len(sealed)} pages sealed"


def stopped_line(output: Path, log: Path, kind: str, known: list[Step]) -> str:
    script = next((step.script for step in known if step.kind), LABEL[kind])
    last = next((line.strip() for line in reversed(read_log(log) or []) if line.strip()), None)
    said = f"; last log line: {clip(last)}" if last else f"; {log} is empty or missing"
    kept = "what it finished is kept" if kind == "finish" else "sealed pages are kept"
    return (f"STOPPED {script}: no process runs it and its log has no last line of it (killed or died); "
            f"{progress_on_disk(output, kind, known)}{said} - run the SAME command again; {kept}")


def duration(seconds: float) -> str:
    seconds = max(0.0, seconds)
    if seconds < 120:
        return f"{seconds:.0f} s"
    if seconds < 7200:
        return f"{seconds / 60:.0f} min"
    return f"{seconds / 3600:.1f} h"


def clip(text: str, size: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= size else text[:size - 1] + "…"


def clip_middle(text: str, size: int = 160) -> str:
    """TEXT cut in the middle, keeping its start and its end."""
    text = " ".join(text.split())
    if len(text) <= size:
        return text
    head = (size - 3) // 2
    start, end = text[:head], text[len(text) - (size - 3 - head):]
    # Cut at spaces where there are any, not inside a word.
    start = start.rsplit(" ", 1)[0] if " " in start else start
    end = end.split(" ", 1)[-1] if " " in end else end
    return start + " … " + end


if __name__ == "__main__":
    sys.exit(main())
