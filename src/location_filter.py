"""
Classify a posting's free-text location as US, non-US, or unknown.

Every ATS formats locations differently, e.g.
    "Boca Raton, FL"                    "USA - California – Irvine"
    "Princeton - NJ - US"               "United States - Illinois - Waukegan"
    "Augusta, Georgia, United States"   "USA UT - Sandy"
    "Suzhou, China"                     "HUN02-01-Budapest-Vaci Greens C"
    "4 Locations"                       "TARRYTOWN"
so this is a heuristic. It errs toward "unknown" rather than guessing:
unknown postings still alert (labelled), only confirmed non-US ones are
dropped.
"""

import re

US = "us"
NON_US = "non_us"
UNKNOWN = "unknown"

UNKNOWN_LOCATION_LABEL = "(location unknown)"

_US_STATES = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas",
    "CA": "california", "CO": "colorado", "CT": "connecticut",
    "DE": "delaware", "FL": "florida", "GA": "georgia", "HI": "hawaii",
    "ID": "idaho", "IL": "illinois", "IN": "indiana", "IA": "iowa",
    "KS": "kansas", "KY": "kentucky", "LA": "louisiana", "ME": "maine",
    "MD": "maryland", "MA": "massachusetts", "MI": "michigan",
    "MN": "minnesota", "MS": "mississippi", "MO": "missouri",
    "MT": "montana", "NE": "nebraska", "NV": "nevada",
    "NH": "new hampshire", "NJ": "new jersey", "NM": "new mexico",
    "NY": "new york", "NC": "north carolina", "ND": "north dakota",
    "OH": "ohio", "OK": "oklahoma", "OR": "oregon", "PA": "pennsylvania",
    "RI": "rhode island", "SC": "south carolina", "SD": "south dakota",
    "TN": "tennessee", "TX": "texas", "UT": "utah", "VT": "vermont",
    "VA": "virginia", "WA": "washington", "WV": "west virginia",
    "WI": "wisconsin", "WY": "wyoming", "DC": "district of columbia",
    "PR": "puerto rico",
}

# Explicit country markers. "US" is matched case-sensitively below so the
# English word "us" doesn't count.
_US_COUNTRY_RE = re.compile(
    r"\bunited states\b|\busa\b|\bu\.s\.a?\.?(?=\W|$)",
    re.IGNORECASE,
)
_US_TOKEN_RE = re.compile(r"(?<![A-Za-z])US(?![A-Za-z])")

_STATE_NAME_RE = re.compile(
    r"\b(?:" + "|".join(sorted(map(re.escape, _US_STATES.values()),
                               key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

# Two-letter state codes only count as standalone uppercase tokens
# ("Boca Raton, FL", "Princeton - NJ - US", "USA UT - Sandy"), so "IN" /
# "OR" / "ME" in ordinary words don't fire.
_STATE_CODE_RE = re.compile(
    r"(?<![A-Za-z])(?:" + "|".join(_US_STATES) + r")(?![A-Za-z])"
)

# Countries and non-US states/provinces, checked BEFORE US states (so
# "Toronto, ON, CA" isn't read as California). "Georgia" and "Jersey"
# are deliberately absent - they collide with US states.
_NON_US_COUNTRIES = [
    "afghanistan", "albania", "algeria", "argentina", "armenia",
    "australia", "austria", "azerbaijan", "bahrain", "bangladesh",
    "belarus", "belgium", "bolivia", "bosnia", "brazil", "brasil",
    "bulgaria", "cambodia", "cameroon", "canada", "chile", "china",
    "colombia", "costa rica", "croatia", "cyprus", "czech", "czechia",
    "denmark", "dominican republic", "ecuador", "egypt", "el salvador",
    "england", "estonia", "ethiopia", "finland", "france", "deutschland",
    "germany", "ghana", "greece", "guatemala", "honduras", "hong kong",
    "hungary", "iceland", "india", "indonesia", "iran", "iraq",
    "ireland", "israel", "italy", "italia", "jamaica", "japan", "jordan",
    "kazakhstan", "kenya", "korea", "kuwait", "latvia", "lebanon",
    "lithuania", "luxembourg", "malaysia", "malta", "mexico", "méxico",
    "morocco", "netherlands", "holland", "new zealand", "nicaragua",
    "nigeria", "norway", "oman", "pakistan", "panama", "paraguay",
    "peru", "philippines", "poland", "polska", "portugal", "qatar",
    "romania", "russia", "saudi arabia", "scotland", "serbia",
    "singapore", "slovakia", "slovenia", "south africa", "spain",
    "españa", "sri lanka", "sweden", "switzerland", "schweiz", "taiwan",
    "thailand", "tunisia", "turkey", "türkiye", "turkiye", "ukraine",
    "united arab emirates", "uae", "united kingdom", "uk", "uruguay",
    "venezuela", "vietnam", "viet nam", "wales",
    "ontario", "quebec", "québec", "british columbia", "alberta",
    "bavaria", "hesse", "ile de france", "île-de-france", "selangor",
    "latin america", "latam", "emea", "apac", "europe", "asia pacific",
]

# Non-US cities that often appear with no country attached. Checked
# AFTER US states, so "London, KY" or "Lima, OH" stay US.
_NON_US_CITIES = [
    "bengaluru", "bangalore", "hyderabad", "pune", "chennai", "mumbai",
    "gurgaon", "gurugram", "noida", "shanghai", "suzhou", "beijing",
    "shenzhen", "guangzhou", "chengdu", "tokyo", "osaka", "seoul",
    "taipei", "penang", "kuala lumpur", "selangor", "kulim", "johor",
    "ho chi minh", "manila", "bangkok", "jakarta", "sydney",
    "melbourne", "toronto", "mississauga", "montreal",
    "montréal", "vancouver", "calgary", "mexico city", "ciudad de mexico",
    "cuidad de mexico", "tijuana", "juarez", "juárez", "guadalajara",
    "monterrey", "heredia", "alajuela", "cartago", "london",
    "galway", "limerick", "cork", "amsterdam", "eindhoven", "utrecht",
    "rotterdam", "paris", "lyon", "munich", "münchen", "berlin",
    "frankfurt", "hamburg", "erlangen", "forchheim", "freiburg",
    "milano", "milan", "madrid", "barcelona", "zurich", "zürich",
    "basel", "geneva", "vienna", "wien", "budapest", "warsaw",
    "krakow", "kraków", "prague", "brno", "stockholm", "copenhagen",
    "oslo", "helsinki", "brussels", "lisbon", "tel aviv", "dubai",
    "riyadh", "sao paulo", "são paulo", "buenos aires", "bogota",
    "bogotá", "santiago", "lima",
]


def _place_re(places):

    return re.compile(
        r"(?<![\w])(?:"
        + "|".join(sorted(map(re.escape, places), key=len, reverse=True))
        + r")(?![\w])",
        re.IGNORECASE,
    )


_NON_US_COUNTRY_RE = _place_re(_NON_US_COUNTRIES)
_NON_US_CITY_RE = _place_re(_NON_US_CITIES)

# Canadian province codes as standalone uppercase tokens.
_CA_PROVINCE_CODE_RE = re.compile(
    r"(?<![A-Za-z])(?:ON|QC|BC|AB|MB|SK|NS|NB|NL|PE)(?![A-Za-z])"
)

# ISO 3166 alpha-3 country codes as standalone uppercase tokens, as in
# Merck's "NLD - North Brabant - Boxmeer" / "USA - New Jersey - Rahway".
_ISO3_NON_US_RE = re.compile(
    r"(?<![A-Za-z])(?:"
    "ARE|ARG|AUS|AUT|BEL|BGR|BRA|CAN|CHE|CHL|CHN|COL|CRI|CZE|DEU|DNK|"
    "DOM|ECU|EGY|ESP|EST|FIN|FRA|GBR|GRC|GTM|HKG|HRV|HUN|IDN|IND|IRL|"
    "ISR|ITA|JPN|KOR|LTU|LVA|MEX|MYS|NLD|NOR|NZL|PAN|PER|PHL|POL|PRT|"
    "ROU|SAU|SGP|SRB|SVK|SVN|SWE|THA|TUR|TWN|UKR|URY|VNM|ZAF"
    r")(?![A-Za-z])"
)

# A trailing ISO alpha-2 country code, as in Boston Scientific's
# "Plaza Roble, Escazú, CR" / "Maple Grove, MN, US, 55311". Codes that
# double as US state abbreviations (CA, DE, IN, IL, CO, MA, PA, ...)
# are left out - those fall through to the state check.
_TRAILING_ISO2_NON_US_RE = re.compile(
    r",\s*(?:"
    "AE|AT|AU|BE|BR|CH|CL|CN|CR|CZ|DK|EG|ES|FI|FR|GB|GR|HK|HU|IE|IT|JP|"
    "KR|MX|MY|NL|NO|NZ|PE|PH|PL|PT|RO|SE|SG|SK|TH|TR|TW|UA|UK|VN|ZA"
    r")(?:\s*,\s*[\w -]+)?\s*$"
)

# GE HealthCare-style site codes: "HUN02-01-Budapest...", "USA12-...".
_SITE_CODE_RE = re.compile(r"^([A-Z]{3})\d{2}-")

_UNKNOWN_RE = re.compile(
    r"^\s*(?:|unknown|n/?a|tbd|remote|hybrid|various|multiple locations|"
    r"\d+\s+locations?)\s*$",
    re.IGNORECASE,
)

_SEGMENT_SPLIT_RE = re.compile(r"\s*(?:;|\||\n|\s/\s)\s*")


def _classify_segment(segment):

    if _UNKNOWN_RE.match(segment):
        return UNKNOWN

    site_code = _SITE_CODE_RE.match(segment.strip())

    if site_code:
        return US if site_code.group(1) == "USA" else NON_US

    if _US_COUNTRY_RE.search(segment) or _US_TOKEN_RE.search(segment):
        return US

    # "New Mexico" must not trip the "mexico" country check.
    without_new_mexico = re.sub(r"\bnew mexico\b", "", segment,
                                flags=re.IGNORECASE)

    if (
        _NON_US_COUNTRY_RE.search(without_new_mexico)
        or _CA_PROVINCE_CODE_RE.search(segment)
        or _ISO3_NON_US_RE.search(segment)
        or _TRAILING_ISO2_NON_US_RE.search(segment)
    ):
        return NON_US

    if _STATE_NAME_RE.search(segment) or _STATE_CODE_RE.search(segment):
        return US

    if _NON_US_CITY_RE.search(segment):
        return NON_US

    return UNKNOWN


def classify_location(location):
    """
    Returns "us", "non_us" or "unknown" for a free-text location.

    Multi-location strings ("Boston, MA; Toronto, Canada") count as US
    if any part is in the US - I can still apply to the US opening.
    """

    if location is None:
        return UNKNOWN

    text = str(location).strip()

    if not text:
        return UNKNOWN

    results = {_classify_segment(part) for part in _SEGMENT_SPLIT_RE.split(text)}

    if US in results:
        return US

    if NON_US in results:
        return NON_US

    return UNKNOWN


def is_us_location(location):

    return classify_location(location) == US


def is_known_non_us(location):

    return classify_location(location) == NON_US
