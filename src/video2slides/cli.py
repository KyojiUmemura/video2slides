"""CLI エントリーポイント。"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

from . import __version__
from .clean_pdf import clean_pdf
from .detector import collect_detection_result, detect_slides
from .pdf import generate_pdf
from .video import check_ffmpeg, extract_frames, probe_video, save_image


_VERSION = "2026-09-07"


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
        type=float,
        default=2.0,
        help="フレーム抽出間隔（秒、デフォルト: 2）",
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
        default=0.0005,
        help="類似度閾値 pHash distance (0.0〜1.0、デフォルト: 0.0005)",
    )
    parser.add_argument(
        "--crop",
        type=str,
        default=None,
        help="切り抜き x,y,width,height",
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
        help="重複スライドの扱い: keep=残す, remove=全重複除去 (デフォルト: keep)",
    )
    parser.add_argument(
        "--clean",
        choices=["on", "off"],
        default="off",
        help="スライドPDFの背景除去 (デフォルト: off)",
    )
    parser.add_argument(
        "--keep-images",
        action="store_true",
        help="中間スライド画像を output/ に保存する",
    )
    parser.add_argument(
        "--bg-pages",
        type=int,
        default=60,
        help="背景推定に使用するページ数（デフォルト: 60）",
    )
    parser.add_argument(
        "--percentile",
        type=float,
        default=90.0,
        help="背景推定のパーセンタイル（デフォルト: 90.0）",
    )
    parser.add_argument(
        "--intensity",
        type=float,
        default=1.0,
        help="背景除去強度 0.0-1.0（デフォルト: 1.0）",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=72,
        help="変換DPI（デフォルト: 72）",
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
    print(f"Duration: {_fmt_ts(info.duration)}")
    print(f"Resolution: {info.width}x{info.height} @ {info.fps:.1f} fps")
    if args.crop:
        print(f"Crop: {args.crop}")
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

    # 検出統計の表示
    if args.background_color_detection == "on" and detection_stats["total"] > 0:
        import statistics
        ratios = detection_stats["ratios"]
        detected_ratios = [r for r in ratios if r >= 0.20]
        rejected_ratios = [r for r in ratios if r < 0.20]

        print("\nBackground color detection statistics:")
        print(f"  Total sampled frames: {detection_stats['total']}")
        print(f"  Detected (slide-dominant, ratio >= 0.20): {detection_stats['detected']}")
        print(f"  Rejected (non-slide-dominant, ratio < 0.20): {detection_stats['rejected']}")

        if detected_ratios:
            print(f"\n  DETECT frames:")
            print(f"    Count: {len(detected_ratios)}")
            print(f"    Max ratio: {max(detected_ratios):.4f}")
            print(f"    Min ratio: {min(detected_ratios):.4f}")
            print(f"    Average ratio: {statistics.mean(detected_ratios):.4f}")
            if len(detected_ratios) > 1:
                print(f"    Std dev: {statistics.stdev(detected_ratios):.4f}")

        if rejected_ratios:
            print(f"\n  NON-DETECT frames:")
            print(f"    Count: {len(rejected_ratios)}")
            print(f"    Max ratio: {max(rejected_ratios):.4f}")
            print(f"    Min ratio: {min(rejected_ratios):.4f}")
            print(f"    Average ratio: {statistics.mean(rejected_ratios):.4f}")
            if len(rejected_ratios) > 1:
                print(f"    Std dev: {statistics.stdev(rejected_ratios):.4f}")
    print()

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

    # generator を消費してスライドリストと統計を取得
    accepted, result = collect_detection_result(slides)

    # 進捗表示
    print()
    print(f"Extracted {detection_stats['total']} candidate frames")
    print(f"Candidates detected: {result.total_candidates}")
    print(f"Slides accepted: {len(accepted)}")
    print(f"Duplicates rejected: {result.duplicates_rejected}")

    if not accepted:
        print("エラー: スライドが検出されませんでした。", file=sys.stderr)
        return 1

    # 画像保存
    if args.keep_images:
        output_dir = args.input.parent / "output"
        output_dir.mkdir(exist_ok=True)
        print(f"\nSaving slides to {output_dir}/")
        for i, candidate in enumerate(accepted):
            ext = "png" if args.image_format == "png" else "jpg"
            save_image(
                candidate.image,
                output_dir / f"slide_{i+1:04d}.{ext}",
                fmt=args.image_format,
                quality=args.jpeg_quality,
            )

    # PDF 生成（generator を直接渡す）
    print(f"\nGenerating PDF: {output_path}")
    slides_for_pdf = ((c.timestamp, c.image) for c in accepted)
    generate_pdf(slides_for_pdf, output_path, image_format=args.image_format, jpeg_quality=args.jpeg_quality)

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

    print(f"Done! {len(accepted)} slides -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
