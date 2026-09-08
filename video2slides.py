#!/usr/bin/env python3
"""video2slides — a tool that automatically generates slide PDFs from videos.

Usage:
    python video2slides.py input.mp4
    python video2slides.py input.mp4 --output slides.pdf

Note: The root video2slides.py shadows the video2slides package.
Load the modules directly from src/ with importlib.util.
"""

import importlib.util
import sys
from pathlib import Path

# Avoid having the root video2slides.py shadow the video2slides package
_src_dir = Path(__file__).parent / "src"

# Register the video2slides package in sys.modules
_pkg_init = _src_dir / "video2slides" / "__init__.py"
_pkg_spec = importlib.util.spec_from_file_location(
    "video2slides", str(_pkg_init),
)
_pkg = importlib.util.module_from_spec(_pkg_spec)
_pkg.__path__ = [str(_src_dir / "video2slides")]
sys.modules["video2slides"] = _pkg
_pkg_spec.loader.exec_module(_pkg)

# Load the cli module
_cli_spec = importlib.util.spec_from_file_location(
    "video2slides.cli",
    str(_src_dir / "video2slides" / "cli.py"),
)
_cli_module = importlib.util.module_from_spec(_cli_spec)
sys.modules["video2slides.cli"] = _cli_module
_cli_spec.loader.exec_module(_cli_module)

if __name__ == "__main__":
    raise SystemExit(_cli_module.main())
