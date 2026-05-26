from hhack.integrations.hh.urls import extract_hh_id, vacancy_url


def test_vacancy_url_roundtrip():
    assert extract_hh_id(vacancy_url(123456789)) == 123456789


def test_extract_hh_id_ignores_query_params():
    assert extract_hh_id("https://hh.ru/vacancy/42?from=feed&hhtmFrom=x") == 42


def test_extract_hh_id_returns_none_on_unrelated_url():
    assert extract_hh_id("https://hh.ru/employer/123") is None
