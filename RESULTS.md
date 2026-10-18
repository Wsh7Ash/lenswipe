# Results

## Environment

- OS: Windows 11 (Git Bash), Python 3.14.3
- Network: **none used** — everything ran against local files
- Dependencies installed: **none** (standard library only)

## Validation performed

1. Syntax gate: `compileall -q src tools` — clean.
2. Full suite: `python -m unittest discover -s tests -t .`
3. Fixture generation: `tools/make_examples.py` (4 images).
4. Live CLI demos of report / check / wipe (incl. dry-run, `--all`,
   JSON output) with exit codes recorded in `results/`.
5. Secret scan over source, tests, docs and results.

## Commands executed

```console
$ python -m unittest discover -s tests -t .
$ PYTHONPATH=src python tools/make_examples.py
$ PYTHONPATH=src python -m lenswipe report examples/ -r
$ PYTHONPATH=src python -m lenswipe check examples/ -r
$ PYTHONPATH=src python -m lenswipe wipe examples/ -r --output-dir "$TMP"
$ PYTHONPATH=src python -m lenswipe check "$TMP" -r
$ PYTHONPATH=src python -m lenswipe wipe examples/sunset.jpg --dry-run --json
$ PYTHONPATH=src python -m lenswipe check examples/ -r --all
```

## Observed result

### Tests

`Ran 86 tests in ~9s — OK (exit 0)`:

| Suite | Count | Focus |
|---|---|---|
| test_jpeg | 18 | segment walk (fill bytes, SOS stop), EXIF II+MM decode, GPS sub-IFD, rationals, strip keeps JFIF/ICC, payload byte-exact, idempotence |
| test_png | 14 | chunk walk, CRC ok/flagged, tEXt/zTXt/iTXt (incl. compressed), strip keeps IDAT/IEND, `--all` drops pHYs, trailing bytes |
| test_webp | 13 | RIFF walk, even-padding, VP8X flag masks before/after, RIFF size recomputation, ICCP with `--all`, idempotence |
| test_inspect_wipe | 21 | detection, dirty/clean inventories, JSON shape, wipe verified outputs, `.bak`, output-dir, dry-run no-write, no-op on clean |
| test_cli | 20 | report/check/wipe end-to-end via subprocess, exit codes 0/1/2, recursive walk, JSON parse, usage |

### Demo: mixed folder reported with GPS flags (exit 0)

```
4 file(s): 3 with metadata, 3 carrying GPS
exit=0
```
(`results/report-mixed.txt` — sunset.jpg carries EXIF+XMP+IPTC+ICC with
GPS lat/long/time; summit.png has text chunks + pHYs + eXIf; banner.webp has
VP8X/EXIF/XMP/ICCP; clean-logo.jpg clean)

### Demo: the gate behaves (check)

```
$ lenswipe check examples/ -r          → exit=1   (dirty present)
$ lenswipe check examples/clean-logo.jpg → exit=0
exit=1 / exit=0
```
(`results/check.txt`)

### Demo: wipe → verify → clean (exit 0, then 0)

```
$ lenswipe wipe examples/ -r --output-dir $TMP   → exit=0
$ lenswipe check $TMP -r                         → exit=0
CLEAN    …/banner.wiped.webp
CLEAN    …/summit.wiped.png
CLEAN    …/sunset.wiped.jpg
```
(`results/wipe-pipeline.txt`; clean-logo.jpg correctly left unchanged)

### Demo: dry-run writes nothing; --all widens the gate (exit 0 then 1)

```
$ lenswipe wipe examples/sunset.jpg --dry-run --json → exit=0
$ lenswipe check examples/ -r --all                  → exit=1
```
(`results/flags.txt` — with `--all`, JFIF and pHYs count as metadata too,
which is why the previously clean-logo now also reports).

## Generated artifacts

| File | Contents |
|---|---|
| `examples/sunset.jpg`, `summit.png`, `banner.webp` | dirty samples (regenerable via `tools/make_examples.py`) |
| `examples/clean-logo.jpg` | pre-clean file (JFIF only) |
| `results/report-mixed.txt` | inventory of the folder incl. GPS + tags |
| `results/check.txt` | gate exit codes 1 (dirty) / 0 (clean) |
| `results/wipe-pipeline.txt` | wipe + post-wipe check all CLEAN + JSON sample |
| `results/flags.txt` | dry-run JSON + `--all` gate |

## Known limitations (honest accounting)

- IPTC inside APP13 is removed as a segment; individual IPTC records are not
  decoded. XMP is sized, not parsed.
- Example entropy/IDAT payloads are placeholders: tests prove container
  handling and byte-exact payload preservation, not rendering.
- HEIC/AVIF/TIFF/GIF/RAW/MP4 are out of scope for 1.0 — they exit 2 with
  "unrecognized file format" rather than being processed.
- Verification proves "no metadata containers remain **as we define them**";
  it cannot prove a file never contained metadata (byte-level forensics is a
  different tool).