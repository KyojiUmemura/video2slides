# video2slides

A tool that automatically extracts slides shown in recorded lectures and presentations and exports them as a PDF.

## Purpose

The tool extracts each slide screen from a video in chronological order and generates a PDF with one slide per page. Audio is not included, allowing users to advance through the slides at their own pace in a PDF viewer.

## Setup on macOS

### 1. Install FFmpeg

FFmpeg is required for video processing. Install it with Homebrew:

```bash
brew install ffmpeg
```

### 2. Set up the Python environment

Python 3.11 or later is required.

```bash
# Create a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Installation (also available on other platforms)

This project can be installed with `pip`.

### Install with pip

```bash
# Install directly from the repository
pip install git+https://github.com/KyojiUmemura/video2slides.git

# Or install from a local checkout
cd SlideVideo
pip install .
```

After installation, the `video2slides` command is available:

```bash
video2slides lecture.mp4
```

### Editable installation (for developers)

To apply source-code changes immediately during development:

```bash
pip install -e .
```

### Development checks

Install the development dependencies:

```bash
pip install -e ".[dev]"
```

Run tests, linting, and type checking with:

```bash
pytest
ruff check src tests video2slides.py
mypy
```

### Dependencies

| Package | Purpose |
|---|---|
| `opencv-python` | Image processing and frame extraction |
| `imagehash` | Image similarity detection using pHash |
| `Pillow` | Image processing |
| `tqdm` | Progress display |
| `img2pdf` | PDF generation |
| `PyMuPDF` | PDF reading and writing |
| `numpy` | Numerical computation |

## Basic usage

```bash
python video2slides.py input.mp4
```

This generates `input.pdf`.

Progress is displayed while the command runs:

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

## CLI options

```text
python video2slides.py INPUT [OPTIONS]

 positional arguments:
   INPUT                 Input video file path

 options:
   --output, -o OUTPUT              Output PDF path (default: INPUT.pdf)
   --sample-interval FLOAT          Frame sampling interval in seconds (greater than 0; default: 2)
   --settle-time FLOAT              Stabilization wait after a slide change in seconds (0 or greater; default: 0.7)
   --similarity-threshold FLOAT     Similarity threshold from 0.0 to 1.0 (default: 0.0005)
   --crop x,y,width,height          Crop the image (x,y >= 0 and width,height > 0)
   --background-color-detection on|off  Detect slide-dominant frames (default: off)
   --dedup-mode keep|remove         How to handle a candidate identical to the last saved slide (default: keep)
   --clean on|off                   Remove the slide PDF background (default: off)
   --bg-pages INT                   Pages used for background estimation (1 or greater; default: 60)
   --percentile FLOAT               Background-estimation percentile from 0.0 to 100.0 (default: 90.0)
   --intensity FLOAT                Background-removal intensity from 0.0 to 1.0 (default: 1.0)
   --image-format jpg|png           Image format (default: jpg)
   --jpeg-quality N                 JPEG quality from 1 to 100 (default: 95)
   --background                     Save the estimated background map as {stem}_background.png
   --quick-sample                   Save an original/background/cleaned comparison sheet as {stem}_sample.png
   --verbose, -v                    Print debug information
   --debug                          Include verbose output and save detection candidates under debug/
   --overwrite                      Overwrite an existing output file
   --version                        Print the version in YYYY-MM-DD format, fixed in README.md
```

### Valid ranges for numeric options

| Option | Valid range |
|---|---|
| `--sample-interval` | A finite value greater than 0 |
| `--settle-time` | A finite value greater than or equal to 0 |
| `--similarity-threshold` | 0.0 to 1.0, inclusive |
| `--bg-pages` | An integer greater than or equal to 1 |
| `--percentile` | 0.0 to 100.0, inclusive |
| `--intensity` | 0.0 to 1.0, inclusive |
| `--jpeg-quality` | An integer from 1 to 100, inclusive |
| `--crop` | `x,y >= 0`, `width,height > 0`, and within the video frame |

Floating-point options do not accept `NaN` or infinity. Out-of-range arguments cause an error before processing begins.

### Examples

```bash
# Basic usage
python video2slides.py lecture.mp4

# Custom options
python video2slides.py lecture.mp4 \
    --output slides.pdf \
    --sample-interval 2 \
    --settle-time 0.7

# Save images as PNG
python video2slides.py lecture.mp4 \
    --image-format png

# Short video (frequent sampling)
python video2slides.py short.mp4 \
    --sample-interval 0.2 \
    --settle-time 0.3

# Extract only slide-dominant frames
python video2slides.py lecture.mp4 \
    --background-color-detection on

# Remove the background
python video2slides.py lecture.mp4 \
    --clean on
```

## How slide detection works

Processing proceeds through the following stages:

```text
Video
 ↓
Extract candidate frames at regular intervals
 ↓
Detect slide changes using pHash similarity
 ↓
Select a stable frame after waiting for settle-time
 ↓
Remove similar and duplicate slides
 ↓
Slide images
 ↓
Generate PDF
 ↓
Remove background (`--clean on`)
```

1. **Frame extraction**: FFmpeg obtains frames from the video at regular intervals.
2. **Similarity detection**: `imagehash` pHash measures the visual similarity between images.
3. **Stabilization wait**: After detecting a slide change, the tool waits for the specified period before saving a representative frame.
4. **Duplicate removal**: Consecutive identical frames are always consolidated into one. With `--dedup-mode remove`, a post-transition candidate is also omitted when it is identical to the most recently saved slide.
5. **PDF generation**: Images are arranged chronologically and written to a PDF without margins.

### Duplicate modes (`--dedup-mode`)

- `keep` (default): Save a stable candidate after a slide transition.
- `remove`: Do not save the candidate if it is identical to the most recently saved slide.

This check does not search every previously saved slide. Therefore, when slide A reappears after some time, as in `A → B → A`, the second A remains as a separate page.

### Slide-dominant frame detection (`--background-color-detection on`)

Only frames in which an almost uniform color occupies at least 20% of the image are treated as slides. This can exclude frames that are not presentation content, such as black screens and title cards.

## Details of `--clean on`

When `--clean on` is specified, background removal is automatically applied to the generated slide PDF to remove watermarks or colored backgrounds.

### Processing pipeline

```text
Slide PDF
 ↓
Read every page as an internal image at 72 PPI
 ↓
Estimate a shared background bias using p90
 ↓
Correct each page with a multiplicative white-balance model
 ↓
Save the cleaned PDF
```

### Background estimation

Up to the first 60 pages of the PDF are sampled in document order. At each pixel position, the value at the percentile selected by `--percentile` (p90 by default) is calculated. Bright components shared across this sample are estimated as the background bias.

- **`--bg-pages`** — Number of pages sampled from the beginning of the PDF for background estimation (default: `60`). Increasing this value increases processing time and memory usage.
- **`--percentile`** — Percentile used for background estimation (default: `90.0`).
  - `90` (default): Standard watermark removal
  - `95`: More conservative removal, leaving more background
  - `85`: More aggressive removal, erasing more background

### Background removal (multiplicative model / white-balance correction)

Each page is corrected using the estimated background bias:

```text
correction factor = (255 / background)^intensity
output = clip(input × correction factor, 0, 255)
```

Bright background areas approach white, while darker background areas become relatively brighter. The multiplicative model preserves dark content such as text and lines.

- **`--intensity`** — Background-removal intensity (default: `1.0`).
  - `1.0`: Fully whiten the background
  - `0.5`: Apply half-strength whitening
  - `0.0`: Do not remove the background (for debugging)

### Output files

With `--clean on`, the following files are generated:

| File | Description | Condition |
|---|---|---|
| `<stem>.pdf` | Cleaned PDF (final result) | Always generated |
| `<stem>_original.pdf` | PDF before background removal (backup) | When `<stem>.pdf` exists during `--clean on` processing |
| `<stem>_background.png` | Estimated background map | When `--background` is specified |
| `<stem>_sample.png` | Comparison sheet containing the original image, background map, and cleaned result | When `--quick-sample` is specified |

`<stem>` is the input filename without its extension. If `<stem>.pdf` already exists, it is backed up as `<stem>_original.pdf` before the cleaned result replaces `<stem>.pdf`.

### Processing resolution

PDF pages are converted to internal images at a fixed resolution of 72 pixels per inch (PPI) during background removal. There is no user-configurable resolution option.

### Recommended parameters

| Use case | `--bg-pages` | `--percentile` | `--intensity` |
|---|---:|---:|---:|
| Standard background removal | `60` | `90` | `1.0` |
| Strong fill | `60` | `90` | `1.0` |
| Documents containing photographs | `60` | `90` | `1.0` |

### Troubleshooting

#### The background is not completely removed

- Confirm that `--intensity` is set to `1.0`.
- Try lowering `--percentile`, for example: `--percentile 85`.

#### Text from the original is also removed

- Try lowering `--intensity`, for example to `0.5`.
- Try raising `--percentile`, for example: `--percentile 95`.

#### Processing is slow or runs out of memory

- Try reducing `--bg-pages`, for example: `--bg-pages 30`.
- Consider using `--clean off`, or increase `--sample-interval` to reduce the number of slides.

## Recommended parameters

| Parameter | Recommended value | Description |
|---|---:|---|
| `--sample-interval` | `2` | Standard lecture videos (default) |
| `--sample-interval` | `1` | Videos with rapid transitions |
| `--settle-time` | `0.7` | Standard fade transitions |
| `--similarity-threshold` | `0.0005` | Standard threshold (default) |
| `--background-color-detection` | `off` | Slide-dominant detection (default) |
| `--clean` | `off` | Background removal (default) |

### Parameter adjustment guidelines

- **Slides are missed** → Decrease `--sample-interval`, for example to `0.2`.
- **Transition frames remain** → Increase `--settle-time`, for example to `1.0`.
- **Noise produces too many false detections** → Increase `--similarity-threshold`, for example to `0.01`.
- **Different slides are treated as identical** → Decrease `--similarity-threshold`, for example to `0.0002`.

## Troubleshooting

### `ffmpeg: command not found`

FFmpeg is not installed.

```bash
brew install ffmpeg
```

### `No video stream found`

The input is not a video file, or its video codec is unsupported.

### Slides are not extracted correctly

1. Run with `--verbose` and inspect the detection log.
2. Adjust `--sample-interval`.
3. Adjust `--similarity-threshold`.
4. Run with `--debug` and inspect the candidate images saved under `debug/`.

### The background is not completely removed after cleaning

- The multiplicative model may not completely remove a dark background.
- It is effective for light watermarks and backgrounds.

### Text from the original is also removed

- This can occur when the boundary between the background and text is unclear.
- If background removal provides little benefit, use `--clean off`.

### Processing is slow or runs out of memory

- `--clean on` expands every PDF page into an image, increasing memory usage.
- For PDFs with many pages, consider increasing `--sample-interval` to reduce the number of slides.

### Dependency installation fails

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## Development

```bash
# Run tests
python -m pytest tests/ -v
```

## License

MIT
