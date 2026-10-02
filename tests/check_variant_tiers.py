#!/usr/bin/env python3
"""Offline checks of the two variant layers: the user's rulings, then OpenCC.

No model, no GPU, no corpus.  The pairs are the ones the layers were checked
on when OpenCC's allograph list was adopted: the user's list decides first,
either way; OpenCC's allographs are acceptable where the user has not ruled;
and nothing joins a pair the user ruled apart.

Usage:
    python3 tests/check_variant_tiers.py
"""

from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import proofread_pages as pp  # noqa: E402
import run_regression as rr  # noqa: E402

UPSTREAM_SHA256 = "edd6b79bb319996d54c5d68c99f12bd4bcf66312032e09b684d9da91664acd36"


def check_vendored_copy() -> None:
    raw = pp.ALLOGRAPHS.read_bytes()
    header, marker, body = raw.partition(b"#---- upstream below ----\n")
    assert marker, "the vendored list lost its header separator"
    assert hashlib.sha256(body).hexdigest() == UPSTREAM_SHA256, "the vendored list was edited"
    assert UPSTREAM_SHA256.encode() in header, "the header no longer names the upstream hash"
    print("vendored list: byte-identical to the pinned upstream file")


def check_user_first() -> None:
    classes = json.loads(pp.VARIANT_LIST.read_text(encoding="utf-8"))["classes"]
    rejected = [c["forms"] for c in classes if not c["acceptable"]]
    assert rejected, "the user's list has no rejected pair to test with"
    for forms in rejected:
        for a, b in itertools.combinations(forms, 2):
            assert pp.classify_pair(None, a, b) == "different", (a, b)
            assert pp.variant_source(a, b) == "user", (a, b)
            assert a.translate(rr.FOLD) != b.translate(rr.FOLD), f"{a}/{b} folded together"
    # A pair the user accepted is a variant whatever OpenCC says.
    assert pp.classify_pair(None, "即", "卽") == "variant"
    assert pp.variant_source("即", "卽") == "user"
    print(f"user first: {len(rejected)} rejected pair(s) stay apart in merging and scoring")


def check_opencc_layer() -> None:
    # 㑹/會 is on OpenCC's list and not on the user's.
    assert frozenset("㑹會") in pp.opencc_allographs()
    assert pp.variant_source("㑹", "會") == "opencc"
    assert pp.classify_pair(None, "㑹", "會") == "variant"
    assert "㑹".translate(rr.FOLD) == "會".translate(rr.FOLD)
    assert "㑹".translate(rr.USER_FOLD) != "會".translate(rr.USER_FOLD)
    # Pairs dictionaries and the model were measured to get wrong are on neither list.
    for a, b in ("刺剌", "着著", "已巳"):
        assert pp.variant_source(a, b) is None, (a, b)
        assert pp.classify_pair(None, a, b) == "unknown", (a, b)
    print("OpenCC layer: allographs accepted where the user has not ruled; known false pairs untouched")


def check_scoring_labels() -> None:
    golden = "會議即日開始"
    output = "㑹議卽日開始"
    metrics = rr.score_golden_page(golden, [(1, output)])
    assert metrics["errors"] == 0, metrics["edits"]
    assert metrics["acceptableSwaps"] == 2 and metrics["acceptableSwapsOpencc"] == 1, metrics
    labels = sorted(e["label"] for e in metrics["edits"])
    assert labels == ["acceptable", "acceptable-opencc"], labels
    print("scoring: a swap only OpenCC accepts is counted and labelled apart")


def check_user_overrides_opencc(tmp: Path) -> None:
    listing = tmp / "list.json"
    groups = tmp / "groups.txt"
    groups.write_text("# header\n甲乙\n丙丁戊\n", encoding="utf-8")
    # Ruling an OpenCC pair apart, including one pair inside a longer group,
    # keeps it apart in scoring; the rest of the group still folds.
    listing.write_text(json.dumps({"classes": [
        {"forms": ["甲", "乙"], "acceptable": False},
        {"forms": ["丙", "戊", "己"], "acceptable": False}]}), encoding="utf-8")
    table = rr._fold_table(listing, groups)
    fold = lambda s: s.translate(table)
    assert fold("甲") != fold("乙"), "an OpenCC pair the user ruled apart was folded"
    assert fold("丙") != fold("戊"), "a pair inside a rejected class of three was folded"
    assert fold("丙") == fold("丁"), "the rest of the OpenCC group should still fold"
    # A user list that accepts and rejects the same pair is a contradiction.
    listing.write_text(json.dumps({"classes": [
        {"forms": ["甲", "乙"], "acceptable": True},
        {"forms": ["乙", "甲"], "acceptable": False}]}), encoding="utf-8")
    try:
        rr._fold_table(listing, groups)
    except SystemExit as error:
        assert "甲/乙" in str(error) or "乙/甲" in str(error), error
    else:
        raise AssertionError("a self-contradicting user list loaded without complaint")
    print("precedence: the user's rejection overrides OpenCC; a self-contradicting list stops the run")


def check_assertions_stay_on_user_layer() -> None:
    # A person's ruling on a form (contains 會) is not met by an OpenCC allograph.
    assert rr.user_fold("會") not in rr.user_fold("㑹議")
    assert rr.opencc_only("會", "㑹議"), "the failure should say OpenCC would accept it"
    assert rr.opencc_only("會", "開議") == ""
    print("assertions: an OpenCC-only match fails and says so")


if __name__ == "__main__":
    import tempfile
    check_vendored_copy()
    check_user_first()
    check_opencc_layer()
    check_scoring_labels()
    check_assertions_stay_on_user_layer()
    with tempfile.TemporaryDirectory() as directory:
        check_user_overrides_opencc(Path(directory))
    print("all variant-layer checks passed")
