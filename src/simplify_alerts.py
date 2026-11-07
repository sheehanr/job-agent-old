"""
Second alert source: Simplify's public internship listings
(SimplifyJobs/Summer2027-Internships), filtered down to companies on
data/simplify_watchlist.txt and to roles I care about, then sent through
the same ntfy/SMS path as the career-site monitor.

Run after the monitor (the GitHub Action does):
    python src/simplify_alerts.py              # alert on new matches
    python src/simplify_alerts.py --baseline   # mark current matches seen
"""

import argparse
import os
import re
import sqlite3
from datetime import date, datetime

import requests

from database_setup import DB_PATH, create_database
from database_alerts import (
    save_alert,
    has_recent_alert,
    get_unsent_alerts,
    mark_alerts_sent,
)
from role_classifier import classify_role, is_ineligible
from location_filter import classify_location, US
from alert_message import alert_title, build_alert_body
from sms_alerts import send_alert

LISTINGS_URL = (
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/"
    "dev/.github/scripts/listings.json"
)

WATCHLIST_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "simplify_watchlist.txt"
)

SOURCE = "simplify"
SOURCE_LABEL = "Simplify"

ALLOWED_CATEGORIES = {
    "Software",
    "Software Engineering",
    "AI/ML/Data",
    "Data Science, AI & Machine Learning",
}

# Hardware-category listings only count for these roles.
HARDWARE_ROLES = {"Embedded", "Firmware", "Robotics"}

# When each kind of term starts (month, day). Winter and Spring start
# Jan 1 of the term's year.
TERM_STARTS = {
    "winter": (1, 1),
    "spring": (1, 1),
    "summer": (5, 15),
    "fall": (8, 20),
}

TERM_HORIZON_YEARS = 2

_TERM_RE = re.compile(r"^\s*(winter|spring|summer|fall)\s+(\d{4})\s*$", re.I)


def _today():
    """Separate function so tests can pin "today"."""

    return date.today()


# ---------------------------------------------------------------- terms


def term_start(term):
    """Start date of a term like "Summer 2027", or None if unparseable."""

    match = _TERM_RE.match(term or "")

    if not match:
        return None

    month, day = TERM_STARTS[match.group(1).lower()]

    return date(int(match.group(2)), month, day)


def _years_after(day, years):

    try:
        return day.replace(year=day.year + years)

    except ValueError:  # Feb 29 -> Feb 28
        return day.replace(year=day.year + years, day=28)


def passes_term_filter(terms, today=None):
    """
    Keep the listing if ANY of its terms hasn't started yet, ignoring
    terms more than TERM_HORIZON_YEARS out. Listings with no term
    (["N/A"] or empty) are kept. Computed from today's date, so it rolls
    forward on its own.
    """

    today = today or _today()

    terms = [t for t in (terms or []) if t is not None]

    if all(str(t).strip().upper() in ("N/A", "") for t in terms):
        return True

    horizon = _years_after(today, TERM_HORIZON_YEARS)

    for term in terms:

        start = term_start(str(term))

        if start is not None and today < start <= horizon:
            return True

    return False


# ------------------------------------------------------------ watchlist


def normalize_company(name):
    """Case-insensitive, whitespace-collapsed whole name."""

    return re.sub(r"\s+", " ", str(name or "")).strip().casefold()


def load_watchlist(path=WATCHLIST_PATH):
    """
    Returns {normalized name or alias: canonical name}. Each line is
    "Canonical Name | alias | alias ..."; blank lines and # comments
    are skipped.
    """

    watchlist = {}

    with open(path, encoding="utf-8") as f:

        for line in f:

            line = line.strip()

            if not line or line.startswith("#"):
                continue

            names = [n.strip() for n in line.split("|") if n.strip()]

            canonical = names[0]

            for name in names:
                watchlist[normalize_company(name)] = canonical

    return watchlist


def watchlist_entries(path=WATCHLIST_PATH):
    """[(canonical, [names incl. aliases])] in file order."""

    entries = []

    with open(path, encoding="utf-8") as f:

        for line in f:

            line = line.strip()

            if line and not line.startswith("#"):
                names = [n.strip() for n in line.split("|") if n.strip()]
                entries.append((names[0], names))

    return entries


def unmatched_watchlist_names(listings, path=WATCHLIST_PATH):
    """Watchlist companies none of whose names/aliases appear anywhere in
    the listings file - usually a spelling difference."""

    present = {normalize_company(l.get("company_name")) for l in listings}

    return [
        canonical
        for canonical, names in watchlist_entries(path)
        if not any(normalize_company(n) in present for n in names)
    ]


# --------------------------------------------------------------- filter


def has_us_location(locations):

    return any(classify_location(loc) == US for loc in (locations or []))


def passes_role_filter(listing):

    category = listing.get("category") or ""
    title = listing.get("title") or ""

    if category in ALLOWED_CATEGORIES:
        return True

    if category == "Hardware":
        return classify_role(title) in HARDWARE_ROLES

    return False


def match_listing(listing, watchlist, today=None):
    """
    Returns the canonical watchlist company name if the listing should
    alert, else None.
    """

    if not (listing.get("active") and listing.get("is_visible")):
        return None

    canonical = watchlist.get(normalize_company(listing.get("company_name")))

    if canonical is None:
        return None

    if not has_us_location(listing.get("locations")):
        return None

    if not passes_term_filter(listing.get("terms"), today):
        return None

    if not passes_role_filter(listing):
        return None

    if is_ineligible(listing.get("title") or ""):
        return None

    return canonical


# ------------------------------------------------------------------ run


def fetch_listings(url=LISTINGS_URL):

    response = requests.get(
        url, headers={"User-Agent": "hidden-gem-agent"}, timeout=60
    )
    response.raise_for_status()

    return response.json()


def _seen_ids(db_path):

    conn = sqlite3.connect(db_path)

    ids = {row[0] for row in conn.execute("SELECT listing_id FROM simplify_seen")}

    conn.close()

    return ids


def _mark_seen(listing, canonical, db_path):

    conn = sqlite3.connect(db_path)

    conn.execute(
        """
        INSERT OR IGNORE INTO simplify_seen
            (listing_id, company, title, first_seen)
        VALUES (?, ?, ?, ?)
        """,
        (
            str(listing["id"]),
            canonical,
            listing.get("title"),
            datetime.now().isoformat(),
        )
    )

    conn.commit()
    conn.close()


def _listing_location(listing):

    us = [l for l in listing.get("locations") or [] if classify_location(l) == US]

    return "; ".join(us)


def run_simplify(baseline=False, db_path=DB_PATH, listings=None, today=None,
                 watchlist_path=WATCHLIST_PATH):
    """
    Process the current Simplify listings. New matches (listing id not in
    simplify_seen) are queued as alerts with source="simplify" unless the
    same company + title was already alerted by either source in the last
    14 days, then all queued Simplify alerts go out as one notification.

    baseline=True records current matches as seen (and their alerts as
    already sent) without notifying. The very first run - an empty
    simplify_seen table - is always treated as a baseline, so turning
    this source on can't flood the phone with every open listing.
    """

    create_database(db_path)

    if listings is None:
        listings = fetch_listings()

    watchlist = load_watchlist(watchlist_path)
    seen = _seen_ids(db_path)

    if not seen and not baseline:
        print("Simplify: first run (nothing seen yet) - running as baseline.")
        baseline = True

    summary = {
        "listings": len(listings),
        "matches": 0,
        "new_matches": 0,
        "duplicates_skipped": 0,
        "alerts_queued": 0,
        "alerts_sent": 0,
        "baseline": baseline,
    }

    for listing in listings:

        canonical = match_listing(listing, watchlist, today)

        if canonical is None or not listing.get("id"):
            continue

        summary["matches"] += 1

        if str(listing["id"]) in seen:
            continue

        seen.add(str(listing["id"]))
        summary["new_matches"] += 1

        _mark_seen(listing, canonical, db_path)

        title = (listing.get("title") or "").strip()

        if has_recent_alert(canonical, title, db_path=db_path):
            summary["duplicates_skipped"] += 1
            continue

        save_alert(
            canonical,
            title,
            _listing_location(listing),
            application_url=listing.get("url") or "",
            db_path=db_path,
            source=SOURCE,
            sent=baseline,
        )

        summary["alerts_queued"] += 1

    if baseline:
        # Also clear anything left queued from an earlier failed send.
        pending = get_unsent_alerts(db_path=db_path, source=SOURCE)
        mark_alerts_sent([a["id"] for a in pending], db_path=db_path)
    else:
        _send_pending(summary, db_path)

    _print_summary(summary)

    return summary


def _send_pending(summary, db_path):

    pending = get_unsent_alerts(db_path=db_path, source=SOURCE)

    if not pending:
        return

    if send_alert(
        build_alert_body(pending, source_label=SOURCE_LABEL),
        title=alert_title(len(pending), SOURCE_LABEL),
    ):
        mark_alerts_sent([a["id"] for a in pending], db_path=db_path)
        summary["alerts_sent"] = len(pending)


def _print_summary(summary):

    print("\n===== Simplify Run Summary =====\n")
    print(f"Listings in file: {summary['listings']}")
    print(f"Matching watchlist/filters: {summary['matches']}")
    print(f"New matches this run: {summary['new_matches']}")
    print(f"Skipped (already alerted by company + title): "
          f"{summary['duplicates_skipped']}")

    if summary["baseline"]:
        print(f"Baseline: recorded {summary['alerts_queued']} as already "
              f"sent, nothing sent.")
    else:
        print(f"Alerts queued: {summary['alerts_queued']}")
        print(f"Alerts sent: {summary['alerts_sent']}")


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--baseline",
        action="store_true",
        help=(
            "Mark every listing that currently matches as seen without "
            "sending anything."
        ),
    )
    parser.add_argument(
        "--report-unmatched",
        action="store_true",
        help="List watchlist companies that appear nowhere in the file.",
    )
    args = parser.parse_args()

    if args.report_unmatched:

        names = unmatched_watchlist_names(fetch_listings())

        print(f"{len(names)} watchlist companies matched nothing:")

        for name in names:
            print(f"  {name}")

    else:
        run_simplify(baseline=args.baseline)
