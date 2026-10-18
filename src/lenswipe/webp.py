"""WebP: RIFF chunk inventory, EXIF/XMP removal, VP8X flag maintenance.

The extended-header flag byte (VP8X) advertises which optional chunks exist:
ICC 0x20, Alpha 0x10, EXIF 0x08, XMP 0x04, Animation 0x02. Stripping the
EXIF/XMP chunks must also clear their bits, otherwise readers look for chunks
that are no longer there.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

RIFF_HEADER = b"RIFF"
WEBP_FOURCC = b"WEBP"

FLAG_ICC = 0x20
FLAG_ALPHA = 0x10
FLAG_EXIF = 0x08
FLAG_XMP = 0x04
FLAG_ANIM = 0x02

METADATA_FOURCCS = {"EXIF", "XMP "}


@dataclass
class RiffChunk:
    fourcc: str
    offset: int
    size: int                  # on disk: 8 + payload + pad
    data: bytes = b""


@dataclass
class ExifChunkView:
    kind: str        # exif | xmp
    offset: int
    size: int
    removable_by_default: bool
    tags: list = field(default_factory=list)
    has_gps: bool = False
    note: str = ""


def is_webp(data: bytes) -> bool:
    return len(data) >= 12 and data[:4] == RIFF_HEADER and data[8:12] == WEBP_FOURCC


def parse_riff(data: bytes) -> list[RiffChunk]:
    if not is_webp(data):
        raise ValueError("not a WebP file")
    (riff_size,) = struct.unpack_from("<I", data, 4)
    pos = 12
    end = min(len(data), 8 + riff_size)
    chunks: list[RiffChunk] = []
    while pos + 8 <= end:
        fourcc = data[pos:pos + 4].decode("latin-1")
        (size,) = struct.unpack_from("<I", data, pos + 4)
        payload = data[pos + 8:pos + 8 + size]
        padded = size + (size & 1)
        if pos + 8 + padded > len(data):
            raise ValueError(f"truncated chunk {fourcc!r} at {pos}")
        chunks.append(RiffChunk(fourcc=fourcc, offset=pos, size=8 + padded,
                                data=payload))
        pos += 8 + padded
    return chunks


def _tiff_payload(raw: bytes) -> bytes:
    return raw[6:] if raw.startswith(b"Exif\0\0") else raw


def classify_webp(data: bytes) -> tuple[list[ExifChunkView], dict[str, int], list[RiffChunk]]:
    """Return (metadata views, VP8X flag byte by offset, riff chunks)."""
    from .jpeg import parse_exif_tiff
    views: list[ExifChunkView] = []
    vp8x_flags: dict[str, int] = {}
    chunks = parse_riff(data)
    for i, c in enumerate(chunks):
        if c.fourcc == "VP8X" and len(c.data) >= 1:
            vp8x_flags[str(i)] = c.data[0]
        elif c.fourcc == "EXIF":
            tags, gps = [], False
            try:
                tags, gps = parse_exif_tiff(_tiff_payload(c.data))
            except ValueError:
                pass
            views.append(ExifChunkView("exif", c.offset, c.size, True,
                                       tags, gps, f"chunk EXIF {c.size} bytes"))
        elif c.fourcc == "XMP ":
            views.append(ExifChunkView("xmp", c.offset, c.size, True,
                                       [], False, f"chunk XMP {c.size} bytes"))
        elif c.fourcc == "ICCP":
            views.append(ExifChunkView("icc", c.offset, c.size, False,
                                       [], False, "chunk ICCP"))
    return views, vp8x_flags, chunks


def strip_webp(data: bytes, drop_fourccs: set[str]) -> bytes:
    chunks = parse_riff(data)
    # VP8X flag maintenance FIRST (execution order matters — see module doc)
    flags = None
    for c in chunks:
        if c.fourcc == "VP8X" and len(c.data) >= 1:
            flags = bytearray(c.data)
            break

    drop_offsets = {c.offset for c in chunks if c.fourcc in drop_fourccs}
    if flags is not None:
        if "EXIF" in drop_fourccs:
            flags[0] &= ~FLAG_EXIF & 0xFF
        if "XMP " in drop_fourccs:
            flags[0] &= ~FLAG_XMP & 0xFF

    body = bytearray()
    for c in chunks:
        if c.offset in drop_offsets:
            continue
        payload = bytes(flags) if (flags is not None and c.fourcc == "VP8X") \
            else c.data
        body += c.fourcc.encode("latin-1")
        body += struct.pack("<I", len(payload))
        body += payload
        if len(payload) & 1:
            body += b"\0"

    out = bytearray()
    out += RIFF_HEADER
    out += struct.pack("<I", 4 + len(body))   # size: 'WEBP' + body
    out += WEBP_FOURCC
    out += body
    # keep any bytes past the declared RIFF size? none: RIFF is the container
    return bytes(out)


def read_vp8x_flags(data: bytes) -> int | None:
    for c in parse_riff(data):
        if c.fourcc == "VP8X" and len(c.data) >= 1:
            return c.data[0]
    return None