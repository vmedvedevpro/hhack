from hhack.integrations.hh.urls import (
    extract_hh_id,
    extract_resume_id,
    search_url_with_page,
    vacancy_url,
)


def test_vacancy_url_roundtrip():
    assert extract_hh_id(vacancy_url(123456789)) == 123456789


def test_extract_hh_id_ignores_query_params():
    assert extract_hh_id("https://hh.ru/vacancy/42?from=feed&hhtmFrom=x") == 42


def test_extract_hh_id_returns_none_on_unrelated_url():
    assert extract_hh_id("https://hh.ru/employer/123") is None


def test_extract_resume_id_returns_id_from_search_url():
    url = "https://hh.ru/search/vacancy?" "resume=abc123def&hhtmFromLabel=rec_vacancy_show_all&hhtmFrom=main"
    assert extract_resume_id(url) == "abc123def"


def test_extract_resume_id_returns_none_when_absent():
    assert extract_resume_id("https://hh.ru/search/vacancy?text=python") is None


def test_search_url_with_page_appends_when_missing():
    url = "https://hh.ru/search/vacancy?resume=abc&hhtmFromLabel=rec_vacancy_show_all"
    paged = search_url_with_page(url, 3)
    assert "page=3" in paged
    assert "resume=abc" in paged
    assert "hhtmFromLabel=rec_vacancy_show_all" in paged


def test_search_url_with_page_replaces_existing_page_param():
    url = "https://hh.ru/search/vacancy?resume=abc&page=0&hhtmFromLabel=x"
    paged = search_url_with_page(url, 5)
    assert paged.count("page=") == 1
    assert "page=5" in paged
    assert "resume=abc" in paged
