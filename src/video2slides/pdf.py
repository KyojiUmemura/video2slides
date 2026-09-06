"""抽出したスライド画像から PDF を生成する。

メモリ効率: generator ベース。画像を一度に全部メモリに保持せず、
1ページずつディスクに書き出して PDF に埋め込む。
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path
from typing import Iterator

from PIL import Image

import img2pdf


def generate_pdf(
    slides: Iterator[tuple[float, Image.Image | Path]],
    output_path: Path,
) -> None:
    """スライド画像を時系列順に並べて PDF に出力する。

    1画像＝1ページ。ページサイズは画像のアスペクト比に合わせる。
    余白は追加しない。

    引数 slides は generator であり、画像は一度に1枚ずつ処理される。
    一時ファイルは tempfile 内で管理され、完了後に自動削除される。

    slides の要素は (timestamp, PIL.Image) または (timestamp, Path) のいずれか。
    Path  that points to an image file is loaded into memory for that page only.

    Args:
        slides: (timestamp, PIL.Image | Path) のイテレータ（時系列順）
        output_path: 出力PDFパス
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        paths: list[Path] = []

        for i, (_, src) in enumerate(slides):
            p = tmp / f"slide_{i:04d}.png"
            if isinstance(src, Path):
                # ファイルパスから直接コピー
                import shutil
                shutil.copy2(str(src), str(p))
            else:
                # PIL Image を保存
                src.save(str(p), "PNG")
            paths.append(p)

        # img2pdf で PDF 生成（全パスを一度に渡すのはディスク上のファイルのみ）
        with open(output_path, "wb") as f:
            f.write(img2pdf.convert([str(p) for p in paths]))
