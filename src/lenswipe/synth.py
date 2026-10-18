"""Synthetic image builders: hand-rolled JPEG/PNG/WebP bytes with known
metadata, shared by the test suite and ``tools/make_examples.py``.

Every builder returns exact bytes: containers are assembled from the specs
(RIFF sizes, PNG CRCs, TIFF offsets) so the resulting files are structurally
genuine even though the entropy/IDAT payloads are empty placeholders.
"""

from __future__ import annotations

import struct
import zlib

# -- JPEG --------------------------------------------------------------


def jpeg_segment(marker: int, payload: bytes) -> bytes:
    return bytes([0xFF, marker]) + struct.pack(">H", len(payload) + 2) + payload


def build_exif_segment(*, make=True, gps=True, extra_ifd0=()) -> bytes:
    """APP1 segment: `b'Exif\\0\\0'` + TIFF built by build_tiff()."""
    entries = list(extra_ifd0)
    base = SAMPLE_IFD0 if make else tuple(e for e in SAMPLE_IFD0
                                          if e[0] != 0x010F)
    entries = tuple(extra_ifd0) + base
    return b"Exif\0\0" + build_tiff(ifd0=entries, gps=gps)


def build_jpeg(*, jfif=True, exif=True, xmp=True, xmp_ext=False, iptc=False,
               icc=False, entropy: bytes = b"\x81\xe3\x02\xc4\xff\xd9") -> bytes:
    parts = [b"\xff\xd8"]                                    # SOI
    if jfif:
        parts.append(jpeg_segment(0xE0, b"JFIF\0" + bytes([1, 2, 0, 0, 1, 0, 1, 0, 0])))
    if exif:
        parts.append(jpeg_segment(0xE1, build_exif_segment()))
    if xmp:
        parts.append(jpeg_segment(0xE1, b"http://ns.adobe.com/xap/1.0/\0"
                                  + b"<x:xmpmeta>lenswipe demo</x:xmpmeta>"))
    if xmp_ext:
        parts.append(jpeg_segment(0xE2, b"http://ns.adobe.com/xmp/extension/\0"
                                  + b"\x00\x00\x00\x00"))
    if icc:
        parts.append(jpeg_segment(0xE2, b"ICC_PROFILE\0" + bytes([1, 1]) + b"\x00" * 8))
    if iptc:
        parts.append(jpeg_segment(0xED, b"Photoshop 3.0\0"
                                  + b"8BIM" + struct.pack(">H", 0x0404)
                                  + b"\x00" + bytes([5]) + struct.pack(">H", 4) + b"demo"))
    parts.append(jpeg_segment(0xDA, b"\x00"))                # SOS header
    parts.append(entropy)
    parts.append(b"\xff\xd9")                                # EOI
    return b"".join(parts)


def sample_jpeg() -> bytes:
    """The 'with everything' sample used across tests and examples."""
    return build_jpeg(jfif=True, exif=True, xmp=True, xmp_ext=True,
                      iptc=True, icc=True)


# -- TIFF / EXIF payload ------------------------------------------------

# default IFD0 + GPS IFD used by sample images (EXIF header excluded)
SAMPLE_IFD0 = (
    (0x010F, 2, 12, b"LenswipeCam\0"),          # Make
    (0x0110, 2, 16, b"PocketTracer X1\0"),      # Model
    (0x0131, 2, 10, b"stampfw1\0"),             # Software
    (0x0132, 2, 20, b"2026:10:17 09:41:03\0"),  # DateTime
    (0x0112, 3, 1, struct.pack("<H", 1)),       # Orientation
)
SAMPLE_EXIF_IFD = (
    (0x8602, 5, 1, struct.pack("<II", 250, 10)),  # (filters on Format)
    (0x9003, 2, 20, b"2026:10:17 09:41:03\0"),    # DateTimeOriginal
    (0x8827, 3, 1, struct.pack("<H", 200)),       # ISOSpeedRatings
)
SAMPLE_GPS_IFD = (
    (0x0001, 2, 2, b"N\0"),                                    # GPSLatitudeRef
    (0x0002, 5, 3, struct.pack("<6I", 51, 1, 30, 1, 12, 1)),   # GPSLatitude
    (0x0003, 2, 2, b"W\0"),                                    # GPSLongitudeRef
    (0x0004, 5, 3, struct.pack("<6I", 0, 1, 7, 1, 55, 1)),     # GPSLongitude
    (0x0007, 5, 3, struct.pack("<6I", 9, 1, 41, 1, 22, 1)),    # GPSTimeStamp
    (0x001D, 2, 11, b"2026:10:17\0"),                          # GPSDateStamp
)


def _ifd_size(n: int) -> int:
    return 2 + 12 * n + 4


def _emit_ifd(entries, data_start: int, next_ptr: int = 0,
               endian: str = "<") -> bytes:
    """One IFD: entry directory followed by its out-of-line value area."""
    body = bytearray(struct.pack(endian + "H", len(entries)))
    area = bytearray()
    cursor = data_start
    for tag, type_id, count, value in entries:
        body += struct.pack(endian + "HHI", tag, type_id, count)
        if len(value) <= 4:
            body += value + b"\0" * (4 - len(value))
        else:
            body += struct.pack(endian + "I", cursor)
            area += value
            cursor += len(value)
    body += struct.pack(endian + "I", next_ptr)
    return bytes(body) + bytes(area)


def build_tiff(*, ifd0=None, exif=None, gps=None, byte_order="II") -> bytes:
    """Bare TIFF payload (no `Exif\\0\\0` header): IFD0 [+Exif IFD] [+GPS IFD]."""
    def _sub(spec, sample):
        if spec is None or spec is True:
            return sample
        if spec is False:
            return ()
        return spec

    exif_ifd = _sub(exif, SAMPLE_EXIF_IFD)
    gps_ifd = _sub(gps, SAMPLE_GPS_IFD)

    entries0 = list(SAMPLE_IFD0 if ifd0 is None else ifd0)
    if exif_ifd:
        entries0.append((0x8769, 4, 1, b"\0\0\0\0"))   # placeholder, real off below
    if gps_ifd:
        entries0.append((0x8825, 4, 1, b"\0\0\0\0"))

    header_len = 8
    ool0 = sum(len(v) for *_x, v in entries0 if len(v) > 4)
    ifd0_data_start = header_len + _ifd_size(len(entries0))
    exif_start = ifd0_data_start + ool0
    gps_start = exif_start + (_ifd_size(len(exif_ifd))
                              + sum(len(v) for *_x, v in exif_ifd if len(v) > 4)
                              if exif_ifd else 0)

    # patch the placeholder pointers
    back = "<" if byte_order == "II" else ">"
    patched = []
    for tag, type_id, count, value in entries0:
        if tag == 0x8769:
            value = struct.pack(back + "I", exif_start)
        elif tag == 0x8825:
            value = struct.pack(back + "I", gps_start)
        patched.append((tag, type_id, count, value))

    parts = []
    if byte_order == "II":
        parts.append(b"II" + struct.pack("<H", 42) + struct.pack("<I", 8))
    else:
        parts.append(b"MM" + struct.pack(">H", 42) + struct.pack(">I", 8))
    parts.append(_emit_ifd(patched, ifd0_data_start, endian=back))
    if exif_ifd:
        parts.append(_emit_ifd(exif_ifd, exif_start + _ifd_size(len(exif_ifd)),
                               endian=back))
    if gps_ifd:
        parts.append(_emit_ifd(gps_ifd, gps_start + _ifd_size(len(gps_ifd)),
                               endian=back))
    return b"".join(parts)


# -- PNG -----------------------------------------------------------------


def png_chunk(ctype: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(payload, zlib.crc32(ctype)) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + ctype + payload + struct.pack(">I", crc)


def build_png(texts: dict[str, str] | None = None, *, itxt=None, ztxt=None,
              exif: bool = False, phys: bool = True,
              idat: bytes = b"\x00\x00\x00\x00") -> bytes:
    parts = [b"\x89PNG\r\n\x1a\n"]
    parts.append(png_chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)))
    if phys:
        parts.append(png_chunk(b"pHYs", struct.pack(">IIB", 2835, 2835, 1)))
    for kw, value in (texts or {}).items():
        parts.append(png_chunk(b"tEXt", kw.encode() + b"\0" + value.encode()))
    for kw, value in (ztxt or {}).items():
        parts.append(png_chunk(b"zTXt", kw.encode() + b"\0\0"
                               + zlib.compress(value.encode())))
    if itxt:
        kw, value = itxt
        parts.append(png_chunk(b"iTXt", kw.encode() + b"\0\0\0\0\0"
                               + value.encode()))
    if exif:
        parts.append(png_chunk(b"eXIf", build_tiff()))
    parts.append(png_chunk(b"IDAT", idat))
    parts.append(png_chunk(b"IEND", b""))
    return b"".join(parts)


def sample_png() -> bytes:
    return build_png(
        texts={"Comment": "shot on the trail", "Author": "Wsh7Ash"},
        itxt=("Description", "summit panorama"),
        ztxt={"XML:com.adobe.xmp": 'x:xmpmeta{"gps":"51.5W"}'},
        exif=True, phys=True)


# -- WebP ----------------------------------------------------------------


def riff_chunk(fourcc: bytes, payload: bytes) -> bytes:
    out = fourcc + struct.pack("<I", len(payload)) + payload
    if len(payload) & 1:
        out += b"\0"
    return out


def build_webp(*, icc=False, alpha=False, exif=True, xmp=True,
               vp8_payload: bytes = b"\x9d\x01\x2a" + b"\x00" * 12) -> bytes:
    flags = 0
    if icc:
        flags |= 0x20
    if alpha:
        flags |= 0x10
    if exif:
        flags |= 0x08
    if xmp:
        flags |= 0x04
    body = bytearray()
    has_extended = bool(flags) or True   # canvas always advertised by VP8X here
    if has_extended:
        vp8x = bytes([flags, 0, 0, 0])                 # flags + 3 reserved bits
        vp8x += struct.pack("<I", (8 - 1) | ((8 - 1) << 12))  # canvas w-1,h-1 packed
        body += riff_chunk(b"VP8X", vp8x[:10])
    if icc:
        body += riff_chunk(b"ICCP", b"\x00" * 16)
    if exif:
        body += riff_chunk(b"EXIF", b"Exif\0\0" + build_tiff())
    if xmp:
        body += riff_chunk(b"XMP ", b"<x:xmpmeta>demo</x:xmpmeta>")
    body += riff_chunk(b"VP8 ", vp8_payload)
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WEBP" + bytes(body)


def sample_webp(**kw) -> bytes:
    return build_webp(**kw)


# convenience samples used by tests           (stable fixture names)
def sample_jpeg_plain() -> bytes:
    return build_jpeg(jfif=True, exif=False, xmp=False)