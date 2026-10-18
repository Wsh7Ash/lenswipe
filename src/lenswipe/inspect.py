"""Unified inventory: detect the container and collect metadata blocks."""

from __future__ import annotations

from dataclasses import dataclass, field

from . import jpeg as jpeg_m
from . import png as png_m
from . import webp as webp_m

# kinds that count as "metadata" for check/report exit codes by default
BASE_DIRTY_KINDS = {"exif", "xmp", "xmp-ext", "iptc", "text"}
# kinds only treated as metadata with --all
EXTRA_DIRTY_KINDS = {"icc", "jfif", "presentation"}

DEFAULT_WIPE_KINDS = {"exif", "xmp", "xmp-ext", "iptc", "text"}
ALL_WIPE_KINDS = DEFAULT_WIPE_KINDS | EXTRA_DIRTY_KINDS


@dataclass
class Block:
    kind: str                      # exif|xmp|xmp-ext|iptc|text|icc|jfif|presentation
    offset: int
    size: int
    note: str = ""
    tags: list = field(default_factory=list)
    has_gps: bool = False


@dataclass
class Inventory:
    path: str
    fmt: str                       # jpeg|png|webp|unknown
    blocks: list[Block] = field(default_factory=list)
    error: str | None = None
    size: int = 0

    def dirty_blocks(self, all_meta: bool = False) -> list[Block]:
        kinds = ALL_WIPE_KINDS if all_meta else BASE_DIRTY_KINDS
        return [b for b in self.blocks if b.kind in kinds]

    def is_clean(self, all_meta: bool = False) -> bool:
        if self.error:
            return False
        return not self.dirty_blocks(all_meta)

    @property
    def has_gps(self) -> bool:
        return any(b.has_gps for b in self.blocks)

    @property
    def tag_count(self) -> int:
        return sum(len(b.tags) for b in self.blocks)

    def removed_desc(self, all_meta: bool = False) -> str:
        parts = []
        for b in self.dirty_blocks(all_meta):
            label = b.kind
            if b.has_gps:
                label += "!"
            parts.append(label)
        return ", ".join(parts) if parts else "clean"

    def to_dict(self, all_meta: bool = False) -> dict:
        return {
            "path": self.path,
            "format": self.fmt,
            "size": self.size,
            "error": self.error,
            "clean": self.is_clean(all_meta),
            "gps": self.has_gps,
            "blocks": [
                {
                    "kind": b.kind,
                    "offset": b.offset,
                    "size": b.size,
                    "note": b.note,
                    "gps": b.has_gps,
                    "dirty": b.kind in (ALL_WIPE_KINDS if all_meta
                                        else BASE_DIRTY_KINDS),
                    "tags": [
                        {"ifd": t.ifd, "name": t.name, "type": t.type_name,
                         "value": t.value, "gps": t.is_gps}
                        for t in b.tags
                    ],
                }
                for b in self.blocks
            ],
        }


def detect(data: bytes) -> str:
    if data.startswith(b"\xff\xd8"):
        return "jpeg"
    if data.startswith(png_m.PNG_SIGNATURE):
        return "png"
    if webp_m.is_webp(data):
        return "webp"
    return "unknown"


def scan_bytes(data: bytes, path: str = "<memory>") -> Inventory:
    fmt = detect(data)
    inv = Inventory(path=path, fmt=fmt, size=len(data))

    def fail(msg: str) -> Inventory:
        inv.error = msg
        return inv

    try:
        if fmt == "jpeg":
            blocks, _segments = jpeg_m.classify_jpeg(data)
            for b in blocks:
                inv.blocks.append(Block(b.kind, b.offset, b.size, b.note,
                                        b.tags, b.has_gps))
        elif fmt == "png":
            for b in png_m.classify_png(data):
                tags, has_gps = [], False
                if b.kind == "exif":
                    tags = png_m.classify_png_exif_tags(data)
                    has_gps = png_m.png_has_gps(data)
                inv.blocks.append(Block(b.kind, b.offset, b.size, b.note,
                                        tags, has_gps))
        elif fmt == "webp":
            views, _flags, _chunks = webp_m.classify_webp(data)
            for v in views:
                inv.blocks.append(Block(v.kind, v.offset, v.size, v.note,
                                        v.tags, v.has_gps))
        else:
            raise ValueError("unrecognized file format (want JPEG/PNG/WebP)")
    except (ValueError, IndexError) as exc:
        return fail(str(exc))
    return inv


def scan_file(path: str) -> Inventory:
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        return Inventory(path=path, fmt="unknown", error=str(exc))
    return scan_bytes(data, path=path)