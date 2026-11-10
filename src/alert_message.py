"""
Builds the phone notifications, shared by both alert sources (the
career-site monitor and the Simplify listings). Where a posting came from
isn't shown - the link goes to the company's own application page either
way. The location goes under each link, never in the title.

One role:
    Stryker - SWE Intern
    https://stryker.com/...
    (Portage, MI)

Same role, 2 or more locations (one link + location per block):
    Lockheed - Embedded Intern
    https://...
    (Austin, TX)

    https://...
    (Denver, CO)

Same company, 2 or more roles in one run:
    Meta - 2 new roles
    ML Intern: https://...
    (Menlo Park, CA)

    SWE Intern: https://...
    (Seattle, WA)
"""

from location_filter import classify_location, UNKNOWN, UNKNOWN_LOCATION_LABEL

# A company with this many new roles in one run gets one notification.
GROUP_AT = 2


def _location_label(location, max_places=3):

    if classify_location(location) == UNKNOWN:
        if "remote" in str(location or "").lower():
            return "(Remote)"
        return UNKNOWN_LOCATION_LABEL

    # Simplify listings can name a dozen cities - keep the line readable.
    places = [p.strip() for p in str(location).split(";") if p.strip()]

    if len(places) > max_places:
        location = "; ".join(places[:max_places]) + (
            f" +{len(places) - max_places} more"
        )

    return f"({location})"


def _group(items, key):

    groups = {}

    for item in items:
        groups.setdefault(key(item), []).append(item)

    return groups


def _posting_block(item, role=None):
    """Link (prefixed with the role when grouping several roles), then
    the location in parentheses on the next line."""

    url = item.get("application_url", "")
    link = f"{role}: {url}" if role else url

    return f"{link}\n{_location_label(item.get('location'))}"


def build_notifications(new_alerts, group_at=GROUP_AT):
    """
    Turn queued alerts into notifications. Returns a list of dicts:
    title, body, click (URL opened by tapping, or None), and ids (the
    alert ids it covers, so each is marked sent only once delivered).
    Every posting's apply link is always included.
    """

    notifications = []

    by_company = _group(new_alerts, lambda a: a["company"])

    for company, company_alerts in by_company.items():

        roles = _group(company_alerts, lambda a: a["title"])

        if len(roles) >= group_at:

            notifications.append({
                "title": f"{company} - {len(roles)} new roles",
                "body": "\n\n".join(
                    _posting_block(item, role=title)
                    for title, items in roles.items()
                    for item in items
                ),
                "click": None,
                "ids": [a.get("id") for a in company_alerts],
            })

            continue

        for title, items in roles.items():

            notifications.append({
                "title": f"{company} - {title}",
                "body": "\n\n".join(_posting_block(item) for item in items),
                "click": (
                    items[0].get("application_url") or None
                    if len(items) == 1 else None
                ),
                "ids": [a.get("id") for a in items],
            })

    return notifications


def send_notifications(pending, send, mark_sent):
    """
    Send each notification for the queued alerts with send(body, title,
    click); mark_sent(ids) runs only after that notification is
    delivered, so a failure leaves just its own alerts queued for the
    next run. Returns (notifications sent, alerts still held).
    """

    sent = held = 0

    for note in build_notifications(pending):

        if send(note["body"], title=note["title"], click=note["click"]):
            mark_sent(note["ids"])
            sent += 1
        else:
            held += len(note["ids"])

    return sent, held
