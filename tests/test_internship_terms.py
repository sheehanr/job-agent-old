import pytest

from internship_terms import INTERN_SEARCH_TERMS, is_internship_title


def test_search_terms_cover_interns_and_coops():

    assert set(INTERN_SEARCH_TERMS) == {
        "intern", "internship", "co-op", "coop", "co op",
        "cooperative education",
    }


@pytest.mark.parametrize("title", [
    "Software Engineering Intern",
    "2027 Summer Internship - Data Science",
    "Interns - Firmware",
    "Software Engineer Co-op",
    # J&J titles co-ops with no hyphen.
    "Software Engineer Coop",
    "R&D Co-ops - Spring 2027",
    "Data Science Co Op",
    "Cooperative Education - Firmware Engineering",
    "COOP - Embedded Systems",
])
def test_internship_titles_match(title):

    assert is_internship_title(title)


@pytest.mark.parametrize("title", [
    "Internal Auditor",
    "International Trade Analyst",
    "Cooperative Purchasing Manager",
    "Co-Operations Lead",
    "Senior Software Engineer",
    "",
    None,
])
def test_non_internship_titles_do_not_match(title):

    assert not is_internship_title(title)
