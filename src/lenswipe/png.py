"""PNG: chunk inventory, CRC verification and metadata chunk removal.

Chunk CRCs are verified on read; dropped chunks take their CRC with them and
kept chunks are copied byte-for-byte, so no CRC ever needs recomputing.

Default removal set: tEXt, zTXt, iTXt, eXIf. `--all` additionally removes
ancillary presentation chunks (pHYs, gAMA, cHRM, sRGB, tIME, bKGD, sBIT,
sPLT, hIST, pHYs… any chunk whose type starts lowercase and is not IDAT/PLTE).
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

DEFAULT_METADATA_TYPES = {"tEXt", "zTXt", "iTXt", "eXIf"}

# always structural: image cannot exist without these
STRUCTURAL = {"IHDR", "PLTE", "IDAT", "IEND"}
# ancillary presentation chunks dropped only with --all
# (implemented dynamically: see _is_droppable)


@dataclass
class PngChunk:
    offset: int
    type: str
    length: int        # 12 + data length
    crc_ok: bool
    data: bytes = b""


@dataclass
class TextEntry:
    keyword: str
    value: str


def parse_chunks(data: bytes, keep_data: bool = False) -> list[PngChunk]:
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("not a PNG (bad signature)")
    chunks: list[PngChunk] = []
    pos = len(PNG_SIGNATURE)
    while pos + 12 <= len(data):
        (length,) = struct.unpack_from(">I", data, pos)
        ctype = data[pos + 4:pos + 8].decode("latin-1")
        data_start = pos + 8
        data_end = data_start + length
        crc_end = data_end + 4
        if crc_end > len(data):
            raise ValueError(f"truncated chunk {ctype} at offset {pos}")
        payload = data[data_start:data_end]
        (stored_crc,) = struct.unpack_from(">I", data, data_end)
        calc = zlib.crc32(ctype.encode("latin-1")) & 0xFFFFFFFF
        calc = zlib.crc32(payload, calc) & 0xFFFFFFFF
        chunks.append(PngChunk(offset=pos, type=ctype, length=12 + length,
                               crc_ok=stored_crc == calc,
                               data=payload if keep_data else payload))
        pos = crc_end
        if ctype == "IEND":
            break
    return chunks


def read_text_entries(data: bytes) -> list[TextEntry]:
    entries: list[TextEntry] = []
    try:
        chunks = parse_chunks(data, keep_data=True)
    except ValueError:
        return entries
    for c in chunks:
        try:
            if c.type == "tEXt":
                kw, _, value = c.data.partition(b"\0")
                entries.append(TextEntry(kw.decode("latin-1"),
                                         value.decode("latin-1", "replace")))
            elif c.type == "zTXt":
                kw, _, rest = c.data.partition(b"\0")
                comp = rest[1:] if rest[:1] == b"\0" else rest
                value = zlib.decompress(comp)
                entries.append(TextEntry(kw.decode("latin-1"),
                                         value.decode("latin-1", "replace")))
            elif c.type == "iTXt":
                kw, _, rest = c.data.partition(b"\0")
                comp_flag = rest[:1]
                comp_method = rest[1:2]
                lang_and_rest = rest[2:]
                _lang, _, rest2 = lang_and_rest.partition(b"\0")
                _translated, _, value_bytes = rest2.partition(b"\0")
                if comp_flag == b"\x01":
                    value = zlib.decompress(value_bytes)
                else:
                    value = value_bytes
                entries.append(TextEntry(kw.decode("latin-1"),
                                         value.decode("utf-8", "replace")))
        except (zlib.error, IndexError, ValueError):
            entries.append(TextEntry("<undecodable chunk>", c.type))
    return entries


@dataclass
class PngTextBlock:
    kind: str                 # text | exif | presentation
    offset: int
    size: int
    removable_by_default: bool
    entries: list[TextEntry] = field(default_factory=list)
    note: str = ""


def _is_droppable_ancillary(t: str) -> bool:
    # ancillary chunk = first char lowercase; never structural, never data*
    if t in STRUCTURAL:
        return False
    return t[0].islower()


def classify_png(data: bytes) -> list[PngTextBlock]:
    blocks: list[PngTextBlock] = []
    for c in parse_chunks(data, keep_data=True):
        if c.type in DEFAULT_METADATA_TYPES:
            entries = read_text_entries(data) if c.type != "eXIf" else []
            kind = "text" if c.type != "eXIf" else "exif"
            block = PngTextBlock("text" if kind == "text" else "exif",
                                 c.offset, c.length, True, entries,
                                 f"chunk {c.type}")
            if kind == "exif":
                block.entries = []
            blocks.append(block)
        elif c.type == "eXIf":
            pass  # handled above
        elif _is_droppable_ancillary(c.type):
            blocks.append(PngTextBlock("presentation", c.offset, c.length,
                                       False, [], f"chunk {c.type}"))
    return blocks


def classify_png_exif_tags(data: bytes) -> list:
    """Decode tags of an eXIf chunk (PNG stores a bare TIFF payload)."""
    from .jpeg import parse_exif_tiff
    for c in parse_chunks(data, keep_data=True):
        if c.type == "eXIf":
            try:
                tags, gps = parse_exif_tiff(c.data)
                return tags
            except ValueError:
                return []
    return []


def png_has_gps(data: bytes) -> bool:
    from .jpeg import parse_exif_tiff
    for c in parse_chunks(data, keep_data=True):
        if c.type == "eXIf":
            try:
                _tags, gps = parse_exif_tiff(c.data)
                if gps:
                    return True
            except ValueError:
                continue
    return False


def strip_png(data: bytes, drop_types: set[str]) -> bytes:
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("not a PNG (bad signature)")
    out = bytearray(PNG_SIGNATURE)
    pos = len(PNG_SIGNATURE)
    while pos + 12 <= len(data):
        (length,) = struct.unpack_from(">I", data, pos)
        ctype = data[pos + 4:pos + 8].decode("latin-1")
        end = pos + 12 + length
        if end > len(data):
            raise ValueError(f"truncated chunk {ctype}")
        if ctype not in drop_types:
            out += data[pos:end]
        pos = end
        if ctype == "IEND":
            break
    if pos < len(data):
        out += data[pos:]          # trailing junk: keep rather than lose bytes
    return bytes(out)