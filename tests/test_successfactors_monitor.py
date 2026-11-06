import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "src", "company_monitors")
)

import successfactors_monitor  # noqa: E402


class FakeResponse:

    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def _row(title, href, location):
    # Real pages render the title link twice per row (desktop + mobile).
    link = f'<a href="{href}" class="jobTitle-link">{title}</a>'
    return (
        f'<tr class="data-row">{link}{link}'
        f'<span class="jobLocation">\n  {location}\n</span></tr>'
    )


PAGE = "<table>" + "".join([
    _row("EMBEDDED SOFTWARE ENGINEER INTERN",
         "/job/Newport-News-Embedded-Intern/1234567/", "Newport News, VA"),
    _row("INTERNAL AUDITOR 3",
         "/job/Newport-News-Internal-Auditor/7654321/", "Newport News, VA"),
    _row("Systems &amp; Software Co-op",
         "/job/Pascagoula-Co-op/1111111/", "Pascagoula, MS"),
]) + "</table>"


def test_parses_rows_dedups_and_filters(monkeypatch):

    monkeypatch.setattr(
        successfactors_monitor.requests, "get",
        lambda url, params, headers, timeout: FakeResponse(PAGE)
    )

    results = successfactors_monitor.get_successfactors_internships(
        "HII", "careers.huntingtoningalls.com"
    )

    assert [r["title"] for r in results] == [
        "EMBEDDED SOFTWARE ENGINEER INTERN",
        "Systems & Software Co-op",
    ]

    first = results[0]
    assert first["role_type"] == "Embedded"
    assert first["location"] == "Newport News, VA"
    assert first["external_job_id"] == "1234567"
    assert first["application_url"] == (
        "https://careers.huntingtoningalls.com"
        "/job/Newport-News-Embedded-Intern/1234567/"
    )


def test_network_failure_returns_empty_list(monkeypatch):

    def raise_error(url, params, headers, timeout):
        raise ConnectionError("boom")

    monkeypatch.setattr(successfactors_monitor.requests, "get", raise_error)

    assert successfactors_monitor.get_successfactors_internships(
        "HII", "careers.huntingtoningalls.com"
    ) == []


def test_searches_every_intern_and_coop_term(monkeypatch):

    searched = []

    class EmptyResponse:
        text = ""

        def raise_for_status(self):
            pass

    def fake_get(url, params, headers, timeout):
        searched.append(params["q"])
        return EmptyResponse()

    monkeypatch.setattr(successfactors_monitor.requests, "get", fake_get)

    successfactors_monitor.get_successfactors_internships(
        "Boston Scientific", "jobs.bostonscientific.com"
    )

    assert searched == list(successfactors_monitor.INTERN_SEARCH_TERMS)


TILE_PAGE = """
<ul id="job-tile-list" class="container job-list">
<li class="job-tile job-id-1376869857 job-row-index-1" data-url="/NorthAmerica/job/x/1376869857/">
  <a class="jobTitle-link fontcolor75f4" data-focus-tile=".job-id-1376869857" href="/NorthAmerica/job/Naples-Software-Engineering-Co-op/1376869857/">
      Software Engineering Co-op
  </a>
  <div id="job-1376869857-desktop-section-location-value">Naples, FL, US, 34108
  </div>
  <a class="jobTitle-link fontcolor75f4" href="/NorthAmerica/job/Naples-Software-Engineering-Co-op/1376869857/">Software Engineering Co-op</a>
</li>
<li class="job-tile job-id-1376689657 job-row-index-2" data-url="/Germany/job/x/1376689657/">
  <a class="jobTitle-link fontcolor75f4" href="/Germany/job/International-Product-Manager/1376689657/">
      International Product Manager
  </a>
  <div id="job-1376689657-desktop-section-location-value">München, DE
  </div>
</li>
</ul>
"""


def test_parses_tile_layout(monkeypatch):
    """Some Career Site Builder sites (e.g. Arthrex) render results as
    <li class="job-tile"> tiles instead of table rows."""

    class TileResponse:
        text = TILE_PAGE

        def raise_for_status(self):
            pass

    monkeypatch.setattr(
        successfactors_monitor.requests, "get",
        lambda url, params, headers, timeout: TileResponse()
    )

    results = successfactors_monitor.get_successfactors_internships(
        "Arthrex", "careers.arthrex.com"
    )

    assert len(results) == 1
    job = results[0]
    assert job["title"] == "Software Engineering Co-op"
    assert job["location"] == "Naples, FL, US, 34108"
    assert job["external_job_id"] == "1376869857"
    assert job["application_url"] == (
        "https://careers.arthrex.com/NorthAmerica/job/"
        "Naples-Software-Engineering-Co-op/1376869857/"
    )
