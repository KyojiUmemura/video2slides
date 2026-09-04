#!/usr/bin/env python3
"""video2slides — 動画からスライドPDFを自動生成するツール

使用方法:
    python video2slides.py input.mp4
    python video2slides.py input.mp4 --output slides.pdf --keep-images
"""

import sys
from pathlib import Path

# プロジェクトルートを sys.path に追加（pip install せずに直接実行するため）
sys.path.insert(0, str(Path(__file__).parent / "src"))

from video2slides.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
