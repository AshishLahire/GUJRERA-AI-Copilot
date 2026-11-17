from datetime import date

import pytest

from gujrera.trust.rera_number import find_rera_numbers, parse_rera_number


def test_parses_clean_project_number():
    r = parse_rera_number("PR/GJ/AHMEDABAD/AHMEDABAD CITY/AUDA/RAA01234/150321")
    assert r is not None
    assert (r.kind, r.district, r.taluka, r.authority, r.code) == (
        "project", "AHMEDABAD", "AHMEDABAD CITY", "AUDA", "RAA01234")
    assert r.reg_date == date(2021, 3, 15)
    assert not r.is_mock and r.warnings == ()


@pytest.mark.parametrize("noisy", [
    "pr / gj / ahmedabad / ahmedabad city / auda / RAA01234 / 150321",
    r"PR\GJ\AHMEDABAD\AHMEDABAD CITY\AUDA\RAA01234\150321",
    "PR|GJ|AHMEDABAD|AHMEDABAD CITY|AUDA|RAAO1234|15O321",
    "PR/GJ/AHMEDABAD/AHMEDABAD  CITY/AUDA/RAA01234/150321 Book now!",
])
def test_normalises_ocr_noise(noisy):
    r = parse_rera_number(noisy)
    assert r is not None
    assert r.normalised == "PR/GJ/AHMEDABAD/AHMEDABAD CITY/AUDA/RAA01234/150321"


def test_agent_and_mock_numbers():
    a = parse_rera_number("AG/GJ/VADODARA/VADODARA/VUDA/MOCK50001/010120")
    assert a.kind == "agent" and a.is_mock


def test_missing_date_and_bad_date_are_warnings():
    assert "missing_date" in parse_rera_number("PR/GJ/SURAT/SURAT CITY/SUDA/RAA01234").warnings
    assert "invalid_date" in parse_rera_number("PR/GJ/SURAT/SURAT CITY/SUDA/RAA01234/310221").warnings


@pytest.mark.parametrize("junk", ["", "hello", "PR/MH/PUNE/P52100001234", "GJ/PR/X/Y/Z"])
def test_rejects_non_gujarat_or_junk(junk):
    assert parse_rera_number(junk) is None


def test_finds_numbers_in_free_text():
    text = (
        "Luxury 2BHK! RERA No: PR\\GJ\\AHMEDABAD\\DASKROI\\AUDA\\RAA07226\\200620, call now;\n"
        "Also PR/GJ/SURAT/OLPAD/SUDA/RAA11111/010122 and again PR/GJ/SURAT/OLPAD/SUDA/RAA11111/010122"
    )
    found = {r.normalised for r in find_rera_numbers(text)}
    assert found == {
        "PR/GJ/AHMEDABAD/DASKROI/AUDA/RAA07226/200620",
        "PR/GJ/SURAT/OLPAD/SUDA/RAA11111/010122",
    }
