"""Background removal.

Two models are supported:

- **additive** (default):  output = input - intensity * background
  Suitable when the background is a bright overlay (watermark, light tint).

- **multiplicative** (white-balance):  output = clip(input * (255/bg)^intensity, 0, 255)
  Suitable when the background is a darker overlay that scales the content.

Both models clip the result to [0, 255].
"""

from __future__ import annotations

import numpy as np


def remove_background(
    pages: list[np.ndarray],
    bg,
    model: str = "additive",
    intensity: float = 1.0,
    clip_min: int = 0,
) -> list[np.ndarray]:
    """Remove the estimated background from each page.

    Args:
        pages:      list of RGB uint8 arrays (H, W, 3)
        bg:         background estimate — either a float (H, W, 3) array
                    (positional/percentile) or an int (3,) array (histogram)
        model:      "additive" or "multiplicative"
        intensity:  0.0 = no removal, 1.0 = full removal
        clip_min:   minimum output value (default 0)

    Returns:
        List of cleaned uint8 RGB arrays.
    """
    if model == "additive":
        return _remove_additive(pages, bg, intensity, clip_min)
    elif model == "multiplicative":
        return _remove_multiplicative(pages, bg, intensity)
    else:
        raise ValueError(f"Unknown model: {model!r}. Use 'additive' or 'multiplicative'.")


def _remove_additive(
    pages: list[np.ndarray],
    bg,
    intensity: float,
    clip_min: int,
) -> list[np.ndarray]:
    """output = clip(input - intensity * bg, clip_min, 255)"""
    if bg.ndim == 1:
        # Flat color: broadcast
        bg_arr = np.tile(bg.astype(np.float32), (pages[0].shape[0], pages[0].shape[1], 1))
    else:
        bg_arr = bg.astype(np.float32)

    cleaned = []
    for p in pages:
        out = np.clip(p.astype(np.float32) - intensity * bg_arr, clip_min, 255).astype(np.uint8)
        cleaned.append(out)
    return cleaned


def _remove_multiplicative(
    pages: list[np.ndarray],
    bg,
    intensity: float,
) -> list[np.ndarray]:
    """output = clip(input * (255 / bg)^intensity, 0, 255)

    The multiplicative (white-balance) model preserves dark content while
    whitening the background.
    """
    if bg.ndim == 1:
        bg_arr = np.tile(bg.astype(np.float32), (pages[0].shape[0], pages[0].shape[1], 1))
    else:
        bg_arr = bg.astype(np.float32)

    scale = np.power(255.0 / np.clip(bg_arr, 1, 255), intensity)
    cleaned = []
    for p in pages:
        out = np.clip(p.astype(np.float32) * scale, 0, 255).astype(np.uint8)
        cleaned.append(out)
    return cleaned


def crop_page(
    page: np.ndarray,
    threshold: int = 240,
) -> np.ndarray:
    """Crop whitespace from around a page.

    A pixel is considered "content" if any channel is below the threshold.
    Returns the cropped page (or the original if nothing to crop).
    """
    # A pixel is "white" (background) if ALL channels >= threshold
    is_white = (page >= threshold).all(axis=-1)  # (H, W) bool

    # Find bounding box of non-white pixels
    rows = np.any(~is_white, axis=1)
    cols = np.any(~is_white, axis=0)

    if not rows.any() or not cols.any():
        return page  # nothing to crop

    r_min, r_max = np.where(rows)[0][[0, -1]]
    c_min, c_max = np.where(cols)[0][[0, -1]]

    # Add 1-pixel padding
    r_min = max(0, r_min - 1)
    r_max = min(page.shape[0] - 1, r_max + 1)
    c_min = max(0, c_min - 1)
    c_max = min(page.shape[1] - 1, c_max + 1)

    return page[r_min:r_max + 1, c_min:c_max + 1].copy()


def crop_all_pages(
    pages: list[np.ndarray],
    threshold: int = 240,
) -> list[np.ndarray]:
    """Crop whitespace from all pages."""
    return [crop_page(p, threshold) for p in pages]
