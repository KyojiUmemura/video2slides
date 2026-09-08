"""抽出したスライド画像から PDF を生成する。

メモリ効率: generator ベース。画像を一度に全部メモリに保持せず、
1ページずつディスクに書き出して PDF に埋め込む。

sentinel パターン: slides イテレータの末尾に DetectionStats が yield される。
これは detect_slides() から渡される統計情報であり、PDF 生成後にアクセス可能。
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterable
from pathlib import Path

import img2pdf
from tqdm import tqdm

from .detector import DetectionStats, SlideCandidate


def generate_pdf(
    slides: Iterable[SlideCandidate | DetectionStats],
    output_path: Path,
    image_format: str = "png",
    jpeg_quality: int = 95,
) -> tuple[int, int]:
    """スライド画像を時系列順に並べて PDF に出力する。

    1画像＝1ページ。ページサイズは画像のアスペクト比に合わせる。
    余白は追加しない。

    引数 slides は generator であり、各画像は1枚ずつ一時ファイルに保存される。
    一時ファイルは tempfile 内で管理され、完了後に自動削除される。

    slides の末尾には DetectionStats が yield される（detect_slides() 由来）。
    これは PDF 生成後に統計情報を取得するために使用される。

    Args:
        slides: SlideCandidate のイテレータ（末尾に DetectionStats が付く）
        output_path: 出力PDFパス
        image_format: "jpg" or "png"
        jpeg_quality: JPEG 品質 (1-100)

    Returns:
        (total_candidates, duplicates_rejected)

        When no slide images are received, no PDF is written. The caller can
        use the returned counts to report the condition and choose its exit
        status.
    """
    output_path = Path(output_path)

    total_candidates = 0
    duplicates_rejected = 0

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        paths: list[Path] = []

        ext = "jpg" if image_format == "jpg" else "png"
        with tqdm(desc="Generating PDF", unit="slide", dynamic_ncols=True) as pbar:
            for item in slides:
                if isinstance(item, DetectionStats):
                    # 統計情報を抽出
                    total_candidates = item.total_candidates
                    duplicates_rejected = item.duplicates_rejected
                    continue

                # SlideCandidate を処理
                p = tmp / f"slide_{len(paths):04d}.{ext}"
                if item.file_path is not None:
                    # ファイルパスから直接コピー
                    shutil.copy2(str(item.file_path), str(p))
                elif item.image is not None:
                    # PIL Image を保存
                    if image_format == "jpg":
                        item.image.save(str(p), "JPEG", quality=jpeg_quality, optimize=True)
                    else:
                        item.image.save(str(p), "PNG")
                else:
                    raise ValueError(f"SlideCandidate at {item.timestamp} has no image or file_path")
                paths.append(p)
                pbar.update(1)

        # No accepted slides: do not invoke img2pdf or create an empty PDF.
        if not paths:
            return total_candidates, duplicates_rejected

        # img2pdf で PDF 生成（全パスを一度に渡すのはディスク上のファイルのみ）
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(img2pdf.convert([str(p) for p in paths]))

    return total_candidates, duplicates_rejected
