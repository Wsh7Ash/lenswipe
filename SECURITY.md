# Security Policy & Privacy

## What lenswipe is for

Removing metadata — camera model, serial-ish software strings, timestamps
and especially **GPS coordinates** — from images you own before you publish
them. Everything runs locally: no network calls, no telemetry, no
third-party dependencies (standard library only).

## Guarantees this tool makes

- Reads only the files you name; writes only where you tell it
  (sibling `*.wiped.*`, `--output-dir`, or `--in-place` with a `.bak`).
- Refuses to write an output it cannot verify as metadata-free: the cleaned
  bytes are re-scanned *before* the write, so a parser bug cannot silently
  produce a "clean" file that still tracks you.
- Never destroys data you did not point at: default mode leaves the input
  untouched, `--dry-run` writes nothing, and in-place mode keeps a backup.
- PNG containers are CRC-validated on read; unknown or corrupt containers
  exit 2 instead of being rewritten.

## What it does NOT do

- It does not edit pixels: faces, plates or watermarks **in the image
  itself** remain — only container metadata is touched.
- It does not judge metadata: `Author` or `Software` strings may be fine for
  you; `check` only tells you what is there.
- It does not handle RAW/HEIC/AVIF/TIFF/MP4 — unsupported input exits 2
  rather than being partially processed.

## Reporting a vulnerability

Open a private security advisory on this repository (not a public issue) for
anything like: writes outside the requested path, path traversal via
filenames, metadata that survives `wipe` + verification, or any case where
`check` says CLEAN on a file that still parses metadata before it was wiped.

## Supported versions

| Version | Supported |
|---|---|
| 1.0.x | ✔ |