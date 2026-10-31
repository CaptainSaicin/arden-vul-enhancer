"""Apply the reviewed coordinate patch to a locally owned source PDF.

No network calls are made by this module. Input bytes are never modified.
"""
from __future__ import annotations

import collections
from dataclasses import dataclass
import errno
import gzip
import hashlib
from importlib import resources
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
import time
from typing import Callable

import pymupdf as fitz

from . import __version__
from . import data as patch_resources
from .compatibility import source_text, page_fingerprint, toc_fingerprint

Progress = Callable[[float, str], None]
MARKER = "ArdenVulEnhancer"
COMMENT_KEYS = ("T", "Subj", "Contents", "RC", "Popup", "IRT", "RT", "State", "StateModel", "CreationDate", "M")


class EnhancementError(Exception):
    """An actionable, user-facing processing error."""


class CancelledError(EnhancementError):
    """Work was cancelled before publishing a completed output."""


@dataclass(frozen=True)
class EnhancementOptions:
    navigation: bool = True
    highlights: bool = True
    add_color_key: bool = True


def _notify(progress, fraction, message):
    if progress:
        progress(max(0.0, min(1.0, float(fraction))), message)


def _check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise CancelledError("Cancelled. Your original PDF has not been changed.")


def load_patch():
    try:
        with resources.files(patch_resources).joinpath("patch.json.gz").open("rb") as stream:
            patch = json.loads(gzip.decompress(stream.read()))
        if patch.get("schema_version") != 1:
            raise ValueError("unsupported data schema")
        if patch["source"]["page_count"] != 1122:
            raise ValueError("incorrect source page count")
        return patch
    except (OSError, KeyError, ValueError) as exc:
        raise EnhancementError("The editing data is missing or damaged. Extract the complete download again.") from exc


def _file_digest(path, cancel):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            _check_cancel(cancel)
            h.update(block)
    return h.hexdigest()


def _geometry_matches(actual, expected):
    for name in ("width", "height", "rotation", "mediabox", "cropbox"):
        if name not in expected:
            continue
        a, b = actual.get(name), expected[name]
        if isinstance(b, list):
            if not isinstance(a, (list, tuple)) or len(a) != len(b) or any(abs(x - y) > .01 for x, y in zip(a, b)):
                return False
        elif a is None or abs(a - b) > .01:
            return False
    return True


def _open_source(input_path, patch, navigation, progress, cancel):
    path = Path(input_path).expanduser().resolve()
    if not path.is_file():
        raise EnhancementError("Choose an existing PDF file.")
    _check_cancel(cancel)
    _notify(progress, .01, "Checking your original PDF...")
    try:
        doc = fitz.open(path)
    except Exception as exc:
        raise EnhancementError("This file could not be opened as a PDF. Try a fresh download of your original book.") from exc
    try:
        if not doc.is_pdf:
            raise EnhancementError("Choose a PDF file.")
        if doc.needs_pass:
            raise EnhancementError("This PDF requires a password. Use an unlocked copy that you are authorized to edit.")
        if len(doc) != patch["source"]["page_count"]:
            raise EnhancementError(f"This file has {len(doc):,} pages. This release supports the original 1,122-page Complete edition. Select that original file, rather than an individual volume, scan, or previously enhanced copy.")
        if doc.xref_get_key(doc.pdf_catalog(), MARKER)[0] != "null":
            raise EnhancementError("This copy has already been processed by Arden Vul Enhancer. Select your original PDF and choose the options you now want.")
        if doc.is_encrypted or not (doc.permissions & fitz.PDF_PERM_MODIFY and doc.permissions & fitz.PDF_PERM_ANNOTATE):
            raise EnhancementError("This PDF's permissions do not allow these edits. Use a copy that you are authorized to modify and annotate.")
        original_toc = doc.get_toc(simple=False)
        if navigation and toc_fingerprint(original_toc) != patch["source"]["original_toc_sha256"]:
            raise EnhancementError("The bookmarks in this file differ from the supported original. For navigation updates, select a fresh original Complete-edition PDF. A matching-page copy may still be usable with highlights only.")
        exact = _file_digest(path, cancel) == patch["source"]["sha256"]
        texts = {}
        if exact:
            _notify(progress, .25, "Original Complete edition verified.")
        else:
            for p, expected in enumerate(patch["source"]["pages"]):
                _check_cancel(cancel)
                actual = page_fingerprint(doc[p])
                valid = _geometry_matches(actual, expected)
                if "line_hashes" in expected:
                    required, present = collections.Counter(expected["line_hashes"]), collections.Counter(actual["line_hashes"])
                    valid = valid and not (required - present)
                else:
                    valid = valid and actual["text_sha256"] == expected["text_sha256"] and actual["glyph_sha256"] == expected["glyph_sha256"]
                if not valid:
                    raise EnhancementError(f"PDF page {p + 1} does not match the supported edition's text and layout. Nothing was changed. Please use the original Complete edition; scanned, resized, cropped, or revised editions are not supported by this patch.")
                _notify(progress, .025 + .225 * (p + 1) / len(doc), f"Checking compatibility: page {p + 1:,} of {len(doc):,}")
        # Prevent accidentally doubling the earlier conversation's markup or
        # this tool's highlights, even if a user removed its key-page/marker.
        for p in doc:
            _check_cancel(cancel)
            for annot in p.annots() or []:
                if annot.type[0] == fitz.PDF_ANNOT_HIGHLIGHT and str(annot.info.get("id", "")).startswith(("GM-", "AVE-")):
                    raise EnhancementError("This copy already contains the reviewed highlights. Select the original book to avoid adding them twice.")
        return path, doc, original_toc, texts, exact
    except BaseException:
        doc.close()
        raise


def inspect_pdf(input_path, progress: Progress | None = None, cancel: threading.Event | None = None):
    """Read-only compatibility check for all three processing modes."""
    patch = load_patch()
    path, doc, toc, _, exact = _open_source(input_path, patch, True, progress, cancel)
    try:
        return {"compatible": True, "input": str(path), "pages": len(doc), "original_bookmarks": len(toc), "exact_source_match": exact}
    finally:
        doc.close()


def _bookmark_title(recipe, original_toc, doc, patch, cache, exact):
    if "original_toc" in recipe:
        return " ".join(original_toc[recipe["original_toc"]][1].split())
    pieces = []
    for part in recipe["parts"]:
        if isinstance(part, str):
            pieces.append(part)
            continue
        p = part["page"]
        if p not in cache:
            expected = patch["source"]["pages"][p]
            if exact:
                # The file hash establishes the original geometry. Bookmark
                # offsets depend on text and order, not glyph coordinates,
                # which can round differently across extraction environments.
                text = source_text(doc[p])
                if hashlib.sha256(text.encode("utf-8")).hexdigest() != expected["text_sha256"]:
                    raise EnhancementError(f"PDF page {p + 1} text could not be verified for bookmark labels; no output was published.")
                cache[p] = text
            else:
                cache[p] = source_text(doc[p], expected.get("line_hashes"))
        text = cache[p][part["start"]:part["end"]]
        if part.get("dehyphenate"):
            text = re.sub(r"(?<=[A-Za-z])-[ \t]*\n[ \t]*(?=[a-z])", "", text)
        text = " ".join(text.split())
        case = part.get("case")
        if case == "lower":
            text = text.lower()
        elif case == "upper":
            text = text.upper()
        elif case == "capitalize":
            text = text.capitalize()
        pieces.append(text)
    title = "".join(pieces)
    if not title.strip():
        raise EnhancementError("A bookmark label could not be reconstructed from this PDF.")
    return title


def _toc_from_patch(doc, patch, original_toc, texts, exact):
    toc = []
    for item in patch["navigation"]["bookmarks"]:
        dest = {"kind": fitz.LINK_GOTO, "page": item["page"], "to": fitz.Point(item.get("to", [72, 36])), "zoom": item.get("zoom", 0)}
        for key in ("bold", "italic", "color", "collapse"):
            if key in item:
                dest[key] = item[key]
        toc.append([item["level"], _bookmark_title(item["title"], original_toc, doc, patch, texts, exact), item["page"] + 1, dest])
    return toc


def _annotation_refs(doc, page):
    import re
    kind, value = doc.xref_get_key(page.xref, "Annots")
    if kind == "xref":
        value = doc.xref_object(int(value.split()[0]), compressed=True)
    return re.findall(r"\d+\s+\d+\s+R", value) if kind in ("array", "xref") else []


def _draw_link_underlines(page, items):
    for item in items:
        rect = fitz.Rect(item["rect"])
        if rect.width <= 0 or rect.height <= 0:
            continue
        # Match the weight and offset of ordinary PDF underlines: lower and fully opaque so it stays visible beneath bold text.
        underline = fitz.Rect(rect.x0, max(rect.y0 + 4.5, rect.y1 - 6.5), rect.x1, rect.y1 - 1.5)
        annot = page.add_underline_annot(underline)
        annot.set_colors(stroke=(.18, .36, .62))
        annot.set_opacity(1.0)
        annot.set_flags(fitz.PDF_ANNOT_IS_PRINT)
        annot.update()


def _add_highlights(doc, page, items, styles):
    oldrefs = _annotation_refs(doc, page)
    newrefs = []
    for i, item in enumerate(items, 1):
        style = styles[item["category"]]
        annot = page.add_highlight_annot([fitz.Rect(rect).quad for rect in item["rects"]])
        annot.set_colors(stroke=style["rgb"])
        annot.set_opacity(style["opacity"])
        annot.set_flags(fitz.PDF_ANNOT_IS_PRINT)
        annot.update()
        doc.xref_set_key(annot.xref, "NM", fitz.get_pdf_str(f"AVE-{item['category']}-{page.number+1}-{i}"))
        for field in COMMENT_KEYS:
            doc.xref_set_key(annot.xref, field, "null")
        newrefs.append(f"{annot.xref} 0 R")
    if newrefs:
        # Existing and newly inserted links remain above highlights for clicks.
        doc.xref_set_key(page.xref, "Annots", "[" + " ".join(newrefs + oldrefs) + "]")


def _add_color_key(doc, counts, styles):
    page = doc.new_page(width=612, height=792)
    ink, muted = (.10, .14, .18), (.35, .39, .43)
    page.draw_rect(fitz.Rect(0, 0, 612, 11), color=None, fill=ink)
    page.insert_text((44, 64), "GM COLOR KEY", fontname="hebo", fontsize=25, color=ink)
    page.insert_text((44, 91), "Arden Vul Enhancer", fontname="helv", fontsize=15, color=muted)
    def box(rect, text, size=11):
        if page.insert_textbox(fitz.Rect(rect), text, fontname="helv", fontsize=size, lineheight=1.3, color=ink) < 0:
            raise EnhancementError("The color key could not be laid out correctly.")
    box((44, 113, 568, 168), "Use the colors for preparation and play. Highlights are editable and have no attached comment text. Original book pages remain in their original positions.")
    entries = [
        ("red", "MONSTERS & ENCOUNTER OCCUPANTS", "Creature names, counts, and encounter identifiers, including conditional and wandering encounters. Appendix entries identify reference material."),
        ("blue", "TRAPS & HAZARDS", "Triggers, harmful effects, environmental dangers, cursed interactions, and relevant detection or avoidance details."),
        ("yellow", "IMPORTANT GM INFORMATION", "Treasure, discoverable items, keys, documents, clues, secrets, special abilities, mechanisms, and rulings."),
        ("green", "PLAYER-SHAREABLE TEXT", "Descriptions, inscriptions, dialogue, and rumors to share when available to the characters. Apply visibility, language, and discovery conditions; rumors retain their uncertainty."),
    ]
    for i, (category, title, body) in enumerate(entries):
        y = 181 + i * 105
        color = styles[category]["rgb"]
        pale = tuple(1 - (1 - x) * .25 for x in color)
        page.draw_rect(fitz.Rect(44, y, 568, y + 91), color=None, fill=pale)
        page.draw_rect(fitz.Rect(44, y, 50, y + 91), color=None, fill=color)
        page.insert_text((64, y + 23), title, fontname="hebo", fontsize=11.8, color=ink)
        box((64, y + 34, 548, y + 83), body, 10.7)
    box((44, 619, 568, 672), "Green is a selective reading aid. Review unmarked sentences before reading them aloud. The encounter and the characters' discoveries determine what they can know.", 10.5)
    page.insert_text((44, 700), f"{sum(counts.values()):,} reviewed highlights | 1,122 original pages preserved", fontname="hebo", fontsize=10.8, color=ink)
    page.insert_text((44, 750), "Unofficial companion tool - editorial key appended after the book", fontsize=9, color=muted)
    return page.number


def _publish_new(temp, output):
    """Publish without ever replacing an existing destination."""
    try:
        os.link(temp, output)
    except FileExistsError as exc:
        raise EnhancementError("That output file already exists. Choose a new filename.") from exc
    except OSError as exc:
        if exc.errno not in (errno.EPERM, errno.EOPNOTSUPP, errno.EXDEV, errno.ENOSYS, errno.EINVAL, errno.EACCES):
            raise
        created = False
        try:
            with open(output, "xb") as destination:
                created = True
                with open(temp, "rb") as source:
                    shutil.copyfileobj(source, destination, 1024 * 1024)
                destination.flush()
                os.fsync(destination.fileno())
        except BaseException:
            if created:
                Path(output).unlink(missing_ok=True)
            raise


def _prepend_key_bookmark(doc, key_page):
    """Link in our key without rewriting original fit-page outline actions."""
    kind, root_ref = doc.xref_get_key(doc.pdf_catalog(), "Outlines")
    if kind != "xref":
        doc.set_toc([[1, "GM color key", key_page + 1]])
        return
    root_xref = int(root_ref.split()[0])
    first_kind, first_ref = doc.xref_get_key(root_xref, "First")
    if first_kind != "xref":
        doc.set_toc([[1, "GM color key", key_page + 1]])
        return
    first_xref = int(first_ref.split()[0])
    new_xref = doc.get_new_xref()
    doc.update_object(new_xref, "<< >>")
    doc.xref_set_key(new_xref, "Title", fitz.get_pdf_str("GM color key"))
    doc.xref_set_key(new_xref, "Parent", root_ref)
    doc.xref_set_key(new_xref, "Next", first_ref)
    doc.xref_set_key(new_xref, "Dest", f"[{doc.page_xref(key_page)} 0 R /XYZ 72 756 0]")
    doc.xref_set_key(first_xref, "Prev", f"{new_xref} 0 R")
    doc.xref_set_key(root_xref, "First", f"{new_xref} 0 R")
    count_kind, count_text = doc.xref_get_key(root_xref, "Count")
    count = int(count_text) if count_kind == "int" else 0
    doc.xref_set_key(root_xref, "Count", str(count + 1 if count >= 0 else count - 1))


def enhance_pdf(input_path, output_path, options: EnhancementOptions | None = None,
                progress: Progress | None = None, cancel: threading.Event | None = None):
    """Write a new enhanced PDF and return a compact, text-free report."""
    started = time.monotonic()
    options = options or EnhancementOptions()
    if not options.navigation and not options.highlights:
        raise EnhancementError("Choose navigation updates, highlights, or both.")
    source_path = Path(input_path).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()
    if output == source_path:
        raise EnhancementError("Choose a different output filename. The original PDF must remain untouched.")
    if output.suffix.lower() != ".pdf":
        raise EnhancementError("The output filename must end in .pdf.")
    if output.exists():
        raise EnhancementError("That output file already exists. Choose a new filename.")
    patch = load_patch()
    doc = None
    temp = None
    try:
        _, doc, original_toc, texts, exact = _open_source(source_path, patch, options.navigation, progress, cancel)
        input_page_count = len(doc)
        original_link_count = sum(len(page.get_links()) for page in doc)
        counts = collections.Counter()
        toc = _toc_from_patch(doc, patch, original_toc, texts, exact) if options.navigation else original_toc
        links_added = 0
        for p in range(input_page_count):
            _check_cancel(cancel)
            page = doc[p]
            if options.navigation:
                for item in patch["navigation"]["links"].get(str(p), []):
                    link = {"from": fitz.Rect(item["rect"])}
                    if "uri" in item:
                        link.update(kind=fitz.LINK_URI, uri=item["uri"])
                    else:
                        link.update(kind=fitz.LINK_GOTO, page=item["page"], to=fitz.Point(item["to"]), zoom=item.get("zoom", 0))
                    page.insert_link(link)
                    _draw_link_underlines(page, [item])
                    links_added += 1
            if options.highlights:
                items = patch["highlights"]["pages"].get(str(p), [])
                _add_highlights(doc, page, items, patch["highlights"]["style"])
                counts.update(item["category"] for item in items)
            if p % 8 == 0 or p + 1 == input_page_count:
                _notify(progress, .25 + .52 * (p + 1) / input_page_count, f"Applying updates: page {p + 1:,} of {input_page_count:,}")
        _check_cancel(cancel)
        key_page = None
        labels = patch["navigation"].get("page_labels", []) if options.navigation else doc.get_page_labels()
        if options.highlights and options.add_color_key:
            key_page = _add_color_key(doc, counts, patch["highlights"]["style"])
            labels = labels + [{"startpage": key_page, "prefix": "GM Key", "style": "", "firstpagenum": 1}]
        if options.navigation:
            if key_page is not None:
                toc = [[1, "GM color key", key_page + 1]] + toc
            doc.set_toc(toc, collapse=1)
            doc.set_page_labels(labels)
        elif key_page is not None:
            _prepend_key_bookmark(doc, key_page)
            doc.set_page_labels(labels)
        stamp = {"version": __version__, "patch": patch.get("patch_id", "reviewed-v4"), "navigation": options.navigation, "highlights": options.highlights}
        doc.xref_set_key(doc.pdf_catalog(), MARKER, fitz.get_pdf_str(json.dumps(stamp, separators=(",", ":"))))
        output.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp = tempfile.mkstemp(prefix=".arden-vul-", suffix=".pdf", dir=output.parent)
        os.close(descriptor)
        _notify(progress, .79, "Saving the enhanced copy. This step may take a moment...")
        doc.save(temp, garbage=2, deflate=True, use_objstms=1)
        doc.close()
        doc = None
        _check_cancel(cancel)
        _notify(progress, .87, "Verifying the saved PDF...")
        with fitz.open(temp) as saved:
            if len(saved) != input_page_count + (key_page is not None):
                raise EnhancementError("The saved page count was unexpected; no output was published.")
            actual_links, actual_highlights = 0, 0
            for p in range(input_page_count):
                _check_cancel(cancel)
                page = saved[p]
                actual_links += len(page.get_links())
                for annot in page.annots() or []:
                    if str(annot.info.get("id", "")).startswith("AVE-"):
                        actual_highlights += 1
                        if any(value for name, value in annot.info.items() if name != "id") or annot.popup_xref:
                            raise EnhancementError("A highlight unexpectedly contained a comment; no output was published.")
                if p % 40 == 0:
                    _notify(progress, .87 + .10 * (p + 1) / input_page_count, f"Verifying: page {p + 1:,} of {input_page_count:,}")
            if actual_links != original_link_count + links_added or actual_highlights != sum(counts.values()):
                raise EnhancementError("The saved update counts did not match; no output was published.")
            bookmarks_total, pages_total = len(saved.get_toc()), len(saved)
        _check_cancel(cancel)
        _publish_new(temp, output)
        _notify(progress, 1, "Finished. Your original PDF is unchanged.")
        return {"output": str(output), "pages": pages_total, "navigation": options.navigation,
                "highlights": options.highlights, "links_added": links_added,
                "bookmarks_total": bookmarks_total, "highlights_added": sum(counts.values()),
                "highlight_counts": dict(counts), "color_key_page": key_page + 1 if key_page is not None else None,
                "original_preserved": True, "exact_source_match": exact, "warnings": [],
                "seconds": round(time.monotonic() - started, 2)}
    except (EnhancementError, CancelledError):
        raise
    except Exception as exc:
        raise EnhancementError(f"The PDF could not be completed: {exc}. Your original file was not changed.") from exc
    finally:
        if doc is not None:
            doc.close()
        if temp:
            Path(temp).unlink(missing_ok=True)
