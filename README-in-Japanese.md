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

## インストール（他環境でも利用可能）

このプロジェクトは `pip` でインストール可能です。

### pip install でのインストール

```bash
# リポジトリから直接インストール
pip install git+https://github.com/KyojiUmemura/video2slides.git

# またはローカルからインストール
cd SlideVideo
pip install .
```

インストール後、`video2slides` コマンドが利用可能になります：

```bash
video2slides lecture.mp4
```

### pip install --editable（開発者向け）

開発時にソースコードを直接反映したい場合：

```bash
pip install -e .
```

### 開発用チェック

開発用依存関係をインストールします。

```bash
pip install -e ".[dev]"
```

テスト、リント、型チェックは次のコマンドで実行できます。

```bash
pytest
ruff check src tests video2slides.py
mypy
```

### 依存パッケージ

| パッケージ | 用途 |
|-----------|------|
| `opencv-python` | 画像処理、フレーム抽出 |
| `imagehash` | pHash による画像類似度判定 |
| `Pillow` | 画像処理 |
| `tqdm` | 進捗表示 |
| `img2pdf` | PDF 生成 |
| `PyMuPDF` | PDF 読み込み・書き出し |
| `numpy` | 数値演算 |

## 基本的な使い方

```bash
python video2slides.py input.mp4
```

`input.pdf` が生成されます。

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

Generating PDF: input.pdf
Done! 57 slides -> input.pdf
```

## CLI オプション

```
python video2slides.py INPUT [OPTIONS]

 positional arguments:
   INPUT                 入力動画ファイルパス

 options:
   --output, -o OUTPUT              出力PDFファイルパス（デフォルト: INPUT.pdf）
   --sample-interval FLOAT          フレーム抽出間隔（秒、0 より大、デフォルト: 2）
   --settle-time FLOAT              スライド切替後の安定待ち時間（秒、0 以上、デフォルト: 0.7）
   --similarity-threshold FLOAT     類似度閾値 0.0〜1.0（デフォルト: 0.0005）
   --crop x,y,width,height          画像の切り抜き（x,y >= 0, width,height > 0）
   --background-color-detection on|off  スライド主体フレームの検出（デフォルト: off）
   --dedup-mode keep|remove         直前の保存スライドと同一の候補の扱い（デフォルト: keep）
   --clean on|off                   スライドPDFの背景除去（デフォルト: off）
   --bg-pages INT                   背景推定に使用するページ数（1 以上、デフォルト: 60）
   --percentile FLOAT               背景推定のパーセンタイル（0.0〜100.0、デフォルト: 90.0）
   --intensity FLOAT                背景除去強度 0.0-1.0（デフォルト: 1.0）
   --image-format jpg|png           画像形式（デフォルト: jpg）
   --jpeg-quality N                 JPEG品質 1〜100（デフォルト: 95）
   --background                     推定した背景マップを {stem}_background.png に保存
   --quick-sample                   元画像・背景マップ・除去後の比較シートを {stem}_sample.png に保存
   --verbose, -v                    デバッグ情報を出力
   --debug                          verbose + debug/ に判定候補を保存
   --overwrite                      既存の出力ファイルを上書き
   --version                        バージョン表示（YYYY-MM-DD 形式、README.md に固定）
```

### 数値オプションの有効範囲

| オプション | 有効範囲 |
|---|---|
| `--sample-interval` | 0 より大きい有限値 |
| `--settle-time` | 0 以上の有限値 |
| `--similarity-threshold` | 0.0〜1.0（両端を含む） |
| `--bg-pages` | 1 以上の整数 |
| `--percentile` | 0.0〜100.0（両端を含む） |
| `--intensity` | 0.0〜1.0（両端を含む） |
| `--jpeg-quality` | 1〜100（両端を含む整数） |
| `--crop` | `x,y >= 0`、`width,height > 0`、かつ動画フレーム内 |

浮動小数点オプションに `NaN` や無限大は指定できません。範囲外の引数は処理開始前にエラーになります。

### 使用例

```bash
# 基本
python video2slides.py lecture.mp4

# カスタムオプション
python video2slides.py lecture.mp4 \
    --output slides.pdf \
    --sample-interval 2 \
    --settle-time 0.7

# PNG 形式で保存
python video2slides.py lecture.mp4 \
    --image-format png

# 短い動画（高速サンプリング）
python video2slides.py short.mp4 \
    --sample-interval 0.2 \
    --settle-time 0.3

# スライド主体フレームのみ抽出
python video2slides.py lecture.mp4 \
    --background-color-detection on

# 背景除去付き
python video2slides.py lecture.mp4 \
    --clean on
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
 ↓
背景除去（`--clean on`）
```

1. **フレーム抽出**: FFmpeg で動画から一定間隔でフレームを取得
2. **類似度判定**: `imagehash` の pHash で画像間の視覚的類似度を計算
3. **安定待ち**: スライド切替検出後、一定時間待ってから代表フレームを保存
4. **重複除去**: 連続する同一フレームは常に1枚にまとめる。`--dedup-mode remove` では、スライド切替後の候補が直前に保存したスライドと同一の場合にも保存しない
5. **PDF 生成**: 画像を時系列順に並べて余白なしの PDF に出力

### 重複モード（`--dedup-mode`）

- `keep`（デフォルト）: スライド切替後の安定した候補を保存する
- `remove`: その候補が直前に保存したスライドと同一なら保存しない

この判定は過去の全スライドを検索するものではありません。そのため、`A → B → A` のように時間を置いて再登場した A は別ページとして残ります。

### スライド主体判定（`--background-color-detection on`）

画像内のほぼ同一色の領域が 20% 以上を占めるフレームのみをスライドとして扱います。
プレゼン内容以外のフレーム（黒画面、タイトルカード等）を除外できます。

## `--clean on` の詳細

`--clean on` を指定すると、生成されたスライド PDF に対して背景除去（透かし・色付き背景の除去）を自動で実行します。

### 処理パイプライン

```
スライド PDF
 ↓
全ページを内部画像として読み込み（72 PPI）
 ↓
全ページ共通の背景バイアスを推定（p90）
 ↓
乗算モデルで各ページを補正（ホワイトバランス）
 ↓
背景除去後の PDF を保存
```

### 背景推定

PDF の先頭から最大 60 ページを文書順にサンプリングし、各ピクセル位置の値ヒストグラムから `--percentile` 番目の値（デフォルト p90）を計算します。このサンプルで共通して明るい成分が背景バイアスとして推定されます。

- **`--bg-pages`** — 背景推定に使用する、PDF 先頭からのページ数（デフォルト: `60`）。値を大きくするほど処理時間とメモリ使用量が増えます。
- **`--percentile`** — 背景推定のパーセンタイル（デフォルト: `90.0`）。
  - `90`（デフォルト）: 標準的な透かし除去
  - `95`: より保守的な除去（背景が残る方向）
  - `85`: より積極的な除去（背景が強く消える）

### 背景除去（乗算モデル / ホワイトバランス補正）

推定した背景バイアスを使って各ページを補正します：

```
補正係数 = (255 / 背景)^intensity
出力 = clip(入力 × 補正係数, 0, 255)
```

背景が明るい領域は白に近づき、背景が濃い領域は相対的に明るくなります。暗いコンテンツ（文字、線）は乗算モデルにより保持されます。

- **`--intensity`** — 背景除去の強度（デフォルト: `1.0`）。
  - `1.0`: 背景を完全に白飛ばし
  - `0.5`: 背景の半分だけ白飛ばし
  - `0.0`: 除去しない（デバッグ用）

### 出力ファイル

`--clean on` 指定時、以下のファイルが生成されます：

| ファイル | 説明 | 条件 |
|---------|------|------|
| `<stem>.pdf` | 背景除去後の PDF（最終結果） | 常時生成 |
| `<stem>_original.pdf` | 除去前の PDF（バックアップ） | `--clean on` 時、`<stem>.pdf` が既存の場合 |
| `<stem>_background.png` | 推定した背景マップ | `--background` 指定時 |
| `<stem>_sample.png` | 元画像・背景マップ・除去後の比較シート | `--quick-sample` 指定時 |

`<stem>` は入力ファイル名から拡張子を除いた部分です。`<stem>.pdf` が既に存在する場合、背景除去前に `<stem>_original.pdf` へバックアップし、除去後の PDF を `<stem>.pdf` として上書きします。

### 処理解像度

背景除去で PDF ページを内部画像に変換する際の解像度は、72 pixels per inch（PPI）で固定です。利用者が指定するオプションはありません。

### 推奨パラメータ

| 用途 | --bg-pages | --percentile | --intensity |
|------|-----------|-------------|-------------|
| 標準（背景除去） | `60` | `90` | `1.0` |
| 強い塗りつぶし | `60` | `90` | `1.0` |
| 写真混じりドキュメント | `60` | `90` | `1.0` |

### トラブルシューティング

#### 背景が完全に除去されない

- `--intensity` が `1.0` になっているか確認してください。
- `--percentile` を下げてみてください（例: `--percentile 85`）。

#### 原本の文字まで消えてしまう

- `--intensity` を `0.5` などに下げてみてください。
- `--percentile` を上げてみてください（例: `--percentile 95`）。

#### 処理が遅い / メモリ不足

- `--bg-pages` を減らしてみてください（例: `--bg-pages 30`）。
- `--clean off` で使用するか、`--sample-interval` を大きくしてスライド数を減らすことを検討してください。

## 推奨パラメータ

| パラメータ | 推奨値 | 説明 |
|---|---|---|
| `--sample-interval` | `2` | 標準的な講義動画（デフォルト） |
| `--sample-interval` | `1` | 切り替えが速い動画 |
| `--settle-time` | `0.7` | 標準的なフェード切替 |
| `--similarity-threshold` | `0.0005` | 標準的な閾値（デフォルト） |
| `--background-color-detection` | `off` | スライド主体判定（デフォルト） |
| `--clean` | `off` | 背景除去（デフォルト） |

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

### 背景除去後、背景が完全に除去されない

- 背景が濃い場合、乗算モデルでは完全除去が難しい場合があります。
- 背景が明るい透かしの場合は効果的です。

### 原本の文字まで消えてしまう

- 背景と文字の境界が不明確な場合に発生します。
- 背景除去の影響が小さい場合は、`--clean off` で使用してください。

### 処理が遅い / メモリ不足

- `--clean on` は PDF の全ページを画像として展開するため、メモリ使用量が増加します。
- ページ数が多い場合は、`--sample-interval` を大きくしてスライド数を減らすことを検討してください。

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
