"""Targets, output schema, and default output path for the scraper."""

from pathlib import Path

TARGET_ASSEMBLIES: set[str] = {"11", "10"}
TARGET_SESSIONS: set[str] = set()  # empty = every session in assemblies 10 and 11

COLUMNS: list[str] = [
    "Assembly", "Session", "Session_Date", "DL_Category", "Sr_No",
    "Question_Number", "Subject", "Questions", "Category", "Departments",
    "Ministry", "Asked_By", "Reply", "Reply_Regional", "Document_Link",
]

# Raw CSV location: a data/ folder at the monorepo root (created on first run).
ROOT: Path = Path(__file__).resolve().parents[4]
DEFAULT_OUT: Path = ROOT / "data" / "dl_questions_raw.csv"
