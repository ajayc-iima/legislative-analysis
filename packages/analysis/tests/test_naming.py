"""Shortest display label that still identifies one member."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from legislative_analysis.naming import (  # noqa: E402
    member_labels, shared_surnames, surname_counts,
)

SANGMAS = ["Mukul Sangma", "Zenith M. Sangma", "Saleng A. Sangma",
           "Mehtab Chandee A Sangma"]
LYNGDOHS = ["George B. Lyngdoh", "Ronnie V. Lyngdoh", "Paul Lyngdoh"]


def test_unique_surname_reduces_to_surname():
    labels = member_labels(SANGMAS + ["Heaving Stone Kharpran"])
    assert labels["Heaving Stone Kharpran"] == "Kharpran"


def test_shared_surname_keeps_given_name():
    labels = member_labels(SANGMAS)
    assert labels["Mukul Sangma"] == "Mukul Sangma"
    assert labels["Zenith M. Sangma"] == "Zenith Sangma"
    assert labels["Saleng A. Sangma"] == "Saleng Sangma"
    assert labels["Mehtab Chandee A Sangma"] == "Mehtab Sangma"


def test_every_label_identifies_exactly_one_member():
    people = SANGMAS + LYNGDOHS + ["Adelbert Nongrum", "David A Nongrum",
                                    "Heaving Stone Kharpran"]
    labels = member_labels(people)
    assert len(set(labels.values())) == len(people)


def test_shared_given_name_falls_back_to_full_name():
    # two members called Mukul Sangma: the short form identifies nobody
    labels = member_labels(["Mukul Sangma", "Mukul A. Sangma"])
    assert labels["Mukul Sangma"] == "Mukul Sangma"
    assert labels["Mukul A. Sangma"] == "Mukul A. Sangma"


def test_singleton_surname_reduces_even_alongside_other_families():
    # "Lyngdoh" is unique in this input set, so it identifies its holder
    labels = member_labels(["Paul Lyngdoh"] + SANGMAS)
    assert labels["Paul Lyngdoh"] == "Lyngdoh"


def test_punctuation_and_spacing_variants_are_one_person():
    people = ["Zenith M. Sangma", "Zenith M Sangma", "Zenith M. Sangma,"]
    labels = member_labels(people)
    # trailing-punctuation variants are one person, so they share a label
    # and do not read as a name collision
    assert len(set(labels.values())) == 1
    assert labels["Zenith M. Sangma"] == labels["Zenith M Sangma"]


def test_labels_ignore_names_outside_the_figure():
    """A top-20 chart must still expand a name a second member shares."""
    in_figure = ["Adelbert Nongrum", "Mukul Sangma"]
    whole_assembly = in_figure + ["David A Nongrum", "Zenith M. Sangma"]
    labels = member_labels(whole_assembly)
    assert labels["Adelbert Nongrum"] == "Adelbert Nongrum"
    assert labels["Mukul Sangma"] == "Mukul Sangma"


def test_shared_surname_counts():
    counts = surname_counts(SANGMAS + LYNGDOHS)
    assert counts["Sangma"] == 4
    assert counts["Lyngdoh"] == 3
    assert shared_surnames(SANGMAS + LYNGDOHS) == {"Sangma", "Lyngdoh"}


@pytest.mark.parametrize("name", ["", "   ", None])
def test_blank_names_are_dropped(name):
    assert member_labels([name, "Paul Lyngdoh"]) == {"Paul Lyngdoh": "Lyngdoh"}


def test_labels_are_deterministic():
    people = SANGMAS + LYNGDOHS
    assert member_labels(people) == member_labels(list(reversed(people)))
