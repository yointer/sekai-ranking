# Bar Chart Racer for YouTube Shorts

Turn a CSV of time-series rankings into a vertical (1080×1920) MP4 sized for YouTube Shorts.

## Prerequisites

- **Python 3.11** (recommended). `bar_chart_race==0.1.0` requires `pandas<2`, which has prebuilt wheels through Python 3.11.
- **ffmpeg** on `PATH`. macOS: `brew install ffmpeg`.

## Install

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Input format (CSV wide)

- First column: time period (date string or any label). Dates like `2024-01` are auto-parsed.
- Remaining columns: one per item being ranked. All numeric.

Example (`examples/sample.csv`):

```csv
date,Alice,Bob,Carol,Dave,Eve
2024-01,120,80,95,40,60
2024-02,140,95,100,55,75
...
```

## Usage

```bash
python generate.py -i examples/sample.csv -o out.mp4 --title "Sample Race" --duration 20
```

### Flags

| Flag | Default | Purpose |
|---|---|---|
| `-i, --input` | required | Input CSV path. |
| `-o, --output` | `out.mp4` | Output MP4 path. |
| `-t, --title` | none | Chart title. |
| `--duration` | `30` | Target video length (seconds). Shorts cap is 60. |
| `--n-bars` | `10` | Max bars visible. |
| `--fps` | `30` | Frame rate. |
| `--cmap` | `dark12` | Color palette name. |
| `--period-fmt` | auto | `strftime` for dates (e.g. `'%Y-%m'`) or `'{x}'` for string labels. |
| `--bar-size` | `0.95` | Bar thickness 0–1. |
| `--dpi` | `120` | With figsize 9×16 yields 1080×1920. |

## Verify output

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,duration -of default=nw=1 out.mp4
```

Expect `width=1080`, `height=1920`, `duration` ≈ `--duration`.
