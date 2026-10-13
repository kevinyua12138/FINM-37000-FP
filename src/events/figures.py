"""Figures for issue #6: refill half-life, refill ratio and forward returns, each over shock time."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

BLUE = "#2a6fdb"
GREY = "#6b7280"
OBSERVATION_S = 3.0
RETURN_COLUMNS = ("y_5s", "y_30s", "y_120s")


def _axes(title, ylabel):
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.set_title(title, loc="left", fontsize=12)
    ax.set_xlabel("shock time")
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", color="#e5e7eb", linewidth=0.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    return fig, ax


def _save(fig, path):
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_half_life(events, path):
    """Seconds until the eaten side is back to half its pre-shock size. Open markers never got there within 3s."""
    fig, ax = _axes("Refill half-life after each shock", "half-life (seconds)")
    recovered = events["half_life_s"].notna()
    ax.scatter(events.loc[recovered, "t0"], events.loc[recovered, "half_life_s"], color=BLUE, s=36, label="recovered within 3s")
    ax.scatter(events.loc[~recovered, "t0"], np.full((~recovered).sum(), OBSERVATION_S), facecolors="none",
               edgecolors=BLUE, s=36, label="not recovered (>3s)")
    ax.set_ylim(-0.2, OBSERVATION_S + 0.4)
    ax.legend(frameon=False, loc="lower left")
    return _save(fig, path)


def plot_refill_ratio(events, path):
    fig, ax = _axes("Refill ratio after each shock", "D_now / D_pre")
    ax.scatter(events["t0"], events["refill_ratio"], color=BLUE, s=36)
    ax.axhline(1.0, color=GREY, linewidth=1)
    return _save(fig, path)


def plot_forward_return(events, column, path):
    """Return in basis points, signed by shock direction, so above zero means the move continued."""
    fig, ax = _axes(f"Forward return {column[2:]} after entry", "return in shock direction (bp)")
    ax.scatter(events["t0"], events[column] * 1e4, color=BLUE, s=36)
    ax.axhline(0.0, color=GREY, linewidth=1)
    return _save(fig, path)


def make_issue6_figures(events, out_dir):
    """Write the five issue #6 figures and the event table to out_dir. Returns the figure paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    events.to_csv(out / "events.csv", index=False)
    paths = [
        plot_half_life(events, out / "half_life.png"),
        plot_refill_ratio(events, out / "refill_ratio.png"),
    ]
    paths += [plot_forward_return(events, c, out / f"{c}.png") for c in RETURN_COLUMNS]
    return paths
