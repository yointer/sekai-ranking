# Bar Chart Racer for YouTube Shorts

Turn a CSV of time-series rankings into a vertical (1080×1920) MP4 sized for YouTube Shorts. Each video lives in its own project folder with its data and optional assets.

## Prerequisites

- **Python 3.11** (recommended). `bar_chart_race==0.1.0` requires `pandas<2`, which has prebuilt wheels through Python 3.11.
- **ffmpeg** on `PATH`. macOS: `brew install ffmpeg`.

## Install

```bash
pyenv install 3.11.10            # if not already installed
pyenv local 3.11.10
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Project folder layout

Each video is a folder under `projects/`:

```
projects/
  sample/
    data.csv       # required — wide-format CSV (first column = time period)
    config.toml    # optional — title, duration, asset paths
    logo.png       # optional — overlaid in top-right corner
    audio.mp3      # optional — background music (looped/trimmed to fit)
    out.mp4        # generated output (overwritten each run)
```

### `data.csv` (CSV wide)

First column is the time period (date string or any label). Remaining columns are items; cells are numeric values.

```csv
date,Alice,Bob,Carol,Dave,Eve
2024-01,120,80,95,40,60
2024-02,140,95,100,55,75
...
```

### `config.toml`

All keys optional; CLI flags override these.

```toml
title       = "Top Creators 2024"
duration    = 20             # seconds; YouTube Shorts max is 60
n_bars      = 5
fps         = 30
cmap        = "dark12"
period_fmt  = "%Y-%m"        # strftime for datetime index, or "{x}" for string labels
bar_size    = 0.95
dpi         = 120

logo        = "logo.png"     # relative to project folder
audio       = "audio.mp3"
```

### Optional assets

- **`logo.png`** — Any PNG. Overlaid at 18% of video width in the top-right corner.
- **`audio.<ext>`** — `.mp3`, `.wav`, `.m4a`, `.aac`. Looped if shorter than the video, trimmed if longer. Original video has no audio.

## Usage

```bash
python generate.py projects/sample
```

Override config values via CLI:

```bash
python generate.py projects/sample --duration 30 --title "My Race"
python generate.py projects/sample --no-audio --no-logo
```

## Make a new project

```bash
cp -r projects/sample projects/my-video
# Edit projects/my-video/data.csv and projects/my-video/config.toml
# Drop in logo.png and/or audio.mp3 if you want them
python generate.py projects/my-video
```

The MP4 is written to `projects/my-video/out.mp4`.

## CLI flags

| Flag | Purpose |
|---|---|
| `project` (positional) | Project folder path. |
| `-o, --output` | Output filename inside the project folder. |
| `-t, --title` | Chart title. |
| `--duration` | Target video length (seconds). |
| `--n-bars` | Max bars visible at once. |
| `--fps` | Frame rate. |
| `--cmap` | bar_chart_race color palette name. |
| `--period-fmt` | strftime for dates or `{x}` for labels. |
| `--bar-size` | Bar thickness 0–1. |
| `--dpi` | With figsize 9×16 yields 1080×1920. |
| `--no-audio` | Skip audio mux even if audio file present. |
| `--no-logo` | Skip logo overlay even if logo.png present. |

## Verify output

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,duration -of default=nw=1 projects/sample/out.mp4
```

Expect `width=1080`, `height=1920`, `duration` ≈ `--duration`.
