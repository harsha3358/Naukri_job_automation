"""Everything the tool knows about how Naukri's pages are built, in one place.

When Naukri changes its site, this is the file to fix. Last checked against the live site
on 2026-10-04.
"""

BASE_URL = "https://www.naukri.com"

# Opening this while logged out sends the browser to Naukri's login page, and back here
# after a successful login. Being on a /mnjuser/ page therefore means "logged in".
ACCOUNT_HOME_URL = f"{BASE_URL}/mnjuser/homepage"
ACCOUNT_PATH_PREFIX = "/mnjuser/"

# --- search results page ---
RESULTS_PER_PAGE = 20
JOB_CARD = ".srp-jobtuple-wrapper[data-job-id]"
NO_RESULTS = '[class*="no-result-container"]'
# "No result found for '...'" shown ABOVE a list of other jobs Naukri suggests instead. Those
# cards are not results for the search (seen: other cities), so the page counts as empty.
# The double underscore matters: normal result pages contain hidden loading placeholders
# whose class starts "styles_failover-shimmer__", and those must not match.
FALLBACK_NOTICE = '[class*="styles_failover__"]'
CARD_LINK = "a.title"
CARD_SKILL = ".tags-gt .tag-li"
CARD_TEXT_FIELDS = {
    "title": "a.title",
    "company": "a.comp-name",
    "experience": ".expwdth",  # "0-1 Yrs"; missing on internship cards
    "salary": ".sal-wrap",  # "2-5 Lacs PA", "Unpaid"; missing when not disclosed
    "location": ".locWdth",  # "Hybrid - Hyderabad, Pune, Bengaluru"
    "description": ".job-desc",
    "posted": ".job-post-day",  # "4 days ago"
}

# --- job page (seen logged in, 2026-10-04) ---
# A job ends up showing exactly one of these two, but every job starts with the plain Apply
# button, and it is swapped for the company-site one only after the job's data has loaded.
# Logged out, a company-site job keeps the plain button (it leads to the login page).
APPLY_BUTTON = "#apply-button"
COMPANY_SITE_BUTTON = "#company-site-button"
# The page loads its own job data from an address containing this. In that data:
#   loggedIn                      true when Naukri treats the browser as logged in
#   jobDetails.applyRedirectUrl   only on company-site jobs: the company's link
#   jobDetails.applyDate          only on jobs already applied to, e.g. "2026-10-04 08:36:13"
#                                 (the page then shows span#already-applied instead of a button)
JOB_DATA_PATH = "/jobapi/v4/job/"

# Clicking Apply makes the page send the application to an address containing this. Seen on the
# first real application (Capgemini, 2026-10-04), the answer was:
#   applyStatus: {"<job id>": 200}
#   jobs: [{"jobId": "<job id>", "status": 200, "message": "You have successfully applied to this job."}]
#   quotaDetails: {"dailyApplied": 1, "dailyQuota": 50, "monthlyApplied": 1, "monthlyQuota": 2000}
# A chat panel may open afterwards asking the user to complete their Naukri profile. That is not
# part of the application (it was already confirmed) and the tool leaves it alone.
APPLY_REQUEST_PATH = "/apply-workflow/v1/apply"
APPLIED_STATUS = 200

# Runs inside the page: turns each job card into a plain dict of the texts above.
READ_CARDS_JS = """
(cards, sel) => cards.map(card => {
  const text = s => { const el = card.querySelector(s); return el ? el.textContent.trim() : ""; };
  const link = card.querySelector(sel.link);
  const job = {
    id: card.dataset.jobId || "",
    url: link ? link.href : "",
    skills: [...card.querySelectorAll(sel.skill)].map(el => el.textContent.trim()),
  };
  for (const [name, s] of Object.entries(sel.fields)) job[name] = text(s);
  return job;
})
"""
