import sys
import os
from datetime import date

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from role_classifier import classify_role
from url_utils import clean_url
from internship_terms import is_internship_title
from location_filter import country_name


def _location(posting):

    categories = posting.get("categories") or {}

    places = categories.get("allLocations") or (
        [categories["location"]] if categories.get("location") else []
    )

    location = "; ".join(places)

    # Lever's "country" is an ISO code for the primary location; spell it
    # out so the US filter can't confuse e.g. Canada's "CA" with California.
    country = posting.get("country")

    if country and len(places) <= 1:
        location = ", ".join(p for p in (location, country_name(country)) if p)

    return location or "Unknown"


def get_lever_internships(company_name, site):
    """
    Fetch internships from a Lever job board through Lever's public
    postings API (https://api.lever.co/v0/postings/<site>), which returns
    every open posting in one response.

    Example:
        get_lever_internships("Veeva Systems", "veeva")

    A posting counts if its title, or its "commitment" (Lever's
    employment-type field, e.g. "Internship"), matches the shared
    intern/co-op pattern.
    """

    url = f"https://api.lever.co/v0/postings/{site}"

    try:
        response = requests.get(
            url,
            params={"mode": "json"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20
        )
        response.raise_for_status()

        postings = response.json()

    except Exception as e:
        print(f"Error fetching jobs for {company_name}: {e}")
        return []

    internships = []

    for posting in postings or []:

        title = posting.get("text", "") or ""
        commitment = (posting.get("categories") or {}).get("commitment") or ""

        if not (is_internship_title(title) or is_internship_title(commitment)):
            continue

        internships.append({
            "company": company_name,
            "title": title,
            "location": _location(posting),
            "role_type": classify_role(title),
            "application_url": clean_url(
                posting.get("hostedUrl") or posting.get("applyUrl") or ""
            ),
            "external_job_id": posting.get("id"),
            "source_platform": "lever",
            "date_discovered": date.today().isoformat(),
        })

    return internships


if __name__ == "__main__":

    jobs = get_lever_internships("Veeva Systems", "veeva")

    print(f"\n{len(jobs)} Veeva internships:\n")

    for job in jobs:
        print(job)
