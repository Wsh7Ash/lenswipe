# Architecture — lenswipe

## Module map

```
src/lenswipe/
  tags.py     EXIF tag-name tables (IFD0 / Exif / GPS) + TIFF types
  jpeg.py     segment walker, EXIF/TIFF decode (II+MM, sub-IFDs), APPn stripping
  png.py      chunk walker with CRC verification, text-chunk decode, stripping
  webp.py     RIFF walker, EXIF/XMP views, strip + VP8X flag maintenance
  synth.py    synthetic sample builders (shared by tests + tools/make_examples.py)
  inspect.py  format detection + unified Inventory {path, fmt, blocks[], error}
  wipe.py     wipe_bytes / wipe_bytes_strict / wipe_file (verify-before-write)
  cli.py      report | check | wipe (exit codes 0/1/2)
```

## Inventory contract

```
scan_bytes(data) -> Inventory
  fmt        jpeg | png | webp | unknown (magic-number detection)
  blocks[]   {kind, offset, size, note, tags[], has_gps}
  error      container-level problems (truncated, bad signature, …)

kind ∈ {exif, xmp, xmp-ext, iptc, text, icc, jfif, presentation}
```

`BASE_DIRTY_KINDS = {exif, xmp, xmp-ext, iptc, text}` decide exit codes;
`icc`, `jfif` and PNG presentation chunks join only with `--all`.

## Per-format notes

**JPEG** — walk `FF nn` segments from SOI to SOS; entropy-coded data and EOI
are never interpreted, only copied. Exif = APP1 payload starting `Exif\0\0`;
its TIFF part is parsed with an ENDIAN-aware IFD reader: IFD0 → optional
`ExifIFD (0x8769)` and `GPSInfoIFD (0x8825)` children (depth ≤ 2), value
types ASCII/BYTE/SHORT/LONG/**RATIONAL (2×u32)**/… per TIFF 6.0. Out-of-line
values (>4 bytes) are read via their absolute offsets; undecodable values
render `<undecodable>` instead of failing a whole report.

**PNG** — 8-byte signature then `(len, type, data, crc)` frames; CRC is
`crc32(type ‖ data)` compared against the stored word (mismatch →
`crc_ok: False` on that chunk, reported but never "repaired"). Dropping
`tEXt/zTXt/iTXt/eXIf` frames takes their CRC with them — kept frames are
copied verbatim, so **no CRC ever needs recomputing**. Text payloads decode
including compressed `zTXt` and the four-header-byte `iTXt` layout
(`flag, method, lang\0, translated\0, value`).

**WebP** — `RIFF….WEBP` then `(4cc, size, data, pad-to-even)`. The extended
header `VP8X` advertises optional chunks with flag bits
(ICC 0x20, Alpha 0x10, EXIF 0x08, XMP 0x04, Anim 0x02). **Order matters:**
strip walks the chunk list, removes `EXIF`/`XMP ` chunks, clears their flag
bits in the payload of `VP8X`, then re-serializes with a recomputed RIFF
size. Forgetting the flags would leave readers hunting for chunks that no
longer exist.

## wipe safety flow

```
read file bytes
  └─ wipe_bytes()            classify → remove per policy
      └─ scan_bytes(out)     ← verification BEFORE any write
           ├─ clean?  → atomic write (tmp + os.replace)
           │             --in-place first copies file.bak
           └─ residual → error, nothing written, exit code reflects it
```

`wipe_file` returns a `WipeResult {path, out_path, removed[], bytes_in/out,
verified, dry_run, error}`; the CLI maps: error → 2, unverified with
removals → 1, else 0.

## The synth module

Tests and `tools/make_examples.py` build containers from primitives
(`jpeg_segment`, `build_tiff`, `png_chunk`, `riff_chunk`) so fixtures are
genuine: real TIFF offsets, real PNG CRCs, real RIFF sizes — that is how the
reader code gets honestly exercised (II *and* MM byte orders, out-of-line
values, GPS sub-IFDs, compressed text chunks).

## Exit-code matrix

| Situation | report | check | wipe |
|---|---|---|---|
| clean files | 0 | 0 | 0 (no-op, not rewritten) |
| metadata present | 0 (1 with `--fail-on-metadata`) | 1 | 0 with verification |
| unknown/corrupt/missing | 2 | 2 | 2 |
| verification alarm | — | — | 1 |