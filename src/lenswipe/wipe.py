"""Apply metadata removal and verify the result.

Safety model:

- the whole input is read first, the cleaned bytes are computed in memory;
- output is written to a temp file and `os.replace`d into place (atomic on
  the same filesystem);
- `--in-place` keeps a `.bak` next to the original unless `--no-backup`;
- before anything is written, the cleaned bytes are **re-scanned**; if any
  metadata block survives, the write is refused and an error is returned
  (a parser mistake must never be able to silently claim a file is clean).
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field

from . import jpeg as jpeg_m
from . import png as png_m
from . import webp as webp_m
from .inspect import ALL_WIPE_KINDS, DEFAULT_WIPE_KINDS, Inventory, scan_bytes


@dataclass
class WipeResult:
    path: str
    out_path: str | None = None
    removed: list[str] = field(default_factory=list)
    bytes_in: int = 0
    bytes_out: int = 0
    verified: bool = False
    dry_run: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and (self.verified or self.dry_run)


def _block_desc(inv: Inventory, kinds: set[str]) -> list[str]:
    out = []
    for b in inv.blocks:
        if b.kind in kinds:
            label = b.kind
            if b.tags:
                label += f"({len(b.tags)} tags"
                label += ", GPS" if b.has_gps else ""
                label += ")"
            elif b.has_gps:
                label += "(GPS)"
            out.append(label)
    return out


def wipe_bytes(data: bytes, all_meta: bool = False) -> tuple[bytes, list[str]]:
    """Clean `data`; returns (cleaned bytes, descriptions of what went)."""
    inv = scan_bytes(data, "<memory>")
    if inv.error:
        raise ValueError(inv.error)
    kinds = ALL_WIPE_KINDS if all_meta else DEFAULT_WIPE_KINDS
    removed = _block_desc(inv, kinds)

    if inv.fmt == "jpeg":
        drop = {k for k in kinds}
        out = jpeg_m.strip_jpeg(data, drop)
    elif inv.fmt == "png":
        drop_types = set(png_m.DEFAULT_METADATA_TYPES)
        if all_meta:
            for c in png_m.parse_chunks(data):
                if png_m._is_droppable_ancillary(c.type):
                    drop_types.add(c.type)
        out = png_m.strip_png(data, drop_types)
    elif inv.fmt == "webp":
        drop_fourccs = {"EXIF", "XMP "} | ({"ICCP"} if all_meta else set())
        out = webp_m.strip_webp(data, drop_fourccs)
    else:  # pragma: no cover - scan_bytes already rejects unknown formats
        raise ValueError("unrecognized file format")
    return out, removed


def wipe_bytes_strict(data: bytes, all_meta: bool = False) -> tuple[bytes, list[str]]:
    """wipe_bytes plus the clean-after guarantee (raises if verification fails)."""
    out, removed = wipe_bytes(data, all_meta=all_meta)
    after = scan_bytes(out, "<result>")
    if after.error:
        raise ValueError(f"post-wipe verification unreadable: {after.error}")
    if not after.is_clean(all_meta):
        survivors = [b.kind for b in after.dirty_blocks(all_meta)]
        raise ValueError(
            f"post-wipe verification found residual metadata: {survivors}")
    if detect_identity_mismatch(data, out):
        raise ValueError("post-wipe verification: container no longer matches")
    return out, removed


def detect_identity_mismatch(before: bytes, after: bytes) -> bool:
    """Same container signature required (a JPEG must stay a JPEG)."""
    fmt_before = scan_bytes(before).fmt if before else "<empty>"
    fmt_after = scan_bytes(after).fmt if after else "<empty>"
    return fmt_before != fmt_after


def wipe_file(path: str, *, in_place: bool = False, output_dir: str | None = None,
              backup: bool = True, all_meta: bool = False,
              dry_run: bool = False) -> WipeResult:
    result = WipeResult(path=path, dry_run=dry_run)
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        result.error = str(exc)
        return result
    result.bytes_in = len(data)

    try:
        cleaned, removed = wipe_bytes_strict(data, all_meta=all_meta)
    except ValueError as exc:
        result.error = str(exc)
        return result
    result.removed = removed
    result.bytes_out = len(cleaned)
    result.verified = True

    stem, suffix = os.path.splitext(path)
    if in_place:
        out_path = path
    elif output_dir:
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, os.path.basename(stem) + ".wiped" + suffix)
    else:
        out_path = stem + ".wiped" + suffix
    result.out_path = out_path

    if dry_run or not removed:
        # nothing written for dry runs, and no point rewriting clean files
        if not removed and not in_place and not dry_run:
            result.out_path = path   # already clean: report as a no-op
        return result

    try:
        if in_place and backup and os.path.exists(path):
            bak = path + ".bak"
            if not os.path.exists(bak):
                with open(bak, "wb") as fh:
                    fh.write(data)
        directory = os.path.dirname(os.path.abspath(out_path))
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".lenswipe-tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(cleaned)
            os.replace(tmp, out_path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
    except OSError as exc:
        result.error = f"write failed: {exc}"
        result.verified = False
    return result