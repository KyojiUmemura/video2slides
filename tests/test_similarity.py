"""画像類似度判定のユニットテスト。

pHash は「同じレイアウト・異なる内容」には不感で、
「異なるレイアウト」にも敏感ではない（距離 < 0.02）。
実測に基づき、この特性でテストする。
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
    """上部にバーがあるスライドレイアウト。"""
    img = Image.new("RGB", size, (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, size[0], 80], fill=bar_color)
    return img


def _slide_layout_left_bar(
    bar_color: tuple[int, ...],
    size: tuple[int, int] = (640, 480),
) -> Image.Image:
    """左側にバーがあるスライドレイアウト。"""
    img = Image.new("RGB", size, (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 120, size[1]], fill=bar_color)
    return img


def _slide_layout_full_image(
    color: tuple[int, ...],
    size: tuple[int, int] = (640, 480),
) -> Image.Image:
    """全面単色のスライド。"""
    return Image.new("RGB", size, color)


def _random_noise(size: tuple[int, int] = (640, 480)) -> Image.Image:
    """ランダムノイズ画像。"""
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
    """明るさを少し上げる。"""
    return img.point(lambda p: min(255, p + 15))


class TestPhashDistance:
    """pHash distance のテスト。"""

    def test_identical_image_distance_is_zero(self):
        """同一画像の distance は 0。"""
        img = _slide_layout_top_bar((30, 60, 150))
        assert phash_distance(img, img) == 0.0

    def test_same_layout_different_color_same_hash(self):
        """同じレイアウト・色違いは distance=0。"""
        img_a = _slide_layout_top_bar((30, 60, 150))
        img_b = _slide_layout_top_bar((180, 30, 30))
        assert phash_distance(img_a, img_b) == 0.0

    def test_different_layouts_have_small_distance(self):
        """異なるレイアウトも distance は小さい（pHash の特性）:
        0.0001 < dist < 0.02
        """
        img_a = _slide_layout_top_bar((30, 60, 150))
        img_b = _slide_layout_left_bar((30, 60, 150))
        dist = phash_distance(img_a, img_b)
        assert 0.0001 < dist < 0.02

    def test_full_color_vs_layout(self):
        """全面単色 vs レイアウト付き: dist > 0"""
        img_a = _slide_layout_full_image((100, 100, 100))
        img_b = _slide_layout_top_bar((30, 60, 150))
        dist = phash_distance(img_a, img_b)
        assert dist > 0

    def test_noise_vs_slide(self):
        """ノイズ vs スライド: 0.001 < dist < 0.02"""
        img_a = _random_noise()
        img_b = _slide_layout_top_bar((30, 60, 150))
        dist = phash_distance(img_a, img_b)
        assert 0.001 < dist < 0.02


class TestAreSimilar:
    """are_similar のテスト。デフォルト閾値 0.0005 で動作確認。"""

    def test_same_image_is_similar(self):
        """同一画像は類似。"""
        img = _slide_layout_top_bar((30, 60, 150))
        assert are_similar(img, img) is True

    def test_same_layout_is_similar(self):
        """同じレイアウトは色違いでも類似。"""
        img_a = _slide_layout_top_bar((30, 60, 150))
        img_b = _slide_layout_top_bar((180, 30, 30))
        assert are_similar(img_a, img_b) is True

    def test_brightness_change_is_similar(self):
        """明るさの微妙な変化は類似。"""
        img_a = _slide_layout_top_bar((30, 60, 150))
        img_b = _slightly_brighter(img_a)
        assert are_similar(img_a, img_b) is True

    def test_different_layout_may_be_similar(self):
        """異なるレイアウトでも pHash によっては類似になる:
        閾値 0.02 では same_layout (0.0) は類似、
        different_layout (0.0001-0.02) は閾値次第。
        """
        img_a = _slide_layout_top_bar((30, 60, 150))
        img_b = _slide_layout_left_bar((30, 60, 150))
        dist = phash_distance(img_a, img_b)
        # 閾値より下なら similar
        if dist < 0.02:
            assert are_similar(img_a, img_b, threshold=0.02) is True
        # 閾値を厳しくすれば not similar
        assert are_similar(img_a, img_b, threshold=dist / 2) is False

    def test_noise_not_similar_with_strict_threshold(self):
        """ノイズは厳しめの閾値では類似しない。"""
        img_a = _random_noise()
        img_b = _slide_layout_top_bar((30, 60, 150))
        # ノイズは distance が大きめ（~0.002）
        # 厳しい閾値では非類似
        assert are_similar(img_a, img_b, threshold=0.001) is False
        # 緩い閾値なら類似になる可能性
        assert are_similar(img_a, img_b, threshold=0.05) is True

    def test_threshold_adjustment(self):
        """閾値で制御可能。"""
        img_a = _slide_layout_top_bar((30, 60, 150))
        img_b = _slightly_brighter(img_a)
        dist = phash_distance(img_a, img_b)
        # 閾値より小さい値なら類似
        assert are_similar(img_a, img_b, threshold=dist + 0.001) is True
        # 閾値より大きい値なら非類似
        assert are_similar(img_a, img_b, threshold=dist - 0.001) is False
