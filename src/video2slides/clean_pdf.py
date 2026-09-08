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
import PIL.Image as PILImage
import PIL.ImageDraw as PILImageDraw
from tqdm import tqdm

from .analyze_positional import positional_background
from .pdf_io import get_page_count, iter_pdf_pages
from .remove import remove_background

_PROCESSING_PPI = 72


def clean_pdf(
    input_pdf: Path,
    output_path: Path,
    bg_pages: int = 60,
    percentile: float = 90.0,
    intensity: float = 1.0,
    model: str = "multiplicative",
    image_format: str = "png",
    jpeg_quality: int = 95,
    save_bg_map: bool = False,
    save_sample: bool = False,
) -> Path:
    """Clean background from a PDF and save the result.

    Args:
        input_pdf: Path to the input PDF file.
        output_path: Path to save the cleaned PDF.
        bg_pages: Max pages to sample for background estimation (default 60).
        percentile: Per-pixel histogram percentile for bg map (default 90).
        intensity: Removal intensity 0-1 (default 1.0 = full removal).
        model: "additive" or "multiplicative" (default multiplicative).
        image_format: Output image format "png" or "jpg" (default "png").
        jpeg_quality: JPEG quality when image_format="jpg" (1-100, default 95).
        save_bg_map: Save the estimated background map as PNG (default False).
        save_sample: Save a before/after comparison sheet as PNG (default False).

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
    with tqdm(total=bg_pages, desc="Sampling pages for bg estimation",
              unit="page", dynamic_ncols=True) as pbar:
        for _page_idx, page in iter_pdf_pages(input_pdf, dpi=_PROCESSING_PPI):
            bg_pages_list.append(page)
            pbar.update(1)
            if len(bg_pages_list) >= bg_pages:
                break

    n_total = len(bg_pages_list)
    print(f"  Sampled {n_total} pages for background estimation")

    print(f"  Estimating positional background (p{percentile:.0f})...")
    bg, conf, coverage = positional_background(
        bg_pages_list, percentile=percentile
    )
    print(f"  bg map: R={bg[..., 0].mean():.0f} G={bg[..., 1].mean():.0f} B={bg[..., 2].mean():.0f}")

    # Save background map if requested
    if save_bg_map:
        bg_path = input_pdf.parent / f"{input_pdf.stem}_background.png"
        bg_u8 = np.clip(bg, 0, 255).astype(np.uint8)
        PILImage.fromarray(bg_u8).save(str(bg_path))
        print(f"  Background map saved: {bg_path}")

    # ------------------------------------------------------------------
    # Phase 2: Stream each page — remove background and write immediately.
    # Only one page is in memory at a time (plus the bg map).
    # ------------------------------------------------------------------
    print(f"  Removing background ({model}, intensity={intensity}) and writing...")
    doc = fitz.open()

    total_pages = get_page_count(input_pdf)
    with tqdm(total=total_pages, desc="Removing background",
              unit="page", dynamic_ncols=True) as pbar:
        for page_idx, page in iter_pdf_pages(input_pdf, dpi=_PROCESSING_PPI):
            # Remove background for this single page
            cleaned = remove_background([page], bg, model=model, intensity=intensity)[0]

            # Create output page sized to the cleaned image dimensions
            h, w, _ = cleaned.shape
            out_page = doc.new_page(width=w, height=h)

            # Embed the cleaned page image
            pil_img = PILImage.fromarray(cleaned)
            buf = io.BytesIO()
            if image_format == "jpg":
                pil_img.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
            else:
                pil_img.save(buf, format="PNG")
            buf.seek(0)
            out_page.insert_image(
                fitz.Rect(0, 0, w, h),
                stream=buf.read(),
            )

            pbar.update(1)

    pdf_bytes = doc.tobytes()
    doc.close()

    # Save sample comparison if requested
    if save_sample:
        sample_path = input_pdf.parent / f"{input_pdf.stem}_sample.png"
        # Sample up to 3 pages for comparison
        sample_pages = []
        for idx, page in iter_pdf_pages(input_pdf, dpi=_PROCESSING_PPI):
            sample_pages.append((idx, page))
            if len(sample_pages) >= 3:
                break

        if sample_pages:
            # Generate comparison sheet
            pass  # Imports are at the top of the file

            # Create a strip with all sampled pages
            panels = []
            labels = []
            for idx, page in sample_pages:
                # Compute whitened version
                whitened = remove_background([page], bg, model=model, intensity=intensity)[0]
                # Generate mask from confidence
                mask = (conf < 0.5).astype(np.uint8)
                # Generate comparison panel
                panel = PILImage.new("RGB", (page.shape[1] * 4 + 30, page.shape[0] + 30), "white")
                draw = PILImageDraw.Draw(panel)
                # Original
                orig_img = PILImage.fromarray(page)
                panel.paste(orig_img, (0, 0))
                draw.text((page.shape[1] // 2, page.shape[0] + 15), "Original",
                         fill="black", anchor="mm")
                # Background map
                bg_u8 = np.clip(bg, 0, 255).astype(np.uint8)
                bg_img = PILImage.fromarray(bg_u8)
                panel.paste(bg_img, (page.shape[1] + 10, 0))
                draw.text((page.shape[1] * 3 // 2 + 5, page.shape[0] + 15), "Background",
                         fill="black", anchor="mm")
                # Whitened
                whitened_img = PILImage.fromarray(whitened)
                panel.paste(whitened_img, (page.shape[1] * 2 + 20, 0))
                draw.text((page.shape[1] * 5 // 2 + 10, page.shape[0] + 15), "Cleaned",
                         fill="black", anchor="mm")
                # Mask
                mask_img = np.where(mask, 255, 0).astype(np.uint8)
                mask_img = np.stack([mask_img] * 3, -1)
                mask_pil = PILImage.fromarray(mask_img)
                panel.paste(mask_pil, (page.shape[1] * 3 + 30, 0))
                draw.text((page.shape[1] * 7 // 2 + 15, page.shape[0] + 15), "Mask",
                         fill="black", anchor="mm")

                panels.append(panel)
                labels.append(f"Page {idx + 1}")

            # Combine all panels horizontally
            if panels:
                total_width = sum(p.width for p in panels) + 20 * (len(panels) - 1)
                max_height = max(p.height for p in panels)
                strip = PILImage.new("RGB", (total_width, max_height), "white")
                x_offset = 0
                for i, panel in enumerate(panels):
                    strip.paste(panel, (x_offset, 0))
                    x_offset += panel.width + 20

                strip.save(str(sample_path))
                print(f"  Sample saved: {sample_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(pdf_bytes)
    print(f"  Cleaned PDF saved: {output_path}")

    return output_path
