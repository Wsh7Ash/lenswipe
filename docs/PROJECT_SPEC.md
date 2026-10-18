# Project Spec — lenswipe

## Summary

An offline metadata inventory and removal tool for JPEG, PNG and WebP images
(Python 3.10+, standard library only): see exactly what a photo carries
(which IFD, which tags, whether GPS is embedded), strip that metadata while
leaving the image data byte-identical, and prove the result is clean with a
CI-friendly exit code.

Category: **desktop-utility** (2nd use — `dupeye` on 2026-09-28 covered
deduplication with quarantine/undo; lenswipe covers a different job:
metadata provenance and privacy).

## Problem

Photos published to the web routinely carry camera serials, timestamps,
software strings and — the classic leak — GPS coordinates. "Just re-save it"
loses quality and misses chunks (`eXIf` in PNG, VP8X flags in WebP). People
need a tool that shows what is there, removes it exactly, and can prove it.

## Goals

1. **Inventory first.** `report` enumerates every metadata container with
   decoded EXIF tags (IFD-aware, GPS sub-IFD flagged with `⚠ GPS`).
2. **Exact removal, image untouched.** Only metadata containers move: JPEG
   APPn (except structural), PNG text/eXIf chunks, WebP EXIF/XMP chunks plus
   the VP8X flag bits that advertise them. Entropy/IDAT/frame payloads are
   copied byte-for-byte.
3. **Verification is non-negotiable.** `wipe` re-scans its own output before
   writing anything; residual metadata → the write is refused and the run
   fails loudly.
4. **CI exit codes.** `check` → 1 while any file is dirty, 0 when clean,
   2 for unreadable/unknown/corrupt input. `report --fail-on-metadata`
   gives the same gate with a full inventory attached.
5. **Safe by default.** Sibling `*.wiped.*` output (input untouched),
   `--dry-run`, `.bak` backups for `--in-place`, atomic writes, PNG CRC
   validation.
6. **Offline.** No network calls, no telemetry, no third-party package.

## Non-goals

- Not a re-encoder: no resampling, quality changes, or format conversion.
- No RAW formats (CR3/NEF/ARW), HEIC/AVIF, TIFF, GIF, MP4/MOV containers
  (documented as out of scope for 1.0).
- No anonymizing of pixel content (faces/plates) — container metadata only.
- Not a photo manager: no albums, ratings, sidecars.

## Acceptance criteria

- `python -m unittest discover -s tests -t .` passes (86 tests) covering all
  three formats: segment/chunk walk, EXIF decode (II + MM byte orders, GPS
  sub-IFD, rationals), stripping, verification, wipe file semantics, CLI.
- Round-trip guarantee demonstrated: the wiped examples pass `check` with
  exit 0; originals stay dirty (exit 1) — captured in `results/`.
- JPEG entropy bytes, PNG IDAT bytes and WebP VP8 payload survive byte-exact
  (asserted in tests, not just spot-checked).
- GPS present → `report`/`check` say so; `wipe` drops the GPS sub-IFD.
- WebP VP8X `EXIF/XMP` flag bits are cleared when those chunks are removed
  (asserted before/after with masks 0x08/0x04).

## Known limitations

- Container translators (IPTC as Photoshop 8BIM blobs inside APP13) are
  removed as whole segments; individual IPTC records are not decoded.
- XMP packets are reported by size, not parsed into fields.
- `--all` on JPEG removes JFIF/ICC too: some legacy readers dislike a
  JFIF-less file, which is why it is opt-in.
- Synthetic example images are structurally genuine but their entropy/IDAT
  payloads are placeholders (they test containers, not renderers).