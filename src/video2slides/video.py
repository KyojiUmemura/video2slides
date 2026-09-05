"""動画ファイルの読み込みとフレーム抽出。

FFmpeg / ffprobe を subprocess で呼び出し、
一定間隔でフレームを取得する。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from tqdm import tqdm


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


def _calc_slide_dominance_ratio(img: Image.Image) -> float:
    """画像のスライド主体比率を計算する。

    約1000ピクセルをランダムにサンプリングし、
    最も多い色の比率（max_count / n_samples）を返す。
    0.0〜1.0 の値を返す。
    """
    arr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2HSV)
    h, w = arr.shape[:2]
    # 約1000ピクセルをランダムにサンプリング
    n_samples = 1000
    if h * w > n_samples:
        indices = np.random.choice(h * w, n_samples, replace=False)
        y = indices // w
        x = indices % w
        arr = arr[y, x]
    # 色を量子化（H: 16段階, S/V: 8段階）
    h_quant = (arr[:, 0] // 16) * 16
    s_quant = (arr[:, 1] // 32) * 32
    v_quant = (arr[:, 2] // 32) * 32
    # 量子化された色を結合
    quantized_colors = (h_quant.astype(np.int32) << 16) | (s_quant.astype(np.int32) << 8) | v_quant.astype(np.int32)
    # 各色の出現回数をカウント
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
    """動画から一定間隔でフレームをストリーミング抽出する。

    戻り値: (generator, 検出統計) のタプル
    検出統計: {"total": int, "detected": int, "rejected": int, "ratios": [float]}

    注意: generator は一度だけ消費される。統計情報 (stats) は generator を
    完全にイテレートした後に正確になる。
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"動画を開けませんでした: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_interval = max(1, int(fps * interval))

    frame_idx = 0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # 検出統計
    detected_count = 0
    rejected_count = 0
    detection_ratios: list[float] = []

    desc = f"Extracting frames from {video_path.name}"
    pbar = tqdm(total=total_frames, desc=desc, unit="frame", position=0, leave=True)

    def frame_generator():
        nonlocal frame_idx, detected_count, rejected_count

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % frame_interval == 0:
                timestamp = frame_idx / fps
                # BGR -> RGB 変換
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(rgb)

                # 切り抜き
                if crop is not None:
                    x, y, w, h = crop
                    img = img.crop((x, y, x + w, y + h))

                # スライド主体判定
                if background_color_detection:
                    ratio = _calc_slide_dominance_ratio(img)
                    # 検出比率を記録（実際の比率値）
                    detection_ratios.append(ratio)
                    if ratio < 0.20:  # 20% 未満は非スライド主体
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

    # 統計情報を格納する辞書
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
            # イテレート終了時に統計を更新
            stats["total"] = len(detection_ratios)
            stats["detected"] = detected_count
            stats["rejected"] = rejected_count
            stats["ratios"] = detection_ratios.copy()
            cap.release()
            pbar.close()

    return wrapped_generator(), stats


def save_image(img: Image.Image, path: Path, fmt: str = "jpg", quality: int = 95) -> None:
    """画像をファイルに保存する。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "png":
        img.save(str(path), "PNG")
    else:
        img.save(str(path), "JPEG", quality=quality, optimize=True)
