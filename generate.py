"""Generate a YouTube Shorts bar chart race video from a project folder.

Usage:
    python generate.py path/to/project [--flag value ...]

Project folder layout:
    project/
      data.csv      # required: wide-format CSV (first column = time period)
      config.toml   # optional: title, duration, asset paths, etc.
      logo.png      # optional: overlaid in top-right corner
      audio.mp3     # optional: muxed as background audio (looped/trimmed)
      out.mp4       # generated output (overwritten on each run)

CLI flags override matching values in config.toml.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import tomllib
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning, module=r"bar_chart_race\..*")

import pandas as pd

try:
    import bar_chart_race as bcr
except ImportError:
    sys.exit("bar_chart_race is not installed. Run: pip install -r requirements.txt")


CONFIG_DEFAULTS: dict = {
    "title": None,
    "duration": 30.0,
    "n_bars": 10,
    "fps": 30,
    "cmap": "dark12",
    "period_fmt": None,
    "bar_size": 0.95,
    "dpi": 120,
    "logo": None,
    "audio": None,
    "data": "data.csv",
    "output": "out.mp4",
}

AUDIO_CANDIDATES = ("audio.mp3", "audio.wav", "audio.m4a", "audio.aac")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Render a project folder as a 1080x1920 YouTube Shorts bar-chart-race MP4.",
    )
    p.add_argument("project", type=Path, help="Project folder (must contain data.csv).")
    p.add_argument("-o", "--output", default=None, help="Output filename (relative to project).")
    p.add_argument("-t", "--title", default=None)
    p.add_argument("--duration", type=float, default=None, help="Target video length (seconds).")
    p.add_argument("--n-bars", type=int, default=None)
    p.add_argument("--fps", type=int, default=None)
    p.add_argument("--cmap", default=None)
    p.add_argument("--period-fmt", default=None)
    p.add_argument("--bar-size", type=float, default=None)
    p.add_argument("--dpi", type=int, default=None)
    p.add_argument("--no-audio", action="store_true", help="Skip audio mux even if audio file present.")
    p.add_argument("--no-logo", action="store_true", help="Skip logo overlay even if logo.png present.")
    return p.parse_args()


def load_config(project_dir: Path) -> dict:
    config = dict(CONFIG_DEFAULTS)
    config_path = project_dir / "config.toml"
    if config_path.exists():
        with config_path.open("rb") as f:
            try:
                user_config = tomllib.load(f)
            except tomllib.TOMLDecodeError as e:
                sys.exit(f"Invalid {config_path}: {e}")
        unknown = set(user_config) - set(CONFIG_DEFAULTS)
        if unknown:
            print(f"WARNING: unknown config keys ignored: {sorted(unknown)}", file=sys.stderr)
        config.update({k: v for k, v in user_config.items() if k in CONFIG_DEFAULTS})
    return config


def merge_cli_overrides(config: dict, args: argparse.Namespace) -> dict:
    overrides = {
        "output": args.output,
        "title": args.title,
        "duration": args.duration,
        "n_bars": args.n_bars,
        "fps": args.fps,
        "cmap": args.cmap,
        "period_fmt": args.period_fmt,
        "bar_size": args.bar_size,
        "dpi": args.dpi,
    }
    for k, v in overrides.items():
        if v is not None:
            config[k] = v
    return config


def load_dataframe(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        sys.exit(f"data file not found: {csv_path}")
    try:
        df = pd.read_csv(csv_path, index_col=0)
    except Exception as e:
        sys.exit(f"Failed to read {csv_path}: {e}")

    try:
        df.index = pd.to_datetime(df.index)
    except (ValueError, TypeError):
        pass

    if len(df) < 2:
        sys.exit(f"{csv_path} needs at least 2 rows.")

    non_numeric = df.select_dtypes(exclude="number").columns.tolist()
    if non_numeric:
        sys.exit(f"Non-numeric columns in {csv_path}: {non_numeric}")

    df = df.dropna(axis=1, how="all").fillna(0)
    if df.shape[1] == 0:
        sys.exit(f"No numeric columns left in {csv_path}.")
    return df


def compute_timing(n_periods: int, duration_s: float, fps: int) -> tuple[int, int]:
    transitions = max(n_periods - 1, 1)
    total_frames = max(int(round(fps * duration_s)), transitions)
    steps_per_period = max(1, round(total_frames / transitions))
    period_length_ms = max(1, round(1000 * steps_per_period / fps))
    return steps_per_period, period_length_ms


def resolve_asset(project_dir: Path, value, candidates: tuple[str, ...] = ()) -> Path | None:
    """Resolve an asset path: explicit value wins, else try candidates, else None."""
    if value:
        path = (project_dir / value) if not Path(value).is_absolute() else Path(value)
        return path if path.exists() else None
    for name in candidates:
        path = project_dir / name
        if path.exists():
            return path
    return None


def render_chart(df: pd.DataFrame, output: Path, config: dict) -> None:
    steps_per_period, period_length_ms = compute_timing(len(df), config["duration"], config["fps"])
    print(
        f"  rendering: {len(df)} periods, {df.shape[1]} items, "
        f"steps_per_period={steps_per_period}, period_length={period_length_ms}ms, fps={config['fps']}",
        file=sys.stderr,
    )
    bcr.bar_chart_race(
        df=df,
        filename=str(output),
        n_bars=config["n_bars"],
        steps_per_period=steps_per_period,
        period_length=period_length_ms,
        figsize=(9, 16),
        dpi=config["dpi"],
        title=config["title"],
        cmap=config["cmap"],
        bar_size=config["bar_size"],
        period_fmt=config["period_fmt"],
        bar_label_size=12,
        tick_label_size=12,
        title_size=18,
        period_label={"x": 0.98, "y": 0.15, "ha": "right", "size": 28},
        bar_kwargs={"alpha": 0.85},
        filter_column_colors=True,
    )


def run_ffmpeg(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"ffmpeg failed:\n{result.stderr.strip()}")


def finalize_video(
    video_in: Path,
    logo: Path | None,
    audio: Path | None,
    video_out: Path,
    fps: int,
) -> None:
    """Single ffmpeg pass: force 1080x1920, overlay logo, mux audio."""
    inputs: list[str] = ["-i", str(video_in)]
    # Normalize source to exactly 1080x1920 (scale-up if needed, then center-crop).
    filters = [
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,setsar=1[bg]"
    ]
    last_video = "[bg]"

    if logo:
        inputs.extend(["-i", str(logo)])
        print(f"  overlay: {logo.name}", file=sys.stderr)
        filters.append("[1:v]scale=iw*0.18:-1[lg]")
        filters.append(f"{last_video}[lg]overlay=W-w-40:40:format=auto[v]")
        last_video = "[v]"

    audio_index = 1 + (1 if logo else 0)
    if audio:
        print(f"  audio: {audio.name}", file=sys.stderr)
        inputs.extend(["-stream_loop", "-1", "-i", str(audio)])

    cmd: list[str] = ["ffmpeg", "-y", "-loglevel", "error", *inputs,
                      "-filter_complex", ";".join(filters),
                      "-map", last_video]
    if audio:
        cmd.extend(["-map", f"{audio_index}:a", "-c:a", "aac", "-b:a", "192k", "-shortest"])
    cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps), str(video_out)])
    run_ffmpeg(cmd)


def main() -> None:
    args = parse_args()
    project = args.project.resolve()
    if not project.is_dir():
        sys.exit(f"Project folder not found: {project}")
    if shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg not found on PATH. Install it (macOS: `brew install ffmpeg`).")

    config = merge_cli_overrides(load_config(project), args)
    if config["duration"] > 60:
        print(f"WARNING: duration {config['duration']}s exceeds YouTube Shorts 60s limit.", file=sys.stderr)

    df = load_dataframe(project / config["data"])
    output_path = project / config["output"]

    logo_path = None if args.no_logo else resolve_asset(project, config["logo"], ("logo.png",))
    audio_path = None if args.no_audio else resolve_asset(project, config["audio"], AUDIO_CANDIDATES)

    print(f"project: {project}", file=sys.stderr)
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "base.mp4"
        render_chart(df, base, config)
        finalize_video(base, logo_path, audio_path, output_path, fps=config["fps"])

    print(f"wrote {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
