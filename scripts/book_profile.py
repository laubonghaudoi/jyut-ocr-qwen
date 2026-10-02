#!/usr/bin/env python3
"""Measure a book before proofreading it.

No two books behave alike, so nothing about a book is assumed; it is measured
on a sample of its own pages and sealed in book-profile.json, which
proofread_pages.py then reads:

- layout:   running heads and folios, including facsimiles that print several
            original leaves on one page.  Measured first, from engine A's
            blocks alone, because furniture must be kept out of the next step.
- engines:  which engine READS this book better.  Only genuine character
            substitutions count - both engines produced text, it is not
            furniture, and it is not two forms of one character - and each is
            read off its crop, with the order in which the two readings are
            shown varied.  Each distinct pair (已/巳, 問/間) is one vote, so a
            pair that recurs all through a book cannot decide it alone.  A
            preference is stated only when the leader's Wilson lower bound
            clears one half; otherwise the profile says "adjudicate".
            Measured: an engine right on 10 of 11 disputes in one book was
            right on 2 of 14 in the next.
- variants: disagreements between two forms of one character (粵/粤, 既/旣).
            Which form is printed is not asked per occurrence: the model is
            not consistent from crop to crop (on one book's single type it
            split 19 to 9 on the same pair), and pixel matching against a
            modern typeface fared no better.  So these are listed per pair,
            most frequent first, with crops from different pages, and one
            ruling per pair covers every occurrence in the book.  At the end
            the model rules each pair by majority over its crops
            (variant_vote.py, into variant-rulings.json next to the profile;
            a person's rulings there are kept, and nothing waits for one);
            --no-variant-vote leaves the pairs no person ruled unruled, as
            before, and takes an earlier vote's rulings out of that file.
- notation: which marks the book prints (circles, dots, doubled circles,
            emphasis circles or dots beside every character, brackets) and
            how dense they get, from a block-by-block survey.

Each finding is sealed with its evidence (verdicts, crops and their hashes,
counts), so a wrong profile can be seen to be wrong.

    python3 scripts/book_profile.py RENDER_DIR DRAFT_DIR DRAFT2_DIR PROFILE.json
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import itertools
import json
import math
import os
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proofread_pages as pp  # noqa: E402
import variant_vote  # noqa: E402

SCHEMA_VERSION = 2
DEFAULT_PROBE_PAGES = 8
DEFAULT_MAX_CROPS = 160
# Distinct substitution pairs with a decided verdict (A or B) needed before a
# preference can be declared.
MIN_DECIDED = 16
# Final decision: a 95% Wilson lower bound.  The interim checks that allow the
# probe to stop early are repeated looks at accumulating data, which inflates
# false positives (simulated: equal engines declared unequal ~17% of the time
# at 1.96), so they use a stricter bound and a fixed schedule.
WILSON_Z = 1.96
WILSON_Z_INTERIM = 3.0
INTERIM_EVERY = 32
PROBE_MINIMUM_AGREEMENT = 0.70     # below this the page is an order conflict
NOTATION_BLOCKS_PER_PAGE = 3
NOTATION_MINIMUM_CHARACTERS = 12
VARIANT_CROPS_PER_PAIR = 3
VARIANT_PAIRS_LISTED = 40
# What the profile says of the variant pairs: without the model's vote
# (--no-variant-vote) the note it always carried; with it, where the rulings are.
VARIANT_NOTE = ("which form is printed is ruled per pair by a person in variant-rulings.json "
                "next to this profile; the model is not asked")
VARIANT_NOTE_VOTE = ("which form is printed is ruled per pair by the model's vote over the pair's crops "
                     "(variant_vote.py) in variant-rulings.json next to this profile; a person's "
                     "rulings there are kept and overrule it")

NOTATION_SYSTEM = """你係古籍標點體例調查員。畀你一個版面 block 嘅裁圖。
淨係報告圖上**印咗**嘅符號，唔好評論內容，唔好推測原書「應該」點斷句。

符號一般印喺字旁或者字後；裁圖邊緣貼住、屬於隔籬行或者隔籬欄嘅符號唔好計。
格線、版框、污點、字嘅筆畫都唔係符號。

逐項答，每項一行，格式一模一樣：
符號：<圖上出現過嘅符號，用以下寫法列出：。 。。 ， 、 ； ： ？ ！ （ ） 「 」 『 』（兩個圈連住就寫 。。）；一個都冇就寫 無>
雙圈：<有／冇>（兩個圈連住印，喺句末或者句中）
圈點：<冇／圈／點>（連續一串字，每個字旁邊都印住圈或者點，用嚟強調，唔係斷句；有就答係圈定係點）
點數：<整數>（圖上符號總數；兩個圈連住計兩個；圈點每個都計）"""

# The prompt before 。。 was one of the forms listed (--no-doubled-notation).
NOTATION_SYSTEM_SINGLE = NOTATION_SYSTEM.replace("。 。。 ，", "。 ，").replace("（兩個圈連住就寫 。。）", "")

NOTATION_MARKS = "。，、；：？！（）「」『』"


def wilson_lower(successes: int, total: int, z: float = WILSON_Z) -> float:
    """Lower bound of the Wilson score interval for a proportion."""
    if total == 0:
        return 0.0
    p = successes / total
    centre = p + z * z / (2 * total)
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return (centre - margin) / (1 + z * z / total)


def decide_preference(votes: Mapping[str, int], minimum: int = MIN_DECIDED,
                      z: float = WILSON_Z) -> tuple[str, str]:
    """Preferred engine from per-pair votes, or 'adjudicate' when unsure."""
    a, b = votes.get("A", 0), votes.get("B", 0)
    decided = a + b
    if decided < minimum:
        return "adjudicate", (f"only {decided} decided pair(s) (A {a}, B {b}); "
                              f"at least {minimum} needed to choose an engine")
    lead, count = ("A", a) if a >= b else ("B", b)
    bound = wilson_lower(count, decided, z)
    if bound <= 0.5:
        return "adjudicate", (f"no engine clearly better: A {a}, B {b} distinct pairs "
                              f"(lower bound {bound:.2f} for {lead})")
    return lead, (f"engine {lead} right on {count} of {decided} distinct substitution pairs "
                  f"(lower bound {bound:.2f})")


# The profile aligns the drafts as written, as it did when the books' preferences
# were measured: the merge's variant-folded alignment (proofread_pages.align_drafts,
# its --no-folded-alignment) is the merge's.  Measured by the round-3 review: on
# pages 1-60 of four books (206 pages) the probe's disagreements differ on 18
# pages folded, and a re-profiled book could change its preference.
PROFILE_FOLDED_ALIGNMENT = False


def page_candidates(renders: Path, drafts: Path, drafts2: Path) -> list[dict[str, Any]]:
    """Every page with both drafts and a render, with its size and agreement."""
    out = []
    for path in sorted(drafts.glob("page-*.txt")):
        match = re.fullmatch(r"page-(\d{4})\.txt", path.name)
        if not match:
            continue
        page = int(match.group(1))
        other = drafts2 / path.name
        render = renders / f"page-{page:04d}.png"
        if not (other.is_file() and render.is_file()):
            continue
        a, b = path.read_text(encoding="utf-8"), other.read_text(encoding="utf-8")
        size = len(pp.CJK(a))
        if size == 0:
            continue
        segments = pp.align_drafts(a, b, folded=PROFILE_FOLDED_ALIGNMENT)
        agreed = sum(len(x["a"]) for x in segments if x["tag"] == "equal")
        agreement = agreed / max(len(pp.CJK(a)), len(pp.CJK(b)), 1)
        out.append({"page": page, "characters": size, "agreement": round(agreement, 3)})
    return out


def select_probe_pages(candidates: Sequence[Mapping[str, Any]], count: int) -> list[int]:
    """Spread the probe across the book: the fullest page of each stratum."""
    if not candidates:
        return []
    count = max(1, min(count, len(candidates)))
    ordered = sorted(candidates, key=lambda c: c["page"])
    chosen = []
    for k in range(count):
        stratum = ordered[k * len(ordered) // count:(k + 1) * len(ordered) // count]
        if stratum:
            chosen.append(max(stratum, key=lambda c: (c["characters"], -c["page"]))["page"])
    return sorted(set(chosen))


def classify(seg: Mapping[str, Any]) -> str:
    if pp.is_numeral_conflict(dict(seg)):
        return "numeral"
    if pp.is_rare_codepoint_conflict(dict(seg)):
        return "rare"
    return "prose"


def page_segments(page: int, renders: Path, drafts: Path, drafts2: Path) -> list[dict[str, Any]]:
    """Every disagreement on a page, located in its layout block."""
    a = (drafts / f"page-{page:04d}.txt").read_text(encoding="utf-8")
    b = (drafts2 / f"page-{page:04d}.txt").read_text(encoding="utf-8")
    blocks = pp.load_blocks(drafts / f"page-{page:04d}.json")
    lengths = [len(pp.CJK(x["text"])) for x in blocks]
    ends = list(itertools.accumulate(lengths))
    valid = bool(blocks) and sum(lengths) == len(pp.CJK(a))
    out, cursor = [], 0
    for seg in pp.fuse_numeral_runs(pp.align_drafts(a, b, folded=PROFILE_FOLDED_ALIGNMENT)):
        start = cursor
        cursor += len(seg["a"])
        if seg["tag"] == "equal":
            continue
        block, offset = pp.locate_segment(blocks, ends, lengths, valid, start, seg)
        out.append({"page": page, "seg": seg, "block": block, "offset": offset,
                    "kind": classify(seg)})
    return out


def is_furniture_item(item: Mapping[str, Any], heads: Sequence[str]) -> bool:
    """A disagreement about furniture says nothing about reading glyphs."""
    block = item.get("block") or {}
    if block.get("label") in pp.FURNITURE_LABELS:
        return True
    if heads and pp.is_running_head(str(block.get("text") or ""), heads):
        return True
    seg = item["seg"]
    both = pp.CJK(seg["a"]) + "|" + pp.CJK(seg["b"])
    return any(head and head in both for head in heads)


def interleave(per_page: Sequence[Sequence[Any]]) -> list[Any]:
    """Round-robin across pages, so a stopped probe still spans the book."""
    out, index = [], 0
    while any(index < len(items) for items in per_page):
        for items in per_page:
            if index < len(items):
                out.append(items[index])
        index += 1
    return out


def pair_votes(verdicts: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """One vote per distinct reading pair, to the majority of its verdicts."""
    by_pair: dict[frozenset, Counter] = defaultdict(Counter)
    for record in verdicts:
        if record["winner"] in ("A", "B"):
            key = frozenset((pp.CJK(record["draft_reading"]), pp.CJK(record["writer_reading"])))
            by_pair[key][record["winner"]] += 1
    votes: Counter = Counter()
    for tally in by_pair.values():
        a, b = tally.get("A", 0), tally.get("B", 0)
        if a != b:
            votes["A" if a > b else "B"] += 1
    return dict(votes)


def calibrate_engines(client: "pp.Client", items: Sequence[Mapping[str, Any]], renders: Path,
                      crops_dir: Path, max_crops: int, workers: int, max_tokens: int,
                      minimum: int) -> dict[str, Any]:
    """Read substitutions off their crops until one engine is clearly the better reader."""
    queue = list(items)
    crops_dir.mkdir(parents=True, exist_ok=True)
    verdicts: list[dict[str, Any]] = []
    usage: Counter = Counter()
    stopped = "all eligible substitutions on the probe pages read"

    def run(index_item: tuple[int, Mapping[str, Any]]) -> dict[str, Any]:
        index, item = index_item
        render = renders / f"page-{item['page']:04d}.png"
        crop = pp.segment_crop(render, None, item["block"], item["offset"], item["seg"])
        name = f"page-{item['page']:04d}-probe-{index:03d}.png"
        if crop:
            (crops_dir / name).write_bytes(crop)
        # Vary which reading is shown first, deterministically so a re-run
        # reproduces it.
        swap = int(hashlib.sha256(f"{item['page']}:{index}".encode()).hexdigest(), 16) % 2 == 1
        _, record, metrics = pp.adjudicate_segment(client, crop, item["seg"], max_tokens,
                                                   fallback_engine="A", swap=swap)
        record.update({"page": item["page"], "kind": item["kind"],
                       "crop": name if crop else None,
                       "cropSha256": hashlib.sha256(crop).hexdigest() if crop else None})
        record.pop("needs_research", None)
        record.pop("research_classified", None)
        return {"record": record, "metrics": metrics}

    position = 0
    while position < len(queue) and position < max_crops:
        end = min(position + INTERIM_EVERY, len(queue), max_crops)
        batch = list(enumerate(queue[position:end], start=position))
        with cf.ThreadPoolExecutor(max(1, workers)) as pool:
            for result in pool.map(run, batch):
                verdicts.append(result["record"])
                for key, value in (result["metrics"] or {}).items():
                    if isinstance(value, (int, float)):
                        usage[key] += value
        position = end
        preference, _ = decide_preference(pair_votes(verdicts), minimum, WILSON_Z_INTERIM)
        if preference in ("A", "B"):
            stopped = f"stopped after {position} crop(s): preference settled at the interim bound"
            break
    else:
        if position >= max_crops and position < len(queue):
            stopped = f"crop budget ({max_crops}) spent with {len(queue) - position} eligible unread"

    votes = pair_votes(verdicts)
    preference, reason = decide_preference(votes, minimum)
    items_tally = Counter(v["winner"] for v in verdicts)
    first = Counter((v["shownFirst"], v["winner"]) for v in verdicts if v["winner"] in ("A", "B"))
    read = items_tally.get("A", 0) + items_tally.get("B", 0) + items_tally.get("neither", 0)
    return {
        "preferEngine": preference,
        "reason": reason,
        "stopped": stopped,
        "decision": {"pairVotes": votes, "preferEngine": preference},
        "items": {"eligible": len(queue), "read": len(verdicts),
                  "A": items_tally.get("A", 0), "B": items_tally.get("B", 0),
                  "neither": items_tally.get("neither", 0),
                  "undecided": items_tally.get("undecided", 0)},
        # Evidence of position bias: how often the reading shown first won.
        "shownFirstWins": {f"{shown}-shown-first": {"A": first.get((shown, "A"), 0),
                                                     "B": first.get((shown, "B"), 0)}
                           for shown in ("A", "B")},
        "expectedAccuracy": {engine: (round(items_tally.get(engine, 0) / read, 3) if read else None)
                             for engine in ("A", "B")},
        "verdicts": verdicts,
        "usage": dict(usage),
    }


def collect_variants(client: "pp.Client", candidates: Sequence[Mapping[str, Any]], renders: Path,
                     drafts: Path, drafts2: Path, heads: Sequence[str], crops_dir: Path,
                     workers: int, crops_per_pair: int = VARIANT_CROPS_PER_PAIR
                     ) -> tuple[dict[str, Any], dict[str, str]]:
    """Every single-character substitution pair in the book, classified; variant pairs
    listed, each with up to CROPS_PER_PAIR crops from different pages."""
    occurrences: dict[tuple[str, str], list[tuple[int, dict]]] = defaultdict(list)
    for candidate in candidates:
        if candidate["agreement"] < PROBE_MINIMUM_AGREEMENT:
            continue
        for item in page_segments(candidate["page"], renders, drafts, drafts2):
            if item["kind"] != "prose" or is_furniture_item(item, heads):
                continue
            a, b = pp.CJK(item["seg"]["a"]), pp.CJK(item["seg"]["b"])
            if a and b and len(a) == len(b):
                for x, y in zip(a, b):
                    if x != y:
                        occurrences[(x, y)].append((candidate["page"], item))
    pairs = sorted(occurrences, key=lambda p: -len(occurrences[p]))
    with cf.ThreadPoolExecutor(max(1, workers)) as pool:
        verdicts = list(pool.map(lambda p: pp.classify_pair(client, p[0], p[1]), pairs))
    classes = {f"{x}|{y}": ("variant" if v == "variant" else "different")
               for (x, y), v in zip(pairs, verdicts)}
    listed = []
    crops_dir.mkdir(parents=True, exist_ok=True)
    # A ruling is about the pair, not about which engine read which form: the
    # engines swap which of them normalises from page to page, so both
    # orientations are one entry.
    merged: dict[frozenset, list[tuple[str, str]]] = defaultdict(list)
    for pair in pairs:
        if classes[f"{pair[0]}|{pair[1]}"] == "variant":
            merged[frozenset(pair)].append(pair)
    ranked = sorted(merged.values(), key=lambda group: -sum(len(occurrences[g]) for g in group))
    for group in ranked[:VARIANT_PAIRS_LISTED]:
        x, y = max(group, key=lambda g: len(occurrences[g]))
        crops = []
        seen_pages: set[int] = set()
        group_occurrences = [o for g in group for o in occurrences[g]]
        for page, item in group_occurrences:
            if len(crops) >= crops_per_pair or page in seen_pages:
                continue
            if item["block"] is None or item["offset"] is None:
                continue
            text_a = pp.CJK(item["seg"]["a"])
            index = max(text_a.find(x), text_a.find(y))
            png = pp.crop_glyph(renders / f"page-{page:04d}.png", item["block"],
                                item["offset"] + max(index, 0), 1, context=2)
            if png:
                name = f"variant-{ord(x):x}-{ord(y):x}-p{page:04d}.png"
                (crops_dir / name).write_bytes(png)
                crops.append({"page": page, "crop": name,
                              "cropSha256": hashlib.sha256(png).hexdigest(),
                              "context": item["seg"]["before"][-4:] + "【】" + item["seg"]["after"][:3]})
                seen_pages.add(page)
        listed.append({"engineA": x, "engineB": y,
                       "occurrences": len(group_occurrences),
                       "byOrientation": {f"{g[0]}|{g[1]}": len(occurrences[g]) for g in group},
                       "pages": sorted({p for p, _ in group_occurrences})[:20], "crops": crops})
    total = sum(len(v) for k, v in occurrences.items() if classes[f"{k[0]}|{k[1]}"] == "variant")
    # Which list decided each pair (the user's rulings, OpenCC's allographs),
    # or "model" where neither covers it and the model's classification stands.
    sources = {f"{x}|{y}": pp.variant_source(x, y) or "model" for x, y in pairs}
    return {"pairs": listed, "variantOccurrences": total, "pairsListed": len(listed),
            "pairSources": sources,
            "note": VARIANT_NOTE}, classes


def parse_notation(text: str, doubled_only: bool = True) -> dict[str, Any]:
    """One block's notation answer.

    A block printing doubled circles and nothing else was answered 符號：無 /
    雙圈：有 / 點數：22 - the listed forms had no 。。 - and read as
    unpunctuated, its doubled circles and its count thrown away: 3 of 43
    blocks on one book (the first holding 7 。。 and 12 。 in its golden), 21
    of 45 on another, which kept its doubled flag only because other blocks
    answered otherwise.  With DOUBLED_ONLY such an answer is a doubled-circle
    block with that count, its mark the circle; one with a count of 0 still
    contradicts itself and stays unpunctuated.
    """
    def line(label: str) -> str:
        match = re.search(rf"{label}[：:]\s*(.+)", text or "")
        return match.group(1).strip() if match else ""
    marks_line = line("符號")
    marks = sorted({c for c in marks_line if c in NOTATION_MARKS})
    count_line = line("點數")
    count = pp.parse_census("符號：" + count_line.split()[0]) if count_line else None
    emphasis_line = line("圈點")
    emphasis = "圈" if emphasis_line.startswith("圈") else "點" if emphasis_line.startswith("點") else None
    none = ("無" in marks_line and not marks)
    if doubled_only and none and line("雙圈").startswith("有") and count:
        marks, none = ["。"], False
    return {
        "marks": marks,
        "none": none,
        # An answer that lists no mark but reports doubled circles, emphasis or
        # a count contradicts itself; only consistent answers are used.
        "doubled": line("雙圈").startswith("有") and not none,
        "emphasis": emphasis if not none else None,
        "count": count if not none else None,
    }


def survey_notation(client: "pp.Client", pages: Sequence[int], renders: Path, drafts: Path,
                    workers: int, max_tokens: int, doubled_only: bool = True) -> dict[str, Any]:
    """Ask, block by block on the probe pages, which marks are printed.
    DOUBLED_ONLY: 。。 is a listed form and a doubled-circle-only answer is
    read as such (parse_notation); off, the older prompt and reading."""
    jobs = []
    for page in pages:
        blocks = pp.load_blocks(drafts / f"page-{page:04d}.json")
        texts = [b for b in blocks if b.get("label") not in pp.FURNITURE_LABELS
                 and len(pp.CJK(str(b["text"]))) >= NOTATION_MINIMUM_CHARACTERS]
        texts.sort(key=lambda b: -len(pp.CJK(str(b["text"]))))
        for block in texts[:NOTATION_BLOCKS_PER_PAGE]:
            render = renders / f"page-{page:04d}.png"
            characters = len(pp.CJK(str(block["text"])))
            # A whole-page block shrinks the marks below what the model can
            # see; survey column groups of it instead (the first and the last,
            # so a block's opening and closing columns are both covered).
            tiles = pp.block_tiles(render, block, characters)
            if tiles:
                for crop, lo, hi in (tiles[0], tiles[-1]):
                    jobs.append((page, block, crop, hi - lo))
            else:
                crop = pp.upscale_crop(pp.crop_block(render, block["box"], pad=0.012, pad_left=0.0))
                jobs.append((page, block, crop, characters))

    def run(job: tuple[int, Mapping[str, Any], bytes | None, int]) -> dict[str, Any]:
        page, block, crop, characters = job
        text, _ = client.ask_answering(NOTATION_SYSTEM if doubled_only else NOTATION_SYSTEM_SINGLE,
                                       "報告呢個 block 印咗乜嘢符號。", crop, max_tokens, kind="notation")
        found = parse_notation(text, doubled_only)
        found.update({"page": page, "label": block["label"], "characters": characters,
                      "perCharacter": (round(found["count"] / characters, 3)
                                       if found["count"] is not None and characters else None),
                      "answer": (text or "").strip()[:400]})
        return found

    with cf.ThreadPoolExecutor(max(1, workers)) as pool:
        blocks = list(pool.map(run, jobs))
    seen = Counter(mark for b in blocks for mark in b["marks"])
    doubled = sum(1 for b in blocks if b["doubled"])
    emphasis = Counter(b["emphasis"] for b in blocks if b["emphasis"])
    ratios = sorted(b["perCharacter"] for b in blocks if b["perCharacter"] is not None)
    top_emphasis = emphasis.most_common(1)[0] if emphasis else None
    return {
        # Evidence, not a verdict: how many surveyed blocks showed each mark.
        "marks": sorted(mark for mark, n in seen.items() if n >= 2),
        "markBlocks": dict(sorted(seen.items(), key=lambda kv: -kv[1])),
        "blocksSurveyed": len(blocks),
        "unpunctuatedBlocks": sum(1 for b in blocks if b["none"]),
        "doubledBlocks": doubled,
        "emphasisBlocks": dict(emphasis),
        "doubled": doubled >= 2,
        "emphasis": top_emphasis[0] if top_emphasis and top_emphasis[1] >= 2 else None,
        "commas": seen.get("，", 0) * 2 > len(blocks),
        # Second-densest consistent block, in marks per character: one
        # miscounted block (a count of characters, not marks) must not relax
        # the degenerate-output guards for a whole book.
        "maxMarksPerCharacter": ratios[-2] if len(ratios) >= 2 else None,
        "medianMarksPerCharacter": statistics.median(ratios) if ratios else None,
        # How the answers were read (parse_notation): doubled-circle-only
        # answers as doubled circles, or as unpunctuated (--no-doubled-notation).
        "doubledOnlyRead": doubled_only,
        "blocks": blocks,
    }


def survey_layout(pool: Sequence[int], drafts: Path, learned_heads: bool = False) -> dict[str, Any]:
    """Running heads and leaves per page, from engine A's blocks alone.
    LEARNED_HEADS (on unless --no-learned-heads): the running head learned by
    where it is printed too (proofread_pages.learn_heads), as learnedHeads."""
    within: Counter = Counter()
    across: Counter = Counter()
    sizes: dict[str, list[float]] = defaultdict(list)
    page_blocks = {page: pp.load_blocks(drafts / f"page-{page:04d}.json") for page in pool}
    for blocks in page_blocks.values():
        texts = [pp.CJK(str(b["text"])) for b in blocks]
        short = [t for t in texts if 3 <= len(t) <= 30]
        for t, n in Counter(short).items():
            if n >= 2:
                within[t] += 1
        for t in set(short):
            across[t] += 1
    pages_seen = len(page_blocks)
    # A leaf's running head repeats on (nearly) every page it appears on; a
    # section heading or date line printed twice on a couple of pages stands
    # alone everywhere else.
    heads = {t for t, n in within.items() if n >= 3 and 2 * n >= across[t]}
    # Whole blocks repeated verbatim on at least half the pages are furniture
    # too (a running head read the same way everywhere).
    heads |= {t for t, n in across.items() if pages_seen >= 3 and n >= max(3, pages_seen // 2)}
    for blocks in page_blocks.values():
        for b in blocks:
            text = pp.CJK(str(b["text"]))
            if text in heads and isinstance(b.get("box"), list) and len(b["box"]) == 4:
                sizes[text].append(max(abs(b["box"][2]), abs(b["box"][3])) / max(len(text), 1))
    per_page = []
    for blocks in page_blocks.values():
        texts = [pp.CJK(str(b["text"])) for b in blocks]
        per_page.append(max([1] + [sum(1 for t in texts if pp.is_running_head(t, [h])) for h in heads]))
    repeating = [n for n in per_page if n >= 2]
    leaves = Counter(repeating).most_common(1)[0][0] if len(repeating) * 2 > len(per_page) else 1
    return {
        "leavesPerPage": leaves,
        "leavesDistribution": dict(sorted(Counter(per_page).items())),
        "runningHeads": sorted(heads),
        # Type size of each head (page fraction per character): a block is
        # dropped as a head only when it is set in that size, so a body line
        # that happens to read the same is not.
        "runningHeadGlyph": {h: round(statistics.median(v), 5) for h, v in sizes.items() if v},
        "pagesExamined": pages_seen,
        # The title with what is printed beside it - labels, their families,
        # the folio sequence - and where the band stands (on unless
        # --no-learned-heads; only when on, so a profile without it is as
        # before).
        **({"learnedHeads": pp.learn_heads(page_blocks, sorted(heads))} if learned_heads else {}),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("render_directory", type=Path)
    parser.add_argument("draft_directory", type=Path, help="engine A drafts (with layout JSON)")
    parser.add_argument("draft2_directory", type=Path, help="engine B drafts")
    parser.add_argument("profile", type=Path, help="where to write book-profile.json")
    parser.add_argument("--probe-pages", type=int, default=DEFAULT_PROBE_PAGES,
                        help=f"pages to sample across the book (default {DEFAULT_PROBE_PAGES})")
    parser.add_argument("--pages", help="explicit probe pages, e.g. 3,40-42 (overrides --probe-pages)")
    parser.add_argument("--max-crops", type=int, default=DEFAULT_MAX_CROPS,
                        help=f"adjudication budget for the engine calibration (default {DEFAULT_MAX_CROPS})")
    parser.add_argument("--min-decided", type=int, default=MIN_DECIDED)
    parser.add_argument("--workers", type=int, default=4,
                        help="parallel model calls; match the server's --max-concurrency.  The client "
                             "never has more than this many requests at the server at once")
    parser.add_argument("--no-inflight-cap", action="store_true",
                        help="no cap on the requests at the server at once (as before): each step runs "
                             "--workers threads, which alone bound them only while no step asks more "
                             "than one call at a time per thread")
    parser.add_argument("--endpoint", default=os.environ.get("PROOFREAD_ENDPOINT", pp.DEFAULT_ENDPOINT))
    parser.add_argument("--model", default=os.environ.get("PROOFREAD_MODEL", pp.DEFAULT_MODEL))
    parser.add_argument("--reasoning-effort", default=os.environ.get("PROOFREAD_EFFORT", pp.DEFAULT_EFFORT))
    parser.add_argument("--max-tokens", type=int, default=16000)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--reuse-engines", action="store_true",
                        help="keep the engine calibration of an existing profile at the same path "
                             "when it was measured by the same schema on the same probe pages and "
                             "drafts; re-measure everything else")
    parser.add_argument("--no-variant-vote", action="store_true",
                        help="do not ask the model which form of each variant pair the book prints "
                             "(variant_vote.py): pairs no person ruled fall back in proofreading as without "
                             "rulings.  An earlier vote's rulings are taken out of variant-rulings.json next "
                             "to the profile (a person's stay; a file with nothing of a person's is removed); "
                             "a file a person wrote alone is not touched")
    parser.add_argument("--variant-vote-crops", type=int, default=variant_vote.VOTE_CROPS_PER_PAIR,
                        help=f"crops the vote asks per pair (default {variant_vote.VOTE_CROPS_PER_PAIR}); the "
                             "profile keeps that many per pair where the book has them.  Ignored with "
                             "--no-variant-vote")
    parser.add_argument("--variant-vote-calls", type=int, default=variant_vote.VOTE_MAX_CALLS,
                        help=f"calls the vote makes per book at most, one per crop asked (default "
                             f"{variant_vote.VOTE_MAX_CALLS}); a call cut off at the token limit is asked "
                             f"again one effort lower, so it can take up to {variant_vote.REQUESTS_PER_CALL} requests")
    parser.add_argument("--no-pair-cache", action="store_true",
                        help="ask the model every variant-pair question again, keeping the answers in this "
                             "process only (as before).  Without it the model's complete answers are read from "
                             "and kept in a store on disk shared by every book and run (PAIR_CACHE_PATH, default "
                             f"{pp._pair_cache.DEFAULT_PATH}), keyed by the request and the server's identity; "
                             "see scripts/_pair_cache.py")
    parser.add_argument("--no-learned-heads", dest="learned_heads", action="store_false", default=True,
                        help="do not learn the running head by where it is printed too (on by default since "
                             "the round-4 benchmark, as proofread_pages.py's --learned-heads; "
                             "proofread_pages.ROUND4_DEFAULTS): with it on, the labels printed beside the "
                             "measured heads on several pages and their families, the folio sequence, where the "
                             "band stands on odd and even pages (proofread_pages.learn_heads) are written as "
                             "layout.learnedHeads, which proofread_pages.py reads unless it runs with "
                             "--no-learned-heads (without it in the profile, phase 3 learns the same record from "
                             "the drafts).  No model call")
    parser.add_argument("--learned-heads", dest="learned_heads", action="store_true", default=True,
                        help="the default, accepted so that a script that passes it runs as before; "
                             "--no-learned-heads switches it off")
    parser.add_argument("--no-doubled-notation", action="store_true",
                        help="the older notation survey: 。。 not a listed form, and a block answered "
                             "'no marks, doubled circles, N marks' read as unpunctuated (parse_notation)")
    return parser


def parse_page_list(text: str) -> list[int]:
    pages: set[int] = set()
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        first, _, last = token.partition("-")
        pages.update(range(int(first), int(last or first) + 1))
    return sorted(pages)


def pair_cache_record(store: Any, sources: Mapping[str, str]) -> dict[str, Any]:
    """What the profile says of the pair classes the model gave (pairSources
    "model"): the store's summary, and for each pair every vote with whether it
    came from the store and when it was kept there."""
    origins = {}
    for key, source in sources.items():
        origin = pp._PAIR_ORIGIN.get(frozenset(key.split("|"))) if source == "model" else None
        if origin is not None:
            origins[origin["pair"]] = origin
    record = {**store.summary(), "pairs": dict(sorted(origins.items()))}
    record["pairsAllFromStore"] = sum(1 for o in origins.values() if all(v["fromStore"] for v in o["votes"]))
    record["pairsAskedNow"] = sum(1 for o in origins.values() if not any(v["fromStore"] for v in o["votes"]))
    record["pairsPartlyFromStore"] = len(origins) - record["pairsAllFromStore"] - record["pairsAskedNow"]
    return record


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    # The model's answers to the pair question come from, and go to, the store
    # on disk shared by every book and run, unless --no-pair-cache.
    previous = pp.use_pair_store(None if arguments.no_pair_cache else pp._pair_cache.PairStore())
    try:
        return profile_book(arguments)
    finally:
        pp.use_pair_store(previous)


def profile_book(arguments: argparse.Namespace) -> int:
    renders = arguments.render_directory.expanduser().resolve()
    drafts = arguments.draft_directory.expanduser().resolve()
    drafts2 = arguments.draft2_directory.expanduser().resolve()
    started = time.monotonic()
    candidates = page_candidates(renders, drafts, drafts2)
    if not candidates:
        print("ERROR no page has both drafts, a render and any text", file=sys.stderr)
        return 1
    # Probe pages for the engine calibration must be pages where the engines
    # agree on reading order; an order conflict is resolved by taking one page
    # whole, so its "disagreements" say nothing about glyphs.  The notation
    # survey can use any page with text.
    aligned = [c for c in candidates if c["agreement"] >= PROBE_MINIMUM_AGREEMENT]
    if arguments.pages:
        wanted = parse_page_list(arguments.pages)
        pages = [c["page"] for c in aligned if c["page"] in wanted]
        survey_pages = [c["page"] for c in candidates if c["page"] in wanted]
    else:
        pages = select_probe_pages(aligned, arguments.probe_pages)
        # Notation does not depend on the engines agreeing about reading order,
        # so its sample is drawn from every page with text.
        survey_pages = select_probe_pages(candidates, arguments.probe_pages)
    effort = None if arguments.reasoning_effort.lower() == "none" else arguments.reasoning_effort
    # The server admits --max-concurrency requests and queues the rest, and the
    # agent that runs the skill shares it: a profile that sends more than its
    # lanes takes them from the agent.  The same cap as phase 3's --max-inflight.
    client = pp.Client(arguments.endpoint, arguments.model, effort, arguments.timeout,
                       arguments.temperature,
                       **({} if arguments.no_inflight_cap else {"max_inflight": max(1, arguments.workers)}))
    profile_path = arguments.profile.expanduser().resolve()
    run_stamp = time.strftime("%Y%m%dT%H%M%S")
    crops_dir = profile_path.with_name(profile_path.stem + "-crops") / run_stamp
    print(f"  probing {len(pages)} page(s) for engines: {pages}; notation on {survey_pages}", flush=True)

    layout = survey_layout([c["page"] for c in candidates], drafts, arguments.learned_heads)
    heads = layout["runningHeads"]
    print(f"  layout: {layout['leavesPerPage']} leaf/leaves per page, "
          f"{len(heads)} running head(s) {heads[:4]}", flush=True)
    if "learnedHeads" in layout:
        learned = layout["learnedHeads"]
        print(f"  learned running head: labels {list(learned['labels'])[:12]}, families {learned['families']}, "
              f"{len(learned['folio']['runs'])} folio run(s), {len(learned['regions'])} region(s), a band on "
              f"{learned['pagesWithBand']} of {learned['pagesExamined']} pages", flush=True)

    # The vote asks up to --variant-vote-crops crops per pair; the profile
    # keeps at least that many where the book has them.  With the vote off it
    # keeps what it always kept.
    crops_per_pair = (VARIANT_CROPS_PER_PAIR if arguments.no_variant_vote
                      else max(VARIANT_CROPS_PER_PAIR, arguments.variant_vote_crops))
    variants, classes = collect_variants(client, candidates, renders, drafts, drafts2, heads,
                                         crops_dir, arguments.workers, crops_per_pair)
    if not arguments.no_variant_vote:
        variants["note"] = VARIANT_NOTE_VOTE
    top = [p["engineA"] + "/" + p["engineB"] + "×" + str(p["occurrences"]) for p in variants["pairs"][:6]]
    print(f"  variants: {variants['variantOccurrences']} variant-form disagreement(s) in "
          f"{sum(1 for v in classes.values() if v == 'variant')} pair(s); top {top}", flush=True)
    pair_cache = (pair_cache_record(pp._PAIR_STORE, variants["pairSources"])
                  if pp._PAIR_STORE is not None else None)
    if pair_cache is not None:
        print(f"  pair store: {len(pair_cache['pairs'])} pair(s) the model classified, "
              f"{pair_cache['pairsAllFromStore']} wholly from the store, {pair_cache['pairsAskedNow']} asked now; "
              f"answers {pair_cache['answersFromStore']} from the store, {pair_cache['answersAskedNow']} asked, "
              f"{pair_cache['answersKept']} kept"
              + (f"; store not used: {pair_cache['notUsedBecause']}" if pair_cache["notUsedBecause"] else ""),
              flush=True)

    engines = None
    digest = pp.draft_digest(pages, drafts, drafts2)
    if arguments.reuse_engines and profile_path.is_file():
        previous = json.loads(profile_path.read_text(encoding="utf-8"))
        if (previous.get("schemaVersion") == SCHEMA_VERSION and previous.get("probePages") == pages
                and (previous.get("sources") or {}).get("probeDraftsSha256") == digest):
            engines = previous.get("engines")
            print("  engines: reused from the existing profile", flush=True)
    if engines is None:
        if not pages:
            engines = {"preferEngine": "adjudicate",
                       "reason": "no page where the engines agree on reading order; "
                                 "engine preference not measurable",
                       "decision": {"pairVotes": {}, "preferEngine": "adjudicate"},
                       "verdicts": []}
        else:
            per_page = []
            excluded: Counter = Counter()
            for page in pages:
                keep = []
                for item in page_segments(page, renders, drafts, drafts2):
                    seg = item["seg"]
                    if item["kind"] != "prose":
                        excluded[item["kind"]] += 1
                    elif not (seg["a"] and seg["b"]):
                        excluded["insertion-or-deletion"] += 1
                    elif is_furniture_item(item, heads):
                        excluded["furniture"] += 1
                    elif pp.variant_segment(None, seg, classes):
                        excluded["variant-form"] += 1
                    else:
                        keep.append(item)
                per_page.append(keep)
            engines = calibrate_engines(client, interleave(per_page), renders, crops_dir,
                                        arguments.max_crops, arguments.workers,
                                        arguments.max_tokens, arguments.min_decided)
            engines["excluded"] = dict(excluded)
    votes = (engines.get("decision") or {}).get("pairVotes") or {}
    print(f"  engines: distinct substitution pairs A {votes.get('A', 0)} / B {votes.get('B', 0)} "
          f"-> {engines['preferEngine']} ({engines.get('reason')}; {engines.get('stopped', '')}; "
          f"excluded {engines.get('excluded')})", flush=True)

    notation = survey_notation(client, survey_pages, renders, drafts, arguments.workers,
                               arguments.max_tokens, doubled_only=not arguments.no_doubled_notation)
    print(f"  notation: {notation['markBlocks']} of {notation['blocksSurveyed']} blocks"
          f"{', doubled' if notation['doubled'] else ''}"
          f"{', emphasis ' + notation['emphasis'] if notation['emphasis'] else ''}"
          f", density bound from {notation['maxMarksPerCharacter']} marks/char", flush=True)

    profile = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": pp.utc_now(),
        "model": arguments.model,
        "reasoningEffort": effort,
        "sources": {"renders": str(renders), "draftA": str(drafts), "draftB": str(drafts2),
                    "probeDraftsSha256": digest},
        "probePages": pages,
        "surveyPages": survey_pages,
        "candidatePages": len(candidates),
        "cropsDirectory": str(crops_dir.relative_to(profile_path.parent)),
        "preferEngine": engines["preferEngine"],
        "engines": engines,
        "pairClasses": classes,
        # How the model's pair classes were reached: from the store on disk or
        # asked now (absent with --no-pair-cache).
        **({"pairClassCache": pair_cache} if pair_cache is not None else {}),
        "variants": variants,
        "notation": notation,
        "layout": layout,
        "seconds": round(time.monotonic() - started, 1),
    }
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = profile_path.with_name(profile_path.name + ".tmp")
    temporary.write_bytes(pp.canonical_json_bytes(profile))
    os.replace(temporary, profile_path)
    print(f"  profile: {profile_path} ({profile['seconds']}s)")
    rulings_path = profile_path.with_name("variant-rulings.json")
    if arguments.no_variant_vote:
        # Off is as before the vote: an earlier vote's rulings next to the
        # profile would still rule the pairs no person ruled, so they go.
        withdrawn = variant_vote.withdraw(rulings_path)
        if withdrawn:
            print(variant_vote.describe_withdrawn(withdrawn, rulings_path), flush=True)
    else:
        # Last, so the profile is sealed whatever the vote does; nothing after
        # it waits for a person.
        record = variant_vote.rule_book(client, profile_path, rulings_path, arguments.variant_vote_crops,
                                        arguments.variant_vote_calls, arguments.workers, arguments.max_tokens)
        print(variant_vote.describe(record, rulings_path), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
