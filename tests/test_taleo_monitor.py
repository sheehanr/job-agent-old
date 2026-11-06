import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "src", "company_monitors")
)

import taleo_monitor  # noqa: E402


class FakeResponse:

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _req(job, title, location):
    return {
        "contestNo": job,
        "column": [title, f'["{location}"]', "10/01/2026"],
    }


PAGES = {
    1: {
        "requisitionList": [
            _req("342925", "2027 Intern - Autonomy Engineer (Air Systems)",
                 "US-Maryland-Hunt Valley"),
            _req("342999", "Internal Controls Manager",
                 "US-Rhode Island-Providence"),
        ],
        "pagingData": {"pageSize": 2, "totalCount": 3},
    },
    2: {
        "requisitionList": [
            _req("342935", "2027 Intern - Firmware Engineer (Weapons)",
                 "US-Maryland-Hunt Valley"),
        ],
        "pagingData": {"pageSize": 2, "totalCount": 3},
    },
}


def test_parses_requisitions_and_pages(monkeypatch):

    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append(json["pageNo"])
        return FakeResponse(PAGES[json["pageNo"]])

    monkeypatch.setattr(taleo_monitor.requests, "post", fake_post)

    results = taleo_monitor.get_taleo_internships(
        "Textron Systems", "textron.taleo.net", "textron", "8140753014"
    )

    # Same two pages once per search term; results deduped across terms.
    assert calls == [1, 2] * len(taleo_monitor.INTERN_SEARCH_TERMS)
    assert [(r["title"], r["role_type"]) for r in results] == [
        ("2027 Intern - Autonomy Engineer (Air Systems)", "Robotics"),
        ("2027 Intern - Firmware Engineer (Weapons)", "Firmware"),
    ]
    assert results[0]["location"] == "US-Maryland-Hunt Valley"
    assert results[0]["application_url"] == (
        "https://textron.taleo.net/careersection/textron/"
        "jobdetail.ftl?job=342925&lang=en"
    )


def test_network_failure_returns_empty_list(monkeypatch):

    def raise_error(url, json, headers, timeout):
        raise ConnectionError("boom")

    monkeypatch.setattr(taleo_monitor.requests, "post", raise_error)

    assert taleo_monitor.get_taleo_internships(
        "Textron Systems", "textron.taleo.net", "textron", "8140753014"
    ) == []
