#!/usr/bin/env python3
"""Offline checks of the OCR phase's speed work (2026-09-30): run_ocr_engines.py on
stand-in runners, survey_pdf.py's sliced render, the budget flag of run_ocr_phase.py,
and the skill text that orders the phase.

No GPU, no model, no corpus.

- scripts/run_ocr_engines.py: both stand-in runners get the command line a runner
  gets alone, with OCR_PHASE_DEADLINE and OCR_PHASE_PROGRESS passed through and
  the progress file shared; the draft (the REAL build_draft.py) is built the
  moment engine B exits 0 while engine A still runs, and its lines are repeated
  at the end; a later call that only skipped sealed pages does not rebuild it,
  one that sealed pages does; exit 0 both done, 75 either deferred, 1 either
  failed (the draft still built when B is done), 2 nothing ran or no renders;
  SIGTERM reaches both runners and the script exits 143 within seconds with no
  runner left; --a-lanes 2 shares the pages out over two engine A processes with
  their own reports; --no-engine-a runs B alone.
- scripts/survey_pdf.py: a made-up PDF surveyed with --jobs 1 and with --jobs 4
  (and a scattered --pages selection with --jobs 3 against --jobs 1) gives
  byte-identical renders, and the same manifest and report but for their
  timestamps and paths.  Skipped, and said, where pdftoppm is not installed.
- scripts/run_ocr_phase.py: --max-seconds 0 is refused (exit 2, naming
  OCR_PHASE_UNLIMITED_SHELL) when the server has to be stopped, and accepted
  with --unlimited-shell.  Only where nvidia-smi exists: without a GPU the
  script never reaches the budget.
- SKILL.md, references/long-book-workflow.md, env.sh.example: engine B first,
  the draft at once, engine A after, one engine per hand-over call;
  run_ocr_engines.py is NOT instructed until its output has been compared with
  solo runs on the GPU (the script and its checks above are kept ready); the
  cap on page viewing in step 1; the unlimited-shell rule and the single long
  wait; the measured retry count; the engine B figures.

Usage:
    python3 tests/check_ocr_engines.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
PY = sys.executable

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    shown = detail if (not ok or len(detail) < 120) else ""
    print(("ok   " if ok else "FAIL ") + name + (f" ({shown})" if shown else ""), flush=True)
    if not ok:
        failures.append(name)


# A stand-in runner: the runners' command line, pages "sealed" from a plan in the
# environment, the phase's progress file appended to, a run report with counts,
# the runners' summary line, and SIGTERM answered the way the runners answer it
# (exit 143, no report).  What it saw goes to a trace file, one per process.
STUB = '''
import argparse, json, os, signal, sys, time
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument("render_directory", type=Path)
p.add_argument("output_directory", type=Path)
p.add_argument("--pages")
p.add_argument("--first-page", type=int)
p.add_argument("--last-page", type=int)
p.add_argument("--overwrite", action="store_true")
p.add_argument("--report", type=Path)
p.add_argument("--extra")
a = p.parse_args()
label = "A" if "paddle" in Path(sys.argv[0]).name else "B"
plan = json.loads(os.environ.get("STUB_PLAN_" + label, "{}"))
trace = Path(os.environ["STUB_TRACE"]) / f"{label}-{os.getpid()}.json"
seen = {"label": label, "argv": sys.argv[1:], "deadline": os.environ.get("OCR_PHASE_DEADLINE"),
        "progress": os.environ.get("OCR_PHASE_PROGRESS"), "pid": os.getpid(), "signal": None}
def on_term(signum, frame):
    seen["signal"] = signum
    trace.write_text(json.dumps(seen))
    sys.exit(128 + signum)
signal.signal(signal.SIGTERM, on_term)
trace.write_text(json.dumps(seen))
a.output_directory.mkdir(parents=True, exist_ok=True)
pages = plan.get("pages", [])
SENTENCES = ["天地玄黃", "宇宙洪荒", "日月盈昃", "辰宿列張", "寒來暑往", "秋收冬藏", "閏餘成歲", "律呂調陽"]
for page in pages:
    time.sleep(plan.get("delay", 0))
    (a.output_directory / f"page-{page:04d}.txt").write_text(
        SENTENCES[(page - 1) % len(SENTENCES)] + "\\n", encoding="utf-8")
    (a.output_directory / f"page-{page:04d}.json").write_text("{}")
    if os.environ.get("OCR_PHASE_PROGRESS"):
        with open(os.environ["OCR_PHASE_PROGRESS"], "a") as h:
            h.write(f"{page}\\n")
    print(f"  page {page:04d}: stand-in {label}", flush=True)
while plan.get("hang"):
    time.sleep(0.2)
counts = {"requested": plan.get("requested", len(pages)), "completed": len(pages),
          "skippedCurrent": plan.get("skipped", 0), "blocked": 0, "failed": plan.get("failed", 0),
          "deferred": plan.get("deferred", 0)}
if a.report is not None and not plan.get("no_report"):
    a.report.write_text(json.dumps({"counts": counts}))
print("  requested {requested} | completed {completed} | skipped {skippedCurrent} | blocked "
      "{blocked} | failed {failed} | deferred {deferred}".format(**counts), flush=True)
print(f"  report: {a.report}", flush=True)
sys.exit(plan.get("exit", 0))
'''

# build_draft.py itself, run from the stand-in folder: run_ocr_engines.py takes
# every script from one folder, so the folder holds this shim for the real one.
DRAFT_SHIM = '''
import runpy, sys
real = {real!r}
sys.argv[0] = real
runpy.run_path(real, run_name="__main__")
'''


class Book:
    """A made-up book folder with stand-in runners in bin/."""

    def __init__(self, root: Path, pages: int = 6) -> None:
        self.root, self.pages = root, pages
        root.mkdir(parents=True)
        (root / "bin").mkdir()
        for name in ("run_paddleocr_vl.py", "run_hunyuanocr.py"):
            (root / "bin" / name).write_text(textwrap.dedent(STUB))
        (root / "bin" / "build_draft.py").write_text(
            textwrap.dedent(DRAFT_SHIM.format(real=str(SCRIPTS / "build_draft.py"))))
        (root / "renders").mkdir()
        records = []
        for page in range(1, pages + 1):
            (root / "renders" / f"page-{page:04d}.png").write_bytes(b"")
            records.append({"scan_page": page, "render_file": f"renders/page-{page:04d}.png",
                            "render_sha256": "0" * 64})
        (root / "page-manifest.json").write_text(json.dumps(
            {"source_sha256": "0" * 64, "expected_scan_pages": pages, "pages": records}),
            encoding="utf-8")
        self.trace = root / "trace"
        self.trace.mkdir()
        self.progress = root / "progress.txt"
        self.progress.write_text("")

    def env(self, plan_a: dict | None, plan_b: dict | None, deadline: float | None = 600.0) -> dict:
        env = dict(os.environ)
        for key in list(env):
            if key.startswith("STUB_") or key.startswith("OCR_PHASE_"):
                del env[key]
        env["STUB_TRACE"] = str(self.trace)
        if plan_a is not None:
            env["STUB_PLAN_A"] = json.dumps(plan_a)
        if plan_b is not None:
            env["STUB_PLAN_B"] = json.dumps(plan_b)
        if deadline is not None:
            env["OCR_PHASE_DEADLINE"] = f"{time.time() + deadline:.3f}"
        env["OCR_PHASE_PROGRESS"] = str(self.progress)
        return env

    def clear_traces(self) -> None:
        for item in self.trace.glob("*.json"):
            item.unlink()

    def traces(self, label: str | None = None) -> list[dict]:
        out = [json.loads(p.read_text()) for p in sorted(self.trace.glob("*.json"))]
        return [t for t in out if label is None or t["label"] == label]

    def command(self, *extra: str) -> list[str]:
        return [PY, str(SCRIPTS / "run_ocr_engines.py"), str(self.root),
                "--scripts-dir", str(self.root / "bin"), *extra]

    def run(self, plan_a: dict | None, plan_b: dict | None, *extra: str,
            deadline: float | None = 600.0) -> tuple[int, str]:
        self.clear_traces()
        done = subprocess.run(self.command(*extra), env=self.env(plan_a, plan_b, deadline),
                              capture_output=True, text=True, timeout=120, cwd=str(self.root))
        return done.returncode, done.stdout + done.stderr


def check_engines() -> None:
    with tempfile.TemporaryDirectory(prefix="ocr-engines-") as folder:
        book = Book(Path(folder) / "book")
        draft = book.root / "draft.md"

        # Both done: A slow, B quick; the draft while A runs.
        code, out = book.run({"pages": [1, 2, 3, 4, 5, 6], "delay": 0.4},
                             {"pages": [1, 2, 3, 4, 5, 6], "delay": 0.02})
        check("both runners done: exit 0", code == 0, f"exit {code}")
        check("the draft is written from engine B's pages", draft.is_file() and "日月盈昃" in
              draft.read_text(encoding="utf-8"), draft.read_text(encoding="utf-8")[-200:] if draft.is_file() else "no draft")
        b_exit = out.find("engine B (run_hunyuanocr.py) exit 0")
        a_exit = out.find("engine A (run_paddleocr_vl.py) exit 0")
        built = out.find("building the draft")
        first_draft_line = out.find(str(draft))
        check("engine B ends before engine A", 0 <= b_exit < a_exit, f"{b_exit} {a_exit}")
        check("the draft is built as soon as B is done, while A still runs",
              b_exit < built < a_exit and b_exit < first_draft_line < a_exit,
              f"B exit at {b_exit}, build at {built}, draft line at {first_draft_line}, A exit at {a_exit}")
        check("the draft's line is repeated after the engines' summary",
              out.rfind(str(draft)) > out.find("engine A (run_paddleocr_vl.py): exit 0"))
        check("the RESULT line says DONE", "[ocr-engines] RESULT exit=0 DONE" in out)
        traces = book.traces()
        check("two runners ran, one per engine", sorted(t["label"] for t in traces) == ["A", "B"],
              str([t["label"] for t in traces]))
        deadline = book.env(None, None)["OCR_PHASE_DEADLINE"]
        check("the runners get the phase's deadline and progress file",
              all(t["deadline"] and t["progress"] == str(book.progress) for t in traces))
        check("both runners append to the one progress file",
              sorted(int(x) for x in book.progress.read_text().split()) == sorted([1, 2, 3, 4, 5, 6] * 2))
        for trace in traces:
            argv = trace["argv"]
            expected_dir = "ocr-paddle" if trace["label"] == "A" else "ocr-hunyuan"
            report = "paddleocr-vl-run.json" if trace["label"] == "A" else "hunyuanocr-run.json"
            check(f"engine {trace['label']}'s command line: renders, its folder, its report, nothing else",
                  argv[:2] == [str(book.root / "renders"), str(book.root / expected_dir)]
                  and argv[2:4] == ["--report", str(book.root / report)] and len(argv) == 4, str(argv))
        check("the runners' summary lines are shown", "engine A (run_paddleocr_vl.py): exit 0 - requested 6 | "
              "completed 6 | skipped 0 | blocked 0 | failed 0 | deferred 0" in out)

        # B leaves pages for the next call: 75, no draft yet.
        draft.unlink()
        shutil.rmtree(book.root / "ocr-hunyuan")
        code, out = book.run({"pages": [1, 2, 3, 4, 5, 6]},
                             {"pages": [1, 2, 3], "exit": 75, "requested": 6, "deferred": 3})
        check("engine B deferred pages: exit 75", code == 75, f"exit {code}")
        check("no draft while engine B is not done", not draft.is_file())
        check("the RESULT line says INCOMPLETE, run the same command", "INCOMPLETE" in out
              and "run the SAME command again" in out)
        # The next call finishes B (A only skips): the draft is built once.
        code, out = book.run({"pages": [], "requested": 6, "skipped": 6},
                             {"pages": [4, 5, 6], "requested": 6, "skipped": 3})
        check("the next call: exit 0", code == 0, f"exit {code}")
        check("the draft is built when B finishes on a later call",
              draft.is_file() and all(w in draft.read_text(encoding="utf-8") for w in ("天地玄黃", "秋收冬藏")))
        stamp = draft.stat().st_mtime_ns
        # A call in which B only skipped sealed pages leaves the draft alone.
        code, out = book.run({"pages": [], "requested": 6, "skipped": 6},
                             {"pages": [], "requested": 6, "skipped": 6})
        check("a call that only skipped does not rebuild the draft", code == 0
              and draft.stat().st_mtime_ns == stamp and "building the draft" not in out)
        # No draft yet (it failed to build last time): a call that only skipped builds it.
        draft.unlink()
        code, out = book.run({"pages": [], "requested": 6, "skipped": 6},
                             {"pages": [], "requested": 6, "skipped": 6})
        check("no draft on disk: a call that only skipped builds it", code == 0 and draft.is_file())
        # --no-draft.
        draft.unlink()
        code, out = book.run({"pages": [], "requested": 6, "skipped": 6},
                             {"pages": [], "requested": 6, "skipped": 6}, "--no-draft")
        check("--no-draft: none built", code == 0 and not draft.is_file())

        # A fails, B done: 1, and the draft is still built.
        draft.unlink(missing_ok=True)
        code, out = book.run({"pages": [1], "exit": 1, "failed": 5, "requested": 6},
                             {"pages": [1, 2, 3, 4, 5, 6]})
        check("engine A failed: exit 1", code == 1, f"exit {code}")
        check("the draft is built although engine A failed", draft.is_file())
        check("the RESULT line says FAILED", "RESULT exit=1 FAILED" in out)
        # A deferred and B failed: 1 (a failure needs reading before any repeat).
        code, out = book.run({"pages": [1], "exit": 75, "deferred": 5, "requested": 6},
                             {"pages": [], "exit": 1, "failed": 6, "requested": 6})
        check("one deferred, one failed: exit 1", code == 1, f"exit {code}")
        # Both refused their configuration: 2.
        code, out = book.run({"exit": 2}, {"exit": 2})
        check("both runners exit 2: exit 2, nothing ran", code == 2 and "CONFIGURATION ERROR" in out)
        # One refused, the other done: 1.
        code, out = book.run({"exit": 2}, {"pages": [1, 2, 3, 4, 5, 6]})
        check("one runner exit 2, the other done: exit 1", code == 1, f"exit {code}")

        # Engine-specific arguments, --pages and --overwrite pass through.
        code, out = book.run({"pages": []}, {"pages": []}, "--pages", "2-3", "--overwrite",
                             "--engine-a-args", "--extra alpha", "--engine-b-args", "--extra beta")
        argv = {t["label"]: t["argv"] for t in book.traces()}
        check("--pages and --overwrite reach both runners", all(
            "--pages" in a and a[a.index("--pages") + 1] == "2-3" and "--overwrite" in a for a in argv.values()))
        check("--engine-a-args / --engine-b-args reach their runner",
              argv["A"][-2:] == ["--extra", "alpha"] and argv["B"][-2:] == ["--extra", "beta"], str(argv))

        # --a-lanes 2: two engine A processes on interleaved pages, their own reports.
        code, out = book.run({"pages": []}, {"pages": []}, "--a-lanes", "2", "--no-draft")
        lanes = book.traces("A")
        pages = sorted(a["argv"][a["argv"].index("--pages") + 1] for a in lanes)
        reports = sorted(a["argv"][a["argv"].index("--report") + 1] for a in lanes)
        check("--a-lanes 2: two engine A processes on interleaved pages", code == 0 and len(lanes) == 2
              and pages == ["1,3,5", "2,4,6"], str(pages))
        check("each lane has its own report", reports == [str(book.root / "paddleocr-vl-run.lane1.json"),
                                                          str(book.root / "paddleocr-vl-run.lane2.json")],
              str(reports))
        check("engine B ran once beside the lanes", len(book.traces("B")) == 1)

        # --no-engine-a: B alone, the draft still built.
        draft.unlink(missing_ok=True)
        code, out = book.run(None, {"pages": [1, 2, 3, 4, 5, 6]}, "--no-engine-a")
        check("--no-engine-a: engine B alone, exit 0, the draft built", code == 0
              and [t["label"] for t in book.traces()] == ["B"] and draft.is_file())
        code, out = book.run(None, None, "--no-engine-a", "--no-engine-b")
        check("nothing to run: exit 2", code == 2)
        # No renders: 2 before anything starts.
        code, out = book.run({"pages": []}, {"pages": []}, "--renders", str(book.root / "nowhere"))
        check("no render directory: exit 2, no runner started", code == 2 and not book.traces())
        # Without a deadline nothing is said about a budget.
        code, out = book.run({"pages": []}, {"pages": []}, deadline=None)
        check("no OCR_PHASE_DEADLINE: no budget line, exit 0", code == 0 and "time budget" not in out)
        check("with a deadline the budget is announced", "time budget: the runners stop starting pages"
              in book.run({"pages": []}, {"pages": []})[1])

        # SIGTERM: passed on to both runners, exit 143 within seconds, no runner left.
        book.clear_traces()
        process = subprocess.Popen(book.command("--no-draft"),
                                   env=book.env({"hang": True}, {"hang": True}),
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                   cwd=str(book.root))
        deadline = time.monotonic() + 20
        while len(book.traces()) < 2 and time.monotonic() < deadline:
            time.sleep(0.1)
        started = time.monotonic()
        process.send_signal(signal.SIGTERM)
        try:
            out, _ = process.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            out, _ = process.communicate()
        took = time.monotonic() - started
        check("SIGTERM: the script exits 143 within seconds", process.returncode == 143 and took < 12,
              f"exit {process.returncode} after {took:.1f}s")
        traces = book.traces()
        check("SIGTERM reached both runners", len(traces) == 2 and all(t["signal"] == 15 for t in traces),
              str([(t["label"], t["signal"]) for t in traces]))
        alive = []
        for trace in traces:
            try:
                os.kill(trace["pid"], 0)
                alive.append(trace["pid"])
            except ProcessLookupError:
                pass
        check("no runner left running", not alive, str(alive))
        check("the STOPPED line says the sealed pages are kept",
              "RESULT exit=143 STOPPED by signal 15; sealed pages are kept" in out)


# --- the sliced render -----------------------------------------------------------

def made_up_pdf(path: Path, pages: int = 9) -> bool:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False
    images = []
    for index in range(pages):
        image = Image.new("RGB", (300, 420), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle([20 + 5 * index, 30, 120 + 9 * index, 60 + 12 * index], fill="black")
        for row in range(12):
            draw.line([(30, 100 + row * 22), (270 - 7 * ((row + index) % 5), 100 + row * 22)],
                      fill="black", width=3)
        draw.text((40, 380), f"page {index + 1}", fill="black")
        images.append(image)
    images[0].save(path, save_all=True, append_images=images[1:], resolution=72.0)
    return True


def survey(pdf: Path, out: Path, *extra: str) -> tuple[int, str]:
    done = subprocess.run([PY, str(SCRIPTS / "survey_pdf.py"), str(pdf), str(out), "--dpi", "72", *extra],
                          capture_output=True, text=True, timeout=300)
    return done.returncode, done.stdout + done.stderr


def without_stamps(path: Path, folder: Path) -> dict:
    text = path.read_text(encoding="utf-8").replace(str(folder), "<out>")
    data = json.loads(text)
    data.pop("generated_at", None)
    if "manifest" in data and isinstance(data["manifest"], dict):
        data["manifest"].pop("sha256", None)  # the manifest's bytes carry its own timestamp
    return data


def check_survey() -> None:
    if not shutil.which("pdftoppm"):
        print("skip survey_pdf.py: pdftoppm is not installed", flush=True)
        return
    with tempfile.TemporaryDirectory(prefix="survey-jobs-") as folder:
        root = Path(folder)
        pdf = root / "made-up.pdf"
        if not made_up_pdf(pdf):
            print("skip survey_pdf.py: PIL is not installed", flush=True)
            return
        code1, out1 = survey(pdf, root / "one", "--jobs", "1")
        code4, out4 = survey(pdf, root / "four", "--jobs", "4")
        check("survey --jobs 1 and --jobs 4 both exit 0", code1 == 0 and code4 == 0, f"{code1} {code4}\n{out1}\n{out4}")
        check("the rendering line says how many processes", "1 pdftoppm process(es) at a time" in out1
              and "4 pdftoppm process(es) at a time" in out4)
        renders1 = sorted((root / "one" / "renders").glob("page-*.png"))
        renders4 = sorted((root / "four" / "renders").glob("page-*.png"))
        check("nine renders each, named page-NNNN.png", [p.name for p in renders1] == [f"page-{n:04d}.png" for n in range(1, 10)]
              and [p.name for p in renders4] == [p.name for p in renders1])
        check("--jobs 4 renders are byte-identical to --jobs 1", all(
            a.read_bytes() == b.read_bytes() for a, b in zip(renders1, renders4)))
        check("the manifests are the same but for the timestamp",
              without_stamps(root / "one" / "page-manifest.json", root / "one")
              == without_stamps(root / "four" / "page-manifest.json", root / "four"))
        check("the reports are the same but for timestamps and paths",
              without_stamps(root / "one" / "survey-report.json", root / "one")
              == without_stamps(root / "four" / "survey-report.json", root / "four"))
        # A scattered selection: three runs, sliced across three processes.
        code_s1, _ = survey(pdf, root / "s1", "--jobs", "1", "--pages", "1,2,5-9")
        code_s3, out_s3 = survey(pdf, root / "s3", "--jobs", "3", "--pages", "1,2,5-9")
        renders_s1 = sorted((root / "s1" / "renders").glob("page-*.png"))
        renders_s3 = sorted((root / "s3" / "renders").glob("page-*.png"))
        check("a scattered --pages selection sliced over 3 processes: the same files, the same bytes",
              code_s1 == 0 and code_s3 == 0 and [p.name for p in renders_s1] == [p.name for p in renders_s3]
              == [f"page-{n:04d}.png" for n in (1, 2, 5, 6, 7, 8, 9)]
              and all(a.read_bytes() == b.read_bytes() for a, b in zip(renders_s1, renders_s3)), out_s3[-400:])
        check("the scattered manifests agree", without_stamps(root / "s1" / "page-manifest.json", root / "s1")
              == without_stamps(root / "s3" / "page-manifest.json", root / "s3"))
        check("the sliced render's pages are the ones the one-call render made",
              [p.read_bytes() for p in renders_s3] == [p.read_bytes() for p in renders1 if p.name in
                                                        {r.name for r in renders_s3}])
        code0, out0 = survey(pdf, root / "zero", "--jobs", "0")
        check("--jobs 0 is refused", code0 == 2 and "--jobs must be at least 1" in out0)


# --- the budget flag ----------------------------------------------------------------

def check_phase_budget() -> None:
    if not shutil.which("nvidia-smi"):
        print("skip run_ocr_phase.py budget: no nvidia-smi, the script runs the runner without a swap", flush=True)
        return
    base = [PY, str(SCRIPTS / "run_ocr_phase.py"), "--force-swap", "--release-cmd", "true",
            "--restore-cmd", "true", "--max-seconds", "0"]
    env = {k: v for k, v in os.environ.items() if not k.startswith("OCR_PHASE_")}
    refused = subprocess.run(base + ["--", "true"], env=env, capture_output=True, text=True, timeout=120)
    check("--max-seconds 0 without --unlimited-shell is refused before the server is stopped",
          refused.returncode == 2 and "OCR_PHASE_UNLIMITED_SHELL" in refused.stderr
          and "release: true" not in refused.stdout, f"exit {refused.returncode}: {refused.stderr[-300:]}")
    allowed = subprocess.run(base + ["--unlimited-shell", "--", "true"], env=env, capture_output=True,
                             text=True, timeout=120)
    check("--max-seconds 0 with --unlimited-shell runs the whole runner", allowed.returncode == 0
          and "release: true" in allowed.stdout and "RESULT exit=0" in allowed.stdout,
          f"exit {allowed.returncode}: {(allowed.stdout + allowed.stderr)[-300:]}")
    env_flag = dict(env, OCR_PHASE_UNLIMITED_SHELL="1")
    by_env = subprocess.run(base + ["--", "true"], env=env_flag, capture_output=True, text=True, timeout=120)
    check("OCR_PHASE_UNLIMITED_SHELL=1 in the environment allows it too", by_env.returncode == 0,
          f"exit {by_env.returncode}")


# --- the text -----------------------------------------------------------------------

def section(text: str, heading: str) -> str:
    return text.split(heading, 1)[-1].split("\n## ", 1)[0] if heading in text else ""


def check_text() -> None:
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    reference = (ROOT / "references" / "long-book-workflow.md").read_text(encoding="utf-8")
    example = (ROOT / "env.sh.example").read_text(encoding="utf-8")
    deliveries = section(skill, "## 分三次交付")
    order = section(skill, "## OCR 工具次序")
    safe = section(skill, "## 安全並行")
    tools = section(skill, "## Deterministic 驗證")
    rules = {
        "the draft follows engine B, not both engines": "引擎 B（HunyuanOCR）做完就即刻跑，唔等引擎 A" in deliveries,
        "no wait for both engines anywhere": "兩個 OCR 引擎都做完" not in skill and "兩個 runner 都做完" not in skill,
        "step 3: engine B first, the draft at once, engine A after": "引擎 B 先、草稿即出、引擎 A 跟住" in order,
        "step 3: engine B's runner, then build_draft.py, then engine A's runner, in that order":
            0 <= order.find("先跑 `run_hunyuanocr.py`") < order.find("exit 0 就即刻跑 `build_draft.py`")
            < order.find("然後先跑 `run_paddleocr_vl.py`"),
        "the two-engine wrapper is not instructed before its output is measured":
            "run_ocr_engines" not in skill and "run_ocr_engines" not in reference,
        "step 1: at most five full pages": "最多睇 5 頁全頁圖" in order,
        "step 1: still no zooming or reading": "唔放大、唔逐字讀" in order,
        "step 1: why the cap, measured": "40 幅頁圖" in order and "13 分鐘" in order,
        "step 1: survey_pdf.py takes BOOK, not BOOK/renders": "`scripts/survey_pdf.py SOURCE.pdf BOOK`" in order
                                                              and "唔好畀佢 `BOOK/renders`" in order,
        "step 1: the survey renders on every core, same bytes": "`--jobs`" in order,
        "safe: one engine per hand-over call, engine B first":
            0 <= safe.find("先叫 `run_hunyuanocr.py` 叫到 exit 0") < safe.find("再叫 `run_paddleocr_vl.py` 叫到 exit 0"),
        "safe: the old order (engine A first) is gone": "先叫 `run_paddleocr_vl.py` 叫到 exit 0" not in skill,
        "safe: the retry count is the measured one": "重試 7 次" in safe and "重試兩次" not in skill,
        "safe: the unlimited-shell rule, timeout omitted": "OCR_PHASE_UNLIMITED_SHELL=1" in safe
                                                         and "唔好設 `timeout`" in safe,
        "safe: a call killed anyway means the setting did not take": "即係設定冇生效" in safe,
        "safe: --max-seconds 0 needs the flag": "要 `OCR_PHASE_UNLIMITED_SHELL=1` 講明" in safe,
        "safe: one wait for the whole step where the shell has no cap": "`--timeout 43200`" in safe,
        "safe: why no agent turn during a long step, measured": "八分一" in safe,
        "safe: each wait call carries a different description (the harness's loop guard)":
            "description 寫唔同嘅字" in safe and "連續 5 個一模一樣嘅 tool call" in safe,
        "furniture: only the candidates are looked at": "淨係睇 candidate" in skill,
        "tools: one runner per hand-over call": "一個 call 包一個 runner" in tools,
        "tools: engine B's measured figures": "約 5.0 GB VRAM" in tools and "4.3 GB" not in skill,
        "tools: the draft after engine B": "引擎 B 做完就寫 `BOOK/draft.md`" in tools,
        "tools: the survey's --jobs": "`--jobs`" in tools,
        "reference: the phase diagram runs engine B, the draft, then engine A":
            "run_hunyuanocr.py …（做完即刻 build_draft.py → BOOK/draft.md），之後再叫 -- run_paddleocr_vl.py" in reference,
        "reference: the example commands run engine B, build_draft.py, engine A, in that order":
            0 <= reference.find("scripts/run_hunyuanocr.py RENDER_DIR OCR_B_DIR")
            < reference.find("python3 scripts/build_draft.py BOOK")
            < reference.find("scripts/run_paddleocr_vl.py RENDER_DIR OCR_A_DIR"),
        "env.sh.example: the unlimited-shell flag, off": "# export OCR_PHASE_UNLIMITED_SHELL=1" in example,
        "env.sh.example: says what the flag means": "no time limit" in example,
    }
    for name, ok in rules.items():
        check(f"text: {name}", ok)
    source = (SCRIPTS / "run_hunyuanocr.py").read_text(encoding="utf-8")
    check("no request sends a repetition penalty", "repeat_penalty" not in source
          and "repetition_penalty" not in source)


def main() -> int:
    check_engines()
    check_survey()
    check_phase_budget()
    check_text()
    if failures:
        print(f"FAIL check_ocr_engines: {len(failures)} failure(s)")
        return 1
    print("ok   check_ocr_engines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
