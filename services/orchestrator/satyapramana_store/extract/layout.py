"""Page layout: words and their bounding boxes, deterministically.

This is the half of extraction that must NOT be done by a model. Vision models
are unreliable at emitting precise coordinates, and charter section 3.5 requires
the extracted region to survive unbroken from ingestion to the rendered chip --
that is what makes clicking a PASS badge land on the right line of the PDF.

So boxes come from the text layer (or, for scans, from OCR), and a model's job
is only ever to say WHICH span is the identifier. It never invents a rectangle.
"""
from __future__ import annotations

import io
from dataclasses import dataclass


@dataclass(frozen=True)
class Word:
    text: str
    page: int
    x0: float
    top: float
    x1: float
    bottom: float


@dataclass(frozen=True)
class Page:
    number: int
    words: tuple[Word, ...]
    width: float
    height: float

    @property
    def has_text_layer(self) -> bool:
        return bool(self.words)


def read_pdf(data: bytes) -> list[Page]:
    """Words with boxes, per page. Raises nothing on a page with no text layer:
    it comes back with an empty word list, which the caller must handle rather
    than paper over."""
    import pdfplumber

    pages: list[Page] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            words = tuple(
                Word(w["text"], index, w["x0"], w["top"], w["x1"], w["bottom"])
                for w in page.extract_words(use_text_flow=False)
            )
            pages.append(Page(index, words, page.width, page.height))
    return pages


@dataclass(frozen=True)
class Span:
    """A run of characters located on a page, with the box that covers it."""
    text: str
    page: int
    region: tuple[float, float, float, float]  # x0, top, x1, bottom
    word_indices: tuple[int, ...]


def searchable(page: Page) -> tuple[str, list[tuple[int, int, int]]]:
    """Concatenate a page's words with no separator, keeping a map back.

    No separator, because a statutory identifier is never meaningfully spaced
    and PDF extractors routinely split one across word boxes. The cost is that
    adjacent unrelated words can form a spurious match -- which is precisely
    what the structural validators in grammars.py exist to reject. A GSTIN
    assembled by accident will almost never carry a correct check digit.
    """
    parts: list[str] = []
    index: list[tuple[int, int, int]] = []  # (start, end, word index)
    cursor = 0
    for i, word in enumerate(page.words):
        parts.append(word.text)
        index.append((cursor, cursor + len(word.text), i))
        cursor += len(word.text)
    return "".join(parts), index


def locate(page: Page, start: int, end: int, index: list[tuple[int, int, int]]) -> Span:
    covering = [i for (s, e, i) in index if s < end and e > start]
    boxes = [page.words[i] for i in covering]
    if not boxes:
        raise ValueError("no words cover the matched span")
    return Span(
        text="".join(w.text for w in boxes),
        page=page.number,
        region=(min(b.x0 for b in boxes), min(b.top for b in boxes),
                max(b.x1 for b in boxes), max(b.bottom for b in boxes)),
        word_indices=tuple(covering),
    )


def lines(page: Page, tolerance: float = 3.0) -> list[list[Word]]:
    """Group a page's words into printed lines, top to bottom, left to right.

    Pure layout geometry -- no assumption about what the words say. Two words
    fall on the same line when their vertical centres are within `tolerance`
    points of each other, because word boxes on one printed line are rarely
    pixel-identical. This is what a label/value document (a PAN card: a
    printed label, the value on the line beneath it) needs and `searchable()`
    does not give -- that function deliberately erases line structure to scan
    for a grammar anywhere on the page.
    """
    grouped: list[list[Word]] = []
    for word in sorted(page.words, key=lambda w: w.top):
        centre = (word.top + word.bottom) / 2
        for line in grouped:
            line_centre = (line[0].top + line[0].bottom) / 2
            if abs(centre - line_centre) <= tolerance:
                line.append(word)
                break
        else:
            grouped.append([word])
    for line in grouped:
        line.sort(key=lambda w: w.x0)
    grouped.sort(key=lambda line: line[0].top)
    return grouped
