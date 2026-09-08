"""CLI entry point."""

from __future__ import annotations

import argparse
import logging
import statistics
import sys
from pathlib import Path

from .arguments import (
    crop_rect,
    jpeg_quality,
    nonnegative_float,
    percentile_float,
    positive_float,
    positive_int,
    unit_interval_float,
)
from .clean_pdf import clean_pdf
from .detector import detect_slides
from .pdf import generate_pdf
from .video import check_ffmpeg, extract_frames, probe_video

_VERSION = "26.09.08"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="video2slides",
        description="Automatically generate a slide PDF from a video",
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Input video file path",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output PDF file path (default: input filename.pdf)",
    )
    parser.add_argument(
        "--sample-interval",
        type=positive_float,
        metavar="FLOAT",
        default=2.0,
        help="Frame extraction interval in seconds (greater than 0; default: 2)",
    )
    parser.add_argument(
        "--settle-time",
        type=nonnegative_float,
        metavar="FLOAT",
        default=0.7,
        help="Settle time after a slide change in seconds (0 or greater; default: 0.7)",
    )
    parser.add_argument(
        "--similarity-threshold",
        type=unit_interval_float,
        metavar="FLOAT",
        default=0.0005,
        help="Similarity threshold as pHash distance (0.0-1.0; default: 0.0005)",
    )
    parser.add_argument(
        "--crop",
        type=crop_rect,
        metavar="x,y,width,height",
        default=None,
        help="Crop region (x,y >= 0, width,height > 0)",
    )
    parser.add_argument(
        "--background-color-detection",
        choices=["on", "off"],
        default="off",
        help="Detect slide-dominant frames (default: off)",
    )
    parser.add_argument(
        "--dedup-mode",
        choices=["keep", "remove"],
        default="keep",
        help="Candidate identical to the last saved slide: keep or remove (default: keep)",
    )
    parser.add_argument(
        "--clean",
        choices=["on", "off"],
        default="off",
        help="Remove the slide PDF background (default: off)",
    )
    parser.add_argument(
        "--bg-pages",
        type=positive_int,
        metavar="INT",
        default=60,
        help="Number of pages used to estimate the background (1 or greater; default: 60)",
    )
    parser.add_argument(
        "--percentile",
        type=percentile_float,
        metavar="FLOAT",
        default=90.0,
        help="Background estimation percentile (0.0-100.0; default: 90.0)",
    )
    parser.add_argument(
        "--intensity",
        type=unit_interval_float,
        metavar="FLOAT",
        default=1.0,
        help="Background removal intensity, 0.0-1.0 (default: 1.0)",
    )
    parser.add_argument(
        "--image-format",
        choices=["jpg", "png"],
        default="jpg",
        help="Slide image format (default: jpg)",
    )
    parser.add_argument(
        "--jpeg-quality",
        type=jpeg_quality,
        metavar="N",
        default=95,
        help="JPEG quality (1-100; default: 95)",
    )
    parser.add_argument(
        "--background",
        action="store_true",
        help="Save the estimated background map to {stem}_background.png",
    )
    parser.add_argument(
        "--quick-sample",
        action="store_true",
        help="Save a comparison sheet of the original, background map, and result to {stem}_sample.png",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print debug information",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable --verbose and save candidate images to debug/",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing output file",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"video2slides {_VERSION}",
    )
    return parser


def _fmt_ts(ts: float) -> str:
    """Format seconds as HH:MM:SS.ss."""
    hours = int(ts // 3600)
    mins = int((ts % 3600) // 60)
    secs = ts % 60
    return f"{hours:02d}:{mins:02d}:{secs:05.2f}"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    # Validate the input file
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        return 1

    # Check FFmpeg
    if not check_ffmpeg():
        print(
            "Error: ffmpeg / ffprobe not found.\n"
            "If you use Homebrew: brew install ffmpeg",
            file=sys.stderr,
        )
        return 1

    # Determine the output path
    output_path = args.output or args.input.with_suffix(".pdf")

    # Handle an existing output file
    if output_path.exists():
        if args.overwrite:
            print(f"Overwriting existing file: {output_path}")
        else:
            print(f"Error: Output file already exists: {output_path}", file=sys.stderr)
            print("  Specify --overwrite or remove the existing file.", file=sys.stderr)
            return 1

    crop = args.crop

    # ===== Main processing =====
    print(f"Analyzing video: {args.input.name}")

    # Read video metadata
    try:
        info = probe_video(args.input)
    except Exception as e:
        print(f"Error: Failed to read video information: {e}", file=sys.stderr)
        return 1

    if crop is not None:
        x, y, width, height = crop
        if x + width > info.width or y + height > info.height:
            print(
                "Error: The --crop region exceeds the video frame"
                f" ({info.width}x{info.height}): {x},{y},{width},{height}",
                file=sys.stderr,
            )
            return 1

    print(f"Duration: {_fmt_ts(info.duration)}")
    print(f"Resolution: {info.width}x{info.height} @ {info.fps:.1f} fps")
    if crop is not None:
        print(f"Crop: {','.join(str(value) for value in crop)}")
    if args.background_color_detection == "on":
        print("Background color detection: on")
    print()

    # Extract frames
    print("Extracting frames...")
    frames_gen, detection_stats = extract_frames(
        args.input,
        interval=args.sample_interval,
        crop=crop,
        background_color_detection=(args.background_color_detection == "on"),
        verbose=args.verbose,
    )
    # Pass the generator directly to detect_slides (statistics are updated there)
    frames_iter = frames_gen

    # Detect slides (consumes the generator and updates statistics)
    debug_dir = Path("debug") if args.debug else None
    print("Detecting slides...")

    slides = detect_slides(
        frames=frames_iter,
        similarity_threshold=args.similarity_threshold,
        settle_time=args.settle_time,
        dedup_mode=args.dedup_mode,
        verbose=args.verbose,
        debug_dir=debug_dir,
    )

    # Generate the PDF (pass the generator directly and collect statistics)
    print(f"\nGenerating PDF: {output_path}")
    total_candidates, duplicates_rejected = generate_pdf(
        slides, output_path,
        image_format=args.image_format,
        jpeg_quality=args.jpeg_quality,
    )

    # Display progress
    print()
    print(f"Extracted {detection_stats['total']} candidate frames")
    print(f"Candidates detected: {total_candidates}")
    print(f"Slides accepted: {total_candidates - duplicates_rejected}")
    print(f"Duplicates rejected: {duplicates_rejected}")

    # The frame generator was consumed by generate_pdf(), so statistics are final here.
    if args.background_color_detection == "on" and detection_stats["total"] > 0:
        ratios = detection_stats["ratios"]
        detected_ratios = [r for r in ratios if r >= 0.20]
        rejected_ratios = [r for r in ratios if r < 0.20]

        print("\nBackground color detection statistics:")
        print(f"  Total sampled frames: {detection_stats['total']}")
        print(f"  Detected (slide-dominant, ratio >= 0.20): {detection_stats['detected']}")
        print(f"  Rejected (non-slide-dominant, ratio < 0.20): {detection_stats['rejected']}")

        if detected_ratios:
            print("\n  DETECT frames:")
            print(f"    Count: {len(detected_ratios)}")
            print(f"    Max ratio: {max(detected_ratios):.4f}")
            print(f"    Min ratio: {min(detected_ratios):.4f}")
            print(f"    Average ratio: {statistics.mean(detected_ratios):.4f}")
            if len(detected_ratios) > 1:
                print(f"    Std dev: {statistics.stdev(detected_ratios):.4f}")

        if rejected_ratios:
            print("\n  NON-DETECT frames:")
            print(f"    Count: {len(rejected_ratios)}")
            print(f"    Max ratio: {max(rejected_ratios):.4f}")
            print(f"    Min ratio: {min(rejected_ratios):.4f}")
            print(f"    Average ratio: {statistics.mean(rejected_ratios):.4f}")
            if len(rejected_ratios) > 1:
                print(f"    Std dev: {statistics.stdev(rejected_ratios):.4f}")

    if total_candidates - duplicates_rejected == 0:
        print("Error: No slides were detected.", file=sys.stderr)
        return 1

    # Remove the background
    if args.clean == "on":
        # Avoid double _cleaned suffix
        stem = output_path.stem
        if stem.endswith("_cleaned"):
            cleaned_name = f"{stem}.pdf"
        else:
            cleaned_name = f"{stem}_cleaned.pdf"
        cleaned_path = output_path.parent / cleaned_name
        print(f"\nCleaning background: {cleaned_path}")
        try:
            clean_pdf(
                output_path, cleaned_path,
                bg_pages=args.bg_pages,
                percentile=args.percentile,
                intensity=args.intensity,
                image_format=args.image_format,
                jpeg_quality=args.jpeg_quality,
                save_bg_map=args.background,
                save_sample=args.quick_sample,
            )
        except Exception as e:
            print(f"Error: Background removal failed: {e}", file=sys.stderr)
            return 1

        # Rename: backup original -> {stem}_old.pdf, then move cleaned -> {stem}.pdf
        if output_path.exists():
            backup_path = output_path.parent / f"{stem}_original.pdf"
            output_path.rename(backup_path)
            print(f"  Original backed up: {backup_path}")
        cleaned_path.rename(output_path)
        print(f"  Cleaned PDF saved: {output_path}")

    print(f"Done! {total_candidates - duplicates_rejected} slides -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
