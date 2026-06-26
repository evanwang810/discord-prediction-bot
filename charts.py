"""Chart rendering via QuickChart.io.

We build a Chart.js config and hand Discord a URL, so QuickChart renders the PNG
on their servers. No matplotlib, almost no RAM. The x axis is a real time scale
so points sit at their actual moment in time, not evenly spaced.
"""
import json
import urllib.parse
from datetime import datetime

_BASE = "https://quickchart.io/chart"
_BG = "#2b2d31"
_GRID = "rgba(255,255,255,0.08)"
_TICK = "#b9bbbe"
_MAX_POINTS = 80


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _downsample(points):
    if len(points) <= _MAX_POINTS:
        return points
    step = len(points) / _MAX_POINTS
    idx = sorted({int(i * step) for i in range(_MAX_POINTS)} | {len(points) - 1})
    return [points[i] for i in idx]


def _url(config) -> str:
    c = urllib.parse.quote(json.dumps(config, separators=(",", ":")))
    return f"{_BASE}?c={c}&w=640&h=320&devicePixelRatio=2&bkg={urllib.parse.quote(_BG)}"


def _x_axis():
    return {
        "type": "time",
        "time": {"displayFormats": {"hour": "MMM D HH:mm", "day": "MMM D"}},
        "ticks": {"fontColor": _TICK, "maxTicksLimit": 7, "maxRotation": 0},
        "gridLines": {"color": _GRID, "zeroLineColor": _GRID},
    }


def odds_chart(times: list[datetime], yes_probs: list[float], question: str) -> str:
    pts = _downsample([{"t": _ms(t), "y": round(p * 100, 1)}
                       for t, p in zip(times, yes_probs)])
    config = {
        "type": "line",
        "data": {"datasets": [{
            "label": "YES probability (%)", "data": pts,
            "borderColor": "#57f287", "backgroundColor": "rgba(87,242,135,0.15)",
            "borderWidth": 2, "fill": True, "steppedLine": True,
            "pointRadius": 0, "lineTension": 0,
        }]},
        "options": {
            "legend": {"labels": {"fontColor": _TICK}},
            "scales": {
                "xAxes": [_x_axis()],
                "yAxes": [{
                    "ticks": {"min": 0, "max": 100, "fontColor": _TICK, "stepSize": 25},
                    "gridLines": {"color": _GRID, "zeroLineColor": _GRID},
                    "scaleLabel": {"display": True, "labelString": "YES %", "fontColor": _TICK},
                }],
            },
        },
    }
    return _url(config)


def portfolio_chart(dates: list[datetime], worths: list[float],
                    username: str, currency: str) -> str:
    pts = _downsample([{"t": _ms(d), "y": round(w)} for d, w in zip(dates, worths)])
    config = {
        "type": "line",
        "data": {"datasets": [{
            "label": f"Net worth ({currency})", "data": pts,
            "borderColor": "#5865f2", "backgroundColor": "rgba(88,101,242,0.15)",
            "borderWidth": 2, "fill": True, "lineTension": 0, "pointRadius": 2,
        }]},
        "options": {
            "legend": {"labels": {"fontColor": _TICK}},
            "scales": {
                "xAxes": [_x_axis()],
                "yAxes": [{
                    "ticks": {"fontColor": _TICK},
                    "gridLines": {"color": _GRID, "zeroLineColor": _GRID},
                }],
            },
        },
    }
    return _url(config)
