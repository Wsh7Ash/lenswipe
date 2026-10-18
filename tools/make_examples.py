"""Regenerate the files in examples/.

Usage:  PYTHONPATH=src python tools/make_examples.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)

from lenswipe.synth import build_jpeg, sample_jpeg, sample_png, sample_webp  # noqa: E402

EXAMPLES = os.path.join(ROOT, "examples")


def main() -> int:
    os.makedirs(EXAMPLES, exist_ok=True)
    outputs = {
        # a photo carrying EXIF (incl. GPS), XMP, IPTC and an ICC profile
        "sunset.jpg": sample_jpeg(),
        # PNG with tEXt/iTXt/zTXt comments, pHYs and an eXIf chunk
        "summit.png": sample_png(),
        # WebP with VP8X flags, ICC, EXIF (GPS) and XMP chunks
        "banner.webp": sample_webp(icc=True, alpha=True),
        # a clean file: JFIF only, nothing to wipe
        "clean-logo.jpg": build_jpeg(jfif=True, exif=False, xmp=False,
                                     xmp_ext=False, iptc=False, icc=False),
    }
    for name, data in outputs.items():
        path = os.path.join(EXAMPLES, name)
        with open(path, "wb") as fh:
            fh.write(data)
        print(f"wrote {path} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())