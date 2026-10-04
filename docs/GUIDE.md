# Naukri Job Automation: full guide

The short version is in the [README](../README.md). This page has every step and every detail.

A tool that runs on your own Windows PC, finds jobs on Naukri that fit you, applies for you, and keeps a record of every application in your own Google Sheet.

## What works today

This project is still being built. Be clear about what you are getting:

| Part | Status |
|---|---|
| Welcome setup, guided tour, dashboard | Working |
| CV upload and reading (PDF, DOCX, TXT) | Working |
| Profile, roles, saved answers, settings | Working |
| Matching engine (filters + 0-100 score) | Working |
| Duplicate job protection | Working |
| Sample jobs to try the matching | Working |
| Searching Naukri for jobs | Working, but Naukri does not always show the tool real results. See [Searching Naukri](#searching-naukri) |
| Connecting your Naukri account | Working (password or OTP login; Google sign-in does not work in the tool's window) |
| Applying on Naukri | Working for jobs with Naukri's own Apply button. Starts in practice mode. See [Applying](#applying) |
| Company-site jobs | Set aside with the company's own link. The tool does not apply on company websites |
| Jobs where the recruiter asks questions | Handed to you. The tool does not answer questions yet |
| Saving applications to your Google Sheet | Working once you connect your Sheet (a 2-minute step, see [Your Google Sheet](#your-google-sheet)) |
| Light and dark theme | Working. The button at the top right switches between them |
| Running by itself on a schedule | Not built yet |

The full plan is in [PLAN.md](../PLAN.md).

## Read this first: the risk to your Naukri account

Naukri's terms of use do not allow automated tools. If Naukri notices automated activity, it can restrict or block your account. This tool keeps the pace slow and limits how many jobs it applies to each day, but that lowers the risk, it does not remove it. You use this tool at your own risk.

The tool never tries to get past a CAPTCHA or an OTP check. If Naukri asks for one, the tool stops and waits for you.

## What you need

- A Windows 10 or 11 PC
- [Python 3.11 or newer](https://www.python.org/downloads/). During the install, tick **Add python.exe to PATH**.
- Microsoft Edge or Google Chrome. Edge comes with Windows.
- A Naukri account, with your profile and resume already filled in on Naukri
- A Google account, for the Google Sheet

## Install and start

1. Download this project. On GitHub: green **Code** button, then **Download ZIP**. Unzip it anywhere.
2. Open the folder and double-click **start.bat**.
3. The first run sets things up, which takes a minute or two and needs internet. After that the dashboard opens in your browser at `http://127.0.0.1:8000`.

Keep the black window open while you use the tool. Close it to stop the tool. To start again, double-click `start.bat`.

## First-time setup

The first time you open the dashboard, a short welcome setup asks for four things. Every step has a **Skip this step** link, and **Skip setup** at the bottom skips all of it. Anything you skip can be added later from the dashboard.

| Step | What it asks | Where to get it |
|---|---|---|
| 1. About you | Your name, email, years of work experience, your city | Type them in. Use 0 years if you are a fresher. |
| 2. Your CV | A PDF, DOCX or TXT file, up to 5 MB | The same CV you use on Naukri. The tool reads your skills from it. |
| 3. Role | The job title you want, and the cities you would work in | Type what you would search on Naukri, for example `Frontend Developer` and `Hyderabad, Remote`. |
| 4. Google Sheet | The link to a Google Sheet you own | See below. Connecting it so the tool can write to it is done afterwards, on the Settings page. |

### How to get your Google Sheet link

1. Open [sheets.new](https://sheets.new) in your browser. It creates a blank sheet in your Google account.
2. Give the sheet a name, for example `Naukri applications`.
3. Copy the link from the browser's address bar. It starts with `https://docs.google.com/spreadsheets/d/`.
4. Paste it into the setup step, or later on the **Settings** page.

After setup you can take a short tour of the dashboard. To see it again, use **Take the tour** at the bottom of any page.

## The dashboard

| Page | What it is for |
|---|---|
| **Overview** | How many jobs were found, are waiting, were applied to or failed, plus a checklist of what is left to set up. |
| **CV** | Upload a new CV, see what the tool read from it, and copy those details into your profile. |
| **Profile** | Your details. The **Skills** list matters most: it decides which jobs match you. Fix it by hand if the CV reading missed something. |
| **Roles** | The job titles to search for. Each role has its own cities, lowest salary, job age, and words or companies to skip. Switch a role off without deleting it. |
| **Answers** | Saved answers for questions recruiters ask while applying, such as "Are you willing to relocate?". |
| **Jobs** | **Search Naukri now**, the **Applying** box, and every job found, best match first. Each job has a link to open it on Naukri, and company-site jobs get the company's own link. Skipped jobs say why they were skipped, and a summary at the top tells you what to change. |
| **Settings** | Connect your Naukri account, connect your Google Sheet, choose practice or real applying, the daily apply limit (50 at most), and the lowest match score to apply. |

The round button at the top right switches between the light and the dark theme. The tool remembers your choice.

When you change your skills, a role, or the lowest match score, the jobs already found are checked again against the new details.

## Searching Naukri

On the **Jobs** page, click **Search Naukri now**. A browser window (Edge or Chrome) opens, loads Naukri's search page for each role that is switched on, in each of its cities, and closes by itself after about a minute. Leave it alone while it works. Only the first page of results (20 jobs) is read for each search, to keep the traffic low.

**Salary is in lakhs per year.** On a role, "lowest salary" of 6 means ₹6,00,000 a year, which is ₹50,000 a month. Do not type rupees: a number like 50000 would reject every job, so the tool refuses it.

The window is always visible on purpose. The tool never hides what it is doing.

**The limit you should know about.** Naukri can tell when a browser is being driven by a tool. In testing, Naukri sometimes answered the tool's browser with "No result found" and a list of unrelated jobs, while a normal browser got real results for the same search. When that happens:

- the tool takes nothing from that page, so unrelated jobs never get in
- the Jobs page tells you that Naukri answered "No result found"
- the tool does not try to disguise itself or get around it

So a search may find jobs one time and nothing another time. If Naukri shows a page the tool does not understand at all, the search stops and a picture of that page is saved in `%LOCALAPPDATA%\NaukriJobAutomation\screenshots`.

### Connecting your Naukri account

On the **Settings** page, click **Connect Naukri**. A browser window opens on Naukri's login page and you log in there yourself. Do not close the window: it closes by itself a few seconds after you are in. The tool never sees, types or saves your password.

Log in with your email or mobile number and your Naukri password, or with **Use OTP to Login**. **Continue with Google does not work in that window.** Google refuses to sign in inside a browser that a tool controls and shows "This browser or app may not be secure". If you normally use Google to get into Naukri, use the OTP login, or set a Naukri password first with **Forgot password** on Naukri in your normal browser. The login stays saved in that window's own profile on your PC. Searching works without connecting. Applying needs it.

## Applying

Jobs that pass your filters and score at or above your cut-off show as **Waiting to apply**. The **Applying** box on the Jobs page works through them, best match first.

The tool starts in **practice mode**. A practice run opens each waiting job on Naukri, as you, and reports what it found. It never clicks Apply. Use it first to see what the tool would do.

When you are ready, choose **Real applications** on the **Settings** page. A real run then does this for each waiting job:

| What the job's page shows | What the tool does |
|---|---|
| Naukri's own **Apply** button | Clicks it once. The job counts as applied only when Naukri itself answers that the application was received. |
| **Apply on company site** | Does not apply. The job is set aside, and the **Apply link** column gets the company's own link so you can apply there yourself. |
| You had already applied | Records it as applied. Never applies twice. |
| Naukri does not confirm, for example because the recruiter asks questions | Stops on that job, saves a picture, and marks it **Apply by hand**. It is never retried by the tool, because the first click may have gone through. |

Things to know before a real run:

- Naukri sends the resume saved on **your Naukri profile**, not the file you uploaded to the tool. Keep that one current.
- An application cannot be taken back.
- Applications are spaced 30 to 90 seconds apart, so 20 applications take around 20 minutes. Leave the browser window alone; closing it stops the run.
- The run stops at your daily limit (Settings, 50 at most, which is also Naukri's own limit), after three problems in a row, or if Naukri logs the tool out.
- After applying, Naukri may open a chat panel asking you to complete your profile. That is not part of the application and the tool leaves it alone.

## Your Google Sheet

Every application the tool sends is copied to a Google Sheet that you own, one row per job: date applied, company, job title, location, experience, salary, key skills, match score, status, the company's apply link, the Naukri link, the CV used, the role, and notes. Jobs you have to apply to yourself (company-site jobs, and jobs where the recruiter asks questions) are listed too, with their status.

Google does not let any tool write to a Sheet with only the Sheet's link. So you add a small script to your own Sheet, once. It takes about two minutes:

1. Open your Sheet. In its menu, click **Extensions**, then **Apps Script**.
2. Delete whatever is in the editor. On the tool's **Settings** page, open **How to connect your Sheet**, click **Copy the script**, and paste it into the editor. Click the save icon.
3. Click **Deploy**, then **New deployment**. Click the gear icon and choose **Web app**.
4. Set **Execute as: Me** and **Who has access: Anyone**. Click **Deploy**.
5. Google asks you to allow it: choose your account, click **Advanced**, then **Go to (project name)**, then **Allow**.
6. Copy the **Web app URL**, paste it into **Connection link** on the Settings page, and click **Save settings**.

The tool tests the link when you save it. Applications made before you connected are sent straight away. From then on, each apply run updates the Sheet by itself.

Good to know:

- The Sheet is a copy. The tool's own database is the record. If Google cannot be reached, the rows wait and are sent later; nothing is lost.
- A job is never added twice. If its status changes, its row is updated.
- **Send everything to my Sheet now** on the Settings page sends every application again. It is safe to use any time.
- Keep the connection link to yourself. Anyone who has it could add rows to that Sheet. It cannot read your Sheet or reach anything else in your Google account.
- The script is in this project as `sheets/applications_sheet.gs`, so you can read exactly what it does.

### Try it without Naukri

On the **Jobs** page, click **Load sample jobs**. The tool makes up a few jobs from your own role and skills and runs them through the matching engine, so you can see what would be applied to and what would be skipped, and why. Sample jobs are never applied to and never written to your Sheet.

## How matching works

Each job goes through two stages.

**1. Filters.** A job is rejected outright if any of these is true:

- its location is not one of the cities on your role (when you listed cities)
- its salary is below your lowest (when the job shows a salary)
- it was posted longer ago than your job-age limit
- its title has a word you chose to skip, or the company is on your skip list
- it asks for over a year more experience than you have

**2. Score.** Jobs that pass get a score from 0 to 100: how closely the title matches your role (45), how many of the job's skills you have (40), and how well your experience fits (15). Jobs at or above the lowest match score on the **Settings** page are queued to apply.

A job that Naukri lists again under a new ID, with the same company, title and location, is treated as a duplicate and ignored.

## Your data

Your CV and your Naukri login stay on your PC. Your applications stay on your PC and, once you connect it, are copied to your own Google Sheet and nowhere else.

**Registration.** If the first welcome step shows a line saying your name and email are sent to the maker of this tool, then those two details are sent when you click Continue, and nothing else. If you use **Skip setup**, nothing is sent. If that line is not shown, this copy sends nothing.

The dashboard also loads its typeface from Google Fonts; without internet it falls back to your system font.

| What | Where |
|---|---|
| Database, logs, the tool's browser profile, saved pictures of failed pages, a copy of the database from before each upgrade | `%LOCALAPPDATA%\NaukriJobAutomation` |
| Uploaded CVs | the `resumes` folder inside the project |

To start over from scratch, close the tool and delete the `NaukriJobAutomation` folder above.

## Problems

| Problem | Fix |
|---|---|
| "Python was not found" | Install Python 3.11+, ticking **Add python.exe to PATH**, then run `start.bat` again. |
| "Setup did not finish" | The first run needs internet to download its parts. Check the connection and run `start.bat` again. |
| CV upload says no text could be read | The file is probably a scanned image. Export your CV from Word or Google Docs as a normal PDF. |
| The page does not open | Look at the black window for the address, and open it in your browser yourself. |
| Search says Naukri answered "No result found" | Try the same search in your own browser. If jobs show there, Naukri is not giving the tool real results. See [Searching Naukri](#searching-naukri). |
| "Couldn't sign you in. This browser or app may not be secure" while connecting Naukri | That is Google refusing its sign-in inside the tool's window. Log in to Naukri with your password or an OTP instead of **Continue with Google**. |
| "Could not open Microsoft Edge or Google Chrome" | Close any browser window the tool opened earlier and try again. |

## For developers

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
.venv\Scripts\python -m backend
```

The layout and the build roadmap are in [PLAN.md](../PLAN.md). If you are the owner of this repository and want to see who uses the tool, read [owner/SETUP.md](../owner/SETUP.md).
