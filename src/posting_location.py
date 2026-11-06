"""
Best-effort lookup of a posting's location from the posting itself, for
postings whose listing gave no usable location (the generic browser
scraper always reports "Unknown"; Workday often says "4 Locations" or a
bare site name like "TARRYTOWN").

Only called for NEW postings that would otherwise alert, so it costs at
most one extra request per new posting.
"""

import json
import re
from urllib.parse import urlparse

import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


def _as_list(value):

    if value is None:
        return []

    return value if isinstance(value, list) else [value]


def _name(value):

    if isinstance(value, dict):
        return value.get("name") or value.get("@id") or ""

    return str(value or "")


def _iter_job_postings(node):

    if isinstance(node, list):
        for item in node:
            yield from _iter_job_postings(item)

    elif isinstance(node, dict):

        types = _as_list(node.get("@type"))

        if "JobPosting" in types:
            yield node

        for key in ("@graph", "itemListElement", "item"):
            if key in node:
                yield from _iter_job_postings(node[key])


def location_from_html(html):
    """
    Pull a location out of schema.org JobPosting JSON-LD, which most ATS
    posting pages embed for Google Jobs. Returns "" if there's none.
    """

    parts = []

    for raw in _JSON_LD_RE.findall(html or ""):

        try:
            data = json.loads(raw.strip())

        except ValueError:
            continue

        for posting in _iter_job_postings(data):

            for place in _as_list(posting.get("jobLocation")):

                address = (place or {}).get("address") or {}

                if isinstance(address, str):
                    parts.append(address)
                    continue

                fields = [
                    _name(address.get("addressLocality")),
                    _name(address.get("addressRegion")),
                    _name(address.get("addressCountry")),
                ]

                text = ", ".join(f for f in fields if f)

                if text:
                    parts.append(text)

            # Remote postings: jobLocationType TELECOMMUTE plus the
            # countries applicants must live in.
            for requirement in _as_list(
                posting.get("applicantLocationRequirements")
            ):
                name = _name(requirement)

                if name:
                    parts.append(f"Remote - {name}")

    return "; ".join(dict.fromkeys(parts))


def location_via_requests(url, timeout=15):

    try:
        response = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=timeout
        )
        response.raise_for_status()

    except Exception as e:
        print(f"Couldn't fetch posting page {url}: {e}")
        return ""

    return location_from_html(response.text)


def location_via_browser(url, browser):
    """Same JSON-LD lookup, but rendering the page in the shared headless
    browser - most custom career sites block or JS-render for plain
    requests."""

    page = browser.new_page(user_agent=USER_AGENT)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(1500)

        return location_from_html(page.content())

    except Exception as e:
        print(f"Couldn't load posting page {url}: {e}")
        return ""

    finally:
        page.close()


def workday_location(application_url, tenant, timeout=15):
    """
    Workday's public job-detail endpoint has the posting's country even
    when the listing only says "4 Locations" or a bare site name.
    application_url looks like https://<host>/en-US/<site>/job/<...>.
    """

    parsed = urlparse(application_url)

    segments = [s for s in parsed.path.split("/") if s]

    # Drop the optional locale segment ("en-US").
    if segments and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", segments[0]):
        segments = segments[1:]

    if len(segments) < 2:
        return ""

    site, job_path = segments[0], "/".join(segments[1:])

    url = (
        f"https://{parsed.netloc}/wday/cxs/{tenant}/{site}/{job_path}"
    )

    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=timeout,
        )
        response.raise_for_status()

        info = response.json().get("jobPostingInfo") or {}

    except Exception as e:
        print(f"Couldn't fetch Workday posting {url}: {e}")
        return ""

    primary = info.get("location") or ""
    country = (info.get("country") or {}).get("descriptor") or ""

    parts = [", ".join(p for p in (primary, country) if p)]
    parts.extend(info.get("additionalLocations") or [])

    return "; ".join(p for p in parts if p)
