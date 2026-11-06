import os
import sqlite3
import tempfile

import pytest

import database_setup
import database_monitor


@pytest.fixture
def test_db():

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    database_setup.create_database(path)

    yield path

    os.remove(path)


@pytest.mark.parametrize(
    "role_type", ["SWE", "ML", "Data", "Embedded", "Firmware", "Robotics"]
)
def test_alert_created_for_target_role(test_db, role_type):

    alert = database_monitor.create_alert_for_new_internship(
        "Acme", "Some Intern", "Remote", role_type, db_path=test_db
    )

    assert alert is not None

    conn = sqlite3.connect(test_db)
    count = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
    conn.close()

    assert count == 1


@pytest.mark.parametrize(
    "role_type",
    ["Cybersecurity", "Hardware", "Product", "Other"]
)
def test_no_alert_for_non_target_role(test_db, role_type):

    alert = database_monitor.create_alert_for_new_internship(
        "Acme", "Some Intern", "Remote", role_type, db_path=test_db
    )

    assert alert is None

    conn = sqlite3.connect(test_db)
    count = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
    conn.close()

    assert count == 0


def test_no_alert_for_phd_or_masters_internship(test_db):

    for title in [
        "Current PhD, AI Engineering Internship Program - Summer 2027",
        "Current Master's - Machine Learning Internship",
        "R&D PhD Summer Intern: AI Agents",
    ]:
        alert = database_monitor.create_alert_for_new_internship(
            "Acme", title, "Remote", "ML", db_path=test_db
        )
        assert alert is None


def test_alert_only_fires_once_per_new_internship(test_db):
    """Re-upserting the same job (no longer 'new') must not alert again."""

    result = database_monitor.upsert_internship(
        "Acme", "SWE Intern", "Remote", "SWE",
        "https://acme.com/jobs/1",
        source_platform="greenhouse",
        external_job_id="1",
        db_path=test_db
    )
    assert result["is_new"] is True

    database_monitor.create_alert_for_new_internship(
        "Acme", "SWE Intern", "Remote", "SWE", db_path=test_db
    )

    # Simulate a re-run of the monitor over the same job.
    result = database_monitor.upsert_internship(
        "Acme", "SWE Intern", "Remote", "SWE",
        "https://acme.com/jobs/1",
        source_platform="greenhouse",
        external_job_id="1",
        db_path=test_db
    )
    assert result["is_new"] is False

    # A real monitor run would only call create_alert_for_new_internship
    # when is_new is True, so simulate that here.
    conn = sqlite3.connect(test_db)
    count = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
    conn.close()

    assert count == 1


def test_new_alert_is_queued_until_sent(test_db):

    import database_alerts

    database_monitor.create_alert_for_new_internship(
        "Acme", "SWE Intern", "Remote", "SWE",
        application_url="https://acme.com/jobs/1", db_path=test_db
    )

    pending = database_alerts.get_unsent_alerts(db_path=test_db)

    assert len(pending) == 1
    assert pending[0]["application_url"] == "https://acme.com/jobs/1"

    database_alerts.mark_alerts_sent(
        [a["id"] for a in pending], db_path=test_db
    )

    assert database_alerts.get_unsent_alerts(db_path=test_db) == []


def test_migration_marks_existing_alerts_as_already_sent():
    """Alerts from before the queue existed were already texted."""

    import database_alerts

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        conn = sqlite3.connect(path)
        conn.execute(
            "CREATE TABLE alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "timestamp TEXT, company TEXT, title TEXT, location TEXT, "
            "matched_users TEXT, match_score INTEGER)"
        )
        conn.execute(
            "INSERT INTO alerts (company, title) VALUES ('Old', 'Old Intern')"
        )
        conn.commit()
        conn.close()

        database_setup.create_database(path)

        assert database_alerts.get_unsent_alerts(db_path=path) == []

    finally:
        os.remove(path)


def test_repost_of_recently_texted_role_does_not_alert_again(test_db):

    import database_alerts

    database_monitor.create_alert_for_new_internship(
        "Acme", "SWE Intern", "Remote", "SWE", db_path=test_db
    )

    # A same-run duplicate (e.g. another location) is still queued, so
    # both links go out grouped in one text.
    assert database_monitor.create_alert_for_new_internship(
        "Acme", "SWE Intern", "Austin", "SWE", db_path=test_db
    ) is not None

    pending = database_alerts.get_unsent_alerts(db_path=test_db)
    database_alerts.mark_alerts_sent(
        [a["id"] for a in pending], db_path=test_db
    )

    # Reposted under a new req id a few days later: no second text.
    assert database_monitor.create_alert_for_new_internship(
        "Acme", "SWE Intern", "Remote", "SWE", db_path=test_db
    ) is None

    # A different role at the same company still alerts.
    assert database_monitor.create_alert_for_new_internship(
        "Acme", "Data Analytics Intern", "Remote", "Data", db_path=test_db
    ) is not None


@pytest.mark.parametrize("location", [
    "Suzhou, China",
    "Milano",
    "HUN02-01-Budapest-Vaci Greens C",
    "Toronto, ON, CA",
])
def test_no_alert_for_known_non_us_location(test_db, location):

    assert database_monitor.create_alert_for_new_internship(
        "Acme", "SWE Intern", location, "SWE", db_path=test_db
    ) is None


@pytest.mark.parametrize("location", [
    "Boca Raton, FL",
    "Remote - US",
    "Unknown",
    "4 Locations",
])
def test_alert_for_us_or_unknown_location(test_db, location):

    assert database_monitor.create_alert_for_new_internship(
        "Acme", "SWE Intern", location, "SWE", db_path=test_db
    ) is not None
