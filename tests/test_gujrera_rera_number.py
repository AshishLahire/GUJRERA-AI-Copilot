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


def test_numbers_as_shown_on_the_public_portal():
    """Formats seen in the portal's search results (2026): an extra end date, 2-letter agent codes, renewals."""
    p = parse_rera_number("PR/GJ/GANDHINAGAR/GANDHINAGAR/Gandhinagar Municipal Corporation/MAA14450/301124/311228")
    assert p.kind == "project" and p.code == "MAA14450" and p.reg_date == date(2024, 11, 30) and not p.warnings
    assert p.authority == "GANDHINAGAR MUNICIPAL CORPORATION" and p.normalised.endswith("/MAA14450/301124/311228")
    a = parse_rera_number("AG/GJ/GANDHINAGAR/GANDHINAGAR/AA06250/240231R1")
    assert a.kind == "agent" and a.code == "AA06250" and a.normalised.endswith("/AA06250/240231R1") and not a.warnings
    ex = parse_rera_number("PR/GJ/GANDHINAGAR/KALOL/AUDA/RAA01953/EX1/170621")  # extension marker
    assert ex.code == "RAA01953" and ex.reg_date == date(2021, 6, 17) and ex.normalised.endswith("/RAA01953/EX1/170621")
    alt = parse_rera_number("PR/GJ/GANDHINAGAR/GANDHINAGAR/Others/RAA15048/A1M/131025/311230")  # alteration marker
    assert alt.code == "RAA15048" and alt.reg_date == date(2025, 10, 13) and not alt.warnings
    rn = parse_rera_number("PR/GJ/GANDHINAGAR/DAHEGAM/Ahmedabad Urban Development Authority/RN366AA10266/201023")
    assert rn.code == "RN366AA10266" and rn.reg_date == date(2023, 10, 20) and not rn.warnings
    found = find_rera_numbers("Call now! RERA: PR/GJ/GANDHINAGAR/KALOL/AUDA/PAA00295/280917, site visit Sunday")
    assert [n.normalised for n in found] == ["PR/GJ/GANDHINAGAR/KALOL/AUDA/PAA00295/280917"]
