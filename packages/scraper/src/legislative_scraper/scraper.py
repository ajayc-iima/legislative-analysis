"""NeVA Digital Library Questions scraper: assemblies x sessions x dates -> rows."""

import argparse
import csv
import traceback
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

from . import client, config

EMPTY_MARKERS = ("no records", "no data", "no record")


def clean_label(text):
    return (text or "").strip().rstrip(".").strip()


def matches(text, targets=None):
    """True when a portal session label is wanted (empty targets = all)."""
    if targets is None:
        targets = config.TARGET_SESSIONS
    if not targets:
        return True
    want = clean_label(text).casefold()
    return any(clean_label(t).casefold() == want for t in targets)


class _Table(HTMLParser):
    """One flat results table -> (headers, [([cell texts], [hrefs])])."""

    def __init__(self):
        super().__init__()
        self.headers = []
        self.rows = []
        self._row = None
        self._header_row = False
        self._cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row, self._header_row = [], False
        elif tag in ("th", "td"):
            if self._row is not None and self._cell is None:
                self._cell = {"text": "", "links": []}
                if tag == "th":
                    self._header_row = True
        elif tag == "a" and self._cell is not None:
            href = dict(attrs).get("href", "").strip()
            if href and href != "#" and "javascript" not in href:
                self._cell["links"].append(urljoin(client.BASE_URL + "/", href))

    def handle_data(self, data):
        if self._cell is not None:
            self._cell["text"] += data

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            row, header = self._row, self._header_row
            self._row = None
            if header:
                if not self.headers:
                    self.headers = [c["text"].strip() for c in row]
            else:
                cells = [c["text"].strip() for c in row]
                links = [u for c in row for u in c["links"]]
                if len(cells) >= 3 and any(cells + links):
                    self.rows.append((cells, links))


def parse_table(html):
    """Parse search HTML; ([], []) when the portal reports no records."""
    if any(m in (html or "").casefold() for m in EMPTY_MARKERS):
        return [], []
    table = _Table()
    table.feed(html or "")
    return table.rows, table.headers


def build_record(cells, links, assembly, session, date):
    """Map one 9-column result row to a COLUMNS-shaped dict.

    Column order is the portal's fixed layout (Sr, Title, Details,
    Category, Member, Ministry->Departments, Department(s)->Ministry,
    Reply, Reply Regional).
    """
    get = lambda i: cells[i] if i < len(cells) else ""
    links = links or []
    pdf = next((u for u in links if u.split("?")[0].split("#")[0].lower().endswith(".pdf")), "")
    return {"Assembly": assembly, "Session": session, "Session_Date": date,
        "DL_Category": "DL Questions", "Sr_No": get(0), "Question_Number": get(1),
        "Subject": get(1), "Questions": get(2), "Category": get(3),
        "Departments": get(5), "Ministry": get(6), "Asked_By": get(4),
        "Reply": get(7), "Reply_Regional": get(8),
        "Document_Link": pdf or next((u for u in links if u.startswith("http")), "")}


def _options(items, value_key, text_key):
    """(value, label) pairs from a JSON option list, placeholders dropped."""
    options = []
    for item in items or []:
        value, text = str(item.get(value_key) or "").strip(), str(item.get(text_key) or "").strip()
        if value and value != "0" and text and text not in client.PLACEHOLDERS:
            options.append((value, text))
    return options


def scrape(portal=None, rows=None):
    portal = portal or client.Portal()
    rows = [] if rows is None else rows
    assemblies = portal.assemblies()
    targets = [a for a in assemblies
               if a[0] in config.TARGET_ASSEMBLIES or any(t in a[1] for t in config.TARGET_ASSEMBLIES)]
    if not targets:
        if not assemblies:
            print("No assemblies found in filter response; skipping")
            return rows
        print("Assembly filter matched nothing; scraping all assemblies instead")
        targets = assemblies
    for assembly_value, assembly_text in targets:
        sessions = _options(portal.sessions(assembly_value), "SessionCode", "SessionName")
        if not sessions:
            print(f"No sessions found for assembly {assembly_text}; skipping")
            continue
        for session_value, session_text in sessions:
            if not matches(session_text):
                continue
            label = clean_label(session_text)
            dates = _options(portal.dates(assembly_value, session_value), "SessionDateId", "SessionDate")
            if not dates:
                print(f"No session dates found for session {label} in assembly {assembly_text}; skipping")
                continue
            for date_value, date_text in dates:
                html = portal.get("/Home/DigitalLibrarySearchList", AssId=assembly_value,
                    SessId=session_value, filterType="0",
                    sesiondatetid=date_value, searchText="").text
                before = len(rows)
                for cells, links in parse_table(html)[0]:
                    rows.append(build_record(cells, links, assembly_text, label, date_text))
                print(f"  {assembly_text} | {label} | {date_text}: {len(rows) - before} rows")
    return rows


def save(rows, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, config.COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=config.DEFAULT_OUT)
    args = parser.parse_args(argv)
    rows = []
    try:
        scrape(client.Portal(), rows)
        save(rows, args.out)
        print(f"Saved {len(rows)} rows to {args.out}")
        if not rows:
            print("WARNING: 0 rows scraped — header-only CSV written; portal may be slow or filters matched nothing")
    except KeyboardInterrupt:
        print(f"Interrupted; saving {len(rows)} partial rows to {args.out}")
        save(rows, args.out)
        return 1
    except Exception:
        traceback.print_exc()
        return 1
    return 0
