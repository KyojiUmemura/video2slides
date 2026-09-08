"""Per-pixel (positional) histogram background detection.

The background is NOT assumed to be a flat color — it may be an image
(paper texture, grain, watermark pattern). So the histogram is built
per pixel position: across all pages, the value that stays stable at a
position (median of the per-pixel value histogram) is background, while
values that vary page-to-page are content.
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------------------
# Per-pixel positional background
# ---------------------------------------------------------------------------

def positional_background(pages, percentile: float = 90.0, tol: int = 16,
                          smooth_sigma: float = 0.0):
    """Detect the background as a full-resolution image.

    At each pixel position, take the percentile of the value histogram across
    pages. For dark content on light background (manga line art, text), a high
    percentile (~90) is the right statistic: it only needs a small upper tail
    of pages to be blank at each position, while the median needs a majority.
    percentile=100 is the per-pixel max.

    Args:
      pages         list of RGB uint8 arrays (same size)
      percentile    0-100; which per-pixel histogram quantile is the background
      tol           per-channel tolerance for "this page matches background here"
      smooth_sigma  optional Gaussian smoothing on the background map

    Returns:
      bg        float array (H, W, 3), the background map
      conf      float array (H, W), fraction of pages matching bg at each position
      coverage  per-page fraction of pixels classified as background
    """
    stack = np.stack(pages).astype(np.float32)  # (N, H, W, 3)
    bg = np.quantile(stack, percentile / 100.0, axis=0)

    if smooth_sigma > 0:
        # Convert to PIL Image for Gaussian blur
        bg_u8 = np.clip(bg * 255, 0, 255).astype(np.uint8)
        bg_pil = Image.fromarray(bg_u8)
        # Apply Gaussian blur (radius ≈ sigma * 2)
        radius = max(1, int(smooth_sigma * 2))
        bg_pil = bg_pil.filter(ImageFilter.GaussianBlur(radius=radius))
        # Convert back to float array
        bg = np.array(bg_pil).astype(np.float32) / 255.0

    # Confidence: at each position, what fraction of pages sit within tol of bg
    diff = np.abs(stack - bg).max(axis=3)          # (N, H, W)
    conf = (diff <= tol).mean(axis=0)              # (H, W)

    # Per-page coverage
    coverage = list((diff <= tol).mean(axis=(1, 2)))

    return bg, conf, coverage


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------

def _font(size=16):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def visualize(pages, page_idx, bg, conf, mask, whitened, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    page = pages[page_idx]
    h, w = page.shape[:2]

    bg_u8 = np.clip(bg, 0, 255).astype(np.uint8)
    Image.fromarray(bg_u8).save(output_dir / "bg_map.png")
    Image.fromarray(np.stack([conf * 255] * 3, -1).astype(np.uint8)).save(output_dir / "confidence.png")
    mask_img = np.where(mask, 255, 0).astype(np.uint8)
    mask_img = np.stack([mask_img] * 3, -1)
    Image.fromarray(mask_img).save(output_dir / "background_mask.png")
    Image.fromarray(whitened).save(output_dir / "whitened.png")

    panels = [Image.fromarray(page), Image.fromarray(bg_u8),
              Image.fromarray(mask_img), Image.fromarray(whitened)]
    labels = [f"Original (p{page_idx + 1})", "Background Map (per-pixel)",
              "Page Mask", "Whitened Result"]
    strip = Image.new("RGB", (w * 4 + 30, h + 30), "white")
    font = _font()
    for i, im in enumerate(panels):
        x = i * (w + 10)
        strip.paste(im, (x, 0))
        ImageDraw.Draw(strip).text((x + w // 2, h + 15), labels[i],
                                   fill="black", font=font, anchor="mm")
    strip.save(output_dir / "comparison.png")

    print("  bg_map.png / confidence.png / comparison.png / background_mask.png / whitened.png")
