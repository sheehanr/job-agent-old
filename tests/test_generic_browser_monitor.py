import sys
import os

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "src", "company_monitors")
)

import generic_browser_monitor as gbm  # noqa: E402


def test_real_posting_with_job_id_accepted():
    assert gbm._looks_like_real_posting(
        "Software Engineering Intern",
        "https://careers.example.com/job/23778683/software-eng-intern"
    ) is True


def test_generic_nav_label_rejected():
    assert gbm._looks_like_real_posting(
        "Internships",
        "https://careers.example.com/careers/career-areas/internships"
    ) is False


def test_link_without_job_id_in_url_rejected():
    # Text looks fine, but the URL doesn't point at a specific posting -
    # this is the McKesson "Internships & Early Careers" nav-link case.
    assert gbm._looks_like_real_posting(
        "Internships & Early Careers",
        "https://careers.example.com/en/early-talent"
    ) is False


def test_single_word_label_rejected():
    assert gbm._looks_like_real_posting(
        "Intern",
        "https://careers.example.com/job/123456"
    ) is False


def test_case_insensitive_generic_label():
    assert gbm._looks_like_real_posting(
        "SEARCH JOBS",
        "https://careers.example.com/job/123456"
    ) is False


def test_scrape_company_page_filters_and_dedupes(monkeypatch):

    class FakePage:

        def wait_for_timeout(self, ms):
            pass

    def fake_goto(page, url, **kwargs):
        pass

    def fake_search(page, term="intern"):
        return False

    def fake_extract(page):
        return [
            (
                "Software Engineering Intern",
                "https://careers.acme.com/job/1001/swe-intern"
            ),
            (
                # Duplicate of the one above.
                "Software Engineering Intern",
                "https://careers.acme.com/job/1001/swe-intern"
            ),
            (
                # Nav link, not a real posting.
                "Internships",
                "https://careers.acme.com/careers/internships"
            ),
            (
                # Not internship-related at all.
                "Senior Engineer",
                "https://careers.acme.com/job/1002/senior-engineer"
            ),
            (
                "Data Science Intern",
                "https://careers.acme.com/job/1003/data-science-intern"
            ),
        ]

    monkeypatch.setattr(gbm, "_goto_with_retries", fake_goto)
    monkeypatch.setattr(gbm, "_try_search_for_interns", fake_search)
    monkeypatch.setattr(gbm, "_extract_links", fake_extract)

    results = gbm._scrape_company_page(FakePage(), "Acme", "https://careers.acme.com")

    titles = {r["title"] for r in results}

    assert titles == {"Software Engineering Intern", "Data Science Intern"}
    assert len(results) == 2

    for r in results:
        assert r["source_platform"] == "custom-browser"
        assert r["location"] == "Unknown"
        assert r["external_job_id"] is None


def test_search_skipped_when_page_already_has_results(monkeypatch):
    """
    Regression test: found via Boeing's real career page, which is
    already a pre-filtered internship listing. The old code always ran
    the search-box flow regardless, which could navigate away and lose
    results that were already on the page. Search should only be
    attempted when the initial extraction finds nothing.
    """

    class FakePage:

        def wait_for_timeout(self, ms):
            pass

    def fake_goto(page, url, **kwargs):
        pass

    def fake_search(page, term="intern"):
        raise AssertionError(
            "search should not be attempted when the page already has "
            "results"
        )

    def fake_extract(page):
        return [
            (
                "Software Engineering Intern",
                "https://careers.acme.com/job/1001/swe-intern"
            ),
        ]

    monkeypatch.setattr(gbm, "_goto_with_retries", fake_goto)
    monkeypatch.setattr(gbm, "_try_search_for_interns", fake_search)
    monkeypatch.setattr(gbm, "_extract_links", fake_extract)

    results = gbm._scrape_company_page(
        FakePage(), "Acme", "https://careers.acme.com"
    )

    assert len(results) == 1


def test_search_attempted_when_no_initial_results(monkeypatch):

    class FakePage:

        def wait_for_timeout(self, ms):
            pass

    def fake_goto(page, url, **kwargs):
        pass

    calls = {"search_called": False, "extract_calls": 0, "terms": []}

    def fake_search(page, term="intern"):
        calls["search_called"] = True
        calls["terms"].append(term)
        return True

    def fake_extract(page):
        calls["extract_calls"] += 1
        if not calls["search_called"]:
            return []
        links = [
            (
                "Data Science Intern",
                "https://careers.acme.com/job/1003/data-science-intern"
            ),
        ]
        if calls["terms"][-1] == "co-op":
            links.append((
                "Software Engineer Co-op",
                "https://careers.acme.com/job/1004/swe-co-op"
            ))
        return links

    monkeypatch.setattr(gbm, "_goto_with_retries", fake_goto)
    monkeypatch.setattr(gbm, "_try_search_for_interns", fake_search)
    monkeypatch.setattr(gbm, "_extract_links", fake_extract)

    results = gbm._scrape_company_page(
        FakePage(), "Acme", "https://careers.acme.com"
    )

    assert calls["search_called"] is True
    assert calls["terms"] == list(gbm.BROWSER_SEARCH_TERMS)
    # The intern posting shows up in both searches but is kept once.
    assert [r["title"] for r in results] == [
        "Data Science Intern", "Software Engineer Co-op"
    ]


def test_slow_page_rechecked_before_searching(monkeypatch):
    """Jobs that render late (e.g. in an iframe) are found by the second
    look, without running the search flow."""

    class FakePage:

        def wait_for_timeout(self, ms):
            pass

    calls = {"search_called": False, "extract_calls": 0}

    def fake_search(page):
        calls["search_called"] = True
        return True

    def fake_extract(page):
        calls["extract_calls"] += 1
        if calls["extract_calls"] == 1:
            return []
        return [(
            "Software Internship 2027",
            "https://acme.submit4jobs.com/#/jobDescription/370159/job"
        )]

    monkeypatch.setattr(gbm, "_goto_with_retries", lambda *a, **k: None)
    monkeypatch.setattr(gbm, "_try_search_for_interns", fake_search)
    monkeypatch.setattr(gbm, "_extract_links", fake_extract)

    results = gbm._scrape_company_page(
        FakePage(), "Acme", "https://acme.submit4jobs.com/"
    )

    assert calls["search_called"] is False
    assert [r["title"] for r in results] == ["Software Internship 2027"]
