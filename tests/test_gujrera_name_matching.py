"""Name matching on registries with many similar names: made-up names are not answered as real projects,
and a name written in full wins over a shorter name inside it."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from gujrera.chat.orchestrator import ChatState, _name_in_question, respond
from gujrera.chat.understand import _INDEX, find_candidates
from gujrera.db.models import Project, Promoter
from gujrera.db.repository import Principal, Repository
from gujrera.db.session import init_db, make_engine, session_factory

NAMES = ["86 Residency", "RADHE KRISHNA  RESIDENCY", "KRISHNA RESIDENCY", "RHYTHM SKY", "THE RHYTHM SKYLINE",
         "Sunrise Skyz", "SKYLINE", "NILKANTH HEIGHT", "NILKANTH HEIGHTS-B", "BANSARI SKYVIEW"]


@pytest.fixture()
def session(tmp_path: Path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'n.sqlite').as_posix()}")
    init_db(engine)
    with session_factory(engine)() as s:
        prom = Promoter(name="Promoter not in imported records", promoter_type="unknown", district="Surat",
                        source_url="https://gujrera.gujarat.gov.in/", is_mock=False)
        s.add(prom)
        s.flush()
        for i, n in enumerate(NAMES, 1):
            s.add(Project(rera_no=f"PR/GJ/SURAT/SURAT CITY/SUDA/RAA{70000 + i}/010120", name=n, promoter_id=prom.id,
                          district="Surat", taluka="Surat City", project_type="residential", status="ongoing",
                          units=10, reg_date=date(2020, 1, 1), proposed_completion=date(2029, 4, 30),
                          reg_valid_until=date(2029, 4, 30), source_url="https://gujrera.gujarat.gov.in/", is_mock=False))
        s.commit()
        _INDEX.clear()
        yield s
    engine.dispose()


def _labels(session, text):
    return [c.label for c in find_candidates(session, text)]


@pytest.mark.parametrize("question", ["બ્લૂ લગૂન રેસિડેન્સી ક્યારે પૂર્ણ થશે?", "મૂનલિટ રેસિડેન્સી વિશે જણાવો",
                                      "when will i get possession of sunrise skyline towers?"])
def test_made_up_names_find_nothing(session, question):
    assert _labels(session, question.lower()) == []
    assert find_candidates(session, "sunrise skyline towers", threshold=90) == []  # the AI path's threshold


@pytest.mark.parametrize("question,expected", [
    ("radhe krishna  residency નું પઝેશન ક્યારે મળશે?", "RADHE KRISHNA  RESIDENCY"),
    ("the rhythm skyline के खिलाफ कितनी शिकायतें हैं?", "THE RHYTHM SKYLINE"),
    ("nilkanth heights-b के खिलाफ कितनी शिकायतें हैं?", "NILKANTH HEIGHTS-B"),
])
def test_the_name_written_in_full_wins(session, question, expected):
    assert _labels(session, question) == [expected]


def test_typos_still_match_on_the_ai_path(session):
    assert [c.label for c in find_candidates(session, "bansari skyveiw possession", threshold=90)] == ["BANSARI SKYVIEW"]


def test_the_chat_answers_the_full_name_instead_of_asking_which_one(session):
    repo = Repository(session, Principal.anonymous(), audit_sink=lambda _r: None)
    r = respond("RADHE KRISHNA  RESIDENCY નું પઝેશન ક્યારે મળશે?", ChatState(), repo).to_dict()
    assert r["intent"] == "possession" and "RAA70002" in r["sources"][0]["id"]


def test_names_from_the_ai_must_stand_in_the_question():
    q = "When will I get possession of Sunrise Skyline Towers?"
    assert _name_in_question("Sunrise Skyline Towers", q)
    assert not _name_in_question("Skyline", q)  # shortened by the model
    assert not _name_in_question("Bansari Skyview", "kab tak milega bhai woh wala flat??")  # not asked at all
    assert _name_in_question("Bansari Skyview", "bansari skyveiw kab milega")  # a corrected typo
    assert _name_in_question("Bansari Skyview", "બંસરી સ્કાયવ્યુ નું પઝેશન ક્યારે?")  # by sound, in Gujarati
