import sys
import os
from datetime import date

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from role_classifier import classify_role
from url_utils import clean_url
from internship_terms import is_internship_title



def get_greenhouse_internships(company_name, board_name):
    """
    Fetch internships from a company's Greenhouse job board.

    Example:
        get_greenhouse_internships("Hudl", "hudl")

    Identifies internships by title containing "intern" OR an
    Employment Type metadata field containing "intern" (catches roles
    like "Product Management Intern" that Greenhouse tags via metadata
    rather than the title alone).

    Returns a list of normalized internship dicts:
        company, title, location, role_type, application_url,
        external_job_id, source_platform, date_discovered
    """

    url = f"https://boards-api.greenhouse.io/v1/boards/{board_name}/jobs"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()

    except Exception as e:
        print(
            f"Error fetching jobs for "
            f"{company_name}: {e}"
        )
        return []

    jobs = data.get("jobs", [])

    internships = []
    seen_job_ids = set()

    for job in jobs:

        title = job.get("title", "") or ""

        employment_type = ""

        for meta in job.get("metadata") or []:

            name = (meta.get("name") or "").lower()

            if "employment type" in name:

                employment_type = str(meta.get("value") or "").lower()

        is_internship = (
            is_internship_title(title)
            or is_internship_title(employment_type)
        )

        if not is_internship:
            continue

        job_id = job.get("id")

        if job_id is not None:

            if job_id in seen_job_ids:
                continue

            seen_job_ids.add(job_id)

        internships.append({
            "company": company_name,
            "title": title,
            "location": job.get("location", {}).get(
                "name",
                "Unknown"
            ),
            "role_type": classify_role(title),
            "application_url": clean_url(job.get("absolute_url", "")),
            "external_job_id": str(job_id) if job_id is not None else None,
            "source_platform": "greenhouse",
            "date_discovered": date.today().isoformat(),
        })

    return internships


if __name__ == "__main__":

    hudl_jobs = get_greenhouse_internships(
        "Hudl",
        "hudl"
    )

    print("\nHudl Internships:\n")

    for job in hudl_jobs:
        print(job)
