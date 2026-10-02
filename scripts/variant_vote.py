#!/usr/bin/env python3
"""Rule which form of each variant pair a book prints, by the model's vote over the pair's crops.

A variant pair is two forms of one character (粵/粤, 既/旣).  The book profile
lists a book's pairs, most frequent first, each with crops of the printed glyph
from different pages (book_profile.collect_variants), and one ruling per pair
decides every occurrence in the book (proofread_pages.resolve_variant).

The model is asked per crop, not per pair: shown one crop and the two forms, in
an order varied from crop to crop, it answers which form the crop shows, or
that it cannot tell.  A reply cut off at the token limit on every rung of the
effort ladder (it may loop on an answer line) or empty is no answer and not
counted, as a failed call is not.  A pair is ruled by the majority of its
crops: the form at least VOTE_MINIMUM crops chose, more crops than chose the
other form and more than half of the crops that answered.  A tie, a pair whose
every crop could not tell and a pair with a single vote stay unruled, and
proofreading falls back for them as it does with no ruling (the engine the
book's rulings favour, else the reading preference; the run report's
variantQueue).  Asking per crop and voting is deliberate: the model is not
consistent from crop to crop (measured: on one book's single type it split 19
to 9 on the same pair), so no single crop may decide a book.  Both forms of a
pair are acceptable variants of one character, so a wrong ruling costs
glyph-form fidelity, not a wrong character, while a person asked to rule costs
a stop of the pipeline.

The result goes next to the profile as variant-rulings.json.  Each ruling the
model made carries "ruledBy": "model", the form it chose ("modelPrinted"), its
votes and every crop asked: the file, its SHA-256, the order the two forms were
shown in, the answer, the tokens spent and the effort that answered (a crop
with no answer says why, with the rungs asked).  Pairs left unruled are listed
under "modelUnruled" with their votes and why; "modelVote" records the run
(model, effort, bounds, calls, requests in usage.n).  A person's rulings in an
existing file are kept as they are, and the model rules only the pairs they
left out.  A person may overrule the model at any time by setting a pair's
"printed" (and "ruledBy": "person"); nothing waits for that.

Runs at the end of book_profile.py.  Its --no-variant-vote turns it off and
takes an earlier vote's rulings out of the file (withdraw), so the pairs no
person ruled fall back as without rulings.  On an existing profile it runs
alone:

    python3 scripts/variant_vote.py BOOK/book-profile.json --workers 8
    python3 scripts/variant_vote.py BOOK/book-profile.json --dry-run
    python3 scripts/variant_vote.py BOOK/book-profile.json --output OTHER.json --compare RULINGS.json
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proofread_pages as pp  # noqa: E402

# Crops asked per pair: the profile keeps this many per pair, each from a
# different page (book_profile.VARIANT_CROPS_PER_PAIR).
VOTE_CROPS_PER_PAIR = 3
# Calls per book, one question per crop: every crop of every pair the
# profile lists (book_profile.VARIANT_PAIRS_LISTED pairs of
# VOTE_CROPS_PER_PAIR crops).  A call is not one request: a question whose
# reply is cut off at the token limit is asked again one effort lower
# (Client.ask_answering), so a call can take up to REQUESTS_PER_CALL
# requests; modelVote.usage.n counts the requests made.
VOTE_MAX_CALLS = 120
REQUESTS_PER_CALL = len(pp.Client.EFFORT_LADDER)
# Crops that must choose the same form before it rules the pair: one crop
# never decides a book.
VOTE_MINIMUM = 2
VOTE_KIND = "variant-vote"
CANNOT_TELL = "cannot tell"
# A crop whose reply was cut off at the token limit on every rung of the
# effort ladder, or was empty: no answer, and not counted.
NO_ANSWER = "no answer"
REPLY_KEPT = 400

VOTE_SYSTEM = """你係古籍字形鑑定專家。畀你一張書頁裁圖（直排：由上至下讀，一欄讀完先讀左邊下一欄），同埋一個字嘅兩種寫法。兩種寫法係同一個字、意思一樣；要答嘅淨係：圖上指定嗰個位，印出嚟嘅字形係邊一種。

1. 先用畀你嘅上下文，喺裁圖入面搵到嗰個字。
2. 淨係描述圖上嗰個字嘅筆畫同部件，兩種寫法唔同嘅地方逐處睇清楚。
3. 最後先同兩種寫法對照。唔好靠邊種寫法常見、邊種舊啲、邊種合規範去揀：舊書兩種都有印，同一本書都可以兩種都印。

搵唔到嗰個字、字太模糊、兩種寫法唔同嘅地方睇唔清，或者圖上嘅字同兩種都唔似，就答睇唔清，唔好估。

最後另起一行，淨係寫以下其中一行：
答：甲
答：乙
答：睇唔清"""

ANSWER_LINE = re.compile(r"答[：:]\s*(睇唔清|甲|乙|\S)")

INSTRUCTIONS = ("per-pair variant-form rulings for this book: printed = the form the pages show, one "
                "ruling for every occurrence of the pair. ruledBy model = the model's vote over the "
                "pair's crops (votes, crops, modelVote); a pair without ruledBy model is a person's "
                "ruling and is never voted on again. Optional: to overrule the model, set printed "
                "and ruledBy person; nothing waits for it")


def shown_order(x: str, y: str, crop_sha: str) -> tuple[str, str]:
    """The order the two forms are offered in for one crop: varied from crop
    to crop, so a model that leans to the first option does not decide a pair
    by position, and fixed by the crop, so a re-run asks the same question."""
    first, second = sorted((x, y))
    flip = int(hashlib.sha256(f"{first}{second}:{crop_sha}".encode()).hexdigest(), 16) % 2 == 1
    return (second, first) if flip else (first, second)


def vote_prompt(context: str | None, first: str, second: str) -> str:
    """One crop's question.  CONTEXT is the profile's reading around the spot,
    with 【】 standing for it."""
    where = (f"裁圖入面嗰段字大約係「{context.replace('【】', '【？】')}」，要判斷嘅係【？】嗰個字。"
             if context and "【】" in context else "要判斷嘅係裁圖中間嗰個字。")
    return (f"{where}\n"
            f"甲) {first}（U+{ord(first):04X}）\n"
            f"乙) {second}（U+{ord(second):04X}）\n"
            "圖上嗰個位印嘅係甲定乙？最後另起一行淨係寫 `答：甲`、`答：乙` 或者 `答：睇唔清`。")


def parse_vote(text: str | None, first: str, second: str) -> str:
    """The form an answer chose, CANNOT_TELL, or "unparsed"."""
    found = ANSWER_LINE.findall(text or "")
    if not found:
        return "unparsed"
    last = found[-1]
    if last == "睇唔清":
        return CANNOT_TELL
    if last == "甲":
        return first
    if last == "乙":
        return second
    return last if last in (first, second) else "unparsed"


def decide(votes: Mapping[str, int], x: str, y: str, answered: int,
           minimum: int = VOTE_MINIMUM) -> tuple[str | None, str]:
    """The form the pair's crops chose, or None, and why.  ANSWERED counts the
    crops that answered anything (a vote, cannot tell, or an answer that was
    neither); calls that failed are not answers."""
    nx, ny = votes.get(x, 0), votes.get(y, 0)
    rest = answered - nx - ny
    if answered == 0:
        return None, "no crop was answered"
    if nx == ny == 0:
        return None, f"no crop chose a form ({answered} could not tell)"
    if nx == ny:
        return None, f"tie: {x} {nx}, {y} {ny} ({rest} could not tell)"
    lead, count, other = (x, nx, ny) if nx > ny else (y, ny, nx)
    if count < minimum:
        return None, f"{lead} chosen by {count} crop(s); at least {minimum} must agree"
    if 2 * count <= answered:
        return None, f"{lead} chosen by {count} of {answered} answered crops, not a majority"
    return lead, (f"{lead} chosen by {count} of {answered} answered crops "
                  f"({other} for the other form, {rest} could not tell)")


def profile_pairs(profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The profile's variant pairs, both orientations as one, most frequent first."""
    merged: dict[frozenset, dict[str, Any]] = {}
    for pair in (profile.get("variants") or {}).get("pairs") or []:
        key = frozenset((pair["engineA"], pair["engineB"]))
        if key in merged:  # profiles written before orientations were merged
            merged[key]["occurrences"] += pair["occurrences"]
            merged[key]["crops"] = merged[key]["crops"] + list(pair.get("crops") or [])
        else:
            merged[key] = dict(pair, crops=list(pair.get("crops") or []))
    return sorted(merged.values(), key=lambda p: -p["occurrences"])


def person_rulings(existing: Mapping[str, Any]) -> tuple[list[Any], set[frozenset]]:
    """The entries of an existing rulings file that are not the model's (kept
    verbatim), and the pairs they rule.  A pair the model left unruled that a
    person gave a printed form on its modelUnruled entry is theirs as well,
    and is kept among the rulings (proofread_pages.variant_person_unruled)."""
    kept, pairs = [], set()
    for entry in [*(existing.get("rulings") or []), *pp.variant_person_unruled(existing)]:
        if isinstance(entry, Mapping) and pp.variant_ruling_by(entry) == "model":
            continue
        kept.append(entry)
        if not isinstance(entry, Mapping):
            continue
        forms = [pp.CJK(str(f)) for f in entry.get("forms") or []]
        if len(forms) == 2 and pp.CJK(str(entry.get("printed") or "")) in forms:
            pairs.add(frozenset(forms))
    return kept, pairs


def plan_votes(pairs: Sequence[Mapping[str, Any]], crops_dir: Path, crops_per_pair: int,
               max_calls: int, minimum: int = VOTE_MINIMUM) -> tuple[list[dict[str, Any]], list[tuple]]:
    """Which crops of which pairs are asked, within the bounds.

    Returns one entry per pair (its crops set aside, and why a pair gets no
    call) and the calls: (pair index, the profile's crop record, crop bytes,
    their SHA-256).  A crop whose file is missing or differs from the hash the
    profile sealed is not asked; a pair with fewer than MINIMUM crops left
    cannot be ruled and is not asked; pairs are served most frequent first
    until MAX_CALLS is spent."""
    entries, calls, budget = [], [], max_calls
    for index, pair in enumerate(pairs):
        chosen, set_aside = [], []
        for crop in pair.get("crops") or []:
            if len(chosen) >= crops_per_pair:
                break
            path = crops_dir / str(crop.get("crop") or "")
            if not path.is_file():
                set_aside.append({"page": crop.get("page"), "crop": crop.get("crop"), "setAside": "no such file"})
                continue
            data = path.read_bytes()
            sha = pp.sha256_bytes(data)
            if crop.get("cropSha256") and crop["cropSha256"] != sha:
                set_aside.append({"page": crop.get("page"), "crop": crop.get("crop"),
                                  "setAside": "the file differs from the hash the profile sealed"})
                continue
            chosen.append((index, crop, data, sha, path))
        entry: dict[str, Any] = {"pair": pair, "setAside": set_aside, "asked": len(chosen)}
        if len(chosen) < minimum:
            entry.update(asked=0, reason=f"{len(chosen)} usable crop(s); at least {minimum} must agree")
        elif len(chosen) > budget:
            entry.update(asked=0, reason=f"call budget ({max_calls} per book) spent")
        else:
            budget -= len(chosen)
            calls.extend(chosen)
        entries.append(entry)
    return entries, calls


def rule_book(client: Any, profile_path: Path, rulings_path: Path | None = None,
              crops_per_pair: int = VOTE_CROPS_PER_PAIR, max_calls: int = VOTE_MAX_CALLS,
              workers: int = 4, max_tokens: int = 16000, minimum: int = VOTE_MINIMUM,
              dry_run: bool = False) -> dict[str, Any] | None:
    """Vote on each pair of the profile a person has not ruled, and write the
    rulings file (RULINGS_PATH, by default variant-rulings.json next to the
    profile).  Returns the run's record (modelVote) with "written" saying
    whether the file was written; None when there is nothing to vote on, and
    the file is not touched.  Calls run WORKERS at a time, under the client's
    own in-flight cap."""
    started = time.monotonic()
    profile_path = profile_path.expanduser().resolve()
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    rulings_path = (rulings_path.expanduser().resolve() if rulings_path
                    else profile_path.with_name("variant-rulings.json"))
    existing: dict[str, Any] = {}
    if rulings_path.is_file():
        existing = json.loads(rulings_path.read_text(encoding="utf-8"))
    kept, ruled_by_person = person_rulings(existing)
    crops_dir = profile_path.parent / (profile.get("cropsDirectory") or "")
    pairs = [p for p in profile_pairs(profile) if frozenset((p["engineA"], p["engineB"])) not in ruled_by_person]
    if not pairs:
        return None
    entries, calls = plan_votes(pairs, crops_dir, crops_per_pair, max_calls, minimum)
    record: dict[str, Any] = {
        "generatedAt": pp.utc_now(),
        "model": getattr(client, "model", None),
        "reasoningEffort": getattr(client, "effort", None),
        "maxTokens": max_tokens,
        "profile": os.path.relpath(profile_path, rulings_path.parent),
        "profileSha256": pp.sha256_file(profile_path),
        "promptSha256": pp.sha256_bytes(VOTE_SYSTEM.encode("utf-8")),
        "cropsPerPair": crops_per_pair,
        "maxCalls": max_calls,
        "requestsPerCallAtMost": REQUESTS_PER_CALL,
        "minimumVotes": minimum,
        "rule": ("a pair is ruled by the form at least minimumVotes crops chose, more than chose the "
                 "other form and more than half of the crops that answered; otherwise it is unruled"),
        "pairsPersonRuled": len(ruled_by_person),
        "pairsToVote": len(pairs),
        "calls": len(calls),
    }
    if dry_run:
        return dict(record, written=False, dryRun=True)

    def ask(call: tuple) -> tuple[dict[str, Any], bool]:
        index, crop, data, sha, path = call
        x, y = pairs[index]["engineA"], pairs[index]["engineB"]
        first, second = shown_order(x, y, sha)
        evidence = {"page": crop.get("page"), "crop": os.path.relpath(path, rulings_path.parent),
                    "cropSha256": sha, "shown": [first, second]}
        try:
            text, metrics = client.ask_answering(VOTE_SYSTEM, vote_prompt(crop.get("context"), first, second),
                                                 data, max_tokens, kind=VOTE_KIND)
        except pp.ProofreadError as error:
            return dict(evidence, answer="error", error=str(error)[:300]), False
        metrics = metrics or {}
        # The effort that answered: a call that thought past max_tokens is
        # asked again one rung lower (Client.ask_answering).  Tokens are those
        # of every request the call made.
        spent = {"reply": (text or "").strip()[-REPLY_KEPT:], "completionTokens": metrics.get("completion_tokens"),
                 "effort": metrics.get("effort")}
        # Cut off on every rung (the longest partial comes back, which may
        # repeat an answer line as it loops) or empty: no answer, as the
        # structure pass refuses it (no_answer).
        why = pp.no_answer(text or "", metrics)
        if why:
            return dict(evidence, answer=NO_ANSWER, noAnswer=why, **spent, degraded=True,
                        **{k: metrics[k] for k in ("rungsAsked", "rungsCutOff") if k in metrics}), True
        return dict(evidence, answer=parse_vote(text, first, second), **spent), True

    ledger: list[dict[str, Any]] = []
    token = pp._CALL_LEDGER.set(ledger)
    try:
        with cf.ThreadPoolExecutor(max(1, workers)) as pool:
            answers = pp.in_context(pool, ask, calls) if calls else []
    finally:
        pp._CALL_LEDGER.reset(token)
    asked: dict[int, list[dict[str, Any]]] = {}
    for call, (evidence, _) in zip(calls, answers):
        asked.setdefault(call[0], []).append(evidence)
    failed = sum(1 for _, ok in answers if not ok)
    unanswered = sum(1 for evidence, _ in answers if evidence["answer"] == NO_ANSWER)

    rulings, unruled = [], []
    for index, entry in enumerate(entries):
        pair = pairs[index]
        x, y = pair["engineA"], pair["engineB"]
        crops = asked.get(index, [])
        tally = Counter(c["answer"] for c in crops)
        answered = sum(n for answer, n in tally.items() if answer not in ("error", NO_ANSWER))
        votes = {x: tally.get(x, 0), y: tally.get(y, 0), "cannotTell": answered - tally.get(x, 0) - tally.get(y, 0)}
        if "reason" in entry:
            printed, reason = None, entry["reason"]
        else:
            printed, reason = decide(tally, x, y, answered, minimum)
        out = {"forms": [x, y], "occurrences": pair["occurrences"], "votes": votes, "reason": reason,
               "crops": crops + entry["setAside"]}
        if printed:
            rulings.append({"forms": [x, y], "printed": printed, "modelPrinted": printed, "ruledBy": "model",
                            **{k: v for k, v in out.items() if k != "forms"}})
        else:
            unruled.append(out)
    record.update({
        "failedCalls": failed,
        "noAnswerCalls": unanswered,
        "pairsRuled": len(rulings),
        "pairsUnruled": len(unruled),
        "seconds": round(time.monotonic() - started, 1),
        "usage": pp.summarize_calls(ledger).get(VOTE_KIND, {}),
    })
    if calls and failed + unanswered == len(calls):
        # Nothing was learned (the server did not answer, or no reply was an
        # answer): an existing file stays as it is.
        return dict(record, written=False)
    document = {k: v for k, v in existing.items() if k not in ("rulings", "modelUnruled", "modelVote")}
    document.setdefault("book", (profile.get("sources") or {}).get("renders"))
    document.setdefault("instructions", INSTRUCTIONS)
    # A top-level ruledBy a person wrote in their own words is theirs to keep.
    if document.get("ruledBy") in (None, "model", "person", "person and model"):
        document["ruledBy"] = ("person and model" if ruled_by_person and rulings
                               else "person" if ruled_by_person else "model")
    document["rulings"] = kept + rulings
    document["modelUnruled"] = unruled
    document["modelVote"] = record
    write_rulings(rulings_path, document)
    return dict(record, written=True)


def write_rulings(rulings_path: Path, document: Mapping[str, Any]) -> None:
    rulings_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = rulings_path.with_name(rulings_path.name + ".tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(temporary, rulings_path)


def withdraw(rulings_path: Path) -> dict[str, Any] | None:
    """Take an earlier vote's rulings out of RULINGS_PATH, for a profile built
    without the vote (book_profile.py --no-variant-vote): proofreading applies
    whatever rulings the file holds, so otherwise the model would still rule
    the pairs no person ruled, which the switch says fall back as without
    rulings.  A person's rulings stay as they are, and a file holding nothing
    of a person's is removed.  Returns how many rulings of the model's were
    taken out, how many entries were kept and whether the file was removed;
    None when the file does not exist or holds nothing of the model's, and it
    is not touched."""
    if not rulings_path.is_file():
        return None
    existing = json.loads(rulings_path.read_text(encoding="utf-8"))
    kept, _ = person_rulings(existing)
    model = [e for e in existing.get("rulings") or [] if isinstance(e, Mapping) and pp.variant_ruling_by(e) == "model"]
    if not model and not any(key in existing for key in ("modelUnruled", "modelVote")):
        return None
    if not kept:
        rulings_path.unlink()
        return {"withdrawn": len(model), "kept": 0, "removed": True}
    document = {k: v for k, v in existing.items() if k not in ("rulings", "modelUnruled", "modelVote")}
    # What the vote wrote at the top, not a person's words.
    if document.get("ruledBy") in ("model", "person and model"):
        document["ruledBy"] = "person"
    if document.get("instructions") == INSTRUCTIONS:
        del document["instructions"]
    document["rulings"] = kept
    write_rulings(rulings_path, document)
    return {"withdrawn": len(model), "kept": len(kept), "removed": False}


def describe(record: Mapping[str, Any] | None, rulings_path: Path) -> str:
    """One line for the log."""
    if record is None:
        return "  variant vote: no pair left to rule (every listed pair ruled by a person, or none listed)"
    if record.get("dryRun"):
        return (f"  variant vote (dry run): {record['pairsToVote']} pair(s) to rule, {record['calls']} call(s); "
                f"{record['pairsPersonRuled']} ruled by a person")
    if not record.get("written"):
        return (f"  WARNING variant vote: all {record['calls']} call(s) failed or answered nothing; "
                f"{rulings_path.name} not written, unruled pairs fall back as without rulings")
    failed = f", {record['failedCalls']} call(s) failed" if record.get("failedCalls") else ""
    failed += (f", {record['noAnswerCalls']} cut off on every effort or empty (no answer)"
               if record.get("noAnswerCalls") else "")
    requests = (record.get("usage") or {}).get("n")
    requests = f" in {requests} request(s)" if requests else ""
    return (f"  variant vote: {record['pairsRuled']} pair(s) ruled by the model, {record['pairsUnruled']} left "
            f"unruled, {record['pairsPersonRuled']} ruled by a person kept; {record['calls']} call(s){requests}"
            f"{failed}; {rulings_path} ({record['seconds']}s)")


def describe_withdrawn(result: Mapping[str, Any], rulings_path: Path) -> str:
    """One line for the log: what withdraw took out."""
    what = ("the file held nothing of a person's and is removed" if result["removed"]
            else f"{result['kept']} entr(y/ies) of a person's kept")
    return (f"  variant vote off: {result['withdrawn']} ruling(s) of an earlier vote taken out of "
            f"{rulings_path}; {what}; pairs no person ruled fall back as without rulings")


def compare(model_path: Path, other_path: Path) -> dict[str, Any]:
    """Pair by pair, the model's rulings in MODEL_PATH against the rulings in
    OTHER_PATH (a person's): which agree, which differ, which the model left
    unruled, which the other file does not rule."""
    model = json.loads(model_path.read_text(encoding="utf-8"))
    other = json.loads(other_path.read_text(encoding="utf-8"))
    theirs = {}
    for entry in other.get("rulings") or []:
        forms = [pp.CJK(str(f)) for f in entry.get("forms") or []]
        printed = pp.CJK(str(entry.get("printed") or ""))
        if len(forms) == 2 and printed in forms:
            theirs[frozenset(forms)] = printed
    rows = []
    for entry in model.get("rulings") or []:
        if pp.variant_ruling_by(entry) != "model":
            continue
        key = frozenset(entry["forms"])
        rows.append({"forms": entry["forms"], "occurrences": entry.get("occurrences"), "model": entry["printed"],
                     "other": theirs.get(key), "votes": entry.get("votes")})
    for entry in model.get("modelUnruled") or []:
        rows.append({"forms": entry["forms"], "occurrences": entry.get("occurrences"), "model": None,
                     "other": theirs.get(frozenset(entry["forms"])), "votes": entry.get("votes"),
                     "reason": entry.get("reason")})
    rows.sort(key=lambda r: -(r["occurrences"] or 0))
    verdicts = Counter("not ruled in the other file" if r["other"] is None
                       else "model unruled" if r["model"] is None
                       else "agree" if r["model"] == r["other"] else "differ" for r in rows)
    weighted = Counter()
    for r in rows:
        if r["other"] is not None and r["model"] is not None:
            weighted["agree" if r["model"] == r["other"] else "differ"] += r["occurrences"] or 0
    return {"pairs": dict(verdicts), "occurrences": dict(weighted), "rows": rows}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("profile", type=Path, help="book-profile.json from scripts/book_profile.py")
    parser.add_argument("--output", type=Path,
                        help="the rulings file to write (default: variant-rulings.json next to the profile); "
                             "a person's rulings already in it are kept")
    parser.add_argument("--crops", type=int, default=VOTE_CROPS_PER_PAIR,
                        help=f"crops asked per pair (default {VOTE_CROPS_PER_PAIR})")
    parser.add_argument("--max-calls", type=int, default=VOTE_MAX_CALLS,
                        help=f"calls per book at most, one per crop asked (default {VOTE_MAX_CALLS}); a call "
                             "cut off at the token limit is asked again one effort lower, so it can take up "
                             f"to {REQUESTS_PER_CALL} requests")
    parser.add_argument("--workers", type=int, default=4,
                        help="calls in flight at once; match the server's --max-concurrency")
    parser.add_argument("--dry-run", action="store_true", help="count the pairs and calls; ask nothing, write nothing")
    parser.add_argument("--compare", type=Path,
                        help="after voting (or, with --dry-run, on the existing --output), compare the model's "
                             "rulings pair by pair with this rulings file")
    parser.add_argument("--endpoint", default=os.environ.get("PROOFREAD_ENDPOINT", pp.DEFAULT_ENDPOINT))
    parser.add_argument("--model", default=os.environ.get("PROOFREAD_MODEL", pp.DEFAULT_MODEL))
    parser.add_argument("--reasoning-effort", default=os.environ.get("PROOFREAD_EFFORT", pp.DEFAULT_EFFORT))
    parser.add_argument("--max-tokens", type=int, default=16000)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=1800.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    profile_path = arguments.profile.expanduser().resolve()
    if not profile_path.is_file():
        print(f"ERROR no such profile: {profile_path}", file=sys.stderr)
        return 2
    rulings_path = (arguments.output.expanduser().resolve() if arguments.output
                    else profile_path.with_name("variant-rulings.json"))
    effort = None if arguments.reasoning_effort.lower() == "none" else arguments.reasoning_effort
    client = pp.Client(arguments.endpoint, arguments.model, effort, arguments.timeout, arguments.temperature,
                       max_inflight=arguments.workers)
    record = rule_book(client, profile_path, rulings_path, arguments.crops, arguments.max_calls,
                       arguments.workers, arguments.max_tokens, dry_run=arguments.dry_run)
    print(describe(record, rulings_path))
    if arguments.compare and rulings_path.is_file():
        result = compare(rulings_path, arguments.compare.expanduser().resolve())
        for row in result["rows"]:
            votes = " ".join(f"{k}{v}" for k, v in (row.get("votes") or {}).items())
            print(f"  {'/'.join(row['forms'])} ×{row['occurrences']}: model {row['model'] or '-'} "
                  f"other {row['other'] or '-'} ({votes}){' ' + row['reason'] if row.get('reason') else ''}")
        print(json.dumps({"pairs": result["pairs"], "occurrences": result["occurrences"]}, ensure_ascii=False))
    if record is not None and not record.get("dryRun") and not record.get("written"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
