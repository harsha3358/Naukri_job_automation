from datetime import date

import pytest

from backend.naukri.parse import (
    build_search_url,
    job_from_card,
    next_page_url,
    parse_experience,
    parse_posted,
    parse_salary,
)

TODAY = date(2026, 10, 4)


def test_search_url_matches_what_naukri_itself_produces():
    assert build_search_url("Frontend Developer", "Hyderabad", 0.0, 7) == (
        "https://www.naukri.com/frontend-developer-jobs-in-hyderabad?k=frontend%20developer&l=hyderabad&experience=0&jobAge=7"
    )


def test_search_url_without_city_or_experience():
    assert build_search_url("  React   Developer ", None, None, 3) == (
        "https://www.naukri.com/react-developer-jobs?k=react%20developer&jobAge=3"
    )
    assert build_search_url("QA", "New Delhi", 2.5, 15) == (
        "https://www.naukri.com/qa-jobs-in-new-delhi?k=qa&l=new%20delhi&experience=2&jobAge=15"
    )


def test_next_page_is_built_from_the_address_naukri_redirected_to():
    # Naukri rewrote "-in-hyderabad" to "-in-hyderabad-secunderabad"; the page number goes after that.
    page_1 = "https://www.naukri.com/ai-engineer-jobs-in-hyderabad-secunderabad?k=ai%20engineer&l=hyderabad&jobAge=7"
    page_2 = next_page_url(page_1, 1)
    assert page_2 == "https://www.naukri.com/ai-engineer-jobs-in-hyderabad-secunderabad-2?k=ai%20engineer&l=hyderabad&jobAge=7"
    assert next_page_url(page_2, 2) == page_2.replace("secunderabad-2?", "secunderabad-3?")


def test_search_url_keeps_symbols_in_the_keyword_but_not_in_the_path():
    url = build_search_url("C++ Developer", None, None, 7)
    assert url == "https://www.naukri.com/c-developer-jobs?k=c%2B%2B%20developer&jobAge=7"


@pytest.mark.parametrize(
    "text, url, expected",
    [
        ("0-1 Yrs", "", (0, 1)),
        ("0 Yrs", "", (0, 0)),
        ("5-10 Yrs", "", (5, 10)),
        ("3+ Yrs", "", (3, None)),
        ("", "https://www.naukri.com/job-listings-intern-acme-hyderabad-0-to-5-years-011026503993", (0, 5)),
        ("", "https://www.naukri.com/job-listings-something", (None, None)),
    ],
)
def test_experience(text, url, expected):
    assert parse_experience(text, url) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("2-5 Lacs PA", (2.0, 5.0)),
        ("3.5-7 Lacs PA", (3.5, 7.0)),
        ("", (None, None)),
        ("Not disclosed", (None, None)),
        ("Unpaid", (0.0, 0.0)),
        ("10,000/month", (1.2, 1.2)),
        ("50,000-75,000 PA", (0.5, 0.75)),
        ("50 Lacs-1 Cr PA", (50.0, 100.0)),
        ("1-1.5 Cr PA", (100.0, 150.0)),
    ],
)
def test_salary_in_lakhs_per_year(text, expected):
    assert parse_salary(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("4 days ago", date(2026, 9, 30)),
        ("1 day ago", date(2026, 10, 3)),
        ("Just now", TODAY),
        ("Few hours ago", TODAY),
        ("Today", TODAY),
        ("30+ days ago", date(2026, 9, 4)),
        ("2 weeks ago", date(2026, 9, 20)),
        ("Starts in 1-3 months", None),
        ("", None),
    ],
)
def test_posted_date(text, expected):
    assert parse_posted(text, TODAY) == expected


def test_card_becomes_a_job():
    job = job_from_card(
        {
            "id": "011026000089",
            "url": "https://www.naukri.com/job-listings-software-engineer-acme-hyderabad-0-to-2-years-011026000089",
            "title": " Software Engineer ",
            "company": "Acme",
            "experience": "0-2 Yrs",
            "salary": "3.5-7 Lacs PA",
            "location": "Hybrid - Hyderabad, Pune, Bengaluru",
            "description": "Build things.",
            "posted": "3 days ago",
            "skills": ["React", " ", "Node.js"],
        },
        TODAY,
    )
    assert (job.naukri_job_id, job.title, job.company) == ("011026000089", "Software Engineer", "Acme")
    assert (job.experience_min, job.experience_max, job.salary_min_lpa, job.salary_max_lpa) == (0, 2, 3.5, 7.0)
    assert job.location == "Hybrid - Hyderabad, Pune, Bengaluru"
    assert job.skills == ["React", "Node.js"]
    assert job.posted_on == date(2026, 10, 1)
    assert not job.is_demo


def test_card_without_an_id_or_title_is_dropped():
    assert job_from_card({"id": "", "title": "Developer"}, TODAY) is None
    assert job_from_card({"id": "123", "title": "  "}, TODAY) is None
