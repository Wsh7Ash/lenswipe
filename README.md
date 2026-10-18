# lenswipe

**Offline EXIF/metadata wiper for JPEG, PNG and WebP** — inventory every
metadata block (GPS flagged loudly), strip it while leaving image data
byte-identical, and verify cleanliness with a CI-friendly exit code.
Standard library only, no network, no dependencies.

```console
$ python -m lenswipe report examples/ -r

examples/sunset.jpg  jpeg  DIRTY  GPS!
    [exif     ] APP1/Exif · 980 bytes ⚠ GPS
        IFD0:Make                                 = LenswipeCam
        IFD0:Model                                = PocketTracer X1
        IFD0:DateTime                             = 2026:10:17 09:41:03
        GPS:GPSLatitude                           = 51/1 30/1 12/1
        GPS:GPSDateStamp                          = 2026:10:17
    [xmp      ] APP1/XMP 65 bytes
    [iptc     ] APP13/Photoshop-IPTC · 24 bytes
    [icc      ] APP2/ICC profile · 20 bytes          ← kept by default

4 file(s): 3 with metadata, 3 carrying GPS
exit=0
```

```console
$ python -m lenswipe check examples/ -r      # gate: exit 1 while dirty
$ python -m lenswipe wipe  examples/ -r --output-dir clean/
wiped examples/sunset.jpg -> clean/sunset.wiped.jpg
  removed: exif(5 tags, GPS), xmp, xmp-ext, iptc
  verified: post-wipe scan found no metadata
$ python -m lenswipe check clean/ -r         # → exit 0
```

## What gets removed

| Format | Default removal | Kept (default) | `--all` also removes |
|---|---|---|---|
| JPEG | APP1 Exif, APP1 XMP, APP2 XMP-ext, APP13 IPTC | APP0 JFIF, APP2 ICC | JFIF + ICC |
| PNG | `tEXt`, `zTXt`, `iTXt`, `eXIf` | `IHDR`/`PLTE`/`IDAT`/`IEND` | presentation chunks (`pHYs`, `gAMA`, `tIME`, …) |
| WebP | `EXIF`, `XMP ` chunks **+ their VP8X flag bits** | `VP8*`, `ICCP` | `ICCP` |

## Safety model

- Image data is copied **byte-for-byte** (JPEG entropy stream, PNG IDAT
  chunks, WebP `VP8 ` payload) — only metadata containers are dropped.
- Before any write, the cleaned bytes are **re-scanned**; if any metadata
  block survives, the write is refused (a parser bug can never claim a file
  is clean silently).
- Atomic write (`tmp` + `os.replace`); `--in-place` keeps a `.bak` unless
  `--no-backup`; `--dry-run` writes nothing.
- PNG chunk CRCs are validated on read; corrupt containers report an error
  and exit 2 rather than being rewritten.

## Exit codes (CI contract)

| Code | Meaning |
|---|---|
| 0 | report done / everything clean / wipe written + verified |
| 1 | `check` found metadata; `report --fail-on-metadata`; wipe verification alarm |
| 2 | usage error, missing file, unsupported or corrupt container |

## Commands

```
lenswipe report FILES... [-r] [--all] [--json] [--fail-on-metadata]
lenswipe check  FILES... [-r] [--all] [--json]
lenswipe wipe   FILES... [-r] [--all] [--json] [--in-place [--no-backup]]
                   [--output-dir DIR] [--dry-run]
```

## Quick start

```console
$ git clone https://github.com/Wsh7Ash/lenswipe && cd lenswipe
$ python -m unittest discover -s tests -t .    # 86 tests
$ PYTHONPATH=src python -m lenswipe report examples/sunset.jpg
$ PYTHONPATH=src python tools/make_examples.py   # regenerate examples/
```

## Documentation

- [docs/PROJECT_SPEC.md](docs/PROJECT_SPEC.md) — requirements and scope
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — per-format parsers and the safety model
- [docs/USAGE.md](docs/USAGE.md) — full command reference
- [RESULTS.md](RESULTS.md) — validation evidence
- [SECURITY.md](SECURITY.md) — privacy and safe-use notes

## Requirements

Python **≥ 3.10**, standard library only.

## License

MIT — see [LICENSE](LICENSE).