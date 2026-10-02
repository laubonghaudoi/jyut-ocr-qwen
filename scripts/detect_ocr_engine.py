#!/usr/bin/env python3
"""Report which of the skill's two local OCR engines are usable on this machine.

The skill reads every page with two engines: PaddleOCR-VL (the primary draft,
with layout blocks and tables) and HunyuanOCR (an independent second reading).
It is host-agnostic - Claude Code, Codex, Qwen Code or any other harness - so
rather than making the agent guess or probe by trial and error, this prints a
machine-readable verdict and the caller goes straight to the runners.

Usage:
    python3 scripts/detect_ocr_engine.py           # JSON verdict
    python3 scripts/detect_ocr_engine.py --brief   # one token: the engine name

Exit status is 0 when an engine is usable and 1 when none is, so a caller can
branch on the status alone.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

SCRIPTS = Path(__file__).resolve().parent

# Interpreters to try for PaddleOCR, in order.  PaddleOCR normally lives in a
# dedicated venv, so an explicit pointer wins over whatever is running this.
def paddle_interpreter_candidates(explicit: str | None) -> list[str]:
    import os

    candidates = [
        explicit,
        os.environ.get("PADDLEOCR_PYTHON"),
        sys.executable,
        shutil.which("python3"),
    ]
    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in candidates:
        if not candidate:
            continue
        # Never resolve(): a venv's bin/python is a symlink to the base
        # interpreter and following it discards the venv.
        path = os.path.abspath(shutil.which(candidate) or candidate)
        if path in seen or not Path(path).is_file():
            continue
        seen.add(path)
        ordered.append(path)
    return ordered


def probe_paddleocr(explicit: str | None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": "paddleocr-vl",
        "runner": str(SCRIPTS / "run_paddleocr_vl.py"),
        "available": False,
        "reason": "",
    }
    probe = (
        "import json, importlib.metadata as m, paddleocr\n"
        "def v(n):\n"
        "    try: return m.version(n)\n"
        "    except Exception: return None\n"
        "print(json.dumps({'paddleocr': getattr(paddleocr, '__version__', None),\n"
        "                  'paddlepaddle-gpu': v('paddlepaddle-gpu')}))\n"
    )
    tried: list[dict[str, str]] = []
    for interpreter in paddle_interpreter_candidates(explicit):
        result = subprocess.run(
            [interpreter, "-c", probe], text=True, capture_output=True, check=False
        )
        if result.returncode == 0:
            entry["available"] = True
            entry["interpreter"] = interpreter
            entry["reason"] = "paddleocr is importable"
            try:
                entry["versions"] = json.loads(result.stdout.strip().splitlines()[-1])
            except (json.JSONDecodeError, IndexError):
                entry["versions"] = {}
            return entry
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        tried.append(
            {"interpreter": interpreter, "error": detail[-1] if detail else "unknown"}
        )
    entry["reason"] = "paddleocr not importable by any candidate interpreter"
    entry["tried"] = tried
    return entry


def probe_hunyuanocr(explicit: str | None) -> dict[str, Any]:
    """A SECOND engine, run alongside the first rather than instead of it.

    Two independent drafts is what the proofread stage merges: agreement freezes
    a character, disagreement is resolved without a model call. Measured on this
    project's book, two engines agree on 94.3% of characters.
    """
    import os
    entry: dict[str, Any] = {
        "name": "hunyuanocr",
        "role": "second-opinion",
        "runner": str(SCRIPTS / "run_hunyuanocr.py"),
        "available": False,
        "reason": "",
    }
    model = explicit or os.environ.get("HUNYUAN_MODEL")
    mmproj = os.environ.get("HUNYUAN_MMPROJ")
    server = os.environ.get("HUNYUAN_LLAMA_SERVER") or shutil.which("llama-server")
    missing = [n for n, v in (("HUNYUAN_MODEL", model), ("HUNYUAN_MMPROJ", mmproj),
                              ("llama-server", server)) if not v]
    if missing:
        entry["reason"] = "not configured: " + ", ".join(missing)
        return entry
    absent = [str(x) for x in (model, mmproj, server) if not Path(x).is_file()]
    if absent:
        entry["reason"] = "configured but missing on disk: " + ", ".join(absent)
        return entry
    entry.update(available=True, reason="weights and llama-server present",
                 model=str(model), mmproj=str(mmproj), server=str(server))
    return entry


def probe_gpu() -> dict[str, Any]:
    """Free VRAM matters: PaddleOCR-VL cannot load behind a large LLM server."""
    smi = shutil.which("nvidia-smi")
    if not smi:
        return {"present": False}
    result = subprocess.run(
        [smi, "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return {"present": False}
    try:
        used, total = (int(v) for v in result.stdout.strip().splitlines()[0].split(","))
    except ValueError:
        return {"present": False}
    return {"present": True, "usedMiB": used, "totalMiB": total, "freeMiB": total - used}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brief", action="store_true", help="print only the engine name")
    parser.add_argument("--python", dest="interpreter", help="PaddleOCR interpreter hint")
    arguments = parser.parse_args(argv)

    engines = [probe_paddleocr(arguments.interpreter)]
    second = probe_hunyuanocr(None)
    selected = next((e["name"] for e in engines if e["available"]), None)

    verdict: dict[str, Any] = {
        "platform": sys.platform,
        "selected": selected,
        "engines": engines,
        "secondOpinion": second,
        "gpu": probe_gpu(),
    }

    gpu = verdict["gpu"]
    if selected == "paddleocr-vl" and gpu.get("present") and gpu["freeMiB"] < 4096:
        verdict["warning"] = (
            f"only {gpu['freeMiB']} MiB VRAM free; PaddleOCR-VL may fail to load "
            "behind a running LLM server. Stop or shrink that server first."
        )

    if second["available"] and selected:
        verdict["note"] = ("run BOTH: paddleocr-vl for text, layout and tables, and "
                           "hunyuanocr as an independent second draft, then merge")
    if arguments.brief:
        print((selected or "none") + ("+hunyuanocr" if second["available"] else ""))
    else:
        print(json.dumps(verdict, ensure_ascii=False, indent=2))
    return 0 if selected else 1


if __name__ == "__main__":
    raise SystemExit(main())
