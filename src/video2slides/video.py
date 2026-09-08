"""Video file loading and frame extraction.

Call FFmpeg / ffprobe via subprocess and retrieve frames at regular intervals.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from tqdm import tqdm


@dataclass
class VideoInfo:
    """Video metadata."""
    path: Path
    duration: float  # seconds
    width: int
    height: int
    fps: float


def check_ffmpeg() -> bool:
    """Check whether ffmpeg and ffprobe are available."""
    for cmd in ("ffmpeg", "ffprobe"):
        if shutil.which(cmd) is None:
            return False
    return True


def probe_video(path: Path) -> VideoInfo:
    """Retrieve video metadata with ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    info = json.loads(result.stdout)

    # Get the video stream
    video_stream = None
    for s in info["streams"]:
        if s["codec_type"] == "video":
            video_stream = s
            break
    if video_stream is None:
        raise RuntimeError(f"{path}: video stream not found")

    duration = float(info["format"]["duration"])
    width = int(video_stream["width"])
    height = int(video_stream["height"])

    # Get fps (r_frame_rate or avg_frame_rate)
    fps_str = video_stream.get(
        "r_frame_rate", video_stream.get("avg_frame_rate", "0/1")
    )
    if "/" in fps_str:
        num, den = fps_str.split("/")
        fps = float(num) / float(den) if float(den) != 0 else 25.0
    else:
        fps = float(fps_str)

    return VideoInfo(
        path=path,
        duration=duration,
        width=width,
        height=height,
        fps=fps,
    )


def _calc_slide_dominance_ratio(img: Image.Image) -> float:
    """Calculate the slide-dominance ratio of an image.

    Randomly sample approximately 1,000 pixels and return the ratio of the
    most common color (max_count / n_samples), from 0.0 to 1.0.
    """
    arr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2HSV)
    h, w = arr.shape[:2]
    # Randomly sample approximately 1,000 pixels
    n_samples = 1000
    if h * w > n_samples:
        indices = np.random.choice(h * w, n_samples, replace=False)
        y = indices // w
        x = indices % w
        arr = arr[y, x]
    # Quantize colors (H: 16 levels, S/V: 8 levels)
    h_quant = (arr[:, 0] // 16) * 16
    s_quant = (arr[:, 1] // 32) * 32
    v_quant = (arr[:, 2] // 32) * 32
    # Combine the quantized color channels
    quantized_colors = (h_quant.astype(np.int32) << 16) | (s_quant.astype(np.int32) << 8) | v_quant.astype(np.int32)
    # Count occurrences of each color
    unique_colors, counts = np.unique(quantized_colors, return_counts=True)
    if counts.size == 0:
        return 0.0
    max_count = counts.max()
    return max_count / n_samples


def extract_frames(
    video_path: Path,
    interval: float = 0.5,
    crop: tuple[int, int, int, int] | None = None,
    background_color_detection: bool = False,
    verbose: bool = False,
) -> tuple[Generator[tuple[float, Image.Image], None, None], dict]:
    """Stream frames from a video at regular intervals.

    Returns: A (generator, detection statistics) tuple.
    Detection statistics: {"total": int, "detected": int, "rejected": int, "ratios": [float]}

    Note: The generator can be consumed only once. Its statistics become
    accurate after it has been fully iterated.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_interval = max(1, int(fps * interval))

    frame_idx = 0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Detection statistics
    sampled_count = 0
    detected_count = 0
    rejected_count = 0
    detection_ratios: list[float] = []

    desc = "Extracting frames"
    pbar = tqdm(total=total_frames, desc=desc, unit="frame", position=0, leave=True)

    def frame_generator():
        nonlocal frame_idx, sampled_count, detected_count, rejected_count

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % frame_interval == 0:
                timestamp = frame_idx / fps
                sampled_count += 1
                # Convert BGR to RGB
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(rgb)

                # Crop
                if crop is not None:
                    x, y, w, h = crop
                    img = img.crop((x, y, x + w, y + h))

                # Determine whether the frame is slide-dominant
                if background_color_detection:
                    ratio = _calc_slide_dominance_ratio(img)
                    # Record the actual detection ratio
                    detection_ratios.append(ratio)
                    if ratio < 0.20:  # Less than 20% is not slide-dominant
                        if verbose:
                            print(f"  SKIP (ratio={ratio:.3f} < 0.20): {timestamp:.1f}s")
                        rejected_count += 1
                        frame_idx += 1
                        pbar.update(1)
                        continue
                    detected_count += 1
                else:
                    detected_count += 1

                yield (timestamp, img)

            frame_idx += 1
            pbar.update(1)

    # Dictionary that stores statistics
    stats = {
        "total": 0,
        "detected": 0,
        "rejected": 0,
        "ratios": [],
    }

    def wrapped_generator():
        nonlocal detected_count, rejected_count
        try:
            yield from frame_generator()
        finally:
            # Update statistics when iteration finishes
            stats["total"] = sampled_count
            stats["detected"] = detected_count
            stats["rejected"] = rejected_count
            stats["ratios"] = detection_ratios.copy()
            cap.release()
            pbar.close()

    return wrapped_generator(), stats
