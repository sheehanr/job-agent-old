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

    assert sms_alerts.send_alert("hello", title="x") is True
    assert sms_calls == ["hello"]


def test_long_ntfy_body_is_trimmed_to_fit(monkeypatch):

    _clear_env(monkeypatch)
    monkeypatch.setenv("NTFY_TOPIC", "alerts")

    posts = _capture_ntfy(monkeypatch)

    body = "\n".join(
        f"https://example.com/job/{i:05d}/some-long-posting-slug"
        for i in range(500)
    )

    assert sms_alerts.send_alert(body) is True

    sent = posts[0]["data"]

    assert len(sent) <= sms_alerts.NTFY_MAX_BYTES
    assert sent.decode().startswith("https://example.com/job/00000/")
    assert sent.decode().endswith("see the dashboard.")
