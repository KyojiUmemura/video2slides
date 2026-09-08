"""Slide-change detection and duplicate removal.

Extract a stable representative frame where a slide changes.

Memory efficiency: generator-based. Detected slide images flow directly into
PDF generation, and the detector retains only the most recent frames.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from PIL import Image

from .similarity import are_similar, is_slide_change

logger = logging.getLogger(__name__)


@dataclass
class SlideCandidate:
    """Slide candidate."""
    timestamp: float
    image: Image.Image | None = None
    file_path: Path | None = None
    status: str = "SAVE"  # "SAME", "CHANGE", "TRANSITION", "STABLE", "SAVE"


@dataclass
class DetectionResult:
    """Detection results (statistics)."""
    total_candidates: int = 0
    duplicates_rejected: int = 0


def detect_slides(
    frames: Iterable[tuple[float, Image.Image]],
    similarity_threshold: float = 0.0005,
    pixel_threshold: float = 0.1,
    settle_time: float = 0.7,
    dedup_mode: str = "keep",  # "keep" or "remove"
    verbose: bool = False,
    debug_dir: Path | None = None,
) -> Iterator[SlideCandidate | DetectionStats]:
    """Detect slide changes and stream stable representative frames.

    Processing flow:
      1. Compare consecutive frames and mark sufficiently different ones as CHANGE.
      2. Wait settle_time seconds after detecting a change.
      3. Yield a representative frame once stable.
      4. If it matches the previous slide, exclude it according to dedup_mode.

    Args:
        frames: Iterable of (timestamp, PIL.Image) in chronological order.
        similarity_threshold: pHash distance threshold (0.0-1.0; default: 0.0005).
        pixel_threshold: Pixel difference threshold (0.0-1.0; default: 0.1).
        settle_time: Seconds to wait after a slide change (default: 0.7).
        dedup_mode: "keep" retains candidates; "remove" drops a candidate identical
                    to the last saved slide. It does not compare all prior slides.
        verbose: Print debug information.
        debug_dir: Directory for debug images (None disables saving).

    Yields:
        SlideCandidate: Detected slide candidates in chronological order.
    """
    # State management
    prev_image: Image.Image | None = None
    settle_start: float = 0.0  # Change detection time
    settling: bool = False      # Waiting for stability
    last_saved_image: Image.Image | None = None  # Last saved slide
    consecutive_same: int = 0
    total_candidates = 0
    duplicates_rejected = 0

    for timestamp, img in frames:
        total_candidates += 1
        if prev_image is None:
            prev_image = img
            if verbose:
                print(f"{_fmt_ts(timestamp)} INIT -> SAVE")
            yield SlideCandidate(
                timestamp=timestamp, image=img, status="SAVE"
            )
            if debug_dir:
                _save_debug(debug_dir, timestamp, img, "INIT")
            consecutive_same = 0
            continue

        # Similarity check (pHash + pixel difference)
        is_change, max_diff = is_slide_change(
            prev_image, img,
            pixel_threshold=pixel_threshold,
            phash_threshold=similarity_threshold,
        )

        if is_change:
            if settling:
                status = "TRANSITION"
            else:
                status = "CHANGE"
                settling = True
                settle_start = timestamp
        else:
            # When similar
            if settling:
                # Waiting for stability
                status = "TRANSITION"
                # Check whether the frame is stable
                if timestamp - settle_start >= settle_time:
                    # Check whether the current frame matches last_saved
                    if last_saved_image is not None and are_similar(
                        last_saved_image, img, similarity_threshold
                    ):
                        # Returned to the previous slide
                        if dedup_mode == "remove":
                            status = "SAME"
                            duplicates_rejected += 1
                            if verbose:
                                print(f"{_fmt_ts(timestamp)} difference={max_diff:.3f} SAME (dedup)")
                            prev_image = img
                            continue
                    # Stable -> save
                    settling = False
                    status = "STABLE"
            else:
                status = "SAME"
                consecutive_same += 1

        if verbose:
            print(f"{_fmt_ts(timestamp)} difference={max_diff:.3f} {status}")

        if status == "STABLE":
            # Check for duplicates
            if last_saved_image is not None and are_similar(
                last_saved_image, img, similarity_threshold
            ):
                if dedup_mode == "remove":
                    duplicates_rejected += 1
                    if verbose:
                        print(f"{_fmt_ts(timestamp)} SAME (duplicate of previous)")
                    prev_image = img
                    continue

            # Save
            yield SlideCandidate(
                timestamp=timestamp, image=img, status="SAVE"
            )
            last_saved_image = img
            if debug_dir:
                _save_debug(debug_dir, timestamp, img, "SLIDE")

        prev_image = img

    # Special object for returning statistics (available when iteration ends)
    # NOTE: Identification with isinstance is fragile. A future SlideCandidate
    # subclass could collide, so replace this with a dedicated end marker if needed.
    yield DetectionStats(total_candidates, duplicates_rejected)


@dataclass
class DetectionStats:
    """Detection statistics (yielded at the end as a sentinel)."""
    total_candidates: int
    duplicates_rejected: int


def _fmt_ts(ts: float) -> str:
    """Format seconds as HH:MM:SS.ss."""
    hours = int(ts // 3600)
    mins = int((ts % 3600) // 60)
    secs = ts % 60
    return f"{hours:02d}:{mins:02d}:{secs:05.2f}"


def _save_debug(debug_dir: Path, timestamp: float, img: Image.Image, label: str) -> None:
    """Save a candidate image to debug/."""
    debug_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{_fmt_ts(timestamp).replace(':', '-')}.png"
    img.save(debug_dir / f"{fname}_{label}.png")
