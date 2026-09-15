# Contributing to pulserver

## Getting set up

```bash
git clone https://github.com/pulserver/pulserver.git
cd pulserver
python -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
pre-commit install
```

## Before you open a pull request

```bash
bash scripts/format_and_lint.sh   # rewrites in place
pytest -q
```

CI runs the same script with `--check`, so anything that passes locally passes
there. If `pre-commit` rewrites a file, stage it and commit again.

## What the tests expect

- pytest with plain functions and fixtures. No `unittest.TestCase` subclasses.
- A test name states the invariant it protects, so a failure reads as a
  sentence: `test_a_double_precision_basis_does_not_reach_the_kernel`.
- Anything that can run on both CPU and CUDA is parametrised over both, and
  the CUDA leg skips cleanly when no device is present. A check that passes on
  one device says nothing about the other.

## Comments and documentation

Write for someone reading the code as it is now, with no memory of an earlier
version. Do not write text whose subject is the history of the code — no "used
to", "previously", "this replaces", no naming a bug that is fixed. A comment
earns its place by explaining a non-obvious algorithm or a choice a reader
would otherwise undo; prefer a well-named function, or a test whose name states
the invariant, because those cannot go stale silently.

## Releasing

Versions come from git tags via `setuptools_scm`. Push a tag matching
`v[0-9]+.[0-9]+.[0-9]+` and the release workflow builds, signs and publishes it.
