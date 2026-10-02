#!/usr/bin/env python3
"""Offline check of the automatic defect counters (scripts/_book_lint.py).

No model, no GPU, no corpus.  The clean made-up book (tests/repair_fixture.py)
counts nothing but its heading levels and its unlabelled page boundaries.
Then one book holds a positive case for each counter, next to a look-alike
that must not count:

- FURN-HEAD: a running-head line on scan 6 and a head glued into prose on
  scan 8 count; the contents title on scan 2, which holds the stem but
  engine A reads in its body, does not.
- FURN-SUFFIX / HEAD-FURNITURE: a `# 甲編` heading on scan 10 counts; the
  divider's own `## 甲編` on scan 5 does not.
- FURN-FOLIO: scan 11's folio 七 left as the last line counts; a 五 at the
  end of scan 14 (whose folio is 二) does not.
- FURN-ANSWER: an adjudicator's answer at the band spot of scan 7 (engine A
  read nothing, engine B the folio) counts.
- MARK-STANDIN: engine B's comma glyph 丶 sealed on scan 9 where engine A
  read a comma counts; the same glyph on scan 15, where engine A read it too,
  does not.
- MARK-REVERSED / MARK-FIGURE-LOST: 丁）（ on scan 17 where engine A read
  （1） counts twice; a ）（ on scan 19 that engine A read too, and a （2） on
  scan 20 that the sealed text keeps, do not.  The numbers engine A read at
  the start of scan 15's title and scan 3's contents line count as lost
  figures too.
- MARK-UNBALANCED: scan 17's reversed pair counts; a bracket opened at the
  end of scan 11 and closed at the start of scan 12 does not.
- MARK-SHAPE: ︵完︶ on scan 18 counts.
- HEAD-NUMBER-LOST: scan 15's unit title without the 2 engine A read counts;
  scan 13's, which keeps its 1, does not.
- TOC-NUMBER-LOST / TOC-UNMATCHED: a contents entry without its number, and
  one with no unit in the body, count - also in a text that has lost a line
  above them since the model read the contents.
- HEAD-FRAGMENT: a heading at the top of scan 20 that ends a sentence scan
  19 left unfinished, in a flush column, counts; scan 15's unit title after
  a finished page does not.
- PARA-DISAGREE: two paragraphs sealed as one on scan 16 count, and so do
  the pages where a line phase 3 left (a head, a folio, an answer) is a
  paragraph the print does not indent.
- ANSWER-PROSE: a ten-character answer to a one-character question counts.
- TEXT-LOST: a character both engines read that scan 9 lost counts.
- JOIN-UNRESOLVED: every marker without a boundary label; none with one.
- On a subset of the pages the neighbours are the book's pages, not the
  subset's.
- AUDIT-ANNOTATED: a heading with no blank line under it counts.
- A counter whose gate failed is not measured (no count), and the command
  line fails with --fail-on a counter that counts, and with exit 2 on a
  --fail-on name that is no counter (a misspelt one would never fail).

Usage:
    python3 tests/check_book_lint.py
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import offline  # noqa: E402,F401
import repair_fixture as fx  # noqa: E402

sys.path.insert(0, str(HERE.parent / "scripts"))
import _book_lint as bl  # noqa: E402
import _repair_inputs as ri  # noqa: E402
import _repair_model as rm  # noqa: E402


FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    print(f"{'ok  ' if condition else 'FAIL'} {message}")
    if not condition:
        FAILURES.append(message)


def lint(root: Path, spec, boundaries=None) -> dict:
    fx.write_book(root, spec)
    book = ri.load_book(ri.InputPaths.resolve(root, {}))
    model = rm.learn(book)
    return bl.lint_book(book, model, boundaries=boundaries)


def pages_of(result: dict, name: str) -> list[int]:
    return sorted(h["page"] for h in result["hits"][name])


def first_chars(spec, scan: int, size: int) -> str:
    """The first SIZE characters of the page's first paragraph."""
    text = next(item[1] for item in spec[scan]["items"] if item[0] == "para")
    return text[:size]


def defects(spec) -> None:
    spec[6]["extraSealed"] = [fx.HEAD + "甲編"]
    first = first_chars(spec, 8, 2)
    spec[8]["sealedEdits"] = [(first, first + fx.HEAD)]
    spec[10]["extraSealed"] = ["# 甲編"]
    spec[11]["extraSealed"] = ["見下頁（甲", "七"]
    first = first_chars(spec, 12, 2)
    spec[12]["sealedEdits"] = [(first, "乙）" + first)]
    spec[14]["extraSealed"] = ["五"]
    body = pp_cjk(fx.printed_text(spec[7]))
    spec[7]["extraSealed"] = ["一"]
    spec[7]["adjudications"] = [{"context_before": body[-8:], "context_after": fx.HEAD + "甲編",
                                 "draft_reading": "", "writer_reading": "三", "resolved": "一",
                                 "resolved_from": "adjudicator"}]
    body12 = pp_cjk(fx.printed_text(spec[12]))
    spec[12]["adjudications"] = [{"context_before": "", "context_after": "", "draft_reading": "甲",
                                  "writer_reading": "乙", "resolved": body12[20:30], "resolved_from": "adjudicator"}]
    spec[9]["sealedEdits"] = [("，", "丶"), (first_chars(spec, 9, 12)[9:12], first_chars(spec, 9, 12)[9:11])]
    spec[15]["sealedEdits"] = [("，", "丶"), ("### 2 田園小記", "### 田園小記")]
    spec[15]["aEdits"] = [("，", "丶")]
    first = first_chars(spec, 17, 2)
    spec[17]["sealedEdits"] = [(first, first + "丁）（")]
    spec[17]["aEdits"] = [(first, first + "（1）")]
    first = first_chars(spec, 19, 2)
    spec[19]["sealedEdits"] = [(first, first + "）（")]
    spec[19]["aEdits"] = [(first, first + "）（")]
    last = fx.printed_text(spec[19]).rstrip()[-3:]
    spec[19]["sealedEdits"].append((last, last[:-1]))
    first = first_chars(spec, 20, 2)
    spec[20]["items"] = [("para", first + "（2）" + item[1][2:], True) if k == 0 else item
                         for k, item in enumerate(spec[20]["items"])]
    spec[20]["sealedEdits"] = [(first + "（2）", "# " + first + "（2）")]
    spec[18]["sealedEdits"] = [("。", "︵完︶。")]
    paragraphs = [item[1] for item in spec[16]["items"] if item[0] == "para"]
    spec[16]["sealedEdits"] = [(paragraphs[1] + "\n\n" + paragraphs[2], paragraphs[1] + paragraphs[2])]
    spec[3]["sealedEdits"] = [("1 晨鐘暮鼓", "晨鐘暮鼓")]
    spec[3]["extraSealed"] = ["4 竹林清話"]
    spec[4]["sealedEdits"] = [(first_chars(spec, 4, 2), "#### 附言\n" + first_chars(spec, 4, 2))]


def pp_cjk(text: str) -> str:
    return fx.pp.CJK(text)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        clean = lint(tmp / "clean", fx.make_spec())
        counts = bl.summary(clean)
        counting = {name: n for name, n in counts.items() if n and name not in ("HEAD-LEVELS", "JOIN-UNRESOLVED")}
        check(not counting and counts["JOIN-UNRESOLVED"] == 20,
              f"the clean made-up book counts only its heading levels and its 20 unlabelled boundaries ({counting})")

        spec = fx.make_spec()
        defects(spec)
        result = lint(tmp / "defects", spec)
        expect = {
            "FURN-HEAD": [6, 8], "FURN-SUFFIX": [10], "HEAD-FURNITURE": [10], "FURN-FOLIO": [11],
            "FURN-ANSWER": [7], "MARK-STANDIN": [9], "MARK-REVERSED": [17], "MARK-FIGURE-LOST": [3, 15, 17],
            "MARK-UNBALANCED": [17, 19], "MARK-SHAPE": [18, 18], "HEAD-NUMBER-LOST": [15],
            "TOC-NUMBER-LOST": [3], "TOC-UNMATCHED": [3], "HEAD-FRAGMENT": [20],
            "PARA-DISAGREE": [6, 7, 11, 14, 16],
            "ANSWER-PROSE": [12], "TEXT-LOST": [9],
        }
        for name, pages in expect.items():
            got = pages_of(result, name)
            check(got == pages, f"{name}: counts on scans {pages} and nowhere else (got {got})")
        audit = result["counters"]["AUDIT-ANNOTATED"]
        check(audit["count"] >= 1, f"AUDIT-ANNOTATED counts the heading with no blank line under it ({audit})")

        # The text counted may have lost lines since the model read the
        # contents (a repair deleted scan 3's group line above its entries):
        # each contents row is found again by its characters.
        book = ri.load_book(ri.InputPaths.resolve(tmp / "defects", {}))
        texts = {scan: book.pages[scan].sealed_text for scan in book.assembly.order}
        texts[3] = texts[3].split("\n\n", 1)[1]
        moved = bl.lint_book(book, rm.learn(book), texts)
        lost = [h["text"] for h in moved["hits"]["TOC-NUMBER-LOST"]]
        unmatched = [h["text"] for h in moved["hits"]["TOC-UNMATCHED"]]
        check(lost == ["晨鐘暮鼓"] and unmatched == ["4 竹林清話"],
              f"TOC-NUMBER-LOST / TOC-UNMATCHED find their contents lines by their text once lines above them "
              f"are gone ({lost}, {unmatched})")

        subset = ri.load_book(ri.InputPaths.resolve(tmp / "defects", {}), {12, 20})
        sub = bl.lint_book(subset, rm.learn(subset))
        check(pages_of(sub, "MARK-UNBALANCED") == [] and pages_of(sub, "HEAD-FRAGMENT") == [20],
              "on a subset of pages the page before and after are the book's: scan 12's bracket closes one "
              "opened on scan 11, and scan 20's heading ends scan 19's sentence")

        labels = {scan: ("start" if scan == 1 else "paragraph") for scan in range(1, 21)}
        labelled = lint(tmp / "labelled", fx.make_spec(), boundaries=labels)
        check(labelled["counters"]["JOIN-UNRESOLVED"]["count"] == 0, "JOIN-UNRESOLVED is 0 when every marker is labelled")

        flat = fx.make_spec()
        for page in flat.values():
            page["items"] = [(i[0], i[1], True) if i[0] == "para" else i for i in page["items"]]
        flat_result = lint(tmp / "flat", flat)
        entry = flat_result["counters"]["PARA-DISAGREE"]
        check(entry["count"] is None and "M-8b" in entry["notMeasured"],
              f"a counter whose gate failed is not measured ({entry})")

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as errors:
            failing = bl.main([str(tmp / "defects"), "--fail-on", "FURN-HEAD", "--json", str(tmp / "lint.json")])
            passing = bl.main([str(tmp / "defects"), "--fail-on", "AUDIT-FINAL"])
            misspelt = bl.main([str(tmp / "defects"), "--fail-on", "FURN_HEAD"])
        written = json.loads((tmp / "lint.json").read_text(encoding="utf-8"))
        check(failing == 1 and passing == 0 and written["counters"]["FURN-HEAD"]["count"] == 2
              and "AUDIT-FINAL: not measured" in errors.getvalue(),
              "the command line fails with --fail-on a counter that counts, and writes every hit; a counter "
              "not measured does not fail it and is named")
        check(misspelt == 2, f"--fail-on a name that is no counter fails the command line, not passes it "
                             f"(got {misspelt})")
    print(f"{'FAIL' if FAILURES else 'ok  '} check_book_lint: {len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
