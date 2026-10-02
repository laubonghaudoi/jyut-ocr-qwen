#!/usr/bin/env python3
"""Offline check of what the skill's text tells the agent to do once phase 3
has sealed the book: run scripts/finish_book.py, deliver final.md and
doubts.md, and never review pages itself.

Measured (Qwen Code end to end, 30 pages, the old skill and the new): both
sealed all 30 pages in about 59 minutes; then the agent cut crops, read them
with zoom_image and read_file into its own conversation and adjudicated
glyphs itself, for one hour (new) or two (old), until Qwen Code stopped with
"Context is too large to send safely after automatic compression ... hard
limit: 177000 ... COMPRESSION_FAILED_OUTPUT_TRUNCATED" (exit 1), no book
assembled.  The transcripts show the wording that sent it there: the rule on
claiming a page-by-page visual check (read as a duty to do one), the
low-confidence check "by context and image", "your eyes are for the dispute
sites and research items", the research queue read from the run report, the
basic profile's page-by-page image check, the core flow's page-by-page pass,
"only the main agent assembles", and doubts that "need the image checked".

- SKILL.md has the finishing step (finish_book.py in the background, waited
  on with wait_for_run.py), the rule that forbids the agent's own review
  (pages, zoom_image, read_file on images, cutting crops, adjudicating),
  the measured crash that says why, that 'visually checked page by page'
  must not be claimed, and a short delivery naming final.md and doubts.md.
- The wording that drove the review is gone from SKILL.md and references/,
  and the references say their image checks are the pipeline's or the
  user's.
- Every switch of finish_book.py is named in SKILL.md, and SKILL.md names
  its exit codes, all of them and no other; wait_for_run.py knows the step.
- The rules on faithful transcription are still there.
- What the review found (each check failed before its fix): the wait rule
  still left "zoom into page images to study the book" for after a step;
  nothing kept a subagent from doing the review, and the other sections'
  image checks (subagent visual audit, heading sizes read off the PDF, the
  contents' 100% image check, subagent-orchestration.md's main agent that
  assembles and runs the visual closure) were not said to be the pipeline's
  or the user's; a short book could run finish_book.py in the foreground (a
  harness time limit kills it); exit 1 left the agent to mend the book
  itself; the edited final.md kept aside (and so no rerun just to check an
  edited final.md), the refused second run and the WARNING lines in
  finish-book.log were not in the text.

Usage:
    python3 tests/check_finish_rules.py
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    print(f"{'ok  ' if condition else 'FAIL'} {message}")
    if not condition:
        FAILURES.append(message)


def section(text: str, heading: str) -> str:
    """The body of the `## HEADING...` section of TEXT."""
    start = text.find(f"\n## {heading}")
    if start < 0:
        return ""
    end = text.find("\n## ", start + 4)
    return text[start:end if end >= 0 else len(text)]


# Wording the e2e transcripts show sending the agent to review pages itself
# (quoted in the agent's own reasoning, or the step it took right after).
OLD_WORDING = {
    "未逐頁視覺對照，就唔可以話": "the claim rule, read as a duty to check every page",
    "聲稱逐頁視覺完成時": "what a page-by-page visual claim needs",
    "要按語境同圖像檢查": "the low-confidence check by context and image",
    "你嘅眼留返畀": "the agent's eyes for dispute sites and research items",
    "跑完之後睇 run report 嘅 `researchQueue`": "reading the research queue from the run report",
    "唔會降低逐頁視覺校對標準": "the profile that never lowers the page-by-page visual standard",
    "逐頁圖文核對": "the basic profile's page-by-page image check",
    "完成逐頁視覺對照": "the core flow's page-by-page visual pass",
    "每次視覺確認一個無括號錯字後": "the agent confirming glyphs by sight",
    "只由主 agent 組裝最終 Markdown": "the main agent assembling the book",
    "主 agent 要 review 每段": "the main agent reviewing every segment",
    "是否逐頁用 individual original": "the delivery reporting a page-by-page visual check",
    "自己組裝全書時": "the agent assembling the book itself",
    "例如放大頁圖研究本書、寫筆記；要做就等呢步做完先做": "zooming into page images left for after a step",
    "幾十頁嘅短書可以前景跑": "the finishing step in the foreground, where a time limit kills it",
}
OLD_IN_REFERENCES = {
    "只由主 agent 或唯一 assembly owner 合併 segments": "the main agent merging the segments",
    "doubt 係交人核圖嘅問題，runner": "doubts as image checks for whoever reads them",
    "逐頁重看 assembled Markdown 同 PDF": "the page-by-page final pass as the agent's step",
    "所有可能改文嘅獨立 visual sweep": "the visual sweep before finalize",
    "Only the main agent assembles the final Markdown": "the main agent assembling and running the visual closure",
}


def skill_checks(skill: str) -> None:
    finish = section(skill, "做完之後")
    rule = finish[finish.find("**唔好自己覆核。**"):]
    wanted = {
        "a section for after phase 3": bool(finish),
        "finish_book.py in the background": "python3 scripts/finish_book.py BOOK > BOOK/finish.log 2>&1" in finish
        and "放背景" in finish,
        "waited on with wait_for_run.py": "python3 scripts/wait_for_run.py BOOK BOOK/finish.log" in finish
        and "600000" in finish,
        "final.md and doubts.md": "`final.md`" in finish and "`doubts.md`" in finish,
        "the forbidding rule": "**唔好自己覆核。**" in finish and "**唔准**" in rule,
        "no page views, zoom_image or read_file on images": all(w in rule for w in ("逐頁睇頁圖", "`zoom_image`",
                                                                                   "`read_file`")),
        "no cutting crops, no adjudicating": "自己切裁圖" in rule and "自己裁定" in rule,
        "no reading sealed pages or the run report to hunt errors": "sealed `.md`／`.json`" in rule
        and "run report" in rule,
        "before, during and after": "由開 phase 3 到交付之後" in rule,
        "doubts.md's image checks are the user's": "係畀用戶做嘅，唔係畀 agent 做" in rule,
        "the measured crash quoted": all(w in rule for w in ("hard limit: 177000", "COMPRESSION_FAILED_OUTPUT_TRUNCATED",
                                                             "59 分鐘", "1 個鐘", "2 個鐘", "冇 `final.md`")),
        "why: every image fills the context": "每張讀入對話嘅圖都塞入 Qwen Code 嘅 context" in rule,
        "a short delivery": "**交付要短。**" in finish and "唔好將 `final.md`、`doubts.md` 或者 log 成段讀入對話" in finish,
        "'visually checked page by page' must not be claimed":
            "**唔可以話「已逐頁視覺校對」「已逐頁同 PDF 對照」" in section(skill, "原文依據")
            and "冇逐頁視覺核對" in finish,
        "the delivery reply says so too": "冇逐頁視覺核對（唔可以話有）" in skill,
        "the research queue goes to doubts.md, searched by text only": "〈要查資料嘅專名〉" in skill
        and "淨係用文字搜尋" in skill and "唔好放大頁圖睇" in skill,
        "the core flow ends with finish_book.py": "`finish_book.py` 拼書、修書、定稿、寫 `doubts.md`，然後交付；唔自己覆核"
        in section(skill, "核心流程"),
        "the step 1 layout look is whole pages only": "唔放大、唔逐字讀" in skill,
        "the references' image checks are the pipeline's or the user's": "references 入面講「核圖」" in skill,
        "the tool listed": "- `scripts/finish_book.py`" in skill,
        "no subagent does it instead": "亦唔准叫 subagent 代你做以上任何一樣" in rule,
        "the other sections' image checks are the pipeline's or the user's":
            "由開 phase 3 起都係流程或者用戶做，唔係 agent，亦唔係 subagent" in rule
            and all(w in rule for w in ("〈安全並行〉", "〈Markdown 結構〉", "visual closure")),
        "always in the background": "**一律放背景**" in finish and "唔好前景跑" in finish,
        "exit 1: told to the user, not mended by hand": "照實話畀用戶知" in finish
        and "唔好自己拼書、改封存頁、切裁圖或者手寫 `final.md` 嚟補" in finish,
        "an edited final.md or doubts.md is kept aside and passed on": "`final.edited-<時間>.md`" in finish
        and "`doubts.edited-<時間>.md`" in finish and "照講畀用戶知" in finish
        and "唔好為咗重跑檢查再跑 `finish_book.py`" in finish,
        "one run per book; wait for the first": "第二個乜都唔寫就 exit 2" in finish,
        "the WARNING lines grepped in finish-book.log and passed on":
            "`grep -n WARNING BOOK/finish/finish-book.log`" in finish and "一齊話畀用戶知" in finish,
    }
    for name, ok in wanted.items():
        check(ok, f"SKILL.md: {name}")


def wording_checks(skill: str, references: dict[str, str]) -> None:
    for words, what in OLD_WORDING.items():
        where = [name for name, text in {"SKILL.md": skill, **references}.items() if words in text]
        check(not where, f"gone: {what} ({words!r}{' in ' + ', '.join(where) if where else ''})")
    for words, what in OLD_IN_REFERENCES.items():
        where = [name for name, text in references.items() if words in text]
        check(not where, f"gone from references/: {what} ({words!r}{' in ' + ', '.join(where) if where else ''})")
    for name in ("jyut-ocr-detailed-rules.md", "common-ocr-traps.md"):
        check("agent 喺對話入面唔讀頁圖" in references.get(name, ""),
              f"references/{name}: its image checks are the pipeline's or the user's")
    workflow = references.get("long-book-workflow.md", "")
    check("係畀用戶做嘅" in workflow and "`finish_book.py` 將佢哋按類同頁碼寫入 `doubts.md`" in workflow,
          "long-book-workflow.md: each doubt's image check is the user's, via doubts.md")
    check("## 一個 command 做完（finish_book.py）" in workflow, "long-book-workflow.md: the finish_book.py section")
    check("`final.edited-<時間>.md`" in workflow and "第二個喺寫任何嘢之前就 exit 2" in workflow
          and "即刻 exit 4" in workflow and "`.assembled.partial/`" in workflow,
          "long-book-workflow.md: edited copies kept, a refused run writes nothing, a stop at once, no input in "
          "assembled/")
    check("agent 同 subagent 都唔喺對話入面讀頁圖" in references.get("subagent-orchestration.md", ""),
          "references/subagent-orchestration.md: its visual audit and closure are the user's, not a subagent's")


def tool_checks(skill: str) -> None:
    import finish_book
    import wait_for_run

    source = (ROOT / "scripts" / "finish_book.py").read_text(encoding="utf-8")
    parser = finish_book.build_parser()
    switches = sorted({o for action in parser._actions for o in action.option_strings if o.startswith("--")}
                      - {"--help"})
    missing = [s for s in switches if f"`{s}`" not in skill]
    check(not missing and len(switches) >= 10, f"every finish_book.py switch named in SKILL.md ({missing or switches})")
    codes = {finish_book.EXIT_DONE, finish_book.EXIT_FAILED, finish_book.EXIT_USAGE, finish_book.EXIT_NOT_READY,
             finish_book.EXIT_STOPPED, finish_book.EXIT_MODEL}
    finish = section(skill, "做完之後")
    named = {int(code) for code in re.findall(r"\*\*exit (\d+)\*\*", finish)}
    check(named == codes, f"SKILL.md〈做完之後〉names every exit code of finish_book.py and no other "
                          f"({sorted(named)} vs {sorted(codes)})")
    docstring = finish_book.__doc__ or ""
    check(all(re.search(rf"^\s+{code}\s", docstring, re.M) for code in codes),
          "finish_book.py's docstring documents each exit code")
    check(wait_for_run.SCRIPTS.get("finish_book.py", ("",))[0] == "finish",
          "wait_for_run.py knows finish_book.py as a step it can wait on")
    check(not re.search(r"\b(?:zoom_image|read_file)\b", source) and "Image.open" not in source,
          "finish_book.py opens no image")


def faithful_checks(skill: str) -> None:
    kept = {
        "the PDF image is the final authority": "以 PDF 圖像為最終依據" in skill,
        "variant forms kept, no normalising, no archaising": "保留原有異體字、舊字形同舊式標點" in skill
        and "亦唔好過度古化" in skill,
        "an earlier transcription is only a draft": "既有轉錄" in skill and "唔係 ground truth" in skill,
        "no invented characters where the PDF is unclear": "唔好憑空補字" in skill,
        "the source's own notation kept": "唔可以當 residual 一律刪" in skill,
        "the page decides the variant form": "頁面印乜字形就寫乜字形" in skill,
    }
    for name, ok in kept.items():
        check(ok, f"still there: {name}")


def main() -> int:
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    references = {path.name: path.read_text(encoding="utf-8") for path in sorted((ROOT / "references").glob("*.md"))}
    skill_checks(skill)
    wording_checks(skill, references)
    tool_checks(skill)
    faithful_checks(skill)
    print(f"{'FAIL' if FAILURES else 'ok  '} the finishing step in the skill's text: {len(FAILURES)} problem(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
