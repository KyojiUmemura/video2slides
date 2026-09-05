#!/usr/bin/env python3
"""video2slides — 動画からスライドPDFを自動生成するツール

使用方法:
    python video2slides.py input.mp4
    python video2slides.py input.mp4 --output slides.pdf --keep-images

注意: root に video2slides.py があるため、video2slides パッケージが
シャドウされる。importlib.util で src/ 上のモジュールを直接ロードする。
"""

import importlib.util
import sys
from pathlib import Path

# root の video2slides.py が video2slides パッケージをシャドウするのを回避
_src_dir = Path(__file__).parent / "src"

# video2slides パッケージを sys.modules に登録
_pkg_init = _src_dir / "video2slides" / "__init__.py"
_pkg_spec = importlib.util.spec_from_file_location(
    "video2slides", str(_pkg_init),
)
_pkg = importlib.util.module_from_spec(_pkg_spec)
_pkg.__path__ = [str(_src_dir / "video2slides")]
sys.modules["video2slides"] = _pkg
_pkg_spec.loader.exec_module(_pkg)

# cli モジュールをロード
_cli_spec = importlib.util.spec_from_file_location(
    "video2slides.cli",
    str(_src_dir / "video2slides" / "cli.py"),
)
_cli_module = importlib.util.module_from_spec(_cli_spec)
sys.modules["video2slides.cli"] = _cli_module
_cli_spec.loader.exec_module(_cli_module)

if __name__ == "__main__":
    raise SystemExit(_cli_module.main())
