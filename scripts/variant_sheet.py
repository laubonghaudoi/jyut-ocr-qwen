#!/usr/bin/env python3
"""Show a book profile's variant pairs, and the model's rulings on them, to a person who wants to look.

Which of two forms of one character a book prints (粵 or 粤, 既 or 旣) is ruled
once per pair, for the whole book, by the model's vote over the pair's crops
at the end of the book profile (variant_vote.py).  Nothing waits for a person;
this is for one who wants to see the crops, and perhaps overrule the model.
It writes, next to the profile:

- variant-sheet.png: one row per pair no person has ruled, most frequent
  first - the two forms, how often the engines disagree on it in this book,
  the model's ruling and votes (or why it left the pair unruled), and crops
  of the printed glyph from different pages;
- variant-rulings.todo.json: the same pairs, each with the model's ruling
  ("model"), for reference.  To overrule the model on a pair, set its printed
  form in variant-rulings.json and its ruledBy to person: on its entry in
  rulings, or in modelUnruled for a pair the model left unruled.

Pairs a person has ruled are left out of the sheet.

    python3 scripts/variant_sheet.py BOOK/book-profile.json [--top 20]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import variant_vote  # noqa: E402
from proofread_pages import variant_person_unruled, variant_ruling_by  # noqa: E402

# Traditional-form faces first: a Simplified or Japanese face draws some pairs
# (内/內, 既/旣) identically, and a face without the glyph draws a box.
# I.Ming is kept only for coverage: it draws both members of many pairs in the
# same inherited shape (真 as 眞), which is exactly what the sheet must show apart.
FONT_CANDIDATES = [
    ("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc", "TC"),
    ("~/.local/share/fonts/I.Ming-8.10.ttf", None),
    ("/usr/share/fonts/truetype/arphic/uming.ttc", None),
    ("/System/Library/Fonts/Supplemental/Songti.ttc", "TC"),
    ("/System/Library/Fonts/PingFang.ttc", "TC"),
]


def load_fonts(size: int) -> list:
    from PIL import ImageFont
    fonts = []
    for path, region in FONT_CANDIDATES:
        path = str(Path(path).expanduser())
        for index in range(12 if path.endswith(".ttc") else 1):
            try:
                font = ImageFont.truetype(path, size, index=index)
            except OSError:
                break
            if region is None or region in font.getname()[0].split():
                fonts.append(font)
                break
    return fonts or [ImageFont.load_default()]


def glyph_bytes(font, char: str) -> bytes:
    from PIL import Image, ImageDraw
    image = Image.new("L", (int(font.size * 1.5), int(font.size * 1.5)), 0)
    ImageDraw.Draw(image).text((0, 0), char, font=font, fill=255)
    return image.tobytes()


def font_for(char: str, fonts: list):
    """The first face that has a real glyph for char (not its .notdef box)."""
    for font in fonts:
        # U+FFFF is a noncharacter, so no face maps it: it draws .notdef.
        if glyph_bytes(font, char) != glyph_bytes(font, "\uffff"):
            return font
    return fonts[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("profile", type=Path)
    parser.add_argument("--top", type=int, default=20, help="pairs to show (default 20)")
    arguments = parser.parse_args(argv)
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("ERROR Pillow is required", file=sys.stderr)
        return 2
    profile_path = arguments.profile.expanduser().resolve()
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    crops_dir = profile_path.parent / profile.get("cropsDirectory", "")
    rulings_path = profile_path.with_name("variant-rulings.json")
    ruled, model = set(), {}
    if rulings_path.is_file():
        document = json.loads(rulings_path.read_text(encoding="utf-8"))
        for ruling in document.get("rulings") or []:
            if variant_ruling_by(ruling) == "model":
                model[frozenset(ruling.get("forms") or [])] = (ruling["printed"], ruling.get("votes") or {})
            elif ruling.get("printed"):
                ruled.add(frozenset(ruling.get("forms") or []))
        for entry in variant_person_unruled(document):
            ruled.add(frozenset(entry.get("forms") or []))
        for entry in document.get("modelUnruled") or []:
            model.setdefault(frozenset(entry.get("forms") or []), (None, entry.get("votes") or {}))
    pairs = [p for p in variant_vote.profile_pairs(profile)
             if frozenset((p["engineA"], p["engineB"])) not in ruled][:arguments.top]
    if not pairs:
        print("  no variant pair in this profile that a person has not ruled")
        return 0

    cell_h, label_w, gap = 220, 330, 12
    rows = []
    for pair in pairs:
        images = []
        for crop in pair.get("crops") or []:
            path = crops_dir / crop["crop"]
            if path.is_file():
                image = Image.open(path).convert("L")
                image.thumbnail((cell_h * 3, cell_h))
                images.append((image, crop["page"]))
        rows.append((pair, images))
    width = label_w + max((sum(i.width + gap for i, _ in images) for _, images in rows), default=0) + gap
    height = len(rows) * (cell_h + gap) + gap
    sheet = Image.new("L", (max(width, label_w + 200), height), 255)
    draw = ImageDraw.Draw(sheet)
    big, small = load_fonts(64), load_fonts(22)[0]
    y = gap
    for number, (pair, images) in enumerate(rows, 1):
        draw.text((gap, y + 10), f"{number}.", font=small, fill=0)
        faces = [font_for(form, big) for form in (pair["engineA"], pair["engineB"])]
        for offset, form, face in zip((0, 120), (pair["engineA"], pair["engineB"]), faces):
            draw.text((gap + 44 + offset, y + 20), form, font=face, fill=0)
        if glyph_bytes(faces[0], pair["engineA"]) == glyph_bytes(faces[1], pair["engineB"]):
            print(f"  WARNING pair {number} ({pair['engineA']}/{pair['engineB']}) draws identically "
                  "in the available fonts; rule it by code point", file=sys.stderr)
        draw.text((gap + 44, y + 110), f"A U+{ord(pair['engineA']):04X}  B U+{ord(pair['engineB']):04X}",
                  font=small, fill=80)
        draw.text((gap + 44, y + 140), f"{pair['occurrences']} disagreement(s)", font=small, fill=80)
        printed, votes = model.get(frozenset((pair["engineA"], pair["engineB"])), (None, None))
        if votes is not None:
            tally = "-".join(str(votes.get(form, 0)) for form in (pair["engineA"], pair["engineB"]))
            said = f"model: U+{ord(printed):04X} ({tally})" if printed else f"model: unruled ({tally})"
            draw.text((gap + 44, y + 170), said, font=small, fill=0)
        x = label_w
        for image, page in images:
            sheet.paste(image, (x, y))
            draw.text((x + 4, y + cell_h - 26), f"p.{page}", font=small, fill=0)
            x += image.width + gap
        draw.line((0, y + cell_h + gap // 2, sheet.width, y + cell_h + gap // 2), fill=200)
        y += cell_h + gap
    sheet_path = profile_path.with_name("variant-sheet.png")
    sheet.save(sheet_path)
    todo = {"book": profile.get("sources", {}).get("renders"),
            "instructions": ("optional, nothing waits for it: the model's ruling of each pair is in "
                             "variant-rulings.json (model here). To overrule it, set that pair's printed "
                             "there to the form the crops show and its ruledBy to person, on its entry in "
                             "rulings, or in modelUnruled for a pair the model left unruled"),
            "rulings": [{"forms": [p["engineA"], p["engineB"]], "printed": None,
                         "model": model.get(frozenset((p["engineA"], p["engineB"])), (None, None))[0],
                         "occurrences": p["occurrences"]} for p in pairs]}
    todo_path = profile_path.with_name("variant-rulings.todo.json")
    todo_path.write_text(json.dumps(todo, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    covered = sum(p["occurrences"] for p in pairs)
    total = (profile.get("variants") or {}).get("variantOccurrences") or 0
    print(f"  {len(pairs)} pair(s) covering {covered} of {total} variant disagreements")
    print(f"  sheet: {sheet_path}")
    print(f"  template: {todo_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
