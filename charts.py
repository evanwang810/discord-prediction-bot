"""Matplotlib chart rendering. Returns PNG bytes ready for discord.File.

matplotlib is imported lazily inside _plt() rather than at module load, so the
~130 MB import cost is only paid the first time someone requests a chart. This
keeps idle memory low enough for small hosts (e.g. bot-hosting.net's 256 MB
free tier).
"""
import io
from datetime import datetime

_plt_mod = None
_mdates_mod = None


def _plt():
    global _plt_mod, _mdates_mod
    if _plt_mod is None:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        _plt_mod, _mdates_mod = plt, mdates
    return _plt_mod, _mdates_mod


_STYLE = {
    "figure.facecolor": "#2b2d31",
    "axes.facecolor": "#2b2d31",
    "axes.edgecolor": "#72767d",
    "axes.labelcolor": "#dcddde",
    "xtick.color": "#b9bbbe",
    "ytick.color": "#b9bbbe",
    "text.color": "#dcddde",
    "grid.color": "#3f4248",
}


def _render(plt, fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def odds_chart(times: list[datetime], yes_probs: list[float], question: str) -> io.BytesIO:
    plt, mdates = _plt()
    with plt.rc_context(_STYLE):
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(times, [p * 100 for p in yes_probs], color="#57f287", linewidth=2,
                drawstyle="steps-post")
        ax.set_ylim(0, 100)
        ax.axhline(50, color="#72767d", linestyle="--", linewidth=0.8)
        ax.set_ylabel("YES probability (%)")
        ax.set_title(question[:80])
        ax.grid(True, alpha=0.5)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d\n%H:%M"))
        fig.autofmt_xdate(rotation=0, ha="center")
        return _render(plt, fig)


def portfolio_chart(dates: list[datetime], worths: list[float],
                    username: str, currency: str) -> io.BytesIO:
    plt, mdates = _plt()
    with plt.rc_context(_STYLE):
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(dates, worths, color="#5865f2", linewidth=2, marker="o", markersize=4)
        ax.set_ylabel(f"Net worth ({currency})")
        ax.set_title(f"{username} — net worth over time")
        ax.grid(True, alpha=0.5)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        fig.autofmt_xdate(rotation=0, ha="center")
        return _render(plt, fig)
