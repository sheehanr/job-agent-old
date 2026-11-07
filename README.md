# Job Agent

> This is a fork of [BadisMami/hidden-gem-agent](https://github.com/BadisMami/hidden-gem-agent),
> customized by me to watch for **internship and co-op postings at
> healthcare/medtech companies and big tech**.

### What I changed in this fork

- **Company registry:** `data/company_registry.csv` now targets healthcare,
  medtech, and digital health companies (Medtronic, Stryker, Abbott, J&J,
  Intuitive Surgical, Epic, Regeneron, Philips, GE HealthCare, Insulet, Dexcom,
  Oura, Tempus AI, and more). The original companies are still in the file,
  disabled.
- **Co-op search terms:** every adapter searches `intern`, `internship`,
  `co-op`, `coop`, `co op`, and `cooperative education`, then dedupes.
- **US-only filter:** postings with a known non-US location never alert.
- **Target roles:** SWE, ML, Data, Embedded, Firmware, Robotics. Hardware is
  no longer targeted.
- **ntfy push alerts:** pushes go to the ntfy phone app. Email-to-SMS
  remains as a fallback.
- **`--baseline` flag:** a first run that records what's already open
  without notifying.
- **Simplify listings filter:** a second alert source built on Simplify's
  public internship list, limited to a company watchlist.
- **Hourly schedule:** the GitHub Action runs every hour instead of every 4
  hours.
- **New adapters:** Lever and iCIMS. The SuccessFactors adapter also handles
  the tile page layout.

## What it does

A GitHub Action runs every hour. It does two things:

1. **Career-site monitor**
   (`src/internship_monitor_service.py`). It checks every `enabled=yes`
   company in the registry, currently 29 healthcare/medtech companies,
   through each one's applicant-tracking system (Workday, SuccessFactors,
   Lever, iCIMS, and others).
2. **Simplify listings** (`src/simplify_alerts.py`). It reads Simplify's
   public internship list and keeps only companies on
   `data/simplify_watchlist.txt`. That list is 23 big tech companies plus
   the same healthcare/medtech companies.

Alerts are deliberately narrow. A posting only alerts if it is:
- an internship or co-op,
- in the United States,
- in a target role (SWE, ML, Data, Embedded, Firmware, Robotics),
- not PhD/Master's-only, and
- not already alerted.

Each source sends one notification per run, listing every new posting with
its apply link. This is a discovery and alerting tool, not an application
tracker: it doesn't track saved jobs, applications, or interviews.

## Architecture

```
data/company_registry.csv (which companies, which platform, enabled?)
        |
        v
internship_monitor_service.py  --dispatches by platform-->  company_monitors/
        |                                                    workday, successfactors,
        |                                                    greenhouse, jibe, lever,
        |                                                    icims, eightfold, oracle_orc,
        |                                                    taleo, adp,
        |                                                    generic_browser (custom)
        v
database_monitor.py (dedup-aware upsert)
        |
        v
database/internship_agent.db (SQLite - runtime source of truth)
        ^
        |
simplify_alerts.py (Simplify listings.json + data/simplify_watchlist.txt)
        |
        +--> dashboard.py (Streamlit: search, alerts, companies)
        +--> database_alerts.py -> alert_message.py -> sms_alerts.py (ntfy / SMS)
```

The monitor loads only `enabled=yes` registry rows and dispatches each to
the adapter for its `platform`. The `platform_identifier` format for each
platform is listed under [Supported platforms](#supported-platforms); `custom`
companies use `career_url` instead. Results are inserted through a
dedup-aware `upsert_internship()`, so re-running never creates duplicate
rows, and an alert is only created the first time a posting is seen.

## How a posting becomes an alert

- **Internship or co-op.** `src/internship_terms.py` defines the search
  terms (`intern`, `internship`, `co-op`, `coop`, `co op`,
  `cooperative education`) and a word-boundary title regex. That regex
  matches "Software Engineer Coop" but not "Internal Auditor". Each
  keyword-search adapter runs one search per term and dedupes the results.
- **Target role.** `src/role_classifier.py` sorts each title into a
  category. Only `TARGET_ROLES` (`SWE`, `ML`, `Data`, `Embedded`,
  `Firmware`, `Robotics`) alert. `Hardware` (EE/RF/FPGA) is still classified
  but not targeted.
  - Broad words (analytics, informatics, digital, information
    technology/systems, IT) only count when the title has no
    business-function word such as marketing, sales, pricing, commercial,
    finance, or HR. So "Digital Marketing Intern" doesn't alert.
- **Eligible.** PhD/Master's-only, SkillBridge, and high-school postings
  never alert (`is_ineligible()`).
- **US only.** `src/location_filter.py` classifies each location as US,
  non-US, or unknown. Known non-US postings never alert.
  - For an unknown location (e.g. Workday's "4 Locations", or the browser
    scraper's "Unknown"), the monitor first looks it up from the posting
    itself, using Workday's job-detail API or the page's schema.org JSON-LD.
  - If it's still unknown, the alert goes out labelled "(location
    unknown)", and the run summary names the company. Currently that's only
    Epic.
- **Not a repost.** The same company + title isn't alerted twice within 14
  days. This check works across both sources and ignores case.

## Setup

macOS / Linux:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Windows (PowerShell):

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

`playwright install chromium` downloads the headless browser that
`company_monitors/generic_browser_monitor.py` uses for `custom` companies.
Copy `.env.example` to `.env` to send alerts from a local run (see
[Alerts](#alerts)).

The commands below assume the venv is activated.

## Running locally

```bash
python src/internship_monitor_service.py              # career-site monitor
python src/internship_monitor_service.py --fast       # skip browser-based companies
python src/internship_monitor_service.py --baseline   # record what's open, send nothing
python src/simplify_alerts.py                         # Simplify listings
python src/simplify_alerts.py --baseline              # record current matches, send nothing
```

The monitor prints a run summary covering:
- companies checked, failed, and skipped
- jobs retrieved and new postings inserted
- alerts created, and alerts dropped as non-US
- locations looked up from posting pages

**`--baseline`:** use it once on a fresh setup, or after adding companies.
It runs the full scan but marks everything it would alert on as already
sent, so your phone isn't flooded with every posting that's currently open.

To run one adapter directly, e.g. `python src/company_monitors/lever_monitor.py`.

## Simplify listings

`src/simplify_alerts.py` runs after the monitor in the same workflow. It
downloads Simplify's public
[`listings.json`](https://github.com/SimplifyJobs/Summer2027-Internships)
and alerts on a listing only if **all** of these hold:

- `active` and `is_visible` are true, and at least one location is in the
  US. Simplify's "NYC", "SF", and "South SF" shorthands count.
- At least one term hasn't started yet. Winter and Spring start Jan 1,
  Summer May 15, Fall Aug 20. Terms more than 2 years out are ignored, and
  listings with `["N/A"]` are kept. The check uses today's date, so there
  are no hardcoded years.
- The category is Software, Software Engineering, AI/ML/Data, or Data
  Science, AI & Machine Learning. Hardware listings only count when
  `classify_role()` says Embedded, Firmware, or Robotics.
- The title isn't ineligible (`is_ineligible()`).
- The company is on `data/simplify_watchlist.txt`. Matching is exact,
  case-insensitive, and on the whole name, with one company per line as
  `Canonical | alias | alias`. So "Epic" matches Epic Systems, but "Epic
  Games" doesn't.

Seen listing ids are stored in the `simplify_seen` table, so each listing
alerts once. The first run, with nothing seen yet, is automatically a
baseline. To find watchlist names that match nothing in Simplify's file:

```bash
python src/simplify_alerts.py --report-unmatched
```

## Alerts

Each run sends **one** notification per source. The title carries the
source and count (e.g. "Simplify: 3 new internships"), and the body lists
each posting as "Title - Company (location)" followed by its apply link.
Every apply link is always in the notification: if a batch is too long for
one ntfy push (about 4 KB), it's split across several pushes, numbered
"(1/2)", "(2/2)", and never trimmed. Alerts go out at any hour, because there is no texting window; use your phone's Do
Not Disturb for quiet hours. A failed send leaves the alerts queued for the
next run.

**ntfy push (primary).** When `NTFY_TOPIC` is set, alerts are posted to
[ntfy.sh](https://ntfy.sh).
1. Install the ntfy app (iOS/Android) and subscribe to the same topic name.
2. Use a long random topic name, because anyone who knows it can read your
   alerts:
   `python -c "import secrets; print('job-agent-' + secrets.token_hex(16))"`
3. Optional: `NTFY_SERVER` (for self-hosted ntfy) and `NTFY_TOKEN` (for a
   protected topic).
4. Send a test with `python src/sms_alerts.py`.

**SMS (fallback).** If `NTFY_TOPIC` is not set, alerts go out by text
through a free email-to-SMS carrier gateway via Gmail SMTP. Set these:
- `EMAIL_SENDER_ADDRESS`: a Gmail address to send from.
- `EMAIL_APP_PASSWORD`: a Gmail
  [App Password](https://myaccount.google.com/apppasswords), not your real
  password.
- `NOTIFICATION_PHONE_NUMBER`: digits only.
- `SMS_CARRIER_GATEWAY`: `vtext.com` (Verizon), `txt.att.net` (AT&T), or
  `tmomail.net` (T-Mobile).

If neither is configured, sending is skipped and alerts stay queued. `.env`
is gitignored, so never commit real credentials.

## GitHub Actions setup

The workflow is `.github/workflows/monitor.yml`. It runs hourly at :17 past
the hour (cron `17 * * * *`). Each run executes the monitor, then
Simplify, then commits `database/internship_agent.db` back to the repo
only if it changed.

1. **Enable Actions on your fork.** Forks start with workflows disabled. In
   the repo's **Actions** tab, click *I understand my workflows, go ahead
   and enable them*.
2. **Run the baseline once, before adding the secret.** Go to Actions →
   *Monitor (hourly, all companies)* → **Run workflow**, tick **baseline**,
   and wait for it to finish. This records everything that's already open,
   for both sources, without notifying. Doing it before step 3 means no
   scheduled run can send that backlog first.
3. **Add the `NTFY_TOPIC` secret.** Go to Settings → Secrets and variables
   → Actions → *New repository secret*, name it `NTFY_TOPIC`, and use your
   topic name as the value. The SMS secrets are optional and only needed
   without ntfy.
4. **Test it.** Run the workflow with **test_alert** ticked. You should get
   a "Test alert" push. If you don't, the step fails.

The workflow already requests `contents: write` so it can commit the
database. No other repository settings are needed.

## Dashboard

```bash
streamlit run src/dashboard.py
```

The dashboard has three tabs:
- **Internships:** searchable, with clickable apply links, and filtered to
  the target roles by default.
- **Alerts:** newest first.
- **Companies:** the registry.

Run `git pull` first to get the latest database from the Action, and use
the sidebar's "Refresh Data" button to reload it.

## Database

`database/internship_agent.db` (SQLite) holds:
- internships
- alerts, tagged with their source
- seen Simplify listing ids

To create or migrate the schema (safe to re-run, keeps existing rows):

```bash
python src/database_setup.py
```

## Tests

```bash
python -m pytest tests/ -q
```

The tests cover:
- role classification and intern/co-op title matching
- US location classification and posting-page location lookups
- every adapter's parsing, with mocked responses
- dedup/upsert behavior
- alert filtering by role, location, and reposts
- ntfy/SMS sending and `--baseline`
- the Simplify filters, including term-date tests with a pinned "today"

## Supported platforms

Each adapter reads the platform's own API or server-rendered results.
`platform_identifier` formats are in parentheses, and the enabled companies
using each platform are listed.

- **Workday** (`<tenant>.wd<N>.myworkdayjobs.com|tenant|site`): Regeneron,
  ModMed, Abbott, Stryker, Philips, GE HealthCare, Bristol Myers Squibb,
  Insulet, Danaher, Medtronic, Pfizer, Edwards Lifesciences, Dexcom, Merck,
  Johnson & Johnson, Amgen, Becton Dickinson, Tempus AI, Eli Lilly, Siemens
  Healthineers. Find the tenant/site in any job link on the company's
  careers site.
- **SuccessFactors Career Site Builder** (`host`): Boston Scientific,
  Arthrex. Parses the `/search/?q=<term>` page, in both the table and the
  tile layouts.
- **Greenhouse** (`board_token`): Oura. A posting counts if its title or
  its employment-type metadata matches.
- **Jibe** (`api_host`): Garmin. Uses the `tags3=Intern` facet plus a
  keyword search per term.
- **Lever** (`site`, as in `jobs.lever.co/<site>`): Veeva. A posting counts
  if its title or its commitment matches. Lever's country code is spelled
  out, so Canada's "CA" isn't read as California.
- **iCIMS** (`<portal>.icims.com`): Cook Medical. Reads
  `/jobs/search?in_iframe=1` with plain requests, because iCIMS shows
  headless browsers a bot check.
- **`custom`** (uses `career_url`): Intuitive Surgical (SmartRecruiters),
  Zimmer Biomet (Phenom), and Epic (Avature).
  `generic_browser_monitor.py` loads the page in headless Chromium,
  including iframes. It keeps links whose text matches the intern/co-op
  pattern and whose URL contains a job id. If there are none, it searches
  "intern" and then "co-op" in the page's search box.

These adapters are also included, but only disabled rows from the original
project use them:
- **Eightfold.ai** (`api_host|company_domain`)
- **Oracle Recruiting Cloud**
  (`career_site_host|tenant_host|site_number|site_name`)
- **Taleo** (`host|career_section|portal_id`)
- **ADP Workforce Now** (`site_name|client_id`, needs the browser)

## Limitations

- Role classification is deterministic keyword matching. Titles it doesn't
  recognize land in `Other` and never alert; for example, generic titles
  like "2027 Engineering Intern".
- `custom` (browser-scraped) sites are best-effort. A site can block
  headless browsers or change its layout. Before relying on `custom`,
  check the network tab for a Workday, SuccessFactors, Lever, iCIMS, or
  Greenhouse API.
- Epic's postings carry no structured location, so its alerts are
  labelled "(location unknown)".
