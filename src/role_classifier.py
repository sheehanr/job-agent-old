import re

# Ordered (most specific / most easily confused with SWE first). The first
# category whose keyword appears in the title wins - order is deliberate,
# e.g. "Robotics Software Intern" must classify as Robotics, not SWE, and
# "Product Management Intern" must not classify as SWE just because it's
# a technical internship.
ROLE_KEYWORDS = [
    ("Product", [
        "product management",
        "product manager",
        "product management intern",
    ]),
    ("Cybersecurity", [
        "cybersecurity",
        "cyber security",
        "security engineer",
        "security analyst",
        "infosec",
        "application security",
    ]),
    ("Robotics", [
        "robotics",
        "robot",
        "autonomy",
        "autonomous",
        "mechatronics",
        "unmanned",
        "guidance navigation",
        "inertial navigation",
        "gnc",
    ]),
    ("ML", [
        "machine learning",
        "artificial intelligence",
        "ai engineer",
        "ai research",
        "ai safety",
        "computer vision",
        "deep learning",
        "nlp",
        "ml engineer",
        "ml research",
        "ai/ml",
        "ai-ml",
    ]),
    ("Embedded", [
        "embedded",
        "rtos",
        "cyber physical",
        "cyber-physical",
    ]),
    ("Firmware", [
        "firmware",
    ]),
    ("Hardware", [
        "hardware",
        "fpga",
        "asic",
        "rtl",
        "verilog",
        "vhdl",
        "vlsi",
        "digital design",
        "microelectronics",
        "semiconductor",
        "chip design",
        "electrical engineer",
        "computer engineer",
        "rf engineer",
        "radar",
        "microwave",
        "signal processing",
        "dsp",
        "avionics",
    ]),
    ("SWE", [
        "software engineer",
        "software engineering",
        "software development",
        "software quality assurance",
        "quality assurance engineer",
        "full stack",
        "fullstack",
        "backend",
        "back end",
        "frontend",
        "front end",
        "web developer",
        "application developer",
        "devops",
        "computer scientist",
        "sw developer",
        "sw engineer",
        # Catch-all for titles like "Software/Network Engineering Intern"
        # or "Software Developer Intern" - keep it last.
        "software",
    ]),
    ("Data", [
        "data science",
        "data scientist",
        "data engineering",
        "data engineer",
        "data analytics",
        "data analyst",
        "bioinformatics",
    ]),
]

# Broad tech-department words. They only count when the title has no
# business-function word (see _NON_CS_RE), so "Digital Marketing Intern"
# and "Pricing & Commercial Analytics Intern" stay Other while "Digital
# Health Intern" and "AI & Analytics Analyst" match. Checked after
# everything above, so "Digital Design" (EE) stays Hardware.
BROAD_ROLE_KEYWORDS = [
    ("Data", [
        "analytics",
        "informatics",
    ]),
    ("SWE", [
        "information technology",
        "information systems",
        "digital",
    ]),
]

# Business functions that make a broad-keyword title a non-CS role.
_NON_CS_RE = re.compile(
    r"\b(?:marketing|sales|pricing|market access|commercial|finance|"
    r"financial|accounting|tax|audit|procurement|sourcing|purchasing|"
    r"supply chain|human resources|hr|talent acquisition|recruiting|"
    r"communications|"
    r"legal|compliance|regulatory|brand|business development|"
    r"customer experience|strategy|patient|medical affairs)\b",
    re.IGNORECASE,
)

# Keywords must start at a word boundary, so short ones like "rtl" and
# "asic" don't fire inside "Portland" or "Basic". No trailing boundary,
# so "robot" still matches "robotics".
def _compile(keyword_table):

    return [
        (category, re.compile("|".join(r"\b" + re.escape(k) for k in keywords)))
        for category, keywords in keyword_table
    ]


_ROLE_PATTERNS = _compile(ROLE_KEYWORDS)
_BROAD_ROLE_PATTERNS = _compile(BROAD_ROLE_KEYWORDS)


_IT_ABBREVIATION_RE = re.compile(r"(?<![A-Za-z])IT(?![A-Za-z])")


# The role categories I actually want texts for. Every internship is
# still stored and classified, but only these trigger an alert.
# Hardware is still classified (EE/RF/FPGA titles) but deliberately not
# targeted - it mostly matched roles that aren't relevant to me.
TARGET_ROLES = {"SWE", "ML", "Data", "Embedded", "Firmware", "Robotics"}


def is_target_role(role_type):

    return role_type in TARGET_ROLES


# PhD/Master's/MBA-only postings. Deliberately doesn't match a bare "MS"
# or "graduate" - those collide with "MS Office", "new grad", etc.
_GRAD_ONLY_RE = re.compile(
    r"\bph\.?\s?d\b|\bdoctoral\b|\bdoctorate\b|\bpost-?doc|"
    r"\bmaster'?s\b|\bmasters\b|\bmaster of\b|\bmba\b|\bmsc\b|"
    r"\bgraduate student|\bgraduate research",
    re.IGNORECASE
)

_UNDERGRAD_RE = re.compile(r"\bundergrad", re.IGNORECASE)


def is_grad_only(title):
    """
    True for internships aimed at PhD/Master's/MBA students. A title that
    also mentions undergrads (e.g. "Undergraduate and Master's R&D
    Intern") is still open to undergrads, so it doesn't count.
    """

    if not title:
        return False

    return bool(_GRAD_ONLY_RE.search(title)) and not _UNDERGRAD_RE.search(title)


# Internship programs that aren't for college students at all: DoD
# SkillBridge (transitioning service members) and high-school programs.
_NOT_COLLEGE_RE = re.compile(r"\bskill\s?bridge\b|\bhigh school", re.IGNORECASE)


def is_ineligible(title):
    """True for postings I can't apply to: grad-only or non-college."""

    if not title:
        return False

    return is_grad_only(title) or bool(_NOT_COLLEGE_RE.search(title))


def classify_role(title):
    """
    Deterministically classify an internship title into a role category.

    Returns one of: SWE, ML, Data, Embedded, Firmware, Hardware,
    Cybersecurity, Robotics, Product, Other.
    """

    if not title:
        return "Other"

    normalized = re.sub(r"\s+", " ", title).strip().lower()

    for category, pattern in _ROLE_PATTERNS:

        if pattern.search(normalized):

            return category

    if _NON_CS_RE.search(normalized):

        return "Other"

    for category, pattern in _BROAD_ROLE_PATTERNS:

        if pattern.search(normalized):

            return category

    # "IT Intern" / "2027 IT Co-op": the abbreviation only counts in
    # uppercase, so the English word "it" doesn't.
    if _IT_ABBREVIATION_RE.search(title):

        return "SWE"

    return "Other"
