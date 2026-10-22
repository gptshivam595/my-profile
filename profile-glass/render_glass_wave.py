#!/usr/bin/env python3
"""Render a GitHub-compatible animated glass-wave contribution graph.

GitHub READMEs cannot run WebGL. This script reads the public contribution
calendar (no token) and paints an animated GIF. Bar height and color follow
real daily counts. The moving light and contour lines do not add activity.

Metrics:
- Total contributions: sum of daily counts in the displayed window.
- Longest streak: most consecutive days with count > 0 inside that window.
- Active since: account created_at from api.github.com.
- Repositories: public_repos only.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

USER_AGENT = "Mozilla/5.0 (compatible; glass-wave/1.0)"
W, H = 1240, 720
FRAMES = 12


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=40) as response:
        return response.read().decode("utf-8", "replace")


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=40) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_year(username: str, year: int) -> dict[str, int]:
    html = fetch(
        f"https://github.com/users/{username}/contributions?from={year}-01-01&to={year}-12-31"
    )
    days: dict[str, int] = {}
    for match in re.finditer(
        r'data-date="(\d{4}-\d{2}-\d{2})" id="(contribution-day-component-[^"]+)" data-level="(\d)"',
        html,
    ):
        day, cell_id, _level = match.groups()
        tip = re.search(
            rf'for="{re.escape(cell_id)}"[^>]*>\s*(?:(\d+)\s+contributions?|No contributions)',
            html,
        )
        days[day] = int(tip.group(1)) if tip and tip.group(1) else 0
    return days


def load_calendar(username: str) -> tuple[list[tuple[date, int]], dict]:
    profile = fetch_json(f"https://api.github.com/users/{username}")
    created = datetime.strptime(profile["created_at"][:10], "%Y-%m-%d").date()
    today = date.today()
    counts: dict[str, int] = {}
    for year in range(created.year, today.year + 1):
        counts.update(fetch_year(username, year))
    start = today - timedelta(days=7 * 52)
    start = start - timedelta(days=(start.weekday() + 1) % 7)
    series: list[tuple[date, int]] = []
    cursor = start
    while cursor <= today:
        series.append((cursor, counts.get(cursor.isoformat(), 0)))
        cursor += timedelta(days=1)
    return series, profile


def longest_streak(series: list[tuple[date, int]]) -> int:
    best = run = 0
    for _day, count in series:
        if count > 0:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def font(size: int, bold: bool = False, script: bool = False) -> ImageFont.FreeTypeFont:
    if script:
        path = Path("/tmp/fonts/GreatVibes-Regular.ttf")
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            url = "https://github.com/google/fonts/raw/main/ofl/greatvibes/GreatVibes-Regular.ttf"
            path.write_bytes(
                urllib.request.urlopen(
                    urllib.request.Request(url, headers={"User-Agent": USER_AGENT}),
                    timeout=40,
                ).read()
            )
        return ImageFont.truetype(str(path), size)
    name = "LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf"
    return ImageFont.truetype(f"/usr/share/fonts/truetype/liberation/{name}", size)


def lerp(a, b, t: float):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def color_for(count: int, peak: int) -> tuple[int, int, int]:
    if count <= 0 or peak <= 0:
        return (22, 48, 96)
    t = min(1.0, math.sqrt(count / peak))
    stops = [
        (0.0, (37, 99, 235)),
        (0.3, (34, 211, 238)),
        (0.55, (139, 92, 246)),
        (0.78, (217, 70, 239)),
        (1.0, (251, 146, 60)),
    ]
    for (left, ca), (right, cb) in zip(stops, stops[1:]):
        if t <= right:
            return lerp(ca, cb, (t - left) / (right - left or 1))
    return stops[-1][1]


def shade(rgb, factor: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(c * factor))) for c in rgb)


def rounded(draw: ImageDraw.ImageDraw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def draw_cube(draw, x, y, bw, bd, height, rgb, glow):
    """Glass prism. (x, y) is the front-bottom corner. Faces stay dark enough to read as glass."""
    rim = lerp(rgb, (210, 250, 255), 0.35 + 0.4 * glow)
    top = lerp(shade(rgb, 1.05), (190, 245, 255), 0.22 + 0.25 * glow)
    left = shade(rgb, 0.62)
    right = shade(rgb, 0.38)
    skew = bd
    yb, yt = y, y - height
    draw.polygon(
        [(x, yt), (x + bw, yt - skew * 0.22), (x + bw, yb - skew * 0.22), (x, yb)],
        fill=right + (235,),
    )
    draw.polygon(
        [(x, yt), (x - skew * 0.85, yt - skew * 0.72), (x - skew * 0.85, yb - skew * 0.72), (x, yb)],
        fill=left + (225,),
    )
    draw.polygon(
        [
            (x, yt),
            (x + bw, yt - skew * 0.22),
            (x + bw - skew * 0.85, yt - skew * 0.94),
            (x - skew * 0.85, yt - skew * 0.72),
        ],
        fill=top + (240,),
    )
    draw.line([(x, yt), (x + bw, yt - skew * 0.22)], fill=rim + (255,), width=1)


def bar_height(count: int, peak: int) -> float:
    if count <= 0 or peak <= 0:
        return 11
    return 18 + 64 * math.sqrt(count / peak)


def render_frame(series, profile, phase: float) -> Image.Image:
    image = Image.new("RGBA", (W, H), (5, 11, 26, 255))
    draw = ImageDraw.Draw(image, "RGBA")
    for y in range(H):
        draw.line([(0, y), (W, y)], fill=lerp((5, 11, 26), (7, 16, 36), y / H) + (255,))

    weeks: list[list[tuple[date, int]]] = []
    bucket: list[tuple[date, int]] = []
    for item in series:
        bucket.append(item)
        if len(bucket) == 7:
            weeks.append(bucket)
            bucket = []
    if bucket:
        weeks.append(bucket)

    peak = max((count for _day, count in series), default=0)
    total = sum(count for _day, count in series)
    streak = longest_streak(series)
    by_month: dict[str, int] = {}
    for day, count in series:
        key = day.strftime("%Y-%m")
        by_month[key] = by_month.get(key, 0) + count
    peak_key = max(by_month, key=by_month.get) if by_month else None
    peak_total = by_month.get(peak_key, 0) if peak_key else 0
    peak_label = datetime.strptime(peak_key, "%Y-%m").strftime("%b %Y") if peak_key else "\u2014"
    recent_start = series[-1][0] - timedelta(days=29)
    recent = sum(count for day, count in series if day >= recent_start)
    created = datetime.strptime(profile["created_at"][:10], "%Y-%m-%d").date()
    public_repos = int(profile.get("public_repos") or 0)
    window_start, window_end = series[0][0], series[-1][0]

    draw.text((32, 16), "GLASS WAVE", font=font(12, True), fill=(103, 202, 247))
    draw.text((32, 34), profile.get("name") or profile["login"], font=font(15), fill=(176, 204, 242))
    title_font = font(42, True)
    draw.text((30, 54), "Contributions", font=title_font, fill=(232, 242, 255))
    title_w = title_font.getlength("Contributions")
    draw.text((38 + title_w, 70), "in Motion", font=font(36, script=True), fill=(56, 189, 248))
    draw.text((32, 104), "Consistent effort creates extraordinary results", font=font(14), fill=(140, 170, 210))
    draw.multiline_text(
        (900, 28),
        "\u201cDiscipline today\nbuilds the opportunities\ntomorrow.\u201d",
        font=font(15),
        fill=(176, 206, 242),
        spacing=3,
    )

    nweeks = max(len(weeks), 1)
    bw, bd, step, row_gap = 13, 7, 11.2, 11
    ox = 90
    oy = 455
    positions = {}

    span = (nweeks - 1) * step + bw
    draw.line([(ox - 8, oy + 8), (ox + span, oy + 6)], fill=(64, 156, 240, 255), width=2)

    order = [(di, wi, day, count) for wi, week in enumerate(weeks) for di, (day, count) in enumerate(week)]
    order.sort(key=lambda item: (item[0], item[1]), reverse=True)
    crest = (phase / math.tau) % 1

    for di, wi, day, count in order:
        band = math.exp(-((wi / nweeks - crest) ** 2) / 0.012)
        wobble = 1.6 * math.sin(phase + wi * 0.45 + di * 0.3)
        height = bar_height(count, peak) + (wobble if count else wobble * 0.35)
        x = ox + wi * step + di * 2.4
        y = oy - di * row_gap
        rgb = color_for(count, peak)
        if count <= 0:
            rgb = lerp((32, 74, 150), (90, 190, 255), 0.25 + 0.45 * band)
        draw_cube(draw, x, y, bw - 1, bd, height, rgb, 0.25 + band)
        positions[(wi, di)] = (x + bw * 0.45, y - height, day, count, height)

    for row, tint in ((1, (56, 189, 248)), (3, (168, 85, 247)), (5, (56, 210, 255))):
        pts = []
        for wi, week in enumerate(weeks):
            if row >= len(week):
                continue
            count = week[row][1]
            height = bar_height(count, peak)
            x = ox + wi * step + row * 2.4 + bw * 0.4
            y = oy - row * row_gap - height - 2 + math.sin(phase * 1.4 + wi * 0.38 + row) * 2.2
            pts.append((x, y))
        if len(pts) > 2:
            draw.line(pts, fill=tint + (150,), width=2)

    seen = set()
    for wi, week in enumerate(weeks):
        month = week[0][0].strftime("%b")
        if month in seen:
            continue
        seen.add(month)
        draw.text((ox + wi * step, oy + 16), month, font=font(12), fill=(148, 176, 214))

    def callout(anchor, text, left_side):
        x, y = anchor
        tx = 36 if left_side else 980
        ty = min(max(y, 150), 250)
        draw.line([(x, y), (tx + (120 if left_side else 0), ty)], fill=(125, 211, 252, 200), width=1)
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(255, 214, 102, 255))
        draw.multiline_text((tx, ty - 32), text, font=font(13, True), fill=(232, 242, 255), spacing=2)

    if peak_key:
        target = None
        for wi, week in enumerate(weeks):
            for di, (day, count) in enumerate(week):
                if day.strftime("%Y-%m") == peak_key and (target is None or count > target[0]):
                    target = (count, wi, di)
        if target and (target[1], target[2]) in positions:
            x, y, _day, _count, _h = positions[(target[1], target[2])]
            callout((x, y), f"Peak month\n{peak_label}\n{peak_total} contributions", target[1] > nweeks * 0.55)

    last_active = None
    for wi, week in enumerate(weeks):
        for di, (day, count) in enumerate(week):
            if count > 0:
                last_active = (wi, di)
    if last_active and last_active in positions:
        x, y, _day, _count, _h = positions[last_active]
        callout((x, y), f"Recent activity\nlast 30 days\n{recent} contributions", False)

    period = f"{window_start.strftime('%b %Y')} \u2013 {window_end.strftime('%b %Y')}"
    draw.text((32, 532), f"{period}   \u00b7   public contributions   \u00b7   height and color = daily count", font=font(12), fill=(126, 154, 196))

    legend = [(0, "None"), (max(1, peak // 8), "Low"), (max(1, peak // 3), "Medium"), (max(1, int(peak * 0.7)), "High"), (max(1, peak), "Peak")]
    lx = 760
    for count, label in legend:
        rgb = (18, 42, 88) if count == 0 else color_for(count, peak)
        draw_cube(draw, lx, 548, 10, 5, 8 if count == 0 else 10 + 8 * math.sqrt(count / max(peak, 1)), rgb, 0.2)
        draw.text((lx + 16, 534), label, font=font(11), fill=(166, 194, 230))
        lx += 78

    cards = [
        (f"{total:,}", "Total contributions", period),
        (str(streak), "Longest streak", "consecutive active days"),
        (str(created.year), "Active since", created.strftime("%b %d, %Y")),
        (str(public_repos), "Repositories", "public repositories"),
    ]
    card_w, card_h, gap = 276, 78, 14
    left = (W - (card_w * 4 + gap * 3)) / 2
    top = 612
    for index, (value, title, subtitle) in enumerate(cards):
        x = left + index * (card_w + gap)
        rounded(draw, (x, top, x + card_w, top + card_h), 14, (8, 16, 36, 255), outline=(48, 126, 214), width=2)
        draw.text((x + 16, top + 8), value, font=font(24, True), fill=(236, 244, 255))
        draw.text((x + 16, top + 38), title, font=font(13, True), fill=(103, 202, 247))
        draw.text((x + 16, top + 56), subtitle, font=font(11), fill=(150, 176, 214))

    return image


def save_gif(frames: list[Image.Image], path: Path) -> None:
    rgb = [frame.convert("RGB") for frame in frames]
    sheet = Image.new("RGB", (W, H * 3))
    for slot, index in enumerate((0, FRAMES // 2, FRAMES - 1)):
        sheet.paste(rgb[index], (0, H * slot))
    palette = sheet.quantize(colors=80, method=Image.Quantize.MEDIANCUT)
    quantized = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in rgb]
    path.parent.mkdir(parents=True, exist_ok=True)
    quantized[0].save(
        path,
        save_all=True,
        append_images=quantized[1:],
        duration=110,
        loop=0,
        optimize=True,
        disposal=2,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="gptshivam595")
    parser.add_argument("--out", default="profile-glass/glass-wave.gif")
    args = parser.parse_args()
    series, profile = load_calendar(args.username)
    if not series:
        raise SystemExit("No contribution days were returned.")
    frames = [render_frame(series, profile, phase=i / FRAMES * math.tau) for i in range(FRAMES)]
    out = Path(args.out)
    save_gif(frames, out)
    frames[0].convert("RGB").save(out.with_suffix(".png"))
    print(json.dumps({
        "days": len(series),
        "from": series[0][0].isoformat(),
        "to": series[-1][0].isoformat(),
        "total": sum(count for _d, count in series),
        "peak_day": max(count for _d, count in series),
        "longest_streak_days": longest_streak(series),
        "public_repos": profile.get("public_repos"),
        "gif_bytes": out.stat().st_size,
    }, indent=2))


if __name__ == "__main__":
    main()
