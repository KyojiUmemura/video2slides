"""動画ファイルの読み込みとフレーム抽出。

FFmpeg / ffprobe を subprocess で呼び出し、
一定間隔でフレームを取得する。
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import cv2
from PIL import Image


@dataclass
class VideoInfo:
    """動画のメタ情報"""
    path: Path
    duration: float  # 秒
    width: int
    height: int
    fps: float


def check_ffmpeg() -> bool:
    """ffmpeg と ffprobe が利用可能か確認する。"""
    for cmd in ("ffmpeg", "ffprobe"):
        if shutil.which(cmd) is None:
            return False
    return True


def probe_video(path: Path) -> VideoInfo:
    """ffprobe で動画のメタ情報を取得する。"""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    import json
    info = json.loads(result.stdout)

    # 動画ストリームを取得
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

    # fps の取得（r_frame_rate または avg_frame_rate）
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


def extract_frames(
    video_path: Path,
    interval: float = 0.5,
) -> list[tuple[float, Image.Image]]:
    """動画から一定間隔でフレームを抽出する。

    戻り値: [(timestamp_sec, PIL.Image), ...] のリスト
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"動画を開けませんでした: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_interval = max(1, int(fps * interval))

    frames: list[tuple[float, Image.Image]] = []
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_interval == 0:
            timestamp = frame_idx / fps
            # BGR -> RGB 変換
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            frames.append((timestamp, img))

        frame_idx += 1

    cap.release()
    return frames


def save_image(img: Image.Image, path: Path, fmt: str = "jpg", quality: int = 95) -> None:
    """画像をファイルに保存する。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "png":
        img.save(str(path), "PNG")
    else:
        img.save(str(path), "JPEG", quality=quality, optimize=True)
