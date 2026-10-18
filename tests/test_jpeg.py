"""JPEG: segments, EXIF decode, stripping."""

import struct
import unittest

from tests import *  # noqa: F401,F403

from lenswipe import jpeg
from lenswipe.synth import (SAMPLE_GPS_IFD, SAMPLE_IFD0, build_exif_segment,
                            build_jpeg, build_tiff, jpeg_segment, sample_jpeg)


class SegmentTests(unittest.TestCase):
    def test_parse_walks_from_soi_to_sos(self):
        data = build_jpeg(jfif=True, exif=False, xmp=True)
        segs = jpeg.parse_segments(data)
        markers = [s.marker for s in segs]
        self.assertEqual(markers, [0xE0, 0xE1, 0xDA])

    def test_entropy_and_eoi_found(self):
        entropy = b"\x11\x22\x33\x44"
        data = build_jpeg(entropy=entropy)
        idx = data.find(entropy)
        eoi = jpeg.find_eoi(data)
        self.assertLess(idx, eoi)
        self.assertEqual(data[eoi:], b"\xff\xd9")

    def test_fill_bytes_are_skipped(self):
        # SOI + FF fill + APP1 marker should still parse
        data = b"\xff\xd8\xff" + jpeg_segment(0xE1, b"Exif\0\0" + build_tiff()) \
            + b"\xff\xd9"
        segs = jpeg.parse_segments(data)
        self.assertTrue(segs)
        self.assertEqual(segs[0].marker, 0xE1)

    def test_not_a_jpeg_raises(self):
        with self.assertRaises(ValueError):
            jpeg.parse_segments(b"PNGBINARY")

    def test_bad_length_raises(self):
        with self.assertRaises(ValueError):
            jpeg.parse_segments(b"\xff\xd8\xff\xe1\x00\x01")   # length < 2

    def test_app0_jfif_and_icc_classified_but_not_default_drop(self):
        data = build_jpeg(jfif=True, icc=True, exif=True)
        blocks, _ = jpeg.classify_jpeg(data)
        kinds = [b.kind for b in blocks]
        self.assertIn("jfif", kinds)
        self.assertIn("icc", kinds)
        self.assertIn("exif", kinds)
        by_kind = {b.kind: b for b in blocks}
        self.assertFalse(by_kind["jfif"].removable_by_default)
        self.assertFalse(by_kind["icc"].removable_by_default)
        self.assertTrue(by_kind["exif"].removable_by_default)


class ExifDecodeTests(unittest.TestCase):
    def test_ifd0_ascii_tags_decode(self):
        tags, has_gps = jpeg.parse_exif_tiff(
            build_exif_segment(make=True, gps=False)[6:])   # drop Exif\0\0
        self.assertFalse(has_gps)
        names = {t.name: t for t in tags}
        self.assertEqual(names["Make"].value, "LenswipeCam")
        self.assertEqual(names["Make"].type_name, "ASCII")
        self.assertEqual(names["Orientation"].value, "1")
        self.assertEqual(names["DateTime"].value, "2026:10:17 09:41:03")
        self.assertEqual(names["Software"].ifd, "IFD0")

    def test_gps_ifd_detected_and_named(self):
        tags, has_gps = jpeg.parse_exif_tiff(build_exif_segment(gps=True)[6:])
        self.assertTrue(has_gps)
        gps_tags = [t for t in tags if t.is_gps]
        names = {t.name for t in gps_tags}
        self.assertIn("GPSLatitude", names)
        self.assertIn("GPSLatitudeRef", names)
        # rationals decode as num/den pairs
        lat = next(t for t in gps_tags if t.name == "GPSLatitude")
        self.assertEqual(lat.value, "51/1 30/1 12/1")
        ref = next(t for t in gps_tags if t.name == "GPSLatitudeRef")
        self.assertEqual(ref.value, "N")
        date = next(t for t in gps_tags if t.name == "GPSDateStamp")
        self.assertEqual(date.value, "2026:10:17")

    def test_exif_sub_ifd_tags(self):
        tags, _ = jpeg.parse_exif_tiff(build_exif_segment(gps=True)[6:])
        exif_tags = [t for t in tags if t.ifd == "Exif"]
        names = {t.name for t in exif_tags}
        self.assertIn("DateTimeOriginal", names)
        self.assertIn("ISOSpeedRatings", names)
        iso = next(t for t in exif_tags if t.name == "ISOSpeedRatings")
        self.assertEqual(iso.value, "200")

    def test_unknown_tag_renders_hex(self):
        tiff = build_tiff(ifd0=((0x9999, 3, 1, struct.pack("<H", 7)),),
                          exif=(), gps=())
        tags, _ = jpeg.parse_exif_tiff(tiff)
        unknown = [t for t in tags if t.name.startswith("tag 0x")]
        self.assertTrue(unknown)
        self.assertEqual(unknown[0].value, "7")

    def test_big_endian_tiff_decodes(self):
        entries = ((0x0112, 3, 1, struct.pack(">H", 6)),)
        tiff = build_tiff(ifd0=entries, exif=False, gps=False, byte_order="MM")
        tags, _ = jpeg.parse_exif_tiff(tiff)
        orient = next(t for t in tags if t.name == "Orientation")
        self.assertEqual(orient.value, "6")

    def test_bad_byte_order_raises(self):
        with self.assertRaises(ValueError):
            jpeg.parse_exif_tiff(b"ZZ\x2a\x00\x00\x00\x00\x08")
        with self.assertRaises(ValueError):
            jpeg.parse_exif_tiff(b"II")
        with self.assertRaises(ValueError):
            jpeg.parse_exif_tiff(b"II\x2a\x00\x00\x00")   # bad magic

    def test_sample_fixture_constants_are_stable(self):
        self.assertEqual(SAMPLE_IFD0[0][3], b"LenswipeCam\0")
        self.assertEqual(SAMPLE_GPS_IFD[1][0], 0x0002)


class StripTests(unittest.TestCase):
    def test_default_drop_removes_exif_xmp_iptc_keeps_jfif_icc(self):
        data = sample_jpeg()
        out = jpeg.strip_jpeg(data, {"exif", "xmp", "xmp-ext", "iptc"})
        blocks, _ = jpeg.classify_jpeg(out)
        kinds = [b.kind for b in blocks]
        self.assertNotIn("exif", kinds)
        self.assertNotIn("xmp", kinds)
        self.assertNotIn("iptc", kinds)
        self.assertIn("jfif", kinds)
        self.assertIn("icc", kinds)

    def test_image_data_is_byte_identical(self):
        entropy = b"\x81\x00\xff\x00\x42\x13"
        data = build_jpeg(entropy=entropy, exif=True, xmp=True, iptc=True)
        out = jpeg.strip_jpeg(data, {"exif", "xmp", "xmp-ext", "iptc"})
        # SOI first, EOI last, entropy blob intact inside
        self.assertTrue(out.startswith(b"\xff\xd8"))
        self.assertTrue(out.endswith(b"\xff\xd9"))
        self.assertIn(entropy, out)
        self.assertLess(len(out), len(data))

    def test_all_meta_drops_jfif_and_icc_too(self):
        data = build_jpeg(jfif=True, icc=True, exif=False, xmp=False)
        out = jpeg.strip_jpeg(data, {"jfif", "icc"})
        segs = jpeg.parse_segments(out)
        self.assertEqual([s.marker for s in segs], [0xDA])

    def test_everything_stripped_sos_still_first_header(self):
        data = build_jpeg(jfif=True, exif=True, xmp=True, iptc=True, icc=True)
        out = jpeg.strip_jpeg(data, {"exif", "xmp", "xmp-ext", "iptc",
                                     "jfif", "icc"})
        segs = jpeg.parse_segments(out)
        self.assertTrue(all(s.marker == 0xDA for s in segs))

    def test_strip_is_idempotent(self):
        data = sample_jpeg()
        once = jpeg.strip_jpeg(data, {"exif", "xmp", "xmp-ext", "iptc"})
        twice = jpeg.strip_jpeg(once, {"exif", "xmp", "xmp-ext", "iptc"})
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()