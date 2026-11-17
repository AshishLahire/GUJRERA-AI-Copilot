"""Build the legal search index: RERA Act 2016, Gujarat RERA General Rules 2017, and RERA orders.

Sources (downloaded from the GUJRERA website into data/gujrera/legal/, not committed):
    rera_act_2016.pdf                    scanned; read with Tesseract OCR
    gujarat_rera_general_rules_2017.pdf  has a text layer

Each document is split into numbered sections/rules, long ones into overlapping
chunks. Orders come from the database. The index stores multilingual-e5
embeddings ("passage: " prefix) plus token lists for keyword search, so a
Gujarati or Hindi question can find English legal text.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from gujrera.config import get_gujrera_settings
from gujrera.db.models import Order

LEGAL_DIR = Path("data/gujrera/legal")
INDEX_DIR = Path("data/gujrera/legal_index")
SOURCES = {
    "act": ("rera_act_2016.pdf", "RERA Act, 2016", "Section"),
    "rules": ("gujarat_rera_general_rules_2017.pdf", "Gujarat RERA General Rules, 2017", "Rule"),
}
CHUNK_CHARS = 1400
OVERLAP = 200
NUMBERED = re.compile(r"(?m)^[ \t]*(\d{1,3}[A-Z]?)\.[ \t]+(\S.*)$")
# OCR sometimes garbles a section number ("12." read as "AZ:"); after a margin title it is accepted
# and numbered from the sequence.
GARBLED = re.compile(r"(?m)^[ \t]*([^\s.:]{1,4})[.:,][ \t]+(\(1\)|[A-Z]\S*)(.*)$")
ANNEXURE = re.compile(r"(?m)^[ \t]*Annexure[ \t]*['‘’\"]?A['‘’\"]?[ \t]*$", re.IGNORECASE)
TITLE_END = re.compile(r"\.\s*[-—–]|—|:-")


@dataclass
class Chunk:
    id: str
    kind: str  # act | rules | order
    doc_title: str
    number: str  # section / rule number, or order number
    title: str
    text: str
    page: int | None
    is_mock: bool = False

    @property
    def label(self) -> str:
        if self.kind == "order":
            return f"Order {self.number}"
        if self.kind == "annexure":
            return f"{self.doc_title}, Annexure A (model agreement for sale)"
        return f"{self.doc_title}, {SOURCES[self.kind][2]} {self.number}"


def _tesseract_cmd() -> str | None:
    cmd = get_gujrera_settings().GUJRERA_TESSERACT_CMD
    return cmd if cmd and Path(cmd).exists() else None


def pdf_pages(path: Path, ocr_lang: str = "eng") -> list[str]:
    """Text of each page; pages without a text layer are read with Tesseract OCR."""
    import pypdfium2 as pdfium

    pages: list[str] = []
    doc = pdfium.PdfDocument(str(path))
    for i in range(len(doc)):
        text = doc[i].get_textpage().get_text_range()
        if len(text.strip()) < 40:
            import pytesseract

            cmd = _tesseract_cmd()
            if cmd:
                pytesseract.pytesseract.tesseract_cmd = cmd
            image = doc[i].render(scale=300 / 72).to_pil()
            text = pytesseract.image_to_string(image, lang=ocr_lang)
        pages.append(text.replace("\r\n", "\n"))
    return pages


def _clean(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"-\n(?=[a-z])", "", text)  # re-join hyphenated words
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _title(rest: str, prev_line: str, next_line: str) -> tuple[str, bool]:
    """Returns (title, title_is_margin_note).

    Act style: the title is a margin note on the line before ("Return of amount and compensation.")
    and the numbered line starts with the body ("18. (1) If the promoter ...").
    Rules style: the title follows the number and ends with ".-" or ".—", possibly on the next line.
    """
    if rest.startswith("(") or rest[:1].islower():
        if prev_line and len(prev_line) < 140 and not re.match(r"^[(\[]?\d", prev_line):
            return prev_line.strip(" .—-"), True
        return rest[:80], False
    head = rest if TITLE_END.search(rest) else f"{rest} {next_line}"
    return re.split(r"\.\s*[-—–]|—|:-|\.\s*\(1\)", head)[0].strip(" .")[:150], False


def split_sections(pages: list[str]) -> list[tuple[str, str, str, int]]:
    """(number, title, body, page) for each numbered section/rule. Numbers must run in sequence
    (small gaps allowed for OCR misses), so list items like "1." inside a section are skipped."""
    joined, offsets = "", []
    for i, page in enumerate(pages, 1):
        offsets.append((len(joined), i))
        joined += _clean(page) + "\n"
    candidates = [(m.start(), m.end(), m.group(1), m.group(2).strip(), False) for m in NUMBERED.finditer(joined)]
    seen = {c[0] for c in candidates}
    for m in GARBLED.finditer(joined):
        if m.start() in seen or m.group(1).isdigit():
            continue
        before = joined[:m.start()].rstrip("\n").split("\n")
        prev = before[-1].strip() if before else ""
        if prev.endswith(".") and len(prev) < 140 and prev[:1].isupper() and not re.match(r"^[(\[]?\d", prev):
            candidates.append((m.start(), m.end(), "", (m.group(2) + m.group(3)).strip(), True))
    candidates.sort()

    found: list[tuple[int, str, str]] = []
    last = 0
    for start_pos, end_pos, num, rest, garbled in candidates:
        if garbled:
            num = str(last + 1)
        n = int(re.match(r"\d+", num).group())
        in_sequence = (n == last + 1) or (n == last and num[-1].isalpha()) \
            or (last > 0 and 0 < n - last <= 3) or (last == 0 and n <= 3)
        if not in_sequence:
            continue
        before = joined[:start_pos].rstrip("\n").split("\n")
        prev_line = before[-1].strip() if before else ""
        after = joined[end_pos:].lstrip("\n").split("\n", 1)
        next_line = after[0].strip() if after else ""
        title, margin = _title(rest, prev_line, next_line)
        if garbled and not margin:
            title, margin = prev_line.strip(" .—-"), True
        start = joined.rfind(prev_line, 0, start_pos) if margin else start_pos
        found.append((start, num, title))
        last = n
    out = []
    for idx, (start, num, title) in enumerate(found):
        end = found[idx + 1][0] if idx + 1 < len(found) else len(joined)
        page = max(p for off, p in offsets if off <= start)
        out.append((num, title, joined[start:end].strip(), page))
    return out


def _chunks_of(text: str) -> list[str]:
    if len(text) <= CHUNK_CHARS:
        return [text]
    parts, i = [], 0
    while i < len(text):
        parts.append(text[i:i + CHUNK_CHARS])
        i += CHUNK_CHARS - OVERLAP
    return parts


def split_annexure(pages: list[str]) -> tuple[list[str], str]:
    """Rules end where Annexure 'A' (the model agreement for sale) starts; return (rule pages, annexure)."""
    for i, page in enumerate(pages):
        m = ANNEXURE.search(page)
        if m:
            return pages[:i] + [page[:m.start()]], page[m.start():] + "\n".join(pages[i + 1:])
    return pages, ""


def legal_chunks(legal_dir: Path = LEGAL_DIR) -> list[Chunk]:
    chunks: list[Chunk] = []
    for kind, (filename, doc_title, _unit) in SOURCES.items():
        path = legal_dir / filename
        if not path.exists():
            continue
        pages = pdf_pages(path)
        annexure = ""
        if kind == "rules":
            pages, annexure = split_annexure(pages)
        for num, title, body, page in split_sections(pages):
            for j, part in enumerate(_chunks_of(body)):
                chunks.append(Chunk(f"{kind}:{num}:{j}", kind, doc_title, num, title, part, page))
        for j, part in enumerate(_chunks_of(_clean(annexure)) if annexure else []):
            chunks.append(Chunk(f"annexure:A:{j}", "annexure", doc_title, "A", "Model agreement for sale", part, None))
    return chunks


def order_chunks(session: Session) -> list[Chunk]:
    return [
        Chunk(f"order:{o.order_no}", "order", "GUJRERA orders", o.order_no, o.order_type.replace("_", " "),
              f"{o.order_type.replace('_', ' ').title()} dated {o.issued_on.isoformat()}: {o.summary}", None,
              o.is_mock)
        for o in session.scalars(select(Order).order_by(Order.issued_on))
    ]


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+|[઀-૿]+|[ऀ-ॿ]+", text.lower())


_MODEL = None


def _model():
    global _MODEL
    if _MODEL is None:
        import os

        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
        from sentence_transformers import SentenceTransformer
        from transformers.utils import logging as hf_logging

        hf_logging.disable_progress_bar()
        hf_logging.set_verbosity_error()

        name = get_gujrera_settings().GUJRERA_EMBEDDING_MODEL
        try:
            # transformers 5 asks huggingface.co whether the model is a Mistral model while loading the
            # tokenizer, even with local_files_only (is_base_mistral -> model_info). Without a network
            # that crashes the load, so answer "no tags" locally: e5 is not a Mistral model.
            from unittest import mock

            with mock.patch("huggingface_hub.model_info", lambda *a, **k: mock.Mock(tags=None)):
                _MODEL = SentenceTransformer(name, local_files_only=True)
        except Exception:  # noqa: BLE001 - not cached yet
            _MODEL = SentenceTransformer(name)
    return _MODEL


def embed(texts: list[str], prefix: str) -> np.ndarray:
    vecs = _model().encode([prefix + t for t in texts], batch_size=32, normalize_embeddings=True,
                           show_progress_bar=False)
    return np.asarray(vecs, dtype=np.float32)


def build_index(session: Session, *, legal_dir: Path = LEGAL_DIR, index_dir: Path = INDEX_DIR,
                chunks: list[Chunk] | None = None) -> dict[str, int]:
    chunks = (chunks if chunks is not None else legal_chunks(legal_dir)) + order_chunks(session)
    if not chunks:
        raise RuntimeError("Nothing to index: no legal PDFs and no orders.")
    texts = [f"{c.label}. {c.title}. {c.text}" for c in chunks]
    vectors = embed(texts, "passage: ")
    index_dir.mkdir(parents=True, exist_ok=True)
    np.save(index_dir / "vectors.npy", vectors)
    (index_dir / "chunks.json").write_text(
        json.dumps([asdict(c) | {"tokens": tokenize(t)} for c, t in zip(chunks, texts)], ensure_ascii=False),
        encoding="utf-8")
    counts: dict[str, int] = {}
    for c in chunks:
        counts[c.kind] = counts.get(c.kind, 0) + 1
    return counts
