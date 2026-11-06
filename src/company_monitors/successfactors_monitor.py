import sys
import os
import re
import html
from datetime import date

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from role_classifier import classify_role
from url_utils import clean_url
from internship_terms import INTERN_SEARCH_TERMS, is_internship_title

# One search-result row. Sites use one of two layouts: a table
# (<tr class="data-row">, e.g. HII, Boston Scientific) or tiles
# (<li class="job-tile">, e.g. Arthrex). Each row renders its title link
# twice (desktop and mobile layouts), hence the dedup on href below.
_ROW_RE = re.compile(
    r'<tr class="data-row".*?</tr>'
    r'|<li class="job-tile.*?(?=<li class="job-tile|</ul>)',
    re.IGNORECASE | re.DOTALL
)
# Attribute order differs between layouts, so find the jobTitle-link
# anchor first and read its href separately.
_TITLE_LINK_RE = re.compile(
    r'<a\b([^>]*\bclass="jobTitle-link[^"]*"[^>]*)>\s*([^<]+?)\s*</a>',
    re.IGNORECASE
)
_HREF_RE = re.compile(r'\bhref="([^"]*/job/[^"]+)"', re.IGNORECASE)
_LOCATION_RE = re.compile(
    r'<span class="jobLocation">\s*([^<]+?)\s*</span>'
    r'|-section-location-value">\s*([^<]+?)\s*</div>',
    re.IGNORECASE
)
_JOB_ID_RE = re.compile(r"/(\d+)/?$")


def get_successfactors_internships(company_name, host, max_pages=8):
    """
    Fetch internships from a SAP SuccessFactors "Career Site Builder"
    site (the ones with /search/?q=... and /job/<slug>/<id>/ URLs), by
    reading its server-rendered search results page.

    Example:
        get_successfactors_internships(
            "Huntington Ingalls Industries", "careers.huntingtoningalls.com"
        )
    """

    page_size = 25  # fixed by the site

    internships = []
    seen_hrefs = set()

    # One search per term (intern, co-op, coop, ...); the seen-id set
    # dedupes postings that match more than one.
    for term in INTERN_SEARCH_TERMS:

        for page in range(max_pages):

            try:
                response = requests.get(
                    f"https://{host}/search/",
                    params={"q": term, "startrow": page * page_size},
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=15
                )
                response.raise_for_status()

            except Exception as e:
                print(f"Error fetching jobs for {company_name}: {e}")
                break

            rows = _ROW_RE.findall(response.text)

            for row in rows:

                link = _TITLE_LINK_RE.search(row)

                if not link:
                    continue

                href = _HREF_RE.search(link.group(1))

                if not href:
                    continue

                href = href.group(1)
                title = html.unescape(link.group(2)).strip()

                if href in seen_hrefs or not is_internship_title(title):
                    continue

                seen_hrefs.add(href)

                location = _LOCATION_RE.search(row)
                job_id = _JOB_ID_RE.search(href)

                internships.append({
                    "company": company_name,
                    "title": title,
                    "location": (
                        html.unescape(location.group(1) or location.group(2))
                        if location else "Unknown"
                    ),
                    "role_type": classify_role(title),
                    "application_url": clean_url(f"https://{host}{href}"),
                    "external_job_id": job_id.group(1) if job_id else href,
                    "source_platform": "successfactors",
                    "date_discovered": date.today().isoformat(),
                })

            if len(rows) < page_size:
                break

    return internships


if __name__ == "__main__":

    jobs = get_successfactors_internships(
        "Huntington Ingalls Industries", "careers.huntingtoningalls.com"
    )

    print(f"\n{len(jobs)} HII internships:\n")

    for job in jobs:
        print(job)
