# extraction/parse_pdf.py

import sys
import os
import re

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def clean_text(text: str) -> str:
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def extract_sections_from_pdf(pdf_file) -> dict:
    """
    Extract structured text sections from a PDF financial report.

    Accepts either a file-like object (e.g. from Streamlit uploader) or a
    string/Path file path.

    Strategy:
      1. Concatenate text from all pages using pdfplumber.
      2. Search for SEC "Item X." section headers (same logic as parse_html.py).
      3. If none are found (non-10-K PDFs, general annual reports), fall back to
         splitting by page so that sections remain a manageable size for BM25 indexing.
    """
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError(
            "pdfplumber is not installed. Run: pip install pdfplumber"
        )

    # Accept both file paths and file-like objects (Streamlit UploadedFile)
    if isinstance(pdf_file, (str, os.PathLike)):
        ctx = pdfplumber.open(pdf_file)
    else:
        # Streamlit UploadedFile or any file-like: pdfplumber accepts them directly
        ctx = pdfplumber.open(pdf_file)

    with ctx as pdf:
        page_texts = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                page_texts.append(clean_text(text))

    if not page_texts:
        return {}

    full_text = "\n".join(page_texts)

    # ── Try SEC "Item X." section detection (same as HTML parser) ────────────
    pattern = re.compile(r'(Item\s+\d+[A-Z]?\.*)\s+([^\n]{3,100})', re.IGNORECASE)
    matches = list(pattern.finditer(full_text))

    if matches:
        sections = {}
        for i, match in enumerate(matches):
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
            section_title = f"{match.group(1).strip()} {match.group(2).strip()}"
            section_text = full_text[start:end].strip()
            if section_text:
                sections[section_title] = clean_text(section_text)
        if sections:
            return sections

    # ── Fallback: use individual pages as sections ────────────────────────────
    # This preserves document structure for BM25 indexing without one giant blob.
    sections = {}
    for i, page_text in enumerate(page_texts, start=1):
        if page_text.strip():
            sections[f"Page {i}"] = page_text

    return sections
