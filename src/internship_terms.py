"""
Shared definition of what counts as an internship / co-op posting.

Every adapter imports from here so the search terms and the title filter
stay in sync across platforms.
"""

import re

# Run as separate server-side searches (results are deduped by job id).
# Many ATS keyword searches don't stem or normalize punctuation, so
# "intern" alone misses e.g. J&J's "Software Engineer Coop" titles.
INTERN_SEARCH_TERMS = (
    "intern",
    "internship",
    "co-op",
    "coop",
    "co op",
    "cooperative education",
)

# Title filter. Word boundaries keep "Internal"/"International"/
# "Cooperation" out. Matches intern/interns/internship(s),
# co-op/coop/co op (+ plural), and "cooperative education".
INTERN_TITLE_RE = re.compile(
    r"\bintern(?:ship)?s?\b"
    r"|\bco[-\s]?ops?\b"
    r"|\bcooperative\s+education\b",
    re.IGNORECASE,
)


def is_internship_title(title):

    return bool(title) and INTERN_TITLE_RE.search(title) is not None
