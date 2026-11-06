import pytest

from role_classifier import classify_role, is_grad_only, is_ineligible


def test_swe_titles():
    assert classify_role("Software Engineering Intern") == "SWE"
    assert classify_role(
        "Software Quality Assurance Engineering Intern"
    ) == "SWE"


def test_ml_title():
    assert classify_role("Machine Learning Intern") == "ML"


def test_data_title():
    assert classify_role("Data Science Intern") == "Data"


def test_embedded_beats_swe():
    assert classify_role("Embedded Software Intern") == "Embedded"


def test_firmware_title():
    assert classify_role("Firmware Engineering Intern") == "Firmware"


def test_fpga_classified_as_hardware():
    assert classify_role("FPGA Intern") == "Hardware"


@pytest.mark.parametrize("title", [
    "FPGA Intern Engineer",
    "Digital Design Electrical Engineer Intern (Summer 2027)(Onsite)",
    "RTL Design Intern",
    "ASIC Verification Intern",
    "Electrical Engineering Intern (Summer 2027)",
    "Computer Engineering Intern",
])
def test_hardware_titles(title):
    assert classify_role(title) == "Hardware"


def test_software_catch_all():
    assert classify_role("Software/Network Engineering Intern") == "SWE"
    assert classify_role("Software Developer Intern") == "SWE"


def test_short_keywords_need_word_boundary():
    # "rtl" inside "Portland", "asic" inside "Basic"
    assert classify_role("Finance Intern - Portland, OR") == "Other"
    assert classify_role("Basic Operations Intern") == "Other"


@pytest.mark.parametrize("title, expected", [
    ("2027 RF Engineering Intern", "Hardware"),
    ("Radar Engineer Intern", "Hardware"),
    ("2027 Internship - Missile Guidance, Navigation, & Control (GNC)",
     "Robotics"),
    ("2027 Internship - Cyber Physical Systems", "Embedded"),
    ("Software Engineer/Data Scientist Intern", "SWE"),
    ("Engineer/SW Developer/Analyst Intern", "SWE"),
    ("Data Science Intern", "Data"),
])
def test_defense_title_keywords(title, expected):
    assert classify_role(title) == expected


@pytest.mark.parametrize("title", [
    "DevOps Engineer (Skillbridge Intern) - 28114",
    "SkillBridge RF Technician Internship for Service Members",
    "AI Prompt Engineer High School Intern - Summer 2027",
    "Current PhD, AI Engineering Internship Program",
])
def test_ineligible_titles(title):
    assert is_ineligible(title) is True


def test_regular_internship_is_eligible():
    assert is_ineligible("2027 Firmware Engineering Co-Op") is False


def test_autonomous_systems_is_robotics():
    assert classify_role("Autonomous Systems Intern") == "Robotics"


def test_robotics_beats_swe():
    assert classify_role("Robotics Software Intern") == "Robotics"


def test_product_management_not_swe():
    assert classify_role("Product Management Intern") == "Product"


def test_unclassifiable_title_is_other():
    assert classify_role("Accounting Intern") == "Other"


def test_empty_title_is_other():
    assert classify_role("") == "Other"
    assert classify_role(None) == "Other"


def test_cybersecurity_title():
    assert classify_role("Cybersecurity Analyst Intern") == "Cybersecurity"


@pytest.mark.parametrize("title", [
    "Current PhD, AI Engineering Internship Program - Summer 2027",
    "2027 Summer Internship - PhD Data Science",
    "Ph.D. Robotics Intern",
    "Current Master's - Data Science Internship",
    "Masters Software Engineering Intern",
    "MBA Intern, Finance Leadership Development Program",
    "Doctoral Research Intern",
    "Graduate Student Embedded Intern",
    "Boeing Graduate Researcher Program, Software Engineering AI Intern",
    "Research & Development Summer Internship (MSc) 2027",
])
def test_grad_only_titles_detected(title):
    assert is_grad_only(title) is True


@pytest.mark.parametrize("title", [
    "Software Engineering Intern",
    "Software Engineer - Undergrad Internship - Summer 2027",
    "Internship - 2027 Undergraduate and Master's Research & Development Intern",
    "Embedded Systems Intern",
    "Microsoft Office / MS Excel Intern",
    "Intern and New Grad Opportunities",
    "Mastercard Software Engineering Intern",
])
def test_undergrad_titles_not_flagged(title):
    assert is_grad_only(title) is False


def test_target_roles():

    from role_classifier import TARGET_ROLES

    assert TARGET_ROLES == {
        "SWE", "ML", "Data", "Embedded", "Firmware", "Robotics"
    }


@pytest.mark.parametrize("title, expected", [
    ("Business Analytics Intern", "Data"),
    ("Data Analytics & AI Innovation Intern", "Data"),
    ("Health Informatics Intern", "Data"),
    ("Bioinformatics Co-op", "Data"),
    ("Digital Analytics Intern", "Data"),
    ("Information Technology Intern", "SWE"),
    ("Digital Health Intern", "SWE"),
    ("Digital Technology Co-op", "SWE"),
    ("IT Intern", "SWE"),
    ("2027 IT Co-op - Infrastructure", "SWE"),
    ("Software Engineer Coop", "SWE"),
    # EE terms still classify as (non-target) Hardware.
    ("Digital Design Intern", "Hardware"),
    ("RF Engineer Intern", "Hardware"),
    # Lowercase "it" isn't the IT abbreviation.
    ("Make it happen intern", "Other"),
])
def test_tech_department_keywords(title, expected):

    assert classify_role(title) == expected
