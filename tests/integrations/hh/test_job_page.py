from datetime import UTC, datetime

from hhack.integrations.hh.job_page import (
    _json_ld_location,
    _json_ld_salary,
    _parse_iso_datetime,
    _strip_html,
    combine_extracted,
)


def test_strip_html_keeps_list_structure():
    text = _strip_html("<p>Hello</p><ul><li>One</li><li>Two</li></ul>")
    assert text == "Hello\n\nOne\nTwo"


def test_strip_html_unescapes_entities():
    assert _strip_html("R&amp;D and &lt;b&gt;") == "R&D and <b>"


def test_strip_html_returns_none_for_blank():
    assert _strip_html(None) is None
    assert _strip_html("") is None
    assert _strip_html("<p></p>") is None


def test_json_ld_location_prefers_locality():
    place = {
        "address": {
            "addressLocality": "Москва",
            "addressRegion": "Москва",
            "addressCountry": "RU",
        }
    }
    assert _json_ld_location(place) == "Москва"


def test_json_ld_location_falls_back_to_region_then_country():
    assert _json_ld_location({"address": {"addressRegion": "Татарстан"}}) == "Татарстан"
    assert _json_ld_location({"address": {"addressCountry": "RU"}}) == "RU"
    assert _json_ld_location({"address": {}}) is None
    assert _json_ld_location(None) is None


def test_json_ld_location_handles_list():
    places = [{"address": {"addressLocality": "Казань"}}]
    assert _json_ld_location(places) == "Казань"


def test_json_ld_salary_single_value():
    assert _json_ld_salary({"currency": "RUR", "value": {"value": 250000, "unitText": "MONTH"}}) == "250000 RUR"


def test_json_ld_salary_range():
    assert (
        _json_ld_salary({"currency": "RUR", "value": {"minValue": 200000, "maxValue": 300000}}) == "200000-300000 RUR"
    )


def test_json_ld_salary_missing_returns_none():
    assert _json_ld_salary(None) is None
    assert _json_ld_salary({"currency": "RUR"}) is None
    assert _json_ld_salary({"currency": "RUR", "value": {}}) is None


def test_parse_iso_datetime_handles_offset_and_z():
    dt = _parse_iso_datetime("2026-05-22T13:08:20.796+03:00")
    assert dt is not None and dt.utcoffset() is not None
    assert _parse_iso_datetime("2026-05-22T10:08:20Z") == datetime(2026, 5, 22, 10, 8, 20, tzinfo=UTC)
    assert _parse_iso_datetime(None) is None
    assert _parse_iso_datetime("not-a-date") is None


def test_combine_prefers_dom_when_present():
    raw = {
        "dom": {
            "full_text": "DOM description",
            "salary": "от 200 000 ₽",
            "location": "Москва, Кутузовская",
            "employment_type": "Полная занятость",
            "posted_at_iso": "2026-05-20T10:00:00+00:00",
        },
        "json_ld": {
            "description": "<p>LD description</p>",
            "datePosted": "2020-01-01T00:00:00+00:00",
            "jobLocation": {"address": {"addressLocality": "Какой-то-другой-город"}},
            "baseSalary": {"currency": "RUR", "value": {"value": 1}},
        },
    }
    d = combine_extracted(raw, hh_id=42)
    assert d.hh_id == 42
    assert d.full_text == "DOM description"
    assert d.salary == "от 200 000 ₽"
    assert d.location == "Москва, Кутузовская"
    assert d.employment_type == "Полная занятость"
    assert d.posted_at is not None and d.posted_at.year == 2026


def test_combine_falls_back_to_json_ld_when_dom_blank():
    raw = {
        "dom": {
            "full_text": None,
            "salary": None,
            "location": None,
            "employment_type": "Полная занятость",
            "posted_at_iso": None,
        },
        "json_ld": {
            "description": "<p>Мы делаем X.</p><ul><li>A</li><li>B</li></ul>",
            "datePosted": "2026-05-22T13:08:20.796+03:00",
            "jobLocation": {"address": {"addressLocality": "Москва"}},
            "baseSalary": {"currency": "RUR", "value": {"minValue": 100000, "maxValue": 150000}},
        },
    }
    d = combine_extracted(raw, hh_id=7)
    assert d.full_text == "Мы делаем X.\n\nA\nB"
    assert d.salary == "100000-150000 RUR"
    assert d.location == "Москва"
    assert d.employment_type == "Полная занятость"
    assert d.posted_at is not None and d.posted_at.day == 22


def test_combine_handles_missing_json_ld():
    raw = {
        "dom": {
            "full_text": "Only DOM",
            "salary": None,
            "location": None,
            "employment_type": None,
            "posted_at_iso": None,
        },
        "json_ld": None,
    }
    d = combine_extracted(raw, hh_id=1)
    assert d.full_text == "Only DOM"
    assert d.salary is None
    assert d.location is None
    assert d.employment_type is None
    assert d.posted_at is None


def test_combine_handles_completely_empty_payload():
    d = combine_extracted({}, hh_id=99)
    assert d.hh_id == 99
    assert d.full_text is None
    assert d.salary is None
    assert d.location is None
    assert d.employment_type is None
    assert d.posted_at is None
