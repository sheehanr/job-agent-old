import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import sms_alerts  # noqa: E402


def _clear_env(monkeypatch):
    for var in (
        "EMAIL_SENDER_ADDRESS",
        "EMAIL_APP_PASSWORD",
        "NOTIFICATION_PHONE_NUMBER",
        "SMS_CARRIER_GATEWAY",
        "NTFY_TOPIC",
        "NTFY_SERVER",
        "NTFY_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)


def test_missing_config_skips_without_error(monkeypatch):

    _clear_env(monkeypatch)

    result = sms_alerts.send_sms_alert("test message")

    assert result is False


def test_partial_config_skips(monkeypatch):

    _clear_env(monkeypatch)
    monkeypatch.setenv("EMAIL_SENDER_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("NOTIFICATION_PHONE_NUMBER", "4075551234")
    # EMAIL_APP_PASSWORD and SMS_CARRIER_GATEWAY intentionally left unset.

    result = sms_alerts.send_sms_alert("test message")

    assert result is False


def test_sends_via_smtp_when_fully_configured(monkeypatch):

    _clear_env(monkeypatch)
    monkeypatch.setenv("EMAIL_SENDER_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("EMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setenv("NOTIFICATION_PHONE_NUMBER", "4075551234")
    monkeypatch.setenv("SMS_CARRIER_GATEWAY", "tmomail.net")

    sent = {}

    class FakeSMTP:

        def __init__(self, host, port, timeout=None):
            sent["host"] = host
            sent["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            sent["starttls"] = True

        def login(self, user, password):
            sent["login"] = (user, password)

        def send_message(self, message):
            sent["message"] = message

    monkeypatch.setattr(sms_alerts.smtplib, "SMTP", FakeSMTP)

    result = sms_alerts.send_sms_alert("New internship!")

    assert result is True
    assert sent["host"] == "smtp.gmail.com"
    assert sent["login"] == ("me@gmail.com", "app-password")
    assert sent["message"]["To"] == "4075551234@tmomail.net"
    assert sent["message"]["From"] == "me@gmail.com"
    assert sent["message"].get_content().strip() == "New internship!"


def test_smtp_failure_returns_false_not_raise(monkeypatch):

    _clear_env(monkeypatch)
    monkeypatch.setenv("EMAIL_SENDER_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("EMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setenv("NOTIFICATION_PHONE_NUMBER", "4075551234")
    monkeypatch.setenv("SMS_CARRIER_GATEWAY", "tmomail.net")

    class ExplodingSMTP:

        def __init__(self, host, port, timeout=None):
            pass

        def __enter__(self):
            raise ConnectionRefusedError("boom")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(sms_alerts.smtplib, "SMTP", ExplodingSMTP)

    result = sms_alerts.send_sms_alert("New internship!")

    assert result is False


class FakeNtfyResponse:

    def __init__(self, fail=False):
        self.fail = fail

    def raise_for_status(self):
        if self.fail:
            raise RuntimeError("HTTP 500")


def _capture_ntfy(monkeypatch, fail=False):

    posts = []

    def fake_post(url, data, headers, timeout):
        posts.append({"url": url, "data": data, "headers": headers})
        return FakeNtfyResponse(fail)

    monkeypatch.setattr(sms_alerts.requests, "post", fake_post)

    return posts


def test_ntfy_used_when_topic_set(monkeypatch):

    _clear_env(monkeypatch)
    monkeypatch.setenv("NTFY_TOPIC", "my-secret-topic")
    # SMS also configured: ntfy must win, with no SMTP traffic.
    monkeypatch.setenv("EMAIL_SENDER_ADDRESS", "me@gmail.com")
    monkeypatch.setenv("EMAIL_APP_PASSWORD", "app-password")
    monkeypatch.setenv("NOTIFICATION_PHONE_NUMBER", "4075551234")
    monkeypatch.setenv("SMS_CARRIER_GATEWAY", "tmomail.net")

    def no_smtp(*args, **kwargs):
        raise AssertionError("SMTP should not be used when NTFY_TOPIC is set")

    monkeypatch.setattr(sms_alerts.smtplib, "SMTP", no_smtp)

    posts = _capture_ntfy(monkeypatch)

    body = "2 new internships found:\n\nSWE Intern - Acme\nhttps://acme.com/j/1"

    assert sms_alerts.send_alert(body, title="2 new internships") is True

    assert len(posts) == 1
    assert posts[0]["url"] == "https://ntfy.sh/my-secret-topic"
    assert posts[0]["data"].decode("utf-8") == body
    assert posts[0]["headers"]["Title"] == "2 new internships"
    assert "Authorization" not in posts[0]["headers"]


def test_ntfy_custom_server_and_token(monkeypatch):

    _clear_env(monkeypatch)
    monkeypatch.setenv("NTFY_TOPIC", "alerts")
    monkeypatch.setenv("NTFY_SERVER", "https://ntfy.example.com/")
    monkeypatch.setenv("NTFY_TOKEN", "tk_abc")

    posts = _capture_ntfy(monkeypatch)

    assert sms_alerts.send_alert("hi") is True
    assert posts[0]["url"] == "https://ntfy.example.com/alerts"
    assert posts[0]["headers"]["Authorization"] == "Bearer tk_abc"


def test_ntfy_failure_returns_false(monkeypatch):

    _clear_env(monkeypatch)
    monkeypatch.setenv("NTFY_TOPIC", "alerts")

    _capture_ntfy(monkeypatch, fail=True)

    assert sms_alerts.send_alert("hi") is False


def test_falls_back_to_sms_without_ntfy_topic(monkeypatch):

    _clear_env(monkeypatch)

    def no_ntfy(*args, **kwargs):
        raise AssertionError("ntfy should not be used without NTFY_TOPIC")

    monkeypatch.setattr(sms_alerts.requests, "post", no_ntfy)

    sms_calls = []
    monkeypatch.setattr(
        sms_alerts, "send_sms_alert",
        lambda body: sms_calls.append(body) or True
    )

    assert sms_alerts.send_alert("hello", title="Simplify: 1 new internship") is True
    # Texts have no title line, so the title goes on top of the body.
    assert sms_calls == ["Simplify: 1 new internship\n\nhello"]


def test_long_ntfy_body_is_split_never_trimmed(monkeypatch):
    """Every apply link must arrive in ntfy - a big batch becomes several
    pushes rather than being cut off."""

    _clear_env(monkeypatch)
    monkeypatch.setenv("NTFY_TOPIC", "alerts")

    posts = _capture_ntfy(monkeypatch)

    blocks = [
        f"Software Engineering Intern {i} - Company{i} (Boston, MA)\n"
        f"https://example.com/job/{i:05d}/some-long-posting-slug"
        for i in range(120)
    ]
    body = "\n\n".join(blocks)

    assert sms_alerts.send_alert(body, title="Career sites: 120 new internships")

    assert len(posts) > 1

    sent = [p["data"].decode("utf-8") for p in posts]

    for part in sent:
        assert len(part.encode("utf-8")) <= sms_alerts.NTFY_MAX_BYTES
        assert "dashboard" not in part

    # Nothing lost, nothing split mid-posting.
    assert "\n\n".join(sent) == body

    titles = [p["headers"]["Title"] for p in posts]
    assert titles[0] == f"Career sites: 120 new internships (1/{len(posts)})"
    assert titles[-1].endswith(f"({len(posts)}/{len(posts)})")


def test_failed_part_returns_false(monkeypatch):

    _clear_env(monkeypatch)
    monkeypatch.setenv("NTFY_TOPIC", "alerts")

    calls = []

    def flaky_post(url, data, headers, timeout):
        calls.append(headers["Title"])
        return FakeNtfyResponse(fail=len(calls) == 2)

    monkeypatch.setattr(sms_alerts.requests, "post", flaky_post)

    body = "\n\n".join(f"Intern {i}\nhttps://x.com/{i:04d}" + "x" * 80
                       for i in range(200))

    assert sms_alerts.send_alert(body, title="t") is False
    assert len(calls) == 2


def test_short_body_is_one_push_without_part_numbers(monkeypatch):

    _clear_env(monkeypatch)
    monkeypatch.setenv("NTFY_TOPIC", "alerts")

    posts = _capture_ntfy(monkeypatch)

    assert sms_alerts.send_alert("SWE Intern - Acme\nhttps://a/1", title="T")
    assert len(posts) == 1
    assert posts[0]["headers"]["Title"] == "T"


def test_test_alerts_send_one_of_each_type(monkeypatch):

    sent = []
    monkeypatch.setattr(
        sms_alerts, "send_alert",
        lambda body, title=None, click=None: sent.append((title, body, click)) or True
    )

    assert sms_alerts.send_test_alerts() is True

    assert [t for t, _, _ in sent] == [
        "Test 1 of 3 - Software Engineering Intern",
        "Test 2 of 3 - Embedded Software Intern",
        "Test 3 of 3 - 2 new roles",
    ]
    assert sent[0][1] == "https://github.com/sheehanr/job-agent\n(Boston, MA)"
    assert sent[0][2] == "https://github.com/sheehanr/job-agent"
    assert "(Austin, TX)\n\n" in sent[1][1]
    assert sent[2][1].startswith("ML Intern: https://github.com/sheehanr/job-agent")

    # The ntfy topic must never be in the public repo.
    for _, body, _ in sent:
        assert "ntfy.sh/" not in body
