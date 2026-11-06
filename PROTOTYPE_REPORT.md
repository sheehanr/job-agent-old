# Hidden Gem Internship Agent: Usage & Design Process

## What it does

The agent checks the career sites of 67 non-Big-Tech companies every hour and texts me when a new **SWE, ML, Embedded, Firmware, Robotics or Hardware/FPGA** internship posts. It skips PhD/Master's-only and SkillBridge roles, and doesn't re-text a role reposted within 14 days. The defense, aerospace and industrial companies it covers (Lockheed Martin, Garmin, John Deere, Honeywell, Target and others) are ones most internship trackers miss. It runs on GitHub Actions, so no computer needs to stay on.

## How to use it

- **Get alerts:** nothing to do. New matches arrive as one text per run with company, title and apply link. Alerts go out 24/7 whenever a run finds something; quiet hours are left to the phone's Do Not Disturb.
- **See all postings:** run `git pull` then `venv\Scripts\streamlit run src/dashboard.py`. The dashboard lets you search every posting, see past alerts and view the company list.
- **Run a check manually:** on GitHub go to Actions → Monitor → Run workflow. Locally, run `venv\Scripts\python src/internship_monitor_service.py`.
- **Change roles:** edit `TARGET_ROLES` in `src/role_classifier.py`.
- **Add or remove a company:** edit `data/company_registry.csv`.

## How it works

1. GitHub Actions starts a run every hour.
2. For each company in the registry, the agent pulls postings from its job API (8 companies). For the other 57, it uses a headless browser.
3. Each title is sorted into a role (SWE, ML, Embedded, etc.) by keyword.
4. New postings are saved to a SQLite database, so the same job is never texted twice.
5. Matching postings are bundled into one text, sent through Gmail to my carrier's free SMS gateway.

## Design process

| Stage | What I built | Why |
| --- | --- | --- |
| MVP (Sep 13) | Static CSV of internships + resume upload | Starting point |
| First live source (Sep 14) | Pulled real postings from Hudl's job API | Replace hand-typed data |
| Coverage (Sep 17) | Adapters for 4 job platforms + browser fallback; grew from 23 to 65 companies | The companies I wanted don't use common job boards |
| Automation (Sep 17) | SMS alerts + GitHub Actions scheduling | Get a text without running anything by hand |
| Tailoring (Sep 24) | Only my roles, no PhD/Master's, one 4-hour schedule, removed unused resume code | Texts were arriving at random hours and for roles I don't want |
| Defense coverage (Oct 4) | Hardware/FPGA roles added; Workday, SuccessFactors, Taleo and ADP adapters; iframe support | An FPGA internship was found but never texted, and Northrop, Leidos, Textron, Mercury etc. returned nothing |

Key choices:
- **Job APIs first, browser as a fallback.** APIs are exact; the browser works on almost any site.
- **Email-to-SMS instead of Twilio.** Free, and enough for one person.
- **Keyword role matching instead of ML.** Predictable and easy to test.

## Testing

- **Automated tests:** 123 tests, run with `venv\Scripts\python -m pytest`, covering role sorting, the PhD/Master's filter, deduplication, the texting-hours window, SMS batching and each job-platform adapter.
- **Live testing:** each adapter was checked against a real company. Full runs across all the companies were done, and a real text was received on my phone.

Bugs testing caught and fixed:
- **Data loss:** the database was wiped on every run. Fixed by saving new postings without rebuilding.
- **False matches:** "Internal Auditor" counted as an internship. Fixed with whole-word matching.
- **Too many texts:** one run sent 40 texts and the carrier blocked them. Fixed by batching into one text.
- **Night texts:** texts came at 3am because GitHub ran jobs hours late. Fixed with a texting-hours check in the code.
- **Wrong roles:** texts came for Cybersecurity, Firmware and PhD roles. Fixed with a target-role list and a grad-only filter.

## Limitations and next steps

- **Coverage gaps:** some consumer/finance companies on the generic browser scraper still return no data. All the defense/embedded companies are now covered.
- **Title-only filtering:** a grad-only requirement stated only in the job description still gets through.
- **Late runs:** GitHub doesn't guarantee run times, so checks can be late or skipped.
