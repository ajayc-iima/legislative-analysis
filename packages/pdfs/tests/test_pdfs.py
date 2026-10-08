"""Tests for the PDF downloader layout and backfill (no live downloads)."""

import csv

from legislative_pdfs.pdfs import (assembly_number, copy_from, slug, target_path,
                                   unique_rows)

ROW = {
    "Assembly": "Eleventh Meghalaya Legislative Assembly",
    "Session": "Autumn Session, 2026",
    "Document_Link": "https://cms.neva.gov.in/NeVA/ML/FileStructures//PaperLaid/11/9/Signed/11_9_S_4037_V1_signed.pdf",
}


def test_slug():
    assert slug("Autumn Session, 2026") == "autumn-session-2026"
    assert slug("") == "unknown"


def test_assembly_number_from_url_and_label():
    assert assembly_number(ROW) == 11
    fallback = {**ROW, "Document_Link": "https://cms/x/y.pdf",
                "Assembly": "Tenth Meghalaya Legislative Assembly"}
    assert assembly_number(fallback) == 10
    assert assembly_number({"Assembly": "", "Document_Link": ""}) == 0


def test_target_path_shape():
    path = target_path("data/pdfs", ROW)
    assert path.parts[-3:] == ("assembly-11", "autumn-session-2026",
                               "11_9_S_4037_V1_signed.pdf")


def test_unique_rows_dedupes_and_skips_non_links(tmp_path):
    csv_path = tmp_path / "q.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ROW))
        writer.writeheader()
        writer.writerow(ROW)
        writer.writerow(ROW)  # duplicate destination
        writer.writerow({**ROW, "Document_Link": ""})
        writer.writerow({**ROW, "Document_Link": "not-a-link"})
    assert len(unique_rows(csv_path)) == 1


def test_copy_from_copies_then_skips(tmp_path):
    csv_path = tmp_path / "q.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ROW))
        writer.writeheader()
        writer.writerow(ROW)
    source = tmp_path / "src"
    source.mkdir()
    (source / "11_9_S_4037_V1_signed.pdf").write_bytes(b"%PDF-1.4 test")
    root = tmp_path / "out"

    copied, skipped, missing = copy_from(csv_path, root, source)
    assert (copied, skipped, missing) == (1, 0, 0)
    target = target_path(root, ROW)
    assert target.read_bytes() == b"%PDF-1.4 test"

    copied, skipped, missing = copy_from(csv_path, root, source)
    assert (copied, skipped, missing) == (0, 1, 0)
    # a source that lacks the file reports it missing
    copied, skipped, missing = copy_from(csv_path, tmp_path / "out2", tmp_path / "empty")
    assert (copied, skipped, missing) == (0, 0, 1)
