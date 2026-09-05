"""画像の知覚ハッシュによる類似度判定。

imagehash の pHash（perceptual hash）を使用して、
2つの画像が「視覚的に同じスライド」かどうかを判定する。
"""

from __future__ import annotations

import imagehash
import numpy as np
from PIL import Image


def phash_distance(
    img_a: Image.Image,
    img_b: Image.Image,
    hash_size: int = 16,
) -> float:
    """2画像の pHash ハミング距離を返す。

    戻り値: 0.0（完全に同一）〜 1.0（完全に異なる）

    Args:
        img_a, img_b: 比較する PIL 画像
        hash_size: pHash のハッシュサイズ（デフォルト 16 → 16x16=256bit）
    """
    hash_a = imagehash.phash(img_a, hash_size=hash_size)
    hash_b = imagehash.phash(img_b, hash_size=hash_size)
    return float(hash_a - hash_b) / hash_a.hash.size**2


def pixel_difference(
    img_a: Image.Image,
    img_b: Image.Image,
) -> float:
    """2画像のピクセルレベル差分（0.0〜1.0）を計算する。

    平均絶対差分（MAD）を正規化。
    """
    arr_a = np.array(img_a.convert("L"), dtype=np.float64)
    arr_b = np.array(img_b.convert("L"), dtype=np.float64)
    mad = np.mean(np.abs(arr_a - arr_b))
    return float(mad) / 255.0


def are_similar(
    img_a: Image.Image,
    img_b: Image.Image,
    threshold: float = 0.0005,
    hash_size: int = 16,
) -> bool:
    """threshold 以下なら「同じスライド」と判定する。

    threshold は pHash distance (0.0〜1.0) で指定する。
    デフォルト 0.0005 は 256bit pHash の約 32bit 差に相当し、
    同一スライドのわずかな変化のみを「同じ」と扱う。
    実測では、同一スライドのフレーム間: <0.001、
    異なるスライド: 0.001〜0.02 の範囲になる。
    """
    return phash_distance(img_a, img_b, hash_size=hash_size) <= threshold


def is_slide_change(
    img_a: Image.Image,
    img_b: Image.Image,
    pixel_threshold: float = 0.1,
    phash_threshold: float = 0.0005,
) -> tuple[bool, float]:
    """スライド切替かどうかを判定する。

    pHash とピクセル差分の両方を使用して判定。
    どちらか一方でも閾値を超えたら「切替あり」とする。

    Returns:
        (is_change, max_difference)
    """
    phash_dist = phash_distance(img_a, img_b)
    pixel_dist = pixel_difference(img_a, img_b)

    is_change = (phash_dist > phash_threshold) or (pixel_dist > pixel_threshold)
    max_diff = max(phash_dist, pixel_dist)

    return is_change, max_diff
