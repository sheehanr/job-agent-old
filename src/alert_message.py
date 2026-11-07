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
    Body of the one-per-run notification. The title (see alert_title)
    already carries the source and the count, so the body is just the
    postings: a "Title - Company" header per role, then its apply link(s).
    Same company + title postings share one header. Every posting's apply
    link is always included.

    source_label is accepted for symmetry with alert_title but isn't
    repeated in the body.
    """

    groups = {}
    group_order = []

    for internship in new_alerts:

        key = (internship["company"], internship["title"])

        if key not in groups:
            groups[key] = []
            group_order.append(key)

        groups[key].append(internship)

    blocks = []

    for key in group_order:

        company, title = key
        items = groups[key]

        header = f"{title} - {company}"

        if len(items) == 1:
            header = f"{header} {_location_label(items[0].get('location'))}"

        lines = [header]

        for item in items:

            url = item.get("application_url", "")

            if len(items) > 1 and classify_location(item.get("location")) == UNKNOWN:
                url = f"{url} {UNKNOWN_LOCATION_LABEL}"

            lines.append(url)

        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)
