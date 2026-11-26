"""The model's pick among retrieved provisions, the glossary's stems and word pairs, and (with the real legal
index, when it is built) search quality on the held-out questions written in buyers' own words."""

from __future__ import annotations

import pytest

from gujrera.legal.glossary import english_terms, expand
from gujrera.legal.rerank import PROMPT, rerank
from gujrera.legal.search import Hit


def _hit(kind, number, title="t", exact=False):
    return Hit({"kind": kind, "number": number, "title": title, "text": "text " * 20, "doc_title": "RERA Act, 2016"},
               0.5, 0.85, exact=exact)


HITS = [_hit("act", "17"), _hit("act", "18"), _hit("act", "13"), _hit("act", "3"), _hit("act", "59"), _hit("act", "71")]


def keys(hits):
    return [h.chunk["number"] for h in hits]


@pytest.mark.parametrize("reply,first", [
    ("2", "18"), (" 3.", "13"), ("(5)", "59"), ("1", "17"),
    ("Section 18 answers it [2].", "17"),  # a sentence, not a number: search order kept
    ("9", "17"), ("", "17"), ("<think>it is 4</think>4", "3"),
])
def test_the_model_only_reorders(reply, first):
    out = rerank("builder missed the handover date", HITS, lambda _p: reply)
    assert keys(out)[0] == first and sorted(keys(out)) == sorted(keys(HITS))  # nothing added or lost


def test_errors_and_exact_lookups_keep_the_search_order():
    def boom(_p):
        raise RuntimeError("model down")

    assert keys(rerank("q", HITS, boom)) == keys(HITS)
    exact = [_hit("act", "18", exact=True)]
    assert rerank("Section 18", exact, lambda _p: "1") is exact


def test_prompt_gives_english_terms_for_gujarati_and_hindi():
    seen = []
    rerank("કબજો મોડો મળે તો?", HITS, lambda p: seen.append(p) or "1")
    assert "Key terms in English: possession" in seen[0] and "{" not in PROMPT.format(question="q", terms="", candidates="c")
    rerank("When is possession due?", HITS, lambda p: seen.append(p) or "1")
    assert "Key terms in English" not in seen[1]


@pytest.mark.parametrize("question,term", [
    ("मुआवजे के दावों का फैसला कौन करता है?", "compensation"),  # inflected: मुआवजे, दावों
    ("कब्जे में देरी", "possession"),
    ("પ્રોજેક્ટની નોંધણીની મુદત વધારી શકાય?", "extension"),
    ("प्रोजेक्ट का पंजीकरण न कराने पर सजा", "non-registration"),
    ("ફ્લેટ ખરીદનારના અધિકારો શું છે?", "rights and duties of allottees"),
    ("क्या एजेंट को पंजीकरण कराना होता है?", "registration of real estate agents"),  # a word pair
])
def test_stems_and_pairs(question, term):
    assert term in english_terms(question) and term in expand(question)


def test_off_topic_words_add_nothing():
    assert english_terms("आज मौसम कैसा है?") == "" and english_terms("best biryani in Surat") == ""


@pytest.fixture(scope="module")
def real_index():
    pytest.importorskip("sentence_transformers")
    from gujrera.legal.search import default_index

    index = default_index()
    if index is None:
        pytest.skip("legal index not built")
    return index


def test_held_out_questions_are_found(real_index):
    """Buyers' own words, not used for tuning: the answering provision must be in the top 3 for nearly all."""
    from gujrera.legal.gold import LEGAL_HELD_OUT

    found = 0
    for _lang, q, want in LEGAL_HELD_OUT:
        wants = want if isinstance(want, list) else [want]
        found += any((h.chunk["kind"], h.chunk["number"]) in wants for h in real_index.search(q, k=3))
    assert found >= len(LEGAL_HELD_OUT) - 1, f"{found}/{len(LEGAL_HELD_OUT)}"
