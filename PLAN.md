# Naukri Job Automation — Plan

## 1. What we are building

A tool that each user runs on their own PC. It:

1. Takes their target role and CV through a small web dashboard
2. Finds matching jobs on Naukri on a schedule
3. Applies to the ones that match, within a daily cap, fully automatically
4. Writes every application into the user's own Google Sheet
5. Shows how many were applied, viewed by recruiters, skipped or failed

## 2. Priorities

Set by the owner. When two goals pull against each other, the higher one wins.

1. Reliability
2. Security
3. Simple onboarding
4. Good UX
5. Modular architecture
6. Error recovery
7. Testability
8. GitHub readiness

## 3. Constraints that shape the design

| Reality | What it means for us |
|---|---|
| Naukri has no public API for applying | We drive a real browser (Playwright) using the user's own logged-in session |
| Naukri's terms of use do not allow automated access | An account could be restricted. We keep volume low (daily cap, one job at a time, slow pace). Each user accepts this risk |
| Login may ask for OTP or CAPTCHA | The user logs in once, by hand, in a browser window the tool opens. The session is saved. If Naukri asks again, the tool pauses and alerts. It never tries to bypass a check |
| Naukri applies with the resume saved on the user's Naukri profile | The CV uploaded to our dashboard builds the candidate profile and is recorded as "CV used" in the sheet. It is not attached per job |
| Jobs come in three kinds | **Direct apply**: automated. **Apply with recruiter questions**: automated only when every question has a saved answer, otherwise flagged. **Apply on company site**: not automated, logged with the link |
| Naukri detects automated browsers (seen live, 2026-10-04) | An invisible (headless) browser gets "Access Denied", and that browser profile then keeps getting "No result found" pages padded with unrelated jobs. A visible automated browser got real results in 1 of 3 fresh test profiles; the other 2 got the "No result found" page while a normal browser showed 13 real jobs. The tool always uses a visible window, never takes jobs from a "No result found" page, reports it to the user, and does nothing to disguise itself. **Search is therefore not dependable, and applying will face the same wall or a stricter one** |
| Google refuses "Continue with Google" in a tool-controlled browser ("This browser or app may not be secure", hit by the owner 2026-10-04) | Users who sign in to Naukri through Google must use Naukri's password or OTP login in the tool's window. The tool does not work around Google's check |
| Naukri does not report "approved" | We can read "Applied" and "Viewed by recruiter" from the application history. Shortlist / interview / rejected arrive by email or call, so the user marks those in the dashboard |

## 4. Tech stack

- **Python 3.11+**, **FastAPI**, **SQLite** (SQLAlchemy)
- **Dashboard**: pages served by FastAPI itself (Jinja2 templates, one CSS file, a little plain JS). One process, no frontend build. Glass theme in light (default) and dark, switched by the button at the top right; all colours are tokens at the top of `style.css`. Motion (scroll reveal, pointer glow, saved tick, page fades) lives in `ui.js` and switches off for people who ask for reduced motion
- **pypdf / python-docx** for reading CVs
- **Playwright** driving the Edge or Chrome already on the PC (no browser download), always in a visible window
- Still to add: **gspread** + Google service account (Sheets), **APScheduler** (background jobs)

Runtime data lives **outside** the project, in `%LOCALAPPDATA%\NaukriJobAutomation\`:
database, logs, and later the browser profile, failure screenshots and Google key file.
Reason: a project folder may sit inside OneDrive, and OneDrive syncing a live SQLite file
or a Chromium profile causes file locks and corruption.

## 5. How it flows

```
Dashboard (role, CV, answers, caps)
        │
        ▼
   SQLite database  ◄──────────── source of truth
        │
Scheduler ──► 1. Discover   search Naukri, read job cards                 (built, button on Jobs page)
              2. Ingest     drop duplicates, run filters, score           (built)
              3. Queue      matched jobs wait, best score first           (built)
              4. Apply      one at a time, daily cap, pause on any check  (not built)
              5. Sync       push new/changed rows to Google Sheets        (not built)
              6. Status     once a day, read application history          (not built)
```

Every job enters through `backend/services/ingest.py`, whatever found it. That is the
boundary Naukri discovery plugs into.

## 6. Folder structure

```
Naukri_job_automation/
├── start.bat                  double-click to install and start
├── README.md                  user guide
├── PLAN.md
├── requirements.txt           requirements-dev.txt adds the test tools
├── .env.example               optional machine settings
├── backend/
│   ├── __main__.py            `python -m backend`: picks a free port, opens the browser
│   ├── main.py                FastAPI app, local-only protections
│   ├── config.py              machine settings (data folder, CV size limit)
│   ├── api/                   one file per page: overview, welcome, cv, profile, roles,
│   │                          answers, jobs, settings; web.py holds shared helpers
│   ├── db/                    database.py, models.py
│   ├── services/
│   │   ├── cv_parser.py       CV file → text → name, email, phone, skills, education
│   │   ├── cv_store.py        save / activate / delete CVs, fill the profile
│   │   ├── skills.py          skill vocabulary shared by parser and matcher
│   │   ├── matching.py        filters + 0-100 score
│   │   ├── ingest.py          duplicate check, score, queue or skip
│   │   ├── demo_jobs.py       sample jobs built from the user's role
│   │   └── sheets_sync.py     Sheet link parsing (sync itself not built)
│   │   ├── registration.py    sends name + email to the owner, only after the welcome notice
│   ├── core/                  clock.py, log.py
│   ├── naukri/
│   │   ├── selectors.py       everything known about Naukri's pages, in ONE file
│   │   ├── parse.py           card text → experience, salary, date; search address builder
│   │   ├── browser.py         visible Edge/Chrome with the tool's own saved profile
│   │   ├── discovery.py       load result pages, read job cards, save evidence on failure
│   │   └── session.py         wait for the user to log in themselves
│   └── workers/
│       ├── runner.py          one browser task at a time, in the background
│       ├── discover.py        search every active role, ingest, record the run
│       └── connect.py         "Connect Naukri"
├── owner/                     for the repository owner: user-list Apps Script + setup steps
├── dashboard/
│   ├── templates/             HTML pages
│   └── static/                style.css, tour.js, favicon.svg
├── scripts/                   (empty) login, install-at-startup
├── resumes/                   uploaded CVs (git-ignored)
└── tests/                     122 tests: CV reading, matching, ingest, search, registration, every page
```

## 7. Database tables

| Table | Holds |
|---|---|
| `candidate_profile` | name, email, phone, city, experience, skills, education, current/expected salary, notice period |
| `cvs` | original file name, stored name, upload date, parsed text and details, which one is active |
| `search_profiles` | one row per role: title, cities, lowest salary, job age, words and companies to skip, on/off |
| `answers` | saved answers for recruiter questions |
| `settings` | Sheet link, daily apply cap, lowest match score, whether welcome setup is done |
| `jobs` | Naukri job ID (unique), title, company, location, experience, salary, skills, URL, posted date, apply type, duplicate key, match score and reasons, sample flag |
| `applications` | one per job: state, CV used, applied at, Naukri status, attempts, last error |
| `sheet_outbox` | rows waiting to be pushed to Google Sheets |
| `runs` | each run: start, end, found, matched, applied, skipped, failed |

Application states:

```
found ──► QUEUED ──► APPLYING ──► APPLIED
   │                    ├───────► FAILED        (retry up to 2 times)
   ├──► SKIPPED         └───────► NEEDS_MANUAL  (unknown question / check shown)
   └──► EXTERNAL  (matches, but must be applied to on the company's site)
```

## 8. Matching

**Filters** reject a job outright: location not in the role's cities, salary below the
lowest, older than the job-age limit, a skip word in the title, a skip company, or more
than one year short on experience.

**Score** for jobs that pass: title 45, skills 40, experience 15. A part with nothing to
compare is left out and the rest re-scaled. Jobs at or above the lowest match score are
queued.

## 9. Google Sheet layout (planned)

**Tab "Applications"** (one row per job, keyed by Naukri Job ID):

Applied On · Company · Job Title · Job Location · Experience · Salary · Key Skills ·
Match Score · Apply Type · CV Used · Search Role · Status · Status Updated ·
Job Link · Naukri Job ID · Notes

**Tab "Needs Manual"**: company-site jobs and jobs with unanswered questions, with links.
**Tab "Run Log"**: one row per run. **Tab "Summary"**: totals by status, per day, per company.

## 10. Rules that keep it from collapsing

1. **Database is the truth, the Sheet is a copy.** If Google is down, rows wait in
   `sheet_outbox` and go out on the next run.
2. **Never apply twice.** Naukri Job ID is unique. A second key (company + title +
   location) catches reposts. Before any retry, check whether Naukri already shows the
   job as applied.
3. **Never duplicate a sheet row.** Sync updates the row with the same Job ID.
4. **One apply at a time**, with a lock so two runs can never overlap.
5. **Daily cap** (default 20, hard ceiling 50), slow pace, working hours only.
6. **Circuit breaker.** Three failures in a row stop the run and alert the user.
7. **All Naukri selectors in one file**, so a redesign is a one-file fix.
8. **Dry-run mode.** Does everything except the final Apply click.
9. **Evidence on failure.** Screenshot + page HTML saved for every failed job.
10. **Sample jobs are never applied to or synced** (`jobs.is_demo`).
11. **Local only.** The app rejects foreign Host headers and cross-site form posts.

## 11. Build roadmap

| # | Step | Status |
|---|---|---|
| 1 | Project structure | Done |
| 2 | Backend + database | Done |
| 3 | Basic web dashboard | Done |
| 4 | CV upload/parser | Done (PDF, DOCX, TXT) |
| 5 | Candidate profile | Done (profile, roles, saved answers, settings) |
| 6 | Job data model | Done |
| 7 | Job matching engine | Done |
| 8 | Naukri job discovery | Built: search button, reads result cards. The owner's own first search (2026-10-04, not logged in) returned 20 real jobs. Naukri does not always give the tool real results (section 3). One results page per search: the address for page 2 returned page 1 again, the fix is untested live. "Connect Naukri" is built but untested with a real login. Job detail pages are not read yet, so real jobs are not yet marked direct-apply or company-site |
| 9 | Duplicate detection | Done for stored jobs. "Already applied on Naukri" check comes with step 11 |
| 10 | Application queue | Done: best score first, daily cap, one browser task at a time |
| 11 | Application workflow | Built, see section 13. Practice and real mode; company-site jobs set aside with their link; recruiter-question jobs handed to the user |
| 12 | Google Sheets synchronization | Built 2026-10-04: outbox, one row per job, batches, retry, "send everything" button. It writes through a small script the user adds to their own Sheet (`sheets/applications_sheet.gs`), not a service account: no Google Cloud project or key file for the user. Tested with a stand-in for Google; **not yet run against a real Sheet**, which needs the owner to deploy the script |
| 13 | Application-status dashboard | Overview counts exist. Funnel, filters, manual status edit not started |
| 14 | Scheduler / background workers | Not started |
| 15 | Logging + retry system | Basic file logging done. Retries, circuit breaker, alerts not started |
| 16 | Deployment | `start.bat` done. Auto-start at Windows login not started |

Also done, outside the original list: first-run welcome setup with skip, guided tour,
sample jobs, README, and a design pass using the `ui-ux-pro-max` skill (Swiss minimal
style, teal palette, Plus Jakarta Sans).

## 12. Decisions made (owner, 2026-10-04)

- **Distribution:** free in the owner's public GitHub repository; the owner also sells
  setup of the same tool to people who are not on GitHub.
- **Seeing who uses it:** the first welcome step, the same for every user, sends name and
  email to a Google Sheet the owner controls, and says so on the screen. Built in
  `registration.py` and `owner/`. It stays off until the owner pastes their Apps Script link
  into `backend/config.py` (`owner/SETUP.md`). The Google side has not been tested.

## 13. Applying (step 11): built 2026-10-04

What exists, in `backend/naukri/apply.py` and `backend/workers/apply.py`:

- **Reading a job page** (`open_job`), verified live on the owner's logged-in profile: normal
  Apply job, company-site job with the company's link read from the page's own data (no
  click), already-applied job. The page's job data decides, not the first button painted.
- **Practice mode** (default) and **real mode**, chosen on Settings. Real mode clicks Apply
  once and trusts only Naukri's own answer for that job ID.
- **One real application** was sent with the owner's explicit choice (Capgemini, Software
  Engineer, 08:36): Naukri answered status 200, "You have successfully applied to this job",
  quota 1 of 50 for the day. `selectors.py` records the shape of that answer.
- Daily cap, 30-90 s spacing, stop after 3 problems in a row, stop when logged out, stop at
  Naukri's own quota, never retry an unconfirmed click.
- Additive database upgrade with a backup first (`database.add_missing_columns`).

Not yet seen or done:

- **The real-mode code path has not run live.** The one real application was sent by a
  hand-run script; `click_apply` is modelled on the answer it captured and is covered by
  fakes only. Its first live run will be the owner's first real run from the dashboard.
- **The real-mode path has now run live** (owner's own runs, 08:46 and 08:47): two jobs from
  Sunrise Biztech Systems. On both, Naukri opened a chat panel saying "Kindly answer all the
  recruiter's questions to successfully apply for the job" with a "Type message here" box.
  The tool did what it should: no confirmation, so "Apply by hand", picture saved, no retry.
  The saved pages are in the owner's screenshots folder (`apply-20261004-0316*.html`) and
  are the first real evidence of the questions panel (`chatbot_Drawer`, `botItem` messages,
  a `textArea` input). A confirmed live application through the dashboard button has still
  not happened.
- **Answering recruiter questions** is the biggest gap for hands-off applying: many jobs ask
  them. Such a job ends as "Apply by hand". The saved answers on the Answers page are not
  used yet. Building this needs the question types seen one by one on live jobs, with the
  owner choosing the jobs, because finishing the questions sends a real application.
- "Viewed by recruiter" status reading (step 13).

Never send a real application while developing without the owner naming the job.

## 13a. Earlier notes on this step

Blocked on the owner clicking **Connect Naukri** and logging in; nothing about the logged-in
pages has been seen yet, so no apply code is written.

Connect had a bug until 2026-10-04: it reported "Connected" within seconds with nobody logged
in, because it read the address before Naukri redirected to its login page. Fixed (the address
must now stay on the account page for 6 seconds) and covered by `tests/test_session.py`, but a
real successful login has still not been seen. First thing to check after one: that the login
survives closing and reopening the tool's browser.

Build order once connected:

1. Look at 2-3 queued job pages logged in, without clicking, to learn the real markup: the
   Apply button (`#apply-button`, seen logged out on three jobs), the company-site button,
   and how an already-applied job looks.
2. Dry run: everything except the final click, with the result shown in the dashboard.
3. One real apply with the owner's explicit go-ahead, saving what Naukri shows afterwards
   (success message or recruiter questions), then build the handling from that evidence.
4. Company-site jobs are never applied to by the tool: every company's form is different.
   The tool marks them and links to them. The company's own address is not in the page; it
   only appears after a logged-in click, so capturing it belongs to this step too.
5. Schema changes from here need the additive-column migration first: the owner now has a
   real database.

## 14. Open decisions (owner)

1. **How far to trust it.** Section 3 still holds: Naukri can stop giving the tool real
   pages at any time.
2. **Selling a tool that automates Naukri** carries more risk than using one: customers'
   accounts can be restricted, the tool may simply stop working for them, and Naukri's terms
   are being broken commercially. Get advice before charging for it.
