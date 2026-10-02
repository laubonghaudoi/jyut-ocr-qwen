#!/usr/bin/env python3
"""Run the OCR draft phase, freeing GPU memory first if a local LLM server holds it.

Why this exists
---------------
On a single GPU the OCR model and a local LLM server usually cannot be resident
at the same time.  Measured on one RTX 5090 (32,607 MiB): a 27B NVFP4 server has
a 22,481 MiB floor before any KV cache, and PaddleOCR-VL peaks at 11,495 MiB.
They do not both fit.

That is awkward when the whole workflow runs *inside* an agent harness backed by
that same server: the agent would have to stop the server it is thinking on.

It works anyway, because during a FOREGROUND shell tool call the harness has no
request in flight and its conversation state is client-side.  Stopping the
server, doing the OCR and restarting it inside ONE command is invisible to the
harness apart from a cold prefix cache on the next turn.

It does not work in the background.  Measured 2026-09-23 in Qwen Code: the agent
backgrounded the handover because a whole book outlasts the harness's shell time
limit (120 s by default, 600 s at most); its next turn found the server stopped
(ECONNREFUSED), it gave up after two retries and exited, and its exit killed the
handover - SIGTERM to the process group, SIGKILL 200 ms later - before the
server came back.  So this script:

- skips the swap entirely when there is already enough free VRAM;
- takes a time budget (--max-seconds, or OCR_PHASE_MAX_SECONDS from the machine
  config) set below the harness's shell time limit: the runner stops between
  pages when the budget is spent, the server is restored, and the exit code is
  75 - "not finished, run the SAME command again".  Runners skip sealed pages,
  so repeated calls finish the book;
- restores the server on success, on failure, and on SIGINT/SIGTERM/SIGHUP;
- starts a detached watchdog, outside the process group, before releasing the
  server: if this process is killed before it has restored the server (a
  harness exit, a SIGKILL), the watchdog restores it;
- waits for the health endpoint and treats a failed restore as a hard error,
  because leaving the agent's own backend down is the worst possible outcome.

Configure the commands for your machine (they are intentionally not hard-coded,
since this skill runs on many hosts):

    export OCR_PHASE_RELEASE_CMD="systemctl --user stop ninfer.service"
    export OCR_PHASE_RESTORE_CMD="systemctl --user start ninfer.service"
    export OCR_PHASE_HEALTH_URL="http://127.0.0.1:8090/v1/models"
    export OCR_PHASE_MAX_SECONDS=540   # below the harness's shell time limit

    python3 scripts/run_ocr_phase.py -- \\
        python3 scripts/run_paddleocr_vl.py RENDER_DIR OUTPUT_DIR
    # exit 75: run the same command again; exit 0: done

Exit codes: 0 done; 75 time budget spent, server restored, call again;
2 configuration; 3 the server was NOT restored; otherwise the runner's own.
"""
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _phase_budget import DEADLINE_ENV, EXIT_INCOMPLETE, PROGRESS_ENV  # noqa: E402

# PaddleOCR-VL measured peak is 11,495 MiB at 300 DPI; leave a little margin.
DEFAULT_REQUIRED_MIB = 12288
DEFAULT_HEALTH_TIMEOUT = 180.0
# Time kept back from the budget to stop the runner and bring the server up.
# The reference server measured about 10 s from start to healthy; the rest is
# margin for a slower host.  Override with --restore-reserve.
DEFAULT_RESTORE_RESERVE = 60.0
# How long a runner gets to exit after SIGTERM before it is killed.
KILL_GRACE = 10.0
# After a restore that followed a phase killed mid-release, how long to watch for
# the interrupted stop landing late.  systemd's default stop timeout is 90 s, but
# a stop that has not landed after this long was not coming.
RELEASE_SETTLE_SECONDS = 45.0
# How long the watchdog lets an interrupted restore finish on its own before it
# runs the (repeatable) restore command itself.
RESTORE_GRACE_SECONDS = 15.0


class PhaseError(RuntimeError):
    """The phase cannot proceed safely."""


def say(message: str, *, error: bool = False) -> None:
    """Print without ever letting a closed stdout stop a restore.

    When the harness that started this command exits, the pipe behind stdout
    goes away; a print that raised there would abort the restore it announces.
    """
    try:
        print(message, file=sys.stderr if error else sys.stdout, flush=True)
    except (OSError, ValueError):
        pass


def free_vram_mib() -> int | None:
    """Free VRAM on device 0, or None when there is no NVIDIA GPU to ask about."""
    smi = shutil.which("nvidia-smi")
    if not smi:
        return None
    result = subprocess.run(
        [smi, "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        used, total = (int(v) for v in result.stdout.strip().splitlines()[0].split(","))
    except ValueError:
        return None
    return total - used


def run_command(command: str, *, label: str) -> None:
    say(f"[ocr-phase] {label}: {command}")
    result = subprocess.run(command, shell=True, check=False, stdin=subprocess.DEVNULL)
    if result.returncode != 0:
        raise PhaseError(f"{label} failed with exit code {result.returncode}")


def wait_for_health(url: str, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if 200 <= response.status < 300:
                    return True
        except (urllib.error.URLError, OSError, ValueError):
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(1.0)


def bring_back(restore_cmd: str, health_url: str | None, health_timeout: float,
               *, label: str = "restore") -> bool:
    """Run the restore command and wait for health; True when the server is back."""
    try:
        run_command(restore_cmd, label=label)
    except PhaseError as error:
        say(f"ERROR {error}", error=True)
        return False
    if health_url:
        if not wait_for_health(health_url, health_timeout):
            say(
                f"ERROR server did not become healthy at {health_url} "
                f"within {health_timeout:.0f}s",
                error=True,
            )
            return False
        say(f"[ocr-phase] health OK: {health_url}")
    return True


class Interrupted(BaseException):
    """A signal asked this phase to stop; cleanup happens in the finally blocks."""


def proc_start_time(pid: int) -> str | None:
    """Kernel start time of a process (Linux), to tell it from a reused pid."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as handle:
            return handle.read().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def gpu_pids() -> set[int] | None:
    """PIDs of the processes holding GPU memory, or None when that cannot be asked."""
    smi = shutil.which("nvidia-smi")
    if not smi:
        return None
    result = subprocess.run(
        [smi, "--query-compute-apps=pid", "--format=csv,noheader,nounits"],
        text=True, capture_output=True, check=False,
    )
    if result.returncode != 0:
        return None
    pids = set()
    for line in result.stdout.split():
        try:
            pids.add(int(line.strip().rstrip(",")))
        except ValueError:
            return None  # not the format asked for (an old driver, a stand-in)
    return pids


def wait_for_gpu_release(baseline: set[int] | None, timeout_seconds: float) -> None:
    """Wait until every GPU process that appeared after the release has exited.

    The processes present right after the release belong to someone else (another
    job sharing the card); anything newer is the OCR model, which must be gone
    before the server loads again.  Free VRAM would be a worse test: other users'
    memory moves while we wait.
    """
    if baseline is None:
        return
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        current = gpu_pids()
        if current is None or not (current - baseline):
            return
        time.sleep(0.5)
    say(f"WARNING a GPU process started during the OCR phase is still alive after "
        f"{timeout_seconds:.0f}s; restoring anyway", error=True)


def watchdog_main(arguments: argparse.Namespace) -> int:
    """Restore the server if the phase process ends without having done so.

    The phase process holds the write end of a pipe and reports each step into
    it: "releasing" before it stops the server, "released", "gpu-baseline PIDS"
    and "runner PID START" once the OCR runner is going, "restoring" and finally
    "restored".  The pipe reaches end-of-file however that process ends - even
    SIGKILL - so a missing "restored" after "releasing" means nobody finished
    bringing the server back.  The watchdog runs in its own session, so a
    process-group kill aimed at the phase does not reach it.
    """
    log_path = arguments.watchdog_log
    try:
        log = open(log_path, "a", encoding="utf-8") if log_path else None
    except OSError:
        log = None

    def note(message: str) -> None:
        if log is not None:
            log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [pid {os.getpid()}] {message}\n")
            log.flush()

    received = b""
    while True:
        try:
            chunk = os.read(arguments.watchdog_fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        received += chunk
    steps = received.decode("utf-8", "replace").split("\n")
    if "restored" in steps:
        return 0
    if "releasing" not in steps:
        return 0  # the server was never stopped
    note("phase process ended without restoring the server")
    sys.stdout = sys.stderr = log if log is not None else open(os.devnull, "w")
    baseline: set[int] | None = None
    for step in steps:
        parts = step.split()
        if parts[:1] == ["runner"] and len(parts) == 3:
            pid, started = int(parts[1]), parts[2]
            # Only the runner we were told about: a reused pid has another start time.
            if proc_start_time(pid) == started:
                try:
                    os.kill(pid, signal.SIGKILL)
                    note(f"killed the orphaned OCR runner {pid}")
                except OSError:
                    pass
        if parts[:1] == ["gpu-baseline"]:
            baseline = {int(x) for x in parts[1:]}
    wait_for_gpu_release(baseline, 60.0)
    if "restoring" in steps and "restore-failed" not in steps and arguments.health_url:
        # A restore was under way.  Whatever killed the phase usually killed the
        # restore command too, but a service manager finishes a start it was
        # already given: allow a short grace, then start it again ourselves.
        if wait_for_health(arguments.health_url, RESTORE_GRACE_SECONDS):
            note("the interrupted restore came up by itself")
            return 0
    # Restore even if the server still answers: a stop that was under way when
    # the phase died completes later.  The restore command must be safe to repeat.
    for attempt in range(1, 4):
        ok = bring_back(arguments.restore_cmd, arguments.health_url,
                        arguments.health_timeout, label="watchdog restore")
        note("server restored" if ok else "server was NOT restored")
        if not ok or "released" in steps or not arguments.health_url:
            break
        # Killed mid-release: the stop may still be finishing (a service manager
        # completes it without the client) and land after this start.  Watch
        # for that and start again if it does.
        if stays_up(arguments.health_url, RELEASE_SETTLE_SECONDS):
            break
        note(f"the server went down again after restore {attempt} (the interrupted "
             "stop finished later); restoring again")
    return 0 if ok else 3


def stays_up(url: str, seconds: float) -> bool:
    """True unless health fails twice in a row within the window."""
    deadline = time.monotonic() + seconds
    misses = 0
    while time.monotonic() < deadline:
        misses = 0 if wait_for_health(url, 0) else misses + 1
        if misses >= 2:
            return False
        time.sleep(1.0)
    return True


def start_watchdog(arguments: argparse.Namespace) -> int:
    """Start the detached watchdog; return the write end of its pipe."""
    read_fd, write_fd = os.pipe()
    log_path = os.environ.get("OCR_PHASE_WATCHDOG_LOG") or os.path.join(
        tempfile.gettempdir(), "ocr-phase-watchdog.log")
    command = [
        sys.executable, os.path.abspath(__file__),
        "--watchdog-fd", str(read_fd),
        "--watchdog-log", log_path,
        "--restore-cmd", arguments.restore_cmd,
        "--health-timeout", str(arguments.health_timeout),
    ]
    if arguments.health_url:
        command += ["--health-url", arguments.health_url]
    try:
        subprocess.Popen(
            command,
            pass_fds=(read_fd,),
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    finally:
        os.close(read_fd)
    return write_fd


def stop_process(process: subprocess.Popen | None) -> None:
    """SIGTERM (the runners turn it into a clean exit that closes their GPU child), then SIGKILL."""
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=KILL_GRACE)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def sealed_pages(progress_file: str) -> int:
    try:
        with open(progress_file, encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())
    except OSError:
        return 0


def run_runner(runner: list[str], env: dict[str, str], hard_stop: float | None,
               holder: dict[str, subprocess.Popen],
               on_start=None) -> int:
    """Run the runner; past the hard stop it is stopped.

    The runner checks the deadline itself between pages and caps each page at
    it, so the hard stop only catches a runner that ignores the budget (or a
    model that takes longer to load than the whole budget).  The wait polls
    instead of blocking, so a signal handler never interrupts a blocking
    ``wait`` that holds Popen's internal lock (measured: that deadlocked the
    phase with the server down).
    """
    process = subprocess.Popen(runner, env=env)
    holder["runner"] = process
    if on_start is not None:
        on_start(process)
    while True:
        try:
            return process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            pass
        if hard_stop is not None and time.time() >= hard_stop:
            say("[ocr-phase] the runner is past the time budget; stopping it", error=True)
            stop_process(process)
            sealed = sealed_pages(env.get(PROGRESS_ENV, ""))
            if sealed:
                return EXIT_INCOMPLETE
            say("ERROR the time budget ran out before a single page was sealed; "
                "calling again would do the same. Read the runner's output above.",
                error=True)
            return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--release-cmd",
        default=os.environ.get("OCR_PHASE_RELEASE_CMD"),
        help="shell command that frees GPU memory (env: OCR_PHASE_RELEASE_CMD)",
    )
    parser.add_argument(
        "--restore-cmd",
        default=os.environ.get("OCR_PHASE_RESTORE_CMD"),
        help="shell command that brings the server back (env: OCR_PHASE_RESTORE_CMD)",
    )
    parser.add_argument(
        "--health-url",
        default=os.environ.get("OCR_PHASE_HEALTH_URL"),
        help="URL polled after restore (env: OCR_PHASE_HEALTH_URL)",
    )
    parser.add_argument(
        "--required-mib",
        type=int,
        default=int(os.environ.get("OCR_PHASE_REQUIRED_MIB", DEFAULT_REQUIRED_MIB)),
        help=f"free VRAM the OCR model needs (default {DEFAULT_REQUIRED_MIB})",
    )
    parser.add_argument(
        "--health-timeout",
        type=float,
        default=DEFAULT_HEALTH_TIMEOUT,
        help=f"seconds to wait for health after restore (default {DEFAULT_HEALTH_TIMEOUT:.0f})",
    )
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=float(os.environ["OCR_PHASE_MAX_SECONDS"])
        if os.environ.get("OCR_PHASE_MAX_SECONDS") else None,
        help="time budget for this call, including the restore; set it below the "
             "harness's shell time limit (env: OCR_PHASE_MAX_SECONDS). Required when "
             "the server has to be stopped; 0 means no budget (only outside a harness)",
    )
    parser.add_argument(
        "--restore-reserve",
        type=float,
        default=float(os.environ.get("OCR_PHASE_RESTORE_RESERVE", DEFAULT_RESTORE_RESERVE)),
        help="seconds of the budget kept for stopping the runner and restoring the "
             f"server (default {DEFAULT_RESTORE_RESERVE:.0f})",
    )
    parser.add_argument(
        "--force-swap",
        action="store_true",
        help="release/restore even if free VRAM already looks sufficient",
    )
    parser.add_argument("--watchdog-fd", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--watchdog-log", help=argparse.SUPPRESS)
    parser.add_argument(
        "runner",
        nargs=argparse.REMAINDER,
        help="the OCR runner command, after a literal --",
    )
    return parser


RESULT_MEANING = {
    0: "DONE",
    EXIT_INCOMPLETE: "INCOMPLETE - time budget spent, finished pages are sealed, the "
                     "server is up: run the SAME command again",
    1: "FAILED - read the runner's summary and ERROR lines above; do not just repeat",
    2: "CONFIGURATION ERROR - nothing was run",
    3: "SERVER NOT RESTORED - the watchdog retries; if it stays down, restart it by hand",
}


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.watchdog_fd is not None:
        return watchdog_main(arguments)
    code = run_phase(arguments)
    # One line that stands on its own, whatever the caller does with the rest of
    # the output (an agent piping through `tail` loses the exit code itself).
    say(f"[ocr-phase] RESULT exit={code} "
        f"{RESULT_MEANING.get(code, 'runner exit code, see its output above')}")
    return code


def run_phase(arguments: argparse.Namespace) -> int:
    started = time.time()
    runner = arguments.runner
    if runner and runner[0] == "--":
        runner = runner[1:]
    if not runner:
        say("ERROR no runner command given (put it after --)", error=True)
        return 2

    env = dict(os.environ)
    env.pop(DEADLINE_ENV, None)
    progress = tempfile.NamedTemporaryFile(prefix="ocr-phase-progress-", delete=False)
    progress.close()
    env[PROGRESS_ENV] = progress.name
    hard_stop = None
    budgeted = bool(arguments.max_seconds)
    if budgeted:
        if arguments.max_seconds <= arguments.restore_reserve:
            say(f"ERROR --max-seconds ({arguments.max_seconds:.0f}) must exceed "
                f"--restore-reserve ({arguments.restore_reserve:.0f})", error=True)
            return 2
        # The runner stops starting pages a full reserve before the end; the hard
        # stop sits halfway into the reserve, leaving the other half to restore.
        env[DEADLINE_ENV] = f"{started + arguments.max_seconds - arguments.restore_reserve:.3f}"
        hard_stop = started + arguments.max_seconds - arguments.restore_reserve / 2

    holder: dict[str, subprocess.Popen] = {}
    try:
        return swap_and_run(arguments, runner, env, hard_stop, holder, budgeted)
    finally:
        try:
            os.unlink(progress.name)
        except OSError:
            pass


def swap_and_run(arguments: argparse.Namespace, runner: list[str], env: dict[str, str],
                 hard_stop: float | None, holder: dict[str, subprocess.Popen],
                 budgeted: bool) -> int:
    free = free_vram_mib()
    if free is None:
        # No NVIDIA GPU to arbitrate: nothing to free, just run the runner.
        say("[ocr-phase] no NVIDIA GPU detected; running the OCR runner directly")
        return run_runner(runner, env, hard_stop, holder)

    need_swap = arguments.force_swap or free < arguments.required_mib
    say(
        f"[ocr-phase] free VRAM {free} MiB, need {arguments.required_mib} MiB "
        f"-> {'swapping' if need_swap else 'no swap needed'}"
    )

    if not need_swap:
        return run_runner(runner, env, hard_stop, holder)

    if not arguments.release_cmd or not arguments.restore_cmd:
        say(
            f"ERROR only {free} MiB VRAM free but no release/restore commands are "
            "configured.\n"
            "       Set OCR_PHASE_RELEASE_CMD and OCR_PHASE_RESTORE_CMD (and ideally\n"
            "       OCR_PHASE_HEALTH_URL), or stop the GPU process yourself and re-run.",
            error=True,
        )
        return 2
    if arguments.max_seconds is None:
        # Without a budget a long call runs until the harness kills it; the
        # watchdog then saves the server but not the agent's next turn.
        say(
            "ERROR stopping the server needs a time budget: set OCR_PHASE_MAX_SECONDS "
            "(machine config) or --max-seconds below the harness's shell time limit, "
            "and run this in the FOREGROUND. Outside an agent harness, --max-seconds 0 "
            "runs without one.",
            error=True,
        )
        return 2

    state = {"restored": False, "restoring": False}
    watchdog_fd: int | None = None
    baseline: set[int] | None = None

    def tell_watchdog(step: str) -> None:
        if watchdog_fd is not None:
            try:
                os.write(watchdog_fd, f"{step}\n".encode())
            except OSError:
                pass

    def restore() -> bool:
        if state["restored"]:
            return True
        state["restoring"] = True
        # The OCR model must let go of the GPU before the server loads again.
        stop_process(holder.get("runner"))
        wait_for_gpu_release(baseline, 60.0)
        tell_watchdog("restoring")
        if not bring_back(arguments.restore_cmd, arguments.health_url,
                          arguments.health_timeout):
            tell_watchdog("restore-failed")  # no point waiting for it; retry at once
            return False
        state["restored"] = True
        tell_watchdog("restored")
        return True

    # A killed phase must not leave the agent's own backend down.  The handler
    # only raises: stopping the runner and restoring happen in the finally below,
    # outside any Popen call the signal may have interrupted.
    def on_signal(signum: int, _frame: object) -> None:
        if state["restoring"]:
            return  # already on the way back; let it finish
        say(f"\n[ocr-phase] caught signal {signum}; restoring before exit")
        raise Interrupted(signum)

    previous = {
        sig: signal.signal(sig, on_signal)
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    }

    def runner_started(process: subprocess.Popen) -> None:
        started = proc_start_time(process.pid)
        if started is not None:
            tell_watchdog(f"runner {process.pid} {started}")

    runner_code = 1
    interrupted: Interrupted | None = None
    try:
        watchdog_fd = start_watchdog(arguments)
        tell_watchdog("releasing")
        run_command(arguments.release_cmd, label="release")
        time.sleep(2)
        tell_watchdog("released")
        baseline = gpu_pids()
        if baseline is not None:
            tell_watchdog("gpu-baseline " + " ".join(str(pid) for pid in sorted(baseline)))
        released_free = free_vram_mib()
        say(f"[ocr-phase] free VRAM after release: {released_free} MiB")
        if released_free is not None and released_free < arguments.required_mib:
            say(
                f"WARNING still only {released_free} MiB free after release; "
                "the OCR model may fail to load",
                error=True,
            )
        say(f"[ocr-phase] running: {shlex.join(runner)}")
        runner_code = run_runner(runner, env, hard_stop, holder, runner_started)
    except PhaseError as error:
        say(f"ERROR {error}", error=True)
        runner_code = 2
    except Interrupted as signal_exit:
        interrupted = signal_exit
    finally:
        # Handlers stay in place (ignoring signals) until the server is back.
        state["restoring"] = True
        ok = restore()
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        if watchdog_fd is not None:
            # Closing without "restored" hands the restore to the watchdog.
            os.close(watchdog_fd)
        if not ok:
            # Losing the backend is worse than a failed OCR pass; say so loudly.
            say(
                "ERROR the GPU server was NOT restored (the watchdog will retry). "
                "If it stays down, restart it manually before continuing:\n"
                f"       {arguments.restore_cmd}",
                error=True,
            )
            return 3

    if interrupted is not None:
        return 128 + int(interrupted.args[0])
    say(f"[ocr-phase] OCR runner exit code {runner_code}")
    return runner_code


if __name__ == "__main__":
    raise SystemExit(main())
