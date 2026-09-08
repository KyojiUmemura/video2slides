"""Tests for command-line numeric and crop validators."""

import argparse
import importlib.util
from pathlib import Path

import pytest

# Load the standalone validator module without importing the CLI's optional
# video/PDF dependencies.
_MODULE_PATH = Path(__file__).parents[1] / "src" / "video2slides" / "arguments.py"
_SPEC = importlib.util.spec_from_file_location("video2slides_arguments", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_ARGUMENTS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_ARGUMENTS)

crop_rect = _ARGUMENTS.crop_rect
jpeg_quality = _ARGUMENTS.jpeg_quality
nonnegative_float = _ARGUMENTS.nonnegative_float
percentile_float = _ARGUMENTS.percentile_float
positive_float = _ARGUMENTS.positive_float
positive_int = _ARGUMENTS.positive_int
unit_interval_float = _ARGUMENTS.unit_interval_float


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "-inf"])
def test_positive_float_rejects_invalid_values(value):
    with pytest.raises(argparse.ArgumentTypeError):
        positive_float(value)


@pytest.mark.parametrize("value", ["-1", "nan", "inf", "-inf"])
def test_nonnegative_float_rejects_invalid_values(value):
    with pytest.raises(argparse.ArgumentTypeError):
        nonnegative_float(value)


@pytest.mark.parametrize("value", ["-0.1", "1.1", "nan", "inf"])
def test_unit_interval_rejects_invalid_values(value):
    with pytest.raises(argparse.ArgumentTypeError):
        unit_interval_float(value)


@pytest.mark.parametrize("value", ["-0.1", "100.1", "nan", "inf"])
def test_percentile_rejects_invalid_values(value):
    with pytest.raises(argparse.ArgumentTypeError):
        percentile_float(value)


@pytest.mark.parametrize("value", ["0", "-1", "1.5"])
def test_positive_int_rejects_invalid_values(value):
    with pytest.raises(argparse.ArgumentTypeError):
        positive_int(value)


@pytest.mark.parametrize("value", ["0", "101", "1.5"])
def test_jpeg_quality_rejects_invalid_values(value):
    with pytest.raises(argparse.ArgumentTypeError):
        jpeg_quality(value)


@pytest.mark.parametrize(
    "value", ["1,2,3", "1,2,3,4,5", "-1,0,10,10", "0,0,0,10", "0,0,10,0"]
)
def test_crop_rejects_invalid_values(value):
    with pytest.raises(argparse.ArgumentTypeError):
        crop_rect(value)


def test_valid_boundary_values():
    assert positive_float("0.001") == 0.001
    assert nonnegative_float("0") == 0.0
    assert unit_interval_float("0") == 0.0
    assert unit_interval_float("1") == 1.0
    assert percentile_float("0") == 0.0
    assert percentile_float("100") == 100.0
    assert positive_int("1") == 1
    assert jpeg_quality("1") == 1
    assert jpeg_quality("100") == 100
    assert crop_rect("0, 0, 1920, 1080") == (0, 0, 1920, 1080)
