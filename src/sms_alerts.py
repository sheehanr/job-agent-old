import os
import smtplib
from email.message import EmailMessage

import requests
from dotenv import load_dotenv

load_dotenv()

NTFY_DEFAULT_SERVER = "https://ntfy.sh"

# ntfy.sh turns messages over 4096 bytes into a file attachment instead of
# showing them in the notification, so a long batch is split across
# several pushes - never trimmed, so every apply link always arrives.
NTFY_MAX_BYTES = 4000


def send_alert(body, title="New internships", click=None):
    """
    Send one phone alert for this run. Uses an ntfy.sh push when
    NTFY_TOPIC is set, otherwise falls back to the email-to-SMS text.

    Returns True only if a message was actually delivered, so callers can
    leave alerts queued for the next run on False.
    """

    if os.environ.get("NTFY_TOPIC", "").strip():
        return send_ntfy_alert(body, title=title, click=click)

    # A text has no separate title line, so put it at the top.
    return send_sms_alert(f"{title}\n\n{body}" if title else body)


def _utf8_len(text):

    return len(text.encode("utf-8"))


def split_ntfy_body(body, limit=NTFY_MAX_BYTES):
    """
    Split a message into chunks that each fit in one ntfy push. Splits
    between postings (blank-line-separated blocks), falling back to
    between lines for a single oversized block, so a posting's title and
    apply link are never cut apart mid-line. Nothing is dropped.
    """

    if _utf8_len(body) <= limit:
        return [body]

    pieces = []

    for block in body.split("\n\n"):

        if _utf8_len(block) <= limit:
            pieces.append(block)
        else:
            pieces.extend(block.split("\n"))

    chunks = []
    current = ""

    for piece in pieces:

        candidate = f"{current}\n\n{piece}" if current else piece

        if current and _utf8_len(candidate) > limit:
            chunks.append(current)
            current = piece
        else:
            current = candidate

    if current:
        chunks.append(current)

    return chunks


def send_ntfy_alert(body, title="New internships", click=None):
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

    if click:
        # Tapping the notification opens this link (the apply page).
        headers["Click"] = click

    token = os.environ.get("NTFY_TOKEN", "").strip()

    if token:
        headers["Authorization"] = f"Bearer {token}"

    chunks = split_ntfy_body(body)

    for number, chunk in enumerate(chunks, 1):

        part_headers = dict(headers)

        if len(chunks) > 1:
            part_headers["Title"] = f"{headers['Title']} ({number}/{len(chunks)})"

        try:

            response = requests.post(
                f"{server}/{topic}",
                data=chunk.encode("utf-8"),
                headers=part_headers,
                timeout=15,
            )
            response.raise_for_status()

        except Exception as e:
            # The whole batch stays queued and is resent next run, so a
            # partial failure can repeat earlier parts - but never loses
            # a link.
            print(f"Failed to send ntfy alert (part {number}): {e}")
            return False

    # Don't print the topic - in a public repo's Actions log it would let
    # anyone subscribe to my alerts.
    print(f"ntfy push alert sent ({len(chunks)} part(s)).")

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

    from alert_message import build_notifications

    # A sample posting, sent exactly the way a real alert is formatted.
    [note] = build_notifications([{
        "id": 0,
        "company": "Job Agent test",
        "title": "Software Engineering Intern",
        "location": "Boston, MA",
        "application_url": "https://github.com/sheehanr/job-agent",
    }])

    delivered = send_alert(note["body"], title=note["title"], click=note["click"])

    # Non-zero exit so a misconfigured secret fails the workflow step.
    sys.exit(0 if delivered else 1)
