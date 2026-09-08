"""Generate a PDF from extracted slide images.

Memory efficiency: generator-based. Write images to disk one page at a time
and embed them in the PDF without holding every image in memory.

Sentinel pattern: DetectionStats is yielded at the end of the slides iterator.
These statistics come from detect_slides() and are available after PDF generation.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterable
from pathlib import Path

import img2pdf
from tqdm import tqdm

from .detector import DetectionStats, SlideCandidate


def generate_pdf(
    slides: Iterable[SlideCandidate | DetectionStats],
    output_path: Path,
    image_format: str = "png",
    jpeg_quality: int = 95,
) -> tuple[int, int]:
    """Arrange slide images chronologically and write them to a PDF.

    Use one image per page, size each page to the image aspect ratio, and add no margins.

    slides is a generator; each image is saved to a temporary file. Temporary
    files are managed by tempfile and removed automatically afterward.

    DetectionStats from detect_slides() is yielded at the end of slides and is
    used to retrieve statistics after PDF generation.

    Args:
        slides: SlideCandidate iterator ending with DetectionStats.
        output_path: Output PDF path.
        image_format: "jpg" or "png"
        jpeg_quality: JPEG quality (1-100).

    Returns:
        (total_candidates, duplicates_rejected)

        When no slide images are received, no PDF is written. The caller can
        use the returned counts to report the condition and choose its exit
        status.
    """
    output_path = Path(output_path)

    total_candidates = 0
    duplicates_rejected = 0

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        paths: list[Path] = []

        ext = "jpg" if image_format == "jpg" else "png"
        with tqdm(desc="Generating PDF", unit="slide", dynamic_ncols=True) as pbar:
            for item in slides:
                if isinstance(item, DetectionStats):
                    # Extract statistics
                    total_candidates = item.total_candidates
                    duplicates_rejected = item.duplicates_rejected
                    continue

                # Process the SlideCandidate
                p = tmp / f"slide_{len(paths):04d}.{ext}"
                if item.file_path is not None:
                    # Copy directly from the file path
                    shutil.copy2(str(item.file_path), str(p))
                elif item.image is not None:
                    # Save the PIL Image
                    if image_format == "jpg":
                        item.image.save(str(p), "JPEG", quality=jpeg_quality, optimize=True)
                    else:
                        item.image.save(str(p), "PNG")
                else:
                    raise ValueError(f"SlideCandidate at {item.timestamp} has no image or file_path")
                paths.append(p)
                pbar.update(1)

        # No accepted slides: do not invoke img2pdf or create an empty PDF.
        if not paths:
            return total_candidates, duplicates_rejected

        # Generate the PDF with img2pdf (all paths refer only to files on disk)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(img2pdf.convert([str(p) for p in paths]))

    return total_candidates, duplicates_rejected
