import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "src", "company_monitors")
)

import icims_monitor  # noqa: E402


def _card(job_id, title, location):
    return f"""
<li class="iCIMS_JobCardItem">
<div class="row">
<div class="col-xs-12 title">
<a href="https://americas-cookmedical.icims.com/jobs/{job_id}/slug/job?in_iframe=1" class="iCIMS_Anchor" title="{job_id} - {title}">
<span class="sr-only field-label">Title</span>
<h3 >
{title}</h3>
</a>
</div>
<dl class="iCIMS_JobHeaderGroup">
<div class="iCIMS_JobHeaderTag">
<dt class="iCIMS_JobHeaderField"><span class="glyphicons glyphicons-map-marker" aria-hidden="true"></span>
<span class="sr-only field-label">Job Locations</span>
</dt>
<dd class="iCIMS_JobHeaderData"><span >
{location}</span>
</dd>
</div>
</dl>
</div>
</li>"""


def _page(cards, page_count=1):
    return (
        '<ul class="container-fluid iCIMS_JobsTable">'
        + "".join(cards)
        + f"</ul><div>Page 1 of {page_count}</div>"
    )


class FakeResponse:

    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def test_parses_cards_and_dedupes_across_terms(monkeypatch):

    searched = []

    def fake_get(url, params, headers, timeout):
        searched.append(params["searchKeyword"])
        cards = [
            _card("19550", "Intern, Applied AI &amp; Full Stack Development",
                  "US-IN-Bloomington"),
            _card("19999", "Senior Engineer", "US-IN-Bloomington"),
        ]
        if params["searchKeyword"] == "co-op":
            cards.append(
                _card("19984", "Software Engineering Co-op", "US-NC-Winston-Salem")
            )
        return FakeResponse(_page(cards))

    monkeypatch.setattr(icims_monitor.requests, "get", fake_get)

    results = icims_monitor.get_icims_internships(
        "Cook Medical", "americas-cookmedical.icims.com"
    )

    assert searched == list(icims_monitor.INTERN_SEARCH_TERMS)
    assert [r["title"] for r in results] == [
        "Intern, Applied AI & Full Stack Development",
        "Software Engineering Co-op",
    ]
    first = results[0]
    assert first["location"] == "US-IN-Bloomington"
    assert first["external_job_id"] == "19550"
    assert first["role_type"] == "SWE"
    assert first["source_platform"] == "icims"
    # in_iframe=1 dropped so the link opens the full posting page.
    assert first["application_url"] == (
        "https://americas-cookmedical.icims.com/jobs/19550/slug/job"
    )


def test_pages_until_last_page(monkeypatch):

    pages = []

    def fake_get(url, params, headers, timeout):
        if params["searchKeyword"] == "intern":
            pages.append(params["pr"])
        return FakeResponse(_page(
            [_card(f"1{params['pr']}000", f"Data Intern {params['pr']}",
                   "US-IN-Bloomington")],
            page_count=3,
        ))

    monkeypatch.setattr(icims_monitor.requests, "get", fake_get)

    results = icims_monitor.get_icims_internships("Cook", "x.icims.com")

    assert pages == [0, 1, 2]
    assert len(results) == 3


def test_network_failure_returns_empty_list(monkeypatch):

    def boom(url, params, headers, timeout):
        raise ConnectionError("down")

    monkeypatch.setattr(icims_monitor.requests, "get", boom)

    assert icims_monitor.get_icims_internships("Cook", "x.icims.com") == []
