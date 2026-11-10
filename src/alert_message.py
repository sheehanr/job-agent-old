"""
Builds the phone notifications, shared by both alert sources (the
career-site monitor and the Simplify listings). Where a posting came from
isn't shown - the link goes to the company's own application page either
way.

One notification per role:
    title: "Stryker - SWE Intern (Portage, MI)"
    body:  the apply link (tapping the notification opens it too)

The same role posted in several locations is one notification with each
location and link in the body. A company posting GROUP_AT or more roles in
one run is a single "Meta - 6 new roles" notification instead of six.
"""

from location_filter import classify_location, UNKNOWN, UNKNOWN_LOCATION_LABEL

# A company with this many new roles in one run gets one notification.
GROUP_AT = 4


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


def _role_lines(items):
    """Apply links for one role: just the link, or location + link per
    posting when the same role has several postings."""

    if len(items) == 1:
        return [items[0].get("application_url", "")]

    lines = []

    for item in items:
        lines.append(_location_label(item.get("location")).strip("()"))
        lines.append(item.get("application_url", ""))

    return lines


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
        ids = [a.get("id") for a in company_alerts]

        if len(roles) >= group_at:

            blocks = []

            for title, items in roles.items():
                header = title
                if len(items) == 1:
                    header = f"{title} {_location_label(items[0].get('location'))}"
                blocks.append("\n".join([header] + _role_lines(items)))

            notifications.append({
                "title": f"{company} - {len(roles)} new roles",
                "body": "\n\n".join(blocks),
                "click": None,
                "ids": ids,
            })

            continue

        for title, items in roles.items():

            heading = f"{company} - {title}"
            click = None

            if len(items) == 1:
                heading = f"{heading} {_location_label(items[0].get('location'))}"
                click = items[0].get("application_url") or None

            notifications.append({
                "title": heading,
                "body": "\n".join(_role_lines(items)),
                "click": click,
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
