import sys
import os
import re
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from role_classifier import classify_role
from url_utils import clean_url
from internship_terms import is_internship_title

# Typed into the site's own search box when the page doesn't already list
# postings. A subset of INTERN_SEARCH_TERMS: each browser search costs
# several seconds, and site search boxes generally treat "co-op"/"coop"/
# "co op" alike.
BROWSER_SEARCH_TERMS = ("intern", "co-op")

# Generic nav/category link text that isn't an actual job posting -
# e.g. Target's and Chipotle's "Internships" nav link to a category page,
# not a specific opening.
_GENERIC_LABELS = {
    "internships", "internship", "interns", "intern",
    "search jobs", "search internships", "view all jobs",
    "view internships", "view all internships",
    "student programs", "student program",
    "early careers", "early career", "early career program",
    "internship program", "internship programs",
    "student internships", "internship opportunities",
    "browse internships", "current internships",
    "co-op", "co-ops", "coop", "co-op program", "co-op programs",
    "internships & co-ops", "internships and co-ops",
    "co-ops & internships", "co-ops and internships",
}

_SEARCH_BOX_SELECTORS = [
    'input[type="search"]',
    'input[placeholder*="job" i]',
    'input[placeholder*="keyword" i]',
    'input[placeholder*="search" i]',
    'input[aria-label*="job" i]',
    'input[aria-label*="search" i]',
    'input[name*="job" i]',
    'input[name*="keyword" i]',
    'input[name*="search" i]',
]

_SUBMIT_BUTTON_SELECTORS = [
    'button[type="submit"]',
    'button[aria-label*="search" i]',
    'button:has-text("Search")',
    'button:has-text("Find")',
    'input[type="submit"]',
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


# Real job-posting URLs almost universally contain a long numeric
# requisition/job id somewhere in the path (e.g. .../job/23778683/...,
# .../communications-intern/733/100099794896) - nav/category links to a
# listing or landing page typically don't have one.
_JOB_ID_IN_URL_RE = re.compile(r"\d{4,}")


def _looks_like_real_posting(text, href):

    normalized = re.sub(r"\s+", " ", text).strip().lower()

    if normalized in _GENERIC_LABELS:
        return False

    if len(normalized.split()) < 2:
        return False

    # A real posting link almost always points at a specific job/req id,
    # not a category or landing page - filters out nav links whose text
    # happens to contain "intern" but which just link to a listing page.
    if not _JOB_ID_IN_URL_RE.search(href):
        return False

    return True


def _goto_with_retries(page, url, max_retries=1, timeout_ms=20000):

    last_error = None

    for attempt in range(max_retries + 1):

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            return

        except Exception as e:
            last_error = e

            if attempt < max_retries:
                page.wait_for_timeout(1500)

    raise last_error


def _try_search_for_interns(page, term="intern"):
    """
    Best-effort: if the loaded page has a job-search box (the career_url
    is often a marketing landing page, not the job listing itself), type
    `term` and submit. Returns True if a search was attempted.
    """

    for selector in _SEARCH_BOX_SELECTORS:

        try:
            box = page.locator(selector).first

            if box.count() == 0:
                continue

            box.fill(term, timeout=5000)
            box.press("Enter")
            page.wait_for_timeout(2000)

            _try_click_submit_button(page)

            page.wait_for_timeout(2000)

            return True

        except Exception:
            continue

    return False


def _try_click_submit_button(page):
    """Enter alone doesn't submit every JS-driven search form - try an
    explicit submit/search button too, on a best-effort basis."""

    for selector in _SUBMIT_BUTTON_SELECTORS:

        try:
            button = page.locator(selector).first

            if button.count() == 0:
                continue

            button.click(timeout=3000)

            return True

        except Exception:
            continue

    return False


def _extract_links(page):
    """Links from the page and every iframe in it - some career pages
    (e.g. Kratos's submit4jobs listing) render their jobs in an iframe."""

    links = []

    for frame in page.frames:

        try:
            raw = frame.eval_on_selector_all(
                "a",
                "els => els.map(e => ({text: e.textContent.trim(), "
                "href: e.href})).filter(l => l.text.length > 0 && l.href)"
            )

        except Exception:
            # Frames can detach mid-read on pages that keep navigating.
            continue

        links.extend((item["text"], item["href"]) for item in raw)

    return links


def _internships_from_links(links, company_name):

    internships = []
    seen = set()

    for text, href in links:

        if not is_internship_title(text):
            continue

        if not _looks_like_real_posting(text, href):
            continue

        application_url = clean_url(href)

        key = (text.strip().lower(), application_url)

        if key in seen:
            continue

        seen.add(key)

        internships.append({
            "company": company_name,
            "title": re.sub(r"\s+", " ", text).strip(),
            "location": "Unknown",
            "role_type": classify_role(text),
            "application_url": application_url,
            "external_job_id": None,
            "source_platform": "custom-browser",
            "date_discovered": date.today().isoformat(),
        })

    return internships


def _scrape_company_page(page, company_name, career_url):

    _goto_with_retries(page, career_url)
    page.wait_for_timeout(3000)

    # Try the page as-loaded first - some career_urls are already a
    # pre-filtered internship listing (e.g. Boeing's /category/
    # internship-jobs/... page), and running the search-box flow on a
    # page like that can navigate away and lose results that were
    # already there, rather than add to them.
    internships = _internships_from_links(_extract_links(page), company_name)

    if internships:
        return internships

    # Slow job widgets (e.g. iframe-embedded listings) often haven't
    # rendered after 3s - give the page one more look before searching.
    page.wait_for_timeout(5000)

    internships = _internships_from_links(_extract_links(page), company_name)

    if internships:
        return internships

    seen_urls = set()

    for term in BROWSER_SEARCH_TERMS:

        if not _try_search_for_interns(page, term):
            break  # no search box on this page at all

        for internship in _internships_from_links(
            _extract_links(page), company_name
        ):
            if internship["application_url"] not in seen_urls:
                seen_urls.add(internship["application_url"])
                internships.append(internship)

    return internships


def get_browser_scraped_internships(company_name, career_url, browser=None):
    """
    Best-effort internship discovery for a career page with no known
    structured API, using a real (headless) browser so JS-rendered SPAs
    render properly - a plain HTTP GET can't see through most of these.

    Loads career_url, attempts a job-search box submission (many career
    pages are landing pages, not the listing itself), then extracts links
    whose text contains "intern"/"internship"/"co-op" as a whole word and
    isn't a generic nav label like "Internships" or "Search Jobs".

    Location is always "Unknown" here - generic link scraping has no
    reliable way to extract a location field. For new postings that would
    alert, the monitor service then opens the posting page and reads its
    JSON-LD location (see posting_location.py).
    application_url quality varies by site; some may point to a search
    results page rather than the specific posting if the link itself
    isn't a direct job-detail URL.

    Pass an existing Playwright `browser` object to reuse across many
    companies in one process (much faster than launching a new browser
    per company); omit it to launch and close one just for this call.
    """

    from playwright.sync_api import sync_playwright

    if browser is not None:

        page = browser.new_page(user_agent=USER_AGENT)

        try:
            return _scrape_company_page(page, company_name, career_url)

        except Exception as e:
            print(f"Error scraping {company_name}: {e}")
            return []

        finally:
            page.close()

    try:
        with sync_playwright() as p:

            launched = p.chromium.launch(
                headless=True, args=["--disable-http2"]
            )

            try:
                page = launched.new_page(user_agent=USER_AGENT)

                return _scrape_company_page(page, company_name, career_url)

            finally:
                launched.close()

    except Exception as e:
        print(f"Error scraping {company_name}: {e}")
        return []


if __name__ == "__main__":

    jobs = get_browser_scraped_internships(
        "Honeywell", "https://careers.honeywell.com/en/sites/Honeywell"
    )

    print(f"\n{len(jobs)} internships found:\n")

    for job in jobs:
        print(job)
