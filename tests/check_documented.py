#!/usr/bin/env python3
"""Offline check that what phase 3 seals is written in the skill's text.

- Every --no-* switch of scripts/proofread_pages.py is named in SKILL.md or
  references/.
- Every decision and switch it records in decisionChanges, and every doubt kind
  it seals, is named in references/long-book-workflow.md, the reference that
  says what each one means and what a person should check.

Found in the round-3 review: a proposed decision (D26), a user's ruling
(headerCharacters), their two switches and three doubt kinds went in with no
word in either file, where every earlier decision had its switch documented.
The patterns are the literal forms the runner writes them in; a new way of
writing one needs a new pattern here.

- Every switch of scripts/repair_book.py (the book repair tool) is named in
  SKILL.md (a stage's switch) or in SKILL.md or references/ (any other), and
  every doubt kind it writes and every counter of scripts/_book_lint.py is
  named in long-book-workflow.md.

- A comment or docstring of scripts/ that says something was found (found
  in review, found when two branches were merged) says what it was found on:
  a made-up page (the check that builds it) or a measurement (unsourced_findings).

- Every doubt kind phase 3 seals has its words in finish_book.py's KINDS, the
  label doubts.md gives it (unlabelled_doubts), and none of the round-4 fixes,
  on by default, is called off by default in scripts/, SKILL.md or
  references/ (called_off).  Found in the round-4 integration review: the
  repair branch's KINDS had no words for the two doubt kinds the round-4
  branch added (neighbour-copy, arabic-figure-unwritten), so doubts.md would
  have headed them with the English kind; and three comments and one
  reference entry still called a fix off by default after the switch.

Usage:
    python3 tests/check_documented.py
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    runner = (ROOT / "scripts" / "proofread_pages.py").read_text(encoding="utf-8")
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    references = "".join(path.read_text(encoding="utf-8") for path in sorted((ROOT / "references").glob("*.md")))
    workflow = (ROOT / "references" / "long-book-workflow.md").read_text(encoding="utf-8")
    switches = sorted(set(re.findall(r'add_argument\(\s*"(--no-[a-z-]+)"', runner)))
    sealed_switches = sorted(set(re.findall(r'"switch":\s*"(--no-[a-z-]+)"', runner)))
    # A decision's name may hold a hyphen (switch R2-C).
    decisions = sorted(set(re.findall(r'"decision":\s*"([A-Za-z0-9][A-Za-z0-9-]*)"', runner)))
    kinds = sorted(set(re.findall(r'"kind":\s*"([a-z-]+)",\s*"detail"', runner)))
    assert len(switches) > 20 and len(sealed_switches) > 10 and len(decisions) > 10 and len(kinds) > 20, \
        "the runner's switches, decisions and doubt kinds were not found"
    problems = ([f"switch {name} is in neither SKILL.md nor references/" for name in switches
                 if name not in skill and name not in references]
                + [f"decisionChanges switch {name} is not in long-book-workflow.md" for name in sealed_switches
                   if name not in workflow]
                + [f"decision {name} is not in long-book-workflow.md" for name in decisions
                   if not re.search(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![0-9])", workflow)]
                + [f"doubt kind `{name}` is not in long-book-workflow.md" for name in kinds
                   if f"`{name}`" not in workflow])
    for problem in problems:
        print("FAIL", problem)
    print(f"{'FAIL' if problems else 'ok  '} {len(switches)} switches, {len(sealed_switches)} decisionChanges "
          f"switches, {len(decisions)} decisions, {len(kinds)} doubt kinds: {len(problems)} not documented")
    repair = repair_problems(skill, references, workflow)
    for problem in repair:
        print("FAIL", problem)
    print(f"{'FAIL' if repair else 'ok  '} the book repair tool's switches, doubt kinds and counters are "
          f"documented: {len(repair)} not")
    problems += repair
    stale = still_proposed(runner, skill + references)
    for problem in stale:
        print("FAIL", problem)
    print(f"{'FAIL' if stale else 'ok  '} the decisions the user ruled on are not called proposed or pending: "
          f"{len(stale)} found")
    unsourced = unsourced_findings({path.relative_to(ROOT): path.read_text(encoding="utf-8")
                                    for path in sorted((ROOT / "scripts").glob("*.py"))})
    for problem in unsourced:
        print("FAIL", problem)
    print(f"{'FAIL' if unsourced else 'ok  '} what the scripts' comments say was found says what it was found on: "
          f"{len(unsourced)} not")
    unlabelled = unlabelled_doubts(kinds)
    for problem in unlabelled:
        print("FAIL", problem)
    print(f"{'FAIL' if unlabelled else 'ok  '} every doubt kind phase 3 seals has its label in doubts.md: "
          f"{len(unlabelled)} not")
    called = called_off([ROOT / "SKILL.md", *sorted((ROOT / "references").glob("*.md")),
                         *sorted((ROOT / "scripts").glob("*.py"))])
    for problem in called:
        print("FAIL", problem)
    print(f"{'FAIL' if called else 'ok  '} the round-4 fixes, on by default, are not called off by default: "
          f"{len(called)} found")
    return 1 if problems or stale or unsourced or unlabelled or called else 0


def tuple_strings(source: str, name: str) -> list[str]:
    """The quoted strings of the tuple assigned to NAME in SOURCE."""
    match = re.search(rf"^{name} = \((.*?)^\)", source, re.M | re.S)
    return re.findall(r'"([A-Za-z0-9-]+)"', match.group(1)) if match else []


def repair_problems(skill: str, references: str, workflow: str) -> list[str]:
    """The book repair tool (scripts/repair_book.py): each stage switch is
    named in SKILL.md and each other switch in SKILL.md or references/; each
    doubt kind it writes (_repair_edits.DOUBT_KINDS) and each defect counter
    (_book_lint.COUNTERS) is named in long-book-workflow.md."""
    scripts = ROOT / "scripts"
    repair = (scripts / "repair_book.py").read_text(encoding="utf-8")
    stage_switches = sorted(set(re.findall(r'Stage\("[a-z-]+",\s*"(--[a-z-]+)"', repair)))
    other = sorted(set(re.findall(r'add_argument\(\s*"(--[a-z-]+)"', repair)) - set(stage_switches))
    kinds = tuple_strings((scripts / "_repair_edits.py").read_text(encoding="utf-8"), "DOUBT_KINDS")
    counters = tuple_strings((scripts / "_book_lint.py").read_text(encoding="utf-8"), "COUNTERS")
    assert len(stage_switches) >= 8 and len(other) >= 5 and len(kinds) >= 9 and len(counters) >= 20, \
        "the repair tool's switches, doubt kinds and counters were not found"
    return ([f"repair_book.py switch {name} is not in SKILL.md" for name in stage_switches if name not in skill]
            + [f"repair_book.py switch {name} is in neither SKILL.md nor references/" for name in other
               if name not in skill and name not in references]
            + [f"repair doubt kind `{name}` is not in long-book-workflow.md" for name in kinds
               if f"`{name}`" not in workflow]
            + [f"lint counter `{name}` is not in long-book-workflow.md" for name in counters
               if f"`{name}`" not in workflow])


# The proposed decisions the user ruled on, all on (the round-2 decision
# register, 2026-09-27: D15, D16 - after its fix, the answer accepted where the
# reading stands nearby - and D20-D25).  D26 is still a proposed decision.
RULED = ("D15", "D16", "D20", "D21", "D22", "D23", "D24", "D25")


def still_proposed(runner: str, text: str) -> list[str]:
    """Where the runner's help and comments, SKILL.md or references/ still call
    a decision in RULED proposed or pending the user's ruling.  Found merging
    round 3: both branches carried the round-2 labels, and the skill's text
    called D16 ruled on in one sentence and its switch's help pending."""
    flat = re.sub(r"\s*\n\s*#?\s*", " ", runner)
    out = []
    for name in RULED:
        number = rf"{name}(?![0-9])"
        if re.search(rf"[Pp]roposed decision {number}|{number}\W{{1,3}}pending the user|"
                     rf"{number} \(--no-[a-z-]+; not yet ruled", flat):
            out.append(f"scripts/proofread_pages.py calls {name} proposed or pending")
        if re.search(rf"建議決定 {number}|{number}，用戶未裁", text):
            out.append(f"SKILL.md or references/ call {name} a proposed decision (建議決定 / 用戶未裁)")
    return out


# What a finding may be sourced by: the check that builds the made-up page it
# was shown on, or words that say it was made up or measured.
FINDING = re.compile(r"\bfound (?:in (?:the )?[\w -]{0,30}review|when [^.:]{0,40}merg\w*|merging|integrating)\b",
                     re.I)
SOURCED = re.compile(r"\bcheck_[a-z_]+|made-up|made up|measured|corpus|benchmark", re.I)


def unsourced_findings(sources: dict[Path, str]) -> list[str]:
    """Each sentence of the scripts' comments and docstrings that says
    something was found and not what it was found on (SOURCED).  The rule is
    the user's: say in comments what was measured.  Found in the round-3
    integration review: a comment presented a made-up test page as something
    found (a prose line written twice when the branches were merged), naming
    neither the page nor its check, so a reader takes it for a corpus
    measurement.  A sentence runs from the words to the first full stop
    followed by a space or the first closing parenthesis, whichever comes
    first (a finding written inside parentheses ends there)."""
    out = []
    for path, text in sources.items():
        flat = re.sub(r"\s*\n\s*#?\s*", " ", text)
        for match in FINDING.finditer(flat):
            rest = flat[match.start():]
            ends = [m.start() for m in (re.search(r"\.(?:\s|$)", rest), re.search(r"\)", rest)) if m]
            sentence = rest[:min(ends)] if ends else rest[:400]
            if not SOURCED.search(sentence):
                out.append(f"{path}: \"{sentence[:90]}…\" says what was found, not on what "
                           "(a made-up page and its check, or a measurement)")
    return out


def unlabelled_doubts(kinds: list[str]) -> list[str]:
    """The doubt kinds of KINDS (the ones phase 3 seals) that finish_book.py's
    KINDS gives no section and words: doubts.md would head them with the
    English kind, in the text section's end."""
    finish = (ROOT / "scripts" / "finish_book.py").read_text(encoding="utf-8")
    match = re.search(r"^KINDS: .*? = \{(.*?)^\}", finish, re.M | re.S)
    labelled = set(re.findall(r'^\s*"([A-Za-z0-9-]+)": \("[a-z]+", "[^"]+"\)', match.group(1), re.M)) if match else set()
    assert len(labelled) > 40, "finish_book.py's KINDS was not found"
    return [f"doubt kind `{name}` has no label in finish_book.py's KINDS" for name in kinds if name not in labelled]


# The round-4 fixes, on by default since the user's decision of 2026-09-30
# (proofread_pages.ROUND4_DEFAULTS), and the words that call a switch off.
ROUND4 = ("--keep-arabic-numerals", "--loop-detector", "--neighbour-guard", "--learned-heads")
CALLED_OFF = r"off by default|off until measured|default off|預設關|等實測先定|等 GPU 實測先定"


def called_off(paths: list[Path]) -> list[str]:
    """Where a round-4 fix is called off by default: the switch, then within
    the same sentence (no full stop and space, or 。, between) and 45
    characters the words."""
    out = []
    for path in paths:
        flat = re.sub(r"\s*\n\s*#?\s*", " ", path.read_text(encoding="utf-8"))
        for switch in ROUND4:
            for match in re.finditer(rf"{re.escape(switch)}(?![a-z-])(?:(?!\. |。).){{0,45}}?(?:{CALLED_OFF})", flat):
                out.append(f"{path.relative_to(ROOT)}: \"{match.group(0)[:90]}\" calls {switch} off by default")
    return out


if __name__ == "__main__":
    sys.exit(main())
