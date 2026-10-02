#!/usr/bin/env python3
"""Offline check of scripts/wait_for_run.py on made-up output folders.

No GPU, no model, no server: each case writes a made-up book folder in a
temporary directory and starts a stand-in process under the name of the real
script (proofread_pages.py, book_profile.py, run_ocr_phase.py and
run_paddleocr_vl.py), which seals pages and prints the lines the real script
prints, then ends the way the case says - with its report, killed, crashed,
with failed pages, or not at all.  wait_for_run.py reads the stand-in's
arguments with the real script's parser, as it would a real run's.  One
launcher runs the real book_profile.main() with its model steps stubbed, so
its log lines and the profile it writes are the real script's; the real
scripts' parsers refuse a wrong option before any file or model call.

Each case checks the exit code, that exactly one line is printed, what the
line says, and that the wait returns promptly when the process ends instead
of sitting out its timeout.

Also checked: the script opens no connection, and SKILL.md's 〈安全並行〉 tells
the agent to wait with it instead of reading logs and sealed pages, with the
measured cost, every exit code the script has and no other (a step that did
not start is exit 1, exit 2 only this script's own arguments), and the rules
that were there before (the handover in the foreground, no run_ocr_phase.py
while a step runs, Qwen Code killing background shells on exit).

Usage:
    python3 tests/check_wait_for_run.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import textwrap
import time

ROOT = Path(__file__).resolve().parent.parent
WAIT = ROOT / "scripts" / "wait_for_run.py"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
# Every process this check starts inherits a pair-class store of this
# process's own and an endpoint nothing listens on (tests/offline.py).
import offline  # noqa: E402,F401

# The stand-ins take what to do from STAND_IN_PLAN (JSON); their command-line
# arguments are only there for wait_for_run.py to read.
COMMON = '''
import json, os, signal, subprocess, sys, time
from pathlib import Path
plan = json.loads(os.environ["STAND_IN_PLAN"])

def end(kind):
    if kind == "kill":
        os.kill(os.getpid(), signal.SIGKILL)
    if kind == "hang":
        time.sleep(120)
    if kind == "traceback":
        raise RuntimeError("stand-in crash")
    if kind == "interrupt":
        raise KeyboardInterrupt
'''

PROOFREAD = COMMON + '''
out = Path(plan["output"])
if plan.get("end") == "error":
    print("ERROR render directory does not exist: " + plan["output"], file=sys.stderr)
    sys.exit(2)
out.mkdir(parents=True, exist_ok=True)
if plan.get("warnings"):        # proofread_pages.py's own two WARNING lines
    print("  WARNING 3 pair(s) are classified differently by the variant lists than by this profile (e.g. "
          "甲|乙, 丙|丁, 戊|己); merging follows the lists, but rebuild the profile (book_profile.py), which "
          "votes on them", flush=True)
print("  engine preference A (from profile book-profile.json); audit every 20", flush=True)
print(f"  proofreading {len(plan['pages'])} page(s), 2 in flight, effort=xhigh", flush=True)
started = time.monotonic()
for page in plan["pages"]:
    time.sleep(plan.get("delay", 0.2))
    (out / f"page-{page:04d}.md").write_text("text\\n")
    (out / f"page-{page:04d}.json").write_text("{}\\n")
    print(f"  page {page:04d}: 1.0s  clean=True  adjudicated=0  calls=3  reasoning=100", flush=True)
for page in plan.get("failed", []):
    print(f"  page {page:04d}: FAILED stand-in page failure", file=sys.stderr, flush=True)
end(plan.get("end"))
failed = len(plan.get("failed", []))
report = Path(plan["report"])
report.write_text(json.dumps({"counts": {"requested": plan["requested"], "completed": len(plan["pages"]),
                                         "skippedCurrent": 0, "blocked": 0, "failed": failed},
                              "wallSeconds": round(time.monotonic() - started, 1)}))
print(f"  requested {plan['requested']} | completed {len(plan['pages'])} | skipped 0 | blocked 0 | "
      f"failed {failed}", flush=True)
print(f"  wall 1.0s -> 1.0s/page effective", flush=True)
if plan.get("warnings"):
    audit = {"every": 20, "pages": plan["pages"], "preferEngine": "A", "votes": {"A": 1, "B": 4},
             "drift": True}
    print(f"  WARNING engine preference A no longer holds on the audit pages ({audit}) - re-profile this "
          "part of the book", flush=True)
print(f"  report: {report}", flush=True)
sys.exit(1 if failed else 0)
'''

PROFILE = COMMON + '''
print("  probing 3 page(s) for engines: [1, 2, 3]; notation on [1, 2, 3]", flush=True)
print("  layout: 1 leaf/leaves per page, 0 running head(s) []", flush=True)
time.sleep(plan.get("classify", 0.2))
if plan.get("end") == "during-classify":
    end("kill")
print("  variants: 12 variant-form disagreement(s) in 2 pair(s); top []", flush=True)
print("  engines: distinct substitution pairs A 1 / B 0 -> adjudicate (too few pairs; ; excluded {})", flush=True)
print("  notation: 3 of 5 blocks, density bound from 0.2 marks/char", flush=True)
# The variants note book_profile.py writes: whether the vote follows.
Path(plan["profile"]).write_text(json.dumps({"variants": {"note": plan["note"]}}) + "\\n")
print(f"  profile: {plan['profile']} (1.5s)")        # no flush, as book_profile.py
if plan.get("vote", True):
    time.sleep(plan.get("voting", 0.2))
    end(plan.get("end"))
    print(f"  variant vote: 2 pair(s) ruled by the model, 0 left unruled, 0 ruled by a person kept; "
          f"6 call(s); {Path(plan['profile']).with_name('variant-rulings.json')} (1.0s)", flush=True)
'''

RUNNER = COMMON + '''
out = Path(plan["output"])
out.mkdir(parents=True, exist_ok=True)
for page in plan["pages"]:
    time.sleep(plan.get("delay", 0.2))
    (out / f"page-{page:04d}.txt").write_text("text\\n")
    (out / f"page-{page:04d}.json").write_text("{}\\n")
    print(f"  page {page:04d}: 4 chars in 0.2s", flush=True)
end(plan.get("end"))
skipped = plan.get("skipped", 0)
deferred = plan["requested"] - len(plan["pages"]) - skipped
report = Path(plan["report"])
report.write_text(json.dumps({"counts": {"requested": plan["requested"], "completed": len(plan["pages"]),
                                         "skippedCurrent": skipped, "blocked": 0, "failed": 0,
                                         "deferred": deferred}, "durationSeconds": 1.0,
                              "tool": {"runner": str(Path(sys.argv[0]).resolve())}}))
print(f"  requested {plan['requested']} | completed {len(plan['pages'])} | skipped {skipped} | blocked 0 | "
      f"failed 0 | deferred {deferred}", flush=True)
print(f"  report: {report}", flush=True)
sys.exit(75 if deferred else 0)
'''

PHASE = COMMON + '''
runner = sys.argv[sys.argv.index("--") + 1:]
code = subprocess.call(runner)
meaning = {0: "DONE", 75: "INCOMPLETE - time budget spent, finished pages are sealed, the server is up: "
                          "run the SAME command again"}.get(code, "FAILED")
print(f"[ocr-phase] RESULT exit={code} {meaning}", flush=True)
sys.exit(code)
'''

# The REAL book_profile.main() with its model steps stubbed (no client, no
# server): its log lines and the profile it writes are the real script's.  The
# variant vote only sleeps, to be killed in.
REAL_PROFILE = '''
import os, sys, time
sys.path.insert(0, os.environ["STAND_IN_SCRIPTS"])
import book_profile as bp
class NoClient:
    def __init__(self, *a, **k):
        self.model, self.effort = "stand-in", None
bp.pp.Client = NoClient
bp.page_candidates = lambda *a: [{"page": 1, "agreement": 1.0}]
bp.select_probe_pages = lambda *a: []
bp.survey_layout = lambda *a: {"leavesPerPage": 1, "runningHeads": []}
bp.collect_variants = lambda *a: ({"pairs": [], "variantOccurrences": 0, "pairSources": {}}, {})
bp.pp.draft_digest = lambda *a: "stand-in"
bp.survey_notation = lambda *a, **k: {"markBlocks": 0, "blocksSurveyed": 0, "doubled": False,
                                      "emphasis": None, "maxMarksPerCharacter": 0.1}
bp.variant_vote.rule_book = lambda *a, **k: time.sleep(120)
sys.exit(bp.main())
'''


class Book:
    """A made-up book folder with stand-in scripts in bin/."""

    def __init__(self, root: Path):
        self.root = root
        (root / "bin").mkdir()
        for name, text in (("proofread_pages.py", PROOFREAD), ("book_profile.py", PROFILE),
                           ("run_paddleocr_vl.py", RUNNER), ("run_ocr_phase.py", PHASE)):
            (root / "bin" / name).write_text(textwrap.dedent(text))
        (root / "bin" / "real").mkdir()
        (root / "bin" / "real" / "book_profile.py").write_text(textwrap.dedent(REAL_PROFILE))
        (root / "renders").mkdir()
        for page in range(1, 5):
            (root / "renders" / f"page-{page:04d}.png").write_bytes(b"")
        (root / "ocr-a").mkdir()
        (root / "ocr-b").mkdir()
        self.processes: list[subprocess.Popen] = []

    def start(self, argv: list[str], log: str, plan: dict) -> subprocess.Popen:
        """Start a stand-in the way the skill launches a background step:
        relative paths, output to LOG."""
        env = dict(os.environ, STAND_IN_PLAN=json.dumps(plan), STAND_IN_SCRIPTS=str(ROOT / "scripts"))
        handle = open(self.root / log, "wb")
        process = subprocess.Popen([sys.executable] + argv, cwd=self.root, env=env, stdout=handle,
                                   stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        handle.close()
        self.processes.append(process)
        return process

    def wait_for_line(self, log: str, text: str, limit: float = 10.0) -> None:
        stop = time.monotonic() + limit
        while not (self.root / log).is_file() or text not in (self.root / log).read_text(errors="replace"):
            assert time.monotonic() < stop, f"the stand-in never printed {text!r}"
            time.sleep(0.05)

    def watch(self, output: str, log: str, timeout: float = 30.0, cwd: Path | None = None
              ) -> tuple[int, str, float]:
        return self.watched(self.start_watch(output, log, timeout, cwd), timeout)

    def start_watch(self, output: str, log: str, timeout: float = 30.0, cwd: Path | None = None
                    ) -> tuple[subprocess.Popen, float]:
        """Start wait_for_run.py (from CWD, the book folder by default)."""
        began = time.monotonic()
        return subprocess.Popen([sys.executable, str(WAIT), output, log, "--timeout", str(timeout),
                                 "--interval", "0.2"], cwd=cwd or self.root, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True), began

    def watched(self, started: tuple[subprocess.Popen, float], timeout: float = 30.0) -> tuple[int, str, float]:
        """The exit code and line of a wait started with start_watch."""
        process, began = started
        stdout, stderr = process.communicate(timeout=timeout + 30)
        lines = stdout.splitlines()
        assert len(lines) == 1 and not stderr, \
            f"wait_for_run.py must print one line and nothing else: {stdout!r} {stderr!r}"
        assert lines[0].startswith(f"[wait] RESULT exit={process.returncode} "), lines[0]
        return process.returncode, lines[0], time.monotonic() - began

    def close(self) -> None:
        for process in self.processes:
            if process.poll() is None:
                process.kill()
            process.wait()


def proofread_argv(extra: list[str] | None = None) -> list[str]:
    return ["bin/proofread_pages.py", "renders", "ocr-a", "proofread", "--draft2-directory", "ocr-b",
            "--workers", "2"] + (extra or [])


def expect(problems: list[str], name: str, got: tuple[int, str, float], code: int, *patterns: str,
           within: float | None = None) -> None:
    returned, line, seconds = got
    wrong = [p for p in patterns if not re.search(p, line)]
    if returned != code or wrong or (within is not None and seconds > within):
        problems.append(f"{name}: exit {returned} (want {code}) in {seconds:.1f}s"
                        f"{f' (want under {within}s)' if within else ''}; missing {wrong}: {line}")
    print(f"{'FAIL' if problems and problems[-1].startswith(name + ':') else 'ok  '} {name} "
          f"({seconds:.1f}s): {line}")


def cases(problems: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        book = Book(Path(tmp))
        try:
            run_cases(book, problems)
        finally:
            book.close()


def run_cases(book: Book, problems: list[str]) -> None:
    import book_profile             # the variants notes the real profile carries
    root = book.root
    report = str(root / "proofread-run.json")

    # Finishes: the report line ends the wait, with its counts and path.  The
    # selection is every render (4 pages), as proofread_pages.py reads it.
    book.start(proofread_argv(), "p1.log", {"output": "proofread", "pages": [1, 2, 3, 4], "requested": 4,
                                            "report": report, "delay": 0.3})
    book.wait_for_line("p1.log", "proofreading")
    expect(problems, "finishes", book.watch("proofread", "p1.log"), 0, r"DONE proofread_pages\.py",
           r"4/4 pages sealed \(4 this run, [\d.]+ pages/h\)", r"0 failed, 0 blocked",
           re.escape(f"report {report}"), r"^(?!.*WARNING)", within=10)

    # Times out: still running at --timeout, with what is sealed out of how
    # many (--pages), the pages per hour and the pages that failed so far.
    long_run = book.start(proofread_argv(["--pages", "1-4", "--overwrite"]), "p2.log",
                          {"output": "proofread", "pages": [1, 2], "failed": [4], "requested": 4,
                           "report": report, "delay": 0.1, "end": "hang"})
    book.wait_for_line("p2.log", "FAILED")
    expect(problems, "times out", book.watch("proofread", "p2.log", timeout=1.5), 75,
           r"RUNNING proofread_pages\.py: 2/4 pages sealed \(2 this run, [\d.]+ pages/h\), 1 failed",
           r"last seal \d+ s ago", r"call wait_for_run\.py again", within=8)
    long_run.kill()
    long_run.wait()

    # Killed while the wait runs: said at once, not after the timeout, and an
    # earlier run's report beside the folder is not taken for this run's end.
    Path(report).write_text(json.dumps({"counts": {"requested": 4, "completed": 4}}))
    book.start(proofread_argv(["--pages", "1-3", "--overwrite"]), "p3.log",
               {"output": "proofread", "pages": [1], "requested": 3, "report": report, "delay": 1.0,
                "end": "kill"})
    book.wait_for_line("p3.log", "proofreading")
    expect(problems, "killed", book.watch("proofread", "p3.log"), 4,
           r"STOPPED proofread_pages\.py: no process runs it", r"killed or died", r"1/3 pages sealed",
           r"last log line: page 0001", r"run the SAME command again", within=10)

    # Gone before the wait starts, with no last line: stopped too.
    expect(problems, "gone before the wait", book.watch("proofread", "p3.log", timeout=1), 4,
           r"STOPPED proofread_pages\.py", within=8)

    # Crashed: the traceback's last line.
    book.start(proofread_argv(), "p4.log", {"output": "proofread", "pages": [1], "requested": 4,
                                            "report": report, "delay": 0.5, "end": "traceback"})
    book.wait_for_line("p4.log", "proofreading")
    expect(problems, "crashed", book.watch("proofread", "p4.log"), 1,
           r"FAILED proofread_pages\.py: it crashed: RuntimeError: stand-in crash", within=10)

    # Interrupted (Ctrl-C): stopped, run it again.
    book.start(proofread_argv(), "p5.log", {"output": "proofread", "pages": [1], "requested": 4,
                                            "report": report, "delay": 0.5, "end": "interrupt"})
    book.wait_for_line("p5.log", "proofreading")
    expect(problems, "interrupted", book.watch("proofread", "p5.log"), 4,
           r"STOPPED proofread_pages\.py: interrupted \(KeyboardInterrupt\)", within=10)

    # Finished with failed pages: exit 1, with the count and the report.
    book.start(proofread_argv(["--pages", "1-3"]), "p6.log",
               {"output": "proofread", "pages": [1, 2], "failed": [3], "requested": 3, "report": report,
                "delay": 0.3})
    book.wait_for_line("p6.log", "proofreading")
    expect(problems, "failed pages", book.watch("proofread", "p6.log"), 1,
           r"FAILED proofread_pages\.py: finished with failed or blocked pages: 2/3 pages sealed",
           r"1 failed, 0 blocked",
           re.escape(f"report {report}"), within=10)

    # Finished with the step's own warnings (stale pair classes at the start,
    # the engine preference drifting at the end): done, and the line names
    # them - the head and the advice at the end - and how to read them all.
    book.start(proofread_argv(["--pages", "1-2", "--overwrite"]), "p11.log",
               {"output": "proofread", "pages": [1, 2], "requested": 2, "report": report, "delay": 0.2,
                "warnings": True})
    book.wait_for_line("p11.log", "proofreading")
    expect(problems, "finished with warnings", book.watch("proofread", "p11.log"), 0,
           r"DONE proofread_pages\.py: 2/2 pages sealed",
           r"; 2 WARNING line\(s\) - read them before the next step \(grep -n WARNING .*p11\.log\)",
           r"'3 pair\(s\) are classified differently by the variant lists .*rebuild the profile "
           r"\(book_profile\.py\), which votes on them'",
           r"'engine preference A no longer holds on the audit pages .*- re-profile this part of the book'",
           within=10)

    # A configuration error before any page: exit 1 with the ERROR.
    book.start(proofread_argv(), "p7.log", {"output": "proofread-missing", "end": "error"})
    expect(problems, "configuration error", book.watch("proofread-missing", "p7.log", timeout=3), 1,
           r"FAILED proofread_pages\.py: ERROR render directory does not exist", within=8)

    # A step that did not start - its own parser refused the arguments (the
    # REAL scripts' parsers, which exit before any file or model call), python
    # found no such script, the shell no such command - failed, since the same
    # command fails the same way; not "stopped, run the SAME command again".
    scripts = ROOT / "scripts"
    for name, command, output, patterns in (
            ("proofread with a wrong option", f"{sys.executable} {scripts}/proofread_pages.py renders ocr-a "
             "proofread --draft2-directory ocr-b --effort xhigh", "proofread",
             (r"FAILED proofread_pages\.py: it did not start: it refused its arguments: "
              r"unrecognized arguments: --effort xhigh",)),
            ("profile with a wrong option", f"{sys.executable} {scripts}/book_profile.py renders ocr-a ocr-b "
             "book-profile.json --max-inflight 8", "book-profile.json",
             (r"FAILED book_profile\.py: it did not start: it refused its arguments: "
              r"unrecognized arguments: --max-inflight 8",)),
            ("no such script", f"{sys.executable} scripts/proofread_pages.py renders ocr-a proofread",
             "proofread", (r"FAILED proofread_pages\.py: it did not start: python cannot open "
                           r".*scripts/proofread_pages\.py",)),
            ("no such command (bash)", "bash -c 'no-such-python3 bin/proofread_pages.py renders ocr-a proofread'",
             "proofread", (r"FAILED proofread_pages\.py: it did not start: the shell says no-such-python3: "
                           r"command not found",)),
            ("no such command (sh)", "sh -c 'no-such-python3 bin/proofread_pages.py renders ocr-a proofread'",
             "proofread", (r"FAILED proofread_pages\.py: it did not start: the shell says no-such-python3: "
                           r"(command )?not found",))):
        log = re.sub(r"\W+", "-", name) + ".log"
        subprocess.run(["bash", "-c", f"{command} > {log} 2>&1"], cwd=root, env=dict(os.environ),
                       stdin=subprocess.DEVNULL, timeout=60)
        expect(problems, name, book.watch(output, log, timeout=3), 1, *patterns,
               r"the same command fails the same way", within=8)

    # Profile: its step while running, then done with the vote's line.
    profile_argv = ["bin/book_profile.py", "renders", "ocr-a", "ocr-b", "book-profile.json", "--workers", "8"]
    book.start(profile_argv, "b1.log", {"profile": str(root / "book-profile.json"), "classify": 3.0,
                                        "note": book_profile.VARIANT_NOTE_VOTE})
    book.wait_for_line("b1.log", "layout:")
    expect(problems, "profile running", book.watch("book-profile.json", "b1.log", timeout=1), 75,
           r"RUNNING book_profile\.py: step 3 of 6 \(classifying variant pairs\)", within=8)
    expect(problems, "profile done", book.watch("book-profile.json", "b1.log"), 0,
           r"DONE book_profile\.py: profile .*book-profile\.json written in 2 s",
           r"variant vote: 2 pair\(s\) ruled by the model", within=15)

    # Profile killed during the variant vote: the profile is on disk, but the
    # step did not finish.
    (root / "book-profile.json").unlink()
    book.start(profile_argv, "b2.log", {"profile": str(root / "book-profile.json"), "voting": 1.5,
                                        "note": book_profile.VARIANT_NOTE_VOTE, "end": "kill"})
    book.wait_for_line("b2.log", "notation:")
    expect(problems, "profile killed in the vote", book.watch("book-profile.json", "b2.log"), 4,
           r"STOPPED book_profile\.py", r"book-profile\.json exists", within=10)

    # Profile with the vote off: done when the profile is written.
    book.start(profile_argv + ["--no-variant-vote"], "b3.log",
               {"profile": str(root / "book-profile.json"), "vote": False, "classify": 0.5,
                "note": book_profile.VARIANT_NOTE})
    book.wait_for_line("b3.log", "probing")
    expect(problems, "profile without vote", book.watch("book-profile.json", "b3.log"), 0,
           r"DONE book_profile\.py: profile .* written", r"no variant vote in the log", within=10)

    # The real book_profile.py killed (SIGTERM) during its vote with its
    # output unbuffered (python3 -u), as an agent may launch it: the profile
    # line is in the log, the vote's is not.  The profile's own variants note
    # says the vote was due, so the step did not finish, whether the wait
    # started after the kill or saw the process only as the writer of its log
    # (OUTPUT not the profile it writes).
    real = ["-u", "bin/real/book_profile.py", "renders", "ocr-a", "ocr-b", "real-profile.json",
            "--no-pair-cache"]
    process = book.start(real, "b4.log", {})
    book.wait_for_line("b4.log", "profile:")
    process.send_signal(signal.SIGTERM)
    process.wait()
    expect(problems, "real profile killed in the vote, wait after", book.watch("real-profile.json", "b4.log",
                                                                                timeout=3), 4,
           r"STOPPED book_profile\.py: profile .*real-profile\.json written",
           r"variant vote after it did not finish", r"run the SAME command again", within=8)
    (root / "elsewhere").mkdir()
    process = book.start(real, "b5.log", {})
    book.wait_for_line("b5.log", "profile:")
    waiting = book.start_watch("real-profile.json", "../b5.log", cwd=root / "elsewhere")
    time.sleep(2.5)                 # the wait finds the process, by its log only
    process.send_signal(signal.SIGTERM)
    process.wait()
    expect(problems, "real profile killed in the vote, watched by its log", book.watched(waiting), 4,
           r"STOPPED book_profile\.py: profile .*real-profile\.json written",
           r"variant vote after it did not finish", within=10)

    # A proofread run that only READS the profile (--profile) is not the
    # profile being built: the finished profile is reported done at once.
    reader = book.start(proofread_argv(["--profile", "book-profile.json"]), "p8.log",
                        {"output": "proofread", "pages": [], "requested": 4, "report": report,
                         "end": "hang"})
    book.wait_for_line("p8.log", "proofreading")
    expect(problems, "reader of the profile", book.watch("book-profile.json", "b1.log", timeout=20), 0,
           r"DONE book_profile\.py", within=5)
    reader.kill()
    reader.wait()

    # OCR under run_ocr_phase.py: the runner's pages, then the phase's RESULT.
    ocr_report = str(root / "paddleocr-vl-run.json")
    runner = ["bin/run_paddleocr_vl.py", "renders", "ocr-a"]
    book.start(["bin/run_ocr_phase.py", "--", sys.executable] + runner + ["--pages", "1-2"], "o1.log",
               {"output": "ocr-a", "pages": [1, 2], "requested": 2, "report": ocr_report, "delay": 0.3})
    book.wait_for_line("o1.log", "page 0001")
    expect(problems, "OCR done", book.watch("ocr-a", "o1.log"), 0,
           r"DONE run_paddleocr_vl\.py: 2/2 pages sealed \(2 this run, [\d.]+ pages/h\)",
           re.escape(f"report {ocr_report}"), within=10)
    book.start(["bin/run_ocr_phase.py", "--", sys.executable] + runner, "o2.log",
               {"output": "ocr-a", "pages": [3], "skipped": 2, "requested": 4, "report": ocr_report,
                "delay": 0.3})
    book.wait_for_line("o2.log", "page 0003")
    expect(problems, "OCR budget spent", book.watch("ocr-a", "o2.log"), 4,
           r"STOPPED run_paddleocr_vl\.py: the OCR call spent its time budget", r"3/4 pages sealed",
           r"run the SAME command again", within=10)
    book.start(runner + ["--pages", "1-4"], "o3.log",
               {"output": "ocr-a", "pages": [4], "requested": 4, "report": ocr_report, "delay": 0.2,
                "end": "hang"})
    book.wait_for_line("o3.log", "page 0004")
    expect(problems, "OCR running", book.watch("ocr-a", "o3.log", timeout=1), 75,
           r"RUNNING run_paddleocr_vl\.py: 4/4 pages sealed \(1 this run", within=8)

    # A process whose arguments name no known script but that writes the log
    # is still running, and a shell that only carries the command in one
    # string is not the step.
    with open(root / "x1.log", "wb") as handle:
        other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], cwd=root,
                                 stdout=handle, stderr=subprocess.STDOUT)
    book.processes.append(other)
    expect(problems, "writer of the log", book.watch("elsewhere", "x1.log", timeout=1), 75, r"RUNNING",
           within=8)
    other.kill()
    other.wait()
    shell = subprocess.Popen(["sh", "-c", f"{sys.executable} bin/proofread_pages.py renders ocr-a proofread "
                              "> p9.log 2>&1; sleep 30"], cwd=root, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True,
                             env=dict(os.environ, STAND_IN_PLAN=json.dumps(
                                 {"output": "proofread", "pages": [1], "requested": 4, "report": report})))
    book.processes.append(shell)
    try:
        book.wait_for_line("p9.log", "report:")
        expect(problems, "shell wrapper", book.watch("proofread", "p9.log"), 0, r"DONE proofread_pages\.py",
               within=5)
    finally:
        os.killpg(shell.pid, signal.SIGKILL)     # the shell and its sleep
        shell.wait()

    # The wrong log given: the file the run writes is read (and named while
    # it runs), so a finished run is done, not stopped.
    book.start(proofread_argv(["--pages", "1-2"]), "p10.log",
               {"output": "proofread", "pages": [1, 2], "requested": 2, "report": report, "delay": 1.2})
    book.wait_for_line("p10.log", "proofreading")
    expect(problems, "wrong log, running", book.watch("proofread", "wrong.log", timeout=0.5), 75,
           r"RUNNING proofread_pages\.py", r"its output goes to .*p10\.log, not .*wrong\.log", within=8)
    expect(problems, "wrong log, finished", book.watch("proofread", "wrong.log"), 0,
           r"DONE proofread_pages\.py: 2/2 pages sealed", within=10)

    # No process and no log: nothing is guessed (a finished run would look
    # killed), whether the output exists or not.
    expect(problems, "no log", book.watch("proofread", "no-such.log", timeout=1), 2,
           r"CANNOT TELL: .*no-such\.log does not exist", within=8)
    expect(problems, "nothing to watch", book.watch("no-such-dir", "no-such.log", timeout=1), 2,
           r"CANNOT TELL", within=8)


def asks_no_model(problems: list[str]) -> None:
    """The wait must cost the server nothing: no HTTP, no socket, no client."""
    source = WAIT.read_text(encoding="utf-8")
    found = [word for word in ("urllib", "http", "socket", "Client(", "ask(", "requests") if word in source]
    if found:
        problems.append(f"wait_for_run.py mentions {found}: it must ask no model and open no connection")
    print(f"{'FAIL' if found else 'ok  '} wait_for_run.py opens no connection: {found or 'none of'} "
          "urllib/http/socket/Client/ask/requests")


def skill_text(problems: list[str], wait_for_run) -> None:
    """What SKILL.md tells the agent about a long step in the background:
    wait with wait_for_run.py instead of reading logs and pages, with the
    measured cost that says why, every exit code the script has and no other,
    and the rules that were there before still there."""
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    section = skill.split("## 安全並行", 1)[-1].split("\n## ", 1)[0]
    start = section.find("scripts/wait_for_run.py")
    bullet = section[section.rfind("\n- ", 0, start):] if start >= 0 else ""
    bullet = bullet[:bullet.find("\n- ", 1)] if "\n- " in bullet[1:] else bullet
    codes = {int(code) for code in re.findall(r"\*\*exit (\d+)\*\*", bullet)}

    def item(code: int) -> str:
        """The bullet's line on exit CODE."""
        return next((line for line in bullet.splitlines() if line.strip().startswith(f"- **exit {code}**")), "")
    script_codes = {wait_for_run.EXIT_DONE, wait_for_run.EXIT_FAILED, wait_for_run.EXIT_USAGE,
                    wait_for_run.EXIT_STOPPED, wait_for_run.EXIT_RUNNING}
    wanted = {
        # How to wait, and not to watch.
        "the wait command in 〈安全並行〉": "python3 scripts/wait_for_run.py OUTPUT LOG" in bullet,
        "the tool call's timeout 600000": "600000" in bullet,
        f"the default wait of {wait_for_run.DEFAULT_TIMEOUT:.0f} s":
            f"{wait_for_run.DEFAULT_TIMEOUT:.0f} 秒" in bullet,
        "not reading the log": "唔好 tail log" in bullet,
        "not reading sealed pages": "唔好讀已封存嘅頁" in bullet,
        "calling it again at once on exit 75": "即刻再叫同一個 command" in bullet,
        "a short conversation before a long step": "對話保持短" in bullet and "唔好將 log" in bullet,
        # The measured cost, plainly.
        "the turns and tokens measured": all(n in bullet for n in ("84 輪", "11 萬", "930 萬")),
        "the server share measured": "三成" in bullet,
        "the pages per hour measured": "7 頁" in bullet and "17–21 頁" in bullet,
        "every exit code of the script and no other": codes == script_codes,
        # A step that did not start is exit 1: fix the command, not run it
        # again; exit 2 is only wait_for_run.py's own arguments and paths.
        "exit 1 covers a step that did not start":
            all(word in item(wait_for_run.EXIT_FAILED) for word in ("did not start", "開唔到工", "改好 command")),
        "exit 2 is wait_for_run.py's own arguments":
            "`wait_for_run.py` 自己嘅參數" in item(wait_for_run.EXIT_USAGE),
        # The step's own warnings, which the agent no longer sees in the log,
        # are read once it is done.
        "on exit 0 the WARNING lines are read first":
            all(word in item(wait_for_run.EXIT_DONE) for word in ("`WARNING`", "grep -n WARNING LOG")),
        # The rules that were there stay.
        "the handover in the foreground": "GPU 交接一定要喺前景行" in section,
        "no run_ocr_phase.py while a step runs": "背景跑緊嘅時候唔好開任何 `run_ocr_phase.py`" in section,
        "Qwen Code kills background shells on exit": "Qwen Code 退出會殺晒背景 shell" in section,
        "the old polling gone": "定時睇 log" not in skill,
        "the script listed": "- `scripts/wait_for_run.py`" in skill,
    }
    missing = [name for name, ok in wanted.items() if not ok]
    for name in missing:
        problems.append(f"SKILL.md: {name}"
                        + (f" (SKILL.md names {sorted(codes)}, the script {sorted(script_codes)})"
                           if name.startswith("every exit code") else ""))
    print(f"{'FAIL' if missing else 'ok  '} SKILL.md on waiting for a long step: "
          f"{len(wanted) - len(missing)} of {len(wanted)} rules")


def main() -> int:
    problems: list[str] = []
    if not WAIT.is_file():
        print(f"FAIL {WAIT.relative_to(ROOT)} does not exist")
        return 1
    import wait_for_run
    if wait_for_run.DEFAULT_TIMEOUT >= 600:
        problems.append("the default wait must stay under Qwen Code's 600 s shell cap")
    skill_text(problems, wait_for_run)
    asks_no_model(problems)
    cases(problems)
    for problem in problems:
        print("FAIL", problem)
    print(f"{'FAIL' if problems else 'ok  '} wait_for_run.py: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
