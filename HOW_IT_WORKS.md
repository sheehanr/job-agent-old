# How it works

Medtech Job Monitor is a fork of
[BadisMami/hidden-gem-agent](https://github.com/BadisMami/hidden-gem-agent),
customized to watch healthcare and medtech companies for internship and
co-op postings. It sends a phone push when something new and relevant
appears.

## What it watches

- **Company career sites.** 29 healthcare, medtech, and digital health
  companies, including Medtronic, Stryker, Abbott, Johnson & Johnson,
  Intuitive Surgical, Epic, Regeneron, Philips, GE HealthCare, Insulet,
  Dexcom, Oura, and Tempus AI.
  - Most are checked through their hiring system's own data feed (Workday,
    SuccessFactors, Lever, iCIMS, Greenhouse, Jibe), so those checks are
    precise.
  - Three (Intuitive Surgical, Zimmer Biomet, Epic) are checked with an
    automated browser instead.
- **Simplify's public internship list.** It's filtered to a watchlist of
  23 big tech companies (Google, Microsoft, NVIDIA, Stripe, and others)
  plus the same healthcare/medtech companies.

## What triggers an alert

A posting has to be all of these:

- an internship or co-op (including spellings like "Coop" and "Co Op"),
- in the United States,
- a SWE, ML, Data, Embedded, Firmware, or Robotics role,
- not PhD/Master's-only, SkillBridge, or high school, and
- new: not already alerted, and not a repost of the same role at the same
  company within 14 days, from either source.

## When it runs

It runs on GitHub's servers, not my computer:

- **Every hour:** a full check of every enabled company, then Simplify's
  list.
- **Alerts go out whenever a run finds something, 24/7.** Quiet hours are
  left to the phone's Do Not Disturb.

Already-seen postings are tracked in a small SQLite database that the
workflow commits back to the repo. If several new postings show up in one
run, they're bundled into a single push per source ("Career sites:" or
"Simplify:"). Each push lists the company, title, and an apply link. The
pushes go through ntfy, with email-to-SMS as a fallback.
