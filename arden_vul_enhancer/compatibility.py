"""Compare the owner's PDF against irreversible text-and-position fingerprints.

The patch never stores source text. Added watermark lines are accepted only when
every original line remains present at the same position. A matching page can
then supply bookmark labels directly from the user's own copy.
"""
from __future__ import annotations

from collections import defaultdict, deque
import hashlib
import json
import re
import unicodedata

import fitz


def normalize_text(value: str) -> str:
    return (unicodedata.normalize("NFKC", value)
            .replace("’", "'").replace("‘", "'")
            .replace("–", "-").replace("—", "-").replace("−", "-")
            .replace("\u00ad", ""))


def _digest(value) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _lines(page):
    flags = fitz.TEXTFLAGS_RAWDICT & ~fitz.TEXT_PRESERVE_IMAGES
    for block in page.get_text("rawdict", flags=flags)["blocks"]:
        for line in block.get("lines", []):
            glyphs = []
            text = []
            for span in line["spans"]:
                for char in span["chars"]:
                    box = [round(float(v), 2) for v in char["bbox"]]
                    for normalized_char in normalize_text(char["c"]):
                        text.append(normalized_char)
                        glyphs.append([normalized_char] + box)
            yield _digest(glyphs), "".join(text)


def _geometry(page):
    return {
        "width": round(float(page.rect.width), 4),
        "height": round(float(page.rect.height), 4),
        "rotation": int(page.rotation),
        "mediabox": [round(float(v), 4) for v in page.mediabox],
        "cropbox": [round(float(v), 4) for v in page.cropbox],
    }


def page_fingerprint(page) -> dict:
    lines = list(_lines(page))
    hashes = [item[0] for item in lines]
    text = "".join(item[1] + "\n" for item in lines)
    return {
        **_geometry(page),
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "glyph_sha256": _digest(hashes),
        "line_hashes": hashes,
    }


def source_text(page, expected_line_hashes=None) -> str:
    lines = list(_lines(page))
    if expected_line_hashes is None:
        return "".join(text + "\n" for _, text in lines)
    available = defaultdict(deque)
    for digest, text in lines:
        available[digest].append(text)
    result = []
    for digest in expected_line_hashes:
        if not available[digest]:
            raise ValueError("An original text line is missing, changed, or moved.")
        result.append(available[digest].popleft() + "\n")
    return "".join(result)


def match_page(page, expected: dict) -> str:
    actual = _geometry(page)
    if actual["rotation"] != expected["rotation"]:
        raise ValueError("The page rotation does not match the supported edition.")
    for field in ("width", "height"):
        if abs(actual[field] - expected[field]) > 0.01:
            raise ValueError("The page size does not match the supported edition.")
    for field in ("mediabox", "cropbox"):
        if len(actual[field]) != len(expected[field]) or any(
                abs(a - b) > 0.01 for a, b in zip(actual[field], expected[field])):
            raise ValueError("The page crop or media box does not match the supported edition.")
    text = source_text(page, expected["line_hashes"])
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != expected["text_sha256"]:
        raise ValueError("The page text does not match the supported edition.")
    return text


def normalize_toc(toc) -> list:
    return [[int(row[0]), re.sub(r"\s+", " ", row[1]).strip(), int(row[2])] for row in toc]


def toc_fingerprint(toc) -> str:
    return _digest(normalize_toc(toc))
