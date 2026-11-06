import sys
import os
import re
import html
from datetime import date

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from role_classifier import classify_role
from internship_terms import INTERN_SEARCH_TERMS, is_internship_title

_CARD_RE = re.compile(
    r'<li class="iCIMS_JobCardItem".*?</li>\s*(?=<li class="iCIMS_JobCardItem"|</ul>)',
    re.IGNORECASE | re.DOTALL
)
_LINK_RE = re.compile(
    r'<a href="([^"]*/jobs/(\d+)/[^"]*)"[^>]*class="iCIMS_Anchor"',
    re.IGNORECASE
)
_TITLE_RE = re.compile(r"<h3[^>]*>\s*(.*?)\s*</h3>", re.IGNORECASE | re.DOTALL)
_LOCATION_RE = re.compile(
    r"Job Locations</span>\s*</dt>\s*<dd[^>]*>\s*<span[^>]*>\s*([^<]+?)\s*</span>",
    re.IGNORECASE
)
_PAGE_COUNT_RE = re.compile(r"Page\s+\d+\s+of\s+(\d+)", re.IGNORECASE)


def get_icims_internships(company_name, host, max_pages=10):
    """
    Fetch internships from an iCIMS career portal ("<portal>.icims.com")
    by reading its server-rendered search results (the in_iframe=1 page
    the company's careers site embeds).

    Example:
        get_icims_internships("Cook Medical", "americas-cookmedical.icims.com")

    Plain HTTP requests work here; iCIMS shows a bot check to headless
    browsers, which is why this isn't left to the generic browser scraper.
    Runs one search per term in INTERN_SEARCH_TERMS and dedupes by job id.
    """

    internships = []
    seen_ids = set()

    for term in INTERN_SEARCH_TERMS:

        for page in range(max_pages):

            try:
                response = requests.get(
                    f"https://{host}/jobs/search",
                    params={
                        "ss": 1,
                        "searchKeyword": term,
                        "in_iframe": 1,
                        "pr": page,
                    },
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=20
                )
                response.raise_for_status()

            except Exception as e:
                print(f"Error fetching jobs for {company_name} ({term!r}): {e}")
                break

            text = response.text
            cards = _CARD_RE.findall(text)

            for card in cards:

                link = _LINK_RE.search(card)
                title = _TITLE_RE.search(card)

                if not link or not title:
                    continue

                job_id = link.group(2)
                title = html.unescape(re.sub(r"\s+", " ", title.group(1))).strip()

                if job_id in seen_ids or not is_internship_title(title):
                    continue

                seen_ids.add(job_id)

                location = _LOCATION_RE.search(card)

                internships.append({
                    "company": company_name,
                    "title": title,
                    "location": (
                        html.unescape(location.group(1)) if location
                        else "Unknown"
                    ),
                    "role_type": classify_role(title),
                    # Drop in_iframe=1 so the link opens the full page.
                    "application_url": html.unescape(link.group(1)).split("?")[0],
                    "external_job_id": job_id,
                    "source_platform": "icims",
                    "date_discovered": date.today().isoformat(),
                })

            page_count = _PAGE_COUNT_RE.search(text)

            if not cards or not page_count or page + 1 >= int(page_count.group(1)):
                break

    return internships


if __name__ == "__main__":

    jobs = get_icims_internships(
        "Cook Medical", "americas-cookmedical.icims.com"
    )

    print(f"\n{len(jobs)} Cook Medical internships:\n")

    for job in jobs:
        print(job)
