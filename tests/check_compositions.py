#!/usr/bin/env python3
"""Offline checks of where round 3's features meet, merged from three branches.

No model, no GPU, no corpus: made-up pages and books (tests/stand_in.py), the
real client asking a model server in this process that answers from the
request (stand_in.Served), and stores in temporary directories.

- Switch C4 (--folio-furniture) and tables: a table block is never in the
  running-head band (furniture_band).  A label only engine B read that D26
  sets in a blank of engine A's grid, and a figure one engine missed in a
  table, are asked of 裁決 with the switch on, as with it off, even where the
  table is small and beside the running head in its row; a folio beside it is
  still written as nothing.
- Switch C1 (--census-confirms-engine-a) and the table-edge text: the text
  written beside a table (engine B's title above it, with its marks) is the
  same with C1 on as off, and sealed alike; no census or punctuation pass
  reads a table block, and the bracket rule writes only the punctuated
  blocks, so C1's kept tiles and its ordered brackets stay in the prose.
  The edge text writes each engine's marks in the order written, as C1
  does: brackets with no character between them (a bracketed Arabic
  numeral, empty brackets at the table's edge) come out in order, not
  backwards or with one bracket.
- Switch R2-C (--top-rung-caps) and the pair-class store: an answer a lower
  rung gave after the cap cut the first rung is kept under a key that holds
  the cap, so a client without the cap asks afresh and one with it reads it
  back; a reply cut on every rung, the cut at the cap included, is not kept.
- The padding of images too narrow for the server and whatever sends images:
  both rungs of a ladder R2-C's cap cut send the image padded and the ledger
  says so on each; request_body is the body ask() sends; R2-C's note names
  the question as the caller asked it; the variant vote's crops go padded,
  and its usage counts them.

Usage:
    python3 tests/check_compositions.py
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _pair_cache as pc  # noqa: E402
import proofread_pages as pp  # noqa: E402
import stand_in  # noqa: E402
import variant_vote as vv  # noqa: E402

failures = 0
SCRATCH = Path(tempfile.mkdtemp(prefix="compositions-check-"))
# Nothing here may touch the store of the machine this runs on.
os.environ[pc.PATH_ENV] = str(SCRATCH / "never-used.jsonl")
os.environ.pop(pc.TAG_ENV, None)


def check(name: str, got, want) -> None:
    global failures
    if got != want:
        failures += 1
        print(f"FAIL {name}: got {got!r}, want {want!r}")
    else:
        print(f"ok   {name}")


def html(rows: list[list[str]]) -> str:
    return "<table>" + "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows) + "</table>"


def png(image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


# --- C4 and tables ---------------------------------------------------------------------

def printed_table(grid: list[list[str]], box: list[float], size=(4000, 5600)):
    """A render (4000 x 5600, so a table a few lines high is measured on
    enough pixels) of a ruled table laid out as GRID in BOX: a rule at each
    column's and row's edges and a bar of ink for each non-empty cell."""
    from PIL import Image, ImageDraw
    image = Image.new("L", size, 255)
    draw = ImageDraw.Draw(image)
    x0, y0, width, height = box[0] * size[0], box[1] * size[1], box[2] * size[0], box[3] * size[1]
    rows, cols = len(grid), len(grid[0])
    cw, rh = width / cols, height / rows
    for c in range(cols + 1):
        draw.rectangle([x0 + c * cw - 2, y0, x0 + c * cw + 2, y0 + height], fill=0)
    for r in range(rows + 1):
        draw.rectangle([x0, y0 + r * rh, x0 + width, y0 + r * rh + 2], fill=0)
    for r, row in enumerate(grid):
        for c, text in enumerate(row):
            if pp.CJK(text):
                draw.rectangle([x0 + c * cw + 0.3 * cw, y0 + r * rh + 0.35 * rh,
                                x0 + c * cw + 0.7 * cw, y0 + r * rh + 0.65 * rh], fill=0)
    return image


HEAD = "某省財政說明書歲入部"
BODY = ["天地玄黃宇宙洪荒日月盈昃辰宿列張", "寒來暑往秋收冬藏閏餘成歲律呂調陽"]
# A small table printed in the running head's row, at the top of the page.
TABLE_BOX = [0.55, 0.015, 0.40, 0.05]
PRINTED = [["甲", "一", "二"], ["乙", "三", ""], ["丙", "四", "五"]]


def head_page(a_grid, b_grid, folio: bool = False):
    """A horizontal page: the running head (the profile's) and, when FOLIO, a
    folio only engine A read, as a row at the top; a small table in that row;
    two lines of body below."""
    blocks = [stand_in.block(HEAD, [0.05, 0.02, 0.40, 0.04], "header"),
              *([stand_in.block("七", [0.47, 0.02, 0.04, 0.04], "number")] if folio else []),
              stand_in.block(html(a_grid), TABLE_BOX, "table"),
              stand_in.block(BODY[0], [0.05, 0.10, 0.90, 0.05], "text"),
              stand_in.block(BODY[1], [0.05, 0.20, 0.90, 0.05], "text")]
    return blocks, HEAD + "\n" + html(b_grid) + "\n" + BODY[0] + "\n" + BODY[1]


def run_head_page(blocks, b_text, extra):
    """The page with 裁決 answering the reading one engine read is printed."""
    model = stand_in.StandIn(census=0, judge=lambda a, b: b or a or "無")
    with stand_in.book({1: (blocks, b_text)}, profile={"layout": {"runningHeads": [HEAD]}}) as root:
        printed_table(PRINTED, TABLE_BOX).save(root / "renders" / "page-0001.png")
        record, markdown = stand_in.run(root, model, extra=extra)[1]
    return record, markdown


def c4_entries(record):
    return [(c["engineA"], c["engineB"], c["evidence"]["blocks"]) for c in record["decisionChanges"]
            if c["decision"] == "C4"]


def table_of(markdown: str):
    found = pp._tables.find_tables(markdown)
    return found[0].grid() if found else None


def check_c4_and_tables() -> None:
    # The band on its own: a small table in the running head's row is not the
    # band's; a text block with the same box and text is.
    heads = type("Arguments", (), {"profile_data": {"layout": {"runningHeads": [HEAD]}}})()
    row = [{"text": HEAD, "box": [0.05, 0.02, 0.40, 0.04], "label": "header"},
           {"text": html(PRINTED), "box": TABLE_BOX, "label": "table"},
           {"text": "甲一二", "box": TABLE_BOX, "label": "text"}]
    check("band: a table block in the running head's row is not the band's",
          pp.furniture_band(row, [HEAD], heads), {0: "running head", 2: "row of block 0"})

    # D26: engine A missed the label 乙, engine B read it and moved the last
    # column up; the print shows engine A's grid, and 乙 goes into its blank,
    # to be asked of 裁決 as engine B's reading alone.
    a_grid = [["甲", "一", "二"], ["", "三", ""], ["丙", "四", "五"]]
    b_grid = [["甲", "一", "二"], ["乙", "三", "五"], ["丙", "四", ""]]
    blocks, b_text = head_page(a_grid, b_grid)
    off, off_md = run_head_page(blocks, b_text, [])
    on, on_md = run_head_page(blocks, b_text, ["--folio-furniture"])
    check("D26 in the band's row: engine A's grid followed, 乙 set in its blank",
          [(c["evidence"]["followed"], c["evidence"]["setInBlanksOfA"]) for c in on["decisionChanges"]
           if c["decision"] == "D26"], [("A", ["乙"])])
    check("D26 in the band's row, C4 on: 乙 asked of 裁決, not written as nothing",
          ([(a["draft_reading"], a["writer_reading"]) for a in on["adjudications"]], c4_entries(on)),
          ([("", "乙")], []))
    check("D26 in the band's row, C4 on: the table as printed", table_of(on_md), PRINTED)
    check("D26 in the band's row: the page as with C4 off", on_md, off_md)

    # A table the engines read in one grid, a figure engine B missed: with C4
    # on it is asked, and the table keeps it; a folio beside the running head,
    # which engine B missed too, is still written as nothing.
    b_grid = [["甲", "一", "二"], ["乙", "", ""], ["丙", "四", "五"]]
    blocks, b_text = head_page(PRINTED, b_grid, folio=True)
    off, off_md = run_head_page(blocks, b_text, [])
    on, on_md = run_head_page(blocks, b_text, ["--folio-furniture"])
    check("a figure one engine missed in the band's row, C4 on: asked, the folio not",
          ([(a["draft_reading"], a["writer_reading"]) for a in on["adjudications"]], c4_entries(on)),
          ([("三", "")], [("七", "", [1])]))
    check("a figure one engine missed in the band's row, C4 on: the table keeps it", table_of(on_md), PRINTED)
    check("a figure one engine missed, C4 off: the folio asked too",
          sorted((a["draft_reading"], a["writer_reading"]) for a in off["adjudications"]),
          [("七", ""), ("三", "")])
    check("a figure one engine missed: the table alike on and off", table_of(off_md), table_of(on_md))


# --- C1 and the table-edge text ----------------------------------------------------------

GRID = [["物名", "件數"], ["黑板", "二"], ["粉筆", "十"]]
PROSE_A = "右表所列，各件均係本年添置之物。(2)其價值另表詳之。"
PROSE_B = "右表所列各件均係本年添置之物二其價值另表詳之"
TITLE_B = "某處學堂器具表（單位件）"
# A title whose brackets hold no character: a bracketed Arabic numeral (the
# merged text holds CJK characters alone, so the numeral is not written) and
# empty brackets at the table's edge.
TITLE_NUMBERED_B = "第(2)某處學堂器具表（）"


def edge_page(extra, title=TITLE_B):
    """A table and, below it, engine A's prose block (its marks and a
    numbered head 。(2), engine B reading the numeral as a character); engine
    B read a title (TITLE) with its marks above the table, at the page's
    start, which the table block's span holds.  The census counts engine A's places on the
    prose; the punctuator answers engine A's marks."""
    blocks = [stand_in.block(html(GRID), [0.1, 0.1, 0.8, 0.5], "table"),
              stand_in.block(PROSE_A, [0.1, 0.7, 0.8, 0.2], "text")]
    b_text = title + "\n" + html(GRID) + "\n" + PROSE_B
    model = stand_in.StandIn(census="5\n雙圈：0", judge=lambda a, b: b or a or "無",
                             punctuate=lambda span: "右表所列，各件均係本年添置之物。二其價值另表詳之。")
    real = pp.leader_count
    # The dot runs measured on the crop: none (a blank made-up crop).
    pp.leader_count = lambda crop: 0
    try:
        with stand_in.book({1: (blocks, b_text)}) as root:
            record, markdown = stand_in.run(root, model, extra=extra)[1]
    finally:
        pp.leader_count = real
    return record, markdown, model.kinds()


def from_table_edge(markdown: str, title: str = TITLE_B) -> str:
    """The page from the table's edge text (the title's line, TITLE as
    written) to the table's end."""
    at = markdown.find(title)
    found = pp._tables.find_tables(markdown)
    return markdown[at:found[0].end] if at >= 0 and found else ""


def check_c1_and_table_edge_text() -> None:
    off, off_md, off_kinds = edge_page([])
    on, on_md, on_kinds = edge_page(["--census-confirms-engine-a"])
    check("C1 on: the prose tile keeps engine A's marks, no punctuate call",
          ([(p["block"], p.get("engineAKept")) for p in on["punctuationPasses"]], "punctuate" in on_kinds),
          ([(1, True)], False))
    check("C1 on: the prose as engine A printed it, the numbered head's brackets in order",
          on_md.rstrip("\n").split("\n")[-1], "右表所列，各件均係本年添置之物。（二）其價值另表詳之。")
    check("C1's entries are the prose block's, none the table block's",
          sorted({c["block"] for c in on["decisionChanges"] if c["decision"] == "C1"}), [1])
    check("the edge text written once before the table, with engine B's marks, C1 on",
          (on_md.count(TITLE_B), table_of(on_md)), (1, GRID))
    check("the edge text and the table: the same with C1 on as off", from_table_edge(on_md), from_table_edge(off_md))
    check("the edge text is there at all", bool(from_table_edge(off_md)), True)
    edge = lambda record: [c for c in record["decisionChanges"] if c["rule"] == "table-edge-text"]  # noqa: E731
    check("the table-edge-text entry: the same with C1 on as off", edge(on), edge(off))
    check("the table-edge-text doubt: the same with C1 on as off",
          [d for d in on["doubts"] if d["kind"] == "table-edge-text"],
          [d for d in off["doubts"] if d["kind"] == "table-edge-text"])
    old, old_md, _ = edge_page(["--census-confirms-engine-a", "--no-table-edge-text"])
    check("--no-table-edge-text with C1: the title dropped as before, the prose kept",
          (TITLE_B in old_md, [p.get("engineAKept") for p in old["punctuationPasses"]]), (False, [True]))
    # Brackets with no character between them: beside the table they are
    # written in the order engine B wrote them, as C1 writes the numbered
    # head's in the prose (marks_as_written) - with C1 on as off.  Before,
    # the title came out 第）（某處學堂器具表）, either way.
    written = "第（）某處學堂器具表（）"
    off, off_md, _ = edge_page([], TITLE_NUMBERED_B)
    on, on_md, _ = edge_page(["--census-confirms-engine-a"], TITLE_NUMBERED_B)
    check("a title whose brackets hold no character: written in order beside the table, C1 off",
          (from_table_edge(off_md, written).split("\n")[0], table_of(off_md)), (written, GRID))
    check("a title whose brackets hold no character: the edge text and the table the same with C1 on as off",
          from_table_edge(on_md, written), from_table_edge(off_md, written))
    check("a title whose brackets hold no character: the table-edge-text entry as written, C1 on as off",
          ([b["written"] for c in edge(on) for b in c["evidence"]["beside"]], edge(on)),
          ([written], edge(off)))
    check("C1 on with that title: the prose's numbered head still in order",
          on_md.rstrip("\n").split("\n")[-1], "右表所列，各件均係本年添置之物。（二）其價值另表詳之。")


# --- R2-C and the pair-class store -------------------------------------------------------

class Transport(pp.Client):
    """The real client (its ladder, its body, its ledger, its transport)
    asking a model server in this process (stand_in.Served) that answers from
    the request: a question needs NEEDS[(system, user)] or DEFAULT completion
    tokens at xhigh and LOWER below it, cut ("length") where max_tokens is
    less; xhigh answers XHIGH(user), a lower rung LOWER_ANSWER(user).  Every
    body sent is kept in SENT, as the server read it.  Over HTTP, because the
    pair-class store keeps only answers that came that way."""

    def __init__(self, caps=None, needs=None, default=(2000, 500), xhigh=None, lower=None):
        super().__init__(stand_in.served().endpoint(self.respond), "stand-in", "xhigh", 30, top_rung_caps=caps)
        self.needs = needs or {}
        self.default = default
        self.xhigh = xhigh or (lambda user: "判定：不同")
        self.lower = lower or (lambda user: "判定：異體")
        self.sent: list[dict] = []

    def respond(self, body):
        self.sent.append(body)
        user = body["messages"][1]["content"][0]["text"]
        top = body.get("reasoning_effort") == "xhigh"
        need = self.needs.get(user, self.default)[0 if top else 1]
        if body["max_tokens"] < need:
            return stand_in.reply("", "length", body["max_tokens"])
        return stand_in.reply((self.xhigh if top else self.lower)(user), "stop", need)


def new_process() -> None:
    """What a new process starts with: no pair classified in memory."""
    pp._PAIR_CACHE.clear()
    pp._PAIR_ORIGIN.clear()


def classify(store, client, a, b):
    new_process()
    previous = pp.use_pair_store(store)
    try:
        return pp.classify_pair(client, a, b, max_tokens=4000)
    finally:
        pp.use_pair_store(previous)


def check_r2c_and_pair_store() -> None:
    path = SCRATCH / "pairs.jsonl"
    server = lambda client: ({"stand-in": "server-1"}, None)  # noqa: E731
    caps = {"pair-class": 1000}
    # Capped: xhigh would finish at 2,000 tokens, the cap cuts it at 1,000 and
    # medium answers 異體.
    capped = Transport(caps)
    store = pc.PairStore(path, server)
    check("capped: the rung below the cap answers", classify(store, capped, "甲", "乙"), "variant")
    check("capped: each order cut at the cap, then medium",
          [(b["reasoning_effort"], b["max_tokens"]) for b in capped.sent],
          [("xhigh", 1000), ("medium", 4000), ("xhigh", 1000), ("medium", 4000)])
    kept = [r for r in pc.JsonLines(path).read_new() if r.get("type") == "answer"]
    check("capped: both answers kept, marked with the cap and the rung that answered",
          [(r["answeredAtEffort"], r.get("topRungCap")) for r in kept], [("medium", 1000), ("medium", 1000)])
    # Without the cap: not the capped answers - asked afresh, xhigh answers.
    plain = Transport()
    store = pc.PairStore(path, server)
    check("uncapped, same server: asked afresh, xhigh's answer", classify(store, plain, "甲", "乙"), "different")
    check("uncapped: two requests, none from the store",
          (len(plain.sent), store.summary()["answersFromStore"], store.summary()["answersKept"]), (2, 0, 2))
    # The cap again: its own answers read back, nothing asked.
    again = Transport(caps)
    store = pc.PairStore(path, server)
    check("capped again: from the store", (classify(store, again, "甲", "乙"), len(again.sent),
                                           store.summary()["answersFromStore"]), ("variant", 0, 2))
    # Another cap is another key.
    other = Transport({"pair-class": 1500})
    store = pc.PairStore(path, server)
    classify(store, other, "甲", "乙")
    check("another cap: asked afresh", (len(other.sent), store.summary()["answersFromStore"]), (4, 0))
    # Cut on every rung, the cap's cut included: degraded, not kept.
    never = 10 ** 9
    cut = Transport(caps, needs={f"甲「{x}」 乙「{y}」": (never, never) for x, y in (("丙", "丁"), ("丁", "丙"))})
    store = pc.PairStore(path, server)
    classify(store, cut, "丙", "丁")
    check("cut on every rung under the cap: not kept",
          (store.summary()["answersKept"], store.summary()["answersNotKept"] >= 2), (0, True))
    check("cut on every rung under the cap: every rung asked, the first at the cap",
          [(b.get("reasoning_effort"), b["max_tokens"]) for b in cut.sent[:len(pp.Client.EFFORT_LADDER)]],
          [(effort, 1000 if not n else 4000) for n, effort in enumerate(pp.Client.EFFORT_LADDER)])
    # A kind the client does not cap: its key is as without the switch.
    check("a kind not capped: the same key as without the switch",
          pc.PairStore(path, server).key(Transport({"adjudicate": 1000}), "s", "sys", "u", 4000, "pair-class", 0, {}),
          pc.PairStore(path, server).key(Transport(), "s", "sys", "u", 4000, "pair-class", 0, {}))


# --- the padding and what sends images ---------------------------------------------------

def image_of(body: dict):
    from PIL import Image
    parts = [c for c in body["messages"][1]["content"] if c.get("type") == "image_url"]
    if not parts:
        return None
    return Image.open(io.BytesIO(base64.b64decode(parts[0]["image_url"]["url"].split(",", 1)[1])))


def aspect(image) -> float:
    return max(image.size) / min(image.size)


def check_padding_and_senders() -> None:
    from PIL import Image, ImageDraw
    thin = Image.new("L", (4, 1000), 236)
    ImageDraw.Draw(thin).rectangle((1, 50, 2, 950), fill=20)
    crop = png(thin)
    limit = pp.MEDIA_ASPECT_LIMIT

    # R2-C's ladder: the first rung cut at the cap, the next answering; both
    # requests carry the crop padded, and the ledger marks both.
    client = Transport({"adjudicate": 1000}, xhigh=lambda u: "定案：甲", lower=lambda u: "定案：乙")
    ledger: list[dict] = []
    notes: list[dict] = []
    ledger_token, notes_token = pp._CALL_LEDGER.set(ledger), pp._EARLY_CUTS.set(notes)
    try:
        text, metrics = client.ask_answering(pp.ADJUDICATE_SYSTEM, "甲) 某\n乙) 某", crop, 4000, kind="adjudicate")
    finally:
        pp._CALL_LEDGER.reset(ledger_token)
        pp._EARLY_CUTS.reset(notes_token)
    sizes = [image_of(body).size for body in client.sent]
    check("R2-C's ladder: the cap's cut, then medium", ([b["reasoning_effort"] for b in client.sent], text),
          (["xhigh", "medium"], "定案：乙"))
    check("R2-C's ladder: both rungs send the crop padded to the limit",
          [aspect(image_of(body)) <= limit and size[1] == 1000 for body, size in zip(client.sent, sizes)],
          [True, True])
    check("R2-C's ladder: the ledger marks both padded, the first cut at the cap",
          [(row["padded"], row.get("topRungCap"), row.get("earlyCut")) for row in ledger],
          [(True, 1000, True), (True, None, None)])
    check("R2-C's ladder: the summary counts both", pp.summarize_calls(ledger)["adjudicate"]["padded"], 2)
    check("R2-C's note names the question as asked, the crop as cut (not as padded)",
          [n["questionSha256"] for n in notes],
          [hashlib.sha256(pp.ADJUDICATE_SYSTEM.encode() + b"\0" + "甲) 某\n乙) 某".encode() + b"\0" + crop).hexdigest()])
    check("request_body: the body ask() sends, image padded",
          client.request_body(pp.ADJUDICATE_SYSTEM, "甲) 某\n乙) 某", crop, 4000, effort_override="medium"),
          client.sent[1])

    # The variant vote's crops: one of three too narrow; each sent padded, and
    # the vote's usage counts it.
    root = SCRATCH / "vote"
    crops = root / "crops"
    crops.mkdir(parents=True)
    records = []
    for page, image in enumerate([thin, Image.new("L", (60, 60), 255), Image.new("L", (80, 40), 255)], 1):
        name = f"variant-p{page:04d}.png"
        data = png(image)
        (crops / name).write_bytes(data)
        records.append({"page": page, "crop": name, "cropSha256": pp.sha256_bytes(data), "context": "上文【】下文"})
    profile = {"schemaVersion": 2, "cropsDirectory": "crops", "sources": {"renders": str(root / "renders")},
               "variants": {"pairs": [{"engineA": "麼", "engineB": "麽", "occurrences": 9, "crops": records}]}}
    (root / "book-profile.json").write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
    voter = Transport(xhigh=lambda u: "構件：略\n答：甲", default=(300, 300))
    record = vv.rule_book(voter, root / "book-profile.json", workers=1)
    shapes = sorted(image_of(body).size for body in voter.sent)
    check("variant vote: every crop sent within the limit",
          [max(s) / min(s) <= limit for s in shapes], [True, True, True])
    check("variant vote: the narrow crop padded, the others as given",
          shapes, sorted([(10, 1000), (60, 60), (80, 40)]))
    check("variant vote: its usage counts the padded crop", (record["usage"]["n"], record["usage"]["padded"]), (3, 1))


def main() -> int:
    check_c4_and_tables()
    check_c1_and_table_edge_text()
    check_r2c_and_pair_store()
    check_padding_and_senders()
    print(f"\n{'FAIL' if failures else 'ok'}: {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
