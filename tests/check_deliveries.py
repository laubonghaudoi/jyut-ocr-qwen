#!/usr/bin/env python3
"""Offline check of the three deliveries on made-up book folders.

No GPU, no model, no server.  Each case writes a made-up book in a temporary
folder - renders, a page manifest listed out of order, engine B's pages with
grounding boxes, a running head carrying the volume and a folio beside it on
either side, sealed proofread pages - and runs the real scripts on it.

- scripts/build_draft.py: engine B's text in scan order, the pages the
  manifest leaves out left out, grounding boxes gone, the running head (read
  right or misread by a character) and its folio taken off on every page
  whether the folio stands outside the head or on the text side of it, a
  folio line at the page's foot taken off, and what only looks like furniture
  kept (a stretch opening a few pages, text starting with a numeral, a line
  of figures that does not follow the page sequence); a visible gap line for
  a page with no OCR file and another for a page read as nothing; the
  header; one line printed, naming the draft's absolute path; fast on a
  488-page book; never a traceback (no manifest, no OCR folder, a broken
  manifest, a page of bad bytes, no book folder at all); engine B's loops (a
  page of thousands of one character, a unit with its last copy cut short,
  text after a loop) cut to the stretch once and a gap line, in the draft and
  the progress file, while a cell printed ten times and a table of empty rows
  are copied, and a book of 488 pages with 16 loops still takes seconds.
- scripts/build_progress.py: sealed pages as proofread and nothing else as
  proofread (a Markdown written after its seal, a seal cut short, a Markdown
  with no seal, a seal of another schema fall back to the draft), a page the
  stitch emptied stays empty, page markers gone, the count in its header, the
  proofread folder untouched.
- Both write through a temporary file and a rename (a new inode each time,
  the old file whole until the rename, no temporary file left, the old file
  kept when the write fails).
- scripts/wait_for_run.py --progress BOOK: a stand-in phase 3 run seals
  pages; the wait rebuilds proofreading.md while it runs and when it returns,
  and its one line ends with the file and the pages proofread; no file without
  the switch or for a step that is not phase 3; a progress file that cannot be
  built changes nothing but the line.
- SKILL.md says the flow: the draft at once and on without waiting, the
  progress file through the wait with its line passed on only when asked or at
  most once an hour, final.md and doubts.md last from finish_book.py as
  〈做完之後〉 runs it (not from repair_book.py, which only repairs), the book
  folder named in Jyutping or English, never Mandarin pinyin, and one name for
  it - BOOK, as 〈做完之後〉 calls it; the draft's loop cut.

Usage:
    python3 tests/check_deliveries.py
"""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import tempfile
import textwrap
import threading
import time

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests"))
import offline  # noqa: E402,F401
import build_draft  # noqa: E402
import build_progress  # noqa: E402
import proofread_pages as pp  # noqa: E402

PROBLEMS: list[str] = []

# The made-up book's furniture: a head naming its volume, folios from 96 up
# (scan page + 95), written in figures, 〇 misread as 口 now and then.
HEAD = "海港商務年報第{volume}冊"
FOLIO_OFFSET = 95
DIGITS = "〇一二三四五六七八九"
# Characters for the made-up body text: no numeral among them, none of the head's.
BODY_CHARS = "天地玄黃宇宙洪荒日月盈昃辰宿列張寒來暑往秋收冬藏閏餘成歲律呂調陽雲騰致雨露結爲霜金生麗水玉出崑岡劍號巨闕珠稱夜光"
NUMERALS = set(DIGITS) | set("十百千零")


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        PROBLEMS.append(f"{name}: {detail}")
    print(f"{'ok  ' if ok else 'FAIL'} {name}" + (f" - {detail}" if detail and not ok else ""))


def figures(number: int, misread: bool = False) -> str:
    text = "".join(DIGITS[int(d)] for d in str(number))
    return text.replace("〇", "口") if misread else text


def body(page: int, size: int = 60) -> str:
    rng = random.Random(page)
    return f"頁{BODY_CHARS[page % len(BODY_CHARS)]}{BODY_CHARS[page // len(BODY_CHARS) % len(BODY_CHARS)]}記" + \
        "".join(rng.choice(BODY_CHARS) for _ in range(size))


def tag(page: int) -> str:
    """The stretch that opens every page's body, unique to the page."""
    return body(page)[:4]


def page_text(page: int, pages: int) -> str:
    """Engine B's text of a page: one line, the head and folio glued to it,
    in one of four places, and a grounding box above."""
    volume = "一" if page <= pages // 2 else "二"
    head = HEAD.format(volume=volume)
    if page == 15:
        head = head.replace("商", "啇")                          # misread by one character
    folio = figures(page + FOLIO_OFFSET, misread=page % 7 == 0)
    text = body(page)
    kind = page % 4
    if kind == 0:
        line = folio + head + text                 # folio outside the head, at the start
    elif kind == 1:
        line = head + folio + text                 # folio on the text side, at the start
    elif kind == 2:
        line = text + head + folio                 # folio outside, at the end
    else:
        line = text + folio + head                 # folio on the text side, at the end
    return "(12,34),(560,78)\n" + line + "\n"


class Book:
    """A made-up book folder."""

    def __init__(self, root: Path, pages: int = 40, manifest: bool = True):
        self.root, self.pages = root, pages
        (root / "renders").mkdir(parents=True)
        (root / "ocr-hunyuan").mkdir()
        (root / "proofread").mkdir()
        records = []
        for page in range(1, pages + 1):
            (root / "renders" / f"page-{page:04d}.png").write_bytes(b"")
            records.append({"scan_page": page, "render_file": f"renders/page-{page:04d}.png",
                            "render_sha256": "0" * 64})
            (root / "ocr-hunyuan" / f"page-{page:04d}.txt").write_text(page_text(page, pages), encoding="utf-8")
        self.left_out = {7: {"marker_expected": False}, 8: {"content": "blank"},
                         9: {"relation": "exact_duplicate", "marker_expected": False}}
        for page, extra in self.left_out.items():
            records[page - 1].update(extra)
        # Labelled a duplicate, its marker expected: the finished book keeps
        # it (the label can stand on both scans of a pair), so the draft does.
        self.kept_duplicate = 18
        if pages >= self.kept_duplicate:
            records[self.kept_duplicate - 1]["relation"] = "exact_duplicate"
        random.Random(1).shuffle(records)
        if manifest:
            (root / "page-manifest.json").write_text(json.dumps(
                {"source_sha256": "0" * 64, "expected_scan_pages": pages, "pages": records}), encoding="utf-8")

    def ocr(self, page: int) -> Path:
        return self.root / "ocr-hunyuan" / f"page-{page:04d}.txt"


def run(script: str, *argv: str, cwd: Path | None = None) -> tuple[int, str, str, float]:
    began = time.monotonic()
    done = subprocess.run([sys.executable, str(SCRIPTS / script), *argv], cwd=cwd or ROOT, capture_output=True,
                          text=True, timeout=120)
    return done.returncode, done.stdout, done.stderr, time.monotonic() - began


# --- the draft -------------------------------------------------------------------

def check_draft() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        book = Book(Path(tmp) / "haigong-soengmou")
        root = book.root
        # Pages with furniture that is not: three pages open with the same
        # stretch (too few to be a head), two pages' text starts with numerals
        # (after the head and its folio, and at the page's edge), one ends with
        # a line of figures off the page sequence, one carries its head and its
        # folio on lines of their own, one page has no OCR text and one bad
        # bytes.
        for page in (21, 22, 23):
            book.ocr(page).write_text(page_text(page, book.pages).replace(tag(page), "諸君今日" + tag(page), 1),
                                      encoding="utf-8")
        for page in (25, 26):
            book.ocr(page).write_text(page_text(page, book.pages).replace(tag(page), "五月初" + tag(page)),
                                      encoding="utf-8")
        book.ocr(29).write_text(page_text(29, book.pages) + "三五五\n", encoding="utf-8")
        book.ocr(30).write_text(f"{HEAD.format(volume='二')}\n{body(30)}\n{body(30 + 100)}\n{figures(125)}\n",
                                encoding="utf-8")
        book.ocr(12).unlink()
        book.ocr(14).write_text("(10,20),(30,40)\n\n", encoding="utf-8")
        book.ocr(13).write_bytes(page_text(13, book.pages).encode("utf-8") + b"\xff\xfe")
        code, out, err, _ = run("build_draft.py", str(root))
        draft = (root / "draft.md").read_text(encoding="utf-8") if (root / "draft.md").is_file() else ""
        check("draft: exit 0, one line, no stderr", code == 0 and len(out.splitlines()) == 1 and not err
              and out.startswith(f"[draft] wrote {root / 'draft.md'}: "), f"{code} {out!r} {err[-300:]!r}")
        check("draft: the line counts the pages", "37 pages, 3 left out by the manifest, 1 with no OCR text [12], "
              "1 read as nothing [14]" in out
              and "1 running head(s) learned ('海港商務年報第#冊')" in out, out)
        lines = draft.splitlines()
        check("draft: a header saying unproofread, and when", len(lines) > 3 and "未校對" in lines[0]
              and re.search(r"建立時間：\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC[+-]\d{2}:\d{2}；", lines[2]) is not None,
              "\n".join(lines[:3]))
        kept = [page for page in range(1, book.pages + 1) if page not in book.left_out and page not in (12, 14)]
        where = [draft.find(tag(page)) for page in kept]
        check("draft: every page's text, in scan order", all(at > 0 for at in where) and where == sorted(where),
              str(list(zip(kept, where))))
        check("draft: the pages the manifest leaves out are left out",
              all(tag(page) not in draft for page in book.left_out))
        check("draft: a scan labelled a duplicate whose marker is expected is kept", tag(book.kept_duplicate) in draft)
        check("draft: a gap line naming the page with no OCR text, another for a page read as nothing",
              "〔掃描第 12 頁：冇 OCR 文字〕" in lines and "〔掃描第 14 頁：OCR 冇讀到字〕" in lines)
        check("draft: no grounding box, no page marker", "(12,34)" not in draft and "<!--" not in draft)
        check("draft: the head gone, read right or misread", "年報第" not in draft and "啇務" not in draft,
              [line[:30] for line in lines if "年報" in line][:3])
        text = draft.split("\n", 3)[3]
        numerals = re.findall(r"[〇一二三四五六七八九十百口]+", text)
        check("draft: every folio gone (outside the head, on the text side, misread, a line at the foot)",
              sorted(numerals) == sorted(["三五五", "五", "五"]), str(numerals))
        check("draft: text that only looks like furniture kept",
              draft.count("諸君今日") == 3 and all("五月初" + tag(page) in draft for page in (25, 26))
              and "三五五" in lines, "")
        check("draft: the bad bytes of one page read, not a failure", tag(13) in draft)

        code, out, err, _ = run("build_draft.py", "haigong-soengmou", cwd=Path(tmp))
        check("draft: a relative book folder - the line names the draft's absolute path",
              out.startswith(f"[draft] wrote {root / 'draft.md'}: "), out)

        # Never a failure: no manifest, no OCR folder, a broken manifest.
        (root / "page-manifest.json").write_text("{not json", encoding="utf-8")
        code, out, err, _ = run("build_draft.py", str(root))
        check("draft: a broken manifest - the pages found on disk, said on the line",
              code == 0 and not err and "no page manifest" in out and "40 pages" in out, out + err[-300:])
        (root / "page-manifest.json").write_text(json.dumps({"pages": [{"scan_page": "1"}]}), encoding="utf-8")
        code, out, err, _ = run("build_draft.py", str(root))
        check("draft: a manifest listing no scan page - the pages found on disk",
              code == 0 and "lists no scan page" in out and "40 pages" in out, out + err[-300:])
        (root / "page-manifest.json").unlink()
        code, out, err, _ = run("build_draft.py", str(root), "--ocr-dir", "no-such-folder")
        written = (root / "draft.md").read_text(encoding="utf-8")
        check("draft: no manifest and no OCR folder - every page a gap line, exit 0",
              code == 0 and not err and written.count("冇 OCR 文字〕") == 40, out + err[-300:])
        code, out, err, _ = run("build_draft.py", str(Path(tmp) / "no-such-book"))
        check("draft: no book folder - exit 1, one line, no traceback",
              code == 1 and out.startswith("[draft] NOT WRITTEN") and "Traceback" not in err + out, out + err)
        (root / "proofread").mkdir(exist_ok=True)
        code, out, err, _ = run("build_draft.py", str(root / "proofread"))
        check("draft: a folder with no page (the proofread folder passed for the book) - exit 1, nothing written",
              code == 1 and out.startswith("[draft] NOT WRITTEN") and "no page found" in out
              and not (root / "proofread" / "draft.md").exists(), out + err[-300:])

    # Fast: a 488-page book in seconds, the interpreter's start included.
    with tempfile.TemporaryDirectory() as tmp:
        book = Book(Path(tmp) / "big", pages=488)
        code, out, _, seconds = run("build_draft.py", str(book.root))
        check("draft: a 488-page book in under 5 s", code == 0 and seconds < 5, f"{seconds:.1f}s {out}")


def check_numbered_text() -> None:
    """Numerals folded to one mark make a date or a numbered article opening
    many pages one stretch; it is text, not a head, and stays - also after a
    head it always follows.  A head naming its volume is learned as before
    (check_draft)."""
    def date(page: int) -> str:
        return f"民國十一年{figures(1 + page // 28)}月{figures(1 + page % 28)}日"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "chronicle"
        (root / "ocr-hunyuan").mkdir(parents=True)
        opened = {}
        for page in range(1, 61):
            text = body(page)
            if page % 6 == 0:
                text = date(page) + text                       # a dated entry opens the page
            elif page % 6 == 3:
                text = f"第{figures(page)}條凡人民" + text           # a numbered article opens the page
            opened[page] = text[:12]
            (root / "ocr-hunyuan" / f"page-{page:04d}.txt").write_text(text + "\n", encoding="utf-8")
        code, out, err, _ = run("build_draft.py", str(root))
        draft = (root / "draft.md").read_text(encoding="utf-8") if code == 0 else ""
        check("draft: dates and numbered articles opening many pages are text - kept",
              code == 0 and "0 running head(s)" in out and all(start in draft for start in opened.values()),
              out + err[-300:])

        for page in range(1, 61):
            (root / "ocr-hunyuan" / f"page-{page:04d}.txt").write_text(
                f"海港政府公報{date(page)}{body(page)}\n", encoding="utf-8")
        code, out, err, _ = run("build_draft.py", str(root))
        draft = (root / "draft.md").read_text(encoding="utf-8") if code == 0 else ""
        check("draft: a head always followed by a date - the date kept",
              code == 0 and all(date(page) + body(page)[:4] in draft for page in range(1, 61)), out + err[-300:])

        # A head naming its chapter, pages sampled across the book: one
        # chapter's number on half the pages, a number of its own on each of
        # the others.  The head is learned whole, the chapter with it, not cut
        # short before the number (which would leave 十章 glued to the text).
        for page in range(1, 41):
            chapter = "十" if page <= 20 else figures(10 + page)
            (root / "ocr-hunyuan" / f"page-{page:04d}.txt").write_text(
                f"海港商務年報第三編第{chapter}章{body(page)[4:]}\n", encoding="utf-8")   # no 頁..記 opening
        for page in range(41, 61):
            (root / "ocr-hunyuan" / f"page-{page:04d}.txt").unlink()
        code, out, err, _ = run("build_draft.py", str(root))
        draft = (root / "draft.md").read_text(encoding="utf-8") if code == 0 else ""
        check("draft: a head naming its chapter is taken off whole, its number with it",
              code == 0 and "'海港商務年報第#編第#章'" in out and "章" not in draft.split("\n", 3)[3]
              and all("\n" + body(page)[4:12] in draft for page in range(1, 41)), out + err[-300:])


def check_loops() -> None:
    """Engine B's loops - one stretch written back to back until its tokens
    ran out, a page of thousands of one character - are cut: the stretch
    once, then a gap line naming the page; in the draft and in the progress
    file's pages not proofread yet.  A repetition the book prints (a table
    cell ten times over) and one of markup alone (empty table rows) are
    copied."""
    looped = {
        20: body(20) + "口" * 4000,                                           # a page of 口
        21: body(21) + ("\n銀三分三厘\n錢五十四文" * 600)[:-4],                    # a unit, its last copy cut short
        22: body(22) + "宣統" * 900 + "\n" + body(122),                        # text after it
        25: "口" * 7000,                                                    # the whole page
    }
    cell = "<td>每百觔</td>" * 10                                             # printed ten times: text
    empty = "<tr><td></td><td></td><td></td></tr>" * 60                       # 2,160 characters of markup
    with tempfile.TemporaryDirectory() as tmp:
        book = Book(Path(tmp) / "loops")
        root = book.root
        for page, text in looped.items():
            book.ocr(page).write_text(page_text(page, book.pages).replace(body(page), text), encoding="utf-8")
        book.ocr(23).write_text(page_text(23, book.pages).replace(body(23), body(23) + cell), encoding="utf-8")
        book.ocr(24).write_text(page_text(24, book.pages).replace(body(24), body(24) + "<table>" + empty
                                                                  + "</table>"), encoding="utf-8")
        code, out, err, _ = run("build_draft.py", str(root))
        draft = (root / "draft.md").read_text(encoding="utf-8") if code == 0 else ""
        lines = draft.splitlines()
        check("loops: exit 0, the line names the pages cut", code == 0 and not err
              and "4 with an OCR loop cut to a gap line [20, 21, 22, 25]" in out, out + err[-300:])
        check("loops: no loop copied", "口" * 20 not in draft and "宣統" * 10 not in draft
              and draft.count("銀三分三厘") == 2 and len(draft) < 12_000, f"{len(draft)} characters")   # kept, quoted
        gap = {page: next((line for line in lines if line.startswith(f"〔掃描第 {page} 頁：OCR 喺呢度將")), "")
               for page in looped}
        check("loops: a gap line naming each page, the stretch and its repeats",
              gap[20] == "〔掃描第 20 頁：OCR 喺呢度將「口」再重複咗 3999 次，冇抄；之後 OCR 冇再讀落去，呢頁其餘嘅字要睇原書〕"
              and gap[25].startswith("〔掃描第 25 頁：OCR 喺呢度將「口」再重複咗 6999 次")
              and "「銀三分三厘 錢五十四文」再重複咗 598 次" in gap[21]   # 599 whole copies, a last one cut short
              and gap[22] == "〔掃描第 22 頁：OCR 喺呢度將「宣統」再重複咗 899 次，冇抄〕", str(gap))
        check("loops: the stretch kept once, then the gap line as a paragraph of its own",
              f"{body(20)}口\n\n{gap[20]}" in draft and f"\n\n口\n\n{gap[25]}" in draft
              and f"{body(22)}宣統\n\n{gap[22]}\n\n{body(122)}" in draft and "\n\n\n" not in draft,
              draft[draft.find(tag(20)):][:120])
        check("loops: the head and folio of a looped page taken off as on any other",
              "年報第" not in draft and "1 running head(s) learned" in out, out)
        check("loops: a cell printed ten times kept", cell in draft)
        check("loops: markup alone kept, however long", "<table>" + empty + "</table>" in draft)
        check("loops: the header counts the pages cut",
              "，4 頁 OCR 不停重複同一段字，重複嘅部分冇抄" in lines[2], lines[2] if len(lines) > 2 else "")
        code, out, err, _ = run("build_progress.py", str(root))
        text = (root / "proofreading.md").read_text(encoding="utf-8") if code == 0 else ""
        check("loops: the progress file's pages not proofread cut the same way",
              code == 0 and "口" * 20 not in text and gap[20] in text and gap[22] in text, out + err[-300:])

    # Still seconds: a 488-page book with a loop on one page in thirty.
    with tempfile.TemporaryDirectory() as tmp:
        book = Book(Path(tmp) / "big", pages=488)
        for page in range(15, 489, 30):
            book.ocr(page).write_text(page_text(page, 488).replace(body(page), body(page) + "號" * 8000),
                                      encoding="utf-8")
        code, out, _, seconds = run("build_draft.py", str(book.root))
        check("loops: a 488-page book with 16 loops in under 5 s",
              code == 0 and seconds < 5 and "16 with an OCR loop cut" in out, f"{seconds:.1f}s {out}")


# --- the progress file -------------------------------------------------------------

def seal(directory: Path, page: int, text: str, **extra) -> None:
    """A page sealed as phase 3 seals it (the fields the seal's check reads)."""
    record = {"schemaVersion": pp.SCHEMA_VERSION, "scanPage": page, "status": "complete", "doubts": [],
              "provenance": {"markdownSha256": pp.sha256_bytes(text.encode("utf-8"))}, **extra}
    record["provenance"]["jsonPayloadSha256"] = pp.sha256_bytes(pp.canonical_json_bytes(record))
    (directory / f"page-{page:04d}.md").write_bytes(text.encode("utf-8"))
    (directory / f"page-{page:04d}.json").write_bytes(pp.canonical_json_bytes(record))


def proofread_text(page: int) -> str:
    return f"## 校對稿第{page}頁\n\n{tag(page)}已經校對。\n"


def snapshot(directory: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(directory.iterdir())}


def check_progress() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        book = Book(Path(tmp) / "haigong-soengmou")
        proofread = book.root / "proofread"
        seal(proofread, 1, f"<!-- page_0001 -->\n{proofread_text(1)}")
        seal(proofread, 2, proofread_text(2))
        (proofread / "page-0002.md").write_text(proofread_text(2) + "再寫咗一半", encoding="utf-8")  # seal not yet
        seal(proofread, 3, proofread_text(3))
        raw = (proofread / "page-0003.json").read_bytes()
        (proofread / "page-0003.json").write_bytes(raw[:len(raw) // 2])                          # cut short
        (proofread / "page-0004.md").write_text(proofread_text(4), encoding="utf-8")              # no seal
        seal(proofread, 5, "", tableStitch={"before": proofread_text(5), "movedTo": 4})            # stitched away
        seal(proofread, 6, proofread_text(6), schemaVersion=pp.SCHEMA_VERSION + 1)                # another schema
        seal(proofread, 7, proofread_text(7))                                                     # left out
        seal(proofread, 10, proofread_text(10))
        (proofread / "page-0016.md").write_text(proofread_text(16), encoding="utf-8")        # JSON, not a seal
        (proofread / "page-0016.json").write_text("[]", encoding="utf-8")
        seal(proofread, 17, proofread_text(17))
        (proofread / "page-0017.json").write_text(json.dumps(
            {"schemaVersion": pp.SCHEMA_VERSION, "status": "complete", "provenance": "?"}), encoding="utf-8")
        before = snapshot(proofread)
        code, out, err, _ = run("build_progress.py", str(book.root), cwd=Path(tmp))
        text = (book.root / "proofreading.md").read_text(encoding="utf-8") if code == 0 else ""
        total = book.pages - len(book.left_out)
        check("progress: exit 0, one line with the count", code == 0 and not err and out.startswith(
            f"[progress] wrote {book.root / 'proofreading.md'}: 3/{total} pages proofread"), out + err[-300:])
        check("progress: a header line with the count and the time", re.match(
            rf"> \*\*校對進行中\*\*：已校對 3／{total} 頁（\d{{4}}-\d{{2}}-\d{{2}} \d{{2}}:\d{{2}} UTC[+-]\d{{2}}:\d{{2}} 更新）", text)
            is not None, text[:120])
        check("progress: sealed pages as proofread", all(f"校對稿第{page}頁" in text for page in (1, 10)))
        check("progress: the header says the other pages are the draft", build_progress.HEADER_REST in text.split("\n")[0])
        check("progress: a page not sealed whole is the draft (Markdown after its seal, seal cut short, "
              "no seal, another schema, JSON not of a seal's shape)",
              all(f"校對稿第{page}頁" not in text and tag(page) in text for page in (2, 3, 4, 6, 16, 17)))
        check("progress: a page the stitch emptied stays empty", tag(5) not in text)
        check("progress: a page the manifest leaves out is left out, sealed or not", tag(7) not in text)
        check("progress: no page marker", "<!--" not in text)
        where = [text.find(tag(page)) for page in range(1, book.pages + 1)
                 if page not in book.left_out and page != 5]
        check("progress: scan order", all(at > 0 for at in where) and where == sorted(where))
        check("progress: the page breaks are paragraph breaks",
              f"{tag(1)}已經校對。\n\n" in text and "\n\n\n" not in text)
        check("progress: the proofread folder untouched", snapshot(proofread) == before)
        inode = (book.root / "proofreading.md").stat().st_ino
        seal(proofread, 11, proofread_text(11))
        code, out, _, _ = run("build_progress.py", "haigong-soengmou", "--output-dir", "proofread", cwd=Path(tmp))
        check("progress: rebuilt with the page sealed since, a new file each time",
              code == 0 and out.startswith(f"[progress] wrote {book.root / 'proofreading.md'}: 4/{total} pages proofread")
              and (book.root / "proofreading.md").stat().st_ino != inode, out)
        code, out, err, _ = run("build_progress.py", str(Path(tmp) / "no-such-book"))
        check("progress: no book folder - exit 1, one line, no traceback",
              code == 1 and out.startswith("[progress] NOT WRITTEN") and "Traceback" not in out + err, out + err)
        before = snapshot(proofread)
        code, out, err, _ = run("build_progress.py", str(proofread))
        check("progress: the proofread folder passed for the book - exit 1, nothing written in it",
              code == 1 and "no page found" in out and snapshot(proofread) == before, out + err[-300:])


def check_atomic() -> None:
    """The old file whole until the rename; nothing left behind; the old file
    kept when the write fails."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "proofreading.md"
        path.write_text("old\n", encoding="utf-8")
        seen = {}
        real_replace = os.replace

        def replace(source, target):
            seen["target"] = Path(target).read_text(encoding="utf-8")
            seen["source"] = Path(source).read_text(encoding="utf-8")
            return real_replace(source, target)

        build_draft.os.replace = replace
        try:
            build_draft.atomic_write(path, "new\n" * 1000)
        finally:
            build_draft.os.replace = real_replace
        check("atomic: the old file whole until the rename, the new one whole in the temporary file",
              seen.get("target") == "old\n" and seen.get("source") == "new\n" * 1000, str(seen)[:100])
        check("atomic: no temporary file left", sorted(p.name for p in Path(tmp).iterdir()) == ["proofreading.md"])
        real_fsync = os.fsync

        def broken(_):
            raise OSError("disk full (made up)")

        build_draft.os.fsync = broken
        try:
            with contextlib.suppress(OSError):
                build_draft.atomic_write(path, "half")
        finally:
            build_draft.os.fsync = real_fsync
        check("atomic: a failed write keeps the old file and leaves nothing",
              path.read_text(encoding="utf-8") == "new\n" * 1000
              and sorted(p.name for p in Path(tmp).iterdir()) == ["proofreading.md"])

    # A reader never sees half a file while the draft is rebuilt again and again.
    with tempfile.TemporaryDirectory() as tmp:
        book = Book(Path(tmp) / "book", pages=200)
        with contextlib.redirect_stdout(io.StringIO()):
            build_draft.main([str(book.root)])
        whole = (book.root / "draft.md").read_text(encoding="utf-8")
        stop = threading.Event()
        torn = []

        def read() -> None:
            while not stop.is_set():
                seen_text = (book.root / "draft.md").read_text(encoding="utf-8")
                if not (seen_text.startswith("> **未校對草稿**") and seen_text[-300:] == whole[-300:]
                        and len(seen_text) == len(whole)):
                    torn.append(len(seen_text))

        reader = threading.Thread(target=read)
        reader.start()
        with contextlib.redirect_stdout(io.StringIO()):
            for _ in range(15):
                build_draft.main([str(book.root)])
        stop.set()
        reader.join()
        check("atomic: a reader never sees half the draft (15 rebuilds)", not torn, str(torn[:5]))


# --- the wait ----------------------------------------------------------------------

# A stand-in phase 3 run: seals the pages it is given, one by one, as the real
# one does (Markdown, then the seal), prints its lines, then ends or hangs.
STAND_IN = '''
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, os.environ["STAND_IN_SCRIPTS"])
import proofread_pages as pp
plan = json.loads(os.environ["STAND_IN_PLAN"])
out = Path(plan["output"])
out.mkdir(parents=True, exist_ok=True)
print(f"  proofreading {len(plan['pages'])} page(s), 2 in flight, effort=xhigh", flush=True)
for page in plan["pages"]:
    time.sleep(plan.get("delay", 0.2))
    text = f"## 校對稿第{page}頁\\n"
    record = {"schemaVersion": pp.SCHEMA_VERSION, "scanPage": page, "status": "complete", "doubts": [],
              "provenance": {"markdownSha256": pp.sha256_bytes(text.encode("utf-8"))}}
    record["provenance"]["jsonPayloadSha256"] = pp.sha256_bytes(pp.canonical_json_bytes(record))
    (out / f"page-{page:04d}.md").write_bytes(text.encode("utf-8"))
    (out / f"page-{page:04d}.json").write_bytes(pp.canonical_json_bytes(record))
    print(f"  page {page:04d}: 1.0s  clean=True  adjudicated=0  calls=3  reasoning=100", flush=True)
if plan.get("hang"):
    time.sleep(120)
report = Path(plan["report"])
report.write_text(json.dumps({"counts": {"requested": len(plan["pages"]), "completed": len(plan["pages"]),
                                         "skippedCurrent": 0, "blocked": 0, "failed": 0}, "wallSeconds": 1.0}))
print(f"  requested {len(plan['pages'])} | completed {len(plan['pages'])} | skipped 0 | blocked 0 | failed 0",
      flush=True)
print(f"  report: {report}", flush=True)
'''


def start(root: Path, plan: dict, log: str) -> subprocess.Popen:
    (root / "bin").mkdir(exist_ok=True)
    (root / "bin" / "proofread_pages.py").write_text(textwrap.dedent(STAND_IN), encoding="utf-8")
    env = dict(os.environ, STAND_IN_PLAN=json.dumps(plan), STAND_IN_SCRIPTS=str(SCRIPTS))
    with open(root / log, "wb") as handle:
        return subprocess.Popen([sys.executable, "bin/proofread_pages.py", "renders", "ocr-paddle", "proofread",
                                 "--draft2-directory", "ocr-hunyuan", "--pages", ",".join(map(str, plan["pages"]))],
                                cwd=root, env=env, stdout=handle, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)


def wait(root: Path, output: str, log: str, *extra: str, timeout: float = 30) -> tuple[int, str]:
    done = subprocess.run([sys.executable, str(SCRIPTS / "wait_for_run.py"), output, log, "--timeout", str(timeout),
                           "--interval", "0.2", *extra], cwd=root, capture_output=True, text=True,
                          timeout=timeout + 60)
    lines = done.stdout.splitlines()
    if len(lines) != 1 or done.stderr:
        PROBLEMS.append(f"wait_for_run.py printed {done.stdout!r} {done.stderr[-300:]!r}")
        return done.returncode, done.stdout
    return done.returncode, lines[0]


def check_wait() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        book = Book(Path(tmp) / "book", pages=12)
        root = book.root
        (root / "ocr-paddle").mkdir()
        total = book.pages - len(book.left_out)
        progress = root / "proofreading.md"

        # Without the switch: nothing written, the line as before.
        process = start(root, {"output": str(root / "proofread"), "pages": [1, 2], "report": str(root / "r0.json"),
                               "delay": 0.1}, "p0.log")
        code, line = wait(root, "proofread", "p0.log")
        process.wait()
        check("wait: without --progress no progress file, the line as before",
              code == 0 and not progress.exists() and "progress" not in line, line)

        # Running when the wait runs out: rebuilt while it waits (a new file
        # each time) and once more when it returns; the line ends with it.
        process = start(root, {"output": str(root / "proofread"), "pages": [3, 4, 5, 6], "report": str(root / "r1.json"),
                               "delay": 0.5, "hang": True}, "p1.log")
        inodes: set[int] = set()
        stop = threading.Event()

        def watch() -> None:
            while not stop.is_set():
                with contextlib.suppress(OSError):
                    inodes.add(progress.stat().st_ino)
                time.sleep(0.05)

        watcher = threading.Thread(target=watch)
        watcher.start()
        code, line = wait(root, "proofread", "p1.log", "--progress", ".", "--progress-every", "0.7", timeout=4)
        stop.set()
        watcher.join()
        text = progress.read_text(encoding="utf-8") if progress.is_file() else ""
        sealed = len(list((root / "proofread").glob("page-*.json")))
        check("wait: still running - exit 75, the line ends with the progress file and the pages proofread",
              code == 75 and line.startswith("[wait] RESULT exit=75 RUNNING proofread_pages.py")
              and line.endswith(f"; progress file {progress}: {sealed}/{total} pages proofread"), line)
        check("wait: the progress file rebuilt while it waits, not only at the end", len(inodes) >= 2,
              f"{len(inodes)} version(s) seen")
        check("wait: the progress file holds the pages sealed", f"已校對 {sealed}／{total} 頁" in text
              and all(f"校對稿第{page}頁" in text for page in range(1, sealed + 1)), text[:100])
        process.kill()
        process.wait()

        # Done: the last rebuild names every page sealed.
        process = start(root, {"output": str(root / "proofread"), "pages": [10, 11, 12],
                               "report": str(root / "r2.json"), "delay": 0.2}, "p2.log")
        code, line = wait(root, "proofread", "p2.log", "--progress", str(root))
        process.wait()
        sealed = len(list((root / "proofread").glob("page-*.json")))
        check("wait: done - exit 0, the line ends with the progress file",
              code == 0 and line.startswith("[wait] RESULT exit=0 DONE proofread_pages.py")
              and line.endswith(f"; progress file {progress}: {sealed}/{total} pages proofread"), line)

        # A progress file that cannot be built: said, the exit code the step's.
        code, line = wait(root, "proofread", "p2.log", "--progress", str(root / "ocr-hunyuan" / "page-0001.txt"))
        check("wait: a progress file that cannot be built changes only the line",
              code == 0 and "DONE proofread_pages.py" in line and "; progress file NOT rebuilt (" in line, line)

        # Not phase 3: no progress file for an OCR runner's wait.
        progress.unlink()
        (root / "ocr-paddle" / "page-0001.txt").write_text("x", encoding="utf-8")
        (root / "ocr-paddle" / "page-0001.json").write_text("{}", encoding="utf-8")
        (root / "o.log").write_text("  requested 1 | completed 1 | skipped 0 | blocked 0 | failed 0\n"
                                    f"  report: {root / 'r3.json'}\n", encoding="utf-8")
        code, line = wait(root, "ocr-paddle", "o.log", "--progress", str(root), timeout=2)
        check("wait: no progress file for a step that is not phase 3",
              code == 0 and not progress.exists() and "progress" not in line, line)


def check_quiet_sources() -> None:
    """The two builders ask no model and open no connection."""
    found = {name: [word for word in ("urllib", "http", "socket", "Client(", "requests")
                    if word in (SCRIPTS / name).read_text(encoding="utf-8")]
             for name in ("build_draft.py", "build_progress.py")}
    check("the builders open no connection", not any(found.values()), str(found))


# --- the skill's text --------------------------------------------------------------

def check_skill_text() -> None:
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    section = skill.split("## 分三次交付", 1)[-1].split("\n## ", 1)[0] if "## 分三次交付" in skill else ""
    safe = skill.split("## 安全並行", 1)[-1].split("\n## ", 1)[0]
    rules = {
        "a section on the three deliveries": bool(section),
        "the draft's command": "python3 scripts/build_draft.py BOOK" in section,
        "the draft when both engines are done": "兩個 OCR 引擎都做完" in section,
        "the draft from engine B, with the measured reason": all(w in section for w in ("引擎 B", "75.8%", "5.8%")),
        "the draft's path told at once, in one line": "即刻用一行話畀用戶知草稿喺邊" in section,
        "on without waiting": "唔使等佢回覆" in section,
        "a draft not written does not stop the flow": "唔阻流程" in section,
        "engine B's loops cut to the stretch once and a gap line, short repetitions copied":
            all(w in section for w in ("不停重複（loop", "嗰段字留一次", "寫一行空位講明重複咗幾多次", "照抄")),
        "the progress file through the wait": "`--progress BOOK`" in section and "proofreading.md" in section,
        "sealed pages as proofread, the others as the draft": "封存齊嘅頁" in section and "用草稿嘅字" in section,
        "the seal alone, not the run's arguments (so an --overwrite run's old seals count)":
            "唔睇封嗰陣用咩參數" in section and "`--overwrite`" in section,
        "the pages left out: no marker expected or blank, a duplicate label alone not":
            all(w in section for w in ("`marker_expected: false`", "`content: blank`", "`relation: exact_duplicate` 嘅頁照出")),
        "the progress line only when asked or once an hour": "用戶問先講" in section and "最多每個鐘講一次" in section,
        "final.md the last delivery": "`final.md`" in section and "最後一次交付" in section,
        # The third delivery is 〈做完之後〉's: finish_book.py writes final.md
        # and doubts.md; repair_book.py alone writes neither.
        "final.md and doubts.md from finish_book.py, as 〈做完之後〉 says":
            all(w in section for w in ("`finish_book.py BOOK`", "〈做完之後〉", "`BOOK/final.md`", "`BOOK/doubts.md`"))
            and "由修補步驟（`scripts/repair_book.py`）出" not in section,
        "final.md with the doubt list": "疑問清單" in section,
        "one name for the book folder, 〈做完之後〉's BOOK": "BOOK_DIR" not in skill
            and "即係〈做完之後〉嘅 `BOOK`" in section,
        "the book folder in Jyutping without tones": "冇聲調嘅粵拼" in section,
        "or plain English": "簡單英文" in section,
        "never Mandarin pinyin": "唔好用普通話拼音" in section,
        "file names in English": all(f"`{name}`" in section for name in ("draft.md", "proofreading.md", "final.md")),
        "step 3 sends to the draft": "兩個 runner 都做完就即刻出未校對草稿（`build_draft.py`）" in skill,
        "the wait bullet: --progress in phase 3": "--progress BOOK   # phase 3" in safe
                                                  and "整唔到都唔改 exit code" in safe,
        "both builders listed": "- `scripts/build_draft.py`" in skill and "- `scripts/build_progress.py`" in skill,
    }
    for name, ok in rules.items():
        check(f"SKILL.md: {name}", ok)
    # The numbers the text states are the code's.
    check("SKILL.md: the rebuild every 5 minutes is wait_for_run.PROGRESS_EVERY",
          __import__("wait_for_run").PROGRESS_EVERY == 300 and "每 5 分鐘" in section)


def main() -> int:
    check_draft()
    check_numbered_text()
    check_loops()
    check_progress()
    check_atomic()
    check_wait()
    check_quiet_sources()
    check_skill_text()
    for problem in PROBLEMS:
        print("FAIL", problem)
    print(f"{'FAIL' if PROBLEMS else 'ok  '} deliveries: {len(PROBLEMS)} problem(s)")
    return 1 if PROBLEMS else 0


if __name__ == "__main__":
    sys.exit(main())
