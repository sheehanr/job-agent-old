import pytest

from location_filter import classify_location, US, NON_US, UNKNOWN


@pytest.mark.parametrize("location", [
    "Boca Raton, FL",
    "Redmond, Washington",
    "United States - Illinois - Waukegan",
    "USA - California – Irvine",
    "USA UT - Sandy",
    "Princeton - NJ - US",
    "Cambridge Crossing - MA - US",
    "Indianapolis - RayzeBio - IN",
    "Augusta, Georgia, United States",
    "State of Colorado, United States of America",
    "US-Maryland-Hunt Valley",
    "Remote - US",
    "Remote, USA",
    "Albuquerque, New Mexico",
    "London, KY",
    "Juncos, Puerto Rico",
    # Multi-location: any US part counts.
    "Boston, MA; Toronto, Canada",
    "TARRYTOWN, United States of America",
    "USA - New Jersey - Rahway",
    "Maple Grove, MN, US, 55311",
    # State codes that are also country codes stay US.
    "Irvine, CA",
    "Newark, DE",
])
def test_us_locations(location):

    assert classify_location(location) == US


@pytest.mark.parametrize("location", [
    "Suzhou, China",
    "Penang, Malaysia",
    "Milano",
    "Mexico - Cuidad de Mexico - Cuidad de Mexico",
    "Malaysia > Selangor : Imazium, No. 8, Jalan SS 21/37",
    "Singapore Affiliate - Duo Tower",
    "HUN02-01-Budapest-Vaci Greens C",
    "IND19-01-Bengaluru-EPIP 122 (Phase II)",
    "Toronto, ON, CA",
    "London, United Kingdom; Utrecht, Holland; Frankfurt, Hesse",
    "Remote, Canada",
    "Latin America",
    "Germany - Freiburg",
    # ISO alpha-3 prefixes (Merck) and trailing alpha-2 codes (Boston
    # Scientific, Arthrex).
    "NLD - North Brabant - Boxmeer",
    "Plaza Roble, Escazú, H, CR",
    "American Free Zone, San Franci, CR",
    "São Paulo, BR",
])
def test_non_us_locations(location):

    assert classify_location(location) == NON_US


@pytest.mark.parametrize("location", [
    None, "", "Unknown", "Remote", "4 Locations", "Multiple Locations",
    "TARRYTOWN", "NTN GR",
])
def test_unknown_locations(location):

    assert classify_location(location) == UNKNOWN


def test_state_codes_must_be_uppercase_tokens():
    """"in"/"or"/"me" inside ordinary words or lowercase text don't count
    as Indiana/Oregon/Maine."""

    assert classify_location("Building in the main campus") == UNKNOWN
