#!/usr/bin/env python3
"""Offline check of the book repair tool's paragraph and page-boundary rules
(scripts/_repair_joins.py) through scripts/repair_book.py: the paragraphs
inside a page (P1, P2, P4, P6, P7) and each page marker's label in
boundaries.json (S, T, H, L, J1-J4, P-1, P-2), which must pass
finalize_page_markers.py's contract.

No model, no GPU, no corpus: made-up books (tests/repair_fixture.py), each
page changed only where a rule's case is set up.  The made-up print sets
paragraphs two cells down and 40 cells a column, so a page that ends with a
full last column and a page that opens flush are laid out on purpose:

Paragraphs:
- P1 a line break inside the page where engine A starts a block at the
  paragraph indent becomes a blank line; P2 a line break inside engine A's
  block, and one before a flush column after a full one, are joined; a line
  break before a flush column after a short one is a question.
- P7 two paragraphs the page runs together, where engine A starts a block
  set at the paragraph indent, are split; a numeral the page holds just
  before such a block, which engine A read outside it, is a question.
- P4 a line written twice that engine A read once keeps one copy; P6 two
  list items a blank line apart become a tight list.

Page boundaries:
- S the first marker; T inside the contents; H onto a unit's heading, and
  after a page that ends with a heading onto a column set down; J1 a flush
  column after a full, unfinished one; J2 the same after a finished
  sentence (the print opens its paragraphs indented, M-8b); J4 a quotation
  set four cells down that goes on at its indent after a full column and
  unfinished text (after a finished one it is a question); P-1 the
  paragraph indent after finished text; P-2 the indent after a short column
  and unfinished text; L a list running on across a page; P-3 a list set
  down after a column two cells short or more; after a join onto a list
  item, the blank line before the list's next item goes (P6).
- signals that disagree (flush after a short column and finished text) are
  a question (Q-B), written `paragraph`, unverified, a `boundary-unverified`
  doubt; --pages with a page left out between two is `paragraph`, unverified.
- boundaries.json covers every marker and passes finalize's contract; the
  evidence file says each label's rule and whether it is verified; a label
  the contract refuses is exit 4.
- a book whose paragraphs are not set down (M-8b failed) asks every soft
  break and every boundary no heading, list or contents settles.

Every run replays its log to its output, and the paragraph rules run again
on their own output change nothing.

Usage:
    python3 tests/check_repair_boundaries.py
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import offline  # noqa: E402,F401
import repair_fixture as fx  # noqa: E402

sys.path.insert(0, str(HERE.parent / "scripts"))
import _repair_edits as re_  # noqa: E402
import _repair_inputs as ri  # noqa: E402
import _repair_joins as rj  # noqa: E402
import repair_book  # noqa: E402


FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    print(f"{'ok  ' if condition else 'FAIL'} {message}")
    if not condition:
        FAILURES.append(message)


class Result:
    def __init__(self, status: int, out: Path, book: Path):
        self.status = status
        self.out = out
        self.report = json.loads((out / "repair-report.json").read_text(encoding="utf-8"))
        self.log = [json.loads(line) for line in (out / "repair-log.jsonl").read_text(encoding="utf-8").splitlines()]
        self.questions = json.loads((out / "questions.json").read_text(encoding="utf-8"))
        self.doubts = json.loads((out / "doubts.json").read_text(encoding="utf-8"))
        self.pages = {int(p.stem.split("-")[1]): p.read_text(encoding="utf-8") for p in (out / "pages").glob("*.md")}
        self.labels = {int(k): v for k, v in json.loads((out / "boundaries.json").read_text(encoding="utf-8"))
                       ["boundaries"].items()} if (out / "boundaries.json").is_file() else {}
        self.evidence = json.loads((out / "boundary-evidence.json").read_text(encoding="utf-8"))["boundaries"] \
            if (out / "boundary-evidence.json").is_file() else {}

    def rules(self, page: int) -> list[str]:
        return [r["rule"] for r in self.log if r["page"] == page]

    def asked(self, page: int) -> list[str]:
        return [q["rule"] for q in self.questions if q["page"] == page]

    def rule_of(self, page: int) -> str | None:
        return (self.evidence.get(str(page)) or {}).get("rule")

    def verified(self, page: int) -> bool:
        return bool((self.evidence.get(str(page)) or {}).get("verified"))


def repair(root: Path, spec: dict[int, dict[str, Any]], name: str, *argv: str) -> Result:
    book = fx.write_book(root / name, spec)
    out = root / f"{name}-out"
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        status = repair_book.main(["--workers", "1", str(book), "--output", str(out), "--no-model", *argv])
    return Result(status, out, book)


def again(root: Path, name: str, result: Result) -> list[Any]:
    """The paragraph rules run on RESULT's own pages (with the model of the
    book): what they would change."""
    book = ri.load_book(ri.InputPaths.resolve(root / name, {}))
    model = json.loads((result.out / "book-model.json").read_text(encoding="utf-8"))
    order = list(book.assembly.order)
    ledger = re_.Ledger({scan: result.pages[scan] for scan in order})
    proposed: list[Any] = []

    def apply(edits):
        proposed.extend(edits)
        ledger.apply("again", edits)
    apply(rj.paragraphs(book, model, ledger.texts, order, apply).edits)
    return proposed


def seal(spec: dict[int, dict[str, Any]], scan: int, old: str, new: str) -> None:
    spec[scan].setdefault("sealedEdits", []).append((old, new))


def paragraphs(spec: dict[int, dict[str, Any]], scan: int) -> list[str]:
    return [item[1] for item in spec[scan]["items"] if item[0] == "para"]


def prose(seed: int, size: int, final: bool) -> str:
    """SIZE made-up characters with a comma every seven; a full stop after
    the last when FINAL."""
    chars = fx.filler(seed, size)
    out = "".join(c + ("，" if i % 7 == 0 and i < size else "") for i, c in enumerate(chars, 1))
    return out + ("。" if final else "")


def end_page(spec: dict[int, dict[str, Any]], scan: int, full: bool, final: bool) -> None:
    """SCAN's last paragraph set so that its last column is full (FULL) or
    short, its text finished (FINAL) or running on."""
    items = spec[scan]["items"]
    k = max(i for i, item in enumerate(items) if item[0] == "para")
    size = 78 if full else 60
    items[k] = ("para", prose(scan * 13, size, final), items[k][2])


def open_page(spec: dict[int, dict[str, Any]], scan: int, indented: bool) -> None:
    """SCAN's first paragraph set flush (running on) or two cells down."""
    items = spec[scan]["items"]
    k = next(i for i, item in enumerate(items) if item[0] == "para")
    items[k] = ("para", items[k][1], not indented)


# --- paragraphs -------------------------------------------------------------------

def paragraph_spec() -> dict[int, dict[str, Any]]:
    spec = fx.make_spec()
    # P1: two paragraphs the page separates by a line break only.
    one, two = paragraphs(spec, 6)[1:3]
    seal(spec, 6, one + "\n\n" + two, one + "\n" + two)
    # P2: a line break inside a paragraph's first column (inside engine A's
    # block), and one at the paragraph's second column (flush after a full
    # first one).
    body = paragraphs(spec, 8)[1]
    seal(spec, 8, body, body[:20] + "\n" + body[20:])
    body = paragraphs(spec, 10)[1]
    first_column = fx.layout(spec[10])["columns"][2]["text"]
    assert body.startswith(first_column), (body, first_column)
    seal(spec, 10, body, first_column + "\n" + body[len(first_column):])
    # Its look-alike: a line break before a flush column after a short one.
    spec[12]["items"][2] = ("para", prose(1201, 20, False), False)
    spec[12]["items"].insert(3, ("para", prose(1202, 45, True), True))
    seal(spec, 12, prose(1201, 20, False) + "\n\n" + prose(1202, 45, True),
         prose(1201, 20, False) + "\n" + prose(1202, 45, True))
    # P7: two paragraphs run together; a numeral the page holds before a
    # paragraph engine A read without it.
    one, two = paragraphs(spec, 14)[1:3]
    seal(spec, 14, one + "\n\n" + two, one + two)
    one, two = paragraphs(spec, 16)[1:3]
    seal(spec, 16, one + "\n\n" + two, one + "二" + two)
    # P4: a line written twice that engine A read once.
    spec[19]["items"].insert(1, ("line", "三年五月七日"))
    seal(spec, 19, "三年五月七日", "三年五月七日\n\n三年五月七日")
    # P6: two items of one list a blank line apart.
    for n, words in ((1, "春風吹過"), (2, "小橋流水")):
        spec[20]["items"].insert(n, ("line", f"{n}. {words}"))
    return spec


def paragraph_checks(tmp: Path) -> None:
    spec = paragraph_spec()
    result = repair(tmp, spec, "paragraphs")
    pages = result.pages
    check(result.status == 0 and result.report["checks"]["logReplay"]["passed"] is True,
          f"paragraphs: the run exits 0 and its log replays to its output (exit {result.status})")
    one, two = paragraphs(spec, 6)[1:3]
    check(one + "\n\n" + two in pages[6] and "P1" in result.rules(6),
          f"P1: a line break before engine A's block at the paragraph indent is a blank line ({result.rules(6)})")
    body = paragraphs(spec, 8)[1]
    check(body in pages[8] and "P2" in result.rules(8),
          f"P2: a line break inside engine A's block is joined ({result.rules(8)})")
    body = paragraphs(spec, 10)[1]
    check(body in pages[10] and "P2" in result.rules(10),
          f"P2: a line break before a flush column after a full one is joined ({result.rules(10)})")
    check("P2" not in result.rules(12) and "P1" in result.asked(12),
          f"a line break before a flush column after a short one is a question ({result.rules(12)}, "
          f"{result.asked(12)})")
    one, two = paragraphs(spec, 14)[1:3]
    check(one + "\n\n" + two in pages[14] and "P7" in result.rules(14),
          f"P7: paragraphs the page ran together are split where engine A's block starts at the indent "
          f"({result.rules(14)})")
    check("P7" not in result.rules(16) and "P7" in result.asked(16),
          f"P7: a numeral before the block, which engine A read outside it, is a question ({result.asked(16)})")
    check(pages[19].count("三年五月七日") == 1 and "P4" in result.rules(19),
          f"P4: a line written twice that engine A read once keeps one copy ({result.rules(19)})")
    check("1. 春風吹過\n2. 小橋流水" in pages[20] and "P6" in result.rules(20),
          f"P6: two items of one list a blank line apart become a tight list ({result.rules(20)})")
    others = sorted({r["page"] for r in result.log} - {6, 8, 10, 12, 14, 16, 19, 20})
    check(not others, f"paragraphs: no other page is changed ({others})")
    rest = again(tmp, "paragraphs", result)
    check(not rest, f"paragraphs: the rules run again on their own output change nothing "
                    f"({[(e.page, e.rule) for e in rest]})")


# --- boundaries -------------------------------------------------------------------

def boundary_spec() -> dict[int, dict[str, Any]]:
    """Page ends and openings laid out for each rule: J1 (15 -> 16), J2
    (19 -> 20), P-1 (9 -> 10), P-2 (16 -> 17), H after a heading (7 -> 8),
    J4 (11 -> 12) and its look-alike after finished text (18 -> 19).  Scans
    7, 9, 11, 13, 15 and 18 open with a unit's heading (H), 5 and 13 with a
    divider; 5 -> 6 keeps the made-up book's finished text, short column and
    flush opening."""
    spec = fx.make_spec()
    # H: scan 7 ends with a heading, scan 8 opens two cells down.
    spec[7]["items"].append(("heading", "一 總說", 2))
    open_page(spec, 8, indented=True)
    # J4: a quotation set four cells down fills scan 11's last column and
    # goes on at its indent on scan 12; the same after a finished sentence
    # (18 -> 19).
    spec[11]["items"].append(("quote", prose(1101, 72, False), QUOTE))
    spec[12]["items"][0] = ("quote", prose(1201, 40, True), QUOTE)
    spec[18]["items"].append(("quote", prose(1801, 72, True), QUOTE))
    spec[19]["items"][0] = ("quote", prose(1901, 40, True), QUOTE)
    end_page(spec, 15, full=True, final=False)
    end_page(spec, 19, full=True, final=True)
    # Scan 9 (a unit's first page) with enough text for a frame (M-8 needs
    # three long columns).
    k = next(i for i, item in enumerate(spec[9]["items"]) if item[0] == "para")
    spec[9]["items"][k] = ("para", prose(901, 118, True), False)
    end_page(spec, 9, full=False, final=True)
    open_page(spec, 10, indented=True)
    end_page(spec, 16, full=False, final=False)
    open_page(spec, 17, indented=True)
    return spec


# A quotation's indent: every column set this many cells down.
QUOTE = 4


def list_spec() -> dict[int, dict[str, Any]]:
    """A list running on across scans 16 and 17."""
    spec = fx.make_spec()
    for n, words in ((1, "春風吹過"), (2, "小橋流水")):
        spec[16]["items"].append(("line", f"{n}. {words}"))
    spec[17]["items"].insert(0, ("line", "3. 人家門前"))
    return spec


def list_join_spec() -> dict[int, dict[str, Any]]:
    """A list item whose text fills scan 16's last column and runs on flush
    onto scan 17, where the list's next item follows it after a blank line
    (P6 across the join)."""
    spec = fx.make_spec()
    spec[16]["items"].append(("line", "1. 春風吹過"))
    spec[16]["items"].append(("line", "2. " + prose(1601, 79, False)))
    spec[17]["items"][0] = ("para", prose(1701, 20, True), True)
    spec[17]["items"].insert(1, ("line", "3. 人家門前"))
    return spec


def list_after_spec() -> dict[int, dict[str, Any]]:
    """A list set two cells down opening scan 17 after a short column (P-3)."""
    spec = fx.make_spec()
    end_page(spec, 16, full=False, final=False)
    spec[17]["items"].insert(0, ("line", "1. 春風吹過", 2))
    spec[17]["items"].insert(1, ("line", "2. 小橋流水", 2))
    return spec


def boundary_checks(tmp: Path) -> None:
    spec = boundary_spec()
    result = repair(tmp, spec, "boundaries")
    check(result.status == 0 and result.report["checks"]["boundaryContract"]["passed"] is True,
          f"boundaries.json passes finalize's contract (exit {result.status}, "
          f"{result.report['checks'].get('boundaryContract')})")
    markers = sorted(result.pages)
    check(sorted(result.labels) == markers, "boundaries.json has a label for every marker page")
    check(result.labels[1] == "start" and result.rule_of(1) == "S", "S: the first marker is `start`")
    check(result.rule_of(3) == "T" and result.labels[3] in ("paragraph", "list-new"),
          f"T: inside the contents ({result.labels[3]}, {result.rule_of(3)})")
    check(result.labels[7] == "structural" and result.rule_of(7) == "H" and result.labels[13] == "structural",
          f"H: onto a unit's heading, and onto a divider, is `structural` ({result.rule_of(7)}, {result.rule_of(13)})")
    check(result.labels[16] == "join" and result.rule_of(16) == "J1",
          f"J1: flush after a full column, unfinished text, is `join` ({result.labels[16]}, {result.rule_of(16)})")
    check(result.labels[20] == "join" and result.rule_of(20) == "J2",
          f"J2: flush after a full column that ends a sentence is `join` ({result.labels[20]}, {result.rule_of(20)})")
    check(result.labels[10] == "paragraph" and result.rule_of(10) == "P-1" and result.verified(10),
          f"P-1: the paragraph indent after finished text is `paragraph` ({result.rule_of(10)})")
    check(result.labels[17] == "paragraph" and result.rule_of(17) == "P-2" and result.verified(17),
          f"P-2: the indent after a short column is `paragraph` ({result.rule_of(17)})")
    check(result.labels[8] == "structural" and result.rule_of(8) == "H" and result.verified(8),
          f"H: after a page that ends with a heading, onto a column set down, is `structural` "
          f"({result.labels[8]}, {result.rule_of(8)})")
    check(result.labels[12] == "join" and result.rule_of(12) == "J4" and result.verified(12),
          f"J4: a quotation that goes on at its indent after a full column and unfinished text is `join` "
          f"({result.labels[12]}, {result.rule_of(12)})")
    check(result.labels[19] == "paragraph" and not result.verified(19) and "J" in result.asked(19),
          f"J4: the same after a finished sentence is a question, written `paragraph` "
          f"({result.labels[19]}, {result.rule_of(19)})")
    # The made-up book's other pages end finished with a short column and
    # open flush: the print and the text disagree.
    check(result.labels[6] == "paragraph" and not result.verified(6) and "J" in result.asked(6)
          and any(d["kind"] == "boundary-unverified" and d["page"] == 6 for d in result.doubts),
          f"signals that disagree are a question (Q-B), written `paragraph`, unverified "
          f"({result.labels[6]}, {result.rule_of(6)}, asked {result.asked(6)})")
    unverified = result.report["boundaries"]["unverified"]
    check(unverified == sum(1 for e in result.evidence.values() if not e.get("verified")) and unverified > 0,
          f"the report counts the unverified labels ({unverified})")
    import _ocr_markdown as om
    combined = (result.out / "combined-repaired.md").read_text(encoding="utf-8")
    final = om.apply_boundary_contract(combined, result.labels)
    check("<!-- page_" not in final and prose(15 * 13, 78, False) + paragraphs(spec, 16)[0] in final,
          "finalize applies the labels: the J1 join runs the sentence on across the page")

    result = repair(tmp, list_spec(), "list")
    check(result.labels[17] == "list-new" and result.rule_of(17) == "L" and result.status == 0,
          f"L: a list running on across the page is `list-new` ({result.labels.get(17)}, {result.rule_of(17)})")

    result = repair(tmp, list_join_spec(), "list-join")
    check(result.labels[17] == "join" and "3. 人家門前" in result.pages[17]
          and "。\n3. 人家門前" in result.pages[17] and "P6" in result.rules(17),
          f"P6 across a join: the list's next item follows the item the join finishes without a blank line "
          f"({result.labels[17]}, {result.rule_of(17)}, {result.rules(17)})")

    result = repair(tmp, list_after_spec(), "list-after")
    check(result.labels[17] == "structural" and result.rule_of(17) == "P-3" and result.verified(17),
          f"P-3: a list set down after a short column is `structural` ({result.labels[17]}, {result.rule_of(17)})")

    result = repair(tmp, fx.make_spec(), "subset", "--pages", "5-7,9-10")
    check(result.labels.get(5) == "start" and result.labels.get(9) == "paragraph" and not result.verified(9)
          and result.rule_of(9) == "gap",
          f"--pages: the first page is `start`, a page after a left-out one `paragraph`, unverified "
          f"({result.labels})")

    # A label the contract refuses (a join into a list item): exit 4.
    real = rj.joins

    def refused(*args, **kwargs):
        plan, labels, evidence = real(*args, **kwargs)
        labels[17] = "list-cont"
        return plan, labels, evidence
    rj.joins = refused
    try:
        result = repair(tmp, list_spec(), "refused")
    finally:
        rj.joins = real
    check(result.status == 4 and result.report["checks"]["boundaryContract"]["passed"] is False,
          f"a label finalize's contract refuses is exit 4 ({result.status})")


def gate_checks(tmp: Path) -> None:
    spec = fx.make_spec()
    for page in spec.values():
        page["items"] = [(i[0], i[1], True) if i[0] == "para" else i for i in page["items"]]
    one, two = paragraphs(spec, 6)[1:3]
    seal(spec, 6, one + "\n\n" + two, one + "\n" + two)
    result = repair(tmp, spec, "flat")
    check(not result.report["gates"]["M-8b"] and "P1" in result.asked(6) and not result.rules(6),
          f"with M-8b failed a line break is asked, not decided ({result.rules(6)}, {result.asked(6)})")
    decided = {int(p): e["rule"] for p, e in result.evidence.items() if e.get("verified")}
    check(set(decided.values()) <= {"S", "T", "H", "L"} and result.status == 0,
          f"with M-8b failed only the first marker, the contents, headings and lists are decided "
          f"({sorted(set(decided.values()))})")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        paragraph_checks(Path(tmp))
        boundary_checks(Path(tmp))
        gate_checks(Path(tmp))
    print(f"{'FAIL' if FAILURES else 'ok  '} check_repair_boundaries: {len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
