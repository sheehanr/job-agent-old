# Hidden Gem Internship Discovery Agent

An agent that automatically discovers technical internships and co-ops at
**healthcare and medtech** companies — Medtronic, Stryker, Abbott, Insulet,
Intuitive Surgical, Epic, Regeneron, Philips, GE HealthCare, J&J, Merck and
more. (The original non-Big-Tech registry - Target, State Farm, John Deere,
etc. - is still in the CSV, disabled.) It's tailored to one person (me): only
US-located SWE, ML, Data, Embedded, Firmware, and Robotics internships/co-ops
trigger a phone alert. It is a discovery and alerting tool, not an application tracker: it does not track saved jobs, applied status, or
interview history.

## Architecture

```
data/company_registry.csv (which companies, which platform, enabled?)
        |
        v
internship_monitor_service.py  --dispatches by platform-->  company_monitors/
        |                                                    greenhouse, jibe, eightfold,
        |                                                    oracle_orc, workday,
        |                                                    successfactors, taleo, adp,
        |                                                    lever, icims,
        |                                                    generic_browser (custom)
        v
database_monitor.py (dedup-aware upsert)
        |
        v
database/internship_agent.db (SQLite - runtime source of truth)
        |
        +--> dashboard.py (Streamlit: search, alerts, companies)
        +--> database_alerts.py (alerts on new target-role matches)
```

Company monitoring is registry-driven: `data/company_registry.csv` lists each
company's `platform` and its `platform_identifier` (format per platform below;
`custom` companies use `career_url` instead).
`internship_monitor_service.py`
loads only `enabled=yes` rows, dispatches to the matching adapter, and
inserts normalized internship records directly into SQLite via a
dedup-aware `upsert_internship()` — re-running the monitor never creates
duplicate rows, and alerts are only generated the first time a job is seen.
A repost of a role I was already texted about (same company + title) in the
last 14 days doesn't text again.

Every posting is stored and classified by `role_classifier.py`, but only
roles in `TARGET_ROLES` (`SWE`, `ML`, `Data`, `Embedded`, `Firmware`,
`Robotics`, defined in `src/role_classifier.py`) create an alert. Edit that
set to change what you get alerted about. `Hardware` (EE/RF/FPGA) is still
classified but not targeted. Broad words (analytics, informatics, digital,
information technology, IT) only count when the title has no
business-function word (marketing, sales, pricing, commercial, finance,
HR, ...), so "Digital Marketing Intern" doesn't alert.

**Internships and co-ops.** `src/internship_terms.py` defines what counts:
every keyword-search adapter runs one search per term (`intern`,
`internship`, `co-op`, `coop`, `co op`, `cooperative education`), dedupes
the results, and re-filters titles with a word-boundary regex.

**US only.** `src/location_filter.py` classifies each location as US,
non-US, or unknown. Known non-US postings never alert. For a new posting
that would alert but whose location is unknown (e.g. Workday's
"4 Locations", or the browser scraper's "Unknown"), the monitor looks the
location up from the posting itself (Workday's job-detail API, or the
page's schema.org JSON-LD) before deciding. If it's still unknown the alert
goes out labelled "(location unknown)", and the run summary lists which
companies that happened for.

## Setup

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

The `playwright install chromium` step is required - it downloads a
headless browser used by `company_monitors/generic_browser_monitor.py`
to render JS-heavy career sites that a plain HTTP request can't see
through (most `platform=custom` companies fall into this category).

Copy `.env.example` to `.env` if you want SMS alerts (optional, see below).

## Database

The SQLite database at `database/internship_agent.db` is the runtime source
of truth for internships and alerts.

```powershell
# Create or safely migrate the schema (idempotent, preserves existing rows)
python src/database_setup.py
```

## Running the monitor

```powershell
python src/internship_monitor_service.py
```

Prints a run summary (companies checked/successful/failed/skipped, jobs
retrieved, new internships inserted, alerts created, alerts dropped as
non-US). Safe to re-run on a schedule — only genuinely new postings create
new rows and alerts.

**First run / after adding companies:** run once with `--baseline`. It does
a full scan but marks every queued alert as sent *without* notifying, so
your phone isn't flooded with every posting that's already open:

```powershell
python src/internship_monitor_service.py --baseline
```

In GitHub Actions, use **Run workflow** with the *baseline* box ticked.

To run the Greenhouse adapter directly against one company:

```powershell
python src/company_monitors/greenhouse_monitor.py
```

## Dashboard

```powershell
streamlit run src/dashboard.py
```

Tabs: Internships (search across company/title/location/role type, with
clickable Apply links, filtered to my target roles by default), Alerts
(newest first), Companies (the registry). Use the sidebar "Refresh Data" button
after running the monitor to pick up new rows without restarting Streamlit.

## Tests

```powershell
python -m pytest tests/ -v
```

Covers role classification, intern/co-op title matching, US location
classification, posting-page location lookup, mocked adapter parsing,
internship dedup/upsert behavior, alert-only-on-new-job logic, target-role
and non-US alert filtering, ntfy/SMS sending, and `--baseline`.

## Environment variables

Alerts are optional. Each run sends **one** notification listing every new
posting with its apply link, at any hour - use your phone's Do Not Disturb
for quiet hours. A failed send leaves the alerts queued for the next run.

**Push notifications (ntfy, recommended).** Set `NTFY_TOPIC` and alerts go
out as an [ntfy.sh](https://ntfy.sh) push instead of a text. Install the
ntfy app (iOS/Android), subscribe to the same topic name, done. Anyone who
knows the topic name can read it, so use a long random one (e.g.
`python -c "import secrets; print('hga-' + secrets.token_hex(16))"`).
Optional: `NTFY_SERVER` (self-hosted ntfy) and `NTFY_TOKEN` (access token
for a protected topic). Test with `python src/sms_alerts.py`.

**SMS fallback.** If `NTFY_TOPIC` is not set, alerts are sent by text. Sending
uses a free email-to-SMS carrier gateway (e.g. `number@tmomail.net` for
T-Mobile) via Gmail SMTP - not a paid SMS API - since this is a
single-user personal alert, not a product sending texts to other people.
Copy `.env.example` to `.env` and set:

- `EMAIL_SENDER_ADDRESS` - a Gmail address to send from
- `EMAIL_APP_PASSWORD` - a Gmail **App Password** (not your real
  password), generated at https://myaccount.google.com/apppasswords
  (requires 2-Step Verification enabled first)
- `NOTIFICATION_PHONE_NUMBER` - your phone number, digits only
- `SMS_CARRIER_GATEWAY` - your carrier's email-to-SMS domain (`vtext.com`
  for Verizon, `txt.att.net` for AT&T, `tmomail.net` for T-Mobile, etc.)

If neither is configured, sending is skipped rather than failing - alerts
stay queued in the DB and the dashboard works either way.
`.env` is gitignored — never commit real credentials.

## Supported platforms

Structured adapters (real title/location/apply-link fields from the
platform's own API). `platform_identifier` format in parentheses:

- **Greenhouse** (`board_token`) - Hudl.
- **Jibe** (`api_host`) - Garmin, State Farm, Johns Hopkins APL. Uses the
  `tags3=Intern` facet, falling back to a keyword search for sites
  without it (APL).
- **Eightfold.ai** (`api_host|company_domain`) - John Deere, Lockheed
  Martin, Eaton, CACI, Northrop Grumman (`jobs.northropgrumman.com|ngc.com`).
- **Oracle Recruiting Cloud** (`career_site_host|tenant_host|site_number|site_name`)
  - Honeywell.
- **Workday** (`<tenant>.wd<N>.myworkdayjobs.com|tenant|site`) - most of
  the healthcare list (Medtronic, Stryker, Abbott, J&J, Merck, Pfizer,
  Lilly, BD, Dexcom, Regeneron, ...). Find the tenant/site in any job link
  on the company's careers site.
- **SuccessFactors Career Site Builder** (`host`) - Boston Scientific,
  Arthrex, HII. Parses the server-rendered `/search/?q=<term>` page (both
  the table and the tile layouts).
- **Lever** (`site`, the name in `jobs.lever.co/<site>`) - Veeva. Reads
  Lever's public postings API; a posting counts if its title or its
  commitment (e.g. "Internship") matches.
- **iCIMS** (`<portal>.icims.com`) - Cook Medical. Reads the server-rendered
  `/jobs/search?in_iframe=1` results (headless browsers get a bot check on
  iCIMS, plain requests don't).
- **Taleo** (`host|career_section|portal_id`) - Textron Systems. The
  `portal` id is on the `rest/jobboard/searchjobs` request in the browser's
  network tab.
- **ADP Workforce Now** (`site_name|client_id`, needs the browser) -
  Mercury Systems. ADP's API needs a session token, so the page is loaded
  in the headless browser and its own API response is read.

Every adapter filters titles with the shared word-boundary regex in
`src/internship_terms.py`, so "Internal Auditor" / "International"
results don't leak through.

Best-effort fallback for everything else:

- **`custom`** - `generic_browser_monitor.py` loads `career_url` in headless
  Chromium (including iframes), takes links whose text contains
  "intern"/"internship"/"co-op" and whose URL has a 4+ digit job id, and if
  there are none, searches "intern" then "co-op" in the page's job-search
  box. Point `career_url` at the site's intern search-results page when one
  exists - landing pages often have no job links at all. Location comes
  back "Unknown" and is looked up from the posting page for new alerts.
  Used for Intuitive Surgical (SmartRecruiters), Zimmer Biomet (Phenom),
  and Epic (Avature).

## Limitations

- Role classification (`src/role_classifier.py`) is deterministic
  keyword matching - titles it hasn't seen land in `Other` and never
  alert. Generic titles like "2027 Engineering Intern" are `Other`.
- Some `custom` companies still return nothing (the site blocks headless
  browsers or needs multi-step interaction). Check the network tab for a
  Workday / Eightfold / Taleo / SuccessFactors API before trying anything
  else - most "custom" sites turned out to be one of those.
