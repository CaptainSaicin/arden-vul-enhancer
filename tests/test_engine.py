"""Exercise real PDF edits using a tiny original fixture, never the book."""
import hashlib
import errno
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch as mock_patch

import pymupdf as fitz

from arden_vul_enhancer import engine
from arden_vul_enhancer.compatibility import page_fingerprint, source_text, toc_fingerprint


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "My original.pdf"
        with fitz.open() as doc:
            for title in ("First chamber", "Second chamber"):
                page = doc.new_page(width=612, height=792)
                page.insert_text((60, 80), title, fontsize=16)
                page.insert_text((60, 110), "An original test fixture; not book content.")
            doc.set_toc([[1, "First chamber", 1], [1, "Second chamber", 2]])
            doc.set_page_labels([{"startpage": 0, "prefix": "", "style": "D", "firstpagenum": 1}])
            doc.save(self.source)
        self.original_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        with fitz.open(self.source) as doc:
            self.patch = {
                "schema_version": 1,
                "source": {"page_count": 2, "sha256": self.original_hash,
                           "pages": [page_fingerprint(p) for p in doc],
                           "original_toc_sha256": toc_fingerprint(doc.get_toc(simple=False))},
                "navigation": {"page_labels": doc.get_page_labels(),
                               "links": {"0": [{"rect": [60, 65, 170, 85], "page": 1, "to": [60, 60]}],
                                         "1": [{"rect": [60, 65, 180, 85], "uri": "https://example.org"}]},
                               "bookmarks": [{"level": 1, "page": 0, "to": [60, 60], "title": {"original_toc": 0}},
                                             {"level": 1, "page": 1, "to": [60, 60], "title": {"parts": ["Jump to ", {"page": 1, "start": 0, "end": len("Second chamber"), "case": "lower"}]}}]},
                "highlights": {"style": {
                    "yellow": {"rgb": [1, .84, .04], "opacity": .38},
                    "green": {"rgb": [.10, .75, .22], "opacity": .32},
                    "blue": {"rgb": [.10, .45, 1], "opacity": .32},
                    "red": {"rgb": [1, .12, .16], "opacity": .32}},
                    "pages": {"0": [{"category": "yellow", "rects": [[60, 65, 170, 85]]}],
                              "1": [{"category": "green", "rects": [[60, 65, 180, 85]]}]}}
            }
        self.loader = mock_patch.object(engine, "load_patch", return_value=self.patch)
        self.loader.start()

    def tearDown(self):
        self.loader.stop()
        self.temp.cleanup()

    def run_mode(self, navigation, highlights, key=True):
        out = self.root / f"output-{navigation}-{highlights}-{key}.pdf"
        report = engine.enhance_pdf(self.source, out, engine.EnhancementOptions(navigation, highlights, key))
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.original_hash)
        with fitz.open(self.source) as src, fitz.open(out) as result:
            self.assertEqual(len(result), 2 + bool(highlights and key))
            self.assertEqual(sum(len(p.get_links()) for p in result), 2 if navigation else 0)
            self.assertEqual(report["highlights_added"], 2 if highlights else 0)
            for i in range(2):
                self.assertEqual(src[i].get_text(), result[i].get_text())
                self.assertEqual([src.xref_stream(x) for x in src[i].get_contents()], [result.xref_stream(x) for x in result[i].get_contents()])
                for annot in result[i].annots() or []:
                    self.assertFalse(annot.popup_xref)
                    self.assertFalse(any(v for k, v in annot.info.items() if k != "id"))
            if navigation:
                toc = result.get_toc()
                self.assertIn([1, "Jump to second chamber", 2], toc)
            else:
                self.assertEqual(result.get_toc()[-2:], src.get_toc())
        return out

    def test_all_three_modes_and_no_key(self):
        for nav, hi, key in [(True, False, True), (False, True, True), (True, True, True), (True, True, False)]:
            with self.subTest(nav=nav, hi=hi, key=key):
                self.run_mode(nav, hi, key)

    def test_existing_output_and_original_are_never_overwritten(self):
        existing = self.root / "keep.pdf"
        existing.write_bytes(b"keep these bytes")
        with self.assertRaises(engine.EnhancementError):
            engine.enhance_pdf(self.source, existing)
        self.assertEqual(existing.read_bytes(), b"keep these bytes")
        with self.assertRaises(engine.EnhancementError):
            engine.enhance_pdf(self.source, self.source)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.original_hash)

    def test_no_options_rejected(self):
        with self.assertRaises(engine.EnhancementError):
            engine.enhance_pdf(self.source, self.root / "none.pdf", engine.EnhancementOptions(False, False))

    def test_cancel_leaves_no_output(self):
        cancel = threading.Event()
        def progress(fraction, message):
            if fraction >= .25:
                cancel.set()
        output = self.root / "cancelled.pdf"
        with self.assertRaises(engine.CancelledError):
            engine.enhance_pdf(self.source, output, progress=progress, cancel=cancel)
        self.assertFalse(output.exists())
        self.assertFalse(list(self.root.glob(".arden-vul-*")))

    def test_metadata_and_separate_watermark_preserve_compatibility(self):
        changed = self.root / "watermarked.pdf"
        with fitz.open(self.source) as doc:
            doc[0].insert_text((300, 750), "Personal ownership watermark")
            doc.set_metadata({"title": "My purchase"})
            doc.save(changed)
        report = engine.enhance_pdf(changed, self.root / "watermark-output.pdf", engine.EnhancementOptions(True, False))
        self.assertFalse(report["exact_source_match"])

    def test_exact_pdf_bookmarks_verify_text_instead_of_glyph_coordinates(self):
        # Simulate a different rounded glyph coordinate in the patch data.
        self.patch["source"]["pages"][1]["line_hashes"][0] = "different geometry"
        out = self.root / "exact.pdf"
        report = engine.enhance_pdf(self.source, out, engine.EnhancementOptions(True, False))
        self.assertTrue(report["exact_source_match"])
        with fitz.open(out) as doc:
            self.assertIn([1, "Jump to second chamber", 2], doc.get_toc())

        # A non-exact file still needs the position-sensitive compatibility check.
        changed = self.root / "changed-metadata.pdf"
        with fitz.open(self.source) as doc:
            doc.set_metadata({"title": "Different file"})
            doc.save(changed)
        with self.assertRaises(engine.EnhancementError):
            engine.enhance_pdf(changed, self.root / "rejected.pdf", engine.EnhancementOptions(True, False))

    def test_exact_pdf_rejects_unverified_bookmark_text(self):
        self.patch["source"]["pages"][1]["text_sha256"] = "different text"
        out = self.root / "rejected.pdf"
        with self.assertRaisesRegex(engine.EnhancementError, "page 2 text could not be verified"):
            engine.enhance_pdf(self.source, out, engine.EnhancementOptions(True, False))
        self.assertFalse(out.exists())

    def test_changed_content_is_rejected(self):
        changed = self.root / "different.pdf"
        with fitz.open(self.source) as doc:
            doc[0].add_redact_annot(fitz.Rect(50, 50, 200, 90))
            doc[0].apply_redactions()
            doc.save(changed)
        with self.assertRaises(engine.EnhancementError):
            engine.enhance_pdf(changed, self.root / "bad.pdf")
        self.assertFalse((self.root / "bad.pdf").exists())

    def test_navigation_requires_original_bookmarks(self):
        changed = self.root / "no-bookmarks.pdf"
        with fitz.open(self.source) as doc:
            doc.set_toc([])
            doc.save(changed)
        with self.assertRaises(engine.EnhancementError):
            engine.enhance_pdf(changed, self.root / "bad.pdf")
        report = engine.enhance_pdf(changed, self.root / "highlights.pdf", engine.EnhancementOptions(False, True, False))
        self.assertEqual(report["highlights_added"], 2)

    def test_previously_processed_copy_rejected(self):
        processed = self.run_mode(True, False)
        with self.assertRaises(engine.EnhancementError):
            engine.enhance_pdf(processed, self.root / "twice.pdf")

    def test_publication_race_does_not_overwrite(self):
        temp, dest = self.root / "temporary.pdf", self.root / "destination.pdf"
        temp.write_bytes(b"new")
        dest.write_bytes(b"existing")
        with self.assertRaises(engine.EnhancementError):
            engine._publish_new(temp, dest)
        self.assertEqual(dest.read_bytes(), b"existing")

    def test_original_fit_page_bookmarks_survive_highlights_and_key(self):
        original = self.root / "fit-page-bookmarks.pdf"
        with fitz.open(self.source) as doc:
            for index, item in enumerate(doc.get_toc(simple=False)):
                doc.xref_set_key(item[3]["xref"], "A", f"<< /S /GoTo /D [{doc.page_xref(index)} 0 R /Fit] >>")
            doc.save(original)
        with fitz.open(original) as doc:
            before = doc.get_toc(simple=False)
            self.assertEqual(before[0][3]["kind"], fitz.LINK_NAMED)
        destination = self.root / "kept-fit-page-bookmarks.pdf"
        engine.enhance_pdf(original, destination, engine.EnhancementOptions(False, True, True))
        with fitz.open(destination) as doc:
            after = doc.get_toc(simple=False)[1:]
        def semantic(row):
            return row[:3] + [{k:v for k,v in row[3].items() if k != "xref"}]
        self.assertEqual(list(map(semantic, before)), list(map(semantic, after)))

    def test_publication_fallback_for_filesystems_without_hardlinks(self):
        temp, dest = self.root / "temp-fallback.pdf", self.root / "saved-fallback.pdf"
        temp.write_bytes(b"complete content")
        with mock_patch.object(engine.os, "link", side_effect=OSError(errno.EPERM, "not supported")):
            engine._publish_new(temp, dest)
        self.assertEqual(dest.read_bytes(), b"complete content")


if __name__ == "__main__":
    unittest.main()
