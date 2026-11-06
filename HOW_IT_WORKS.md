What this is

Most internship trackers on GitHub just list openings at the usual FAANG+ companies. This one is different: it's a curated list of 67 companies chosen around my interests (embedded systems, ML, software/aerospace engineering). Some are the expected defense/aerospace names — Honeywell, Garmin, Lockheed Martin. Others are companies you'd never guess run tech internship programs at all — Target, Chipotle, Alo, Progressive.

A bot checks all 67 automatically and texts me when something new and relevant posts - only SWE, ML, embedded/firmware, robotics, and hardware/FPGA roles, and never PhD/Master's-only or SkillBridge ones.

How it works

A scheduled program visits each company's career page and checks for new internship postings that match my interests. Some companies (7 so far, including Hudl, Garmin, Honeywell, Lockheed Martin) have a structured API-style feed, so those checks are precise. The rest get checked with an automated browser that scans listings for the word "intern" — works most of the time, still expanding coverage company by company.

It runs on GitHub's servers, not my computer:

Every hour: full check of every enabled company
Alerts go out whenever a run finds something (24/7); quiet hours are left to the phone's Do Not Disturb

Already-seen postings are tracked in a small database, so I only get texted about genuinely new ones. If multiple show up at once, they're bundled into a single text with company, title, location, and a link.
