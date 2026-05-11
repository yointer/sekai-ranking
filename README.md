# Bar Chart Racer for YouTube Shorts

Turn a CSV of time-series rankings into a vertical (1080×1920) MP4 sized for YouTube Shorts. Each video lives in its own project folder with its data, optional config, and optional assets (icons, logo, audio).

## Prerequisites

- **Python 3.11+** (needs the stdlib `tomllib`).
- **ffmpeg** on `PATH`. macOS: `brew install ffmpeg`.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Project folder layout

Each video is a folder under `projects/`:

```
projects/
  sample/
    data.csv         # required — wide CSV (first column = time period)
    config.toml      # optional — title, duration, asset paths, sizes
    icons/           # optional — <column-name>.png per item (circular y-axis icons)
      Alice.png
      Bob.png
      ...
    logo.png         # optional — overlaid in top-right corner of the video
    audio.mp3        # optional — background music (looped/trimmed to fit)
    out.mp4          # generated output (overwritten each run)
```

### `data.csv` (wide format)

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
title              = "Top Creators 2024"
duration           = 20            # seconds; YouTube Shorts max is 60
n_bars             = 5             # how many bars to show simultaneously
fps                = 30
period_fmt         = "%Y-%m"       # strftime for datetime index, or "{x}" for label strings
bar_size           = 0.85          # bar thickness 0–1
dpi                = 120
title_size         = 54            # chart title font size
value_label_size   = 22            # in-bar value labels
period_label_size  = 36            # bottom-right date label
icon_size_px       = 220           # source size for circular icons
background         = "white"       # figure background (any matplotlib color or #hex)

logo               = "logo.png"
audio              = "audio.mp3"
icons_dir          = "icons"
```

### Optional assets

- **`icons/<column>.png`** — One image per CSV column. Cropped to a circle and drawn where the y-axis label would normally be. Columns without a matching file show no icon. Accepted: `.png`, `.jpg`, `.jpeg`, `.webp`.
- **`logo.png`** — Overlaid at 18 % of video width in the top-right corner.
- **`audio.<ext>`** — `.mp3`, `.wav`, `.m4a`, `.aac`. Looped if shorter than the video, trimmed if longer. Source video has no audio.

## Styling

The rendering is custom (pure matplotlib + ffmpeg, no `bar_chart_race`) so we can hit specific visual requirements:

- No chart-area background fill (only the figure background shows through).
- Bar value labels rendered **inside** each bar in bold white.
- Y-axis labels replaced with circular icons; falls back to nothing when an icon is missing.
- All sizes (title, in-bar labels, period label, icons) tunable via config.

## Usage

```bash
python generate.py projects/sample
```

Override config values via CLI:

```bash
python generate.py projects/sample --duration 30 --title "My Race"
python generate.py projects/sample --no-audio --no-logo
python generate.py projects/sample --title-size 72 --background "#0a0a0a"
```

## Make a new project

```bash
cp -r projects/sample projects/my-video
# 1. replace projects/my-video/data.csv with your numbers
# 2. edit projects/my-video/config.toml (title, duration)
# 3. drop one PNG per column into projects/my-video/icons/ (filename = column name)
# 4. optional: drop logo.png and audio.mp3 in projects/my-video/
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
| `--period-fmt` | strftime for dates or `{x}` for labels. |
| `--bar-size` | Bar thickness 0–1. |
| `--dpi` | DPI; figsize 9×16 yields 1080×1920. |
| `--title-size` | Title font size. |
| `--background` | Figure background color (name or `#hex`). |
| `--no-audio` | Skip audio mux. |
| `--no-logo` | Skip logo overlay. |

## Verify output

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,duration -of default=nw=1 projects/sample/out.mp4
```

Expect `width=1080`, `height=1920`, `duration` ≈ `--duration`.
