"""Generate a bar-chart-racer MP4 sized for YouTube Shorts (1080x1920) from a CSV."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import pandas as pd

try:
    import bar_chart_race as bcr
except ImportError:
    sys.exit(
        "bar_chart_race is not installed. Run: pip install -r requirements.txt"
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Render a CSV of time-series rankings as a YouTube Shorts MP4 "
        "(1080x1920, vertical) bar chart race.",
    )
    p.add_argument("-i", "--input", required=True, type=Path, help="Input CSV (wide format).")
    p.add_argument("-o", "--output", default=Path("out.mp4"), type=Path, help="Output MP4 path.")
    p.add_argument("-t", "--title", default=None, help="Chart title.")
    p.add_argument("--duration", type=float, default=30.0, help="Target video length in seconds.")
    p.add_argument("--n-bars", type=int, default=10, help="Max bars visible at once.")
    p.add_argument("--fps", type=int, default=30, help="Frame rate.")
    p.add_argument("--cmap", default="dark12", help="bar_chart_race color palette name.")
    p.add_argument(
        "--period-fmt",
        default=None,
        help="strftime for datetime index (e.g. '%%Y-%%m') or '{x}' for string labels.",
    )
    p.add_argument("--bar-size", type=float, default=0.95, help="Bar thickness (0-1).")
    p.add_argument("--dpi", type=int, default=120, help="DPI; with figsize 9x16 yields 1080x1920.")
    return p.parse_args()


def load_dataframe(path: Path) -> pd.DataFrame:
    if not path.exists():
        sys.exit(f"Input file not found: {path}")
    try:
        df = pd.read_csv(path, index_col=0)
    except Exception as e:
        sys.exit(f"Failed to read CSV {path}: {e}")

    try:
        df.index = pd.to_datetime(df.index)
    except (ValueError, TypeError):
        pass

    if len(df) < 2:
        sys.exit("CSV needs at least 2 rows (time periods).")

    non_numeric = df.select_dtypes(exclude="number").columns.tolist()
    if non_numeric:
        sys.exit(
            f"Non-numeric value columns found: {non_numeric}. "
            "All columns except the first (index) must be numeric."
        )

    df = df.dropna(axis=1, how="all").fillna(0)
    if df.shape[1] == 0:
        sys.exit("No usable numeric columns after dropping all-NaN columns.")

    return df


def compute_timing(n_periods: int, duration_s: float, fps: int) -> tuple[int, int]:
    """Return (steps_per_period, period_length_ms) such that the video lasts ~duration_s."""
    transitions = max(n_periods - 1, 1)
    total_frames = max(int(round(fps * duration_s)), transitions)
    steps_per_period = max(1, round(total_frames / transitions))
    period_length_ms = max(1, round(1000 * steps_per_period / fps))
    return steps_per_period, period_length_ms


def main() -> None:
    args = parse_args()

    if shutil.which("ffmpeg") is None:
        sys.exit(
            "ffmpeg not found on PATH. Install it (macOS: `brew install ffmpeg`) "
            "and re-run."
        )

    df = load_dataframe(args.input)

    if args.duration > 60:
        print(
            f"WARNING: --duration={args.duration}s exceeds YouTube Shorts 60s limit.",
            file=sys.stderr,
        )

    steps_per_period, period_length_ms = compute_timing(len(df), args.duration, args.fps)

    args.output.parent.mkdir(parents=True, exist_ok=True)

    print(
        f"Rendering {len(df)} periods, {df.shape[1]} items -> {args.output} "
        f"(steps_per_period={steps_per_period}, period_length={period_length_ms}ms, "
        f"fps={args.fps})",
        file=sys.stderr,
    )

    try:
        bcr.bar_chart_race(
            df=df,
            filename=str(args.output),
            n_bars=args.n_bars,
            steps_per_period=steps_per_period,
            period_length=period_length_ms,
            figsize=(9, 16),
            dpi=args.dpi,
            title=args.title,
            cmap=args.cmap,
            bar_size=args.bar_size,
            period_fmt=args.period_fmt,
            bar_label_size=12,
            tick_label_size=12,
            title_size=18,
            period_label={"x": 0.98, "y": 0.15, "ha": "right", "size": 28},
            bar_kwargs={"alpha": 0.85},
            filter_column_colors=True,
        )
    except Exception as e:
        sys.exit(f"Rendering failed: {e}")

    print(f"Wrote {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
