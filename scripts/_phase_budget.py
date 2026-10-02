"""Time budget and process hygiene for one call of an OCR runner under run_ocr_phase.py.

Why this exists: an agent harness gives each shell tool call a time limit
(Qwen Code: 120 s by default, 600 s at most), and a whole book takes hours.  The
GPU handover must run in the FOREGROUND - while the LLM server is stopped the
agent has no model to think with, so a backgrounded handover leaves the agent's
next turn talking to a dead server (measured 2026-09-23: the harness gave up
after two retries and exited, and its exit killed the handover before the
server came back).  So one handover call does as many pages as fit in the
budget, stops between pages, restores the server and says "call me again";
sealed pages are skipped on the next call, so repeated calls finish the book.

run_ocr_phase.py sets two variables for the runner:

- OCR_PHASE_DEADLINE: absolute ``time.time()`` seconds.  A runner starts another
  page only while the time left exceeds the longest page it has done in this
  call, and never lets a page run past the deadline; with no deadline set it
  never stops early.
- OCR_PHASE_PROGRESS: a file the runner appends each sealed page to, so the
  phase can tell "stopped after sealing pages" (call again) from "stopped with
  nothing sealed" (calling again would do the same) even when it had to kill
  the runner.

The OCR model itself runs in a child of the runner (PaddleOCR worker,
llama-server).  If the runner dies without closing it, that child keeps the
GPU while the LLM server is started again: two models, one card.  So children
are started with ``die_with_parent`` and SIGTERM is turned into a normal exit
that runs the runner's ``finally`` blocks.
"""
from __future__ import annotations

import os
import signal
import sys
import time

DEADLINE_ENV = "OCR_PHASE_DEADLINE"
PROGRESS_ENV = "OCR_PHASE_PROGRESS"
# EX_TEMPFAIL: not finished, nothing wrong - run the same command again.
EXIT_INCOMPLETE = 75


class Budget:
    def __init__(self) -> None:
        raw = os.environ.get(DEADLINE_ENV, "").strip()
        try:
            self.deadline: float | None = float(raw) if raw else None
        except ValueError:
            self.deadline = None
        self.progress_file = os.environ.get(PROGRESS_ENV) or None
        self.longest = 0.0

    def remaining(self) -> float | None:
        """Seconds left before the deadline (may be negative), or None without one."""
        return None if self.deadline is None else self.deadline - time.time()

    def allows_next_page(self) -> bool:
        left = self.remaining()
        return left is None or left > self.longest

    def page_timeout(self, own_limit: float) -> tuple[float, bool]:
        """The limit for the next page, and whether the budget (not the runner) set it."""
        left = self.remaining()
        if left is not None and left < own_limit:
            return max(left, 0.0), True
        return own_limit, False

    def record(self, seconds: float) -> None:
        self.longest = max(self.longest, seconds)

    def sealed(self, scan_page: int) -> None:
        if not self.progress_file:
            return
        try:
            with open(self.progress_file, "a", encoding="utf-8") as handle:
                handle.write(f"{scan_page}\n")
        except OSError:
            pass


def exit_on_sigterm() -> None:
    """Make SIGTERM/SIGHUP raise SystemExit so the runner's finally closes its GPU child."""
    def handler(signum: int, _frame: object) -> None:
        raise SystemExit(128 + signum)
    for sig in (signal.SIGTERM, signal.SIGHUP):
        try:
            signal.signal(sig, handler)
        except (ValueError, OSError):
            pass


def die_with_parent():
    """A preexec_fn: on Linux the child is SIGKILLed when the runner dies, however it dies."""
    if not sys.platform.startswith("linux"):
        return None

    def preexec() -> None:
        try:
            import ctypes
            libc = ctypes.CDLL(None, use_errno=True)
            libc.prctl(1, signal.SIGKILL)  # PR_SET_PDEATHSIG
        except Exception:
            pass
    return preexec
