"""lenswipe CLI: report | check | wipe

Exit codes: 0 all good · 1 metadata found where none is allowed (check flag
failures, report --fail-on-metadata, verification alarms) · 2 usage/input error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .inspect import Inventory, scan_file
from .wipe import wipe_file

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if reconf is None:
            continue
        try:
            reconf(encoding="utf-8", errors="replace")
        except (OSError, ValueError):   # pragma: no cover
            pass


def _collect(paths: list[str], recursive: bool) -> tuple[list[str], list[str]]:
    files: list[str] = []
    errors: list[str] = []
    for p in paths:
        if os.path.isdir(p):
            if not recursive:
                errors.append(f"{p}: is a directory (use -r/--recursive)")
                continue
            for root, _dirs, names in os.walk(p):
                for name in sorted(names):
                    if os.path.splitext(name)[1].lower() in IMAGE_EXT:
                        files.append(os.path.join(root, name))
        elif os.path.exists(p):
            files.append(p)
        else:
            errors.append(f"{p}: no such file")
    return files, errors


def _fmt_block_line(b) -> str:
    gps = " ⚠ GPS" if b.has_gps else ""
    head = f"    [{b.kind:<9}] {b.note or '-'} · {b.size} bytes{gps}"
    lines = [head]
    for t in b.tags:
        prefix = f"{t.ifd}:{t.name}"
        lines.append(f"        {prefix:<34} = {t.value}")
    return "\n".join(lines)


def _report_text(invs: list[Inventory], errors: list[str],
                 all_meta: bool) -> str:
    lines = []
    dirty = 0
    gps_count = 0
    for inv in invs:
        if inv.error:
            lines.append(f"{inv.path}  ERROR {inv.error}")
            continue
        state = "clean" if inv.is_clean(all_meta) else "DIRTY"
        badges = []
        if inv.has_gps:
            badges.append("GPS!")
            gps_count += 1
        if state == "DIRTY":
            dirty += 1
        lines.append(f"{inv.path}  {inv.fmt}  {state}"
                     + (f"  {' '.join(badges)}" if badges else ""))
        for b in inv.blocks:
            lines.append(_fmt_block_line(b))
    lines.append("")
    lines.append(f"{len(invs)} file(s): {dirty} with metadata, "
                 f"{gps_count} carrying GPS")
    for e in errors:
        lines.append(f"error: {e}")
    return "\n".join(lines)


def _check_text(invs: list[Inventory], errors: list[str],
                all_meta: bool) -> str:
    lines = []
    dirty = 0
    for inv in invs:
        if inv.error:
            lines.append(f"ERROR {inv.path}: {inv.error}")
            continue
        if inv.is_clean(all_meta):
            lines.append(f"CLEAN    {inv.path}")
        else:
            dirty += 1
            lines.append(f"DIRTY    {inv.path}  ({inv.removed_desc(all_meta)})")
    for e in errors:
        lines.append(f"error: {e}")
    lines.append("")
    lines.append(f"{len(invs)} file(s): {len(invs) - dirty} clean, {dirty} dirty")
    return "\n".join(lines)


def _wipe_text(results, all_meta: bool) -> str:
    lines = []
    ok = 0
    for r in results:
        if r.error:
            lines.append(f"ERROR {r.path}: {r.error}")
            continue
        if not r.removed:
            lines.append(f"unchanged {r.path} (already clean)")
            ok += 1
            continue
        verb = "would wipe" if r.dry_run else "wiped"
        target = r.out_path if not r.dry_run else r.out_path
        lines.append(f"{verb} {r.path} -> {target}")
        lines.append(f"  removed: {', '.join(r.removed)}"
                     + (f" · {r.bytes_in} -> {r.bytes_out} bytes"
                        if not r.dry_run else ""))
        if r.verified and not r.dry_run:
            lines.append("  verified: post-wipe scan found no metadata")
        ok += 1
    lines.append("")
    lines.append(f"{len(results)} file(s): {ok} ok, {len(results) - ok} failed"
                 + (" (dry run: nothing written)" if all(r.dry_run for r in results)
                    and results else ""))
    return "\n".join(lines)


def _json_dump(payload) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lenswipe",
        description="Inventory and remove EXIF/metadata from JPEG/PNG/WebP "
                    "(offline, no dependencies).")
    p.add_argument("--version", action="version", version=f"lenswipe {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("files", nargs="+", help="image files or directories")
        sp.add_argument("-r", "--recursive", action="store_true",
                        help="walk directories")
        sp.add_argument("--all", action="store_true",
                        help="treat ICC/JFIF/presentation chunks as metadata too")
        sp.add_argument("--json", action="store_true", help="JSON output")

    rep = sub.add_parser("report", help="inventory every metadata block/tag")
    common(rep)
    rep.add_argument("--fail-on-metadata", action="store_true",
                     help="exit 1 if any file is not clean")

    chk = sub.add_parser("check", help="exit 1 if any file carries metadata")
    common(chk)

    wp = sub.add_parser("wipe", help="strip metadata into a new/updated file")
    common(wp)
    wp.add_argument("--in-place", action="store_true",
                    help="overwrite the input (keeps .bak unless --no-backup)")
    wp.add_argument("--no-backup", action="store_true",
                    help="with --in-place, do not keep a .bak copy")
    wp.add_argument("--output-dir", help="write results into this directory")
    wp.add_argument("--dry-run", action="store_true",
                    help="only report what would be removed")
    return p


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        _force_utf8_stdio()
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        files, errors = _collect(args.files, args.recursive)
        if not files and errors:
            for e in errors:
                print(f"lenswipe: {e}", file=sys.stderr)
            return 2

        if args.command == "report":
            invs = [scan_file(f) for f in files]
            hard_errors = [e for e in errors] + \
                [f"{i.path}: {i.error}" for i in invs if i.error]
            if args.json:
                print(_json_dump({"files": [i.to_dict(args.all) for i in invs],
                                  "errors": hard_errors}))
            else:
                print(_report_text(invs, errors, args.all))
            if hard_errors and not args.fail_on_metadata:
                return 2
            if args.fail_on_metadata and any(
                    not i.is_clean(args.all) for i in invs):
                return 1
            return 2 if hard_errors else 0

        if args.command == "check":
            invs = [scan_file(f) for f in files]
            hard_errors = [e for e in errors] + \
                [f"{i.path}: {i.error}" for i in invs if i.error]
            dirty = [i for i in invs if not i.is_clean(args.all)]
            if args.json:
                print(_json_dump({"files": [i.to_dict(args.all) for i in invs],
                                  "errors": hard_errors,
                                  "dirty": len(dirty)}))
            else:
                print(_check_text(invs, errors, args.all))
            if hard_errors:
                return 2
            return 1 if dirty else 0

        # wipe
        results = [wipe_file(f, in_place=args.in_place,
                             output_dir=args.output_dir,
                             backup=not args.no_backup,
                             all_meta=args.all, dry_run=args.dry_run)
                   for f in files]
        if args.json:
            print(_json_dump({
                "files": [
                    {"path": r.path, "out": r.out_path, "removed": r.removed,
                     "bytes_in": r.bytes_in, "bytes_out": r.bytes_out,
                     "verified": r.verified, "dry_run": r.dry_run,
                     "error": r.error}
                    for r in results],
                "errors": errors,
            }))
        else:
            print(_wipe_text(results, args.all))
        hard_errors = [e for e in errors] + \
            [r.error for r in results if r.error]
        unverified = [r for r in results
                      if r.error is None and r.removed
                      and not r.verified and not r.dry_run]
        if hard_errors:
            for e in hard_errors:
                print(f"lenswipe: {e}", file=sys.stderr)
            return 2
        if unverified:
            return 1
        return 0
    except (ValueError, OSError) as exc:
        print(f"lenswipe: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(main())