"""Charts via QuickChart.io.

We build a Chart.js config, POST it to QuickChart, and get back PNG bytes that
get attached to the Discord message. Posting (instead of putting the config in
the image URL) avoids Discord's 2048-char embed-URL limit. No matplotlib, almost
no RAM. The x axis is a real time scale so points sit at their actual time.
"""
from datetime import datetime
import aiohttp

_ENDPOINT = "https://quickchart.io/chart"
_BG = "#2b2d31"
_GRID = "rgba(255,255,255,0.06)"
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


def _x_axis():
    return {
        "type": "time",
        "time": {"displayFormats": {"hour": "MMM D HH:mm", "day": "MMM D"}},
        "ticks": {"fontColor": _TICK, "maxTicksLimit": 4, "maxRotation": 0},
        "gridLines": {"display": False},
    }


def odds_config(times: list[datetime], yes_probs: list[float]):
    pts = _downsample([{"t": _ms(t), "y": round(p * 100, 1)}
                       for t, p in zip(times, yes_probs)])
    return {
        "type": "line",
        "data": {"datasets": [{
            "data": pts, "borderColor": "#57f287",
            "backgroundColor": "rgba(87,242,135,0.15)", "borderWidth": 2,
            "fill": True, "steppedLine": True, "pointRadius": 0, "lineTension": 0,
        }]},
        "options": {
            "legend": {"display": False},
            "scales": {
                "xAxes": [_x_axis()],
                "yAxes": [{
                    "ticks": {"min": 0, "max": 100, "stepSize": 50, "fontColor": _TICK},
                    "gridLines": {"color": _GRID, "zeroLineColor": _GRID},
                }],
            },
        },
    }


def portfolio_config(dates: list[datetime], worths: list[float]):
    pts = _downsample([{"t": _ms(d), "y": round(w)} for d, w in zip(dates, worths)])
    return {
        "type": "line",
        "data": {"datasets": [{
            "data": pts, "borderColor": "#5865f2",
            "backgroundColor": "rgba(88,101,242,0.15)", "borderWidth": 2,
            "fill": True, "pointRadius": 0, "lineTension": 0,
        }]},
        "options": {
            "legend": {"display": False},
            "scales": {
                "xAxes": [_x_axis()],
                "yAxes": [{
                    "ticks": {"fontColor": _TICK, "maxTicksLimit": 4},
                    "gridLines": {"color": _GRID, "zeroLineColor": _GRID},
                }],
            },
        },
    }


async def render_png(config, width=640, height=280):
    """POST a chart config to QuickChart, return PNG bytes (or None on failure)."""
    payload = {"chart": config, "width": width, "height": height,
               "backgroundColor": _BG, "devicePixelRatio": 2, "format": "png"}
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(_ENDPOINT, json=payload) as resp:
                if resp.status != 200:
                    return None
                return await resp.read()
    except Exception:
        return None
