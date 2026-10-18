"""Unified inventory + wipe application."""

import json
import os
import tempfile
import unittest

from tests import *  # noqa: F401,F403

from lenswipe.inspect import detect, scan_bytes, scan_file
from lenswipe.synth import (build_jpeg, build_png, build_webp, sample_jpeg,
                            sample_png, sample_webp)
from lenswipe.wipe import (detect_identity_mismatch, wipe_bytes,
                           wipe_bytes_strict, wipe_file)


class DetectTests(unittest.TestCase):
    def test_magic_detection(self):
        self.assertEqual(detect(sample_jpeg()), "jpeg")
        self.assertEqual(detect(sample_png()), "png")
        self.assertEqual(detect(sample_webp()), "webp")
        self.assertEqual(detect(b"GIF89a..."), "unknown")
        self.assertEqual(detect(b""), "unknown")


class ScanTests(unittest.TestCase):
    def test_scan_dirty_jpeg(self):
        inv = scan_bytes(sample_jpeg())
        self.assertEqual(inv.fmt, "jpeg")
        self.assertFalse(inv.is_clean())
        self.assertTrue(inv.has_gps)
        self.assertTrue(inv.tag_count >= 5)
        self.assertGreaterEqual(len(inv.dirty_blocks()), 3)

    def test_scan_clean_jpeg(self):
        inv = scan_bytes(build_jpeg(jfif=True, exif=False, xmp=False))
        self.assertTrue(inv.is_clean())          # JFIF alone is not metadata
        self.assertFalse(inv.has_gps)

    def test_png_and_webp_scans(self):
        png_inv = scan_bytes(sample_png())
        webp_inv = scan_bytes(sample_webp())
        for inv in (png_inv, webp_inv):
            self.assertFalse(inv.is_clean())
            self.assertTrue(inv.has_gps)

    def test_unknown_format_is_an_error(self):
        inv = scan_bytes(b"MZ\x90\x00", path="evil.bin")
        self.assertEqual(inv.fmt, "unknown")
        self.assertIn("unrecognized", inv.error)
        self.assertFalse(inv.is_clean())
        self.assertFalse(inv.is_clean(all_meta=True))

    def test_corrupt_container_reports_error(self):
        # APP1 declares 255 bytes but the file ends mid-segment
        inv = scan_bytes(b"\xff\xd8\xff\xe1\x00\xff", path="broken.jpg")
        self.assertIsNotNone(inv.error)

    def test_bad_path_reports_error(self):
        inv = scan_file("/does/not/exist.jpg")
        self.assertIsNotNone(inv.error)

    def test_all_meta_flag_dirties_jfif_and_phys(self):
        jpeg_inv = scan_bytes(build_jpeg(jfif=True, exif=False, xmp=False))
        self.assertFalse(jpeg_inv.is_clean(all_meta=True))
        png_inv = scan_bytes(build_png(exif=False, phys=True))
        self.assertFalse(png_inv.is_clean(all_meta=True))
        self.assertTrue(scan_bytes(build_png(exif=False, phys=False),
                                   ).is_clean(all_meta=True))

    def test_to_dict_is_json_serializable(self):
        inv = scan_bytes(sample_jpeg())
        payload = json.loads(json.dumps(inv.to_dict()))
        self.assertEqual(payload["format"], "jpeg")
        self.assertTrue(payload["gps"])
        kinds = [b["kind"] for b in payload["blocks"]]
        self.assertIn("exif", kinds)
        exif = next(b for b in payload["blocks"] if b["kind"] == "exif")
        self.assertTrue(exif["dirty"])
        self.assertTrue(any(t["name"] == "Make" for t in exif["tags"]))


class WipeBytesTests(unittest.TestCase):
    def test_wipe_jpeg_makes_it_clean(self):
        data = sample_jpeg()
        out, removed = wipe_bytes(data)
        self.assertTrue(removed)
        self.assertTrue(scan_bytes(out).is_clean())
        self.assertNotIn("exif", removed)
        self.assertTrue(any("GPS" in r for r in removed))

    def test_wipe_png_makes_it_clean(self):
        out, removed = wipe_bytes(sample_png())
        self.assertTrue(scan_bytes(out).is_clean())
        self.assertFalse(scan_bytes(out).is_clean(all_meta=True))
        # default wipe leaves presentation chunks (pHYs) in place
        with_phys = scan_bytes(out)
        kinds = [b.kind for b in with_phys.blocks]
        self.assertIn("presentation", kinds)

    def test_wipe_png_all_meta(self):
        out, removed = wipe_bytes(sample_png(), all_meta=True)
        inv = scan_bytes(out)
        self.assertTrue(inv.is_clean(all_meta=True))
        self.assertTrue(any("presentation" in r for r in removed))

    def test_wipe_webp_makes_it_clean_and_preserves_image_chunk(self):
        out, removed = wipe_bytes(sample_webp())
        inv = scan_bytes(out)
        self.assertTrue(inv.is_clean())
        self.assertEqual(inv.fmt, "webp")
        fourccs = [c.fourcc for _n, c in [(0, c) for c in
                                          __import__("lenswipe.webp",
                                                     fromlist=["x"]).parse_riff(out)]]
        self.assertIn("VP8 ", fourccs)

    def test_wipe_unknown_raises(self):
        with self.assertRaises(ValueError):
            wipe_bytes(b"always text")

    def test_strict_verifies_cleanliness(self):
        out, _ = wipe_bytes_strict(sample_jpeg())
        self.assertTrue(scan_bytes(out).is_clean())

    def test_identity_mismatch_detection(self):
        self.assertTrue(detect_identity_mismatch(sample_jpeg(), sample_png()))
        self.assertFalse(detect_identity_mismatch(sample_jpeg(),
                                                  sample_jpeg()))

    def test_wipe_of_clean_file_is_a_noop(self):
        clean = build_jpeg(jfif=True, exif=False, xmp=False)
        out, removed = wipe_bytes(clean)
        self.assertEqual(removed, [])
        self.assertEqual(out, clean)


class WipeFileTests(unittest.TestCase):
    def test_default_writes_sibling_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "photo.jpg")
            with open(src, "wb") as fh:
                fh.write(sample_jpeg())
            r = wipe_file(src)
            self.assertIsNone(r.error)
            self.assertTrue(r.verified)
            self.assertIsNotNone(r.out_path)
            self.assertTrue(r.out_path.endswith(".wiped.jpg"))
            self.assertTrue(os.path.exists(r.out_path))
            self.assertTrue(scan_file(r.out_path).is_clean())
            self.assertFalse(scan_file(src).is_clean())   # original untouched
            self.assertLess(r.bytes_out, r.bytes_in)

    def test_output_dir_changes_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "photo.png")
            out_dir = os.path.join(tmp, "cleaned")
            with open(src, "wb") as fh:
                fh.write(sample_png())
            r = wipe_file(src, output_dir=out_dir)
            self.assertIsNone(r.error)
            self.assertTrue(r.out_path.startswith(out_dir))
            self.assertTrue(os.path.exists(r.out_path))

    def test_in_place_keeps_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "shot.webp")
            original = sample_webp()
            with open(src, "wb") as fh:
                fh.write(original)
            r = wipe_file(src, in_place=True)
            self.assertIsNone(r.error)
            self.assertTrue(r.verified)
            self.assertEqual(r.out_path, src)
            with open(src, "rb") as fh:
                self.assertTrue(scan_bytes(fh.read()).is_clean())
            bak = src + ".bak"
            self.assertTrue(os.path.exists(bak))
            with open(bak, "rb") as fh:
                self.assertEqual(fh.read(), original)

    def test_in_place_no_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "shot.jpg")
            with open(src, "wb") as fh:
                fh.write(sample_jpeg())
            r = wipe_file(src, in_place=True, backup=False)
            self.assertIsNone(r.error)
            self.assertFalse(os.path.exists(src + ".bak"))

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "shot.jpg")
            with open(src, "wb") as fh:
                fh.write(sample_jpeg())
            r = wipe_file(src, dry_run=True)
            self.assertTrue(r.dry_run)
            self.assertTrue(r.ok)
            self.assertTrue(r.removed)
            self.assertEqual(os.listdir(tmp), ["shot.jpg"])

    def test_clean_input_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "clean.png")
            data = build_png(exif=False, texts={}, phys=False)
            with open(src, "wb") as fh:
                fh.write(data)
            r = wipe_file(src)
            self.assertIsNone(r.error)
            self.assertEqual(r.removed, [])
            self.assertEqual(os.listdir(tmp), ["clean.png"])   # no wipe file

    def test_missing_file_reports_error(self):
        r = wipe_file("/no/such/file.jpg")
        self.assertIsNotNone(r.error)
        self.assertFalse(r.ok)


if __name__ == "__main__":
    unittest.main()