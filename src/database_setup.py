import sqlite3
from datetime import datetime

DB_PATH = "database/internship_agent.db"


def _column_names(cursor, table):

    cursor.execute(f"PRAGMA table_info({table})")

    return {row[1] for row in cursor.fetchall()}


def _table_exists(cursor, table):

    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    )

    return cursor.fetchone() is not None


def create_database(db_path=DB_PATH):
    """
    Create (or migrate) the SQLite schema. Safe to call repeatedly -
    existing rows are preserved and missing columns are added in place
    rather than dropping and recreating tables.
    """

    conn = sqlite3.connect(db_path)

    cursor = conn.cursor()

    # Leftovers from the old CSV-seeded multi-user setup. Companies now
    # live in data/company_registry.csv and target roles in
    # role_classifier.TARGET_ROLES.
    cursor.execute("DROP TABLE IF EXISTS companies")
    cursor.execute("DROP TABLE IF EXISTS users")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS internships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        external_job_id TEXT,
        company TEXT NOT NULL,
        title TEXT NOT NULL,
        location TEXT,
        role_type TEXT,
        application_url TEXT,
        source_platform TEXT NOT NULL DEFAULT 'legacy',
        date_discovered TEXT,
        last_seen TEXT,
        is_active INTEGER NOT NULL DEFAULT 1,
        dedup_key TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        company TEXT,
        title TEXT,
        location TEXT,
        application_url TEXT,
        sms_sent INTEGER NOT NULL DEFAULT 0,
        source TEXT NOT NULL DEFAULT 'monitor'
    )
    """)

    # Simplify listing ids already processed (see simplify_alerts.py), so
    # each listing alerts at most once.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS simplify_seen (
        listing_id TEXT PRIMARY KEY,
        company TEXT,
        title TEXT,
        first_seen TEXT
    )
    """)

    conn.commit()

    _migrate_internships_table(conn, cursor)
    _migrate_alerts_table(conn, cursor)

    conn.commit()
    conn.close()

    print("Database ready (created or migrated).")


def _migrate_internships_table(conn, cursor):
    """
    If an older 'internships' table exists without the new columns
    (created via pandas to_sql(if_exists='replace') from the CSV loader),
    add the missing columns in place, preserving existing rows.
    """

    if not _table_exists(cursor, "internships"):
        return

    existing_columns = _column_names(cursor, "internships")

    if "id" not in existing_columns:
        _rebuild_legacy_internships_table(conn, cursor)
        return

    new_columns = {
        "external_job_id": "TEXT",
        "source_platform": "TEXT NOT NULL DEFAULT 'legacy'",
        "date_discovered": "TEXT",
        "last_seen": "TEXT",
        "is_active": "INTEGER NOT NULL DEFAULT 1",
        "dedup_key": "TEXT",
    }

    for column, ddl_type in new_columns.items():

        if column not in existing_columns:

            cursor.execute(
                f"ALTER TABLE internships ADD COLUMN {column} {ddl_type}"
            )

    conn.commit()

    # Backfill dedup_key for any rows that don't have one yet (legacy rows
    # loaded before the dedup key existed).
    cursor.execute(
        """
        SELECT id, external_job_id, company, title, location,
               application_url, source_platform
        FROM internships
        WHERE dedup_key IS NULL OR dedup_key = ''
        """
    )

    rows = cursor.fetchall()

    for row in rows:

        (
            row_id, external_job_id, company, title,
            location, application_url, source_platform
        ) = row

        key = _compute_dedup_key(
            source_platform or "legacy",
            company,
            title,
            location,
            application_url,
            external_job_id
        )

        cursor.execute(
            "UPDATE internships SET dedup_key = ? WHERE id = ?",
            (key, row_id)
        )

    conn.commit()

    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_internships_dedup_key "
        "ON internships(dedup_key)"
    )

    conn.commit()


def _migrate_alerts_table(conn, cursor):
    """
    Add application_url/sms_sent to an older alerts table. Existing rows
    default to sms_sent=1 - they were already texted under the old
    send-immediately behavior and must not be re-sent.
    """

    existing_columns = _column_names(cursor, "alerts")

    if "application_url" not in existing_columns:
        cursor.execute("ALTER TABLE alerts ADD COLUMN application_url TEXT")

    if "sms_sent" not in existing_columns:
        cursor.execute(
            "ALTER TABLE alerts ADD COLUMN sms_sent INTEGER NOT NULL DEFAULT 1"
        )

    # Which alert source queued the row ("monitor" or "simplify"), so each
    # one only sends its own queue. Existing rows all came from the
    # monitor.
    if "source" not in existing_columns:
        cursor.execute(
            "ALTER TABLE alerts ADD COLUMN source TEXT NOT NULL "
            "DEFAULT 'monitor'"
        )

    conn.commit()


def _rebuild_legacy_internships_table(conn, cursor):
    """
    A pre-existing internships table created via pandas
    to_sql(if_exists='replace') has no 'id' column, which SQLite cannot
    add via ALTER TABLE ADD COLUMN (it must be part of the table's
    original PRIMARY KEY definition). Rebuild the table under the new
    schema, preserving every existing row.
    """

    existing_columns = _column_names(cursor, "internships")

    cursor.execute("ALTER TABLE internships RENAME TO internships_legacy")

    cursor.execute("""
    CREATE TABLE internships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        external_job_id TEXT,
        company TEXT NOT NULL,
        title TEXT NOT NULL,
        location TEXT,
        role_type TEXT,
        application_url TEXT,
        source_platform TEXT NOT NULL DEFAULT 'legacy',
        date_discovered TEXT,
        last_seen TEXT,
        is_active INTEGER NOT NULL DEFAULT 1,
        dedup_key TEXT
    )
    """)

    def col(name):
        return name if name in existing_columns else "NULL"

    cursor.execute(f"""
        SELECT {col('company')}, {col('title')}, {col('location')},
               {col('role_type')}, {col('application_url')}
        FROM internships_legacy
    """)

    now = datetime.now().isoformat()

    for company, title, location, role_type, application_url in cursor.fetchall():

        dedup_key = _compute_dedup_key(
            "legacy", company, title, location, application_url, None
        )

        cursor.execute(
            """
            INSERT OR IGNORE INTO internships (
                external_job_id, company, title, location, role_type,
                application_url, source_platform, date_discovered,
                last_seen, is_active, dedup_key
            )
            VALUES (NULL, ?, ?, ?, ?, ?, 'legacy', ?, ?, 1, ?)
            """,
            (company, title, location, role_type, application_url,
             now, now, dedup_key)
        )

    cursor.execute("DROP TABLE internships_legacy")

    conn.commit()

    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_internships_dedup_key "
        "ON internships(dedup_key)"
    )

    conn.commit()


def _compute_dedup_key(
    source_platform,
    company,
    title,
    location,
    application_url,
    external_job_id
):

    def norm(value):
        return (value or "").strip().lower()

    if external_job_id:

        return "|".join([
            norm(source_platform),
            norm(company),
            norm(external_job_id)
        ])

    return "|".join([
        norm(company),
        norm(title),
        norm(location),
        norm(application_url)
    ])


if __name__ == "__main__":
    create_database()
