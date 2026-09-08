"""Unit tests for image similarity detection.

pHash is insensitive to the same layout with different content and is also
not very sensitive to different layouts (distance < 0.02). These tests use
that empirically observed behavior.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from PIL import Image, ImageDraw

from video2slides.similarity import are_similar, phash_distance


def _slide_layout_top_bar(
    bar_color: tuple[int, ...],
    size: tuple[int, int] = (640, 480),
) -> Image.Image:
    """Slide layout with a bar at the top."""
    img = Image.new("RGB", size, (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, size[0], 80], fill=bar_color)
    return img


def _slide_layout_left_bar(
    bar_color: tuple[int, ...],
    size: tuple[int, int] = (640, 480),
) -> Image.Image:
    """Slide layout with a bar on the left."""
    img = Image.new("RGB", size, (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 120, size[1]], fill=bar_color)
    return img


def _slide_layout_full_image(
    color: tuple[int, ...],
    size: tuple[int, int] = (640, 480),
) -> Image.Image:
    """Solid-color slide."""
    return Image.new("RGB", size, color)


def _random_noise(size: tuple[int, int] = (640, 480)) -> Image.Image:
    """Random-noise image."""
    import random
    random.seed(42)
    img = Image.new("RGB", size)
    for y in range(size[1]):
        for x in range(size[0]):
            img.putpixel((x, y), (
                random.randint(0, 255),
                random.randint(0, 255),
                random.randint(0, 255),
            ))
    return img


def _slightly_brighter(img: Image.Image) -> Image.Image:
    """Increase brightness slightly."""
    return img.point(lambda p: min(255, p + 15))


class TestPhashDistance:
    """Tests for pHash distance."""

    def test_identical_image_distance_is_zero(self):
        """Identical images have a distance of 0."""
        img = _slide_layout_top_bar((30, 60, 150))
        assert phash_distance(img, img) == 0.0

    def test_same_layout_different_color_same_hash(self):
        """The same layout in different colors has distance=0."""
        img_a = _slide_layout_top_bar((30, 60, 150))
        img_b = _slide_layout_top_bar((180, 30, 30))
        assert phash_distance(img_a, img_b) == 0.0

    def test_different_layouts_have_small_distance(self):
        """Different layouts also have a small distance (a pHash property):
        0.0001 < dist < 0.02
        """
        img_a = _slide_layout_top_bar((30, 60, 150))
        img_b = _slide_layout_left_bar((30, 60, 150))
        dist = phash_distance(img_a, img_b)
        assert 0.0001 < dist < 0.02

    def test_full_color_vs_layout(self):
        """Solid color versus a structured layout: dist > 0."""
        img_a = _slide_layout_full_image((100, 100, 100))
        img_b = _slide_layout_top_bar((30, 60, 150))
        dist = phash_distance(img_a, img_b)
        assert dist > 0

    def test_noise_vs_slide(self):
        """Noise versus slide: 0.001 < dist < 0.02."""
        img_a = _random_noise()
        img_b = _slide_layout_top_bar((30, 60, 150))
        dist = phash_distance(img_a, img_b)
        assert 0.001 < dist < 0.02


class TestAreSimilar:
    """Tests for are_similar using the default threshold of 0.0005."""

    def test_same_image_is_similar(self):
        """Identical images are similar."""
        img = _slide_layout_top_bar((30, 60, 150))
        assert are_similar(img, img) is True

    def test_same_layout_is_similar(self):
        """The same layout remains similar with different colors."""
        img_a = _slide_layout_top_bar((30, 60, 150))
        img_b = _slide_layout_top_bar((180, 30, 30))
        assert are_similar(img_a, img_b) is True

    def test_brightness_change_is_similar(self):
        """Slight brightness changes are similar."""
        img_a = _slide_layout_top_bar((30, 60, 150))
        img_b = _slightly_brighter(img_a)
        assert are_similar(img_a, img_b) is True

    def test_different_layout_may_be_similar(self):
        """Different layouts may be similar according to pHash:
        With threshold 0.02, same_layout (0.0) is similar, while
        different_layout (0.0001-0.02) depends on the threshold.
        """
        img_a = _slide_layout_top_bar((30, 60, 150))
        img_b = _slide_layout_left_bar((30, 60, 150))
        dist = phash_distance(img_a, img_b)
        # Similar when below the threshold
        if dist < 0.02:
            assert are_similar(img_a, img_b, threshold=0.02) is True
        # Not similar with a stricter threshold
        assert are_similar(img_a, img_b, threshold=dist / 2) is False

    def test_noise_not_similar_with_strict_threshold(self):
        """Noise is not similar at a strict threshold."""
        img_a = _random_noise()
        img_b = _slide_layout_top_bar((30, 60, 150))
        # Noise has a relatively large distance (~0.002)
        # Not similar at a strict threshold
        assert are_similar(img_a, img_b, threshold=0.001) is False
        # May be similar with a loose threshold
        assert are_similar(img_a, img_b, threshold=0.05) is True

    def test_threshold_adjustment(self):
        """Similarity can be controlled by the threshold."""
        img_a = _slide_layout_top_bar((30, 60, 150))
        img_b = _slightly_brighter(img_a)
        dist = phash_distance(img_a, img_b)
        # Similar when the value is below the threshold
        assert are_similar(img_a, img_b, threshold=dist + 0.001) is True
        # Not similar when the value is above the threshold
        assert are_similar(img_a, img_b, threshold=dist - 0.001) is False
