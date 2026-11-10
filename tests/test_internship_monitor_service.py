import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import internship_monitor_service as svc  # noqa: E402


def _make_internship(company, title, location="Remote", url="https://example.com/job/1"):
    return {
        "company": company,
        "title": title,
        "location": location,
        "application_url": url,
    }


def _patch_pending(monkeypatch, pending, send_result=True):

    sent_bodies = []
    marked = []

    monkeypatch.setattr(svc, "get_unsent_alerts", lambda: pending)
    monkeypatch.setattr(svc, "mark_alerts_sent", lambda ids: marked.extend(ids))

    def fake_send(body, title=None, click=None):
        sent_bodies.append((title, body))
        return send_result

    monkeypatch.setattr(svc, "send_alert", fake_send)

    return sent_bodies, marked


_PENDING = [
    {"id": 1, **_make_internship("Acme", "SWE Intern", url="https://a/1")},
    {"id": 2, **_make_internship("Globex", "ML Intern", url="https://g/2")},
]

def test_no_quiet_hours_window():
    """Alerts go out 24/7 - quiet hours are the phone's job now."""

    assert not hasattr(svc, "in_texting_window")


def test_each_role_is_its_own_notification(monkeypatch):

    sent, marked = _patch_pending(monkeypatch, _PENDING)
    summary = {"sms_sent": 0, "alerts_held": 0}

    svc._send_pending_alerts(summary)

    assert sent == [
        ("Acme - SWE Intern", "https://a/1\n(Remote)"),
        ("Globex - ML Intern", "https://g/2\n(Remote)"),
    ]
    assert marked == [1, 2]
    assert summary["sms_sent"] == 2


def test_failed_send_keeps_alerts_queued(monkeypatch):

    sent, marked = _patch_pending(monkeypatch, _PENDING, send_result=False)
    summary = {"sms_sent": 0, "alerts_held": 0}

    svc._send_pending_alerts(summary)

    assert len(sent) == 2
    assert marked == []
    assert summary["alerts_held"] == 2


def test_baseline_marks_queued_alerts_sent_without_sending(monkeypatch):

    sent, marked = _patch_pending(monkeypatch, _PENDING)
    summary = {"sms_sent": 0, "alerts_held": 0}

    svc._baseline_pending_alerts(summary)

    assert sent == []
    assert marked == [1, 2]
    assert summary["alerts_baselined"] == 2


def test_run_monitor_baseline_never_sends(monkeypatch):

    monkeypatch.setattr(svc, "create_database", lambda: None)
    monkeypatch.setattr(svc, "load_enabled_companies", lambda: [])

    sent, marked = _patch_pending(monkeypatch, _PENDING)

    summary = svc.run_monitor(baseline=True)

    assert sent == []
    assert marked == [1, 2]
    assert summary["sms_sent"] == 0


def _empty_summary():
    return {
        "companies_successful": 0, "companies_failed": 0,
        "companies_skipped": 0, "jobs_retrieved": 0,
        "internships_matched": 0, "new_internships_inserted": 0,
        "existing_internships_skipped": 0, "alerts_created": 0,
        "alerts_skipped_non_us": 0, "locations_resolved": 0,
        "unknown_location_companies": set(),
    }


def _run_with(monkeypatch, company, internships, resolved=""):
    """Run _run_all_companies against stubbed DB/lookups; returns
    (alerts created, location updates, lookups attempted, summary)."""

    alerts, updates, lookups = [], [], []

    monkeypatch.setattr(
        svc, "upsert_internship",
        lambda **kw: {"is_new": True, "dedup_key": kw["title"]}
    )

    def fake_alert(company, title, location, role_type, application_url=""):
        alerts.append((title, location))
        return {"role_type": role_type}

    monkeypatch.setattr(svc, "create_alert_for_new_internship", fake_alert)
    monkeypatch.setattr(
        svc, "update_internship_location",
        lambda key, loc: updates.append((key, loc))
    )

    def fake_resolve(company_row, internship, browser=None):
        lookups.append(internship["title"])
        return resolved

    monkeypatch.setattr(svc, "_resolve_location", fake_resolve)

    summary = _empty_summary()

    svc._run_all_companies(
        [company], {company["platform"]: lambda c: internships}, summary
    )

    return alerts, updates, lookups, summary


def _job(title, location, role_type="SWE"):
    return {
        "company": "Acme", "title": title, "location": location,
        "role_type": role_type, "application_url": f"https://acme/{title}",
    }


def test_non_us_postings_do_not_alert(monkeypatch):

    alerts, _, lookups, summary = _run_with(
        monkeypatch,
        {"company": "Acme", "platform": "workday"},
        [
            _job("SWE Intern A", "Boca Raton, FL"),
            _job("SWE Intern B", "Suzhou, China"),
        ],
    )

    assert alerts == [("SWE Intern A", "Boca Raton, FL")]
    assert lookups == []
    assert summary["alerts_skipped_non_us"] == 1


def test_unknown_location_resolved_from_posting(monkeypatch):

    alerts, updates, lookups, summary = _run_with(
        monkeypatch,
        {"company": "Acme", "platform": "custom"},
        [_job("SWE Intern", "Unknown")],
        resolved="Verona, WI, US",
    )

    assert lookups == ["SWE Intern"]
    assert updates == [("SWE Intern", "Verona, WI, US")]
    assert alerts == [("SWE Intern", "Verona, WI, US")]
    assert summary["locations_resolved"] == 1
    assert summary["unknown_location_companies"] == set()


def test_unknown_location_resolved_to_non_us_is_dropped(monkeypatch):

    alerts, _, _, summary = _run_with(
        monkeypatch,
        {"company": "Acme", "platform": "workday"},
        [_job("SWE Intern", "4 Locations")],
        resolved="London, United Kingdom; Utrecht, Holland",
    )

    assert alerts == []
    assert summary["alerts_skipped_non_us"] == 1


def test_still_unknown_location_alerts_and_is_reported(monkeypatch):

    alerts, updates, _, summary = _run_with(
        monkeypatch,
        {"company": "Acme", "platform": "custom"},
        [_job("SWE Intern", "Unknown")],
        resolved="",
    )

    assert alerts == [("SWE Intern", "Unknown")]
    assert updates == []
    assert summary["unknown_location_companies"] == {"Acme"}


def test_no_lookup_for_non_target_roles(monkeypatch):

    _, _, lookups, _ = _run_with(
        monkeypatch,
        {"company": "Acme", "platform": "custom"},
        [_job("Marketing Intern", "Unknown", role_type="Other")],
    )

    assert lookups == []


