"""PDF reading and writing utilities.

Uses PyMuPDF (fitz) for PDF-to-image conversion and output PDF generation.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import List, Tuple

import fitz  # PyMuPDF
import numpy as np
from PIL import Image


def load_pdf_pages(
    pdf_path: str | Path,
    dpi: int = 72,
) -> List[np.ndarray]:
    """Load all pages of a PDF as RGB numpy arrays.

    Args:
        pdf_path: Path to the input PDF file.
        dpi: Resolution for rendering pages. Default 72 matches original PDF
             resolution for faster processing and smaller output.

    Returns:
        List of RGB images, each a uint8 numpy array of shape
        (height, width, 3).
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"Input PDF not found: {pdf_path}")

    doc = fitz.open(str(pdf_path))
    pages: List[np.ndarray] = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        # Render at specified DPI (fitz uses 72 DPI as base)
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        arr = np.array(img)
        pages.append(arr)

    doc.close()

    if not pages:
        raise ValueError(f"PDF contains no pages: {pdf_path}")

    return pages


def get_page_count(pdf_path: str | Path) -> int:
    """Return the number of pages in a PDF without rendering them."""
    pdf_path = Path(pdf_path)
    doc = fitz.open(str(pdf_path))
    count = len(doc)
    doc.close()
    return count


def get_page_size(pdf_path: str | Path, page_index: int = 0, dpi: int = 300) -> Tuple[int, int]:
    """Return (width, height) in pixels for a given page at the specified DPI."""
    pdf_path = Path(pdf_path)
    doc = fitz.open(str(pdf_path))
    page = doc[page_index]
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    width, height = pix.width, pix.height
    doc.close()
    return width, height


def iter_pdf_pages(
    pdf_path: str | Path,
    dpi: int = 72,
):
    """Yield each page of a PDF as an RGB numpy array, one at a time.

    The PDF document is opened once and pages are rendered on demand,
    so only one page's worth of memory is held at a time.

    Yields:
        (page_index, rgb_array) pairs in document order.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"Input PDF not found: {pdf_path}")

    doc = fitz.open(str(pdf_path))
    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            arr = np.array(img)
            yield page_num, arr
    finally:
        doc.close()


def save_pdf(
    images: List[np.ndarray],
    output_path: str | Path,
    compression: str = "zip",
    jpeg_quality: int = 95,
) -> Path:
    """Save a list of RGB images as a multi-page PDF.

    Args:
        images: List of uint8 RGB numpy arrays.
        output_path: Destination path for the output PDF.
        compression: One of 'zip' (lossless), 'jpeg' (lossy), or 'none'.
        jpeg_quality: JPEG quality when compression='jpeg' (1-100).

    Returns:
        Path to the written PDF file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if compression == "jpeg":
        # For JPEG compression, save via PIL and embed
        pdf_bytes = _images_to_pdf_jpeg(images, jpeg_quality)
    else:
        # For zip/none, use PyMuPDF's native PDF creation
        pdf_bytes = _images_to_pdf_raw(images, compression)

    output_path.write_bytes(pdf_bytes)
    return output_path


def _images_to_pdf_jpeg(
    images: List[np.ndarray],
    quality: int,
) -> bytes:
    """Create PDF by embedding JPEG-compressed pages via PIL."""
    import img2pdf  # lazy import; optional dependency

    buffers = []
    for img in images:
        pil_img = Image.fromarray(img)
        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=quality, optimize=True)
        buffers.append(buf.getvalue())

    pdf_bytes = img2pdf.convert(buffers)
    return pdf_bytes


def _images_to_pdf_raw(
    images: List[np.ndarray],
    compression: str = "zip",
) -> bytes:
    """Create PDF directly via PyMuPDF with raw image embedding."""
    doc = fitz.open()

    for img in images:
        height, width, _ = img.shape
        # Convert to PIL for embedding
        pil_img = Image.fromarray(img)

        # Save to bytes buffer
        buf = io.BytesIO()
        if compression == "zip":
            pil_img.save(buf, format="PNG")
        else:
            # 'none' still uses PNG internally (fitz requires it)
            pil_img.save(buf, format="PNG")
        buf.seek(0)

        # Create a page sized in points (1 pt = 1/72 in) and fill it with the image.
        # NOTE: fitz.Rect and new_page() both take points — do NOT divide by 72
        # here, or the image gets squashed into a tiny corner (see _images_to_pdf_raw).
        page = doc.new_page(width=width, height=height)
        page.insert_image(
            fitz.Rect(0, 0, width, height),
            stream=buf.read(),
        )

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes
