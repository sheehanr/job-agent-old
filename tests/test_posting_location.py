import json

import posting_location


class FakeResponse:

    def __init__(self, payload=None, text=""):
        self._payload = payload
        self.text = text

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _page(data):
    return (
        "<html><head><script type=\"application/ld+json\">"
        + json.dumps(data)
        + "</script></head><body>Job</body></html>"
    )


def test_reads_jobposting_json_ld_address():

    html = _page({
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Software Engineer Intern",
        "jobLocation": {
            "@type": "Place",
            "address": {
                "addressLocality": "Verona",
                "addressRegion": "WI",
                "addressCountry": "US",
            },
        },
    })

    assert posting_location.location_from_html(html) == "Verona, WI, US"


def test_reads_multiple_locations_and_graph():

    html = _page({"@graph": [{
        "@type": "JobPosting",
        "jobLocation": [
            {"address": {"addressLocality": "Sunnyvale",
                         "addressCountry": {"name": "United States"}}},
            {"address": {"addressLocality": "Aubonne",
                         "addressCountry": "Switzerland"}},
        ],
    }]})

    assert posting_location.location_from_html(html) == (
        "Sunnyvale, United States; Aubonne, Switzerland"
    )


def test_remote_posting_uses_applicant_location_requirements():

    html = _page({
        "@type": "JobPosting",
        "jobLocationType": "TELECOMMUTE",
        "applicantLocationRequirements": {
            "@type": "Country", "name": "USA"
        },
    })

    assert posting_location.location_from_html(html) == "Remote - USA"


def test_no_json_ld_returns_empty():

    assert posting_location.location_from_html("<html>nothing</html>") == ""
    assert posting_location.location_from_html(
        '<script type="application/ld+json">{not json</script>'
    ) == ""


def test_workday_location_uses_detail_endpoint(monkeypatch):

    requested = {}

    def fake_get(url, headers, timeout):
        requested["url"] = url
        return FakeResponse({"jobPostingInfo": {
            "location": "TARRYTOWN",
            "country": {"descriptor": "United States of America"},
            "additionalLocations": ["Rensselaer"],
        }})

    monkeypatch.setattr(posting_location.requests, "get", fake_get)

    location = posting_location.workday_location(
        "https://regeneron.wd1.myworkdayjobs.com/en-US/Careers"
        "/job/Tarrytown-NY/IT-Intern_R123",
        "regeneron",
    )

    assert requested["url"] == (
        "https://regeneron.wd1.myworkdayjobs.com/wday/cxs/regeneron/Careers"
        "/job/Tarrytown-NY/IT-Intern_R123"
    )
    assert location == "TARRYTOWN, United States of America; Rensselaer"


def test_workday_location_failure_returns_empty(monkeypatch):

    def boom(url, headers, timeout):
        raise ConnectionError("down")

    monkeypatch.setattr(posting_location.requests, "get", boom)

    assert posting_location.workday_location(
        "https://x.wd1.myworkdayjobs.com/en-US/Site/job/A_1", "x"
    ) == ""
