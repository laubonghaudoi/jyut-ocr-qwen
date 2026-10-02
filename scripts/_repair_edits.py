"""Offset edits on page texts, the repair log, the doubts, and the log's
replay (scripts/repair_book.py).

A stage proposes edits against the page texts as they stand when it starts:
each replaces text[start:end] of one page with AFTER, and names the rule or
the question that justifies it and the evidence.  Ledger.apply() takes a
stage's edits in the order proposed; on a page, an edit whose span overlaps
one already taken is not applied - the first proposed wins, and the other
becomes a doubt of kind `conflict` naming both.  Two edits overlap when
their spans share a character, when an insertion (an empty span) falls
strictly inside the other's span, or when two insertions are at one place;
an insertion at the edge of another span does not overlap it and goes first.

Every applied edit is one record of repair-log.jsonl.  A record's offset is
into the page text as it stands just before that record is applied, in log
order, so replay() - the sealed pages plus the log, record by record - gives
the repaired pages; each record's BEFORE must be what the page holds at its
offset, or the replay fails.  Offsets count Python characters (code points).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Iterable, Mapping, Sequence


# The doubt kinds the repair writes (doubts.json); each is described in
# references/long-book-workflow.md (tests/check_documented.py).
DOUBT_KINDS = (
    "look-refused",          # a guard refused the model's answer, or it could not tell
    "look-not-asked",        # a question not asked (--no-model, no crop, no site, the model unreachable)
    "verify-disagrees",      # --verify-sample: the print question reads otherwise than a rule's edit
    "conflict",              # two edits over the same text; the first proposed was applied
    "unit-not-in-scan",      # a contents entry with no unit in the body
    "leaves-missing",        # a jump in the folio sequence inside a run
    "boundary-unverified",   # a page boundary written without a settled label
    "heading-kind-unknown",  # a heading no rule can place
    "gate-failed",           # a rule family off for this book, with its measurement
    "detector-unmatched",    # a lint hit that no rule or question covers
)


class ReplayError(Exception):
    """A log record does not apply to the text it names."""


@dataclass
class Edit:
    """One proposed change: PAGE's text[start:end] becomes AFTER."""
    page: int
    start: int
    end: int
    after: str
    rule: str | None = None
    question: str | None = None
    evidence: Mapping[str, Any] = field(default_factory=dict)
    answer: str | None = None
    crop: str | None = None
    crop_sha256: str | None = None

    def __post_init__(self) -> None:
        if not (self.rule or self.question):
            raise ValueError("an edit names the rule or the question that justifies it")
        if self.start < 0 or self.end < self.start:
            raise ValueError(f"bad span {self.start}:{self.end}")
        if self.question and not (self.crop and self.crop_sha256 and self.answer is not None):
            raise ValueError("an edit from a question carries the answer, the crop and its hash")


def overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    (s1, e1), (s2, e2) = a, b
    if s1 == e1 and s2 == e2:
        return s1 == s2
    if s1 == e1:
        return s2 < s1 < e2
    if s2 == e2:
        return s1 < s2 < e1
    return s1 < e2 and s2 < e1


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


class Ledger:
    """The page texts under repair, the log of applied edits and the doubts."""

    def __init__(self, texts: Mapping[int, str]):
        self.original = dict(texts)
        self.texts = dict(texts)
        self.records: list[dict[str, Any]] = []
        self.doubts: list[dict[str, Any]] = []

    def doubt(self, kind: str, page: int | None, detail: str, **fields: Any) -> dict[str, Any]:
        if kind not in DOUBT_KINDS:
            raise ValueError(f"unknown doubt kind {kind!r}")
        record = {"id": f"U{len(self.doubts) + 1:04d}", "kind": kind, "page": page, "detail": detail, **fields}
        self.doubts.append(record)
        return record

    def apply(self, stage: str, edits: Sequence[Edit]) -> list[dict[str, Any]]:
        """Apply one stage's EDITS (see the module's docstring); returns the
        records written, in log order."""
        taken: dict[int, list[Edit]] = {}
        for edit in edits:
            if edit.page not in self.texts:
                raise ValueError(f"no page {edit.page} under repair")
            text = self.texts[edit.page]
            if edit.end > len(text):
                raise ValueError(f"page {edit.page}: span {edit.start}:{edit.end} past the end ({len(text)})")
            if text[edit.start:edit.end] == edit.after:
                continue
            clash = next((other for other in taken.get(edit.page, [])
                          if overlaps((edit.start, edit.end), (other.start, other.end))), None)
            if clash is not None:
                self.doubt("conflict", edit.page,
                           f"{describe(edit)} overlaps {describe(clash)}; the first proposed was applied",
                           stage=stage, applied=describe_record(clash, text),
                           refused=describe_record(edit, text))
                continue
            taken.setdefault(edit.page, []).append(edit)
        written = []
        for page in sorted(taken):
            text = self.texts[page]
            shift = 0
            pieces = []
            at = 0
            # Insertions at an edge go before the span they touch.
            for edit in sorted(taken[page], key=lambda e: (e.start, e.end)):
                before = text[edit.start:edit.end]
                offset = edit.start + shift
                pieces.append(text[at:edit.start])
                pieces.append(edit.after)
                at = edit.end
                current = "".join(pieces) + text[at:]
                record = {
                    "id": f"E{len(self.records) + 1:04d}",
                    "stage": stage,
                    "page": page,
                    "line": line_of(current, offset),
                    "offset": offset,
                    "before": before,
                    "after": edit.after,
                    "rule": edit.rule,
                    "evidence": dict(edit.evidence),
                    "question": edit.question,
                    "answer": edit.answer,
                    "crop": edit.crop,
                    "cropSha256": edit.crop_sha256,
                }
                self.records.append(record)
                written.append(record)
                shift += len(edit.after) - len(before)
            pieces.append(text[at:])
            self.texts[page] = "".join(pieces)
        return written


def describe(edit: Edit) -> str:
    return f"{edit.rule or edit.question} at {edit.start}:{edit.end}"


def describe_record(edit: Edit, text: str) -> dict[str, Any]:
    return {"rule": edit.rule, "question": edit.question, "start": edit.start, "end": edit.end,
            "before": text[edit.start:edit.end], "after": edit.after}


REQUIRED_FIELDS = ("id", "stage", "page", "line", "offset", "before", "after", "rule", "evidence",
                   "question", "answer", "crop", "cropSha256")


def record_problems(record: Mapping[str, Any]) -> list[str]:
    """What a log record lacks: every field, a rule or a question, and for a
    question its answer, crop and crop hash."""
    name = record.get("id", "?")
    problems = [f"{name}: no field {key}" for key in REQUIRED_FIELDS if key not in record]
    if not (record.get("rule") or record.get("question")):
        problems.append(f"{name}: names neither a rule nor a question")
    if record.get("question") and not (record.get("crop") and record.get("cropSha256")
                                       and record.get("answer") is not None):
        problems.append(f"{name}: a question's record lacks its answer, crop or crop hash")
    if not isinstance(record.get("page"), int):
        problems.append(f"{name}: no page")
    return problems


def replay(original: Mapping[int, str], records: Iterable[Mapping[str, Any]]) -> dict[int, str]:
    """The pages ORIGINAL becomes under RECORDS, applied one by one; a record
    whose BEFORE is not at its offset raises ReplayError."""
    texts = dict(original)
    for record in records:
        page = record["page"]
        if page not in texts:
            raise ReplayError(f"{record.get('id')}: no page {page}")
        text = texts[page]
        offset = record["offset"]
        before = record["before"]
        if not (0 <= offset <= len(text)) or text[offset:offset + len(before)] != before:
            raise ReplayError(f"{record.get('id')}: page {page} does not hold {before!r} at {offset}")
        texts[page] = text[:offset] + record["after"] + text[offset + len(before):]
    return texts


def read_log(lines: Iterable[str]) -> list[dict[str, Any]]:
    return [json.loads(line) for line in lines if line.strip()]


def log_bytes(records: Sequence[Mapping[str, Any]]) -> bytes:
    return "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
                   for record in records).encode("utf-8")
