"""PDF background removal.

Pipeline:
    1. Load PDF pages as numpy arrays (PyMuPDF)
    2. Estimate per-pixel background map (p90 percentile)
    3. White-balance each page: out = clip(page * (255/bg)^intensity, 0, 255)
    4. Save cleaned PDF
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .pdf_io import load_pdf_pages, save_pdf
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

    # 1. Load pages
    pages = load_pdf_pages(input_pdf, dpi=72)
    n_total = len(pages)
    print(f"  Loaded {n_total} pages, {pages[0].shape[1]}x{pages[0].shape[0]}")

    # 2. Estimate background map
    if n_total > bg_pages:
        idx = np.unique(np.linspace(0, n_total - 1, bg_pages).astype(int))
        bg_pages_list = [pages[i] for i in idx]
        print(f"  Estimating bg from {len(bg_pages_list)} sampled pages")
    else:
        bg_pages_list = pages

    print(f"  Estimating positional background (p{percentile:.0f})...")
    bg, conf, coverage = positional_background(
        bg_pages_list, percentile=percentile
    )
    print(f"  bg map: R={bg[..., 0].mean():.0f} G={bg[..., 1].mean():.0f} B={bg[..., 2].mean():.0f}")

    # 3. Remove background
    print(f"  Removing background ({model}, intensity={intensity})...")
    cleaned = remove_background(pages, bg, model=model, intensity=intensity)

    # 4. Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_pdf(cleaned, output_path, compression="zip")
    print(f"  Cleaned PDF saved: {output_path}")

    return output_path
