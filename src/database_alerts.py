import sqlite3
from datetime import datetime, timedelta

from database_setup import DB_PATH


def save_alert(
    company,
    title,
    location,
    application_url="",
    db_path=DB_PATH
):
    """
    Save an alert as not-yet-texted. It's sent (and marked sent) by the
    next monitor run.
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
        sms_sent
    )
    VALUES (?, ?, ?, ?, ?, 0)
    """, (
        str(datetime.now()),
        company,
        title,
        location,
        application_url
    ))

    conn.commit()
    conn.close()

    print(
        f"Alert saved: {company}"
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
        WHERE company = ? AND title = ? AND sms_sent = 1
          AND timestamp >= ?
        LIMIT 1
        """,
        (company, title, cutoff)
    ).fetchone()

    conn.close()

    return row is not None


def get_unsent_alerts(db_path=DB_PATH):

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT id, company, title, location, application_url
        FROM alerts
        WHERE sms_sent = 0
        ORDER BY id
        """
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
