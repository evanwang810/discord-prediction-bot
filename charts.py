"""Chart rendering via QuickChart.io.

We build a Chart.js config and hand Discord a URL — QuickChart renders the PNG
on their servers, so the bot ships no matplotlib/numpy and uses almost no RAM.
The returned URL goes straight into an embed's image.
"""
import json
import urllib.parse
from datetime import datetime

_BASE = "https://quickchart.io/chart"
_BG = "#2b2d31"          # Discord dark background
_GRID = "rgba(255,255,255,0.08)"
_TICK = "#b9bbbe"
_MAX_POINTS = 60         # keep the GET URL comfortably short


def _downsample(xs, ys):
    if len(xs) <= _MAX_POINTS:
        return xs, ys
    step = len(xs) / _MAX_POINTS
    idx = sorted({int(i * step) for i in range(_MAX_POINTS)} | {len(xs) - 1})
    return [xs[i] for i in idx], [ys[i] for i in idx]


def _url(config) -> str:
    c = urllib.parse.quote(json.dumps(config, separators=(",", ":")))
    return (f"{_BASE}?c={c}&w=640&h=320&devicePixelRatio=2"
            f"&bkg={urllib.parse.quote(_BG)}")


def _axes(y_label, y_min=None, y_max=None):
    y = {"grid": {"color": _GRID}, "ticks": {"color": _TICK},
         "title": {"display": True, "text": y_label, "color": _TICK}}
    if y_min is not None:
        y["min"] = y_min
    if y_max is not None:
        y["max"] = y_max
    return {"x": {"grid": {"color": _GRID}, "ticks": {"color": _TICK,
            "maxTicksLimit": 8}}, "y": y}


def odds_chart(times: list[datetime], yes_probs: list[float], question: str) -> str:
    times, yes_probs = _downsample(times, yes_probs)
    labels = [t.strftime("%m/%d %H:%M") for t in times]
    config = {
        "type": "line",
        "data": {"labels": labels, "datasets": [{
            "label": "YES probability (%)",
            "data": [round(p * 100, 1) for p in yes_probs],
            "borderColor": "#57f287", "backgroundColor": "rgba(87,242,135,0.15)",
            "borderWidth": 2, "fill": True, "tension": 0.25,
            "pointRadius": 0, "stepped": False,
        }]},
        "options": {
            "plugins": {"legend": {"labels": {"color": _TICK}}},
            "scales": _axes("YES %", 0, 100),
        },
    }
    return _url(config)


def portfolio_chart(dates: list[datetime], worths: list[float],
                    username: str, currency: str) -> str:
    dates, worths = _downsample(dates, worths)
    labels = [d.strftime("%m/%d") for d in dates]
    config = {
        "type": "line",
        "data": {"labels": labels, "datasets": [{
            "label": f"Net worth ({currency})",
            "data": [round(w) for w in worths],
            "borderColor": "#5865f2", "backgroundColor": "rgba(88,101,242,0.15)",
            "borderWidth": 2, "fill": True, "tension": 0.25, "pointRadius": 2,
        }]},
        "options": {
            "plugins": {"legend": {"labels": {"color": _TICK}}},
            "scales": _axes(currency),
        },
    }
    return _url(config)
