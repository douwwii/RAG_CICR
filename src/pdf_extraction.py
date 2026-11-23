"""Extraction numérique uniquement ; positions dans un texte conservé intégralement."""
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


@dataclass(frozen=True)
class PageSpan:
    page: int
    start: int
    end: int


@dataclass(frozen=True)
class ExtractedPDF:
    text: str
    pages: list[PageSpan]

    def page_range(self, start: int, end: int) -> tuple[int, int]:
        while start < end and self.text[start].isspace():
            start += 1
        while end > start and self.text[end - 1].isspace():
            end -= 1
        pages = [p.page for p in self.pages if p.start < end and p.end > start]
        if not pages:
            raise ValueError('Extrait sans page source.')
        return pages[0], pages[-1]


def extract_pdf(path: Path, *, max_pages: int = 100, max_characters: int = 24000) -> ExtractedPDF:
    reader = PdfReader(path)
    if reader.is_encrypted:
        raise ValueError('Les PDF protégés par un mot de passe ne sont pas pris en charge.')
    if not 1 <= len(reader.pages) <= max_pages:
        raise ValueError(f'Le PDF doit contenir entre 1 et {max_pages} pages.')
    parts, spans = [], []
    cursor = 0
    for number, page in enumerate(reader.pages, 1):
        stream = page.get_contents()
        if stream is not None and len(stream.get_data()) > 10_000_000:
            raise ValueError('Page trop complexe pour cette version locale.')
        text = page.extract_text() or ''
        # Une page vide ou numérisée n'est jamais présentée comme ingérée avec succès.
        if not text.strip():
            raise ValueError(f'Page {number} sans texte numérique exploitable ; OCR non pris en charge.')
        part = text + ('\n\n' if number < len(reader.pages) else '')
        parts.append(part)
        spans.append(PageSpan(number, cursor, cursor + len(part)))
        cursor += len(part)
        if cursor > max_characters:
            raise ValueError(f'Document trop long pour la V1 ({max_characters} caractères maximum).')
    return ExtractedPDF(''.join(parts), spans)
