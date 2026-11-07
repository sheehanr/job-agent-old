"""
Builds the one-per-run phone notification, shared by both alert sources
(the career-site monitor and the Simplify listings).
"""

from location_filter import classify_location, UNKNOWN, UNKNOWN_LOCATION_LABEL


def alert_title(count, source_label):
    """Notification title, e.g. "Simplify: 3 new internships"."""

    noun = "1 new internship" if count == 1 else f"{count} new internships"

    return f"{source_label}: {noun}"


def _location_label(location, max_places=3):

    if classify_location(location) == UNKNOWN:
        return UNKNOWN_LOCATION_LABEL

    # Simplify listings can name a dozen cities - keep the line readable.
    places = [p.strip() for p in str(location).split(";") if p.strip()]

    if len(places) > max_places:
        location = "; ".join(places[:max_places]) + (
            f" +{len(places) - max_places} more"
        )

    return f"({location})"


def build_alert_body(new_alerts, source_label=None):
    """
    Consolidates all of a run's alerts into ONE message instead of one
    per internship - carriers' email-to-SMS gateways rate-limit bursts,
    and one push per run is easier to read anyway. Same company + title
    postings are grouped under one header with all their links.
    source_label (e.g. "Simplify") prefixes the message so you can tell
    the two sources apart.
    """

    prefix = f"{source_label}: " if source_label else ""

    count = len(new_alerts)

    if count == 1:

        internship = new_alerts[0]

        return (
            f"{prefix}New internship: {internship['company']} - "
            f"{internship['title']} "
            f"{_location_label(internship.get('location'))}\n"
            f"{internship.get('application_url', '')}"
        )

    groups = {}
    group_order = []

    for internship in new_alerts:

        key = (internship["company"], internship["title"])

        if key not in groups:
            groups[key] = []
            group_order.append(key)

        groups[key].append(internship)

    lines = [f"{prefix}{count} new internships found:"]

    for key in group_order:

        company, title = key

        lines.append("")
        lines.append(f"{title} - {company}")

        for item in groups[key]:

            url = item.get("application_url", "")

            if classify_location(item.get("location")) == UNKNOWN:
                url = f"{url} {UNKNOWN_LOCATION_LABEL}"

            lines.append(url)

    return "\n".join(lines)
