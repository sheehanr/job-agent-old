import sys
import os
from datetime import date

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from role_classifier import classify_role
from url_utils import clean_url
from internship_terms import INTERN_SEARCH_TERMS, is_internship_title


def get_oracle_orc_internships(
    company_name,
    career_site_host,
    tenant_host,
    site_number,
    site_name
):
    """
    Fetch internships from a company's Oracle Recruiting Cloud (Fusion
    HCM) career site.

    Example:
        get_oracle_orc_internships(
            "Honeywell",
            "careers.honeywell.com",
            "ibqbjb.fa.ocs.oraclecloud.com",
            "CX_1",
            "Honeywell"
        )

    career_site_host is the public-facing careers page; tenant_host is
    the underlying Oracle Fusion tenant that actually serves the REST
    API; site_number identifies the specific career site within that
    tenant for API calls (e.g. "CX_1"); site_name is the human-readable
    site path segment used in public job URLs (e.g. "Honeywell" in
    careers.honeywell.com/en/sites/Honeywell/job/12345) - these are two
    different identifiers for the same site.

    Oracle's keyword search is a broad text match (it also matches
    "Internal Auditor"), so results are re-filtered with a word-boundary
    regex.
    """

    url = (
        f"https://{tenant_host}/hcmRestApi/resources/latest/"
        f"recruitingCEJobRequisitions"
    )

    internships = []
    seen_job_ids = set()

    limit = 25
    max_pages = 10  # safety cap

    # One search per term (intern, co-op, coop, ...); the seen-id set
    # dedupes postings that match more than one.
    for term in INTERN_SEARCH_TERMS:

        offset = 0

        for _ in range(max_pages):

            finder = (
                f"findReqs;siteNumber={site_number},"
                f"keyword={term},limit={limit},offset={offset}"
            )

            params = {
                "onlyData": "true",
                "expand": "requisitionList.secondaryLocations",
                "finder": finder,
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

            items = data.get("items") or []

            if not items:
                break

            item = items[0]
            requisitions = item.get("requisitionList") or []

            if not requisitions:
                break

            for req in requisitions:

                title = req.get("Title", "") or ""

                if not is_internship_title(title):
                    continue

                job_id = req.get("Id")

                if job_id is not None:

                    if job_id in seen_job_ids:
                        continue

                    seen_job_ids.add(job_id)

                application_url = clean_url(
                    f"https://{career_site_host}/en/sites/"
                    f"{site_name}/job/{job_id}"
                )

                internships.append({
                    "company": company_name,
                    "title": title,
                    "location": req.get("PrimaryLocation", "Unknown"),
                    "role_type": classify_role(title),
                    "application_url": application_url,
                    "external_job_id": (
                        str(job_id) if job_id is not None else None
                    ),
                    "source_platform": "oracle_orc",
                    "date_discovered": date.today().isoformat(),
                })

            total_count = item.get("TotalJobsCount", 0)

            offset += limit

            if offset >= total_count:
                break

    return internships


if __name__ == "__main__":

    jobs = get_oracle_orc_internships(
        "Honeywell",
        "careers.honeywell.com",
        "ibqbjb.fa.ocs.oraclecloud.com",
        "CX_1",
        "Honeywell"
    )

    print(f"\n{len(jobs)} Honeywell internships:\n")

    for job in jobs:
        print(job)
