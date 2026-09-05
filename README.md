# video2slides

講義・プレゼンテーションを録画した動画から、表示されているスライドを自動的に抽出し、PDF に出力するツールです。

## 目的

動画の各スライド画面を時系列順に抽出し、1ページに1スライドの PDF を生成します。音声は含めず、PDF ビューアで自由にページを進められるようにします。

## macOS でのセットアップ

### 1. FFmpeg のインストール

動画処理に FFmpeg が必要です。Homebrew でインストールします。

```bash
brew install ffmpeg
```

### 2. Python 環境の構築

Python 3.11 以上が必要です。

```bash
# 仮想環境を作成（推奨）
python3 -m venv .venv
source .venv/bin/activate

# 依存パッケージをインストール
pip install -r requirements.txt
```

## 基本的な使い方

```bash
python video2slides.py input.mp4
```

`input_slides.pdf` が生成されます。

実行中は次のように進捗が表示されます。

```text
Analyzing video: input.mp4
Duration: 01:52:34
Resolution: 1920x1080 @ 30.0 fps

Extracting frames...
Extracting frames from input.mp4: 100%|██████████| 1234/1234 [00:42<00:00, 29.3frame/s]

Detecting slides...

Extracted 123 candidate frames
Candidates detected: 83
Slides accepted: 57
Duplicates rejected: 26

Generating PDF: input_slides.pdf
Done! 57 slides -> input_slides.pdf
```

### 出力ディレクトリに画像も保存する場合

```bash
python video2slides.py input.mp4 --keep-images
```

`output/` ディレクトリに `slide_0001.jpg` などの画像が保存されます。

## CLI オプション

```
python video2slides.py INPUT [OPTIONS]

 positional arguments:
   INPUT                 入力動画ファイルパス

 options:
   --output, -o OUTPUT              出力PDFファイルパス（デフォルト: INPUT_slides.pdf）
   --sample-interval FLOAT          フレーム抽出間隔（秒、デフォルト: 10）
   --settle-time FLOAT              スライド切替後の安定待ち時間（秒、デフォルト: 0.7）
   --similarity-threshold FLOAT     類似度閾値 0.0〜1.0（デフォルト: 0.0005）
   --crop x,y,width,height          画像の切り抜き
   --background-color-detection on|off  スライド主体フレームの検出（デフォルト: on）
   --dedup-mode keep|remove         重複スライドの扱い（デフォルト: keep）
   --keep-images                    中間画像を保存
   --image-format jpg|png           画像形式（デフォルト: jpg）
   --jpeg-quality N                 JPEG品質 1〜100（デフォルト: 95）
   --verbose, -v                    デバッグ情報を出力
   --debug                          verbose + debug/ に判定候補を保存
   --overwrite                      既存の出力ファイルを上書き
   --version                        バージョン表示
```

### 使用例

```bash
# 基本
python video2slides.py lecture.mp4

# カスタムオプション
python video2slides.py lecture.mp4 \
    --output slides.pdf \
    --sample-interval 2 \
    --settle-time 0.7 \
    --keep-images

# PNG 形式で保存
python video2slides.py lecture.mp4 \
    --image-format png \
    --keep-images

# 短い動画（高速サンプリング）
python video2slides.py short.mp4 \
    --sample-interval 0.2 \
    --settle-time 0.3

# スライド主体フレームのみ抽出
python video2slides.py lecture.mp4 \
    --background-color-detection on
```

## スライド検出の考え方

処理は以下の段階で行われます。

```
動画
 ↓
候補フレームの抽出（一定間隔）
 ↓
スライド変更の検出（pHash 類似度）
 ↓
画面が安定したフレームを選択（settle-time 待ち）
 ↓
類似・重複スライドの除去
 ↓
スライド画像
 ↓
PDF 生成
```

1. **フレーム抽出**: FFmpeg で動画から一定間隔でフレームを取得
2. **類似度判定**: `imagehash` の pHash で画像間の視覚的類似度を計算
3. **安定待ち**: スライド切替検出後、一定時間待ってから代表フレームを保存
4. **重複除去**: 連続する同一スライドを除去（オプションで全重複も除去可能）
5. **PDF 生成**: 画像を時系列順に並べて余白なしの PDF に出力

### スライド主体判定（`--background-color-detection on`）

画像内のほぼ同一色の領域が 20% 以上を占めるフレームのみをスライドとして扱います。
プレゼン内容以外のフレーム（黒画面、タイトルカード等）を除外できます。

## 推奨パラメータ

| パラメータ | 推奨値 | 説明 |
|---|---|---|
| `--sample-interval` | `10` | 標準的な講義動画（デフォルト） |
| `--sample-interval` | `1` | 切り替えが速い動画 |
| `--settle-time` | `0.7` | 標準的なフェード切替 |
| `--similarity-threshold` | `0.0005` | 標準的な閾値（デフォルト） |
| `--background-color-detection` | `on` | スライド主体判定（デフォルト） |

### パラメータの調整目安

- **スライドが見落とされる** → `--sample-interval` を小さく（例: `0.2`）
- **切替途中の画像が残る** → `--settle-time` を大きく（例: `1.0`）
- **ノイズで偽検出が多い** → `--similarity-threshold` を大きく（例: `0.01`）
- **本来違うスライドが同一と判定される** → `--similarity-threshold` を小さく（例: `0.0002`）

## トラブルシューティング

### `ffmpeg: command not found`

FFmpeg がインストールされていません。

```bash
brew install ffmpeg
```

### `No video stream found`

入力ファイルが動画でない、または動画コーデックが未対応です。

### スライドが正しく抽出されない

1. `--verbose` を付けて実行し、検出ログを確認
2. `--sample-interval` を調整
3. `--similarity-threshold` を調整
4. `--debug` で `debug/` ディレクトリに判定候補画像が保存されるので確認

### 依存パッケージのインストールに失敗

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## 開発

```bash
# テスト実行
python -m pytest tests/ -v
```

## ライセンス

MIT
