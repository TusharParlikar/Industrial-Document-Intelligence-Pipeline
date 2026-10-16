"""Text extraction: PDF text layer when present, Tesseract OCR otherwise."""
import os
import shutil
from pathlib import Path

import pymupdf

MIN_CHARS = 20  # fewer characters than this on a page = treat it as a scan


def extract_text(path: str) -> tuple[str, float]:
    """Return (document text, source quality in [0, 1]).

    Quality is 1.0 for digital text and the mean Tesseract word confidence for OCR'd pages.
    Images (PNG/JPG/TIFF) open as one-page documents and always go through OCR.
    """
    texts, qualities = [], []
    with pymupdf.open(path) as doc:
        for page in doc:
            text = page.get_text()
            if len(text.strip()) >= MIN_CHARS:
                texts.append(text)
                qualities.append(1.0)
            else:
                text, quality = _ocr(page)
                texts.append(text)
                qualities.append(quality)
    # ponytail: one quality score per document, per-word confidences if scans mix good and bad pages
    return "\n".join(texts), sum(qualities) / len(qualities) if qualities else 0.0


def _ocr(page: pymupdf.Page) -> tuple[str, float]:
    import pytesseract
    from PIL import Image, ImageOps

    pytesseract.pytesseract.tesseract_cmd = _tesseract_cmd()

    pix = page.get_pixmap(dpi=300, colorspace=pymupdf.csGRAY)
    # ponytail: autocontrast only, add deskew/denoise when real scans need it
    img = ImageOps.autocontrast(Image.frombytes("L", (pix.width, pix.height), pix.samples))
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

    lines: dict[tuple, list[str]] = {}
    confs = []
    for i, word in enumerate(data["text"]):
        conf = float(data["conf"][i])
        if word.strip() and conf >= 0:
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            lines.setdefault(key, []).append(word)
            confs.append(conf)
    text = "\n".join(" ".join(words) for words in lines.values())
    return text, sum(confs) / len(confs) / 100 if confs else 0.0


def _tesseract_cmd() -> str:
    """TESSERACT_CMD, else PATH, else the Windows installer's default folder (it does not touch PATH)."""
    default = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR" / "tesseract.exe"
    return os.getenv("TESSERACT_CMD") or shutil.which("tesseract") or (str(default) if default.exists() else "tesseract")
