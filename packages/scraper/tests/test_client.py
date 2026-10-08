"""Tests for the portal client (fake HTTP session; no live calls)."""

from legislative_scraper.client import Portal, select_options

FILTER_HTML = (
    '<select id="assemblyLst">'
    '<option value="0">Select</option>'
    '<option value="11">Eleventh Meghalaya Legislative Assembly</option>'
    '<option value="10">Tenth Meghalaya Legislative Assembly</option>'
    "</select>"
)


def test_select_options_skips_placeholders():
    assert select_options(FILTER_HTML, "assemblyLst") == [
        ("11", "Eleventh Meghalaya Legislative Assembly"),
        ("10", "Tenth Meghalaya Legislative Assembly"),
    ]


def test_select_options_missing_select():
    assert select_options("<div></div>", "assemblyLst") == []


class FakeResponse:
    def __init__(self, text="", payload=None):
        self.text = text
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeSession:
    """Stands in for requests.Session; serves one canned response per path."""

    def __init__(self, canned):
        self.headers = {}
        self.canned = canned
        self.calls = []

    def get(self, url, params=None, **kwargs):
        self.calls.append((url, params))
        for path, response in self.canned.items():
            if url.endswith(path):
                return response
        return FakeResponse()


def make_portal(canned):
    return Portal("https://fake.test", session=FakeSession(canned))


def test_assemblies_reads_filter_panel():
    portal = make_portal({"/Home/DLGetFilterOptionbyType": FakeResponse(text=FILTER_HTML)})
    assert portal.assemblies()[0] == ("11", "Eleventh Meghalaya Legislative Assembly")
    assert portal.http.calls[1][0].endswith("/Home/DLGetFilterOptionbyType")
    assert portal.http.calls[1][1] == {"SearchTypeID": 1}


def test_sessions_and_dates_hit_portal_endpoints():
    sessions = [{"SessionCode": 9, "SessionName": "Autumn Session, 2026."}]
    dates = [{"SessionDateId": 1882, "SessionDate": "28/Aug/2026"}]
    portal = make_portal({"/Home/AssemblyChange": FakeResponse(payload=sessions),
                          "/Home/SessionChangeNew": FakeResponse(payload=dates)})
    assert portal.sessions("11") == sessions
    assert portal.dates("11", "9") == dates
    assert portal.http.calls[1] == ("https://fake.test/Home/AssemblyChange", {"AssemblyId": "11"})
    assert portal.http.calls[2] == ("https://fake.test/Home/SessionChangeNew",
                                    {"AssemblyId": "11", "SessionId": "9"})
