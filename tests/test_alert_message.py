import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from alert_message import build_notifications, send_notifications  # noqa: E402


_next_id = iter(range(1, 10_000))


def _alert(company, title, location="Boston, MA", url=None):
    i = next(_next_id)
    return {
        "id": i, "company": company, "title": title, "location": location,
        "application_url": url or f"https://{company.lower()}.com/j/{i}",
    }


def test_single_role_title_is_company_role_location_and_body_is_link():

    a = _alert("Stryker", "SWE Intern", "Portage, Michigan", "https://stryker.com/j/2")

    [note] = build_notifications([a])

    assert note["title"] == "Stryker - SWE Intern (Portage, Michigan)"
    assert note["body"] == "https://stryker.com/j/2"
    assert note["click"] == "https://stryker.com/j/2"
    assert note["ids"] == [a["id"]]
    # No source label anywhere.
    assert "Simplify" not in note["title"] + note["body"]
    assert "Career sites" not in note["title"] + note["body"]


def test_each_role_gets_its_own_notification():

    notes = build_notifications([
        _alert("Acme", "SWE Intern"),
        _alert("Acme", "ML Intern"),
        _alert("Globex", "Data Intern"),
    ])

    assert [n["title"] for n in notes] == [
        "Acme - SWE Intern (Boston, MA)",
        "Acme - ML Intern (Boston, MA)",
        "Globex - Data Intern (Boston, MA)",
    ]


def test_same_role_several_locations_is_one_notification():

    notes = build_notifications([
        _alert("Lockheed", "Embedded Intern", "Austin, TX", "https://lm.com/1"),
        _alert("Lockheed", "Embedded Intern", "Denver, CO", "https://lm.com/2"),
        _alert("Lockheed", "Embedded Intern", "Unknown", "https://lm.com/3"),
    ])

    assert len(notes) == 1
    assert notes[0]["title"] == "Lockheed - Embedded Intern"
    assert notes[0]["click"] is None
    assert notes[0]["body"] == (
        "Austin, TX\nhttps://lm.com/1\n"
        "Denver, CO\nhttps://lm.com/2\n"
        "location unknown\nhttps://lm.com/3"
    )
    assert len(notes[0]["ids"]) == 3


def test_company_with_many_roles_is_grouped_into_one():

    alerts = [_alert("Meta", f"Role {i}", url=f"https://meta.com/{i}") for i in range(5)]
    alerts.append(_alert("Acme", "SWE Intern"))

    notes = build_notifications(alerts)

    assert len(notes) == 2
    assert notes[0]["title"] == "Meta - 5 new roles"
    for i in range(5):
        assert f"Role {i} (Boston, MA)\nhttps://meta.com/{i}" in notes[0]["body"]
    assert len(notes[0]["ids"]) == 5
    assert notes[1]["title"] == "Acme - SWE Intern (Boston, MA)"


def test_three_roles_at_one_company_still_separate():

    notes = build_notifications([_alert("Acme", f"Role {i}") for i in range(3)])

    assert len(notes) == 3


def test_unknown_location_is_labelled():

    [note] = build_notifications([_alert("Epic", "SWE Intern", "Unknown")])

    assert note["title"] == "Epic - SWE Intern (location unknown)"


def test_failed_notification_only_holds_its_own_alerts():

    a, b = _alert("Acme", "SWE Intern"), _alert("Globex", "ML Intern")
    marked = []

    def send(body, title=None, click=None):
        return not title.startswith("Acme")

    sent, held = send_notifications([a, b], send, marked.extend)

    assert (sent, held) == (1, 1)
    assert marked == [b["id"]]
