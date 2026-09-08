"""CLI エントリーポイント。"""

from __future__ import annotations

import argparse
import logging
import statistics
import sys
from pathlib import Path

from .arguments import (
    crop_rect,
    jpeg_quality,
    nonnegative_float,
    percentile_float,
    positive_float,
    positive_int,
    unit_interval_float,
)
from .clean_pdf import clean_pdf
from .detector import detect_slides
from .pdf import generate_pdf
from .video import check_ffmpeg, extract_frames, probe_video

_VERSION = "2026-09-08"


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
        help="出力PDFファイルパス（デフォルト: 入力ファイル名.pdf）",
    )
    parser.add_argument(
        "--sample-interval",
        type=positive_float,
        metavar="FLOAT",
        default=2.0,
        help="フレーム抽出間隔（秒、0 より大、デフォルト: 2）",
    )
    parser.add_argument(
        "--settle-time",
        type=nonnegative_float,
        metavar="FLOAT",
        default=0.7,
        help="スライド切替後の安定待ち時間（秒、0 以上、デフォルト: 0.7）",
    )
    parser.add_argument(
        "--similarity-threshold",
        type=unit_interval_float,
        metavar="FLOAT",
        default=0.0005,
        help="類似度閾値 pHash distance (0.0〜1.0、デフォルト: 0.0005)",
    )
    parser.add_argument(
        "--crop",
        type=crop_rect,
        metavar="x,y,width,height",
        default=None,
        help="切り抜き（x,y >= 0, width,height > 0）",
    )
    parser.add_argument(
        "--background-color-detection",
        choices=["on", "off"],
        default="off",
        help="スライド主体フレームの検出 (デフォルト: off)",
    )
    parser.add_argument(
        "--dedup-mode",
        choices=["keep", "remove"],
        default="keep",
        help="直前の保存スライドと同一の候補: keep=残す, remove=除去 (デフォルト: keep)",
    )
    parser.add_argument(
        "--clean",
        choices=["on", "off"],
        default="off",
        help="スライドPDFの背景除去 (デフォルト: off)",
    )
    parser.add_argument(
        "--bg-pages",
        type=positive_int,
        metavar="INT",
        default=60,
        help="背景推定に使用するページ数（1 以上、デフォルト: 60）",
    )
    parser.add_argument(
        "--percentile",
        type=percentile_float,
        metavar="FLOAT",
        default=90.0,
        help="背景推定のパーセンタイル（0.0〜100.0、デフォルト: 90.0）",
    )
    parser.add_argument(
        "--intensity",
        type=unit_interval_float,
        metavar="FLOAT",
        default=1.0,
        help="背景除去強度 0.0-1.0（デフォルト: 1.0）",
    )
    parser.add_argument(
        "--image-format",
        choices=["jpg", "png"],
        default="jpg",
        help="スライド画像の形式 (デフォルト: jpg)",
    )
    parser.add_argument(
        "--jpeg-quality",
        type=jpeg_quality,
        metavar="N",
        default=95,
        help="JPEG 品質 (1〜100、デフォルト: 95)",
    )
    parser.add_argument(
        "--background",
        action="store_true",
        help="推定した背景マップを {stem}_background.png に保存",
    )
    parser.add_argument(
        "--quick-sample",
        action="store_true",
        help="元画像・背景マップ・除去後の比較シートを {stem}_sample.png に保存",
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
        "--overwrite",
        action="store_true",
        help="既存の出力ファイルを上書きする",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"video2slides {_VERSION}",
    )
    return parser


def _fmt_ts(ts: float) -> str:
    """秒を HH:MM:SS.ss にフォーマットする。"""
    hours = int(ts // 3600)
    mins = int((ts % 3600) // 60)
    secs = ts % 60
    return f"{hours:02d}:{mins:02d}:{secs:05.2f}"


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
    output_path = args.output or args.input.with_suffix(".pdf")

    # 出力先が既存の場合
    if output_path.exists():
        if args.overwrite:
            print(f"既存のファイルを上書きします: {output_path}")
        else:
            print(f"エラー: 出力先が既に存在します: {output_path}", file=sys.stderr)
            print("  --overwrite を指定するか、既存ファイルを削除してください。", file=sys.stderr)
            return 1

    crop = args.crop

    # ===== メイン処理 =====
    print(f"Analyzing video: {args.input.name}")

    # 動画メタ情報取得
    try:
        info = probe_video(args.input)
    except Exception as e:
        print(f"エラー: 動画の情報取得に失敗しました: {e}", file=sys.stderr)
        return 1

    if crop is not None:
        x, y, width, height = crop
        if x + width > info.width or y + height > info.height:
            print(
                "エラー: --crop の範囲が動画フレームを超えています"
                f" ({info.width}x{info.height}): {x},{y},{width},{height}",
                file=sys.stderr,
            )
            return 1

    print(f"Duration: {_fmt_ts(info.duration)}")
    print(f"Resolution: {info.width}x{info.height} @ {info.fps:.1f} fps")
    if crop is not None:
        print(f"Crop: {','.join(str(value) for value in crop)}")
    if args.background_color_detection == "on":
        print("Background color detection: on")
    print()

    # フレーム抽出
    print("Extracting frames...")
    frames_gen, detection_stats = extract_frames(
        args.input,
        interval=args.sample_interval,
        crop=crop,
        background_color_detection=(args.background_color_detection == "on"),
        verbose=args.verbose,
    )
    # generator を detect_slides に直接渡す（統計は detect_slides 内で更新）
    frames_iter = frames_gen

    # スライド検出（generator を消費して統計も更新される）
    debug_dir = Path("debug") if args.debug else None
    print("Detecting slides...")

    slides = detect_slides(
        frames=frames_iter,
        similarity_threshold=args.similarity_threshold,
        settle_time=args.settle_time,
        dedup_mode=args.dedup_mode,
        verbose=args.verbose,
        debug_dir=debug_dir,
    )

    # PDF 生成（generator を直接渡す、統計情報も同時に取得）
    print(f"\nGenerating PDF: {output_path}")
    total_candidates, duplicates_rejected = generate_pdf(
        slides, output_path,
        image_format=args.image_format,
        jpeg_quality=args.jpeg_quality,
    )

    # 進捗表示
    print()
    print(f"Extracted {detection_stats['total']} candidate frames")
    print(f"Candidates detected: {total_candidates}")
    print(f"Slides accepted: {total_candidates - duplicates_rejected}")
    print(f"Duplicates rejected: {duplicates_rejected}")

    # フレーム generator は generate_pdf() 内で消費済みのため、ここで統計が確定する。
    if args.background_color_detection == "on" and detection_stats["total"] > 0:
        ratios = detection_stats["ratios"]
        detected_ratios = [r for r in ratios if r >= 0.20]
        rejected_ratios = [r for r in ratios if r < 0.20]

        print("\nBackground color detection statistics:")
        print(f"  Total sampled frames: {detection_stats['total']}")
        print(f"  Detected (slide-dominant, ratio >= 0.20): {detection_stats['detected']}")
        print(f"  Rejected (non-slide-dominant, ratio < 0.20): {detection_stats['rejected']}")

        if detected_ratios:
            print("\n  DETECT frames:")
            print(f"    Count: {len(detected_ratios)}")
            print(f"    Max ratio: {max(detected_ratios):.4f}")
            print(f"    Min ratio: {min(detected_ratios):.4f}")
            print(f"    Average ratio: {statistics.mean(detected_ratios):.4f}")
            if len(detected_ratios) > 1:
                print(f"    Std dev: {statistics.stdev(detected_ratios):.4f}")

        if rejected_ratios:
            print("\n  NON-DETECT frames:")
            print(f"    Count: {len(rejected_ratios)}")
            print(f"    Max ratio: {max(rejected_ratios):.4f}")
            print(f"    Min ratio: {min(rejected_ratios):.4f}")
            print(f"    Average ratio: {statistics.mean(rejected_ratios):.4f}")
            if len(rejected_ratios) > 1:
                print(f"    Std dev: {statistics.stdev(rejected_ratios):.4f}")

    if total_candidates - duplicates_rejected == 0:
        print("エラー: スライドが検出されませんでした。", file=sys.stderr)
        return 1

    # 背景除去
    if args.clean == "on":
        # Avoid double _cleaned suffix
        stem = output_path.stem
        if stem.endswith("_cleaned"):
            cleaned_name = f"{stem}.pdf"
        else:
            cleaned_name = f"{stem}_cleaned.pdf"
        cleaned_path = output_path.parent / cleaned_name
        print(f"\nCleaning background: {cleaned_path}")
        try:
            clean_pdf(
                output_path, cleaned_path,
                bg_pages=args.bg_pages,
                percentile=args.percentile,
                intensity=args.intensity,
                image_format=args.image_format,
                jpeg_quality=args.jpeg_quality,
                save_bg_map=args.background,
                save_sample=args.quick_sample,
            )
        except Exception as e:
            print(f"エラー：背景除去に失敗しました：{e}", file=sys.stderr)
            return 1

        # Rename: backup original -> {stem}_old.pdf, then move cleaned -> {stem}.pdf
        if output_path.exists():
            backup_path = output_path.parent / f"{stem}_original.pdf"
            output_path.rename(backup_path)
            print(f"  Original backed up: {backup_path}")
        cleaned_path.rename(output_path)
        print(f"  Cleaned PDF saved: {output_path}")

    print(f"Done! {total_candidates - duplicates_rejected} slides -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
