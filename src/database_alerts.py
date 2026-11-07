import sqlite3
from datetime import datetime, timedelta

from database_setup import DB_PATH


def save_alert(
    company,
    title,
    location,
    application_url="",
    db_path=DB_PATH,
    source="monitor",
    sent=False,
):
    """
    Save an alert as not-yet-sent. It's sent (and marked sent) by the
    next run of its source. sent=True records it as already sent (used
    by Simplify's --baseline, so later dedupe still sees it).
    """

    conn = sqlite3.connect(db_path)

    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO alerts (
        timestamp,
        company,
        title,
        location,
        application_url,
        sms_sent,
        source
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        str(datetime.now()),
        company,
        title,
        location,
        application_url,
        1 if sent else 0,
        source,
    ))

    conn.commit()
    conn.close()

    print(
        f"Alert saved ({source}): {company}"
    )


def was_recently_texted(company, title, days=14, db_path=DB_PATH):
    """
    True if I was already texted about this company + title in the last
    `days` days. Companies often repost the same role under a new req id
    (or one per location), which would otherwise text me again.
    Unsent alerts don't count, so same-run duplicates still go out
    together, grouped into one entry in the text.
    """

    cutoff = str(datetime.now() - timedelta(days=days))

    conn = sqlite3.connect(db_path)

    row = conn.execute(
        """
        SELECT 1 FROM alerts
        WHERE company = ? COLLATE NOCASE
          AND TRIM(title) = TRIM(?) COLLATE NOCASE
          AND sms_sent = 1
          AND timestamp >= ?
        LIMIT 1
        """,
        (company, title, cutoff)
    ).fetchone()

    conn.close()

    return row is not None


def has_recent_alert(company, title, days=14, db_path=DB_PATH):
    """
    True if ANY alert (sent or still queued, from either source) exists
    for this company + title in the last `days` days. Simplify uses this
    to skip roles the career-site monitor already alerted on (and vice
    versa, the monitor's was_recently_texted sees Simplify's rows).
    Case- and surrounding-whitespace-insensitive.
    """

    cutoff = str(datetime.now() - timedelta(days=days))

    conn = sqlite3.connect(db_path)

    row = conn.execute(
        """
        SELECT 1 FROM alerts
        WHERE company = ? COLLATE NOCASE
          AND TRIM(title) = TRIM(?) COLLATE NOCASE
          AND timestamp >= ?
        LIMIT 1
        """,
        (company.strip(), title, cutoff)
    ).fetchone()

    conn.close()

    return row is not None


def get_unsent_alerts(db_path=DB_PATH, source="monitor"):

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT id, company, title, location, application_url
        FROM alerts
        WHERE sms_sent = 0 AND source = ?
        ORDER BY id
        """,
        (source,)
    ).fetchall()

    conn.close()

    return [dict(row) for row in rows]


def mark_alerts_sent(alert_ids, db_path=DB_PATH):

    conn = sqlite3.connect(db_path)

    conn.executemany(
        "UPDATE alerts SET sms_sent = 1 WHERE id = ?",
        [(alert_id,) for alert_id in alert_ids]
    )

    conn.commit()
    conn.close()
