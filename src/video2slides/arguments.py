"""Argument parsers and range validators for the command-line interface."""

from __future__ import annotations

import argparse
import math


def finite_float(value: str) -> float:
    """Parse a finite floating-point CLI value."""
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Please specify a finite number") from exc
    if not math.isfinite(parsed):
        raise argparse.ArgumentTypeError("Please specify a finite number")
    return parsed


def positive_float(value: str) -> float:
    parsed = finite_float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("Please specify a value greater than 0")
    return parsed


def nonnegative_float(value: str) -> float:
    parsed = finite_float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("Please specify a value greater than or equal to 0")
    return parsed


def unit_interval_float(value: str) -> float:
    parsed = finite_float(value)
    if not 0.0 <= parsed <= 1.0:
        raise argparse.ArgumentTypeError("Please specify a value from 0.0 to 1.0")
    return parsed


def percentile_float(value: str) -> float:
    parsed = finite_float(value)
    if not 0.0 <= parsed <= 100.0:
        raise argparse.ArgumentTypeError("Please specify a value from 0.0 to 100.0")
    return parsed


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Please specify a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("Please specify a positive integer")
    return parsed


def jpeg_quality(value: str) -> int:
    parsed = positive_int(value)
    if parsed > 100:
        raise argparse.ArgumentTypeError("Please specify an integer from 1 to 100")
    return parsed


def crop_rect(value: str) -> tuple[int, int, int, int]:
    try:
        raw_parts = value.split(",")
        if len(raw_parts) != 4:
            raise ValueError
        x, y, width, height = (int(part.strip()) for part in raw_parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("The format is x,y,width,height") from exc
    if x < 0 or y < 0:
        raise argparse.ArgumentTypeError("x and y must be greater than or equal to 0")
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("width and height must be greater than 0")
    return x, y, width, height
