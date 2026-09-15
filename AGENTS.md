# pulserver — agent instructions

`CLAUDE.md` and `GEMINI.md` import this file. Edit this file only.

## What this package is

Orchestrator for MR acquisitions: sequence design, scanner preparation,
reconstruction and real-time feedback.

Pulserver sits on top of two engines it does not reimplement: sequence design
is [`pypulseqpp`](https://github.com/pulserver/pypulseqpp) and the
reconstruction engine is [`bartorch`](https://github.com/mcencini/bartorch).
Vendor-specific playout and data conversion live in the scanner-side
interpreters; they call pulserver's public API and carry no sequence or
reconstruction logic of their own. Code that belongs to an engine goes
upstream into that engine, not into a copy here.

## Build and test

```bash
pip install -e .[dev]
bash scripts/format_and_lint.sh   # rewrites in place; --check to verify only
pytest -q
```

Build and test steps are mandatory before reporting a change complete. Run them
and report the exact output; do not assume success.

## Tests

pytest with plain functions and fixtures — never `unittest.TestCase`. A test
name states the invariant it protects, so a failure reads as a sentence.

Anything numerical that can run on CPU and CUDA is parametrised over both, and
the CUDA leg skips when no device is present. A kernel-layout check that ran on
CPU only has passed in this codebase while CUDA was 100% wrong.

## Comments

Write for someone reading the code as it is now, who has no memory of any
earlier version of it. **Never** write text whose subject is the history of the
code. Banned in comments, docstrings and prose alike:

- "used to", "was once", "no longer", "previously", "now that", "this replaces",
  "the old X", "before the fix"
- justifying the present shape by contrast with a shape that is gone
- naming a bug that has been fixed, or the session that fixed it
- restating what the code plainly says

A comment earns its place only by explaining a non-obvious algorithm or a
choice a reader would otherwise undo — and even then, prefer a well-named
function or a test whose name states the invariant, because those cannot go
stale silently. When tempted to explain *why not the other way*, write a test.
Put implementation comments next to the implementation they explain.

Stale comments are actively harmful. Deleting an outdated comment is always
correct; rewriting one to describe the change is not.

## Docstrings

The goal is **human readability**: documentation optimised for a developer
reading and navigating the code. LLM readability is welcome only where it
follows from precise, concise documentation; never make a docstring longer or
more explanatory for the sake of an LLM.

Docstrings are NumPy style.

Before writing or changing a docstring, read the implementation, its callers
and its tests, and the native code behind it when there is any. Never carry
behaviour over from an existing docstring the implementation contradicts, and
never resolve an ambiguity by making the docstring vague: resolve it from the
code.

1. **High information density.** State what is useful and not already obvious
   from the name, signature, annotations, or a quick reading of the body.
2. **Direct, technical prose** for a reader scanning code. No narrative,
   conversational, literary, tutorial, anthropomorphic or essay style.
3. **No reasoning dumps.** Do not explain how the implementation arrives at its
   result unless that reasoning is an externally important invariant or design
   constraint.
4. **Preserve non-obvious semantics**, when they apply:
   - coordinate and reference frames;
   - physical units;
   - composition and application order;
   - invariants and state transitions;
   - externally visible side effects;
   - non-obvious return conventions, such as returning `None` instead of
     allocating an empty result;
   - assumptions callers must satisfy;
   - behaviour a maintainer could easily break;
   - surprising but intentional behaviour;
   - compatibility or architectural constraints that materially affect use of
     the API.
5. **No redundancy.** Do not restate parameter names in prose, types the
   annotations already give (unless the convention requires them),
   implementation steps visible below the docstring, trivial return values,
   obvious attributes, generic phrases such as "helper function for...", or
   internal trivia that affects neither callers nor maintenance.
6. **Separate abstraction levels.** A package or module docstring states its
   purpose in one or a few sentences; it is not an architecture essay or a
   design document. Long architectural rationale belongs in dedicated
   documentation, unless the constraint is needed to use or safely modify the
   module.
7. **Public APIs get useful documentation, not maximum documentation**: a
   concise purpose, plus parameters, returns, exceptions, units, conventions
   or side effects where these add information.
8. **Private helpers get no filler.** A short docstring is justified when the
   contract, invariant, algorithmic assumption, state behaviour or return
   convention is non-obvious. If the name, signature and body already make the
   behaviour clear, write none; remove an existing one that adds nothing.
9. **Class docstrings describe the abstraction.** Document constructor
   parameters and attributes when their semantics matter and are not obvious
   from name and type, not because they exist.
10. **Do not trade precision for brevity.** Two or three sentences stating a
    genuinely non-obvious invariant beat an ambiguous one-liner.

Worth keeping:

- "Prescription orientation is composed after the rotation already attached to
  the block."
- "Translation is expressed in logical coordinates, in metres."
- "The label is sticky: setting it exempts that block and following blocks
  until cleared."
- "Returns None when the sequence never uses this label."
- "This state stores the k-space origin of the current excitation when
  processing the sequence in chunks."

To remove:

- prose that walks through the implementation line by line;
- stories or scenarios where a direct statement of the rule suffices;
- claims such as "which is nearly all of them", and performance commentary
  without a documented contract;
- explanations of elementary operations visible in the implementation;
- the same design justification repeated in every function it affects;
- verbose restatements of argument names and type annotations.

When editing documentation:

- Preserve runtime behaviour, signatures, public API and algorithms. Never
  change behaviour to make a docstring true; make the docstring describe the
  behaviour.
- Do not refactor unrelated code in the same change.
- Fix grammar, spelling, terminology and awkward phrasing in what you touch.
- Keep meaningful existing documentation, even when it needs a full rewrite.
- Prefer deleting redundant prose over replacing it with different redundant
  prose.
- No gratuitous formatting, headings, notes, examples or cross-references.
- No new documentation dependencies or linting tools.

## Documentation audit

When asked to audit documentation, cover every package, module, class, method,
function, property and private helper, not a representative sample. After the
pass:

- search again for unusually long docstrings and inspect each; a long docstring
  must justify its length with genuinely useful semantics;
- search for trivial or filler docstrings on private helpers and remove those
  that add nothing;
- check package and module docstrings for essay-style prose;
- review the complete diff for lost units, frames, composition order,
  invariants, state semantics, side effects and return conventions;
- run the normal tests and checks.

Then report the areas audited, the kinds of problems corrected, any long
docstrings kept and why, and the checks run with their results.

## Documentation style

The audience is MR scientists. Write in the vocabulary of pulse sequences and
physics, not of software architecture. Never justify a design by describing the
design it replaced.

Do not print a measured constant that is not guaranteed across releases or
hardware. Name the symbol and where it comes from, and let the build supply the
number. Benchmark tables in the README are regenerated by the benchmark script,
not typed in.
