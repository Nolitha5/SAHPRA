"""Source-aware, page-anchored chunking. Token approximation, not model tokenizer."""
import hashlib
import re
from collections.abc import Iterable
from .schemas import RegulatoryChunk

WORD = re.compile(r"\S+")
CTD_RE = re.compile(r"(?:^|\n)\s*(3\.2\.S(?:\.\d+(?:\.\d+)?)?)\b", re.IGNORECASE)


def stable_id(source_id: str, section: str, page: int | None, position: int, text: str) -> str:
    raw = "\x1f".join([source_id, section, str(page), str(position), text]).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:28]


def section_chunks(source_id: str, pages: Iterable[tuple[int, str]], *, size: int = 512,
                   overlap: int = 128, default_section: str = "unclassified", tokenizer=None) -> list[RegulatoryChunk]:
    if size < 2 or overlap < 0 or overlap >= size:
        raise ValueError("chunk size must be >=2 and 0 <= overlap < size")
    chunks: list[RegulatoryChunk] = []
    current_section = default_section
    for page, raw in pages:
        if not raw or not raw.strip():
            continue
        # Split at CTD boundaries; headings must never bleed into preceding chunk.
        matches = list(CTD_RE.finditer(raw))
        parts: list[tuple[str, str]] = []
        left = 0
        for m in matches:
            if m.start() > left and raw[left:m.start()].strip():
                parts.append((current_section, raw[left:m.start()].strip()))
            current_section = m.group(1).upper()
            left = m.start()
        if raw[left:].strip():
            parts.append((current_section, raw[left:].strip()))
        for section, segment in parts:
            tokens = (tokenizer.encode(segment, add_special_tokens=False) if tokenizer is not None else WORD.findall(segment))
            if not tokens:
                continue
            start, pos = 0, 0
            while start < len(tokens):
                text = (tokenizer.decode(tokens[start:start + size], skip_special_tokens=True)
                        if tokenizer is not None else " ".join(tokens[start:start + size]))
                cid = stable_id(source_id, section, page, pos, text)
                chunks.append(RegulatoryChunk(chunk_id=cid, source_id=source_id, text=text, section=section,
                    page=page, checksum=hashlib.sha256(text.encode()).hexdigest(),
                    metadata={"token_count_approx": len(tokens[start:start+size]), "tokenizer": "hf-exact" if tokenizer is not None else "whitespace-approx"}))
                pos += 1
                if start + size >= len(tokens):
                    break
                start += size - overlap
    return chunks


def chunks_from_pdf(pdf_path: str, source_id: str, size: int = 512,
                    overlap: int = 128, default_section: str = "unclassified", tokenizer=None) -> list[RegulatoryChunk]:
    import fitz
    with fitz.open(pdf_path) as pdf:
        pages = [(i + 1, p.get_text(sort=True)) for i, p in enumerate(pdf)]
    if not any(s.strip() for _, s in pages):
        raise ValueError("No extractable text. Send scanned PDFs to M3 OCR; never silently index empty pages")
    return section_chunks(source_id, pages, size=size, overlap=overlap, default_section=default_section, tokenizer=tokenizer)
