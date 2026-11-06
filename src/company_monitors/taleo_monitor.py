import sys
import os
import json
from datetime import date

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from role_classifier import classify_role
from internship_terms import INTERN_SEARCH_TERMS, is_internship_title


def get_taleo_internships(
    company_name, host, career_section, portal_id, max_pages=10
):
    """
    Fetch internships from an Oracle Taleo career section
    ("<host>/careersection/<career_section>/jobsearch.ftl") through the
    JSON search endpoint its page calls. portal_id is the "portal=" value
    on that request (visible in the browser's network tab).

    Example:
        get_taleo_internships(
            "Textron Systems", "textron.taleo.net", "textron", "8140753014"
        )
    """

    url = (
        f"https://{host}/careersection/rest/jobboard/searchjobs"
        f"?lang=en&portal={portal_id}"
    )

    internships = []
    seen_job_ids = set()

    # One search per term (intern, co-op, coop, ...); the seen-id set
    # dedupes postings that match more than one.
    for term in INTERN_SEARCH_TERMS:

        for page_no in range(1, max_pages + 1):

            body = {
                "multilineEnabled": False,
                # 3 = posting date, newest first
                "sortingSelection": {
                    "sortBySelectionParam": "3",
                    "ascendingSortingOrder": "false",
                },
                "fieldData": {
                    "fields": {"KEYWORD": term, "LOCATION": ""},
                    "valid": True,
                },
                "filterSelectionParam": {"searchFilterSelections": []},
                "advancedSearchFiltersSelectionParam": {
                    "searchFilterSelections": []
                },
                "pageNo": page_no,
            }

            try:
                response = requests.post(
                    url,
                    json=body,
                    # Taleo 500s without the timezone headers its page sends.
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "tz": "GMT-05:00",
                        "tzname": "America/New_York",
                    },
                    timeout=15
                )
                response.raise_for_status()

                data = response.json()

            except Exception as e:
                print(f"Error fetching jobs for {company_name}: {e}")
                break

            requisitions = data.get("requisitionList") or []

            for req in requisitions:

                # column = [title, JSON list of locations, posting date]
                columns = req.get("column") or []

                title = columns[0] if columns else ""

                job_number = req.get("contestNo") or req.get("jobId")

                if not is_internship_title(title):
                    continue

                if job_number in seen_job_ids:
                    continue

                seen_job_ids.add(job_number)

                internships.append({
                    "company": company_name,
                    "title": title,
                    "location": _first_location(columns),
                    "role_type": classify_role(title),
                    "application_url": (
                        f"https://{host}/careersection/{career_section}/"
                        f"jobdetail.ftl?job={job_number}&lang=en"
                    ),
                    "external_job_id": str(job_number),
                    "source_platform": "taleo",
                    "date_discovered": date.today().isoformat(),
                })

            paging = data.get("pagingData") or {}

            if page_no * (paging.get("pageSize") or 25) >= (
                paging.get("totalCount") or 0
            ):
                break

    return internships


def _first_location(columns):

    if len(columns) < 2:
        return "Unknown"

    try:
        locations = json.loads(columns[1])

    except (TypeError, ValueError):
        return str(columns[1]) or "Unknown"

    return locations[0] if locations else "Unknown"


if __name__ == "__main__":

    jobs = get_taleo_internships(
        "Textron Systems", "textron.taleo.net", "textron", "8140753014"
    )

    print(f"\n{len(jobs)} Textron internships:\n")

    for job in jobs:
        print(job)
