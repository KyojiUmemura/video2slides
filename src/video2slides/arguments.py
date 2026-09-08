"""Argument parsers and range validators for the command-line interface."""

from __future__ import annotations

import argparse
import math


def finite_float(value: str) -> float:
    """Parse a finite floating-point CLI value."""
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("有限の数値を指定してください") from exc
    if not math.isfinite(parsed):
        raise argparse.ArgumentTypeError("有限の数値を指定してください")
    return parsed


def positive_float(value: str) -> float:
    parsed = finite_float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("0 より大きい値を指定してください")
    return parsed


def nonnegative_float(value: str) -> float:
    parsed = finite_float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("0 以上の値を指定してください")
    return parsed


def unit_interval_float(value: str) -> float:
    parsed = finite_float(value)
    if not 0.0 <= parsed <= 1.0:
        raise argparse.ArgumentTypeError("0.0 から 1.0 の値を指定してください")
    return parsed


def percentile_float(value: str) -> float:
    parsed = finite_float(value)
    if not 0.0 <= parsed <= 100.0:
        raise argparse.ArgumentTypeError("0.0 から 100.0 の値を指定してください")
    return parsed


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("正の整数を指定してください") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("正の整数を指定してください")
    return parsed


def jpeg_quality(value: str) -> int:
    parsed = positive_int(value)
    if parsed > 100:
        raise argparse.ArgumentTypeError("1 から 100 の整数を指定してください")
    return parsed


def crop_rect(value: str) -> tuple[int, int, int, int]:
    try:
        raw_parts = value.split(",")
        if len(raw_parts) != 4:
            raise ValueError
        x, y, width, height = (int(part.strip()) for part in raw_parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("形式は x,y,width,height です") from exc
    if x < 0 or y < 0:
        raise argparse.ArgumentTypeError("x と y は 0 以上で指定してください")
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("width と height は 0 より大きくしてください")
    return x, y, width, height
