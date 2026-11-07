import streamlit as st
import sqlite3
import pandas as pd

from company_registry_loader import COMPANY_REGISTRY_PATH
from database_setup import DB_PATH
from role_classifier import TARGET_ROLES, is_ineligible

# Allowlist for load_table - never build SQL from unvalidated input.
ALLOWED_TABLES = {"internships", "alerts"}


@st.cache_data
def load_table(table_name):

    if table_name not in ALLOWED_TABLES:
        raise ValueError(f"Unknown table: {table_name}")

    conn = sqlite3.connect(DB_PATH)

    query = f"SELECT * FROM {table_name}"

    if table_name == "internships":
        query += " WHERE is_active = 1"

    if table_name == "alerts":
        query += " ORDER BY timestamp DESC"

    df = pd.read_sql(
        query,
        conn
    )

    conn.close()

    return df


st.set_page_config(
    page_title="Job Agent",
    layout="wide"
)

# =====================================
# SIDEBAR
# =====================================

if st.sidebar.button("Refresh Data"):
    st.cache_data.clear()
    st.rerun()

# =====================================
# TITLE
# =====================================

st.title(
    "Job Agent"
)

# =====================================
# DATA
# =====================================

internships_df = load_table(
    "internships"
)

alerts_df = load_table(
    "alerts"
)

companies_df = pd.read_csv(
    COMPANY_REGISTRY_PATH
)

# =====================================
# METRICS
# =====================================

col1, col2, col3 = st.columns(3)

col1.metric(
    "Internships",
    len(internships_df)
)

col2.metric(
    "Alerts",
    len(alerts_df)
)

col3.metric(
    "Companies",
    len(companies_df)
)

# =====================================
# TABS
# =====================================

tab1, tab2, tab3 = st.tabs([
    "Internships",
    "Alerts",
    "Companies"
])

# =====================================
# INTERNSHIPS
# =====================================

with tab1:

    st.header(
        "Internships"
    )

    search_term = st.text_input(
        "Search company, title, location, or role type"
    )

    only_my_roles = st.checkbox(
        f"Only my roles ({', '.join(sorted(TARGET_ROLES))}, no PhD/Master's)",
        value=True
    )

    internships = internships_df.copy()

    if only_my_roles:

        internships = internships[
            internships["role_type"].isin(TARGET_ROLES)
            & ~internships["title"].apply(is_ineligible)
        ]

    if search_term:

        searchable_columns = [
            "company",
            "title",
            "location",
            "role_type"
        ]

        mask = pd.Series(False, index=internships.index)

        for column in searchable_columns:

            if column in internships.columns:

                mask |= internships[column].astype(str).str.contains(
                    search_term,
                    case=False,
                    na=False
                )

        internships = internships[mask]

    if len(internships) == 0:

        st.info("No internships match your search.")

    else:

        st.dataframe(
            internships,
            width="stretch",
            column_config={
                "application_url": st.column_config.LinkColumn(
                    "Apply",
                    display_text="Apply →"
                )
            }
        )

# =====================================
# ALERTS
# =====================================

with tab2:

    st.header(
        "Alerts"
    )

    alerts = alerts_df.copy()

    if len(alerts) == 0:

        st.info("No alerts yet. Alerts appear here as new matching internships are discovered.")

    else:

        st.dataframe(
            alerts[["timestamp", "company", "title", "location"]],
            width="stretch"
        )

# =====================================
# COMPANIES
# =====================================

with tab3:

    st.header(
        "Companies"
    )

    st.dataframe(
        companies_df,
        width="stretch"
    )
