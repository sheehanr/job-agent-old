import os
import sqlite3
import tempfile
from datetime import date

import pytest

import database_alerts
import database_setup
import simplify_alerts as sa


# ---------------------------------------------------------------- terms


@pytest.fixture
def today(monkeypatch):
    """Pin "today" by patching the module's date source."""

    def pin(day):
        monkeypatch.setattr(sa, "_today", lambda: day)
        return day

    return pin


def test_term_start_dates():

    assert sa.term_start("Winter 2027") == date(2027, 1, 1)
    assert sa.term_start("Spring 2027") == date(2027, 1, 1)
    assert sa.term_start("Summer 2027") == date(2027, 5, 15)
    assert sa.term_start("Fall 2027") == date(2027, 8, 20)
    assert sa.term_start("summer  2028") == date(2028, 5, 15)
    assert sa.term_start("N/A") is None
    assert sa.term_start("Summer") is None


@pytest.mark.parametrize("pinned, terms, expected", [
    # Nov 2026: Summer 2027 hasn't started, Summer/Fall 2026 have.
    (date(2026, 11, 6), ["Summer 2027"], True),
    (date(2026, 11, 6), ["Summer 2026"], False),
    (date(2026, 11, 6), ["Fall 2026"], False),
    (date(2026, 11, 6), ["Winter 2027"], True),
    (date(2026, 11, 6), ["Fall 2026", "Spring 2027"], True),
    # Winter/Spring start Jan 1 - started once the year begins.
    (date(2027, 1, 1), ["Spring 2027"], False),
    (date(2026, 12, 31), ["Spring 2027"], True),
    # Summer starts May 15, Fall Aug 20 (the start day counts as started).
    (date(2027, 5, 14), ["Summer 2027"], True),
    (date(2027, 5, 15), ["Summer 2027"], False),
    (date(2027, 8, 19), ["Fall 2027"], True),
    (date(2027, 8, 20), ["Fall 2027"], False),
    # More than 2 years out is ignored.
    (date(2026, 11, 6), ["Summer 2029"], False),
    (date(2026, 11, 6), ["Fall 2028"], True),
    (date(2026, 11, 6), ["Summer 2029", "Summer 2027"], True),
    # No term given.
    (date(2026, 11, 6), ["N/A"], True),
    (date(2026, 11, 6), [], True),
    # Garbage-only terms aren't "no term".
    (date(2026, 11, 6), ["Summer 2016"], False),
])
def test_term_filter_with_mocked_today(today, pinned, terms, expected):

    today(pinned)

    assert sa.passes_term_filter(terms) is expected


def test_term_filter_rolls_forward_by_itself(today):
    """Same terms, later date: no hardcoded years anywhere."""

    today(date(2026, 11, 6))
    assert sa.passes_term_filter(["Summer 2027"])
    assert not sa.passes_term_filter(["Summer 2029"])

    today(date(2027, 11, 6))
    assert not sa.passes_term_filter(["Summer 2027"])
    assert sa.passes_term_filter(["Summer 2028"])
    assert sa.passes_term_filter(["Summer 2029"])


def test_horizon_handles_leap_day(today):

    today(date(2028, 2, 29))

    assert sa.passes_term_filter(["Winter 2029"])


# ------------------------------------------------------------ watchlist


WATCHLIST = """\
# comment line
Google
Intuit
Epic Systems | Epic
Johnson & Johnson | J&J
GE HealthCare | GE Healthcare
Regeneron | Regeneron Pharmaceuticals
Insulet
"""


@pytest.fixture
def watchlist_path(tmp_path):

    path = tmp_path / "simplify_watchlist.txt"
    path.write_text(WATCHLIST)

    return str(path)


@pytest.mark.parametrize("company, canonical", [
    ("Google", "Google"),
    ("google", "Google"),
    ("  GOOGLE ", "Google"),
    ("Epic", "Epic Systems"),
    ("Epic Systems", "Epic Systems"),
    ("Regeneron Pharmaceuticals", "Regeneron"),
    ("GE Healthcare", "GE HealthCare"),
    ("Johnson & Johnson", "Johnson & Johnson"),
    # Whole-name only - never substring.
    ("Epic Games", None),
    ("Intuitive Surgical", None),
    ("Google DeepMind", None),
    ("Insulet Corporation", None),
])
def test_watchlist_exact_whole_name(watchlist_path, company, canonical):

    watchlist = sa.load_watchlist(watchlist_path)

    assert watchlist.get(sa.normalize_company(company)) == canonical


def test_unmatched_watchlist_names(watchlist_path):

    listings = [
        {"company_name": "google"},
        {"company_name": "Regeneron Pharmaceuticals"},
        {"company_name": "Epic Games"},
    ]

    assert sa.unmatched_watchlist_names(listings, watchlist_path) == [
        "Intuit", "Epic Systems", "Johnson & Johnson", "GE HealthCare",
        "Insulet",
    ]


def test_seeded_watchlist_file_is_valid():
    """The real data file parses and keeps the Epic distinction."""

    watchlist = sa.load_watchlist()

    assert watchlist["google"] == "Google"
    assert watchlist["epic"] == "Epic Systems"
    assert "epic games" not in watchlist
    assert watchlist["ge healthcare"] == "GE HealthCare"
    assert watchlist["regeneron pharmaceuticals"] == "Regeneron"
    assert watchlist["intuitive surgical"] == "Intuitive Surgical"
    assert watchlist["boston scientific"] == "Boston Scientific"


# --------------------------------------------------------------- filter


def _listing(**overrides):

    listing = {
        "id": "id-1",
        "company_name": "Google",
        "title": "Software Engineering Intern",
        "category": "Software",
        "active": True,
        "is_visible": True,
        "terms": ["Summer 2027"],
        "locations": ["Mountain View, CA"],
        "url": "https://careers.google.com/jobs/1",
    }
    listing.update(overrides)

    return listing


@pytest.fixture
def pinned_today(today):
    return today(date(2026, 11, 6))


@pytest.mark.parametrize("overrides, expected", [
    ({}, "Google"),
    ({"active": False}, None),
    ({"is_visible": False}, None),
    ({"company_name": "Epic Games"}, None),
    ({"company_name": "Epic"}, "Epic Systems"),
    # Location: at least one US.
    ({"locations": ["London, UK", "Toronto, ON, Canada"]}, None),
    ({"locations": ["London, UK", "NYC"]}, "Google"),
    ({"locations": ["SF"]}, "Google"),
    ({"locations": ["Remote in USA"]}, "Google"),
    # Terms.
    ({"terms": ["Summer 2026"]}, None),
    ({"terms": ["N/A"]}, "Google"),
    # Categories.
    ({"category": "AI/ML/Data"}, "Google"),
    ({"category": "Software Engineering"}, "Google"),
    ({"category": "Data Science, AI & Machine Learning"}, "Google"),
    ({"category": "Product"}, None),
    ({"category": "Quant"}, None),
    # Hardware only for Embedded / Firmware / Robotics titles.
    ({"category": "Hardware", "title": "Embedded Software Intern"}, "Google"),
    ({"category": "Hardware", "title": "Firmware Engineer Co-op"}, "Google"),
    ({"category": "Hardware", "title": "Robotics Intern"}, "Google"),
    ({"category": "Hardware", "title": "ASIC Design Intern"}, None),
    ({"category": "Hardware", "title": "Electronics Technician Intern"}, None),
    # Ineligible titles.
    ({"title": "PhD Software Engineering Intern"}, None),
    ({"title": "Master's Machine Learning Intern"}, None),
])
def test_match_listing(watchlist_path, pinned_today, overrides, expected):

    watchlist = sa.load_watchlist(watchlist_path)

    assert sa.match_listing(_listing(**overrides), watchlist) == expected


# ------------------------------------------------------------------ run


@pytest.fixture
def test_db():

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database_setup.create_database(path)

    yield path

    os.remove(path)


@pytest.fixture
def sends(monkeypatch):

    sent = []

    def fake_send(body, title=None):
        sent.append((title, body))
        return True

    monkeypatch.setattr(sa, "send_alert", fake_send)

    return sent


def _run(test_db, watchlist_path, listings, **kwargs):

    return sa.run_simplify(
        db_path=test_db,
        listings=listings,
        watchlist_path=watchlist_path,
        **kwargs
    )


def _seed_seen(test_db, watchlist_path):
    """Get past the automatic first-run baseline."""

    _run(test_db, watchlist_path, [_listing(id="old", title="Old Intern")])


def test_first_run_is_automatic_baseline(test_db, watchlist_path,
                                         pinned_today, sends):

    summary = _run(test_db, watchlist_path, [_listing()])

    assert summary["baseline"] is True
    assert sends == []
    assert database_alerts.get_unsent_alerts(test_db, source="simplify") == []


def test_new_match_alerts_once_labelled_simplify(test_db, watchlist_path,
                                                 pinned_today, sends):

    _seed_seen(test_db, watchlist_path)

    listings = [
        _listing(id="a", title="Software Engineering Intern"),
        _listing(id="b", company_name="Epic", title="Software Developer Intern",
                 locations=["Verona, WI"], url="https://epic/1"),
        _listing(id="c", company_name="Epic Games", title="Gameplay Intern"),
    ]

    summary = _run(test_db, watchlist_path, listings)

    assert summary["alerts_sent"] == 2
    assert len(sends) == 1
    title, body = sends[0]
    assert title == "Simplify: 2 new internships"
    assert body.startswith("Simplify: 2 new internships found:")
    assert "Software Developer Intern - Epic Systems" in body
    assert "Gameplay" not in body

    # Same listings next run: already seen, nothing new.
    sends.clear()
    summary = _run(test_db, watchlist_path, listings)

    assert summary["new_matches"] == 0
    assert sends == []


def test_dedupes_against_monitor_alert(test_db, watchlist_path,
                                       pinned_today, sends):

    _seed_seen(test_db, watchlist_path)

    # The career-site monitor already alerted on this role (different
    # case/whitespace, registry spelling of the company).
    database_alerts.save_alert(
        "GE HealthCare", "software engineer intern ", "Waukesha, WI",
        db_path=test_db, source="monitor", sent=True,
    )

    summary = _run(test_db, watchlist_path, [
        _listing(id="x", company_name="GE Healthcare",
                 title="Software Engineer Intern"),
    ])

    assert summary["duplicates_skipped"] == 1
    assert sends == []


def test_monitor_dedupes_against_simplify_alert(test_db):

    database_alerts.save_alert(
        "Regeneron", "2027 Summer Intern IT & Systems", "Rensselaer, NY",
        db_path=test_db, source="simplify", sent=True,
    )

    assert database_alerts.was_recently_texted(
        "regeneron", "2027 Summer Intern IT & Systems", db_path=test_db
    )


def test_explicit_baseline_marks_seen_without_sending(test_db, watchlist_path,
                                                      pinned_today, sends):

    _seed_seen(test_db, watchlist_path)

    summary = _run(test_db, watchlist_path, [_listing(id="new")], baseline=True)

    assert summary["alerts_queued"] == 1
    assert sends == []
    assert database_alerts.get_unsent_alerts(test_db, source="simplify") == []

    conn = sqlite3.connect(test_db)
    seen = {r[0] for r in conn.execute("SELECT listing_id FROM simplify_seen")}
    conn.close()

    assert "new" in seen

    # And it doesn't alert later either.
    summary = _run(test_db, watchlist_path, [_listing(id="new")])
    assert summary["new_matches"] == 0
    assert sends == []


def test_failed_send_stays_queued_and_retries(test_db, watchlist_path,
                                             pinned_today, monkeypatch):

    _seed_seen(test_db, watchlist_path)

    monkeypatch.setattr(sa, "send_alert", lambda body, title=None: False)

    _run(test_db, watchlist_path, [_listing(id="q")])

    assert len(database_alerts.get_unsent_alerts(test_db, source="simplify")) == 1

    retried = []
    monkeypatch.setattr(
        sa, "send_alert",
        lambda body, title=None: retried.append(body) or True
    )

    _run(test_db, watchlist_path, [_listing(id="q")])

    assert len(retried) == 1
    assert database_alerts.get_unsent_alerts(test_db, source="simplify") == []


def test_sources_only_send_their_own_queue(test_db):

    database_alerts.save_alert("A", "SWE Intern", "NYC", db_path=test_db,
                               source="simplify")
    database_alerts.save_alert("B", "SWE Intern", "NYC", db_path=test_db)

    monitor = database_alerts.get_unsent_alerts(test_db)
    simplify = database_alerts.get_unsent_alerts(test_db, source="simplify")

    assert [a["company"] for a in monitor] == ["B"]
    assert [a["company"] for a in simplify] == ["A"]


def test_old_alerts_table_gets_source_column(tmp_path):

    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE alerts (id INTEGER PRIMARY KEY, timestamp TEXT, "
        "company TEXT, title TEXT, location TEXT, application_url TEXT, "
        "sms_sent INTEGER NOT NULL DEFAULT 0)"
    )
    conn.execute(
        "INSERT INTO alerts (company, title, sms_sent) VALUES ('X', 'Y', 0)"
    )
    conn.commit()
    conn.close()

    database_setup.create_database(path)

    conn = sqlite3.connect(path)
    row = conn.execute("SELECT source FROM alerts").fetchone()
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    conn.close()

    assert row == ("monitor",)
    assert "simplify_seen" in tables
