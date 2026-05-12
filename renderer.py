"""Custom matplotlib bar chart race renderer.

Replaces bar_chart_race with full styling control:
- No fill on the chart area (transparent axes).
- Bar value labels rendered inside each bar in white.
- Y-axis labels replaced with circular icon images when provided.
- Configurable title sizing.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import matplotlib.patheffects as path_effects
from matplotlib.animation import FFMpegWriter, FuncAnimation
from matplotlib.font_manager import FontProperties
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
from matplotlib.transforms import blended_transform_factory
from PIL import Image, ImageDraw

DARK_PALETTE: list[str] = [
    "#E63946", "#F77F00", "#FCBF49", "#90BE6D", "#43AA8B",
    "#577590", "#9D4EDD", "#F72585", "#FF6B35", "#06AED5",
    "#7B2CBF", "#FB8500",
]

ICON_EXTS: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".webp")


def _make_circular(img: Image.Image, size: int) -> Image.Image:
    img = img.convert("RGBA").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
    img.putalpha(mask)
    return img


def load_icons(icons_dir: Path, columns: list[str], size: int = 220) -> dict[str, np.ndarray]:
    """Return {column_name: RGBA array} for each column that has a matching icon file."""
    icons: dict[str, np.ndarray] = {}
    if not icons_dir.is_dir():
        return icons
    for col in columns:
        for ext in ICON_EXTS:
            path = icons_dir / f"{col}{ext}"
            if path.exists():
                icons[col] = np.array(_make_circular(Image.open(path), size))
                break
    return icons


def _format_value(v: float) -> str:
    if v >= 1_000_000_000:
        return f"{v / 1_000_000_000:.1f}B"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if v >= 10_000:
        return f"{v / 1_000:.1f}K"
    return f"{v:,.0f}"


def _format_period(idx_lo, idx_hi, alpha: float, fmt: str | None) -> str:
    if isinstance(idx_lo, pd.Timestamp) and isinstance(idx_hi, pd.Timestamp):
        interp = idx_lo + (idx_hi - idx_lo) * alpha
        return interp.strftime(fmt or "%Y-%m")
    label = idx_lo if alpha < 0.5 else idx_hi
    if fmt and "{x}" in fmt:
        return fmt.replace("{x}", str(label))
    return str(label)


def render_bar_chart_race(
    df: pd.DataFrame,
    output_path: Path,
    *,
    icons: dict[str, np.ndarray],
    config: dict,
) -> None:
    """Render df to output_path as an MP4 with the custom styling."""
    duration = float(config["duration"])
    fps = int(config["fps"])
    n_bars = int(config["n_bars"])
    bar_size = float(config["bar_size"])
    dpi = int(config["dpi"])
    title = config.get("title")
    title_size = int(config["title_size"])
    value_label_size = int(config["value_label_size"])
    period_label_size = int(config["period_label_size"])
    name_label_size = int(config.get("name_label_size", 28))
    period_fmt = config.get("period_fmt")
    background = config.get("background") or "white"
    font_path = config.get("font_path")
    font_props = FontProperties(fname=font_path) if font_path else FontProperties()

    total_frames = max(int(round(duration * fps)), 2)
    hold_pct = float(config.get("hold_final_pct", 0.0) or 0.0)
    hold_frames = max(0, int(round(total_frames * hold_pct)))
    animated_frames = max(2, total_frames - hold_frames)
    n_periods = len(df)
    columns = list(df.columns)
    custom_colors = config.get("colors") or {}
    colors = {
        col: custom_colors.get(col, DARK_PALETTE[i % len(DARK_PALETTE)])
        for i, col in enumerate(columns)
    }
    display_labels = config.get("labels") or {}

    fig, ax = plt.subplots(figsize=(9, 16), dpi=dpi)
    fig.patch.set_facecolor(background)
    # Reserve 10% white space on top and bottom of the frame for commentary text
    # added later in an editor. Chart axes occupy the middle 80%, with the title
    # rendered as a figure-level text inside that band (never escaping it).
    fig.subplots_adjust(left=0.24, right=0.95, top=0.82, bottom=0.10)

    if title:
        fig.text(
            0.5, 0.86, title,
            ha="center", va="center",
            fontsize=title_size, fontweight="bold",
            fontproperties=font_props,
        )

    icon_trans = blended_transform_factory(ax.transAxes, ax.transData)

    def update(frame_idx: int):
        ax.clear()

        # Map frame -> fractional period position. The final `hold_frames` frames
        # are clamped to the last period so the video ends with a still snapshot.
        if frame_idx >= animated_frames:
            t = float(n_periods - 1)
        else:
            t = frame_idx / max(animated_frames - 1, 1) * (n_periods - 1)
        lo = min(int(t), n_periods - 1)
        hi = min(lo + 1, n_periods - 1)
        alpha = 0.0 if hi == lo else t - lo

        values = df.iloc[lo] * (1 - alpha) + df.iloc[hi] * alpha
        # Rank by smoothed values directly so positions stay uniformly spaced.
        # Bars jump one slot when their values cross, but no overlaps or gaps.
        ranks = values.rank(method="first", ascending=False)

        top_items = ranks.nsmallest(n_bars).index.tolist()
        y_positions = [n_bars - ranks[item] for item in top_items]
        bar_values = [float(values[item]) for item in top_items]

        # Bars: solid colour if `colors[item]` is a string; horizontal stripe
        # band if it's a list/tuple (the chain's tri-colour palette painted
        # across every bar from that chain).
        for item, y, val in zip(top_items, y_positions, bar_values):
            spec = colors[item]
            if isinstance(spec, (list, tuple)) and not isinstance(spec, str):
                n_stripes = len(spec)
                stripe_h = bar_size / n_stripes
                top_edge = y + bar_size / 2
                for i, c in enumerate(spec):
                    sub_y = top_edge - (i + 0.5) * stripe_h
                    ax.barh(sub_y, val, color=c, height=stripe_h,
                            edgecolor="none", alpha=0.97)
            else:
                ax.barh(y, val, color=spec, height=bar_size,
                        edgecolor="none", alpha=0.97)

        max_value = max(bar_values) if bar_values else 1.0
        for item, y, val in zip(top_items, y_positions, bar_values):
            if val <= 0:
                continue
            txt = ax.text(
                val - max_value * 0.012,
                y,
                _format_value(val),
                ha="right",
                va="center",
                color="white",
                fontsize=value_label_size,
                fontweight="bold",
                fontproperties=font_props,
            )
            # Thin dark outline so the value stays readable on yellow/cyan stripes.
            txt.set_path_effects([
                path_effects.Stroke(linewidth=2.5, foreground="#222"),
                path_effects.Normal(),
            ])

        for item, y in zip(top_items, y_positions):
            if item in icons:
                imagebox = OffsetImage(icons[item], zoom=0.30)
                ab = AnnotationBbox(
                    imagebox,
                    (-0.06, y),
                    xycoords=icon_trans,
                    frameon=False,
                    box_alignment=(0.5, 0.5),
                    pad=0.0,
                )
                ax.add_artist(ab)
            else:
                ax.text(
                    -0.015, y, display_labels.get(item, str(item)),
                    transform=icon_trans,
                    ha="right", va="center",
                    fontsize=name_label_size,
                    fontweight="bold",
                    color="#222222",
                    fontproperties=font_props,
                )

        ax.set_facecolor("none")
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.grid(False)
        ax.set_xlim(0, max_value * 1.08)
        ax.set_ylim(-0.5, n_bars - 0.5)
        ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)

        period_str = _format_period(df.index[lo], df.index[hi], alpha, period_fmt)
        ax.text(
            0.98,
            -0.04,
            period_str,
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=period_label_size,
            fontweight="bold",
            color="#555555",
            fontproperties=font_props,
            clip_on=False,
        )
        return []

    anim = FuncAnimation(
        fig, update, frames=total_frames, interval=1000 / fps, blit=False,
    )
    writer = FFMpegWriter(
        fps=fps, codec="libx264", bitrate=6000,
        extra_args=["-pix_fmt", "yuv420p"],
    )
    print(
        f"  rendering: {total_frames} frames ({animated_frames} animated + {hold_frames} hold), "
        f"{n_periods} periods, fps={fps}",
        flush=True,
    )
    anim.save(str(output_path), writer=writer, dpi=dpi)
    plt.close(fig)
