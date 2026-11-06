import sys
import os
from datetime import date

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from role_classifier import classify_role
from url_utils import clean_url
from internship_terms import INTERN_SEARCH_TERMS, is_internship_title


def get_eightfold_internships(company_name, api_host, company_domain):
    """
    Fetch internships from a company's Eightfold.ai-powered career site
    (the "careers.<company>.com" sites with a public /api/pcsx/search
    endpoint).

    Example:
        get_eightfold_internships("John Deere", "careers.deere.com", "johndeere.com")

    Eightfold's search is a plain keyword search, not a structured filter,
    so the server-side "intern" query is a broad net (it also matches
    "Internal Auditor") - results are re-filtered here with a
    word-boundary regex so "Internal"/"International" etc. don't leak
    through as false positives.
    """

    url = f"https://{api_host}/api/pcsx/search"

    internships = []
    seen_job_ids = set()

    page_size = 10
    max_pages = 30  # safety cap - Eightfold has no larger page-size param

    # One search per term (intern, co-op, coop, ...); the seen-id set
    # dedupes postings that match more than one.
    for term in INTERN_SEARCH_TERMS:

        start = 0

        while start < page_size * max_pages:

            params = {
                "domain": company_domain,
                "query": term,
                "location": "",
                "start": start,
            }

            try:
                response = requests.get(
                    url,
                    params=params,
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=10
                )
                response.raise_for_status()

                data = response.json()

            except Exception as e:
                print(
                    f"Error fetching jobs for "
                    f"{company_name}: {e}"
                )
                break

            positions = (data.get("data") or {}).get("positions") or []

            if not positions:
                break

            for position in positions:

                title = position.get("name", "") or ""

                if not is_internship_title(title):
                    continue

                job_id = position.get("id")

                if job_id is not None:

                    if job_id in seen_job_ids:
                        continue

                    seen_job_ids.add(job_id)

                locations = position.get("locations") or []
                location = locations[0] if locations else "Unknown"

                position_url = position.get("positionUrl", "") or ""

                application_url = clean_url(
                    f"https://{api_host}{position_url}"
                    if position_url.startswith("/")
                    else position_url
                )

                internships.append({
                    "company": company_name,
                    "title": title,
                    "location": location,
                    "role_type": classify_role(title),
                    "application_url": application_url,
                    "external_job_id": (
                        str(job_id) if job_id is not None else None
                    ),
                    "source_platform": "eightfold",
                    "date_discovered": date.today().isoformat(),
                })

            total_count = (data.get("data") or {}).get("count", 0)

            start += page_size

            if start >= total_count:
                break

    return internships


if __name__ == "__main__":

    jobs = get_eightfold_internships(
        "John Deere", "careers.deere.com", "johndeere.com"
    )

    print(f"\n{len(jobs)} John Deere internships:\n")

    for job in jobs:
        print(job)
