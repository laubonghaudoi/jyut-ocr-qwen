#!/usr/bin/env python3
"""Repair an assembled book without re-running its pages: the finishing step
between assembly and finalize_page_markers.py.

It reads the sealed pages (proofread/), the annotated assembly and its page
list, both engine drafts, the renders, the book profile and the page
manifest, and writes a NEW folder (--output).  Nothing it reads is ever
written: an output inside an input folder is refused, and every input file's
SHA-256 is taken before the run and checked after it.

The run, in order:

1. the inputs are verified (each sealed page against its own seal and the
   page list; the assembled page text against the sealed text; each render
   against the page manifest) - exit 2 on any failure;
2. the book model is learned from the book itself (book-model.json:
   running heads, volume labels, folios, dividers, contents pages, engine
   B's stand-ins, geometry and paragraph indents, each with its gate); a
   failed gate is a `gate-failed` doubt, a folio jump a `leaves-missing` one;
3. the defect counters (_book_lint.py) are taken on the sealed text;
4. the repair stages run in order, each switchable: furniture, marks,
   headings (per page), the model's questions (--no-model), contents,
   title page, heading levels, paragraphs and joins (book level).  Every change is an offset
   edit logged in repair-log.jsonl with its page, the text before and after,
   the rule or question, and the evidence; two edits over the same text are
   a `conflict` doubt.  The questions stage asks the model the questions
   the per-page stages planned (_repair_questions.py: one crop each, phase
   3's Client, its effort ladder, max_tokens and in-flight cap); each later
   stage's questions are asked as soon as that stage has run, so the next
   stage works on the answered text.  An answer a guard refuses is a doubt,
   never an edit; every answer is kept in answers.jsonl as it comes, and
   --resume asks nothing it holds (with --no-model it uses what it holds and
   lists the rest, asking nothing);
5. the pages, the repaired annotated book, the log, the questions and the
   doubts are written; the log is replayed on the sealed pages and must give
   the written pages and book byte for byte (exit 5 otherwise); the
   counters are taken again; the inputs are hashed again (exit 2 if any
   changed); repair-report.json says what ran, what changed and what did
   not.

A stage that is not in this build says so in the report ("not built") and
changes nothing.

Usage:
    python3 scripts/repair_book.py BOOK --output BOOK/repaired [--pages SPEC]
        [--plan-only] [--no-model] [--resume] [--verify-sample FRACTION]
        [--endpoint URL] [--model NAME] [--reasoning-effort xhigh] [--max-tokens 16000]
        [--max-inflight 8] [--timeout SECONDS]
        [--no-furniture] [--no-marks] [--no-headings] [--no-contents]
        [--no-title-page] [--no-levels] [--no-paragraphs] [--no-joins]

Exit codes: 0 done; 2 inputs failed verification (or changed during the
run, or the output lies in an input folder); 3 the output folder exists;
4 boundaries.json fails the finalize contract; 5 the log replay differs from
the written output; 6 the model could not be asked (the answers already
given are kept: run again with --resume).
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Callable, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proofread_pages as pp  # noqa: E402
import _book_lint as lint  # noqa: E402
import _repair_edits as re_  # noqa: E402
import _repair_inputs as ri  # noqa: E402
import _repair_model as rm  # noqa: E402
import _repair_joins as rj  # noqa: E402
import _repair_questions as rq  # noqa: E402
import _repair_rules as rr  # noqa: E402
import _repair_structure as rs  # noqa: E402
from _ocr_markdown import parse_page_spec  # noqa: E402


SCHEMA_VERSION = 1

EXIT_DONE = 0
EXIT_INPUTS = 2
EXIT_OUTPUT_EXISTS = 3
EXIT_BOUNDARIES = 4
EXIT_REPLAY = 5
EXIT_MODEL = 6


@dataclass
class StageResult:
    """What one stage proposes: edits, the questions it plans, and doubts
    (kind, page, detail, fields)."""
    edits: list[re_.Edit] = field(default_factory=list)
    questions: list[dict[str, Any]] = field(default_factory=list)
    doubts: list[tuple[str, int | None, str, dict[str, Any]]] = field(default_factory=list)


@dataclass
class Context:
    """What a stage reads: the book, its model, the ledger (the page texts
    as they stand), the run's arguments and the answers of an earlier run.
    A stage that needs the text its own first edits leave (the marks
    stage's second pass) applies them with apply() before it returns."""
    book: ri.Book
    model: dict[str, Any]
    ledger: re_.Ledger
    arguments: argparse.Namespace
    answers: dict[str, dict[str, Any]]
    output: Path
    stage: str = ""
    _facts: rr.BookFacts | None = None
    _readings: rs.Readings | None = None
    # What the joins stage decides: each marker page's label, and why.
    boundaries: dict[int, str] | None = None
    boundary_evidence: dict[str, Any] | None = None

    def facts(self) -> rr.BookFacts:
        """What the rules read of the book model, and the book-wide counts."""
        if self._facts is None:
            self._facts = rr.book_facts(self.book, self.model)
        return self._facts

    def readings(self) -> rs.Readings:
        """The structure rules' page readings, shared by their stages."""
        if self._readings is None:
            self._readings = rs.Readings(self.book, self.model)
        return self._readings

    def apply(self, edits: Sequence[re_.Edit]) -> None:
        self.ledger.apply(self.stage, edits)

    def order(self) -> list[int]:
        return list(self.book.assembly.order)


def furniture_stage(context: Context) -> StageResult:
    """Running heads, run suffixes, folios and answers at band spots
    (_repair_rules F1-F7), and the body's characters lost at a page's edge
    (F8)."""
    plan = rr.furniture(context.book, context.model, context.ledger.texts, context.order(), context.facts())
    return StageResult(plan.edits, plan.questions, plan.doubts)


def marks_stage(context: Context) -> StageResult:
    """Engine B's stand-ins, marks and brackets (_repair_rules K1-K14, K-seq):
    the first pass is applied before the second is proposed."""
    plan = rr.marks(context.book, context.model, context.ledger.texts, context.order(), context.apply,
                    context.facts())
    return StageResult(plan.edits, plan.questions, plan.doubts)


def headings_stage(context: Context) -> StageResult:
    """Heading content per page (_repair_structure H-JOIN, S6, S7x, S8, S10,
    S15), in passes applied before the last is proposed."""
    plan = rs.headings(context.book, context.model, context.ledger.texts, context.order(), context.apply,
                       context.facts(), context.readings())
    return StageResult(plan.edits, plan.questions, plan.doubts)


def contents_stage(context: Context) -> StageResult:
    """The contents and their units (_repair_structure S9, S4, S16, S7, S11),
    in passes applied before the last is proposed."""
    plan = rs.contents_stage(context.book, context.model, context.ledger.texts, context.order(), context.apply,
                             context.facts(), context.readings())
    return StageResult(plan.edits, plan.questions, plan.doubts)


def title_page_stage(context: Context) -> StageResult:
    """A page printed right to left (_repair_structure S13)."""
    plan = rs.title_pages(context.book, context.model, context.ledger.texts, context.order(), context.facts(),
                          context.readings())
    return StageResult(plan.edits, plan.questions, plan.doubts)


def levels_stage(context: Context) -> StageResult:
    """Every heading's kind and one level scheme (_repair_structure S5,
    S12)."""
    plan = rs.levels(context.book, context.model, context.ledger.texts, context.order(), context.facts(),
                     context.readings())
    return StageResult(plan.edits, plan.questions, plan.doubts)


def paragraphs_stage(context: Context) -> StageResult:
    """Paragraphing within pages (_repair_joins P4, P7, P1, P2, P6; and
    _repair_rules P5, the blank line around a heading)."""
    plan = rj.paragraphs(context.book, context.model, context.ledger.texts, context.order(), context.apply,
                         context.facts(), context.readings())
    return StageResult(plan.edits, plan.questions, plan.doubts)


def joins_stage(context: Context) -> StageResult:
    """Every page boundary's label (_repair_joins S, T, H, L, J1-J4, P-1-P-3),
    kept on the context for boundaries.json; P6 across a join."""
    demoted = {r["page"] for r in context.ledger.records if r.get("rule") == "S10"}
    plan, labels, evidence = rj.joins(context.book, context.model, context.ledger.texts, context.order(),
                                      demoted, context.facts(), context.readings())
    context.boundaries, context.boundary_evidence = labels, evidence
    return StageResult(plan.edits, plan.questions, plan.doubts)


def questions_stage(context: Context) -> StageResult:
    """The model's questions (_repair_questions): run() asks the questions
    the stages before it planned at this place in the order, and each later
    stage's as soon as it has run; this stands for the stage in STAGES."""
    return StageResult()


@dataclass(frozen=True)
class Stage:
    name: str
    switch: str | None
    run: Callable[[Context], StageResult] | None


# The stages in the order they run (the design's: per page furniture, marks
# and heading content; the model's questions; then the book-level contents,
# title page, paragraphs and joins).  `run` is None for a stage not in this
# build: it is reported "not built" and changes nothing.
STAGES: tuple[Stage, ...] = (
    Stage("furniture", "--no-furniture", furniture_stage),
    Stage("marks", "--no-marks", marks_stage),
    Stage("headings", "--no-headings", headings_stage),
    Stage("questions", "--no-model", questions_stage),
    Stage("contents", "--no-contents", contents_stage),
    Stage("title-page", "--no-title-page", title_page_stage),
    Stage("levels", "--no-levels", levels_stage),
    Stage("paragraphs", "--no-paragraphs", paragraphs_stage),
    Stage("joins", "--no-joins", joins_stage),
)
# The rules each built stage runs in this build (the report names them; a
# stage's other rules are not built yet).
STAGE_RULES = {
    "furniture": ["F1", "F2", "F2b", "F2c", "F3", "F4", "F5", "F6", "F7", "F8"],
    "marks": ["K1", "K2", "K2-stray", "K3", "K4a", "K4b", "K5", "K6", "K7a", "K7b", "K8", "K9", "K10", "K12",
              "K13", "K14", "K-seq"],
    "headings": ["H-JOIN", "S6", "S7x", "S8", "S10", "S15"],
    "contents": ["S9", "S6", "S4", "S16", "S7", "S11"],
    "title-page": ["S13"],
    "levels": ["S5", "S12"],
    "paragraphs": ["P4", "P7", "P1", "P2", "P6", "P5"],
    "joins": ["S", "T", "H", "L", "P-3", "J1", "J2", "J3", "J4", "P-1", "P-2", "P6"],
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("book", type=Path, help="the book folder (proofread/, assembled/, renders/, ocr-*/)")
    parser.add_argument("--output", type=Path, required=True,
                        help="a new folder for the repaired book; refused if it exists (unless --resume) "
                             "or lies in an input folder")
    for name, what in (("assembled", "the annotated assembly"), ("page-sources", "the assembly's page list"),
                       ("proofread", "the sealed pages' folder"), ("renders", "the renders' folder"),
                       ("ocr-a", "engine A's drafts"), ("ocr-b", "engine B's drafts"),
                       ("profile", "book-profile.json"), ("page-manifest", "the page manifest")):
        parser.add_argument(f"--{name}", type=Path, help=f"{what} (default: the book folder's layout)")
    parser.add_argument("--pages", help="only these scan pages, e.g. 1-9,17 (a benchmark subset); without "
                                        "--assembled the annotated text is built from the sealed pages")
    parser.add_argument("--plan-only", action="store_true",
                        help="detect and write the plan (repair-plan.jsonl, questions.json); ask nothing, "
                             "write no repaired text")
    parser.add_argument("--no-model", action="store_true",
                        help="ask the model nothing: every question becomes a `look-not-asked` doubt - but with "
                             "--resume, the answers the earlier run holds are used as they would be, and only the "
                             "questions none of them answers are (listed in the report's model.unasked)")
    parser.add_argument("--resume", action="store_true",
                        help="reuse an existing --output this tool wrote, and the answers in its questions.json")
    for stage in STAGES:
        if stage.switch and stage.switch != "--no-model":
            parser.add_argument(stage.switch, action="store_true", help=f"skip the {stage.name} stage")
    parser.add_argument("--verify-sample", type=float, default=0.0, metavar="FRACTION",
                        help="re-check this share (0-1) of the mechanical edits with a print question "
                             "(default 0)")
    parser.add_argument("--workers", type=int, default=min(6, os.cpu_count() or 1),
                        help="CPU processes for the book model and the counters")
    # The model, as phase 3 asks it (proofread_pages.py's defaults).
    parser.add_argument("--endpoint", default=os.environ.get("PROOFREAD_ENDPOINT", pp.DEFAULT_ENDPOINT),
                        help="the model server's chat endpoint (phase 3's)")
    parser.add_argument("--model", default=os.environ.get("PROOFREAD_MODEL", pp.DEFAULT_MODEL),
                        help="the model's name (phase 3's)")
    ladder = " -> ".join(str(rung) for rung in pp.Client.EFFORT_LADDER)
    parser.add_argument("--reasoning-effort", default=os.environ.get("PROOFREAD_EFFORT", pp.DEFAULT_EFFORT),
                        help=f"the first rung of the effort ladder (default {pp.DEFAULT_EFFORT}); a call cut off "
                             f"at --max-tokens is asked again a rung lower ({ladder})")
    parser.add_argument("--max-tokens", type=int, default=16000, help="each call's max_tokens (phase 3's)")
    parser.add_argument("--max-inflight", type=int,
                        default=int(os.environ.get("PROOFREAD_MAX_INFLIGHT") or 0) or pp.DEFAULT_WORKERS,
                        help="requests on the wire at once: the server's lanes (default: PROOFREAD_MAX_INFLIGHT, "
                             f"else {pp.DEFAULT_WORKERS})")
    parser.add_argument("--timeout", type=float, default=1800.0, help="seconds one request may take")
    return parser


def build_client(arguments: argparse.Namespace) -> Any:
    """Phase 3's Client, as the run's arguments set it."""
    effort = None if arguments.reasoning_effort.lower() == "none" else arguments.reasoning_effort
    return pp.Client(arguments.endpoint, arguments.model, effort, arguments.timeout,
                     max_inflight=max(1, arguments.max_inflight))


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8")


def code_identity() -> dict[str, Any]:
    """The skill's commit and whether its scripts differ from it, plus a hash
    of the repair tool's own files."""
    here = Path(__file__).resolve().parent
    names = sorted(p.name for p in here.glob("*.py") if p.name.startswith(("_repair", "repair_book", "_book_lint")))
    digest = hashlib.sha256()
    for name in names:
        digest.update(name.encode() + b"\0" + (here / name).read_bytes())
    out: dict[str, Any] = {"files": names, "sha256": digest.hexdigest(), "commit": None, "dirty": None}
    try:
        out["commit"] = subprocess.run(["git", "-C", str(here), "rev-parse", "HEAD"], capture_output=True,
                                       text=True, timeout=10, check=True).stdout.strip() or None
        # --no-optional-locks: a plain status may rewrite the repository's
        # index, a write outside the output folder.
        status = subprocess.run(["git", "--no-optional-locks", "-C", str(here), "status", "--porcelain", "--", "."],
                                capture_output=True, text=True, timeout=10, check=True).stdout
        out["dirty"] = bool(status.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return out


def clear_earlier_run(output: Path) -> list[str]:
    """--resume: remove what an earlier run wrote in OUTPUT, but the answers
    and crops a resumed run reuses (ri.REUSED_FILES, crops/).  Only the
    tool's own names are removed: the page texts pages/page-NNNN.md (and
    their temporary files), and ri.RUN_FILES.  Returns what was removed."""
    removed = []
    pages = output / "pages"
    if pages.is_dir() and not pages.is_symlink():
        for path in sorted(pages.iterdir()):
            name = path.name
            if path.is_file() and not path.is_symlink() and re.fullmatch(r"\.?page-\d+\.md(?:\.tmp)?", name):
                path.unlink()
                removed.append(f"pages/{name}")
    for name in ri.RUN_FILES:
        path = output / name
        if path.is_file() and not path.is_symlink():
            path.unlink()
            removed.append(name)
    return removed


def load_answers(output: Path) -> dict[str, dict[str, Any]]:
    """The answers of an earlier run in OUTPUT (--resume), by call hash."""
    return rq.load_answers(output)


def model_doubts(model: Mapping[str, Any], ledger: re_.Ledger) -> None:
    """A `gate-failed` doubt for every gate the book failed, and a
    `leaves-missing` doubt for every jump in the folio sequence."""
    for name, gate in sorted((model.get("gates") or {}).items()):
        if not gate.get("passed"):
            measured = {k: v for k, v in gate.items() if k != "passed"}
            ledger.doubt("gate-failed", None, f"{name} failed on this book; the rules that need it stay silent",
                         gate=name, measured=measured)
    for jump in (model.get("folio") or {}).get("jumps") or []:
        if jump.get("kind") == "leaves-missing":
            ledger.doubt("leaves-missing", jump["before"],
                         f"folios {jump['missingFrom']}-{jump['missingTo']} of run {jump['suffix']!r} are not in "
                         f"the scan (between scans {jump['after']} and {jump['before']})", jump=jump)


def choose_sample(records: Sequence[Mapping[str, Any]], fraction: float, seed: str) -> list[str]:
    """--verify-sample: a share of the mechanical edits (rule, no question),
    the same share of the same edits on every run of the same inputs."""
    mechanical = [r for r in records if r.get("rule") and not r.get("question")]
    if fraction <= 0 or not mechanical:
        return []
    size = max(1, round(fraction * len(mechanical)))
    ranked = sorted(mechanical, key=lambda r: hashlib.sha256(f"{seed}:{r['id']}".encode()).hexdigest())
    return sorted(r["id"] for r in ranked[:size])


def assign_ids(questions: Sequence[dict[str, Any]], taken: set[str]) -> None:
    """Q0001, Q0002, ... to the questions without an id, in plan order."""
    number = 0
    for question in questions:
        if question.get("id"):
            taken.add(question["id"])
    for question in questions:
        if question.get("id"):
            continue
        number += 1
        while f"Q{number:04d}" in taken:
            number += 1
        question["id"] = f"Q{number:04d}"
        taken.add(question["id"])


def unasked_summary(unasked: Mapping[Any, Mapping[str, Any]]) -> dict[str, Any]:
    """--no-model on a resumed run: the calls no held answer answers - how
    many, of how many questions, by call kind and by role (a question's
    first call, or a follow-up: a second glyph round, a copied character's
    glyph question)."""
    calls = list(unasked.values())
    return {"calls": len(calls), "questions": len({c["question"] for c in calls}),
            "byKind": dict(Counter(c["kind"] for c in calls)),
            "followUps": sum(1 for c in calls if c["role"] != "main")}


def clear_crops(output: Path, kept: set[str]) -> None:
    """Crops of an earlier run that no question of this run names."""
    folder = output / rq.CROPS
    if not folder.is_dir() or folder.is_symlink():
        return
    for path in folder.iterdir():
        if re.fullmatch(r"Q\d+-[a-z0-9]+\.png", path.name) and path.is_file() and not path.is_symlink() \
                and f"{rq.CROPS}/{path.name}" not in kept:
            path.unlink()


def run(arguments: argparse.Namespace, client: Any | None = None) -> int:
    started = time.monotonic()
    timings: dict[str, float] = {}
    if not 0.0 <= arguments.verify_sample <= 1.0:
        print("--verify-sample is a share between 0 and 1", file=sys.stderr)
        return EXIT_INPUTS
    given = {"assembled": arguments.assembled, "page_sources": arguments.page_sources,
             "proofread": arguments.proofread, "renders": arguments.renders, "ocr_a": arguments.ocr_a,
             "ocr_b": arguments.ocr_b, "profile": arguments.profile, "page_manifest": arguments.page_manifest}
    paths = ri.InputPaths.resolve(arguments.book, given)
    try:
        output = ri.check_output(arguments.output, paths, arguments.resume)
    except ri.OutputError as error:
        print(f"output refused: {error}", file=sys.stderr)
        return EXIT_OUTPUT_EXISTS if error.exists else EXIT_INPUTS
    try:
        pages = parse_page_spec([arguments.pages]) if arguments.pages else None
    except ValueError as error:
        print(f"--pages: {error}", file=sys.stderr)
        return EXIT_INPUTS
    try:
        book = ri.load_book(paths, pages)
    except ri.InputError as error:
        print(f"inputs failed verification:\n{error}", file=sys.stderr)
        return EXIT_INPUTS
    files = ri.input_files(book)
    hashes_before = ri.hash_inputs(files)
    timings["inputs"] = round(time.monotonic() - started, 2)
    answers = load_answers(output) if arguments.resume else {}
    output.mkdir(parents=True, exist_ok=arguments.resume)
    # The folder says a run is under way until its report is written at the
    # end: a run that stops half way leaves no earlier run's report beside
    # its own files, and stays resumable.
    atomic_write(output / ri.REPORT_NAME, json_bytes({"tool": ri.TOOL_NAME, "schemaVersion": SCHEMA_VERSION,
                                                      "status": "running", "generatedAt": pp.utc_now()}))
    cleared = clear_earlier_run(output) if arguments.resume else []

    mark = time.monotonic()
    model = rm.learn(book, workers=arguments.workers)
    atomic_write(output / "book-model.json", json_bytes(model))
    timings["model"] = round(time.monotonic() - mark, 2)

    order = book.assembly.order
    sealed = {scan: book.pages[scan].sealed_text for scan in order}
    ledger = re_.Ledger(sealed)
    model_doubts(model, ledger)
    mark = time.monotonic()
    lint_before = lint.lint_book(book, model, sealed, workers=arguments.workers)
    timings["lint-before"] = round(time.monotonic() - mark, 2)

    context = Context(book, model, ledger, arguments, answers, output)
    stages: dict[str, dict[str, Any]] = {}
    questions: list[dict[str, Any]] = []
    taken: set[str] = set()
    # The model's questions: asked with phase 3's Client, unless --no-model;
    # under --plan-only their crops and prompts are made and nothing is asked.
    asker = None
    if not arguments.no_model:
        if client is None and not arguments.plan_only:
            client = build_client(arguments)
        asker = rq.Asker(None if arguments.plan_only else client, output, answers, arguments.max_tokens,
                         arguments.max_inflight, plan_only=arguments.plan_only)
    elif arguments.resume and answers and not arguments.plan_only:
        # --no-model on a resumed run: the answers the earlier run holds are
        # used as they would be; a question none of them answers is listed
        # (`look-not-asked`, and model.unasked in the report), never asked.
        # The Client only says how a call would be asked: it sends nothing.
        asker = rq.Asker(client or build_client(arguments), output, answers, arguments.max_tokens,
                         arguments.max_inflight, listing=True)
    pending: list[dict[str, Any]] = []
    asking = False
    failure: str | None = None

    def ask_now(batch: list[dict[str, Any]], label: str) -> rq.Outcome:
        env = rq.Env(book, model, ledger, context.readings(), context.facts(), asker, list(order),
                     context.boundaries, context.boundary_evidence)
        return rq.ask(batch, env, label)

    for stage in STAGES:
        off = stage.switch and stage.switch != "--no-model" and getattr(arguments, stage.switch[2:].replace("-", "_"))
        if off:
            stages[stage.name] = {"status": f"off ({stage.switch})"}
            continue
        if stage.run is None:
            stages[stage.name] = {"status": "not built"}
            continue
        if stage.name == "questions":
            if asker is None:
                stages[stage.name] = {"status": "off (--no-model)"}
                continue
            mark = time.monotonic()
            logged, doubted = len(ledger.records), len(ledger.doubts)
            asked, reused = asker.asked, asker.reused
            try:
                outcome = ask_now(pending, stage.name)
            except pp.ProofreadError as error:
                failure = str(error)
                stages[stage.name] = {"status": f"failed: {failure}"}
                break
            stages[stage.name] = {"status": "ran", "questions": len(pending), "edits": len(ledger.records) - logged,
                                  "doubts": len(ledger.doubts) - doubted, "asked": asker.asked - asked,
                                  "reused": asker.reused - reused, "outcomes": dict(outcome.counts),
                                  "seconds": round(time.monotonic() - mark, 2)}
            pending = []
            asking = True
            continue
        mark = time.monotonic()
        logged = len(ledger.records)
        context.stage = stage.name
        result = stage.run(context)
        # Under --plan-only the edits are applied in memory too, so each
        # stage plans against the text the one before it would leave.
        ledger.apply(stage.name, result.edits)
        for question in result.questions:
            question.setdefault("stage", stage.name)
        questions.extend(result.questions)
        assign_ids(questions, taken)
        entry = {"status": "ran", "edits": len(ledger.records) - logged,
                 "questions": len(result.questions), "doubts": len(result.doubts),
                 "rules": STAGE_RULES.get(stage.name)}
        settled: set[int] = set()
        if asker is not None and asking and result.questions:
            # A stage after the questions stage: its questions now, before
            # its doubts are written (an answered boundary is no doubt).
            logged = len(ledger.records)
            asked, reused = asker.asked, asker.reused
            try:
                outcome = ask_now(result.questions, f"{stage.name}-questions")
            except pp.ProofreadError as error:
                failure = str(error)
                entry["status"] = f"failed: {failure}"
                stages[stage.name] = entry
                break
            settled = outcome.settled
            entry.update(answered={"edits": len(ledger.records) - logged, "asked": asker.asked - asked,
                                   "reused": asker.reused - reused, "outcomes": dict(outcome.counts)})
        else:
            pending.extend(result.questions)
        for kind, page, detail, fields in result.doubts:
            if kind == "boundary-unverified" and page in settled:
                continue
            ledger.doubt(kind, page, detail, stage=stage.name, **fields)
        entry["seconds"] = round(time.monotonic() - mark, 2)
        stages[stage.name] = entry

    seed = hashlib.sha256("".join(sorted(v or "" for v in hashes_before.values())).encode()).hexdigest()
    sample = choose_sample(ledger.records, arguments.verify_sample, seed) if failure is None else []
    verify = []
    for edit_id in sample:
        record = next(r for r in ledger.records if r["id"] == edit_id)
        verify.append({"kind": "Q-P", "purpose": "verify", "edit": edit_id, "page": record["page"],
                       "status": "planned", "stage": "verify"})
    questions.extend(verify)
    assign_ids(questions, taken)
    if verify and asker is not None and failure is None:
        try:
            ask_now(verify, "verify")
        except pp.ProofreadError as error:
            failure = str(error)
    for question in questions:
        if arguments.plan_only:
            question.setdefault("status", "planned")
            continue
        if question.get("status") not in (None, "planned"):
            continue
        why = ("--no-model" if arguments.no_model else f"the model could not be asked ({failure})" if failure
               else "no question stage ran after it was planned")
        question["status"] = "not-asked"
        ledger.doubt("look-not-asked", question.get("page"), f"{question.get('kind')} {question.get('id')}: {why}",
                     question=question.get("id"))
    if asker is not None:
        clear_crops(output, asker.crops)

    written: dict[str, str] = {}
    log_name = "repair-plan.jsonl" if arguments.plan_only else "repair-log.jsonl"
    data = re_.log_bytes(ledger.records)
    atomic_write(output / log_name, data)
    written[log_name] = pp.sha256_bytes(data)
    for name, value in (("questions.json", questions), ("doubts.json", ledger.doubts)):
        data = json_bytes(value)
        atomic_write(output / name, data)
        written[name] = pp.sha256_bytes(data)

    checks: dict[str, Any] = {"logRecords": [p for r in ledger.records for p in re_.record_problems(r)]}
    lint_after = None
    status = EXIT_DONE if failure is None else EXIT_MODEL
    boundaries = context.boundaries
    if not arguments.plan_only:
        combined = book.assembly.compose(ledger.texts)
        if boundaries is not None:
            manifest = {"boundaries": {str(scan): boundaries[scan] for scan in sorted(boundaries)}}
            evidence = {"boundaries": context.boundary_evidence or {}}
            for name, value in (("boundaries.json", manifest), ("boundary-evidence.json", evidence)):
                data = json_bytes(value)
                atomic_write(output / name, data)
                written[name] = pp.sha256_bytes(data)
            problems = rj.contract_problems(combined, boundaries)
            checks["boundaryContract"] = {"passed": not problems, "problems": problems[:50],
                                          "labels": len(boundaries)}
            if problems:
                status = EXIT_BOUNDARIES
        else:
            checks["boundaryContract"] = {"passed": None, "why": "the joins stage did not run"}
        for scan in order:
            data = ledger.texts[scan].encode("utf-8")
            atomic_write(output / "pages" / f"{ri.page_stem(scan)}.md", data)
        data = combined.encode("utf-8")
        atomic_write(output / "combined-repaired.md", data)
        written["combined-repaired.md"] = pp.sha256_bytes(data)
        # The replay: the sealed pages as read again from disk, the log as
        # written, against the files as written.
        try:
            logged = re_.read_log((output / log_name).read_text(encoding="utf-8").splitlines())
            again = {scan: book.pages[scan].paths["md"].read_text(encoding="utf-8") for scan in order}
            replayed = re_.replay(again, logged)
            on_disk = {scan: (output / "pages" / f"{ri.page_stem(scan)}.md").read_text(encoding="utf-8")
                       for scan in order}
            same_pages = replayed == on_disk
            same_book = book.assembly.compose(replayed).encode("utf-8") == (output / "combined-repaired.md").read_bytes()
            checks["logReplay"] = {"passed": same_pages and same_book, "pages": same_pages, "book": same_book,
                                   "records": len(logged)}
        except (re_.ReplayError, OSError, json.JSONDecodeError) as error:
            checks["logReplay"] = {"passed": False, "error": str(error)}
        if not checks["logReplay"]["passed"]:
            status = EXIT_REPLAY if status in (EXIT_DONE, EXIT_BOUNDARIES) else status
        mark = time.monotonic()
        explained: dict[int, Counter] = {}
        for record in ledger.records:
            if record.get("question"):
                explained.setdefault(record["page"], Counter()).update(pp.CJK(record["before"]))
        lint_after = lint.lint_book(book, model, ledger.texts, combined, boundaries=boundaries,
                                    evidence={"boundaries": context.boundary_evidence or {}} if boundaries else None,
                                    explained=explained, workers=arguments.workers)
        timings["lint-after"] = round(time.monotonic() - mark, 2)
    else:
        checks["logReplay"] = {"passed": None, "why": "--plan-only writes no repaired text"}
    data = json_bytes({"before": lint_before, "after": lint_after})
    atomic_write(output / "lint.json", data)
    written["lint.json"] = pp.sha256_bytes(data)
    written["book-model.json"] = pp.sha256_file(output / "book-model.json")

    hashes_after = ri.hash_inputs(files)
    changed = sorted(path for path in hashes_before if hashes_before[path] != hashes_after.get(path))
    checks["inputsUnchanged"] = {"passed": not changed, "changed": changed}
    if changed:
        status = EXIT_INPUTS

    calls = asker.calls if asker is not None else []
    report = {
        "tool": ri.TOOL_NAME,
        "schemaVersion": SCHEMA_VERSION,
        "status": "finished" if failure is None else "failed",
        **({"error": f"the model could not be asked: {failure}"} if failure else {}),
        "generatedAt": pp.utc_now(),
        "book": str(paths.book),
        "code": code_identity(),
        "arguments": {"pages": arguments.pages, "planOnly": arguments.plan_only, "noModel": arguments.no_model,
                      "resume": arguments.resume, "verifySample": arguments.verify_sample,
                      "off": [s.switch for s in STAGES if s.switch and s.switch != "--no-model"
                              and getattr(arguments, s.switch[2:].replace("-", "_"))]},
        "pages": {"selected": len(book.order), "markers": len(order), "assembly": book.assembly.source},
        "notes": book.notes,
        "stages": stages,
        "counts": {
            "edits": len(ledger.records),
            "rules": dict(Counter(r["rule"] for r in ledger.records if r.get("rule"))),
            "questions": dict(Counter(q.get("kind") for q in questions)),
            "questionOutcomes": dict(Counter(q.get("status") for q in questions)),
            "doubts": dict(Counter(d["kind"] for d in ledger.doubts)),
        },
        "gates": {name: bool(g.get("passed")) for name, g in (model.get("gates") or {}).items()},
        "boundaries": None if boundaries is None else {
            "labels": dict(Counter(boundaries.values())),
            "rules": dict(Counter(e.get("rule") for e in (context.boundary_evidence or {}).values())),
            "unverified": sum(1 for e in (context.boundary_evidence or {}).values() if not e.get("verified"))},
        "lint": {"before": lint.summary(lint_before), "after": lint.summary(lint_after) if lint_after else None},
        "checks": checks,
        "verifySample": {"fraction": arguments.verify_sample, "edits": sample},
        "resume": {"answersAvailable": len(answers), "earlierOutputsRemoved": len(cleared),
                   "answersReused": asker.reused if asker else 0},
        "model": None if asker is None else {
            "endpoint": arguments.endpoint if not (arguments.plan_only or asker.listing) else None,
            "settings": asker.settings, "maxInflight": arguments.max_inflight,
            "ladder": [r or "none" for r in pp.Client.EFFORT_LADDER],
            "asked": asker.asked, "reused": asker.reused, "calls": pp.summarize_calls(calls),
            **({"unasked": unasked_summary(asker.unasked)} if asker.listing else {})},
        "inputs": {"files": len(files), "sha256": hashes_before},
        "outputs": written,
        "timings": {**timings, "total": round(time.monotonic() - started, 2)},
        "tokens": {"prompt": sum(c.get("prompt_tokens", 0) or 0 for c in calls),
                   "completion": sum(c.get("completion_tokens", 0) or 0 for c in calls)},
        "exitStatus": status,
    }
    atomic_write(output / ri.REPORT_NAME, json_bytes(report))
    print(f"repair_book: {len(order)} marker pages, {len(ledger.records)} edits, {len(questions)} questions, "
          f"{len(ledger.doubts)} doubts; stages: "
          + ", ".join(f"{name} {info['status']}" for name, info in stages.items())
          + f"; replay {checks['logReplay'].get('passed')}; inputs unchanged {not changed}; exit {status}")
    return status


def main(argv: Sequence[str] | None = None, client: Any | None = None) -> int:
    """The command line; CLIENT stands in for phase 3's Client (the offline
    checks' stand-in model)."""
    return run(build_parser().parse_args(argv), client)


if __name__ == "__main__":
    sys.exit(main())
