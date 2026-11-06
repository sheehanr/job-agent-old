import sqlite3
from datetime import datetime

from database_setup import DB_PATH, _compute_dedup_key
from role_classifier import is_target_role, is_ineligible
from location_filter import is_known_non_us
from database_alerts import save_alert, was_recently_texted


def upsert_internship(
    company,
    title,
    location,
    role_type,
    application_url,
    source_platform="legacy",
    external_job_id=None,
    db_path=DB_PATH
):
    """
    Insert a new internship, or refresh last_seen/is_active on an existing
    one. Uniqueness is determined by dedup_key:
      - source_platform + company + external_job_id, when an external id
        is available (e.g. Greenhouse job id)
      - company + title + location + application_url otherwise

    Returns a dict: {"is_new": bool, "dedup_key": str}
    """

    dedup_key = _compute_dedup_key(
        source_platform,
        company,
        title,
        location,
        application_url,
        external_job_id
    )

    now = datetime.now().isoformat()

    conn = sqlite3.connect(db_path)

    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM internships WHERE dedup_key = ?",
        (dedup_key,)
    )

    existing = cursor.fetchone()

    if existing:

        cursor.execute(
            """
            UPDATE internships
            SET last_seen = ?,
                is_active = 1,
                role_type = ?,
                application_url = ?
            WHERE dedup_key = ?
            """,
            (now, role_type, application_url, dedup_key)
        )

        conn.commit()
        conn.close()

        return {"is_new": False, "dedup_key": dedup_key}

    cursor.execute(
        """
        INSERT INTO internships (
            external_job_id, company, title, location, role_type,
            application_url, source_platform, date_discovered,
            last_seen, is_active, dedup_key
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (
            external_job_id, company, title, location, role_type,
            application_url, source_platform, now, now, dedup_key
        )
    )

    conn.commit()
    conn.close()

    return {"is_new": True, "dedup_key": dedup_key}


def create_alert_for_new_internship(
    company,
    title,
    location,
    role_type,
    application_url="",
    db_path=DB_PATH
):
    """
    Create an alert for a newly discovered internship if its role_type is
    one of my target roles (see role_classifier.TARGET_ROLES), it isn't
    a grad-only or non-college posting (role_classifier.is_ineligible),
    its location isn't known to be outside the US
    (location_filter.is_known_non_us - unknown locations still alert),
    and I wasn't already texted about the same company + title recently
    (a repost). Returns None otherwise.
    """

    if not is_target_role(role_type) or is_ineligible(title):
        return None

    if is_known_non_us(location):
        return None

    if was_recently_texted(company, title, db_path=db_path):
        return None

    save_alert(
        company,
        title,
        location,
        application_url=application_url,
        db_path=db_path
    )

    return {"role_type": role_type}


def update_internship_location(dedup_key, location, db_path=DB_PATH):
    """
    Store a location looked up from the posting page. dedup_key is left
    alone, so the next run (which sees the listing's original "Unknown")
    still matches this row.
    """

    conn = sqlite3.connect(db_path)

    conn.execute(
        "UPDATE internships SET location = ? WHERE dedup_key = ?",
        (location, dedup_key)
    )

    conn.commit()
    conn.close()
