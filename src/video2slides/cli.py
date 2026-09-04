"""CLI エントリーポイント。"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

from . import __version__
from .detector import detect_slides
from .pdf import generate_pdf
from .video import check_ffmpeg, extract_frames, probe_video, save_image


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="video2slides",
        description="動画からスライドPDFを自動生成するツール",
    )
    parser.add_argument(
        "input",
        type=Path,
        help="入力動画ファイルパス",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="出力PDFファイルパス（デフォルト: 入力ファイル名_slides.pdf）",
    )
    parser.add_argument(
        "--sample-interval",
        type=float,
        default=5.0,
        help="フレーム抽出間隔（秒、デフォルト: 5）",
    )
    parser.add_argument(
        "--settle-time",
        type=float,
        default=0.7,
        help="スライド切替後の安定待ち時間（秒、デフォルト: 0.7）",
    )
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.15,
        help="類似度閾値 pHash distance (0.0〜1.0、デフォルト: 0.15)",
    )
    parser.add_argument(
        "--crop",
        type=str,
        default=None,
        help="切り抜き x,y,width,height",
    )
    parser.add_argument(
        "--dedup-mode",
        choices=["keep", "remove"],
        default="keep",
        help="重複スライドの扱い: keep=残す, remove=全重複除去 (デフォルト: keep)",
    )
    parser.add_argument(
        "--keep-images",
        action="store_true",
        help="中間スライド画像を output/ に保存する",
    )
    parser.add_argument(
        "--image-format",
        choices=["jpg", "png"],
        default="jpg",
        help="スライド画像の形式 (デフォルト: jpg)",
    )
    parser.add_argument(
        "--jpeg-quality",
        type=int,
        default=95,
        help="JPEG 品質 (1〜100、デフォルト: 95)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="デバッグ情報を出力する",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="--verbose を含み、debug/ に判定候補画像を保存する",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"video2slides {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # ロギング設定
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    # 入力ファイル確認
    if not args.input.exists():
        print(f"エラー: 入力ファイルが見つかりません: {args.input}", file=sys.stderr)
        return 1

    # FFmpeg 確認
    if not check_ffmpeg():
        print(
            "エラー: ffmpeg / ffprobe が見つかりません。\n"
            "Homebrew を使っている場合: brew install ffmpeg",
            file=sys.stderr,
        )
        return 1

    # 出力パス決定
    output_path = args.output or args.input.with_stem(
        args.input.stem + "_slides"
    ).with_suffix(".pdf")

    # 出力先が既存の場合
    if output_path.exists():
        print(f"エラー: 出力先が既に存在します: {output_path}", file=sys.stderr)
        print("  --output で別のパスを指定するか、既存ファイルを削除してください。", file=sys.stderr)
        return 1

    # 切り抜きパラメータ
    crop = None
    if args.crop:
        try:
            parts = args.crop.split(",")
            if len(parts) != 4:
                raise ValueError
            crop = tuple(int(p.strip()) for p in parts)
        except ValueError:
            print("エラー: --crop の形式は x,y,width,height です。", file=sys.stderr)
            return 1

    # ===== メイン処理 =====
    print(f"Analyzing video: {args.input.name}")

    # 動画メタ情報取得
    try:
        info = probe_video(args.input)
    except Exception as e:
        print(f"エラー: 動画の情報取得に失敗しました: {e}", file=sys.stderr)
        return 1

    duration_h = int(info.duration // 3600)
    duration_m = int((info.duration % 3600) // 60)
    duration_s = info.duration % 60
    print(f"Duration: {duration_h:02d}:{duration_m:02d}:{duration_s:05.2f}")
    print(f"Resolution: {info.width}x{info.height} @ {info.fps:.1f} fps")
    print()

    # フレーム抽出
    print("Extracting frames...")
    frames = extract_frames(args.input, interval=args.sample_interval)
    print(f"Extracted {len(frames)} candidate frames")
    print()

    # スライド検出
    debug_dir = Path("debug") if args.debug else None
    print("Detecting slides...")

    from tqdm import tqdm

    accepted: list[tuple[float, object]] = []
    result = detect_slides(
        frames=frames,
        similarity_threshold=args.similarity_threshold,
        settle_time=args.settle_time,
        dedup_mode=args.dedup_mode,
        verbose=args.verbose,
        debug_dir=debug_dir,
    )

    # 進捗表示
    print()
    print(f"Candidates detected: {result.total_candidates}")
    print(f"Slides accepted: {len(result.accepted)}")
    print(f"Duplicates rejected: {result.duplicates_rejected}")

    if not result.accepted:
        print("エラー: スライドが検出されませんでした。", file=sys.stderr)
        return 1

    # 画像保存
    if args.keep_images:
        output_dir = args.input.parent / "output"
        output_dir.mkdir(exist_ok=True)
        print(f"\nSaving slides to {output_dir}/")
        for i, candidate in enumerate(result.accepted):
            ext = "png" if args.image_format == "png" else "jpg"
            save_image(
                candidate.image,
                output_dir / f"slide_{i+1:04d}.{ext}",
                fmt=args.image_format,
                quality=args.jpeg_quality,
            )

    # PDF 生成
    print(f"\nGenerating PDF: {output_path}")
    slides_for_pdf = [(c.timestamp, c.image) for c in result.accepted]
    generate_pdf(slides_for_pdf, output_path)

    print(f"Done! {len(result.accepted)} slides → {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
