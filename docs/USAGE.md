# Usage — lenswipe

```
lenswipe report FILES... [-r] [--all] [--json] [--fail-on-metadata]
lenswipe check  FILES... [-r] [--all] [--json]
lenswipe wipe   FILES... [-r] [--all] [--json]
                [--in-place [--no-backup]] [--output-dir DIR] [--dry-run]
```

`FILES` accepts images and directories (directories need `-r/--recursive`;
only `.jpg/.jpeg/.png/.webp` files inside them are considered).

Exit codes: **0** · **1** = metadata where none is allowed (see above) ·
**2** = usage error, missing file, unknown or corrupt container.

## report — see what a file carries

```console
$ lenswipe report examples/sunset.jpg
examples/sunset.jpg  jpeg  DIRTY  GPS!
    [exif     ] APP1/Exif · 980 bytes ⚠ GPS
        IFD0:Make                                 = LenswipeCam
        IFD0:Orientation                          = 1
        Exif:DateTimeOriginal                     = 2026:10:17 09:41:03
        GPS:GPSLatitude                           = 51/1 30/1 12/1
        GPS:GPSCoordinates...
    [xmp      ] APP1/XMP 65 bytes
    [icc      ] APP2/ICC profile · 20 bytes
```

- `⚠ GPS` / `GPS!` marks files whose location can be extracted.
- `--fail-on-metadata` turns the inventory into a gate (exit 1 when dirty).
- `--json` emits the structured form (per-block kind/offset/size/dirty plus
  decoded tags) for scripts.
- `--all` counts ICC/JFIF/presentation chunks as metadata too.

## check — the CI gate

```console
$ lenswipe check photos/ -r
CLEAN    photos/outdoor/clean-logo.jpg
DIRTY    photos/outdoor/sunset.jpg  (exif, xmp, iptc)
...
2 file(s): 1 clean, 1 dirty
exit=1
```

Use it in CI or a pre-commit hook: `lenswipe check exports/ -r || echo "strip first"`.

## wipe — strip metadata, prove it

```console
$ lenswipe wipe examples/sunset.jpg
wiped examples/sunset.jpg -> examples/sunset.wiped.jpg
  removed: exif(5 tags, GPS), xmp, xmp-ext, iptc
  verified: post-wipe scan found no metadata

$ lenswipe wipe photos/ -r --output-dir clean/     # batch into a folder
$ lenswipe wipe photo.jpg --in-place                # overwrite, photo.jpg.bak kept
$ lenswipe wipe photo.jpg --in-place --no-backup    # overwrite without .bak
$ lenswipe wipe photo.jpg --dry-run                 # print the plan only
```

Guarantees:

1. default writes a **sibling** `name.wiped.ext`; the input is never touched;
2. `--in-place` writes atomically and keeps `name.ext.bak` (unless
   `--no-backup`);
3. cleaned bytes are **re-scanned before writing** — residual metadata means
   the write is refused and the command exits non-zero;
4. files that are already clean are not rewritten at all;
5. image payloads (JPEG entropy stream, PNG IDAT, WebP VP8) are byte-identical.

## Flags recap

| Flag | Applies to | Effect |
|---|---|---|
| `-r, --recursive` | all | walk directories |
| `--all` | all | treat ICC/JFIF/presentation chunks as metadata |
| `--json` | all | machine-readable output |
| `--fail-on-metadata` | report | exit 1 when anything is dirty |
| `--in-place` | wipe | overwrite input (keeps `.bak`) |
| `--no-backup` | wipe | skip the `.bak` copy |
| `--output-dir DIR` | wipe | write `*.wiped.*` files into DIR |
| `--dry-run` | wipe | report the plan, write nothing |

## Recipes

```console
# pre-publish gate for a static site's image folder
$ lenswipe check site/static/img -r --all || exit 1

# inventory a camera drop as JSON for auditing
$ lenswipe report SD/card/DCIM -r --json > audit.json

# clean in place, refuse anything the tool cannot prove clean
$ lenswipe wipe album/ -r --in-place || echo "needs attention"
```