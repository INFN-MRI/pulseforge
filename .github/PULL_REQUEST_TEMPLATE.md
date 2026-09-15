## What this changes

<!-- One or two sentences. What behaviour is different afterwards? -->

## Why

<!-- The problem this solves. Link the issue if there is one. -->

## How it was verified

<!-- The commands you ran and what they said. Paste the output, don't
     summarise it. "Tests pass" is not verification. -->

```
```

## Checklist

- [ ] `bash scripts/format_and_lint.sh` is clean
- [ ] `pytest -q` passes, and new behaviour has a test whose name states the
      invariant it protects
- [ ] Anything numerical is exercised on CPU and CUDA, or the CUDA leg is
      marked `@pytest.mark.cuda` and skips cleanly
- [ ] No comment or docstring describes the code's history
