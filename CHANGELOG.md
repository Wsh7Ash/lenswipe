# Changelog

All notable changes to lenswipe are documented here.

## 1.0.0 — 2026-10-17

Initial release.

### Added

- **Three containers**: JPEG (APP1 Exif / APP1 XMP / APP2 XMP-ext / APP13
  IPTC; JFIF+ICC kept by default), PNG (`tEXt`/`zTXt`/`iTXt`/`eXIf`;
  presentation chunks with `--all`), WebP (`EXIF`/`XMP ` chunks **with VP8X
  flag-bit maintenance**; `ICCP` with `--all`).
- **EXIF decoding**: IFD0 + Exif + GPS sub-IFDs, little- and big-endian
  TIFF, 12 TIFF value types (incl. RATIONAL as 2×u32), GPS flagging,
  unknown tags rendered as `tag 0xXXXX`.
- **`report`** — per-block inventory with decoded tags, `⚠ GPS` badges,
  `--json`, `--fail-on-metadata` gate.
- **`check`** — the CI gate: 1 while metadata remains, 0 when clean, 2 on
  unreadable/unknown/corrupt input.
- **`wipe`** — sibling `*.wiped.*` by default, `--output-dir`,
  `--in-place` with `.bak` (`--no-backup` to skip), `--dry-run`, atomic
  writes, and mandatory **verify-before-write** (residual metadata refuses
  the write).
- **`synth`** — spec-accurate sample builders (TIFF offsets, PNG CRCs, RIFF
  sizes) shared with `tools/make_examples.py`.
- Safety rails: only metadata containers move (JPEG entropy, PNG IDAT and
  WebP VP8 payloads byte-identical — asserted), PNG CRC validation on read,
  container-identity check after wipe.
- Test suite: **86 tests** across `test_jpeg`, `test_png`, `test_webp`,
  `test_inspect_wipe`, `test_cli` (subprocess end-to-end).
- CI workflow (Python 3.10/3.12/3.14), docs (`PROJECT_SPEC`,
  `ARCHITECTURE`, `USAGE`, `SECURITY`), MIT license, regenerable example
  images in `examples/`.