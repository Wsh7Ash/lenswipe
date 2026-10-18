"""WebP: RIFF parsing, extension flag maintenance, stripping."""

import struct
import unittest

from tests import *  # noqa: F401,F403

from lenswipe import webp
from lenswipe.synth import build_webp, riff_chunk, sample_webp


def riffs(data: bytes) -> list[tuple[str, int]]:
    return [(c.fourcc, c.size) for c in webp.parse_riff(data)]


class ParseTests(unittest.TestCase):
    def test_chunks_walk(self):
        data = sample_webp(icc=True, alpha=True)
        fourccs = [f for f, _s in riffs(data)]
        self.assertEqual(fourccs, ["VP8X", "ICCP", "EXIF", "XMP ", "VP8 "])

    def test_riff_sizes_are_consistent(self):
        data = sample_webp()
        (declared,) = struct.unpack_from("<I", data, 4)
        self.assertEqual(declared, len(data) - 8)   # everything after the size field

    def test_odd_payload_padding(self):
        data = build_webp(exif=False, xmp=False,
                          vp8_payload=b"odd")   # 3 bytes + pad byte
        chunks = webp.parse_riff(data)
        vp8 = next(c for c in chunks if c.fourcc == "VP8 ")
        self.assertEqual(vp8.size, 8 + 4)        # padded to even
        self.assertTrue(data.endswith(b"odd\0"))

    def test_not_webp_raises(self):
        with self.assertRaises(ValueError):
            webp.parse_riff(b"RIFF0000WAVEfmt ")
        with self.assertRaises(ValueError):
            webp.parse_riff(b"\x89PNG\r\n\x1a\n")

    def test_vp8x_flags_reflect_features(self):
        flags = webp.read_vp8x_flags(sample_webp(icc=True, exif=True, xmp=True))
        self.assertEqual(flags & webp.FLAG_ICC, webp.FLAG_ICC)
        self.assertEqual(flags & webp.FLAG_EXIF, webp.FLAG_EXIF)
        self.assertEqual(flags & webp.FLAG_XMP, webp.FLAG_XMP)

    def test_classify_finds_exif_with_gps(self):
        views, _flags, _chunks = webp.classify_webp(sample_webp())
        kinds = [v.kind for v in views]
        self.assertIn("exif", kinds)
        self.assertIn("xmp", kinds)
        exif = next(v for v in views if v.kind == "exif")
        self.assertTrue(exif.has_gps)
        self.assertTrue(any(t.name == "Make" for t in exif.tags))

    def test_exif_chunk_with_and_without_exif00_prefix(self):
        from lenswipe.synth import build_tiff
        bare = build_webp(exif=True, xmp=False)
        # rebuild with a bare TIFF (no Exif\0\0) payload
        chunks = webp.parse_riff(bare)
        body = bytearray()
        for c in chunks:
            payload = build_tiff() if c.fourcc == "EXIF" else c.data
            body += c.fourcc.encode() + struct.pack("<I", len(payload)) + payload
            if len(payload) & 1:
                body += b"\0"
        data = b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WEBP" + bytes(body)
        views, _f, _c = webp.classify_webp(data)
        exif = next(v for v in views if v.kind == "exif")
        self.assertTrue(any(t.name == "Make" for t in exif.tags))


class StripTests(unittest.TestCase):
    def test_exif_and_xmp_removed_and_flags_cleared(self):
        data = sample_webp(icc=True, alpha=True, exif=True, xmp=True)
        flags_before = webp.read_vp8x_flags(data)
        self.assertEqual(flags_before & webp.FLAG_EXIF, webp.FLAG_EXIF)
        self.assertEqual(flags_before & webp.FLAG_XMP, webp.FLAG_XMP)

        out = webp.strip_webp(data, {"EXIF", "XMP "})
        fourccs = [f for f, _s in riffs(out)]
        self.assertNotIn("EXIF", fourccs)
        self.assertNotIn("XMP ", fourccs)
        self.assertIn("ICCP", fourccs)
        self.assertIn("VP8 ", fourccs)

        flags_after = webp.read_vp8x_flags(out)
        self.assertEqual(flags_after & webp.FLAG_EXIF, 0)
        self.assertEqual(flags_after & webp.FLAG_XMP, 0)
        self.assertEqual(flags_after & webp.FLAG_ICC, webp.FLAG_ICC)
        self.assertEqual(flags_after & webp.FLAG_ALPHA, webp.FLAG_ALPHA)

    def test_riff_size_recomputed(self):
        data = sample_webp()
        out = webp.strip_webp(data, {"EXIF", "XMP "})
        (declared,) = struct.unpack_from("<I", out, 4)
        self.assertEqual(declared, len(out) - 8)
        self.assertLess(len(out), len(data))

    def test_icc_only_dropped_with_all(self):
        data = sample_webp(icc=True)
        kept = webp.strip_webp(data, {"EXIF", "XMP "})
        self.assertIn("ICCP", [f for f, _s in riffs(kept)])
        dropped = webp.strip_webp(kept, {"ICCP"})
        self.assertNotIn("ICCP", [f for f, _s in riffs(dropped)])
        # VP8 + VP8X still present: container remains a valid webp
        self.assertTrue(webp.is_webp(dropped))
        self.assertEqual(dropped[:4], b"RIFF")

    def test_strip_idempotent(self):
        data = sample_webp()
        once = webp.strip_webp(data, {"EXIF", "XMP "})
        twice = webp.strip_webp(once, {"EXIF", "XMP "})
        self.assertEqual(once, twice)

    def test_payload_is_recognized_after_pad(self):
        # even a VP8X-less simple webp strips gracefully (no flags to clear)
        body = riff_chunk(b"VP8 ", b"\x30\x01\x00\x9d")
        data = b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WEBP" + body
        out = webp.strip_webp(data, {"EXIF", "XMP "})
        self.assertEqual(out, data)


if __name__ == "__main__":
    unittest.main()