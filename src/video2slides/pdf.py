"""抽出したスライド画像から PDF を生成する。"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

import img2pdf
from PIL import Image


def generate_pdf(
    slides: list[tuple[float, Image.Image]],
    output_path: Path,
) -> None:
    """スライド画像を時系列順に並べて PDF に出力する。

    1画像＝1ページ。ページサイズは画像のアスペクト比に合わせる。
    余白は追加しない。

    Args:
        slides: [(timestamp, PIL.Image), ...] 時系列順
        output_path: 出力PDFパス
    """
    # 一時ファイルに画像を保存
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        paths: list[Path] = []

        for i, (_, img) in enumerate(slides):
            p = tmp / f"slide_{i:04d}.png"
            img.save(str(p), "PNG")
            paths.append(p)

        # img2pdf で PDF 生成
        with open(output_path, "wb") as f:
            f.write(img2pdf.convert([str(p) for p in paths]))
