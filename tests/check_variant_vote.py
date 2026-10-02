#!/usr/bin/env python3
"""Checks of the model's vote on a book's variant pairs (scripts/variant_vote.py), which
replaced a person's ruling: each pair's crops are asked one by one, the forms offered in an
order varied per crop, and the pair is ruled by the majority of its crops; a tie, a pair no
crop could tell and a pair with one vote stay unruled.  A person's rulings are kept; the
vote runs at the end of book_profile.py, and --no-variant-vote leaves everything as it was.

No model, no GPU, no corpus: made-up profiles and books in temporary directories, and a
stand-in model that answers each crop from what the check wrote into the crop.

Usage: python3 tests/check_variant_vote.py   (exits non-zero if any check fails)
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import book_profile as bp  # noqa: E402
import proofread_pages as pp  # noqa: E402
import stand_in  # noqa: E402
import variant_vote as vv  # noqa: E402

failures = 0


def check(name: str, got, want) -> None:
    global failures
    if got != want:
        failures += 1
        print(f"FAIL {name}: got {got!r}, want {want!r}")
    else:
        print(f"ok   {name}")


class Voter:
    """Answers a vote from its crop: a crop's bytes end in what it shows - a form,
    "?" (cannot tell), "junk" (an answer that names neither), "cut" (cut off at the
    token limit on every effort, looping on an answer line) or "error" (the call
    fails)."""

    model, effort = "stand-in", None

    def __init__(self, delay: float = 0.0):
        self.delay = delay
        self.calls: list[tuple[str, str, bytes]] = []
        self.lock = threading.Lock()
        self.inflight = self.peak = 0

    def ask_answering(self, system: str, user_text: str, image_bytes: bytes | None,
                      max_tokens: int, kind: str = "other"):
        assert system == vv.VOTE_SYSTEM and kind == vv.VOTE_KIND, (system[:20], kind)
        with self.lock:
            self.calls.append((kind, user_text, image_bytes))
            self.inflight += 1
            self.peak = max(self.peak, self.inflight)
        try:
            time.sleep(self.delay)
            first = user_text.split("甲) ")[1][0]
            second = user_text.split("乙) ")[1][0]
            shows = image_bytes.decode("utf-8").rsplit(":", 1)[1]
            if shows == "error":
                raise pp.ProofreadError("HTTP 500: stand-in")
            if shows == "junk":
                return "構件：略\n答：丙", {}
            if shows == "cut":
                # What Client.ask_answering hands back when every rung was cut
                # off: the longest partial, marked degraded.
                return (f"構件：略\n答：{min(first, second)}\n" * 50,
                        {"completion_tokens": 64000, "finish_reason": "length", "effort": "xhigh",
                         "degraded": True, "rungsAsked": 4, "rungsCutOff": 4})
            if shows == "?":
                return "構件：略\n答：睇唔清", {}
            return f"構件：略\n答：{'甲' if shows == first else '乙'}", {"completion_tokens": 11, "effort": "xhigh"}
        finally:
            with self.lock:
                self.inflight -= 1


def make_profile(root: Path, pairs) -> Path:
    """A profile whose variant pairs are PAIRS: (form A, form B, occurrences, what each
    crop shows).  Crops are files of made-up bytes; each ends in what it shows."""
    crops = root / "book-profile-crops" / "stamp"
    crops.mkdir(parents=True, exist_ok=True)
    listed = []
    for x, y, occurrences, shows in pairs:
        records = []
        for page, show in enumerate(shows, 1):
            name = f"variant-{ord(x):x}-{ord(y):x}-p{page:04d}.png"
            data = f"{x}{y}:{page}:{show}".encode("utf-8")
            (crops / name).write_bytes(data)
            records.append({"page": page, "crop": name, "cropSha256": pp.sha256_bytes(data),
                            "context": "上文兩字【】下文"})
        listed.append({"engineA": x, "engineB": y, "occurrences": occurrences, "crops": records})
    profile = {"schemaVersion": 2, "cropsDirectory": "book-profile-crops/stamp",
               "sources": {"renders": str(root / "renders")},
               "variants": {"pairs": listed, "note": bp.VARIANT_NOTE_VOTE}}
    path = root / "book-profile.json"
    path.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
    return path


def rulings(root: Path) -> dict:
    return json.loads((root / "variant-rulings.json").read_text(encoding="utf-8"))


def by_forms(entries) -> dict:
    return {"".join(e["forms"]): e for e in entries}


# --- the rule ------------------------------------------------------------------------
check("decide: two of three crops rule the pair", vv.decide({"甲": 2, "乙": 1}, "甲", "乙", 3)[0], "甲")
check("decide: a tie is unruled", vv.decide({"甲": 1, "乙": 1}, "甲", "乙", 3)[0], None)
check("decide: every crop cannot tell - unruled", vv.decide({}, "甲", "乙", 3)[0], None)
check("decide: one vote, two cannot tell - one crop never decides", vv.decide({"甲": 1}, "甲", "乙", 3)[0], None)
check("decide: one crop of one - unruled", vv.decide({"甲": 1}, "甲", "乙", 1)[0], None)
check("decide: two of four answered is no majority", vv.decide({"甲": 2, "乙": 1}, "甲", "乙", 4)[0], None)
check("decide: two of two", vv.decide({"乙": 2}, "甲", "乙", 2)[0], "乙")
check("parse_vote: 甲, 乙, cannot tell, the form itself, neither",
      [vv.parse_vote(t, "麼", "麽") for t in ("答：甲", "略\n答：乙", "答：睇唔清", "答：麽", "答：丙", "")],
      ["麼", "麽", vv.CANNOT_TELL, "麽", "unparsed", "unparsed"])
check("parse_vote: the last answer line counts", vv.parse_vote("答：甲 係錯\n再睇\n答：乙", "麼", "麽"), "麽")
orders = {vv.shown_order("麼", "麽", pp.sha256_bytes(str(n).encode())) for n in range(12)}
check("shown_order: both orders are used across crops", orders, {("麼", "麽"), ("麽", "麼")})
check("shown_order: fixed by the crop", vv.shown_order("麽", "麼", "ab"), vv.shown_order("麼", "麽", "ab"))

# --- a book's vote --------------------------------------------------------------------
PAIRS = [("麼", "麽", 150, ["麽", "麽", "麼"]),      # majority
         ("爲", "為", 140, ["爲", "為", "?"]),        # tie
         ("淸", "清", 130, ["?", "?", "?"]),          # cannot tell
         ("眞", "真", 120, ["眞", "?", "?"]),         # a single vote
         ("旣", "既", 110, ["既", "既", "junk"]),     # an answer that names neither is no vote
         ("囘", "回", 100, ["回", "error", "回"]),    # a failed call is no answer
         ("衞", "衛", 90, ["衞"])]                     # one crop on file: never asked
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    profile = make_profile(root, PAIRS)
    voter = Voter(delay=0.02)
    record = vv.rule_book(voter, profile, workers=3)
    written = rulings(root)
    ruled, unruled = by_forms(written["rulings"]), by_forms(written["modelUnruled"])
    check("vote: pairs ruled and their forms",
          {k: (e["printed"], e["modelPrinted"], e["ruledBy"]) for k, e in ruled.items()},
          {"麼麽": ("麽", "麽", "model"), "旣既": ("既", "既", "model"), "囘回": ("回", "回", "model")})
    check("vote: pairs left unruled", sorted(unruled), sorted(["爲為", "淸清", "眞真", "衞衛"]))
    check("vote: the majority's votes", ruled["麼麽"]["votes"], {"麼": 1, "麽": 2, "cannotTell": 0})
    check("vote: a tie says so", unruled["爲為"]["reason"].startswith("tie"), True)
    check("vote: every crop could not tell", unruled["淸清"]["votes"], {"淸": 0, "清": 0, "cannotTell": 3})
    check("vote: one vote is not enough", "at least 2 must agree" in unruled["眞真"]["reason"], True)
    check("vote: the answer naming neither form counts as answered, not as a vote",
          (ruled["旣既"]["votes"], [c["answer"] for c in ruled["旣既"]["crops"]]),
          ({"旣": 0, "既": 2, "cannotTell": 1}, ["既", "既", "unparsed"]))
    check("vote: the failed call is recorded, not counted",
          ([c["answer"] for c in ruled["囘回"]["crops"]], ruled["囘回"]["votes"]),
          (["回", "error", "回"], {"囘": 0, "回": 2, "cannotTell": 0}))
    check("vote: a pair with one crop is not asked",
          (unruled["衞衛"]["reason"], [c["crop"] for c in unruled["衞衛"]["crops"]]),
          ("1 usable crop(s); at least 2 must agree", []))
    check("vote: one call per crop asked, 18 in all", len(voter.calls), 18)
    evidence = ruled["麼麽"]["crops"][0]
    crop_file = root / evidence["crop"]
    check("vote: each crop's file, hash, order shown and answer are sealed",
          (crop_file.is_file(), pp.sha256_bytes(crop_file.read_bytes()) == evidence["cropSha256"],
           sorted(evidence["shown"]), evidence["answer"], evidence["reply"].endswith("答：甲")
           or evidence["reply"].endswith("答：乙")),
          (True, True, ["麼", "麽"], "麽", True))
    shown = [c["shown"] for e in written["rulings"] + written["modelUnruled"] for c in e["crops"] if "shown" in c]
    check("vote: each crop's tokens and the effort that answered it are sealed",
          (evidence["completionTokens"], evidence["effort"]), (11, "xhigh"))
    check("vote: the forms were offered in both orders across the book's crops",
          {first < second for first, second in shown}, {True, False})
    check("vote: the run is recorded",
          {k: written["modelVote"][k] for k in ("calls", "failedCalls", "pairsRuled", "pairsUnruled",
                                                 "cropsPerPair", "maxCalls", "minimumVotes", "pairsPersonRuled")},
          {"calls": 18, "failedCalls": 1, "pairsRuled": 3, "pairsUnruled": 4, "cropsPerPair": 3,
           "maxCalls": 120, "minimumVotes": 2, "pairsPersonRuled": 0})
    check("vote: ruledBy model at the top", (written["ruledBy"], written["book"]), ("model", str(root / "renders")))
    check("vote: calls ran at most --workers at once, and in parallel", 1 < voter.peak <= 3, True)
    check("vote: the record returned says the file was written", (record["written"], record["pairsRuled"]), (True, 3))
    check("vote: proofreading reads the model's rulings as rulings",
          {frozenset(e["forms"]): pp.variant_ruling_by(e) for e in written["rulings"]},
          {frozenset("麼麽"): "model", frozenset("既旣"): "model", frozenset("回囘"): "model"})

# --- bounds ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    profile = make_profile(root, [("麼", "麽", 9, ["麽"] * 3), ("爲", "為", 8, ["爲"] * 3),
                                  ("淸", "清", 7, ["淸"] * 3)])
    voter = Voter()
    vv.rule_book(voter, profile, crops_per_pair=2, max_calls=5)
    written = rulings(root)
    check("bounds: crops per pair, then calls per book, most frequent pairs first",
          (len(voter.calls), sorted(by_forms(written["rulings"])), by_forms(written["modelUnruled"])["淸清"]["reason"]),
          (4, ["爲為", "麼麽"], "call budget (5 per book) spent"))
    dry = vv.rule_book(Voter(), profile, dry_run=True)
    check("bounds: a dry run counts the calls and asks nothing", (dry["calls"], dry["written"]), (9, False))

# --- a person's rulings ---------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    profile = make_profile(root, [("麼", "麽", 150, ["麽", "麽", "麽"]), ("爲", "為", 140, ["爲", "爲", "爲"]),
                                  ("淸", "清", 130, ["清", "清", "清"]), ("眞", "真", 120, ["眞", "眞", "眞"])])
    person = {"book": "a person's book", "note": "a person's note", "ruledBy": "user (crops)",
              "rulings": [
                  {"forms": ["麽", "麼"], "printed": "麼", "occurrences": 150},
                  # A model ruling a person changed: theirs now.
                  {"forms": ["爲", "為"], "printed": "為", "modelPrinted": "爲", "ruledBy": "model"},
                  # The model's own earlier ruling: voted again.
                  {"forms": ["淸", "清"], "printed": "淸", "modelPrinted": "淸", "ruledBy": "model"},
                  # Not a ruling (no printed form): kept, and the pair is voted on.
                  {"forms": ["眞", "真"], "printed": None}]}
    (root / "variant-rulings.json").write_text(json.dumps(person, ensure_ascii=False), encoding="utf-8")
    voter = Voter()
    vv.rule_book(voter, profile)
    written = rulings(root)
    asked = sorted({c[2].decode("utf-8")[:2] for c in voter.calls})
    check("person: only the pairs no person ruled are asked", asked, ["淸清", "眞真"])
    check("person: their rulings are kept as written, first",
          written["rulings"][:3], [person["rulings"][0], person["rulings"][1], person["rulings"][3]])
    check("person: the model's earlier ruling is replaced by the new vote",
          [(e["forms"], e["printed"], e["ruledBy"]) for e in written["rulings"][3:]],
          [(["淸", "清"], "清", "model"), (["眞", "真"], "眞", "model")])
    check("person: their own top-level words are kept",
          (written["book"], written["note"], written["ruledBy"]), ("a person's book", "a person's note", "user (crops)"))
    check("person: the changed model ruling counts as theirs",
          [pp.variant_ruling_by(e) for e in written["rulings"]], ["person", "person", "person", "model", "model"])
    all_person = {"rulings": [{"forms": list(p[:2]), "printed": p[0]} for p in
                              (("麼", "麽"), ("爲", "為"), ("淸", "清"), ("眞", "真"))]}
    (root / "variant-rulings.json").write_text(json.dumps(all_person, ensure_ascii=False), encoding="utf-8")
    before = (root / "variant-rulings.json").read_bytes()
    voter = Voter()
    check("person: every pair ruled by a person - nothing asked, the file untouched",
          (vv.rule_book(voter, profile), len(voter.calls), (root / "variant-rulings.json").read_bytes() == before),
          (None, 0, True))

# A person rules a pair the model left unruled on that pair's own entry, in
# modelUnruled: it is theirs, and the next vote moves it into the rulings.
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    profile = make_profile(root, [("麼", "麽", 9, ["麽"] * 3), ("爲", "為", 8, ["爲", "為", "?"])])
    vv.rule_book(Voter(), profile)
    document = rulings(root)
    entry = by_forms(document["modelUnruled"])["爲為"]
    entry.update(printed="為", ruledBy="person")
    (root / "variant-rulings.json").write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    voter = Voter()
    vv.rule_book(voter, profile)
    again = rulings(root)
    check("person on modelUnruled: not voted on again, moved into the rulings as theirs",
          (sorted({c[2].decode("utf-8")[:2] for c in voter.calls}),
           [(e["forms"], e["printed"], pp.variant_ruling_by(e)) for e in again["rulings"]],
           [e["forms"] for e in again["modelUnruled"]]),
          (["麼麽"], [(["爲", "為"], "為", "person"), (["麼", "麽"], "麽", "model")], []))
    person_unruled_document = document

# Every call failing (the server down) teaches nothing: the file stays as it was.
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    profile = make_profile(root, [("麼", "麽", 9, ["error"] * 3)])
    record = vv.rule_book(Voter(), profile)
    check("failure: every call failed - not written", (record["written"], (root / "variant-rulings.json").exists()),
          (False, False))

# A reply cut off at the token limit on every effort is no answer, however often it
# repeats an answer line: not a vote, and the crop's evidence says so.
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    profile = make_profile(root, [("麼", "麽", 9, ["cut", "cut", "麽"]), ("爲", "為", 8, ["cut"] * 3)])
    record = vv.rule_book(Voter(), profile)
    written = rulings(root)
    unruled = by_forms(written["modelUnruled"])
    both = {**by_forms(written["rulings"]), **unruled}
    check("no answer: replies cut off on every effort decide nothing",
          ([(e["forms"], e["printed"]) for e in written["rulings"]], sorted(unruled), both["麼麽"]["votes"],
           both["爲為"]["reason"]),
          ([], ["爲為", "麼麽"], {"麼": 0, "麽": 1, "cannotTell": 0}, "no crop was answered"))
    cut = both["麼麽"]["crops"][0]
    check("no answer: the crop says so, with the rungs asked and the tokens spent",
          (cut["answer"], cut.get("degraded"), cut.get("rungsAsked"), cut.get("rungsCutOff"),
           cut.get("noAnswer", "").startswith("no answer: cut off"), cut["completionTokens"]),
          ("no answer", True, 4, 4, True, 64000))
    check("no answer: counted in the run", (record.get("noAnswerCalls"), record["failedCalls"]), (5, 0))
    (root / "variant-rulings.json").unlink()
    profile = make_profile(root, [("麼", "麽", 9, ["cut"] * 3)])
    record = vv.rule_book(Voter(), profile)
    check("no answer: no crop answered - not written",
          (record["written"], (root / "variant-rulings.json").exists()), (False, False))

# --- at the end of book_profile.py ----------------------------------------------------
# Three pages of different text (text repeated on every page is furniture), each with
# the four pairs, engine A reading one form and engine B the other.
OPENINGS = {1: "第一章總論", 2: "第二章各論", 3: "第三章附則"}
# Two more pages, for a book with more pages per pair than the profile keeps crops.
MORE_OPENINGS = {**OPENINGS, 4: "第四章罰則", 5: "第五章施行"}
TEXT_A = "此事爲國家計淸理財政甚麼事都要做到眞實"
TEXT_B = "此事為國家計清理財政甚麽事都要做到真實"


class BookModel(Voter):
    """The profile's other calls answered too; every crop shows engine B's form."""

    def ask_answering(self, system, user_text, image_bytes, max_tokens, kind="other"):
        if system == vv.VOTE_SYSTEM:
            return super().ask_answering(system, user_text, image_bytes, max_tokens, kind)
        self.calls.append((kind, user_text, image_bytes))
        if system == pp.PAIR_SYSTEM:
            return "判定：異體", {}
        if system == pp.ADJUDICATE_SYSTEM:
            return "定案：無\nRESEARCH: no", {}
        return "符號：無\n雙圈：冇\n圈點：冇\n點數：0", {}


def crop_stand_in(render, block, index, run, context=4, pad=0.02, whole_run=None):
    # The crop ends in what it shows: engine B's form at that spot.
    page = int(Path(render).stem.split("-")[1])
    return f"{page}:{index}:{(MORE_OPENINGS[page] + TEXT_B)[index]}".encode("utf-8")


def profile_book(root: Path, extra=()):
    model = BookModel()
    real_client, real_crop = pp.Client, pp.crop_glyph
    pp.Client = lambda *args, **kwargs: model
    pp.crop_glyph = crop_stand_in
    try:
        status = bp.main([str(root / "renders"), str(root / "a"), str(root / "b"),
                          str(root / "book-profile.json"), "--workers", "2", *extra])
    finally:
        pp.Client, pp.crop_glyph = real_client, real_crop
    assert status == 0, status
    return model, json.loads((root / "book-profile.json").read_text(encoding="utf-8"))


def proofread_book(root: Path, overwrite: bool):
    """Phase 3 on the three pages under ROOT's book profile and rulings; returns
    the exit status and each page's status in the run report."""
    real_client = pp.Client
    pp.Client = lambda *args, **kwargs: stand_in.StandIn(census=0)
    try:
        status = pp.main([str(root / "renders"), str(root / "a"), str(root / "out"),
                          "--draft2-directory", str(root / "b"), "--profile", str(root / "book-profile.json"),
                          "--pages", "1-3", "--report", str(root / "report.json"), "--no-adjudicate",
                          *(["--overwrite"] if overwrite else [])])
    finally:
        pp.Client = real_client
    report = json.loads((root / "report.json").read_text(encoding="utf-8"))
    return status, [page["status"] for page in report["pages"]]


def comparable(profile: dict) -> dict:
    out = copy.deepcopy(profile)
    for key in ("generatedAt", "seconds", "cropsDirectory"):
        out.pop(key, None)
    out["variants"].pop("note")
    return out


PAGES = {page: ([stand_in.block(opening + TEXT_A, [0.3, 0.1, 0.4, 0.8])], opening + TEXT_B)
         for page, opening in OPENINGS.items()}
with stand_in.book(PAGES) as root:
    model, on = profile_book(root)
    written = rulings(root)
    check("book_profile: the vote runs at the end, one call per crop",
          [k for k, _, _ in model.calls].count(vv.VOTE_KIND), 12)
    check("book_profile: every pair ruled by the model, engine B's forms",
          sorted((e["printed"], e["ruledBy"]) for e in written["rulings"]),
          [("清", "model"), ("為", "model"), ("真", "model"), ("麽", "model")])
    check("book_profile: the profile says the model rules the pairs", on["variants"]["note"], bp.VARIANT_NOTE_VOTE)
    # Profiled again with the same answers, at another time: the file's own record
    # changes, no ruling does, and the pages sealed under the first vote resume.
    first = rulings(root)
    check("resume: proofread under the model's rulings", proofread_book(root, overwrite=True)[0], 0)
    real_now, times = pp.utc_now, iter(f"2001-01-01T00:00:{n:02d}Z" for n in range(60))
    pp.utc_now = lambda: next(times)
    try:
        profile_book(root)
    finally:
        pp.utc_now = real_now
    again = rulings(root)
    check("resume: the second vote wrote its own record, the same rulings",
          (again["modelVote"]["generatedAt"] != first["modelVote"]["generatedAt"],
           [(e["forms"], e["printed"]) for e in again["rulings"]] == [(e["forms"], e["printed"]) for e in first["rulings"]]),
          (True, True))
    check("resume: a re-profile that changed no ruling leaves the sealed pages current",
          proofread_book(root, overwrite=False), (0, ["skipped-current"] * 3))
    again["rulings"][0]["printed"] = next(f for f in again["rulings"][0]["forms"] if f != again["rulings"][0]["printed"])
    (root / "variant-rulings.json").write_text(json.dumps(again, ensure_ascii=False), encoding="utf-8")
    status, statuses = proofread_book(root, overwrite=False)
    check("resume: a changed ruling still refuses the pages sealed under the old one",
          (status, statuses), (1, ["blocked"] * 3))
    # Switched off on a book voted on before: the pairs no person ruled fall back as
    # without rulings, so the earlier vote's rulings are taken out; the one a person
    # changed above is theirs and stays.
    profile_book(root, ["--no-variant-vote"])
    left = rulings(root)
    check("--no-variant-vote after a vote: the model's rulings are taken out, a person's stay",
          ([(e["forms"], e["printed"], pp.variant_ruling_by(e)) for e in left["rulings"]],
           sorted(k for k in left if k.startswith("model"))),
          ([(["爲", "為"], "爲", "person")], []))
    proofread_book(root, overwrite=True)
    page = json.loads((root / "out" / "page-0001.json").read_text(encoding="utf-8"))
    check("--no-variant-vote after a vote: phase 3 falls back for the pairs no person ruled",
          ([(d["engineA"], d["resolved"], d["resolved_by"]) for d in page["engineDisagreements"]
            if d["resolved_by"].startswith("variant")], "variantRuledByModel" in page),
          ([("爲", "爲", "variant-ruling"), ("淸", "淸", "variant-unruled-engine-A"),
            ("麼", "麼", "variant-unruled-engine-A"), ("眞", "眞", "variant-unruled-engine-A")], False))
    (root / "variant-rulings.json").unlink()
    profile_book(root)
    model, off = profile_book(root, ["--no-variant-vote"])
    check("--no-variant-vote: no vote, and a rulings file the vote alone wrote is gone",
          ([k for k, _, _ in model.calls].count(vv.VOTE_KIND), (root / "variant-rulings.json").exists()), (0, False))
    check("--no-variant-vote: the profile's note as it always was", off["variants"]["note"],
          "which form is printed is ruled per pair by a person in variant-rulings.json "
          "next to this profile; the model is not asked")
    check("--no-variant-vote: the profile is otherwise the one the vote runs after", comparable(off), comparable(on))
    person = {"rulings": [{"forms": ["爲", "為"], "printed": "爲"}]}
    (root / "variant-rulings.json").write_text(json.dumps(person, ensure_ascii=False), encoding="utf-8")
    before = (root / "variant-rulings.json").read_bytes()
    profile_book(root, ["--no-variant-vote"])
    check("--no-variant-vote: a person's rulings file is left byte for byte",
          (root / "variant-rulings.json").read_bytes() == before, True)

# The profile keeps as many crops per pair as the vote asks for; with the vote off it
# keeps what it always kept, whatever --variant-vote-crops says.
with stand_in.book({page: ([stand_in.block(opening + TEXT_A, [0.3, 0.1, 0.4, 0.8])], opening + TEXT_B)
                    for page, opening in MORE_OPENINGS.items()}) as root:
    _, off = profile_book(root, ["--no-variant-vote", "--variant-vote-crops", "5"])
    check("--no-variant-vote: crops per pair as before, whatever --variant-vote-crops says",
          [len(pair["crops"]) for pair in off["variants"]["pairs"]], [bp.VARIANT_CROPS_PER_PAIR] * 4)
    model, on = profile_book(root, ["--variant-vote-crops", "5"])
    check("--variant-vote-crops 5 with the vote on: five crops kept and asked per pair",
          ([len(pair["crops"]) for pair in on["variants"]["pairs"]], [k for k, _, _ in model.calls].count(vv.VOTE_KIND)),
          ([5] * 4, 20))

# --- phase 3: the model's rulings are used like a person's, and said to be the model's ---
PAGE_A = "此事爲國家計淸理財政"
PAGE_B = "此事為國家計清理財政"


def proofread(rulings_document=None, page_a=PAGE_A, page_b=PAGE_B):
    """One page of a book preferring engine A, proofread with RULINGS_DOCUMENT as
    its variant-rulings.json (none if None); returns the record, the page's
    Markdown and the run report."""
    blocks = [stand_in.block(page_a, [0.3, 0.1, 0.4, 0.8])]
    with stand_in.book({1: (blocks, page_b)}, profile={"preferEngine": "A"}) as root:
        if rulings_document is not None:
            (root / "variant-rulings.json").write_text(json.dumps(rulings_document, ensure_ascii=False),
                                                       encoding="utf-8")
        record, markdown = stand_in.run(root, stand_in.StandIn(census=0))[1]
        report = json.loads((root / "report.json").read_text(encoding="utf-8"))
    return record, markdown, report


def variant_rows(record):
    return [(d["engineA"], d["engineB"], d["resolved"], d["resolved_by"]) for d in record["engineDisagreements"]
            if d["resolved_by"].startswith("variant")]


PERSON = {"forms": ["爲", "為"], "printed": "為"}
MODEL = {"forms": ["淸", "清"], "printed": "清", "modelPrinted": "清", "ruledBy": "model",
         "votes": {"淸": 0, "清": 3, "cannotTell": 0}}
record, markdown, report = proofread({"rulings": [PERSON, MODEL]})
check("phase 3: a model ruling is written like a person's", pp.CJK(markdown), "此事為國家計清理財政")
check("phase 3: each variant site says whose ruling decided it", variant_rows(record),
      [("爲", "為", "為", "variant-ruling"), ("淸", "清", "清", "variant-model-ruling")])
check("phase 3: the page lists the pairs the model ruled", record.get("variantRuledByModel"), ["淸|清"])
check("phase 3: the run report says which pairs the model ruled and which a person",
      {k: report["variantRulings"][k] for k in ("person", "model")},
      {"person": [{"pair": "爲|為", "printed": "為"}],
       "model": [{"pair": "淸|清", "printed": "清", "occurrences": 1}]})
# A person's ruling stands over the model's for the same pair, wherever it is in the file.
record, markdown, report = proofread({"rulings": [dict(PERSON, forms=["淸", "清"], printed="淸"), MODEL]})
check("phase 3: a person's ruling stands over the model's for the same pair",
      (variant_rows(record)[1], record.get("variantRuledByModel"), report["variantRulings"]["model"]),
      (("淸", "清", "淸", "variant-ruling"), None, []))
# Two pairs side by side are one segment with two sites: each site the model ruled is
# listed and counted whatever else the segment holds, and the segment's label says
# whose rulings decided it.
record, markdown, report = proofread({"rulings": [MODEL]}, "此事爲淸國家計理財政", "此事為清國家計理財政")
check("phase 3: a segment the model ruled in part - its model site listed and counted",
      (pp.CJK(markdown), variant_rows(record), record.get("variantRuledByModel"), report["variantRulings"]["model"]),
      ("此事爲清國家計理財政", [("爲淸", "為清", "爲清", "variant-partly-ruled-engine-A")], ["淸|清"],
       [{"pair": "淸|清", "printed": "清", "occurrences": 1}]))
record, markdown, report = proofread({"rulings": [PERSON, MODEL]}, "此事爲淸國家計理財政", "此事為清國家計理財政")
check("phase 3: a segment a person and the model ruled - labelled as both, the model's site listed",
      (pp.CJK(markdown), variant_rows(record), record.get("variantRuledByModel")),
      ("此事為清國家計理財政", [("爲淸", "為清", "為清", "variant-person-and-model-ruling")], ["淸|清"]))
record, markdown, report = proofread({"rulings": [MODEL, dict(PERSON, printed="爲", modelPrinted="爲", ruledBy="model")]},
                                     "此事爲淸國家計理財政", "此事為清國家計理財政")
check("phase 3: a segment the model ruled at every site",
      (variant_rows(record), record.get("variantRuledByModel")),
      ([("爲淸", "為清", "爲清", "variant-model-ruling")], ["爲|為", "淸|清"]))
# A person's printed form on a pair the model left unruled decides its sites at once,
# before any vote runs again.
record, markdown, report = proofread(person_unruled_document)
check("phase 3: a person's ruling on a modelUnruled entry is used as theirs",
      (variant_rows(record)[0], report["variantRulings"]["person"]),
      (("爲", "為", "為", "variant-ruling"), [{"pair": "爲|為", "printed": "為"}]))
# Without model rulings nothing new is sealed: the page is the one a person's rulings
# (or none) always made.
person_record, person_markdown, _ = proofread({"rulings": [PERSON, dict(MODEL, ruledBy="person")]})
check("phase 3: a person's rulings only - resolved as before, no model key on the page",
      (variant_rows(person_record), "variantRuledByModel" in person_record),
      ([("爲", "為", "為", "variant-ruling"), ("淸", "清", "清", "variant-ruling")], False))
bare_record, bare_markdown, bare_report = proofread()
check("phase 3: no rulings - the reading preference, the pairs queued, no model key",
      (variant_rows(bare_record), "variantRuledByModel" in bare_record, bare_report["variantQueue"],
       bare_report["variantRulings"]),
      ([("爲", "為", "爲", "variant-unruled-engine-A"), ("淸", "清", "淸", "variant-unruled-engine-A")], False,
       [{"pair": "爲|為", "occurrences": 1}, {"pair": "淸|清", "occurrences": 1}],
       {"file": None, "sha256": "", "fileSha256": "", "person": [], "model": []}))

# --- the sheet: for a person who wants to look; nothing waits for it -----------------
import variant_sheet  # noqa: E402
from PIL import Image  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    profile = make_profile(root, [("麼", "麽", 9, ["麽"] * 2), ("爲", "為", 8, ["爲"] * 2), ("淸", "清", 7, ["?"] * 2)])
    for crop in (root / "book-profile-crops" / "stamp").iterdir():
        Image.new("L", (40, 120), 255).save(crop)
    document = {"rulings": [{"forms": ["爲", "為"], "printed": "爲"},
                            {"forms": ["麼", "麽"], "printed": "麽", "modelPrinted": "麽", "ruledBy": "model",
                             "votes": {"麼": 0, "麽": 2, "cannotTell": 0}}],
                "modelUnruled": [{"forms": ["淸", "清"], "votes": {"淸": 0, "清": 0, "cannotTell": 2}}]}
    (root / "variant-rulings.json").write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    status = variant_sheet.main([str(profile)])
    todo = json.loads((root / "variant-rulings.todo.json").read_text(encoding="utf-8"))
    check("sheet: the model's pairs are shown with its ruling, a person's are not",
          (status, (root / "variant-sheet.png").is_file(),
           [(e["forms"], e["printed"], e["model"]) for e in todo["rulings"]]),
          (0, True, [(["麼", "麽"], None, "麽"), (["淸", "清"], None, None)]))
    check("sheet: it says nothing waits for it", todo["instructions"].startswith("optional, nothing waits"), True)
    document["modelUnruled"][0].update(printed="清", ruledBy="person")
    (root / "variant-rulings.json").write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    variant_sheet.main([str(profile)])
    todo = json.loads((root / "variant-rulings.todo.json").read_text(encoding="utf-8"))
    check("sheet: a pair a person ruled on its modelUnruled entry is left out as theirs",
          [e["forms"] for e in todo["rulings"]], [["麼", "麽"]])

# --- the skill's text: no step waits for a person to rule a variant -----------------
ROOT = Path(__file__).resolve().parents[1]
skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
workflow = (ROOT / "references" / "long-book-workflow.md").read_text(encoding="utf-8")
check("SKILL.md: the vote, its switch and bounds are described",
      [name for name in ("variant_vote.py", "--no-variant-vote", "--variant-vote-crops", "--variant-vote-calls",
                         "ruledBy: model", "modelUnruled") if name not in skill], [])
check("SKILL.md: no step hands the variant sheet to a person or waits for a ruling",
      [phrase for phrase in ("代人裁", "交畀佢裁", "逐對由人裁", "填好「printed」", "留畀人裁") if phrase in skill], [])
check("long-book-workflow.md: what phase 3 seals for the model's rulings",
      [name for name in ("variant-model-ruling", "variant-person-and-model-ruling", "variantRuledByModel",
                         "variantRulings", "modelUnruled")
       if name not in workflow], [])

print("FAILED" if failures else "all variant-vote checks passed")
sys.exit(1 if failures else 0)
