"""Integration tests for generating a slide PDF from a video.

Generate a test video with FFmpeg, process it with video2slides, and verify
that the expected number of slides is detected.
"""

import subprocess
import sys
from pathlib import Path

import pytest

# Add src/ to the import path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from video2slides.cli import main


@pytest.fixture(scope="module")
def test_video(tmp_path_factory):
    """Generate a three-slide test video with five seconds per slide."""
    video_path = tmp_path_factory.mktemp("test_data") / "test_slides.mp4"

    # Slide A: white background + blue bar at the top
    # Slide B: white background + red bar on the left
    # Slide C: solid blue background
    slide_files = []
    for i, (vf, color) in enumerate([
        ("drawbox=x=0:y=0:w=640:h=80:color=blue:t=fill", "white"),
        ("drawbox=x=0:y=0:w=120:h=480:color=red:t=fill", "white"),
        ("null", "blue"),
    ]):
        slide_path = tmp_path_factory.mktemp("slides") / f"slide_{i}.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c={color}:s=640x480:d=5",
            "-vf", vf if vf != "null" else "null",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(slide_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        slide_files.append(slide_path)

    concat_list = tmp_path_factory.mktemp("concat") / "list.txt"
    concat_list.write_text("\n".join(f"file '{p}'" for p in slide_files) + "\n")

    # Concatenate
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(video_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return video_path


def test_three_slides_detected(test_video):
    """A three-slide video produces a three-page PDF."""
    output_pdf = test_video.parent / f"{test_video.stem}_slides.pdf"

    # Remove an existing PDF
    if output_pdf.exists():
        output_pdf.unlink()

    ret = main([
        str(test_video),
        "--output", str(output_pdf),
        "--sample-interval", "0.5",
        "--settle-time", "0.5",
        "--similarity-threshold", "0.02",
    ])

    assert ret == 0, "CLI execution failed"
    assert output_pdf.exists(), "PDF was not generated"

    # Verify the PDF page count
    import fitz
    doc = fitz.open(str(output_pdf))
    page_count = len(doc)
    doc.close()
    assert page_count >= 3, f"Expected at least 3 pages, got {page_count}"


def test_output_not_overwritten(test_video):
    """Do not overwrite an existing output file."""
    output_pdf = test_video.parent / f"{test_video.stem}_slides.pdf"

    # Create an existing PDF
    output_pdf.write_bytes(b"%PDF-1.4 fake content")

    ret = main([
        str(test_video),
        "--output", str(output_pdf),
        "--sample-interval", "0.5",
        "--settle-time", "0.5",
    ])

    assert ret == 1, "Expected error when output exists"
    # The file remains unchanged
    assert output_pdf.read_bytes() == b"%PDF-1.4 fake content"


def test_overwrite_flag(test_video):
    """--overwrite allows an existing file to be overwritten."""
    output_pdf = test_video.parent / f"{test_video.stem}_slides.pdf"

    # Create an existing PDF
    output_pdf.write_bytes(b"%PDF-1.4 fake content")

    ret = main([
        str(test_video),
        "--output", str(output_pdf),
        "--sample-interval", "0.5",
        "--settle-time", "0.5",
        "--overwrite",
    ])

    assert ret == 0, "CLI execution failed with --overwrite"
    # The file was overwritten (its contents differ)
    assert output_pdf.read_bytes() != b"%PDF-1.4 fake content"


def test_generate_pdf_with_file_paths():
    """generate_pdf() accepts SlideCandidate input."""
    from PIL import Image

    from video2slides.detector import DetectionStats, SlideCandidate
    from video2slides.pdf import generate_pdf

    # Create test images on disk
    img_a = Image.new("RGB", (100, 100), "red")
    img_b = Image.new("RGB", (100, 100), "blue")
    path_a = Path("/tmp/test_pdf_a.png")
    path_b = Path("/tmp/test_pdf_b.png")
    img_a.save(str(path_a))
    img_b.save(str(path_b))
    img_a.close()
    img_b.close()

    # Create SlideCandidate objects
    slides: list[SlideCandidate | DetectionStats] = [
        SlideCandidate(timestamp=0.0, file_path=path_a),
        SlideCandidate(timestamp=1.0, file_path=path_b),
        DetectionStats(total_candidates=2, duplicates_rejected=0),
    ]

    output = Path("/tmp/test_pdf_output.pdf")
    total_candidates, duplicates_rejected = generate_pdf(slides, output)
    assert output.exists()
    assert output.stat().st_size > 0
    assert total_candidates == 2
    assert duplicates_rejected == 0

    # Verify the PDF page count
    import fitz
    doc = fitz.open(str(output))
    assert len(doc) == 2, f"Expected 2 pages, got {len(doc)}"
    doc.close()

    # Clean up
    path_a.unlink()
    path_b.unlink()
    output.unlink()


def test_slide_candidate_with_file_path():
    """SlideCandidate supports file_path."""
    from video2slides.detector import SlideCandidate

    c = SlideCandidate(
        timestamp=1.0,
        image=None,
        file_path=Path("/tmp/test.png"),
        status="SAVE",
    )
    assert c.status == "SAVE"
    assert c.file_path == Path("/tmp/test.png")
    assert c.image is None

    # Image-only case
    from PIL import Image
    img = Image.new("RGB", (10, 10), "white")
    c2 = SlideCandidate(timestamp=2.0, image=img, file_path=None, status="SAVE")
    assert c2.image is not None
    assert c2.file_path is None
    img.close()
