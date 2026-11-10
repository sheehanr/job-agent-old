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


def test_single_role_title_is_company_role_and_body_is_link_then_location():

    a = _alert("Stryker", "SWE Intern", "Portage, MI", "https://stryker.com/j/2")

    [note] = build_notifications([a])

    assert note["title"] == "Stryker - SWE Intern"
    assert note["body"] == "https://stryker.com/j/2\n(Portage, MI)"
    assert note["click"] == "https://stryker.com/j/2"
    assert note["ids"] == [a["id"]]
    # No source label anywhere.
    assert "Simplify" not in note["title"] + note["body"]
    assert "Career sites" not in note["title"] + note["body"]


def test_different_companies_get_separate_notifications():

    notes = build_notifications([
        _alert("Acme", "SWE Intern"),
        _alert("Globex", "Data Intern"),
    ])

    assert [n["title"] for n in notes] == [
        "Acme - SWE Intern",
        "Globex - Data Intern",
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
        "https://lm.com/1\n(Austin, TX)\n"
        "\n"
        "https://lm.com/2\n(Denver, CO)\n"
        "\n"
        "https://lm.com/3\n(location unknown)"
    )
    assert len(notes[0]["ids"]) == 3


def test_company_with_two_roles_is_one_notification():

    notes = build_notifications([
        _alert("Meta", "ML Intern", "Menlo Park, CA", "https://meta.com/1"),
        _alert("Meta", "SWE Intern", "Seattle, WA", "https://meta.com/2"),
        _alert("Acme", "SWE Intern", "Boston, MA", "https://acme.com/1"),
    ])

    assert len(notes) == 2
    assert notes[0]["title"] == "Meta - 2 new roles"
    assert notes[0]["body"] == (
        "ML Intern: https://meta.com/1\n(Menlo Park, CA)\n"
        "\n"
        "SWE Intern: https://meta.com/2\n(Seattle, WA)"
    )
    assert notes[0]["click"] is None
    assert len(notes[0]["ids"]) == 2
    assert notes[1]["title"] == "Acme - SWE Intern"


def test_grouped_role_with_several_locations_lists_each_link():

    [note] = build_notifications([
        _alert("Meta", "ML Intern", "Menlo Park, CA", "https://meta.com/1"),
        _alert("Meta", "ML Intern", "Seattle, WA", "https://meta.com/2"),
        _alert("Meta", "SWE Intern", "Seattle, WA", "https://meta.com/3"),
    ])

    assert note["title"] == "Meta - 2 new roles"
    assert note["body"].count("ML Intern: ") == 2
    assert "SWE Intern: https://meta.com/3\n(Seattle, WA)" in note["body"]


def test_unknown_and_remote_locations_are_labelled():

    [unknown] = build_notifications([_alert("Epic", "SWE Intern", "Unknown")])
    [remote] = build_notifications([_alert("Acme", "SWE Intern", "Remote")])

    assert unknown["title"] == "Epic - SWE Intern"
    assert unknown["body"].endswith("\n(location unknown)")
    assert remote["body"].endswith("\n(Remote)")


def test_failed_notification_only_holds_its_own_alerts():

    a, b = _alert("Acme", "SWE Intern"), _alert("Globex", "ML Intern")
    marked = []

    def send(body, title=None, click=None):
        return not title.startswith("Acme")

    sent, held = send_notifications([a, b], send, marked.extend)

    assert (sent, held) == (1, 1)
    assert marked == [b["id"]]
