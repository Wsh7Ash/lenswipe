# Contributing to lenswipe

Thanks for helping improve lenswipe.

## Development

```console
$ python -m unittest discover -s tests -t .    # 86 tests, no dependencies
$ PYTHONPATH=src python -m lenswipe report examples/ -r
$ PYTHONPATH=src python tools/make_examples.py   # regenerate fixtures
```

Python ≥ 3.10, **standard library only**. Style: 4-space indent, type hints
on public functions, `from __future__ import annotations`, module docstrings.

## Where things live

| Area | File(s) | Notes |
|---|---|---|
| Container walkers | `jpeg.py`, `png.py`, `webp.py` | never touch image payloads |
| Tag names/decoding | `tags.py`, `jpeg.py` | II *and* MM byte orders |
| Inventory | `inspect.py` | `Inventory`/`Block` is the public contract |
| Removal + safety | `wipe.py` | verification-before-write is mandatory |
| Fixtures | `synth.py` | build containers from spec primitives |
| CLI | `cli.py` | exit codes 0/1/2 are public API |

## Guidelines

- **Every change ships with tests.** New format knowledge = a fixture built
  from bytes in `synth.py`, plus assertions that a wipe of that fixture
  passes `scan_bytes(...).is_clean()`.
- Never add a code path that writes output without going through the
  verification step in `wipe_bytes_strict`.
- Keep image payload copying byte-exact — there are tests that compare the
  entropy/IDAT/VP8 bytes; they should stay boring.
- RIP: if you add a metadata kind, update `BASE_DIRTY_KINDS` /
  `ALL_WIPE_KINDS`, the README table and `docs/USAGE.md` together.

## Commits

Small, described-by-purpose commits; reference issues where they exist.