import pytest

from pulserver.protocol import (
    PROTOCOL_BEGIN,
    PROTOCOL_END,
    InputMode,
    Kind,
    Parameter,
    TEPreset,
    Validation,
    format_listing,
    format_validation,
    format_values,
    parse_listing,
    parse_validation,
    parse_values,
)

LISTING = {
    "TE": Parameter(
        Kind.FLOAT,
        8.0,
        InputMode.DROPDOWN,
        1.0,
        80.0,
        0.1,
        "ms",
        (TEPreset.MINIMUM, 5.0, 8.0),
    ),
    "TR": Parameter(Kind.FLOAT, 250.0, InputMode.TYPEIN, 5.0, 5000.0, 1.0, "ms"),
    "matrix": Parameter(Kind.INT, 128, InputMode.DROPDOWN, 64, 512, 64, "", (128, 256)),
    "swap_pf": Parameter(Kind.BOOL, False),
    "sequence_type": Parameter(
        Kind.STRINGLIST, "gre", InputMode.DROPDOWN, options=("gre", "se")
    ),
    "enable_sar_burst": Parameter(Kind.CONFIG, 1, InputMode.OFF),
    "note": Parameter(Kind.DESCRIPTION, "Line one\nline two"),
}

# One line per kind, in the grammar pulseg_protocol_parse reads.
LISTED_LINES = [
    "TE: float|dropdown|8.0|1.0|80.0|0.1|ms|-2.0|5.0|8.0",
    "TR: float|typein|250.0|5.0|5000.0|1.0|ms",
    "matrix: int|dropdown|128|64|512|64||128|256",
    "swap_pf: bool|false",
    "sequence_type: stringlist|0|gre|se",
    "enable_sar_burst: config|1",
    "note: description|Line one\\nline two",
]


def test_every_listed_line_matches_the_interpreter_grammar():
    lines = format_listing(LISTING).splitlines()
    assert lines == [PROTOCOL_BEGIN, *LISTED_LINES, PROTOCOL_END]


def test_a_listed_protocol_parses_back_to_the_same_schema():
    assert parse_listing(format_listing(LISTING)) == LISTING


def test_a_preset_travels_as_its_negative_dropdown_value():
    block = format_values({"TE": TEPreset.MINIMUM}, LISTING)
    assert "TE: -2.0" in block.splitlines()
    assert parse_values(block, LISTING)["TE"] == TEPreset.MINIMUM


def test_a_stringlist_value_is_read_by_option_or_by_index():
    by_index = f"{PROTOCOL_BEGIN}\nsequence_type: 1\n{PROTOCOL_END}"
    by_option = f"{PROTOCOL_BEGIN}\nsequence_type: se\n{PROTOCOL_END}"
    assert parse_values(by_index, LISTING) == {"sequence_type": "se"}
    assert parse_values(by_option, LISTING) == {"sequence_type": "se"}
    assert "sequence_type: 1" in format_values({"sequence_type": "se"}, LISTING)


def test_read_only_entries_travel_in_listings_but_not_in_values():
    block = format_values({"TR": 10.0, "enable_sar_burst": 1, "note": "x"}, LISTING)
    assert block.splitlines() == [PROTOCOL_BEGIN, "TR: 10.0", PROTOCOL_END]
    sent = f"{PROTOCOL_BEGIN}\nTR: 10\nnote: anything\n{PROTOCOL_END}"
    assert parse_values(sent, LISTING) == {"TR": 10.0}


def test_a_value_for_an_undeclared_parameter_is_refused():
    with pytest.raises(ValueError, match="flip"):
        parse_values(f"{PROTOCOL_BEGIN}\nflip: 10\n{PROTOCOL_END}", LISTING)


@pytest.mark.parametrize(
    "validation",
    [
        Validation(True, 1.5, "TA = 0:02", {"TE": 2.74, "TR": 6.34}),
        Validation(True, None, "", {"swap_pf": True}),
        Validation(False, None, "the requested TR is too short", {"TR": 1.0}),
    ],
    ids=["valid", "no-duration", "invalid"],
)
def test_a_validation_reply_round_trips(validation):
    assert (
        parse_validation(format_validation(validation, LISTING), LISTING) == validation
    )


def test_a_dropdown_without_options_is_refused():
    with pytest.raises(ValueError, match="dropdown"):
        Parameter(Kind.FLOAT, 1.0, InputMode.DROPDOWN)
