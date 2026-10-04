# Naukri Job Automation

**It finds the jobs on Naukri that fit you, applies for you, and logs every application in your Google Sheet.**

It runs on your own Windows PC. Your data stays with you.

## What you get

| | |
|---|---|
| **Finds** | Searches Naukri for the roles and cities you choose |
| **Filters** | Keeps only jobs that fit your skills, salary and experience, and tells you why it skipped the rest |
| **Applies** | Clicks Apply for you, up to a daily limit you set |
| **Tracks** | One row per application in your own Google Sheet |

## What it will not do

- **Apply on company websites.** It hands you the company's link instead.
- **Answer a recruiter's questions.** It hands you those jobs to finish.
- **Get past a CAPTCHA, an OTP or any Naukri check.** It stops and waits for you.
- **Run on a schedule.** For now, you press the buttons.

## The one risk to know

Naukri's rules do not allow automated tools. Your account could be restricted.

The tool works slowly and caps how many jobs it applies to each day. That lowers the risk. It does not remove it. Naukri may also, at times, stop showing the tool real search results.

The decision is yours.

## Start in 3 steps

1. Install [Python 3.11 or newer](https://www.python.org/downloads/). Tick **Add python.exe to PATH**.
2. Download this project and double-click **start.bat**.
3. Follow the welcome screen: your name, your CV, the job you want.

Then, on the **Settings** page:

- **Connect Naukri.** You log in yourself, with your password or an OTP. Google sign-in does not work in the tool's window.
- **Connect your Google Sheet.** Two minutes, once. The steps are on the page.

## Using it

| Step | Where | What happens |
|---|---|---|
| 1 | **Jobs → Search Naukri now** | Finds and scores jobs |
| 2 | **Jobs → Practice run** | Shows what it would apply to. Sends nothing |
| 3 | **Settings → Real applications**, then **Jobs → Apply** | Sends real applications |

Start with the practice run. An application cannot be taken back.

## Your data

- Your CV and your Naukri login stay on your PC. The tool never sees your password.
- Your applications go to your own Google Sheet, and nowhere else.
- If the welcome screen says so, your name and email go to the maker of this tool. Nothing else does. Use **Skip setup** to send nothing.

## Where it stands

| Working today | Not yet |
|---|---|
| Search, matching, applying through Naukri's own Apply button, Google Sheet log, light and dark theme | Answering recruiters' questions, running on a schedule |

## More

- [Full guide](docs/GUIDE.md): every step, how matching works, and fixes for common problems
- [Plan](PLAN.md): what is built and what is next
- [For the owner](owner/SETUP.md): see who is using the tool
