"""Generate a YouTube Shorts bar chart race video from a project folder.

Usage:
    python generate.py path/to/project [--flag value ...]

Project folder layout:
    project/
      data.csv         # required: wide-format CSV (first column = time period)
      config.toml      # optional: title, duration, asset paths, etc.
      icons/           # optional: <column-name>.png per item (circular icons on y-axis)
      logo.png         # optional: overlaid in top-right corner
      audio.mp3        # optional: muxed as background audio (looped/trimmed)
      out.mp4          # generated output (overwritten on each run)

CLI flags override matching values in config.toml.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

import pandas as pd

from renderer import render_bar_chart_race, load_icons


CONFIG_DEFAULTS: dict = {
    "title": None,
    "duration": 30.0,
    "n_bars": 10,
    "fps": 30,
    "period_fmt": None,
    "bar_size": 0.85,
    "dpi": 120,
    "title_size": 54,
    "value_label_size": 22,
    "period_label_size": 36,
    "name_label_size": 28,
    "icon_size_px": 220,
    "background": "white",
    "font_path": "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "hold_final_pct": 0.02,
    "logo": None,
    "audio": None,
    "data": "data.csv",
    "icons_dir": "icons",
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
    p.add_argument("--period-fmt", default=None)
    p.add_argument("--bar-size", type=float, default=None)
    p.add_argument("--dpi", type=int, default=None)
    p.add_argument("--title-size", type=int, default=None)
    p.add_argument("--background", default=None, help="Figure background color (named or #hex).")
    p.add_argument("--no-audio", action="store_true", help="Skip audio mux.")
    p.add_argument("--no-logo", action="store_true", help="Skip logo overlay.")
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
        "period_fmt": args.period_fmt,
        "bar_size": args.bar_size,
        "dpi": args.dpi,
        "title_size": args.title_size,
        "background": args.background,
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


def resolve_asset(project_dir: Path, value, candidates: tuple[str, ...] = ()) -> Path | None:
    if value:
        path = (project_dir / value) if not Path(value).is_absolute() else Path(value)
        return path if path.exists() else None
    for name in candidates:
        path = project_dir / name
        if path.exists():
            return path
    return None


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

    icons = load_icons(project / config["icons_dir"], list(df.columns), size=config["icon_size_px"])
    if icons:
        print(f"  icons: {len(icons)}/{df.shape[1]} items", file=sys.stderr)

    logo_path = None if args.no_logo else resolve_asset(project, config["logo"], ("logo.png",))
    audio_path = None if args.no_audio else resolve_asset(project, config["audio"], AUDIO_CANDIDATES)

    print(f"project: {project}", file=sys.stderr)
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "base.mp4"
        render_bar_chart_race(df, base, icons=icons, config=config)
        finalize_video(base, logo_path, audio_path, output_path, fps=config["fps"])

    print(f"wrote {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
