import os
import smtplib
from email.message import EmailMessage

import requests
from dotenv import load_dotenv

load_dotenv()

NTFY_DEFAULT_SERVER = "https://ntfy.sh"

# ntfy.sh turns messages over 4096 bytes into a file attachment instead of
# showing them in the notification, so long batches are trimmed to fit.
NTFY_MAX_BYTES = 4000


def send_alert(body, title="New internships"):
    """
    Send one phone alert for this run. Uses an ntfy.sh push when
    NTFY_TOPIC is set, otherwise falls back to the email-to-SMS text.

    Returns True only if a message was actually delivered, so callers can
    leave alerts queued for the next run on False.
    """

    if os.environ.get("NTFY_TOPIC", "").strip():
        return send_ntfy_alert(body, title=title)

    return send_sms_alert(body)


def _fit_ntfy_body(body, limit=NTFY_MAX_BYTES):

    if len(body.encode("utf-8")) <= limit:
        return body

    footer = "\n\n...more new postings - see the dashboard."
    budget = limit - len(footer.encode("utf-8"))

    kept = []
    used = 0

    for line in body.split("\n"):

        size = len(line.encode("utf-8")) + 1

        if used + size > budget:
            break

        kept.append(line)
        used += size

    return "\n".join(kept) + footer


def send_ntfy_alert(body, title="New internships"):
    """
    Push via ntfy.sh (https://ntfy.sh): install the ntfy app, subscribe
    to NTFY_TOPIC, and every POST to https://ntfy.sh/<topic> shows up as
    a notification. Anyone who knows the topic name can read it, so use
    a long random one. NTFY_SERVER overrides the server for self-hosted
    ntfy; NTFY_TOKEN adds an access token if the topic is protected.
    """

    topic = os.environ.get("NTFY_TOPIC", "").strip()

    if not topic:
        print("ntfy alerts not configured (NTFY_TOPIC unset). Skipping.")
        return False

    server = (
        os.environ.get("NTFY_SERVER", "").strip() or NTFY_DEFAULT_SERVER
    ).rstrip("/")

    headers = {
        # HTTP headers must be latin-1; titles are plain ASCII anyway.
        "Title": title.encode("ascii", "ignore").decode(),
        "Priority": "default",
    }

    token = os.environ.get("NTFY_TOKEN", "").strip()

    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:

        response = requests.post(
            f"{server}/{topic}",
            data=_fit_ntfy_body(body).encode("utf-8"),
            headers=headers,
            timeout=15,
        )
        response.raise_for_status()

    except Exception as e:
        print(f"Failed to send ntfy alert: {e}")
        return False

    # Don't print the topic - in a public repo's Actions log it would let
    # anyone subscribe to my alerts.
    print("ntfy push alert sent.")

    return True


def send_sms_alert(body):
    """
    Send an SMS alert via an email-to-SMS carrier gateway (e.g. Verizon's
    number@vtext.com, T-Mobile's number@tmomail.net) if configured.

    Returns True if a message was sent, False if SMS is not configured
    (this is optional - internship discovery works without it).
    """

    sender_address = os.environ.get("EMAIL_SENDER_ADDRESS")
    sender_app_password = os.environ.get("EMAIL_APP_PASSWORD")
    phone_number = os.environ.get("NOTIFICATION_PHONE_NUMBER")
    carrier_gateway = os.environ.get("SMS_CARRIER_GATEWAY")

    if not all(
        [sender_address, sender_app_password, phone_number, carrier_gateway]
    ):
        print("SMS alerts not configured (missing env vars). Skipping.")
        return False

    to_address = f"{phone_number}@{carrier_gateway}"

    message = EmailMessage()
    message["From"] = sender_address
    message["To"] = to_address
    message["Subject"] = ""
    message.set_content(body)

    try:

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as smtp:

            smtp.starttls()
            smtp.login(sender_address, sender_app_password)
            smtp.send_message(message)

    except Exception as e:
        print(f"Failed to send SMS alert: {e}")
        return False

    print(f"SMS alert sent to {to_address}")

    return True


if __name__ == "__main__":
    import sys

    delivered = send_alert(
        "Internship Radar test - if you can read this, phone alerts work.\n"
        "https://github.com/sheehanr/internship-radar",
        title="Test alert",
    )

    # Non-zero exit so a misconfigured secret fails the workflow step.
    sys.exit(0 if delivered else 1)
