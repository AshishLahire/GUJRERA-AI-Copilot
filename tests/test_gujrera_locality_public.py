"""Locality questions on public records, which carry no address: answer from project names, and say so."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select, update

from gujrera.chat.basics import locality_list
from gujrera.db.models import Project
from gujrera.db.repository import Principal, Repository
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.ingest.mock_generator import MockConfig, generate


@pytest.fixture()
def repo(tmp_path: Path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'l.sqlite').as_posix()}")
    init_db(engine)
    with session_factory(engine)() as s:
        generate(s, MockConfig())
        s.execute(update(Project).where(Project.district == "Ahmedabad").values(locality=None))  # like public data
        p = s.scalar(select(Project).where(Project.district == "Ahmedabad").order_by(Project.id))
        p.name = "Shivam Heights, Gota"
        q = s.scalar(select(Project).where(Project.district == "Surat").order_by(Project.id))
        q.locality = "Vesu"  # a district whose records do carry localities
        s.commit()
        yield Repository(s, Principal.anonymous(), audit_sink=lambda _row: None)
    engine.dispose()


def test_name_match_with_an_honest_note(repo):
    sentences, card, ids = locality_list(repo, "Gota", "en")
    assert "do not give project addresses" in sentences[0].text and "1 registered project" in sentences[0].text
    assert card["match"] == "name" and len(ids) == 1
    gu, _card, _ids = locality_list(repo, "Gota", "gu")
    assert "ગોતા" in gu[0].text and "સરનામું નથી" in gu[0].text


def test_no_name_match_gives_district_totals_not_a_bare_not_found(repo):
    sentences, _card, ids = locality_list(repo, "Bopal", "en")
    assert ids == [] and "cannot list projects in Bopal" in sentences[0].text and "Ahmedabad district has" in sentences[0].text


def test_records_with_localities_keep_the_exact_answer(repo):
    sentences, card, ids = locality_list(repo, "Vesu", "en")
    assert "match" not in card and len(ids) == 1 and "do not give project addresses" not in sentences[0].text
