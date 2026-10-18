"""JPEG: segment walking, EXIF/TIFF tag decode, metadata segment removal.

Only APPn segments are ever touched — SOI/APP0-JFIF/SOS/entropy/EOI are
copied byte-for-byte, so the decoded image cannot change.

Default removal set: APP1 Exif, APP1 XMP, APP13 Photoshop/IPTC, APP2 XMP
extensions. Kept by default: APP0 JFIF (structural) and APP2 ICC color
profiles; `--all` removes those too.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .tags import GPS_TAGS, IFD0_TAGS, TIFF_TYPES, tag_name

SOI = b"\xff\xd8"
EOI = b"\xff\xd9"

SOS = 0xDA
APP0 = 0xE0
APP1 = 0xE1
APP2 = 0xE2
APP13 = 0xED

XMP_APP1_HEADER = b"http://ns.adobe.com/xap/1.0/\0"
XMP_APP2_HEADER = b"http://ns.adobe.com/xmp/extension/\0"
EXIF_HEADER = b"Exif\0\0"
PS_HEADER = b"Photoshop 3.0\0"
JFIF_HEADER = b"JFIF\0"
ICC_HEADER = b"ICC_PROFILE\0"


@dataclass
class Segment:
    offset: int
    marker: int
    payload: bytes                  # excludes the 2-byte length field
    end: int                        # offset just past the segment


@dataclass
class Tag:
    ifd: str
    name: str
    type_name: str
    value: str
    is_gps: bool = False


def parse_segments(data: bytes) -> list[Segment]:
    """Walk JPEG marker segments from SOI up to (excluding) SOS data."""
    if len(data) < 4 or data[:2] != SOI:
        raise ValueError("not a JPEG (missing SOI)")
    segments: list[Segment] = []
    pos = 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            raise ValueError(f"expected marker at offset {pos}")
        marker = data[pos + 1]
        if marker == 0xFF:            # fill bytes
            pos += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            pos += 2                  # standalone markers
            continue
        if marker == 0xD9:
            break
        length = struct.unpack(">H", data[pos + 2:pos + 4])[0]
        if length < 2 or pos + 2 + length > len(data):
            raise ValueError(f"bad segment length at offset {pos}")
        seg_end = pos + 2 + length
        segments.append(Segment(offset=pos, marker=marker,
                                payload=data[pos + 4:seg_end],
                                end=seg_end))
        if marker == SOS:
            break
        pos = seg_end
    return segments


def find_eoi(data: bytes) -> int:
    idx = data.rfind(EOI)
    return idx if idx != -1 else len(data)


# -- EXIF / TIFF decode ------------------------------------------------------


def _decode_value(raw: bytes, type_id: int, count: int, endian: str) -> str:
    type_info = TIFF_TYPES.get(type_id)
    if type_info is None:
        return f"<type {type_id}x{len(raw)}>"
    _type_name, unit = type_info
    need = unit * count
    view = raw[:need] if len(raw) >= need else raw
    if type_id == 2:                                   # ASCII
        return view.split(b"\0")[0].decode("utf-8", "replace")[:80]
    if type_id == 7:                                   # UNDEFINED
        preview = view[:8].hex().upper()
        more = "…" if len(view) > 8 else ""
        return f"<{len(view)} bytes: {preview}{more}>"
    if type_id == 1:                                   # BYTE / GPSVersionID
        return ".".join(str(b) for b in view[:8])
    if type_id in (5, 10):                             # RATIONAL / SRATIONAL
        # TIFF rationals are two 32-bit ints (II / ii), 8 bytes each
        pair = "II" if type_id == 5 else "ii"
        unit_size = 8
        out = []
        for i in range(0, min(len(view), 4 * unit_size), unit_size):
            chunk = view[i:i + unit_size]
            if len(chunk) < unit_size:
                break
            num, den = struct.unpack(endian + pair, chunk)
            out.append(f"{num}/{den}" if den else f"{num}/0")
        if not out:
            return "<empty rational>"
        suffix = f" … (+{count - len(out)})" if count > len(out) else ""
        return " ".join(out) + suffix
    code = {"BYTE": "B", "SHORT": "H", "LONG": "L", "SBYTE": "b",
            "SSHORT": "h", "SLONG": "l", "FLOAT": "f", "DOUBLE": "d"}.get(_type_name)
    if code is None:
        return f"<{len(view)} bytes>"
    size = struct.calcsize(endian + code)
    values = []
    for i in range(min(count, 6)):
        chunk = view[i * size:(i + 1) * size]
        if len(chunk) < size:
            break
        values.append(struct.unpack(endian + code, chunk)[0])
    if not values:
        return "<empty>"
    if count > len(values):
        return " ".join(str(v) for v in values) + f" … (+{count - len(values)})"
    return " ".join(str(v) for v in values)


def parse_exif_tiff(tiff: bytes) -> tuple[list[Tag], bool]:
    """Parse EXIF TIFF payload (after the `Exif\\0\\0` header).

    Returns the tag list and whether a GPS IFD was found.
    """
    tags: list[Tag] = []
    has_gps = False
    if len(tiff) < 8:
        raise ValueError("EXIF payload too short")
    order = tiff[:2]
    if order == b"II":
        endian = "<"
    elif order == b"MM":
        endian = ">"
    else:
        raise ValueError("bad EXIF byte order mark")
    magic = struct.unpack(endian + "H", tiff[2:4])[0]
    if magic != 42:
        raise ValueError(f"bad TIFF magic {magic}")

    def read_ifd(offset: int, label: str, table: dict | None,
                 gps: bool, depth: int = 0) -> None:
        nonlocal has_gps
        if depth > 2 or offset <= 0 or offset + 2 > len(tiff):
            return
        (count,) = struct.unpack_from(endian + "H", tiff, offset)
        pos = offset + 2
        subdirs: list[tuple[int, str, dict | None, bool]] = []
        for _ in range(count):
            if pos + 12 > len(tiff):
                break
            tag, type_id, cnt = struct.unpack_from(endian + "HHI", tiff, pos)
            value_off = pos + 8
            type_info = TIFF_TYPES.get(type_id)
            nbytes = (type_info[1] * cnt) if type_info else 0
            if type_info is None:
                data_bytes = b""
            elif nbytes <= 4:
                data_bytes = tiff[value_off:value_off + nbytes]
            else:
                (abs_off,) = struct.unpack_from(endian + "L", tiff, value_off)
                data_bytes = tiff[abs_off:abs_off + min(nbytes, 4096)]
            name = tag_name(tag, table)
            type_name = type_info[0] if type_info else f"TYPE{type_id}"
            try:
                value = _decode_value(data_bytes, type_id, cnt, endian)
            except (struct.error, IndexError):
                value = "<undecodable>"
            tags.append(Tag(ifd=label, name=name, type_name=type_name,
                            value=value, is_gps=gps))
            if tag == 0x8825 and gps is False:          # GPS IFD pointer
                has_gps = True
                (gps_off,) = struct.unpack_from(endian + "L", tiff, value_off)
                subdirs.append((gps_off, "GPS", GPS_TAGS, True))
            elif tag == 0x8769 and gps is False:        # Exif IFD pointer
                (sub_off,) = struct.unpack_from(endian + "L", tiff, value_off)
                subdirs.append((sub_off, "Exif", EXIF_TABLE, False))
            pos += 12
        for sub_offset, label, table, is_gps in subdirs:
            read_ifd(sub_offset, label, table, is_gps, depth + 1)

    (ifd0,) = struct.unpack_from(endian + "L", tiff, 4)
    read_ifd(ifd0, "IFD0", IFD0_TAGS, False)
    return tags, has_gps


# imported late to avoid a cycle at module import time in EXIF_TABLE
from .tags import EXIF_TAGS as EXIF_TABLE  # noqa: E402


@dataclass
class JpegBlock:
    kind: str           # exif | xmp | iptc | xmp-ext | icc | jfif
    offset: int
    size: int           # whole segment incl. marker + length
    removable_by_default: bool
    tags: list[Tag] = field(default_factory=list)
    has_gps: bool = False
    note: str = ""


def classify_jpeg(data: bytes) -> tuple[list[JpegBlock], list[Segment]]:
    """Inventory of metadata-bearing segments + the raw segment list."""
    segments = parse_segments(data)
    blocks: list[JpegBlock] = []
    for seg in segments:
        seg_size = seg.end - seg.offset
        p = seg.payload
        if seg.marker == APP1 and p.startswith(EXIF_HEADER):
            tags, gps = parse_exif_tiff(p[6:])
            blocks.append(JpegBlock("exif", seg.offset, seg_size, True,
                                    tags, gps, "APP1/Exif"))
        elif seg.marker == APP1 and p.startswith(XMP_APP1_HEADER):
            blocks.append(JpegBlock("xmp", seg.offset, seg_size, True, [],
                                    False, f"APP1/XMP {len(p)} bytes"))
        elif seg.marker == APP2 and p.startswith(XMP_APP2_HEADER):
            blocks.append(JpegBlock("xmp-ext", seg.offset, seg_size, True,
                                    [], False, "APP2/XMP packet"))
        elif seg.marker == APP13 and p.startswith(PS_HEADER):
            blocks.append(JpegBlock("iptc", seg.offset, seg_size, True,
                                    [], False, "APP13/Photoshop-IPTC"))
        elif seg.marker == APP0 and p.startswith(JFIF_HEADER):
            blocks.append(JpegBlock("jfif", seg.offset, seg_size, False,
                                    [], False, "APP0/JFIF (structural)"))
        elif seg.marker == APP2 and p.startswith(ICC_HEADER):
            blocks.append(JpegBlock("icc", seg.offset, seg_size, False,
                                    [], False, "APP2/ICC profile"))
    return blocks, segments


def strip_jpeg(data: bytes, drop_kinds: set[str]) -> bytes:
    """Return JPEG bytes with the marked segments removed; image data is
    copied verbatim from SOI through SOS onwards."""
    segments = parse_segments(data)
    drop: set[int] = {b.offset for b in classify_jpeg(data)[0]
                      if b.kind in drop_kinds}
    out = bytearray()
    out += SOI
    eoi = find_eoi(data)
    cursor = 2
    sos_end = len(data)
    for seg in segments:
        if seg.marker == SOS:
            sos_end = seg.offset
            break
    # header region: SOI .. SOS (with drops applied)
    for seg in segments:
        if seg.offset < sos_end and seg.offset not in drop:
            out += data[seg.offset:seg.end]
        cursor = max(cursor, seg.end)
    # entropy-coded data .. EOI verbatim
    out += data[sos_end:eoi]
    out += EOI
    return bytes(out)