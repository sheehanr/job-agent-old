import sys
import os
import re
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from role_classifier import classify_role
from internship_terms import is_internship_title


_REQUISITIONS_API = "job-requisitions/apply-custom-filters"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def get_adp_internships(company_name, site_name, client_id, browser):
    """
    Fetch internships from an ADP Workforce Now career site
    ("myjobs.adp.com/<site_name>/cx/job-listing?c=<client_id>").

    ADP's job API needs a session token the page mints in JavaScript, so
    this loads the page in the shared headless browser and reads the API
    response the page itself requests - rewriting its page size from 10
    to 500 on the way out so one response holds every open job.

    Example:
        get_adp_internships(
            "Mercury Systems", "mercurysystemscareers", "1162151", browser
        )
    """

    page_url = (
        f"https://myjobs.adp.com/{site_name}/cx/job-listing"
        f"?c={client_id}&d=ExternalCareerSite"
    )

    page = browser.new_page(user_agent=USER_AGENT)

    def widen_page_size(route):
        route.continue_(url=route.request.url.replace("$top=10", "$top=500"))

    page.route(re.compile(re.escape(_REQUISITIONS_API)), widen_page_size)

    try:
        with page.expect_response(
            lambda r: _REQUISITIONS_API in r.url, timeout=30000
        ) as response_info:
            page.goto(page_url, wait_until="domcontentloaded", timeout=30000)

        requisitions = response_info.value.json().get("jobRequisitions") or []

    except Exception as e:
        print(f"Error fetching jobs for {company_name}: {e}")
        return []

    finally:
        page.close()

    internships = []

    for req in requisitions:

        title = req.get("publishedJobTitle") or req.get("jobTitle") or ""

        if not is_internship_title(title):
            continue

        req_id = req.get("reqId") or req.get("clientRequisitionID")

        internships.append({
            "company": company_name,
            "title": title,
            "location": _first_location(req),
            "role_type": classify_role(title),
            "application_url": (
                f"https://myjobs.adp.com/{site_name}/cx/job-details"
                f"?c={client_id}&d=ExternalCareerSite&reqId={req_id}"
            ),
            "external_job_id": str(req_id) if req_id else None,
            "source_platform": "adp",
            "date_discovered": date.today().isoformat(),
        })

    return internships


def _first_location(req):

    for loc in req.get("requisitionLocations") or []:

        address = loc.get("address") or {}

        city = address.get("cityName")
        state = (address.get("countrySubdivisionLevel1") or {}).get("codeValue")

        if city:
            return f"{city}, {state}" if state else city

    return "Unknown"


if __name__ == "__main__":

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=True)

        jobs = get_adp_internships(
            "Mercury Systems", "mercurysystemscareers", "1162151", browser
        )

        browser.close()

    print(f"\n{len(jobs)} Mercury Systems internships:\n")

    for job in jobs:
        print(job)
