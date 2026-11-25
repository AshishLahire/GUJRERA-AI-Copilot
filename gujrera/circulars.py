"""GUJRERA circulars: upload PDFs, read them (OCR for scanned pages), and answer questions with citations.

Flow:

1. A state-level officer (the POC admin) uploads circular PDFs. Pages with a text layer are read directly;
   scanned pages are read with Tesseract OCR in Gujarati, English and Hindi.
2. The circular number, date and subject are read from the first page ("Circular No.", "પરિપત્ર ક્રમાંક",
   "Date", "તારીખ", "Subject", "વિષય"); the admin checks and corrects them, then publishes. Drafts are never
   searched.
3. Each page is split into passages with a multilingual-e5 vector, stored in the database, so a published
   circular is searchable at once, with no rebuild step.
4. Citizens and officers ask in Gujarati, Hindi or English. The answer quotes the passage and cites the
   circular's number, date and page, with a link to that page of the PDF. Nothing is paraphrased, and if no
   circular matches, the answer says so.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gujrera.db.models import Circular, CircularChunk, User
from gujrera.db.repository import AccessDenied, Repository
from gujrera.profile.summarise import Sentence

MAX_BYTES = 30 * 1024 * 1024
MAX_PAGES = 60
CHUNK_CHARS = 800
OVERLAP = 120
OCR_LANG = "guj+eng+hin"
WORDS = ("circular", "circulars", "notification", "notifications", "office order", "gazette",
         "પરિપત્ર", "જાહેરનામ", "परिपत्र", "अधिसूचना")
LATEST = ("latest", "recent", "new", "newest", "list", "all", "તાજેતર", "નવા", "નવીનતમ", "યાદી", "નવું", "બધા",
          "नवीनतम", "नए", "हाल", "सूची", "सभी")
_GU_DIGITS = str.maketrans("૦૧૨૩૪૫૬૭૮૯०१२३४५६७८९", "01234567890123456789")


# ------------------------------------------------------------------ access and storage
def require_admin(repo: Repository) -> None:
    if repo.p.role != "officer" or repo.p.district_scope:
        raise AccessDenied("Managing circulars is for state-level GUJRERA officers.")


def folder(session: Session) -> Path:
    db = session.get_bind().url.database
    base = Path(db).parent if db and db != ":memory:" else Path("data/gujrera")
    f = base / "uploads" / "circulars"
    f.mkdir(parents=True, exist_ok=True)
    return f


def pdf_path(session: Session, c: Circular) -> Path:
    return folder(session) / c.stored_as


# ------------------------------------------------------------------ reading
def _ocr(page, hint: str = "") -> str:  # noqa: ANN001 - a pypdfium2 page
    """OCR one page; a garbled text layer tells which script the page is in."""
    import pytesseract

    from gujrera.legal.build import _tesseract_cmd

    cmd = _tesseract_cmd()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
    gu, hi = len(re.findall(r"[઀-૿]", hint)), len(re.findall(r"[ऀ-ॿ]", hint))
    lang = "guj+eng" if gu > 3 * max(hi, 1) else "hin+eng" if hi > 3 * max(gu, 1) else OCR_LANG
    return pytesseract.image_to_string(page.render(scale=300 / 72).to_pil(), lang=lang)


def read_pages(path: Path) -> tuple[list[str], int]:
    """Text of each page and how many needed OCR."""
    import pypdfium2 as pdfium

    try:
        doc = pdfium.PdfDocument(str(path))
    except Exception as exc:  # noqa: BLE001 - not a PDF, encrypted, damaged
        raise ValueError(f"Could not open the PDF: {exc}") from None
    pages, ocr = [], 0
    try:
        if len(doc) > MAX_PAGES:
            raise ValueError(f"The PDF has {len(doc)} pages; circulars over {MAX_PAGES} pages are not accepted.")
        for i in range(len(doc)):
            page = doc[i]
            text = page.get_textpage().get_text_range()
            if len(re.sub(r"\s", "", text)) < 40 or broken_text_layer(text):
                try:
                    text = _ocr(page, text)
                    ocr += 1
                except Exception:  # noqa: BLE001 - Tesseract not installed: keep what there is
                    pass
            pages.append(_clean(text))
            page.close()
    finally:
        doc.close()  # Windows keeps an open PDF locked: close it so it can be deleted later
    return pages, ocr


_FOREIGN = re.compile(r"[^\sA-Za-z0-9઀-૿ऀ-ॿ -ÿ -⁯.,:;()\[\]/\\\-–—'\"“”‘’!?@#%&*+=<>_|₹₨]")
_SPLIT_MATRA = re.compile(r"[઀-૿]\s+[ા-ૌ]|[ઁ-ૌ]\s[ા-ૌ]|\s[િ-ૌ]")


def broken_text_layer(text: str) -> bool:
    """True when an Indic PDF's text layer is garbled (glyphs mapped to the wrong characters, vowel signs
    split from their letters), as many Gujarati PDFs are; such pages are read with OCR instead."""
    letters = re.findall(r"[^\s\d\W]", text)
    if len(re.findall(r"[઀-૿ऀ-ॿ]", text)) < 20 or not letters:
        return False
    foreign = len(_FOREIGN.findall(text))
    split = len(_SPLIT_MATRA.findall(text))
    return foreign / len(letters) > 0.01 or split / len(letters) > 0.02


def _clean(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"-\n(?=[a-z])", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


_NUMBER = re.compile(
    r"(?:circular|notification|office\s+order|પરિપત્ર|જાહેરનામું|परिपत्र|अधिसूचना)\s*"
    r"(?:no\.?|number|nos?\.|ક્રમાંક|ક્રમ|નં\.?|नं\.?|क्रमांक|संख्या|सं\.)\s*[:.\-–]?\s*([A-Za-z0-9][A-Za-z0-9/\-.()_ ]{0,60}[A-Za-z0-9)])",
    re.IGNORECASE)
_NUMBER_ALT = re.compile(r"\b(?:no\.|ક્રમાંક|क्रमांक)\s*[:.\-–]?\s*((?:GUJ)?RERA[A-Za-z0-9/\-.()_ ]{2,60}[A-Za-z0-9)])", re.IGNORECASE)
_DATE_LABEL = re.compile(r"(?:dated?|date|તારીખ|તા\.|दिनांक|दि\.)\s*[:.\-–]?\s*(\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4})", re.IGNORECASE)
_DATE_ANY = re.compile(r"\b(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})\b")
_SUBJECT = re.compile(r"(?:subject|sub\.|વિષય|विषय)\s*[:.\-–]\s*(.+)", re.IGNORECASE)


def _parse_date(text: str) -> date | None:
    m = re.match(r"(\d{1,2})[./\-](\d{1,2})[./\-](\d{2,4})", text)
    if not m:
        return None
    d, mth, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    y = y + 2000 if y < 100 else y
    try:
        return date(y, mth, d)
    except ValueError:
        return None


def language(text: str) -> str:
    gu = len(re.findall(r"[઀-૿]", text))
    hi = len(re.findall(r"[ऀ-ॿ]", text))
    en = len(re.findall(r"[A-Za-z]", text))
    total = gu + hi + en or 1
    if gu / total > 0.6:
        return "gu"
    if hi / total > 0.6:
        return "hi"
    if en / total > 0.6:
        return "en"
    return "mixed"


def detect(pages: list[str]) -> dict[str, Any]:
    """Number, date, subject and language, read from the first page (the admin checks them)."""
    first = (pages[0] if pages else "").translate(_GU_DIGITS)
    m = _NUMBER.search(first) or _NUMBER_ALT.search(first)
    number = re.sub(r"\s+", " ", m.group(1)).strip(" .:-") if m else None
    d = _DATE_LABEL.search(first)
    issued = _parse_date(d.group(1)) if d else None
    if issued is None:
        for g in _DATE_ANY.finditer(first):
            issued = _parse_date(g.group(0))
            if issued:
                break
    s = _SUBJECT.search(first)
    subject = re.sub(r"\s+", " ", s.group(1)).strip()[:400] if s else None
    if not subject:
        lines = [ln.strip() for ln in first.splitlines() if len(ln.strip()) > 15]
        subject = lines[0][:400] if lines else None
    return {"number": number, "issued_on": issued, "subject": subject,
            "language": language(" ".join(pages))}


def _repeated_lines(pages: list[str]) -> set[str]:
    """Lines printed more than once in the document: letterheads, footers, stamps."""
    counts: dict[str, int] = {}
    for page in pages:
        for line in page.splitlines():
            key = re.sub(r"\s+", " ", line).strip()
            if len(key) >= 12:
                counts[key] = counts.get(key, 0) + 1
    return {k for k, n in counts.items() if n >= 2}


def passages(pages: list[str]) -> list[tuple[int, int, str]]:
    """(page, seq, text) passages of about CHUNK_CHARS, split at sentence ends where possible; lines repeated
    on the pages (letterhead, footer, stamp) are left out."""
    out = []
    repeated = _repeated_lines(pages)
    for pno, text in enumerate(pages, 1):
        text = "\n".join(ln for ln in text.splitlines() if re.sub(r"\s+", " ", ln).strip() not in repeated)
        text = re.sub(r"\s+", " ", text).strip()
        seq, i = 0, 0
        while i < len(text):
            end = min(len(text), i + CHUNK_CHARS)
            if end < len(text):
                cut = max(text.rfind(". ", i, end), text.rfind("। ", i, end), text.rfind("? ", i, end))
                if cut > i + CHUNK_CHARS // 2:
                    end = cut + 1
            part = text[i:end].strip()
            if len(part) > 20:
                out.append((pno, seq, part))
                seq += 1
            if end >= len(text):
                break
            i = max(end - OVERLAP, i + 1)
    return out


# ------------------------------------------------------------------ admin: upload, review, publish
def _username(repo: Repository) -> str | None:
    u = repo.s.get(User, repo.p.user_id) if repo.p.user_id else None
    return u.username if u else None


def _dict(c: Circular, *, with_pages: list[str] | None = None) -> dict[str, Any]:
    d = {"id": c.id, "number": c.number, "subject": c.subject,
         "issued_on": c.issued_on.isoformat() if c.issued_on else None, "language": c.language,
         "filename": c.filename, "pages": c.pages, "ocr_pages": c.ocr_pages, "status": c.status,
         "uploaded_by": c.uploaded_by, "uploaded_at": c.uploaded_at.isoformat(timespec="minutes"),
         "published_at": c.published_at.isoformat(timespec="minutes") if c.published_at else None,
         "pdf_url": f"/api/gujrera/circulars/{c.id}/pdf"}
    if with_pages is not None:
        d["preview"] = [p[:600] for p in with_pages[:3]]
    return d


def upload(repo: Repository, filename: str, data: bytes) -> dict[str, Any]:
    require_admin(repo)
    name = Path(filename or "circular.pdf").name[:200]
    if Path(name).suffix.lower() != ".pdf" or not data.startswith(b"%PDF"):
        raise ValueError("Upload a PDF file.")
    if len(data) > MAX_BYTES:
        raise ValueError("The PDF is larger than 30 MB.")
    stored = f"{uuid.uuid4().hex}.pdf"
    path = folder(repo.s) / stored
    path.write_bytes(data)
    try:
        pages, ocr = read_pages(path)
    except ValueError:
        path.unlink(missing_ok=True)
        raise
    if not any(p.strip() for p in pages):
        path.unlink(missing_ok=True)
        raise ValueError("No text could be read from this PDF (OCR found nothing either).")
    meta = detect(pages)
    c = Circular(number=meta["number"], subject=meta["subject"], issued_on=meta["issued_on"],
                 language=meta["language"], filename=name, stored_as=stored, pages=len(pages), ocr_pages=ocr,
                 status="draft", uploaded_by=_username(repo), uploaded_at=datetime.now())
    repo.s.add(c)
    repo.s.flush()
    _index(repo.s, c, pages)
    repo.s.flush()
    repo._audit("circular_uploaded", {"id": c.id, "file": name, "pages": len(pages), "ocr_pages": ocr})
    return {"circular": _dict(c, with_pages=pages)}


EXTRA_TERMS = {"qpr": "quarterly progress report", "ત્રિમાસિક પ્રગતિ": "quarterly progress report",
               "ત્રિમાસિક અહેવાલ": "quarterly progress report", "त्रैमासिक": "quarterly progress report",
               "qr": "qr code", "હોર્ડિંગ": "hoarding advertisement", "मुदत": "extension",
               "મુદત વધારા": "extension of registration", "विस्तार": "extension of registration",
               "escrow": "designated account", "70%": "seventy per cent designated account"}
_FILLER = ("what does", "what do", "is there", "are there", "do you have", "tell me", "say about", "says about",
           "say", "says", "about", "regarding", "related to", "on the", "any", "the", "please", "issued", "gujrera",
           "શું કહે છે", "કહે છે", "અંગે", "બાબત", "વિશે", "શું", "છે", "કોઈ", "के बारे में", "क्या कहता है",
           "क्या", "है", "में", "का", "की", "के", "कोई")


def _terms(text: str) -> str:
    """English equivalents of the Gujarati/Hindi RERA words in a text, so English and Gujarati meet."""
    from gujrera.legal.glossary import expand

    lowered = text.lower()
    extra = [en for w, en in EXTRA_TERMS.items() if w in lowered]
    expanded = expand(text)
    return " ".join([expanded[len(text):].strip(), *extra]).strip()


def clean_question(question: str) -> str:
    """The question without circular words and filler, which match every circular."""
    q = " " + (question or "").lower().translate(_GU_DIGITS) + " "
    for w in sorted(WORDS, key=len, reverse=True):
        q = re.sub(rf"\S*{re.escape(w)}\S*", " ", q)
    for f in sorted(_FILLER, key=len, reverse=True):
        q = re.sub(rf"(?<![\w઀-૿ऀ-ॿ]){re.escape(f)}(?![\w઀-૿ऀ-ॿ])", " ", q)
    q = re.sub(r"[?!.,;:]+", " ", q)
    from gujrera.legal.search import STOPWORDS

    small = {"a", "an", "in", "on", "of", "to", "for", "is", "be", "by", "at", "or", "as", "it", "if", "do", "me",
             "showing", "show", "shown"}
    return " ".join(w for w in q.split() if w not in STOPWORDS and w not in small)


def _index(s: Session, c: Circular, pages: list[str]) -> None:
    from gujrera.legal.build import embed, tokenize

    s.query(CircularChunk).filter(CircularChunk.circular_id == c.id).delete()
    parts = passages(pages)
    if not parts:
        return
    head = f"{c.subject or ''} {c.number or ''}".strip()
    texts = [f"{head}. {t}" if head else t for _p, _s, t in parts]
    texts = [f"{t} {_terms(t)}".strip() for t in texts]  # English terms for Gujarati/Hindi passages
    vecs = embed(texts, "passage: ")
    for (pno, seq, text), full, v in zip(parts, texts, vecs):
        s.add(CircularChunk(circular_id=c.id, page=pno, seq=seq, text=text, tokens=json.dumps(tokenize(full)),
                            vector=np.asarray(v, dtype=np.float32).tobytes()))


def update(repo: Repository, cid: int, *, number: str | None = None, subject: str | None = None,
           issued_on: date | None = None, clear_date: bool = False, status: str | None = None) -> dict[str, Any]:
    require_admin(repo)
    c = repo.s.get(Circular, cid)
    if c is None:
        raise ValueError("No such circular.")
    changed: dict[str, Any] = {}
    if number is not None and number.strip() != (c.number or ""):
        c.number = number.strip()[:120] or None
        changed["number"] = c.number
    if subject is not None and subject.strip() != (c.subject or ""):
        c.subject = subject.strip()[:400] or None
        changed["subject"] = c.subject
    if issued_on is not None or clear_date:
        c.issued_on = None if clear_date else issued_on
        changed["issued_on"] = c.issued_on
    if status is not None:
        if status not in ("draft", "published"):
            raise ValueError("status must be draft or published")
        if status == "published" and not (c.number or c.subject):
            raise ValueError("Give the circular a number or a subject before publishing it.")
        if status != c.status:
            c.status = status
            c.published_at = datetime.now() if status == "published" else None
            changed["status"] = status
    if {"number", "subject"} & changed.keys():  # the passage vectors carry the subject and number
        _index(repo.s, c, _pages_of(repo.s, c))
    repo.s.flush()
    if changed:
        repo._audit("circular_updated", {"id": c.id, **{k: str(v) for k, v in changed.items()}})
    return {"circular": _dict(c)}


def _pages_of(s: Session, c: Circular) -> list[str]:
    rows = s.scalars(select(CircularChunk).where(CircularChunk.circular_id == c.id)
                     .order_by(CircularChunk.page, CircularChunk.seq)).all()
    pages: dict[int, list[str]] = {}
    for r in rows:
        pages.setdefault(r.page, []).append(r.text)
    return [" ".join(pages.get(i, [])) for i in range(1, (max(pages) if pages else 0) + 1)]


def delete(repo: Repository, cid: int) -> dict[str, Any]:
    require_admin(repo)
    c = repo.s.get(Circular, cid)
    if c is None:
        raise ValueError("No such circular.")
    repo.s.query(CircularChunk).filter(CircularChunk.circular_id == cid).delete()
    path = pdf_path(repo.s, c)
    repo.s.delete(c)
    repo.s.flush()
    try:
        path.unlink(missing_ok=True)
    except OSError:  # still open elsewhere: the record is gone; the file is removed on a later delete
        pass
    repo._audit("circular_deleted", {"id": cid, "file": c.filename})
    return {"deleted": cid}


def list_all(repo: Repository) -> dict[str, Any]:
    require_admin(repo)
    rows = repo.s.scalars(select(Circular).order_by(Circular.issued_on.desc().nullslast(), Circular.id.desc())).all()
    return {"circulars": [_dict(c) for c in rows],
            "published": sum(c.status == "published" for c in rows), "drafts": sum(c.status == "draft" for c in rows)}


def list_published(session: Session) -> list[dict[str, Any]]:
    rows = session.scalars(select(Circular).where(Circular.status == "published")
                           .order_by(Circular.issued_on.desc().nullslast(), Circular.id.desc())).all()
    return [_dict(c) for c in rows]


# ------------------------------------------------------------------ search
_CACHE: dict[tuple, Any] = {}


def _search_index(s: Session):
    """The published passages as a hybrid (e5 + BM25) index, rebuilt when circulars change."""
    from gujrera.legal.search import LegalIndex

    key = (str(s.get_bind().url),
           s.scalar(select(func.count()).select_from(Circular).where(Circular.status == "published")),
           s.scalar(select(func.max(CircularChunk.id))), s.scalar(select(func.max(Circular.published_at))),
           s.scalar(select(func.count()).select_from(CircularChunk)))
    if key in _CACHE:
        return _CACHE[key]
    rows = s.execute(select(CircularChunk, Circular).join(Circular, Circular.id == CircularChunk.circular_id)
                     .where(Circular.status == "published").order_by(CircularChunk.id)).all()
    if not rows:
        idx = None
    else:
        chunks = [{"kind": "circular", "number": f"{c.id}:{ch.page}:{ch.seq}", "doc_title": c.subject or "",
                   "title": c.subject or "", "text": ch.text, "page": ch.page, "tokens": json.loads(ch.tokens),
                   "circular_id": c.id, "circular_number": c.number,
                   "issued_on": c.issued_on.isoformat() if c.issued_on else None, "is_mock": False}
                  for ch, c in rows]
        vectors = np.vstack([np.frombuffer(ch.vector, dtype=np.float32) for ch, _c in rows])
        idx = LegalIndex(chunks, vectors)
    _CACHE.clear()
    _CACHE[key] = idx
    return idx


def _label(chunk: dict[str, Any]) -> str:
    num = chunk.get("circular_number") or "GUJRERA circular"
    if not re.match(r"(?i)(circular|notification|પરિપત્ર|परिपत्र)", num):
        num = f"Circular {num}"
    when = ""
    if chunk.get("issued_on"):
        when = f" dated {date.fromisoformat(chunk['issued_on']).strftime('%d %b %Y')}"
    return f"{num}{when}, page {chunk['page']}"


def search(s: Session, question: str, k: int = 3) -> list[Any]:
    idx = _search_index(s)
    if idx is None:
        return []
    q = clean_question(question)
    if not q:
        return []
    singular = [w[:-1] for w in re.findall(r"[a-z]{4,}", q) if w.endswith("s") and not w.endswith("ss")]
    q = f"{q} {' '.join(singular)} {_terms(q)}".strip()  # "advertisements" also finds "advertisement"
    hits = idx.search(q, k=k * 3, kinds=("circular",))
    hits.sort(key=lambda h: (-round(h.score, 9), -h.cosine))  # equal fused rank: the closer meaning first
    out, seen = [], set()
    for h in hits:  # one passage per circular
        cid = h.chunk["circular_id"]
        if cid in seen:
            continue
        seen.add(cid)
        out.append(h)
        if len(out) >= k:
            break
    return out


def _excerpt(text: str, question: str, limit: int = 340) -> str:
    """The sentence(s) of the passage that share most words with the question."""
    from gujrera.legal.build import tokenize
    from gujrera.legal.glossary import expand

    cq = clean_question(question)
    q = set(tokenize(expand(cq))) | set(tokenize(cq)) | set(tokenize(_terms(cq)))
    q |= {w[:-1] for w in q if len(w) > 4 and w.endswith("s") and not w.endswith("ss")}  # "reports" ~ "report"
    sentences = [x.strip() for x in re.split(r"(?<=[.।?!])\s+", text) if x.strip()]
    if not sentences:
        return text[:limit]
    # the header (number, date, subject) is already in the answer: prefer the operative text
    scores = [len(q & set(tokenize(x))) - (3 if (_SUBJECT.search(x) or _DATE_LABEL.search(x) or _NUMBER.search(x))
                                            else 0) for x in sentences]
    best = max(range(len(sentences)), key=lambda i: (scores[i], -i))
    out = sentences[best]
    if len(out) < limit // 2 and best + 1 < len(sentences):
        out = f"{out} {sentences[best + 1]}"
    return out if len(out) <= limit else out[:limit].rsplit(" ", 1)[0] + " …"


def citation(chunk: dict[str, Any]) -> dict[str, Any]:
    return {"type": "circular", "id": _label(chunk), "is_mock": False,
            "url": f"/api/gujrera/circulars/{chunk['circular_id']}/pdf#page={chunk['page']}"}


T = {
    "lead": {"en": "{label}: {subject}.", "gu": "{label}: {subject}.", "hi": "{label}: {subject}।"},
    "quote": {"en": "It says: “{excerpt}”", "gu": "તેમાં લખ્યું છે: “{excerpt}”", "hi": "इसमें लिखा है: “{excerpt}”"},
    "also": {"en": "Also relevant: {labels}.", "gu": "આ પણ સંબંધિત છે: {labels}.", "hi": "यह भी संबंधित है: {labels}।"},
    "none": {"en": "I could not find a GUJRERA circular about this among the circulars loaded so far.",
             "gu": "અત્યાર સુધી લોડ થયેલા GUJRERA પરિપત્રોમાં આ વિશે કોઈ પરિપત્ર મળ્યો નથી.",
             "hi": "अब तक लोड किए गए GUJRERA परिपत्रों में इसके बारे में कोई परिपत्र नहीं मिला।"},
    "empty": {"en": "No GUJRERA circulars have been loaded yet.", "gu": "હજી કોઈ GUJRERA પરિપત્ર લોડ થયો નથી.",
              "hi": "अभी तक कोई GUJRERA परिपत्र लोड नहीं हुआ है।"},
    "latest": {"en": "Latest GUJRERA circulars ({n}):", "gu": "તાજેતરના GUJRERA પરિપત્રો ({n}):",
               "hi": "नवीनतम GUJRERA परिपत्र ({n}):"},
    "item": {"en": "{label}: {subject}.", "gu": "{label}: {subject}.", "hi": "{label}: {subject}।"},
    "advice": {"en": "Open the circular for the full text; this is information, not legal advice.",
               "gu": "પૂરું લખાણ પરિપત્રમાં જુઓ; આ માહિતી છે, કાનૂની સલાહ નથી.",
               "hi": "पूरा पाठ परिपत्र में देखें; यह जानकारी है, कानूनी सलाह नहीं।"},
}


def _t(key: str, lang: str, **v: Any) -> str:
    return T[key].get(lang, T[key]["en"]).format(**v)


def wants_circular(text_lc: str) -> bool:
    return any(w in text_lc for w in WORDS)


def answer(s: Session, question: str, lang: str) -> tuple[str, list[Sentence], dict[str, Any] | None]:
    """(intent, sentences, card) for a question about circulars."""
    q = (question or "").lower()
    published = list_published(s)
    if not published:
        return "circular_none", [Sentence(_t("empty", lang), [], "circ_empty")], None
    content = clean_question(q).split()
    content = [w for w in content if len(w) > 2 and not any(x in w for x in LATEST)
               and w not in ("show", "give", "list", "which", "what", "rera", "કયા", "બતાવો", "दिखाओ", "कौन")]
    if any(w in q for w in LATEST) and not content:
        top = published[:5]
        sents = [Sentence(_t("latest", lang, n=len(published)), [], "circ_latest")]
        for c in top:
            ch = {"circular_id": c["id"], "circular_number": c["number"], "issued_on": c["issued_on"], "page": 1}
            sents.append(Sentence(_t("item", lang, label=_label(ch).rsplit(", page", 1)[0], subject=c["subject"] or ""),
                                  [citation(ch)], "circ_item"))
        return "circular_list", sents, {"type": "circulars", "circulars": top}
    hits = search(s, question)
    if not hits:
        return "circular_not_found", [Sentence(_t("none", lang), [], "circ_none")], None
    top = hits[0].chunk
    sents = [Sentence(_t("lead", lang, label=_label(top), subject=top.get("title") or ""), [citation(top)], "circ_lead"),
             Sentence(_t("quote", lang, excerpt=_excerpt(top["text"], question)), [citation(top)], "circ_quote")]
    others = hits[1:]
    if others:
        sents.append(Sentence(_t("also", lang, labels="; ".join(_label(h.chunk) for h in others)),
                              [citation(h.chunk) for h in others], "circ_also"))
    sents.append(Sentence(_t("advice", lang), [], "circ_advice"))
    card = {"type": "circulars", "hits": [{"circular_id": h.chunk["circular_id"], "label": _label(h.chunk),
                                           "subject": h.chunk.get("title"), "page": h.chunk["page"],
                                           "excerpt": _excerpt(h.chunk["text"], question, 600),
                                           "url": citation(h.chunk)["url"], "score": round(h.cosine, 3)}
                                          for h in hits]}
    return "circular", sents, card


def related(s: Session, question: str, lang: str = "en") -> list[Sentence]:
    """For a law question: one line pointing to a closely matching circular, if there is one."""
    hits = search(s, question, k=1)
    if not hits or hits[0].cosine < 0.84:
        return []
    ch = hits[0].chunk
    lead = {"en": "See also", "gu": "આ પણ જુઓ:", "hi": "यह भी देखें:"}.get(lang, "See also")
    return [Sentence(f"{lead} {_label(ch)}: {ch.get('title') or ''}.", [citation(ch)], "circ_related")]
