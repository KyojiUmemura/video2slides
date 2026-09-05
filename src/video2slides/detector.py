"""スライド切替検出と重複除去。

候補フレームから、スライドが切り替わった箇所の
「安定した代表フレーム」を抽出する。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from PIL import Image

from .similarity import are_similar, is_slide_change

logger = logging.getLogger(__name__)


@dataclass
class SlideCandidate:
    """スライド候補"""
    timestamp: float
    image: Image.Image
    status: str  # "SAME", "CHANGE", "TRANSITION", "STABLE", "SAVE"


@dataclass
class DetectionResult:
    """検出結果"""
    accepted: list[SlideCandidate] = field(default_factory=list)
    duplicates_rejected: int = 0
    total_candidates: int = 0


def detect_slides(
    frames: Iterable[tuple[float, Image.Image]],
    similarity_threshold: float = 0.02,
    pixel_threshold: float = 0.1,
    settle_time: float = 0.7,
    dedup_mode: str = "keep",  # "keep" or "remove"
    verbose: bool = False,
    debug_dir: Path | None = None,
) -> DetectionResult:
    """スライド切替を検出し、安定した代表フレームを抽出する。

    処理フロー:
      1. 連続フレームを比較し、十分に異なる場合は「CHANGE」と判定
      2. 切替検出後、settle_time 秒経過するまで待機
      3. 安定した時点で代表フレームとして保存
      4. 前のスライドと同一の場合、dedup_mode に応じて除外

    Args:
        frames: 時系列順の (timestamp, PIL.Image) イテラブル
        similarity_threshold: pHash distance 閾値 (0.0〜1.0、デフォルト: 0.02)
        pixel_threshold: ピクセル差分閾値 (0.0〜1.0、デフォルト: 0.1)
        settle_time: スライド切替検出後の安定待ち時間（秒、デフォルト: 0.7）
        dedup_mode: "keep"=離れて再登場も残す, "remove"=全重複を除去
        verbose: デバッグ情報を出力
        debug_dir: debug/ 画像を保存するディレクトリ（None で保存しない）

    Returns:
        DetectionResult
    """
    result = DetectionResult()

    # 状態管理
    prev_image: Image.Image | None = None
    settle_start: float = 0.0  # 切替検出時刻
    settling: bool = False      # 安定待ち中
    last_saved_image: Image.Image | None = None  # 最後に保存したスライド
    consecutive_same: int = 0  # 連続 SAME 数
    total_candidates = 0

    for timestamp, img in frames:
        total_candidates += 1
        if prev_image is None:
            prev_image = img
            if verbose:
                print(f"{_fmt_ts(timestamp)} INIT -> SAVE")
            result.accepted.append(SlideCandidate(
                timestamp=timestamp, image=img, status="SAVE"
            ))
            if debug_dir:
                _save_debug(debug_dir, timestamp, img, "INIT")
            consecutive_same = 0
            continue

        # 類似度判定（pHash + ピクセル差分）
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
            # 類似している場合
            if settling:
                # 安定待ち中
                status = "TRANSITION"
                # 安定したか確認
                if timestamp - settle_start >= settle_time:
                    # 現在のフレームが last_saved と同じか確認
                    if last_saved_image is not None and are_similar(
                        last_saved_image, img, similarity_threshold
                    ):
                        # 前と同じスライドに戻った
                        if dedup_mode == "remove":
                            status = "SAME"
                            result.duplicates_rejected += 1
                            if verbose:
                                print(f"{_fmt_ts(timestamp)} difference={max_diff:.3f} SAME (dedup)")
                            prev_image = img
                            continue
                    # 安定 → 保存
                    settling = False
                    status = "STABLE"
            else:
                status = "SAME"
                consecutive_same += 1

        if verbose:
            print(f"{_fmt_ts(timestamp)} difference={max_diff:.3f} {status}")

        if status == "STABLE":
            # 重複チェック
            if last_saved_image is not None and are_similar(
                last_saved_image, img, similarity_threshold
            ):
                if dedup_mode == "remove":
                    result.duplicates_rejected += 1
                    if verbose:
                        print(f"{_fmt_ts(timestamp)} SAME (duplicate of previous)")
                    prev_image = img
                    continue

            # 保存
            result.accepted.append(SlideCandidate(
                timestamp=timestamp, image=img, status="SAVE"
            ))
            last_saved_image = img
            if debug_dir:
                _save_debug(debug_dir, timestamp, img, "SLIDE")

        prev_image = img

    result.total_candidates = total_candidates
    return result


def _calc_approx_diff(a: Image.Image, b: Image.Image) -> float:
    """2画像の大まかな差分（0.0〜1.0）を推定する。"""
    import imagehash
    ha = imagehash.phash(a)
    hb = imagehash.phash(b)
    return float(ha - hb) / ha.hash.size**2


def _fmt_ts(ts: float) -> str:
    """秒を HH:MM:SS.ss にフォーマットする。"""
    hours = int(ts // 3600)
    mins = int((ts % 3600) // 60)
    secs = ts % 60
    return f"{hours:02d}:{mins:02d}:{secs:05.2f}"


def _save_debug(debug_dir: Path, timestamp: float, img: Image.Image, label: str) -> None:
    """debug/ に判定候補画像を保存する。"""
    debug_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{_fmt_ts(timestamp).replace(':', '-')}.png"
    img.save(debug_dir / f"{fname}_{label}.png")
