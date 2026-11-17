"""Legal RAG: section splitting, glossary, retrieval, grounded answers, chat routing.

Uses a small synthetic index, so it does not need the downloaded PDFs. Needs the cached
multilingual-e5 model (skipped otherwise).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("sentence_transformers")

import gujrera.legal.answer as legal_answer_mod  # noqa: E402
import gujrera.legal.search as search_mod  # noqa: E402
from gujrera.chat.orchestrator import ChatState, respond  # noqa: E402
from gujrera.db.repository import Principal, Repository  # noqa: E402
from gujrera.db.session import init_db, make_engine, session_factory  # noqa: E402
from gujrera.ingest.mock_generator import MockConfig, generate  # noqa: E402
from gujrera.legal.build import Chunk, build_index, split_annexure, split_sections  # noqa: E402
from gujrera.legal.glossary import expand  # noqa: E402
from gujrera.legal.search import LegalIndex  # noqa: E402

ACT_PAGES = [
    "THE REAL ESTATE (REGULATION AND DEVELOPMENT) ACT, 2016\n\n"
    "Short title.\n1. (1) This Act may be called the Real Estate Act.\n\n"
    "Definitions.\n2. In this Act, unless the context otherwise requires,—\n(a) “allottee” means a person.\n"
    "1. a list item that must not become a section\n\n"
    "Prior registration of real estate project with Real Estate Regulatory Authority.\n"
    "3. (1) No promoter shall advertise, market, book, sell or offer for sale any plot, apartment or "
    "building in any real estate project without registering the project with the Authority.\n",
    "No deposit or advance to be taken by promoter without first entering into agreement for sale.\n"
    "AZ: A promoter shall not accept a sum more than ten per cent of the cost of the apartment as an advance "
    "payment without first entering into a written agreement for sale.\n\n"
    "Return of amount and compensation.\n"
    "5. (1) If the promoter fails to complete or is unable to give possession of an apartment, he shall be "
    "liable to return the amount received with interest at such rate as may be prescribed, or pay interest "
    "for every month of delay till the handing over of the possession.\n",
]
RULE_PAGES = [
    "1. Short title.- These rules may be called the Gujarat Rules.\n"
    "2. Definitions.- In these rules, unless the context otherwise requires.\n"
    "3. Rate of interest payable by the promoter and the allottee.- The rate of interest shall be the "
    "State Bank of India highest marginal cost of lending rate plus two percent.\n"
    "Annexure ‘A’\n1. The Allottee agrees to buy the apartment.\n2. The price is fixed.\n",
]


def test_split_sections_act_style_with_margin_titles_and_garbled_number():
    secs = split_sections(ACT_PAGES)
    assert [n for n, *_ in secs] == ["1", "2", "3", "4", "5"]
    titles = {n: t for n, t, _, _ in secs}
    assert titles["3"].startswith("Prior registration")
    assert titles["4"].startswith("No deposit or advance")  # "AZ:" heading inferred as section 4
    assert titles["5"] == "Return of amount and compensation"
    body5 = next(b for n, _, b, _ in secs if n == "5")
    assert body5.startswith("Return of amount") and "every month of delay" in body5


def test_split_rules_and_annexure():
    pages, annexure = split_annexure(RULE_PAGES)
    secs = split_sections(pages)
    assert [n for n, *_ in secs] == ["1", "2", "3"]
    assert secs[2][1] == "Rate of interest payable by the promoter and the allottee"
    assert annexure.startswith("Annexure") and "The price is fixed" in annexure


def test_glossary_expansion():
    assert "possession" in expand("પઝેશનમાં મોડું") and "delay" in expand("पज़ेशन में देरी")
    assert expand("plain english question") == "plain english question"
    assert "rule" not in expand("કયો નિયમ છે").split()  # meta words are not expanded


@pytest.fixture(scope="module")
def index(tmp_path_factory):
    tmp: Path = tmp_path_factory.mktemp("legal")
    engine = make_engine(f"sqlite:///{(tmp / 'db.sqlite').as_posix()}")
    init_db(engine)
    with session_factory(engine)() as s:
        generate(s, MockConfig(seed=4))
        chunks = []
        for num, title, body, page in split_sections(ACT_PAGES):
            chunks.append(Chunk(f"act:{num}:0", "act", "RERA Act, 2016", num, title, body, page))
        pages, _ = split_annexure(RULE_PAGES)
        for num, title, body, page in split_sections(pages):
            chunks.append(Chunk(f"rules:{num}:0", "rules", "Gujarat RERA General Rules, 2017", num, title, body, page))
        build_index(s, index_dir=tmp / "ix", chunks=chunks)
    engine.dispose()
    return LegalIndex.load(tmp / "ix")


@pytest.mark.parametrize("question,expected", [
    ("Section 3", ("act", "3")),
    ("કલમ 5", ("act", "5")),
    ("नियम 3", ("rules", "3")),
    ("If the builder delays possession can I get interest?", ("act", "5")),
    ("બિલ્ડર પઝેશનમાં મોડું કરે તો વ્યાજ મળે?", ("act", "5")),
    ("Can a promoter advertise without registering the project?", ("act", "3")),
    ("How much advance can the promoter take before the agreement for sale?", ("act", "4")),
])
def test_retrieval(index, question, expected):
    hits = index.search(question, k=3)
    assert expected in [(h.chunk["kind"], h.chunk["number"]) for h in hits]


@pytest.mark.parametrize("question", ["best biryani in Surat", "what is the weather today", "આજે હવામાન કેવું છે?"])
def test_off_topic_returns_nothing(index, question):
    assert index.search(question) == []


@pytest.fixture
def patched_index(index, monkeypatch):
    monkeypatch.setattr(legal_answer_mod, "default_index", lambda: index)
    monkeypatch.setattr(search_mod, "default_index", lambda: index)
    return index


def test_answer_uses_llm_summary_only_when_guarded(patched_index):
    q = "If the builder delays possession can I get interest?"
    good = legal_answer_mod.answer(q, "en", generate=lambda p: "Yes, you can claim interest for every month of delay [1].")
    assert good.card["summary_by"] == "llm"
    assert any(s.key == "legal_summary" and s.citations for s in good.sentences)
    bad = legal_answer_mod.answer(q, "en", generate=lambda p: "You get 18% interest within 30 days [1].")
    assert bad.card["summary_by"] == "quote"  # invented numbers are rejected
    uncited = legal_answer_mod.answer(q, "gu", generate=lambda p: "Yes, interest is payable.")
    assert uncited.card["summary_by"] == "quote" and uncited.sentences[0].text.startswith("સંબંધિત જોગવાઈ")
    assert uncited.sentences[-1].key == "legal_disclaimer"


def test_answer_not_found(patched_index):
    out = legal_answer_mod.answer("best biryani in Surat", "hi", use_llm=False)
    assert out.intent == "legal_not_found" and out.card is None


def test_chat_routes_law_questions(patched_index, tmp_path, monkeypatch):
    monkeypatch.setattr(legal_answer_mod, "ollama_generate", lambda p: "")
    engine = make_engine(f"sqlite:///{(tmp_path / 'c.sqlite').as_posix()}")
    init_db(engine)
    with session_factory(engine)() as s:
        generate(s, MockConfig(seed=5))
        repo = Repository(s, Principal.anonymous())
        assert respond("What does Section 3 say?", ChatState(), repo).intent == "legal"
        out = respond("If the builder delays possession, can I get interest?", ChatState(), repo).to_dict()
        assert out["intent"] == "legal" and out["cards"][0]["type"] == "legal"
        assert respond("I want to file a complaint", ChatState(), repo).intent == "complaint_filing"
    engine.dispose()
