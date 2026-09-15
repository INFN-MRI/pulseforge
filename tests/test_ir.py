import re
import shutil
import struct
import subprocess
from pathlib import Path

import pypulseqpp as pp
import pytest
from pypulseqpp import sequences

from pulserver.ir import cache_path, chain, convert, summary

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "sequences"
C_SOURCES = ROOT / "src" / "c"
CONTINUATIONS = {
    match.decode()
    for path in FIXTURES.glob("*.seq")
    for match in re.findall(rb"^NextSequence\s+(\S+)", path.read_bytes(), re.MULTILINE)
}
SEQUENCES = sorted(
    path.name for path in FIXTURES.iterdir() if path.name not in CONTINUATIONS
)
# The limits the library's C cache tests convert these fixtures under.
SYSTEM = pp.Opts(
    max_grad=40.0,
    grad_unit="mT/m",
    max_slew=170.0,
    slew_unit="T/m/s",
    B0=3.0,
    rf_raster_time=1e-6,
    grad_raster_time=1e-5,
    adc_raster_time=1e-7,
    block_duration_raster=1e-5,
)
GEHC = 2
GE_LABELS = (8, 0, 6)


def _copy(name, directory):
    """Copy the fixture folder, so a chain's continuation files come along."""
    shutil.copytree(FIXTURES, directory, dirs_exist_ok=True)
    return directory / name


@pytest.mark.parametrize("name", SEQUENCES)
def test_a_converted_cache_reads_back_as_the_parse_it_came_from(name, tmp_path):
    seq = _copy(name, tmp_path)
    signed = seq.suffix == ".seq"
    assert convert(seq, SYSTEM, verify_signature=signed) == cache_path(seq)
    assert summary(seq, SYSTEM, cache_ext=".pseg") == summary(seq, SYSTEM)


def test_the_chain_lists_every_file_in_play_order(tmp_path):
    seq = _copy("dedup_gre_pair.seq", tmp_path)
    assert [p.name for p in chain(seq)] == [
        "dedup_gre_pair.seq",
        "dedup_gre_pair_b.seq",
    ]


def test_the_cache_is_named_by_the_extension_it_was_given(tmp_path):
    seq = _copy("gre_2d_3sl.seq", tmp_path)
    assert convert(seq, SYSTEM, cache_ext=".pge") == tmp_path / "gre_2d_3sl.pge"
    assert not (tmp_path / "gre_2d_3sl.pseg").exists()


def test_the_cache_header_carries_the_vendor_and_file_size_it_was_given(tmp_path):
    seq = _copy("gre_2d_3sl.seq", tmp_path)
    header = convert(seq, SYSTEM, vendor=GEHC).read_bytes()[:24]
    _marker, _major, _minor, _revision, vendor, size = struct.unpack("<6i", header)
    assert (vendor, size) == (GEHC, seq.stat().st_size)


def test_a_reader_built_for_another_vendor_refuses_the_cache(tmp_path):
    seq = _copy("gre_2d_3sl.seq", tmp_path)
    convert(seq, SYSTEM, vendor=GEHC)
    with pytest.raises(ValueError, match="cannot load"):
        summary(seq, SYSTEM, cache_ext=".pseg")


def test_an_unsigned_file_is_refused_when_verification_is_asked(tmp_path):
    seq = _copy("gre_2d_3sl.seq", tmp_path)
    text = seq.read_text()
    seq.write_text(text[: text.index("[SIGNATURE]")])
    with pytest.raises(ValueError):
        convert(seq, SYSTEM)
    assert convert(seq, SYSTEM, verify_signature=False).is_file()


class _ChainApp(sequences.SequenceApp):
    MAX_GRAD = 40.0
    MAX_SLEW = 150.0

    def init_sequence(self, n_repetitions: int = 3) -> None:
        self.n_repetitions = n_repetitions
        self.adc = pp.make_adc(num_samples=64, duration=3.2e-3, system=self.system)

    def prescans(self):
        return {"dummy": self._dummy}

    def _dummy(self) -> None:
        self.seq.add_block(pp.make_delay(5e-3))

    def loop(self) -> None:
        for _ in range(self.n_repetitions):
            self.kernel()

    def kernel(self) -> None:
        self.seq.add_block(self.adc)
        self.seq.add_block(pp.make_delay(5e-3))


def test_a_prescan_chain_converts_as_subsequences(tmp_path):
    first = Path(_ChainApp(SYSTEM).write(tmp_path / "sequence.seq", offline=True)[0])
    convert(first, SYSTEM)
    assert summary(first, SYSTEM)["num_subsequences"] == 2


def _reader_lines(s):
    lines = [
        f"num_subsequences {s['num_subsequences']}",
        f"num_segments {s['num_segments']}",
        f"max_adc_samples {s['max_adc_samples']}",
        f"total_readouts {s['total_readouts']}",
    ]
    lines += [
        f"subsequence {i} num_trs {x['num_trs']} tr_size {x['tr_size']} "
        f"num_unique_adcs {x['num_unique_adcs']} num_unique_rf {x['num_unique_rf']}"
        for i, x in enumerate(s["subsequences"])
    ]
    lines += [
        f"segment {i} duration_us {x['duration_us']} num_blocks {x['num_blocks']} "
        f"start_block {x['start_block']} is_nav {x['is_nav']}"
        for i, x in enumerate(s["segments"])
    ]
    return lines


@pytest.fixture(scope="module")
def scanner_reader(tmp_path_factory):
    """The cache reader compiled as the scanner builds it: 32-bit, GE vendor."""
    directory = tmp_path_factory.mktemp("reader")
    probe = directory / "probe.c"
    probe.write_text("int main(void) { return 0; }\n")
    toolchain = subprocess.run(
        ["gcc", "-m32", str(probe), "-o", str(directory / "probe")],
        capture_output=True,
        check=False,
    )
    if toolchain.returncode != 0:
        pytest.skip("no 32-bit C toolchain")
    folders = (
        "pulseq",
        "core",
        "io",
        "structure",
        "waveforms",
        "safety",
        "cache",
        "vendor",
    )
    sources = [
        str(p) for folder in folders for p in sorted((C_SOURCES / folder).glob("*.c"))
    ]
    includes = [
        f"-I{C_SOURCES / sub}"
        for sub in (
            "",
            "include",
            "include/pulseg",
            "include/pulseq",
            "pulseq",
            "vendor",
        )
    ]
    output = directory / "read_cache_summary"
    subprocess.run(
        [
            "gcc",
            "-m32",
            "-std=c89",
            f"-DPULSEG_VENDOR={GEHC}",
            *includes,
            str(ROOT / "tests" / "native" / "read_cache_summary.c"),
            *sources,
            "-lm",
            "-o",
            str(output),
        ],
        check=True,
    )
    return output


@pytest.mark.parametrize(
    "name", ["gre_2d_3sl.seq", "epi_2d_main.seq", "mprage_stack_of_spirals_3d.seq"]
)
def test_a_ge_cache_written_here_loads_in_the_scanner_reader(
    name, tmp_path, scanner_reader
):
    seq = _copy(name, tmp_path)
    cache = convert(
        seq, SYSTEM, vendor=GEHC, label_column_map=GE_LABELS, cache_ext=".pge"
    )
    printed = subprocess.run(
        [str(scanner_reader), str(cache), str(seq.stat().st_size)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    expected = summary(seq, SYSTEM, label_column_map=GE_LABELS)
    assert printed.splitlines() == _reader_lines(expected)
