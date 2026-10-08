"""Minimal plain-HTTP client for the NeVA Digital Library portal.

Replays the three read-only endpoints the portal's own page JS uses:
- /Home/DLGetFilterOptionbyType?SearchTypeID=1        -> filter HTML (assemblies)
- /Home/AssemblyChange?AssemblyId=..                  -> JSON sessions
- /Home/SessionChangeNew?AssemblyId=..&SessionId=..   -> JSON session dates

A warm-up request is required first: the endpoints need the ASP.NET
session cookie handed out by the site root.
"""

import re

import requests

BASE_URL = "https://mgla.neva.gov.in"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Edge/154"
TIMEOUT = 30
PLACEHOLDERS = {"Select", "--Select--"}


class Portal:
    def __init__(self, base=BASE_URL, session=None):
        self.base = base
        self.http = session if session is not None else requests.Session()
        self.http.headers["User-Agent"] = USER_AGENT
        self.http.get(base, timeout=TIMEOUT).raise_for_status()

    def get(self, path, **params):
        response = self.http.get(self.base + path, params=params, timeout=TIMEOUT)
        response.raise_for_status()
        return response

    def assemblies(self):
        """[(value, label), ...] from the filter panel's assembly dropdown."""
        page = self.get("/Home/DLGetFilterOptionbyType", SearchTypeID=1).text
        return select_options(page, "assemblyLst")

    def sessions(self, assembly):
        return self.get("/Home/AssemblyChange", AssemblyId=assembly).json()

    def dates(self, assembly, session):
        return self.get(
            "/Home/SessionChangeNew", AssemblyId=assembly, SessionId=session
        ).json()


def select_options(page, select_id):
    """(value, label) pairs of one <select>, placeholders dropped."""
    block = re.search(
        r'<select[^>]*id="%s"[^>]*>(.*?)</select>' % re.escape(select_id), page or "", re.S
    )
    if not block:
        return []
    options = []
    for value, label in re.findall(r'<option value="([^"]*)"[^>]*>(.*?)</option>', block.group(1), re.S):
        label = re.sub(r"<[^>]+>", "", label).strip()
        if value and value != "0" and label and label not in PLACEHOLDERS:
            options.append((value, label))
    return options
