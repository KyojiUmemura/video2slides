"""動画からスライドPDFを生成する統合テスト。

FFmpeg でテスト用動画を生成し、video2slides で処理して
期待される数のスライドが検出されるか確認する。
"""

import subprocess
import sys
from pathlib import Path

import pytest

# src/ を import path に追加
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from video2slides.cli import main


@pytest.fixture(scope="module")
def test_video(tmp_path_factory):
    """3スライドのテスト動画（各5秒）を生成する。"""
    video_path = tmp_path_factory.mktemp("test_data") / "test_slides.mp4"

    # スライドA: 白背景 + 上部青バー
    # スライドB: 白背景 + 左側赤バー
    # スライドC: 青背景（全面単色）
    slide_files = []
    for i, (vf, color) in enumerate([
        ("drawbox=x=0:y=0:w=640:h=80:color=blue:t=fill", "white"),
        ("drawbox=x=0:y=0:w=120:h=480:color=red:t=fill", "white"),
        ("null", "blue"),
    ]):
        slide_path = tmp_path_factory.mktemp("slides") / f"slide_{i}.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c={color}:s=640x480:d=5",
            "-vf", vf if vf != "null" else "null",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(slide_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        slide_files.append(slide_path)

    concat_list = tmp_path_factory.mktemp("concat") / "list.txt"
    concat_list.write_text("\n".join(f"file '{p}'" for p in slide_files) + "\n")

    # 連結
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(video_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return video_path


def test_three_slides_detected(test_video):
    """3スライドの動画から3ページのPDFが生成される。"""
    output_pdf = test_video.parent / f"{test_video.stem}_slides.pdf"

    # 既存PDFを削除
    if output_pdf.exists():
        output_pdf.unlink()

    ret = main([
        str(test_video),
        "--output", str(output_pdf),
        "--sample-interval", "0.5",
        "--settle-time", "0.5",
        "--similarity-threshold", "0.02",
    ])

    assert ret == 0, "CLI execution failed"
    assert output_pdf.exists(), "PDF was not generated"

    # PDF のページ数を確認
    import fitz
    doc = fitz.open(str(output_pdf))
    page_count = len(doc)
    doc.close()
    assert page_count >= 3, f"Expected at least 3 pages, got {page_count}"


def test_output_not_overwritten(test_video):
    """既存の出力ファイルを上書きしない。"""
    output_pdf = test_video.parent / f"{test_video.stem}_slides.pdf"

    # 既存PDFを作成
    output_pdf.write_bytes(b"%PDF-1.4 fake content")

    ret = main([
        str(test_video),
        "--output", str(output_pdf),
        "--sample-interval", "0.5",
        "--settle-time", "0.5",
    ])

    assert ret == 1, "Expected error when output exists"
    # ファイルは変更されていない
    assert output_pdf.read_bytes() == b"%PDF-1.4 fake content"


def test_overwrite_flag(test_video):
    """--overwrite で既存ファイルを上書きできる。"""
    output_pdf = test_video.parent / f"{test_video.stem}_slides.pdf"

    # 既存PDFを作成
    output_pdf.write_bytes(b"%PDF-1.4 fake content")

    ret = main([
        str(test_video),
        "--output", str(output_pdf),
        "--sample-interval", "0.5",
        "--settle-time", "0.5",
        "--overwrite",
    ])

    assert ret == 0, "CLI execution failed with --overwrite"
    # ファイルが上書きされている（中身が異なる）
    assert output_pdf.read_bytes() != b"%PDF-1.4 fake content"


def test_generate_pdf_with_file_paths():
    """generate_pdf() が SlideCandidate からの入力に対応している。"""
    from PIL import Image

    from video2slides.detector import DetectionStats, SlideCandidate
    from video2slides.pdf import generate_pdf

    # ディスク上のテスト画像を作成
    img_a = Image.new("RGB", (100, 100), "red")
    img_b = Image.new("RGB", (100, 100), "blue")
    path_a = Path("/tmp/test_pdf_a.png")
    path_b = Path("/tmp/test_pdf_b.png")
    img_a.save(str(path_a))
    img_b.save(str(path_b))
    img_a.close()
    img_b.close()

    # SlideCandidate オブジェクトを作成
    slides: list[SlideCandidate | DetectionStats] = [
        SlideCandidate(timestamp=0.0, file_path=path_a),
        SlideCandidate(timestamp=1.0, file_path=path_b),
        DetectionStats(total_candidates=2, duplicates_rejected=0),
    ]

    output = Path("/tmp/test_pdf_output.pdf")
    total_candidates, duplicates_rejected = generate_pdf(slides, output)
    assert output.exists()
    assert output.stat().st_size > 0
    assert total_candidates == 2
    assert duplicates_rejected == 0

    # PDF のページ数を確認
    import fitz
    doc = fitz.open(str(output))
    assert len(doc) == 2, f"Expected 2 pages, got {len(doc)}"
    doc.close()

    # クリーンアップ
    path_a.unlink()
    path_b.unlink()
    output.unlink()


def test_slide_candidate_with_file_path():
    """SlideCandidate が file_path をサポートしている。"""
    from video2slides.detector import SlideCandidate

    c = SlideCandidate(
        timestamp=1.0,
        image=None,
        file_path=Path("/tmp/test.png"),
        status="SAVE",
    )
    assert c.status == "SAVE"
    assert c.file_path == Path("/tmp/test.png")
    assert c.image is None

    # image のみのケース
    from PIL import Image
    img = Image.new("RGB", (10, 10), "white")
    c2 = SlideCandidate(timestamp=2.0, image=img, file_path=None, status="SAVE")
    assert c2.image is not None
    assert c2.file_path is None
    img.close()
