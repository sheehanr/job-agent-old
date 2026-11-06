import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "src", "company_monitors")
)

import lever_monitor  # noqa: E402


class FakeResponse:

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _posting(pid, title, location, country=None, commitment="Full-time",
             all_locations=None):
    return {
        "id": pid,
        "text": title,
        "country": country,
        "hostedUrl": f"https://jobs.lever.co/veeva/{pid}",
        "applyUrl": f"https://jobs.lever.co/veeva/{pid}/apply",
        "categories": {
            "commitment": commitment,
            "location": location,
            "allLocations": all_locations or [location],
        },
    }


POSTINGS = [
    _posting("a1", "Software Engineer Intern", "Pleasanton, CA", "US"),
    _posting("a2", "Data Science Co-op", "Toronto", "CA"),
    _posting("a3", "Associate Consultant (R&D)", "China - Shanghai", "CN",
             commitment="Internship"),
    _posting("a4", "Senior Software Engineer", "Boston, MA", "US"),
    _posting("a5", "Software Engineering Intern", "Boston, MA", None,
             all_locations=["Boston, MA", "Toronto, ON"]),
]


def test_filters_interns_by_title_or_commitment(monkeypatch):

    monkeypatch.setattr(
        lever_monitor.requests, "get",
        lambda url, params, headers, timeout: FakeResponse(POSTINGS)
    )

    results = lever_monitor.get_lever_internships("Veeva Systems", "veeva")

    by_id = {r["external_job_id"]: r for r in results}

    assert set(by_id) == {"a1", "a2", "a3", "a5"}
    assert by_id["a1"]["role_type"] == "SWE"
    assert by_id["a1"]["source_platform"] == "lever"
    assert by_id["a1"]["application_url"] == "https://jobs.lever.co/veeva/a1"


def test_country_code_spelled_out(monkeypatch):
    """Lever's "CA" is Canada - it must not read as California."""

    from location_filter import classify_location

    monkeypatch.setattr(
        lever_monitor.requests, "get",
        lambda url, params, headers, timeout: FakeResponse(POSTINGS)
    )

    by_id = {
        r["external_job_id"]: r
        for r in lever_monitor.get_lever_internships("Veeva", "veeva")
    }

    assert by_id["a1"]["location"] == "Pleasanton, CA, United States"
    assert by_id["a2"]["location"] == "Toronto, Canada"
    assert classify_location(by_id["a1"]["location"]) == "us"
    assert classify_location(by_id["a2"]["location"]) == "non_us"
    assert by_id["a5"]["location"] == "Boston, MA; Toronto, ON"


def test_network_failure_returns_empty_list(monkeypatch):

    def boom(url, params, headers, timeout):
        raise ConnectionError("down")

    monkeypatch.setattr(lever_monitor.requests, "get", boom)

    assert lever_monitor.get_lever_internships("Veeva", "veeva") == []
