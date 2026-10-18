"""CLI end-to-end (subprocess)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

from tests import *  # noqa: F401,F403

from lenswipe.inspect import scan_file
from lenswipe.synth import build_png, sample_jpeg, sample_png, sample_webp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
ENV = dict(os.environ, PYTHONPATH=SRC)


def run(*args, stdin_text=None):
    return subprocess.run(
        [sys.executable, "-m", "lenswipe", *args],
        input=stdin_text, capture_output=True, text=True, encoding="utf-8",
        env=ENV, cwd=ROOT, timeout=60)


def write(tmp, name, data):
    path = os.path.join(tmp, name)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


class ReportTests(unittest.TestCase):
    def test_report_text_lists_tags_and_gps(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = write(tmp, "a.jpg", sample_jpeg())
            r = run("report", p)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("DIRTY", r.stdout)
            self.assertIn("GPS", r.stdout)
            self.assertIn("Make", r.stdout)
            self.assertIn("LenswipeCam", r.stdout)
            self.assertIn("exif", r.stdout)

    def test_report_clean_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = write(tmp, "clean.jpg",
                      __import__("lenswipe.synth", fromlist=["x"])
                      .build_jpeg(jfif=True, exif=False, xmp=False))
            r = run("report", p)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("clean", r.stdout)

    def test_report_json_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = write(tmp, "a.png", sample_png())
            r = run("report", p, "--json")
            self.assertEqual(r.returncode, 0, r.stderr)
            payload = json.loads(r.stdout)
            self.assertEqual(len(payload["files"]), 1)
            entry = payload["files"][0]
            self.assertEqual(entry["format"], "png")
            self.assertFalse(entry["clean"])
            self.assertTrue(entry["gps"])
            kinds = [b["kind"] for b in entry["blocks"]]
            self.assertIn("text", kinds)

    def test_report_fail_on_metadata_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            dirty = write(tmp, "d.jpg", sample_jpeg())
            clean = write(tmp, "c.jpg", build_png(exif=False, phys=False))
            self.assertEqual(run("report", dirty, "--fail-on-metadata").returncode, 1)
            self.assertEqual(run("report", clean, "--fail-on-metadata").returncode, 0)

    def test_report_all_meta_sees_jfif(self):
        with tempfile.TemporaryDirectory() as tmp:
            from lenswipe.synth import build_jpeg
            p = write(tmp, "j.jpg", build_jpeg(jfif=True, exif=False, xmp=False))
            self.assertEqual(run("report", p).returncode, 0)
            r = run("report", p, "--all", "--fail-on-metadata")
            self.assertEqual(r.returncode, 1)


class CheckTests(unittest.TestCase):
    def test_dirty_exits_one_clean_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            dirty = write(tmp, "d.webp", sample_webp())
            clean = write(tmp, "c.png", build_png(exif=False, texts={}, phys=False))
            self.assertEqual(run("check", dirty).returncode, 1)
            self.assertEqual(run("check", clean).returncode, 0)
            out = run("check", dirty, clean).stdout
            self.assertIn("DIRTY", out)
            self.assertIn("CLEAN", out)

    def test_check_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = write(tmp, "d.jpg", sample_jpeg())
            r = run("check", p, "--json")
            self.assertEqual(r.returncode, 1)
            payload = json.loads(r.stdout)
            self.assertEqual(payload["dirty"], 1)

    def test_check_unknown_format_is_error_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = write(tmp, "doc.txt", b"just text")
            r = run("check", p)
            self.assertEqual(r.returncode, 2, r.stdout)
            self.assertIn("unrecognized", r.stdout + r.stderr)


class WipeTests(unittest.TestCase):
    def test_wipe_creates_wiped_file_that_passes_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = write(tmp, "shot.jpg", sample_jpeg())
            r = run("wipe", p)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("verified", r.stdout)
            wiped = os.path.join(tmp, "shot.wiped.jpg")
            self.assertTrue(os.path.exists(wiped))
            self.assertEqual(run("check", wiped).returncode, 0)
            self.assertEqual(run("check", p).returncode, 1)
            self.assertTrue(scan_file(p).has_gps)
            self.assertFalse(scan_file(wiped).has_gps)

    def test_wipe_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = write(tmp, "shot.jpg", sample_jpeg())
            r = run("wipe", p, "--dry-run", "--json")
            self.assertEqual(r.returncode, 0, r.stderr)
            payload = json.loads(r.stdout)
            self.assertTrue(payload["files"][0]["dry_run"])
            self.assertTrue(payload["files"][0]["removed"])
            self.assertEqual(os.listdir(tmp), ["shot.jpg"])

    def test_wipe_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = write(tmp, "shot.png", sample_png())
            r = run("wipe", p, "--in-place")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue(os.path.exists(p + ".bak"))
            self.assertEqual(run("check", p).returncode, 0)

    def test_wipe_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = write(tmp, "s.webp", sample_webp())
            r = run("wipe", p, "--json")
            self.assertEqual(r.returncode, 0, r.stderr)
            payload = json.loads(r.stdout)["files"][0]
            self.assertTrue(payload["verified"])
            self.assertLess(payload["bytes_out"], payload["bytes_in"])
            self.assertIn("exif", "".join(payload["removed"]))


class UsageTests(unittest.TestCase):
    def test_missing_file_exits_2(self):
        r = run("check", "/does/not/exist.jpg")
        self.assertEqual(r.returncode, 2)

    def test_directory_requires_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.jpg", sample_jpeg())
            r = run("check", tmp)
            self.assertEqual(r.returncode, 2)
            r2 = run("check", tmp, "-r")
            self.assertEqual(r2.returncode, 1)

    def test_recursive_walk_only_picks_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.jpg", sample_jpeg())
            write(tmp, "notes.txt", b"hello")
            sub = os.path.join(tmp, "nested")
            os.makedirs(sub)
            write(sub, "b.webp", sample_webp())
            r = run("check", tmp, "-r", "--json")
            payload = json.loads(r.stdout)
            self.assertEqual(len(payload["files"]), 2)

    def test_version_and_help(self):
        self.assertIn("lenswipe 1.0.0", run("--version").stdout)
        help_out = run("--help").stdout
        for word in ("report", "check", "wipe"):
            self.assertIn(word, help_out)
        self.assertIn("--in-place", run("wipe", "--help").stdout)

    def test_no_arguments_exits_nonzero(self):
        self.assertNotEqual(run().returncode, 0)


if __name__ == "__main__":
    unittest.main()