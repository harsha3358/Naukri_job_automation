from datetime import date, timedelta

from backend.db.models import CandidateProfile, Job, SearchProfile
from backend.services.matching import MatchResult, score_job

TODAY = date(2026, 10, 4)


def make_job(**overrides) -> Job:
    values = dict(
        naukri_job_id="1",
        title="Frontend Developer",
        company="Acme Tech",
        location="Hyderabad",
        experience_min=0,
        experience_max=2,
        salary_min_lpa=None,
        salary_max_lpa=None,
        skills=["React.js", "JavaScript", "HTML", "CSS", "Redux"],
        description="",
        posted_on=TODAY - timedelta(days=1),
    )
    values.update(overrides)
    return Job(**values)


def make_role(**overrides) -> SearchProfile:
    values = dict(
        role="Frontend Developer",
        locations=["Hyderabad"],
        min_salary_lpa=None,
        max_job_age_days=7,
        exclude_keywords=[],
        exclude_companies=[],
    )
    values.update(overrides)
    return SearchProfile(**values)


def make_candidate(**overrides) -> CandidateProfile:
    values = dict(experience_years=0.0, skills=["React", "JavaScript", "HTML", "CSS", "Next.js", "Git"])
    values.update(overrides)
    return CandidateProfile(**values)


def match(job=None, role=None, candidate=None) -> MatchResult:
    return score_job(job or make_job(), role or make_role(), candidate or make_candidate(), today=TODAY)


# --- score -------------------------------------------------------------------


def test_a_job_that_fits_scores_high():
    result = match()
    assert result.score >= 90
    assert not result.excluded


def test_a_different_job_scores_below_the_default_threshold():
    backend = make_job(title="Backend Java Developer", skills=["Java", "Spring Boot", "Hibernate", "MySQL"])
    assert match(backend).score < 60


def test_jobs_rank_in_a_sensible_order():
    perfect = match().score
    partial_skills = match(make_job(skills=["React", "TypeScript", "GraphQL", "Redux", "Jest", "Webpack"])).score
    wrong_role = match(make_job(title="Sales Executive", skills=["Sales", "Communication"])).score
    assert perfect > partial_skills > wrong_role


def test_title_spelling_variants_still_match():
    assert "Title: 2 of 2 role words found" in match(make_job(title="Jr. Front End Engineer (React.js)")).notes


def test_java_role_does_not_fully_match_a_javascript_title():
    result = match(make_job(title="JavaScript Developer"), make_role(role="Java Developer"))
    assert "Title: 1 of 2 role words found" in result.notes


def test_one_year_short_on_experience_lowers_the_score_but_is_allowed():
    result = match(make_job(experience_min=1, experience_max=3))
    assert not result.excluded
    assert result.score < match().score


def test_missing_job_details_neither_help_nor_hurt():
    assert match(make_job(experience_min=None, experience_max=None)).score == match().score
    assert match(make_job(location="")).score == match().score
    assert match(make_job(posted_on=None)).score == match().score


def test_filler_tags_do_not_drag_the_skills_score_down():
    # Tags as seen on a real Naukri card: three real skills among five filler words.
    padded = make_job(
        skills=["Computer science", "Front end", "Coding", "React.js", "Web development", "HTML", "Information technology", "CSS"]
    )
    result = match(padded)
    assert "Skills: 3 of 3 match (React, HTML, CSS)" in result.notes
    assert result.score == match().score


def test_a_tag_the_user_lists_counts_even_if_the_tool_does_not_know_it():
    result = match(make_job(skills=["Zoho Creator", "Deluge"]), candidate=make_candidate(skills=["Zoho Creator"]))
    assert "Skills: 1 of 1 match (Zoho Creator)" in result.notes


def test_skills_come_from_the_description_when_the_job_lists_none():
    result = match(make_job(skills=[], description="We use React and JavaScript."))
    assert "Skills: 2 of 2 match (JavaScript, React)" in result.notes


# --- filters -----------------------------------------------------------------


def assert_rejected(result: MatchResult, reason: str) -> None:
    assert result.excluded
    assert result.score == 0
    assert any(reason in note for note in result.notes), result.notes


def test_excluded_title_word_rejects_the_job():
    assert_rejected(match(make_job(title="Senior Frontend Developer"), make_role(exclude_keywords=["senior"])), 'contains "senior"')


def test_excluded_word_must_be_a_whole_word():
    assert not match(make_job(title="Frontend Developer Internship"), make_role(exclude_keywords=["intern"])).excluded


def test_excluded_company_rejects_the_job():
    assert_rejected(match(make_job(company="Acme Tech Pvt Ltd"), make_role(exclude_companies=["acme tech"])), "companies to skip")


def test_job_outside_the_chosen_cities_is_rejected():
    assert_rejected(match(make_job(location="Pune")), "not one of your cities")


def test_any_city_is_fine_when_none_are_chosen():
    assert not match(make_job(location="Pune"), make_role(locations=[])).excluded


def test_city_spellings_are_treated_as_the_same_place():
    assert match(make_job(location="Bengaluru"), make_role(locations=["Bangalore"])).score == match().score
    assert match(make_job(location="Work from home"), make_role(locations=["Remote"])).score == match().score
    assert not match(make_job(location="Hybrid - Pune, Hyderabad (+2 more)")).excluded


def test_salary_below_the_lowest_is_rejected_but_undisclosed_is_not():
    wants_salary = make_role(min_salary_lpa=4)
    assert_rejected(match(make_job(salary_max_lpa=3), wants_salary), "below your lowest")
    assert match(make_job(), wants_salary).score == match().score
    assert match(make_job(salary_max_lpa=6), wants_salary).score == match().score


def test_an_old_posting_is_rejected():
    assert_rejected(match(make_job(posted_on=TODAY - timedelta(days=20))), "older than your 7-day limit")


def test_a_job_needing_far_more_experience_is_rejected():
    assert_rejected(match(make_job(experience_min=3, experience_max=5)), "job needs 3+ yrs")
    experienced = make_candidate(experience_years=2.5)
    assert not match(make_job(experience_min=3, experience_max=5), candidate=experienced).excluded
