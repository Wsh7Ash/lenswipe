"""PNG: chunks, text decoding, CRC handling, stripping."""

import struct
import unittest
import zlib

from tests import *  # noqa: F401,F403

from lenswipe import png
from lenswipe.synth import build_png, build_tiff, png_chunk, sample_png


class ChunkTests(unittest.TestCase):
    def test_chunk_walk_and_crc(self):
        data = build_png(texts={"Comment": "hi"})
        chunks = png.parse_chunks(data, keep_data=True)
        types = [c.type for c in chunks]
        self.assertEqual(types, ["IHDR", "pHYs", "tEXt", "IDAT", "IEND"])
        self.assertTrue(all(c.crc_ok for c in chunks))

    def test_crc_mismatch_flagged(self):
        data = bytearray(build_png(texts={"A": "b"}))
        # corrupt one byte inside the tEXt payload (after type bytes)
        idx = data.find(b"tEXt") + 6
        data[idx] ^= 0xFF
        chunks = png.parse_chunks(bytes(data), keep_data=True)
        text = next(c for c in chunks if c.type == "tEXt")
        self.assertFalse(text.crc_ok)

    def test_not_a_png_raises(self):
        with self.assertRaises(ValueError):
            png.parse_chunks(b"\xff\xd8\xff\xd8")

    def test_truncated_chunk_raises(self):
        data = build_png(texts={"A": "b"})[:24]
        with self.assertRaises(ValueError):
            png.parse_chunks(data)

    def test_text_decoders_all_three_kinds(self):
        data = build_png(texts={"Comment": "plain one"},
                         ztxt={"Keywords": "trail, photo"},
                         itxt=("Description", "long text ünïcode"))
        entries = {e.keyword: e.value for e in png.read_text_entries(data)}
        self.assertEqual(entries["Comment"], "plain one")
        self.assertEqual(entries["Keywords"], "trail, photo")
        self.assertEqual(entries["Description"], "long text ünïcode")

    def test_compressed_itxt_round_trip(self):
        payload = zlib.compress("compressed itxt body".encode())
        chunk = png_chunk(b"iTXt", b"Key\0\x01\0\0\0" + payload)
        data = b"\x89PNG\r\n\x1a\n" + chunk
        # parser expects a full file; embed inside a genuine frame instead
        data = build_png()
        # rebuild the file with our compressed iTXt between IHDR and IDAT
        base = build_png()
        idat_at = base.find(b"IDAT") - 4
        data = base[:idat_at] + chunk + base[idat_at:]
        entries = {e.keyword: e.value for e in png.read_text_entries(data)}
        self.assertEqual(entries["Key"], "compressed itxt body")


class ClassifyTests(unittest.TestCase):
    def test_default_blocks(self):
        blocks = png.classify_png(sample_png())
        kinds = sorted(b.kind for b in blocks)
        self.assertIn("text", kinds)
        self.assertIn("exif", kinds)
        self.assertIn("presentation", kinds)   # pHYs, visible without --all
        by_kind_pos = {b.offset: b.kind for b in blocks}
        self.assertTrue(by_kind_pos)
        phys = next(b for b in blocks if b.note == "chunk pHYs")
        self.assertFalse(phys.removable_by_default)

    def test_exif_chunk_tags_and_gps(self):
        tags = png.classify_png_exif_tags(sample_png())
        self.assertTrue(tags)
        self.assertEqual(tags[0].name, "Make")
        self.assertTrue(any(t.name == "DateTimeOriginal" for t in tags))
        self.assertTrue(png.png_has_gps(sample_png()))
        self.assertFalse(png.png_has_gps(build_png(texts={"A": "b"})))

    def test_text_entries_surface_on_blocks(self):
        blocks = png.classify_png(build_png(texts={"Comment": "hey"}))
        text = next(b for b in blocks if b.kind == "text")
        self.assertEqual(text.entries[0].keyword, "Comment")
        self.assertEqual(text.entries[0].value, "hey")


class StripTests(unittest.TestCase):
    def test_default_strip_keeps_structure(self):
        data = sample_png()
        out = png.strip_png(data, set(png.DEFAULT_METADATA_TYPES))
        types = [c.type for c in png.parse_chunks(out)]
        self.assertEqual(types[0], "IHDR")
        self.assertEqual(types[-1], "IEND")
        self.assertIn("IDAT", types)
        self.assertNotIn("tEXt", types)
        self.assertNotIn("zTXt", types)
        self.assertNotIn("iTXt", types)
        self.assertNotIn("eXIf", types)

    def test_keep_chunks_are_byte_identical(self):
        data = sample_png()
        out = png.strip_png(data, {"tEXt"})
        # IDAT chunk bytes must survive untouched
        i_idat = data.find(b"IDAT") - 4
        crc_end = i_idat + 12 + struct.unpack(">I", data[i_idat:i_idat + 4])[0]
        self.assertEqual(out.find(data[i_idat:crc_end]) != -1, True)

    def test_all_meta_drops_phys_too(self):
        data = build_png(texts={"A": "b"}, phys=True)
        drop = set(png.DEFAULT_METADATA_TYPES) | {t for c in png.parse_chunks(data)
                                                  if png._is_droppable_ancillary(c.type)
                                                  for t in (c.type,)}
        out = png.strip_png(data, drop)
        types = [c.type for c in png.parse_chunks(out)]
        self.assertNotIn("pHYs", types)
        self.assertEqual(types, ["IHDR", "IDAT", "IEND"])

    def test_trailing_bytes_preserved(self):
        data = build_png(texts={"A": "b"}) + b"\x00TAIL"
        out = png.strip_png(data, set(png.DEFAULT_METADATA_TYPES))
        self.assertTrue(out.endswith(b"\x00TAIL"))

    def test_non_png_raises_at_strip(self):
        with self.assertRaises(ValueError):
            png.strip_png(b"JUNKJUNK", {"tEXt"})

    def test_strip_idempotent(self):
        data = sample_png()
        once = png.strip_png(data, set(png.DEFAULT_METADATA_TYPES))
        twice = png.strip_png(once, set(png.DEFAULT_METADATA_TYPES))
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()