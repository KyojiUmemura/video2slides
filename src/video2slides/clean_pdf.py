"""PDF background removal.

Pipeline:
    1. Sample a subset of pages and estimate per-pixel background map
    2. Stream each page: remove background and write to output PDF

Memory efficiency: the background map is computed from a sample of pages
only. The full removal pass processes one page at a time — only the
background map and the current page are held in memory.
"""

from __future__ import annotations

import io
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np

from .pdf_io import iter_pdf_pages
from .analyze_positional import positional_background
from .remove import remove_background


def clean_pdf(
    input_pdf: Path,
    output_path: Path,
    bg_pages: int = 60,
    percentile: float = 90.0,
    intensity: float = 1.0,
    model: str = "multiplicative",
) -> Path:
    """Clean background from a PDF and save the result.

    Args:
        input_pdf: Path to the input PDF file.
        output_path: Path to save the cleaned PDF.
        bg_pages: Max pages to sample for background estimation (default 60).
        percentile: Per-pixel histogram percentile for bg map (default 90).
        intensity: Removal intensity 0-1 (default 1.0 = full removal).
        model: "additive" or "multiplicative" (default multiplicative).

    Returns:
        Path to the cleaned PDF file.
    """
    input_pdf = Path(input_pdf)
    output_path = Path(output_path)

    if not input_pdf.exists():
        raise FileNotFoundError(f"Input PDF not found: {input_pdf}")

    print(f"Cleaning PDF: {input_pdf}")

    # ------------------------------------------------------------------
    # Phase 1: Estimate background map from a sample of pages.
    # Only bg_pages pages are held in memory at once.
    # ------------------------------------------------------------------
    bg_pages_list = []
    for _page_idx, page in iter_pdf_pages(input_pdf, dpi=72):
        bg_pages_list.append(page)
        if len(bg_pages_list) >= bg_pages:
            break

    n_total = len(bg_pages_list)
    print(f"  Sampled {n_total} pages for background estimation")

    print(f"  Estimating positional background (p{percentile:.0f})...")
    bg, conf, coverage = positional_background(
        bg_pages_list, percentile=percentile
    )
    print(f"  bg map: R={bg[..., 0].mean():.0f} G={bg[..., 1].mean():.0f} B={bg[..., 2].mean():.0f}")

    # ------------------------------------------------------------------
    # Phase 2: Stream each page — remove background and write immediately.
    # Only one page is in memory at a time (plus the bg map).
    # ------------------------------------------------------------------
    print(f"  Removing background ({model}, intensity={intensity}) and writing...")
    doc = fitz.open()

    for page_idx, page in iter_pdf_pages(input_pdf, dpi=72):
        # Remove background for this single page
        cleaned = remove_background([page], bg, model=model, intensity=intensity)[0]

        # Create output page sized to the cleaned image dimensions
        h, w, _ = cleaned.shape
        out_page = doc.new_page(width=w, height=h)

        # Embed the cleaned page image
        pil_img = Image.fromarray(cleaned)
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        buf.seek(0)
        out_page.insert_image(
            fitz.Rect(0, 0, w, h),
            stream=buf.read(),
        )

        # Progress: print every 50 pages
        if (page_idx + 1) % 50 == 0 or page_idx == 0:
            print(f"    processed {page_idx + 1} pages...")

    pdf_bytes = doc.tobytes()
    doc.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(pdf_bytes)
    print(f"  Cleaned PDF saved: {output_path}")

    return output_path
