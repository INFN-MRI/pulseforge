"""A Pulseq text file read straight from its sections, as the oracle of a test.

Only what a comparison needs: the numbered tables, the shape library and the
extension chains, in the file's own numbering.
"""

from __future__ import annotations

from pathlib import Path


def sections(path: Path | str) -> dict[str, list[str]]:
    """Every ``[SECTION]`` of a text file, as its non-empty, non-comment lines."""
    found: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in Path(path).read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current = found.setdefault(stripped[1:-1], [])
        elif current is not None and stripped and not stripped.startswith("#"):
            current.append(stripped)
    return found


def table(lines: list[str]) -> dict[int, list[float]]:
    """A numbered table, keyed by the id in its first column.

    A trailing non-numeric field (an RF ``use`` letter) is dropped.
    """
    rows = {}
    for line in lines:
        fields = line.split()
        if not fields[-1].lstrip("-").replace(".", "", 1).isdigit():
            fields = fields[:-1]
        rows[int(fields[0])] = [float(f) for f in fields[1:]]
    return rows


def rf_use(lines: list[str]) -> dict[int, str]:
    """The use letter of every RF row that carries one."""
    return {
        int(line.split()[0]): line.split()[-1]
        for line in lines
        if not line.split()[-1].lstrip("-").replace(".", "", 1).isdigit()
    }


def shapes(lines: list[str]) -> dict[int, tuple[int, list[float]]]:
    """Each shape as ``(uncompressed sample count, stored samples)``."""
    found: dict[int, tuple[int, list[float]]] = {}
    identifier = 0
    count = 0
    samples: list[float] = []
    for line in lines:
        if line.startswith("shape_id"):
            identifier = int(line.split()[1])
            samples = []
        elif line.startswith("num_samples"):
            count = int(line.split()[1])
            found[identifier] = (count, samples)
        else:
            samples.append(float(line))
    return found


def extension_chains(lines: list[str]) -> tuple[dict[int, list[tuple[int, int]]], dict]:
    """The chains and the specification tables of the ``[EXTENSIONS]`` section.

    Returns the chain of every head id as ``[(type number, row id), ...]`` in
    play order, and each ``extension <NAME> <type>`` table as its own numbered
    rows keyed by name.
    """
    links: dict[int, tuple[int, int, int]] = {}
    specifications: dict[str, dict[int, list[float]]] = {}
    numbers: dict[str, int] = {}
    current: list[str] | None = None
    name = ""
    for line in lines:
        if line.startswith("extension "):
            _, name, number = line.split()
            numbers[name] = int(number)
            current = []
            specifications[name] = {}
        elif current is None:
            identifier, kind, reference, following = (int(f) for f in line.split()[:4])
            links[identifier] = (kind, reference, following)
        else:
            fields = line.split()
            specifications[name][int(fields[0])] = [
                float(f) if f.lstrip("-").replace(".", "", 1).isdigit() else f
                for f in fields[1:]
            ]

    by_number = {number: name for name, number in numbers.items()}
    chains = {}
    for head in links:
        walk, node = [], head
        while node:
            kind, reference, following = links[node]
            walk.append((by_number.get(kind, str(kind)), reference))
            node = following
        chains[head] = walk
    return chains, specifications
