import argparse

from company_registry_loader import load_enabled_companies
from company_monitors.greenhouse_monitor import get_greenhouse_internships
from company_monitors.jibe_monitor import get_jibe_internships
from company_monitors.eightfold_monitor import get_eightfold_internships
from company_monitors.oracle_orc_monitor import get_oracle_orc_internships
from company_monitors.workday_monitor import get_workday_internships
from company_monitors.successfactors_monitor import get_successfactors_internships
from company_monitors.adp_monitor import get_adp_internships
from company_monitors.taleo_monitor import get_taleo_internships
from company_monitors.lever_monitor import get_lever_internships
from company_monitors.icims_monitor import get_icims_internships
from company_monitors.generic_browser_monitor import get_browser_scraped_internships
from database_setup import create_database
from database_monitor import (
    upsert_internship,
    create_alert_for_new_internship,
    update_internship_location,
)
from database_alerts import get_unsent_alerts, mark_alerts_sent
from role_classifier import is_target_role, is_ineligible
from location_filter import (
    classify_location,
    UNKNOWN,
    NON_US,
    UNKNOWN_LOCATION_LABEL,
)
import posting_location
from sms_alerts import send_alert


def _eightfold_adapter(company):

    api_host, company_domain = company["platform_identifier"].split("|")

    return get_eightfold_internships(
        company["company"], api_host, company_domain
    )


def _oracle_orc_adapter(company):

    career_site_host, tenant_host, site_number, site_name = (
        company["platform_identifier"].split("|")
    )

    return get_oracle_orc_internships(
        company["company"],
        career_site_host,
        tenant_host,
        site_number,
        site_name
    )


def _workday_adapter(company):

    host, tenant, site = company["platform_identifier"].split("|")

    return get_workday_internships(company["company"], host, tenant, site)


def _taleo_adapter(company):

    host, career_section, portal_id = (
        company["platform_identifier"].split("|")
    )

    return get_taleo_internships(
        company["company"], host, career_section, portal_id
    )


def _make_adp_adapter(browser):

    def adapter(company):

        site_name, client_id = company["platform_identifier"].split("|")

        return get_adp_internships(
            company["company"], site_name, client_id, browser
        )

    return adapter


# Platforms that need the shared headless browser.
BROWSER_PLATFORMS = {"custom", "adp"}


def _make_custom_adapter(browser):
    """
    "custom" platform companies have no known structured API. Falls back
    to a real (shared, headless) browser scraping career_url directly -
    best-effort, since these sites vary wildly and some actively resist
    automated browsing. Companies with a verified platform (greenhouse,
    jibe, eightfold, oracle_orc) always use their dedicated adapter
    instead, since it's far more accurate.
    """

    def adapter(company):

        return get_browser_scraped_internships(
            company["company"],
            company["career_url"],
            browser=browser
        )

    return adapter


# Platforms with a normalized adapter that returns internship dicts ready
# for direct SQLite insertion. "custom" uses a generic browser-based
# fallback (see _make_custom_adapter) rather than a per-platform API,
# since most of those companies' actual ATS hasn't been individually
# verified yet.
def _build_platform_adapters(browser):

    return {
        "greenhouse": lambda company: get_greenhouse_internships(
            company["company"],
            company["platform_identifier"]
        ),
        "jibe": lambda company: get_jibe_internships(
            company["company"],
            company["platform_identifier"]
        ),
        "eightfold": _eightfold_adapter,
        "oracle_orc": _oracle_orc_adapter,
        "workday": _workday_adapter,
        "successfactors": lambda company: get_successfactors_internships(
            company["company"],
            company["platform_identifier"]
        ),
        "taleo": _taleo_adapter,
        "lever": lambda company: get_lever_internships(
            company["company"],
            company["platform_identifier"]
        ),
        "icims": lambda company: get_icims_internships(
            company["company"],
            company["platform_identifier"]
        ),
        "adp": _make_adp_adapter(browser),
        "custom": _make_custom_adapter(browser),
    }


def run_monitor(skip_custom=False, baseline=False):
    """
    skip_custom=True (--fast) skips every company that needs the slow
    headless browser (BROWSER_PLATFORMS) without importing
    Playwright. Handy for a quick local check; the scheduled workflow
    always does a full run.

    baseline=True (--baseline) runs the full scan but, instead of
    sending, marks every queued alert as sent. Use it once on a fresh
    registry so the first real run only alerts on postings that are
    genuinely new, not everything currently open.
    """

    create_database()

    companies = load_enabled_companies()

    if skip_custom:
        companies = [
            c for c in companies
            if c.get("platform") not in BROWSER_PLATFORMS
        ]

    summary = {
        "companies_checked": len(companies),
        "companies_successful": 0,
        "companies_failed": 0,
        "companies_skipped": 0,
        "jobs_retrieved": 0,
        "internships_matched": 0,
        "new_internships_inserted": 0,
        "existing_internships_skipped": 0,
        "alerts_created": 0,
        "sms_sent": 0,
        "alerts_held": 0,
        "alerts_skipped_non_us": 0,
        "locations_resolved": 0,
        "alerts_baselined": 0,
        # Companies with an alert whose location stayed unknown.
        "unknown_location_companies": set(),
    }

    needs_browser = any(
        c.get("platform") in BROWSER_PLATFORMS for c in companies
    )

    if needs_browser:

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:

            browser = p.chromium.launch(
                headless=True, args=["--disable-http2"]
            )

            try:
                _run_all_companies(
                    companies,
                    _build_platform_adapters(browser),
                    summary,
                    browser=browser,
                )
            finally:
                browser.close()

    else:

        _run_all_companies(
            companies, _build_platform_adapters(None), summary
        )

    if baseline:
        _baseline_pending_alerts(summary)
    else:
        _send_pending_alerts(summary)

    print_summary(summary)

    return summary


def _baseline_pending_alerts(summary):
    """Mark every queued alert as sent without sending anything."""

    pending = get_unsent_alerts()

    if pending:
        mark_alerts_sent([alert["id"] for alert in pending])

    summary["alerts_baselined"] = len(pending)

    print(
        f"Baseline: marked {len(pending)} queued alert(s) as sent "
        f"without sending."
    )


def _send_pending_alerts(summary):
    """
    Send every queued (not yet sent) alert in one notification, at any
    hour (quiet hours are left to the phone's own Do Not Disturb). Only
    marks them sent once the send succeeds, so a failed send is retried
    by the next run instead of lost.
    """

    pending = get_unsent_alerts()

    if not pending:
        return

    count = len(pending)
    title = (
        "1 new internship" if count == 1 else f"{count} new internships"
    )

    if send_alert(_build_batch_sms_body(pending), title=title):

        mark_alerts_sent([alert["id"] for alert in pending])

        summary["sms_sent"] += 1

    else:

        summary["alerts_held"] = len(pending)


def _build_batch_sms_body(new_alerts):
    """
    Consolidates all of this run's new-internship alerts into ONE
    message (one SMTP send), instead of one text per internship.
    Carriers' email-to-SMS gateways (e.g. T-Mobile's tmomail.net)
    rate-limit and will bounce/block a sender that fires off many
    separate messages in a burst - a single run that finds several new
    postings at once (e.g. right after adding a new company) would
    otherwise trigger exactly that. Listing everything in one email
    doesn't have that problem even if the carrier splits it into
    multiple physical texts on the receiving end, since it's still one
    send from this end.
    """

    count = len(new_alerts)

    if count == 1:

        internship = new_alerts[0]

        return (
            f"New internship: {internship['company']} - "
            f"{internship['title']} "
            f"{_location_label(internship.get('location'))}\n"
            f"{internship.get('application_url', '')}"
        )

    # Group same-named postings at the same company together (e.g. a
    # company opening 5 identical "Software Engineering Intern" reqs at
    # once) so the text reads as one role with 5 links, not 5 separate
    # near-duplicate entries.
    groups = {}
    group_order = []

    for internship in new_alerts:

        key = (internship["company"], internship["title"])

        if key not in groups:
            groups[key] = []
            group_order.append(key)

        groups[key].append(internship)

    lines = [f"{count} new internships found:"]

    for key in group_order:

        company, title = key
        items = groups[key]

        lines.append("")
        lines.append(f"{title} - {company}")

        for item in items:

            url = item.get("application_url", "")

            if classify_location(item.get("location")) == UNKNOWN:
                url = f"{url} {UNKNOWN_LOCATION_LABEL}"

            lines.append(url)

    return "\n".join(lines)


def _location_label(location):

    if classify_location(location) == UNKNOWN:
        return UNKNOWN_LOCATION_LABEL

    return f"({location})"


def _resolve_location(company, internship, browser=None):
    """
    The listing gave no usable location - try the posting itself.
    Returns the looked-up location string, or "" if none was found.
    """

    url = internship.get("application_url") or ""

    if not url:
        return ""

    platform = company.get("platform", "")

    try:

        if platform == "workday":

            tenant = company["platform_identifier"].split("|")[1]

            return posting_location.workday_location(url, tenant)

        if browser is not None and platform in BROWSER_PLATFORMS:

            return posting_location.location_via_browser(url, browser)

        return posting_location.location_via_requests(url)

    except Exception as e:
        print(f"Location lookup failed for {url}: {e}")
        return ""


def _run_all_companies(companies, adapters, summary, browser=None):

    for company in companies:

        name = company.get("company", "Unknown")
        platform = company.get("platform", "")

        adapter = adapters.get(platform)

        if adapter is None:

            print(f"[SKIP] {name}: no adapter for platform '{platform}'")

            summary["companies_skipped"] += 1

            continue

        try:

            internships = adapter(company)

        except Exception as e:

            print(f"[FAIL] {name}: {e}")

            summary["companies_failed"] += 1

            continue

        summary["companies_successful"] += 1
        summary["jobs_retrieved"] += len(internships)
        summary["internships_matched"] += len(internships)

        for internship in internships:

            result = upsert_internship(
                company=internship["company"],
                title=internship["title"],
                location=internship.get("location", ""),
                role_type=internship.get("role_type", "Other"),
                application_url=internship.get("application_url", ""),
                source_platform=internship.get("source_platform", platform),
                external_job_id=internship.get("external_job_id"),
            )

            if result["is_new"]:

                summary["new_internships_inserted"] += 1

                location = internship.get("location", "")
                role_type = internship.get("role_type", "Other")

                would_alert = (
                    is_target_role(role_type)
                    and not is_ineligible(internship["title"])
                )

                # Only spend a lookup on postings that would otherwise
                # alert and whose listing gave no usable location.
                if would_alert and classify_location(location) == UNKNOWN:

                    resolved = _resolve_location(company, internship, browser)

                    if resolved and classify_location(resolved) != UNKNOWN:

                        location = resolved

                        update_internship_location(
                            result["dedup_key"], location
                        )

                        summary["locations_resolved"] += 1

                if would_alert and classify_location(location) == NON_US:

                    summary["alerts_skipped_non_us"] += 1

                    continue

                alert = create_alert_for_new_internship(
                    internship["company"],
                    internship["title"],
                    location,
                    role_type,
                    application_url=internship.get("application_url", ""),
                )

                if alert:

                    summary["alerts_created"] += 1

                    if classify_location(location) == UNKNOWN:
                        summary["unknown_location_companies"].add(name)

            else:

                summary["existing_internships_skipped"] += 1


def print_summary(summary):

    print("\n===== Monitor Run Summary =====\n")

    print(f"Companies checked: {summary['companies_checked']}")
    print(f"Companies successful: {summary['companies_successful']}")
    print(f"Companies failed: {summary['companies_failed']}")
    print(f"Companies skipped (no adapter): {summary['companies_skipped']}")
    print(f"Jobs retrieved: {summary['jobs_retrieved']}")
    print(f"Internships matched: {summary['internships_matched']}")
    print(f"New internships inserted: {summary['new_internships_inserted']}")
    print(
        f"Existing internships skipped: "
        f"{summary['existing_internships_skipped']}"
    )
    print(f"Alerts created: {summary['alerts_created']}")
    print(f"Alerts skipped (non-US): {summary['alerts_skipped_non_us']}")
    print(
        f"Locations looked up from posting pages: "
        f"{summary['locations_resolved']}"
    )
    print(f"Alerts sent (batches): {summary['sms_sent']}")
    print(f"Alerts held for later: {summary['alerts_held']}")

    if summary.get("alerts_baselined"):
        print(
            f"Alerts marked sent by --baseline: "
            f"{summary['alerts_baselined']}"
        )

    unknown = summary.get("unknown_location_companies") or set()

    if unknown:
        print(
            "Alerts with unknown location from: "
            + ", ".join(sorted(unknown))
        )


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fast",
        action="store_true",
        help=(
            "Skip companies that need the headless browser (custom and "
            "adp platforms). Only checks companies with a structured API; "
            "doesn't require Playwright/Chromium."
        ),
    )
    parser.add_argument(
        "--baseline",
        action="store_true",
        help=(
            "Run the full scan but mark every queued alert as sent "
            "without sending anything. Run once on a fresh setup so the "
            "first real run doesn't alert on every currently open posting."
        ),
    )
    args = parser.parse_args()

    run_monitor(skip_custom=args.fast, baseline=args.baseline)
