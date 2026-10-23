#!/usr/bin/env python3
"""GitHub-style contribution heatmap for gptshivam595. Real public counts only."""
import math
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

USER = "gptshivam595"
OUT = Path(__file__).resolve().parent / "heatmap.png"
SKY = ["#ebedf0", "#c6e48b", "#7bc96f", "#239a3b", "#196127"]


def fetch_year():
    now = datetime.now(timezone.utc)
    counts = {}
    for year in (now.year - 1, now.year):
        url = f"https://github.com/users/{USER}/contributions?from={year}-01-01&to={year}-12-31"
        req = urllib.request.Request(url, headers={"User-Agent": "contribution-heatmap"})
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
        tips = {}
        for tip_id, n in re.findall(
            r'for="(contribution-day-component-[^"]+)"[^>]*>\s*(?:(\d+)\s+contributions?|No contributions)',
            html,
        ):
            tips[tip_id] = int(n) if n else 0
        for date, tip_id in re.findall(
            r'data-date="(\d{4}-\d{2}-\d{2})" id="(contribution-day-component-[^"]+)"',
            html,
        ):
            counts[date] = tips.get(tip_id, 0)
    return counts


def grid(counts):
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=364)
    start -= timedelta(days=(start.weekday() + 1) % 7)
    cells = []
    day = start
    while day <= end:
        key = day.isoformat()
        cells.append((key, counts.get(key, 0)))
        day += timedelta(days=1)
    nz = sorted(c for _, c in cells if c > 0)
    busy = nz[math.floor(0.95 * (len(nz) - 1))] if nz else 0

    def level(count):
        if count <= 0:
            return 0
        if busy <= 0:
            return 4
        return 1 + min(3, math.floor((count / busy) * 4))

    weeks = []
    for i in range(0, len(cells), 7):
        weeks.append([(d, c, level(c)) for d, c in cells[i : i + 7]])
    return weeks, sum(c for _, c in cells)


def font(size, bold=False):
    path = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    )
    if Path(path).exists():
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def render():
    weeks, total = grid(fetch_year())
    cell, gap = 12, 3
    label_w = 32
    left, top = 28, 78
    grid_w = label_w + len(weeks) * (cell + gap)
    width = max(860, left + grid_w + 28)
    height = top + 7 * (cell + gap) + 64
    img = Image.new("RGB", (width, height), "#f6f8fa")
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((8, 8, width - 9, height - 9), 16, fill="#ffffff", outline="#d0d7de")
    draw.text((left, 24), f"{total:,} contributions in the last year", fill="#1f2328", font=font(16, True))
    small = font(12)
    months = []
    prev = None
    for i, week in enumerate(weeks):
        month = week[0][0][5:7]
        if month != prev:
            months.append((i, datetime.fromisoformat(week[0][0]).strftime("%b")))
            prev = month
    if len(months) > 1 and months[1][0] - months[0][0] < 3:
        months.pop(0)
    for i, name in months:
        x = left + label_w + i * (cell + gap)
        draw.text((x, top - 18), name, fill="#656d76", font=small)
    for name, row in (("Mon", 1), ("Wed", 3), ("Fri", 5)):
        y = top + row * (cell + gap)
        draw.text((left, y - 1), name, fill="#656d76", font=small)
    for w, week in enumerate(weeks):
        for d, (_date, _count, level) in enumerate(week):
            x = left + label_w + w * (cell + gap)
            y = top + d * (cell + gap)
            draw.rounded_rectangle((x, y, x + cell - 1, y + cell - 1), 2, fill=SKY[level])
    lx = width - 28 - (5 * (cell + 4) + 70)
    ly = height - 42
    draw.text((lx, ly), "Less", fill="#656d76", font=small)
    x = lx + 36
    for color in SKY:
        draw.rounded_rectangle((x, ly + 1, x + cell - 1, ly + cell), 2, fill=color)
        x += cell + 4
    draw.text((x + 4, ly), "More", fill="#656d76", font=small)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, "PNG")
    print(f"wrote {OUT} {img.size} total={total}")


if __name__ == "__main__":
    render()
