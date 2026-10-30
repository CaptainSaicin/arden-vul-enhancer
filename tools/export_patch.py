#!/usr/bin/env python3
"""Maintainer-only export of coordinate edits from two privately owned PDFs.

Run from the project root with --original /private/original.pdf and
--enhanced /private/enhanced.pdf. Neither PDF is copied into the project.
The result contains hashes, positions and short label-reconstruction recipes;
it contains no PDF pages, illustrations, extracted prose, or original title list.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

import fitz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from arden_vul_enhancer.compatibility import (
    normalize_toc, page_fingerprint, source_text, toc_fingerprint,
)

STYLE = {
    "red": {"rgb": [1, .12, .16], "opacity": .32},
    "blue": {"rgb": [.10, .45, 1], "opacity": .32},
    "yellow": {"rgb": [1, .84, .04], "opacity": .38},
    "green": {"rgb": [.10, .75, .22], "opacity": .32},
}


def flattened(text):
    out, mapping = [], []
    i = 0
    while i < len(text):
        if text[i] == "-" and i and text[i - 1].isalpha():
            match = re.match(r"-[ \t]*\n[ \t]*(?=[a-z])", text[i:])
            if match:
                i += match.end()
                continue
        if text[i].isspace():
            if out and out[-1] != " ":
                out.append(" ")
                mapping.append(i)
        else:
            out.append(text[i])
            mapping.append(i)
        i += 1
    while out and out[-1] == " ":
        out.pop()
        mapping.pop()
    return "".join(out), mapping


def label_part(page_no, start, end, *, case=None, dehyphenate=False):
    result = {"page": page_no, "start": start, "end": end}
    if case:
        result["case"] = case
    if dehyphenate:
        result["dehyphenate"] = True
    return result


def render_part(part, texts):
    if isinstance(part, str):
        return part
    text = texts[part["page"]][part["start"]:part["end"]]
    if part.get("dehyphenate"):
        text = re.sub(r"(?<=[A-Za-z])-[ \t]*\n[ \t]*(?=[a-z])", "", text)
    text = " ".join(text.split())
    method = part.get("case")
    return getattr(text, method)() if method else text


def make_title_recipe(title, page_no, texts, flats, original_toc):
    # Most original outline labels are read back from the owner's original TOC.
    exact_original = [i for i, row in enumerate(original_toc) if row[1] == title]
    if exact_original:
        return {"original_toc": exact_original[0]}
    text, mapping = flats[page_no]
    if title in text:
        start = text.index(title)
        part = label_part(page_no, mapping[start], mapping[start + len(title) - 1] + 1)
        if render_part(part, texts) != title:
            part["dehyphenate"] = True
        if render_part(part, texts) == title:
            return {"parts": [part]}
    # Added shortcuts sometimes have our own explanatory prefix or descriptor.
    # Use longest exact phrases from the destination page where possible; keep
    # our short connectors, punctuation, room codes, and descriptors as literals.
    tokens = list(re.finditer(r"\S+", title))
    parts, at = [], 0
    while at < len(tokens):
        found = None
        for last in range(len(tokens), at, -1):
            phrase = title[tokens[at].start():tokens[last - 1].end()]
            # Room IDs and punctuation are metadata, not copied source prose.
            if len(phrase) < 3:
                continue
            matches = list(re.finditer(re.escape(phrase), text))
            transform = None
            if not matches and phrase.islower():
                matches = list(re.finditer(re.escape(phrase), text, re.I)); transform = "lower"
            if not matches and phrase[:1].isupper() and phrase[1:].islower():
                matches = list(re.finditer(re.escape(phrase), text, re.I)); transform = "capitalize"
            if not matches and phrase.isupper():
                matches = list(re.finditer(re.escape(phrase), text, re.I)); transform = "upper"
            if not matches:
                continue
            match = matches[0]
            part = label_part(page_no, mapping[match.start()], mapping[match.end() - 1] + 1, case=transform)
            if render_part(part, texts) != phrase:
                part["dehyphenate"] = True
            if render_part(part, texts) == phrase:
                found = last, part
                break
        if parts:
            parts.append(" ")
        if found:
            at, part = found
            parts.append(part)
        else:
            parts.append(tokens[at].group()); at += 1
    # Coalesce adjacent authored literal fragments for a compact manifest.
    merged = []
    for part in parts:
        if isinstance(part, str) and merged and isinstance(merged[-1], str):
            merged[-1] += part
        else:
            merged.append(part)
    assert "".join(render_part(part, texts) for part in merged) == title
    return {"parts": merged}


def export(original_path, enhanced_path, output):
    original, enhanced = fitz.open(original_path), fitz.open(enhanced_path)
    assert len(original) == 1122 and len(enhanced) == 1123
    original_toc = normalize_toc(original.get_toc())
    reviewed_toc = [row for row in enhanced.get_toc(False) if row[1] != "GM color key"]
    assert len(original_toc) == 3669 and len(reviewed_toc) == 3929
    assert [row[0] for row in reviewed_toc[-3669:]] == [row[0] for row in original_toc]
    source_pages, texts, flats = [], [], []
    for page in original:
        source_pages.append(page_fingerprint(page))
        text = source_text(page)
        texts.append(text); flats.append(flattened(text))
        if (page.number + 1) % 200 == 0:
            print(f"Fingerprinted {page.number + 1} source pages", flush=True)
    bookmarks, literal_fragments = [], []
    for i, row in enumerate(reviewed_toc):
        level, title, _, destination = row
        page = destination["page"]
        if i >= 260:
            original_index = i - 260
            assert title == original_toc[original_index][1]
            recipe = {"original_toc": original_index}
        else:
            recipe = make_title_recipe(title, page, texts, flats, original_toc)
        reconstructed = original_toc[recipe["original_toc"]][1] if "original_toc" in recipe else "".join(render_part(part, texts) for part in recipe["parts"])
        assert reconstructed == title, (i, reconstructed, title)
        entry = {"level": level, "page": page, "to": list(destination.get("to", (0, 0))), "title": recipe}
        for field in ("zoom", "bold", "italic", "color"):
            if destination.get(field):
                entry[field] = destination[field]
        bookmarks.append(entry)
        for part in recipe.get("parts", []):
            if isinstance(part, str) and part.strip():
                literal_fragments.append(part)
    links, highlights = {}, {}
    colors = Counter()
    for p in range(len(original)):
        page_links, page_highlights = [], []
        for link in enhanced[p].get_links():
            item = {"rect": list(link["from"])}
            if link["kind"] == fitz.LINK_GOTO:
                item.update(page=link["page"], to=list(link["to"]))
                if link.get("zoom"):
                    item["zoom"] = link["zoom"]
            elif link["kind"] == fitz.LINK_URI:
                item["uri"] = link["uri"]
            else:
                raise ValueError(f"Unexpected reviewed link kind: {link['kind']}")
            page_links.append(item)
        for annotation in enhanced[p].annots() or []:
            name = annotation.info.get("id", "")
            if annotation.type[0] != fitz.PDF_ANNOT_HIGHLIGHT or not name.startswith("GM-"):
                continue
            category = name.split("-")[1]
            rectangles = [list(fitz.Quad(annotation.vertices[i:i + 4]).rect) for i in range(0, len(annotation.vertices), 4)]
            page_highlights.append({"category": category, "rects": rectangles})
            colors[category] += 1
        if page_links:
            links[str(p)] = page_links
        if page_highlights:
            highlights[str(p)] = page_highlights
    count_links = sum(len(v) for v in links.values())
    assert count_links == 44338 and sum(colors.values()) == 19890
    data = {
        "schema_version": 1,
        "patch_version": "1.0.0",
        "source": {
            "page_count": len(original),
            "sha256": hashlib.sha256(Path(original_path).read_bytes()).hexdigest(),
            "pymupdf_version": fitz.VersionBind,
            "pages": source_pages,
            "original_toc_count": len(original_toc),
            "original_toc_sha256": toc_fingerprint(original.get_toc()),
        },
        "navigation": {
            "page_labels": [r for r in enhanced.get_page_labels() if r["startpage"] < 1122],
            "links": links,
            "bookmarks": bookmarks,
        },
        "highlights": {"style": STYLE, "pages": highlights},
        "counts": {"links": count_links, "bookmarks": len(bookmarks), "highlights": sum(colors.values()), "highlights_by_color": dict(colors), "highlighted_pages": len(highlights)},
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    output.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))
    report = {"schema_version": 1, "counts": data["counts"], "compressed_size": output.stat().st_size, "uncompressed_size": len(raw), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "bookmark_title_recipes_exact": len(bookmarks), "source_text_in_patch": False, "literal_fragments": literal_fragments}
    original.close()
    enhanced.close()
    print(json.dumps({k: v for k, v in report.items() if k != "literal_fragments"}, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--enhanced", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "arden_vul_enhancer/data/patch.json.gz")
    parser.add_argument("--private-report", type=Path)
    args = parser.parse_args()
    report = export(args.original, args.enhanced, args.output)
    if args.private_report:
        args.private_report.write_text(json.dumps(report, ensure_ascii=False, indent=2))
