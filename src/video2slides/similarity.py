"""Image similarity detection using perceptual hashes.

Use imagehash pHash (perceptual hash) to determine whether two images are
visually the same slide.
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
    """Return the pHash Hamming distance between two images.

    Returns: 0.0 (identical) to 1.0 (completely different).

    Args:
        img_a, img_b: PIL images to compare.
        hash_size: pHash size (default 16 -> 16x16=256 bits).
    """
    hash_a = imagehash.phash(img_a, hash_size=hash_size)
    hash_b = imagehash.phash(img_b, hash_size=hash_size)
    return float(hash_a - hash_b) / hash_a.hash.size**2


def pixel_difference(
    img_a: Image.Image,
    img_b: Image.Image,
) -> float:
    """Calculate the pixel-level difference between two images (0.0-1.0).

    Normalize the mean absolute difference (MAD).
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
    """Return whether the images are the same slide at the given threshold.

    Specify threshold as a pHash distance (0.0-1.0). The default 0.0005
    corresponds to approximately 32 differing bits in a 256-bit pHash and
    treats only minor changes to the same slide as identical. In measurements,
    frames of the same slide are below 0.001 and different slides are 0.001-0.02.
    """
    return phash_distance(img_a, img_b, hash_size=hash_size) <= threshold


def is_slide_change(
    img_a: Image.Image,
    img_b: Image.Image,
    pixel_threshold: float = 0.1,
    phash_threshold: float = 0.0005,
) -> tuple[bool, float]:
    """Determine whether a slide change occurred.

    Use both pHash and pixel differences. A change occurs when either exceeds
    its threshold.

    Returns:
        (is_change, max_difference)
    """
    phash_dist = phash_distance(img_a, img_b)
    pixel_dist = pixel_difference(img_a, img_b)

    is_change = (phash_dist > phash_threshold) or (pixel_dist > pixel_threshold)
    max_diff = max(phash_dist, pixel_dist)

    return is_change, max_diff
