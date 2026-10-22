#!/usr/bin/env python3
"""Render a GitHub-compatible animated glass-wave contribution graph.

GitHub READMEs cannot run WebGL. This script reads the public contribution
calendar (no token) and paints an animated GIF whose bar heights and colors
follow real daily counts. A traveling highlight and contour lines animate;
they do not invent activity.

Metrics, all computed from the fetched calendar plus the public user profile:
- Total contributions: sum of daily counts in the displayed window.
- Longest streak: most consecutive days with count > 0 inside that window.
- Active since: the account created_at date from api.github.com.
- Repositories: public_repos from api.github.com (not private repos).
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
W, H = 1100, 640
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
            path.write_bytes(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=40).read())
        return ImageFont.truetype(str(path), size)
    name = "LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf"
    return ImageFont.truetype(f"/usr/share/fonts/truetype/liberation/{name}", size)


def lerp(a, b, t: float):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def color_for(count: int, peak: int) -> tuple[int, int, int]:
    if count <= 0 or peak <= 0:
        return (22, 40, 82)
    t = min(1.0, count / peak)
    stops = [
        (0.0, (37, 99, 235)),
        (0.28, (34, 211, 238)),
        (0.55, (124, 58, 237)),
        (0.78, (217, 70, 239)),
        (1.0, (251, 146, 60)),
    ]
    for (left, ca), (right, cb) in zip(stops, stops[1:]):
        if t <= right:
            return lerp(ca, cb, (t - left) / (right - left))
    return stops[-1][1]


def shade(rgb, factor: float) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(c * factor))) for c in rgb)


def rounded(draw: ImageDraw.ImageDraw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def draw_cube(draw, x, y, bw, bd, height, rgb, glow):
    top = shade(rgb, 1.15 + 0.25 * glow)
    left = shade(rgb, 0.72)
    right = shade(rgb, 0.48)
    x0, y0 = x, y - height
    top_poly = [(x0, y0), (x0 + bw, y0 - bd * 0.35), (x0 + bw - bd, y0 - bd), (x0 - bd, y0 - bd * 0.65)]
    left_poly = [(x0 - bd, y0 - bd * 0.65), (x0, y0), (x0, y0 + height), (x0 - bd, y0 + height - bd * 0.65)]
    right_poly = [(x0, y0), (x0 + bw, y0 - bd * 0.35), (x0 + bw, y0 + height - bd * 0.35), (x0, y0 + height)]
    draw.polygon(left_poly, fill=left)
    draw.polygon(right_poly, fill=right)
    draw.polygon(top_poly, fill=top)


def render_frame(series, profile, phase: float) -> Image.Image:
    image = Image.new("RGBA", (W, H), (5, 8, 22, 255))
    draw = ImageDraw.Draw(image, "RGBA")
    for y in range(H):
        t = y / H
        draw.line([(0, y), (W, y)], fill=lerp((5, 10, 28), (8, 18, 48), t) + (255,))

    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow, "RGBA")
    gdraw.ellipse((180, 120, 980, 560), fill=(37, 99, 235, 28))
    image.alpha_composite(glow)

    weeks: list[list[tuple[date, int]]] = []
    bucket: list[tuple[date, int]] = []
    for item in series:
        bucket.append(item)
        if len(bucket) == 7:
            weeks.append(bucket)
            bucket = []
    if bucket:
        weeks.append(bucket)

    peak = max((count for _d, count in series), default=0)
    total = sum(count for _d, count in series)
    streak = longest_streak(series)
    by_month: dict[str, int] = {}
    for day, count in series:
        key = day.strftime("%Y-%m")
        by_month[key] = by_month.get(key, 0) + count
    peak_key = max(by_month, key=by_month.get) if by_month else None
    peak_total = by_month.get(peak_key, 0) if peak_key else 0
    peak_label = datetime.strptime(peak_key, "%Y-%m").strftime("%b %Y") if peak_key else "—"
    recent_start = series[-1][0] - timedelta(days=29) if series else date.today()
    recent = sum(count for day, count in series if day >= recent_start)
    created = datetime.strptime(profile["created_at"][:10], "%Y-%m-%d").date()
    public_repos = int(profile.get("public_repos") or 0)
    window_start, window_end = series[0][0], series[-1][0]

    draw.text((36, 22), "GLASS WAVE", font=font(13, True), fill=(125, 211, 252))
    draw.text((36, 44), profile.get("name") or profile["login"], font=font(16), fill=(186, 210, 255))
    draw.text((34, 66), "Contributions", font=font(46, True), fill=(226, 240, 255))
    draw.text((318, 78), "in Motion", font=font(42, script=True), fill=(56, 189, 248))
    draw.text((36, 124), "Consistent effort creates extraordinary results", font=font(15), fill=(148, 176, 214))

    quote = "\u201cDiscipline today\nbuilds the opportunities\ntomorrow.\u201d"
    draw.multiline_text((860, 36), quote, font=font(15), fill=(186, 214, 255), spacing=4, align="left")

    for index, amp in enumerate((18, 28, 14)):
        pts = []
        for x in range(70, 1040, 8):
            y = 430 + math.sin((x * 0.02) + phase + index) * amp + index * 16
            pts.append((x, y))
        gdraw = ImageDraw.Draw(image, "RGBA")
        gdraw.line(pts, fill=(56, 189, 248, 110), width=2)

    ox, oy = 78, 470
    xstep, zstep = 16.2, 11
    positions = {}
    order = []
    for wi, week in enumerate(weeks):
        for di, (day, count) in enumerate(week):
            order.append((di, wi, day, count))
    order.sort(key=lambda item: (item[0], item[1]), reverse=True)

    for di, wi, day, count in order:
        depth = di / 6
        scale = 1.08 - depth * 0.28
        height = (7 if count <= 0 else 12 + (count / max(peak, 1)) * 78) * scale
        x = ox + wi * xstep + depth * 34
        y = oy - depth * zstep
        nweeks = max(len(weeks), 1)
        crest = (phase / math.tau) % 1
        band = math.exp(-((wi / nweeks - crest) ** 2) / 0.008)
        rgb = color_for(count, peak)
        if count <= 0:
            rgb = shade(rgb, 0.7 + 0.55 * band)
            glow_amt = 0.15 + band
        else:
            glow_amt = 0.35 + band
        bw, bd = 11 * scale, 7 * scale
        draw_cube(draw, x, y, bw, bd, height, rgb, glow_amt)
        positions[(wi, di)] = (x, y - height, day, count)

    label_font = font(12)
    seen = set()
    for wi, week in enumerate(weeks):
        month = week[0][0].strftime("%b")
        if month in seen:
            continue
        seen.add(month)
        x = ox + wi * xstep
        draw.text((x, oy + 16), month, font=label_font, fill=(148, 176, 214))

    def callout(anchor, text, side):
        x, y = anchor
        tx = 150 if side == "left" else 900
        ty = max(168, y - 36)
        draw.line([(x, y), (tx, ty)], fill=(125, 211, 252, 180), width=1)
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(255, 214, 102))
        draw.multiline_text((tx, ty - 28), text, font=font(13, True), fill=(226, 240, 255), spacing=2)

    if peak_key:
        target = None
        for wi, week in enumerate(weeks):
            for di, (day, count) in enumerate(week):
                if day.strftime("%Y-%m") == peak_key and (target is None or count > target[0]):
                    target = (count, wi, di)
        if target and (target[1], target[2]) in positions:
            x, y, _day, _count = positions[(target[1], target[2])]
            callout((x, y), f"Peak month\n{peak_label}\n{peak_total} contributions", "right" if target[1] < len(weeks) / 2 else "left")

    if series:
        last_active = None
        for wi, week in enumerate(weeks):
            for di, (day, count) in enumerate(week):
                if count > 0:
                    last_active = (wi, di, day)
        if last_active and (last_active[0], last_active[1]) in positions:
            x, y, _d, _c = positions[(last_active[0], last_active[1])]
            callout((x, y), f"Recent activity\nlast 30 days\n{recent} contributions", "right")

    period = f"{window_start.strftime('%b %Y')} \u2013 {window_end.strftime('%b %Y')}"
    draw.text((36, 508), f"{period}  \u00b7  public contributions  \u00b7  bar height = daily count", font=font(12), fill=(120, 146, 186))

    cards = [
        (f"{total:,}", "Total contributions", period),
        (str(streak), "Longest streak", "consecutive active days"),
        (str(created.year), "Active since", created.strftime("%b %d, %Y")),
        (str(public_repos), "Repositories", "public repositories"),
    ]
    card_w, card_h = 246, 78
    gap = 16
    left = (W - (card_w * 4 + gap * 3)) / 2
    top = 540
    for index, (value, title, subtitle) in enumerate(cards):
        x = left + index * (card_w + gap)
        rounded(draw, (x, top, x + card_w, top + card_h), 16, (10, 18, 42, 230), outline=(56, 130, 220), width=2)
        draw.text((x + 16, top + 10), value, font=font(24, True), fill=(226, 240, 255))
        draw.text((x + 16, top + 40), title, font=font(13, True), fill=(125, 211, 252))
        draw.text((x + 16, top + 56), subtitle, font=font(11), fill=(148, 176, 214))

    return image


def save_gif(frames: list[Image.Image], path: Path) -> None:
    rgb = [frame.convert("RGB") for frame in frames]
    sheet = Image.new("RGB", (W, H * 3))
    for index in (0, FRAMES // 2, FRAMES - 1):
        sheet.paste(rgb[index], (0, H * (0 if index == 0 else 1 if index == FRAMES // 2 else 2)))
    palette = sheet.quantize(colors=72, method=Image.Quantize.MEDIANCUT)
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
    total = sum(count for _d, count in series)
    print(json.dumps({
        "days": len(series),
        "from": series[0][0].isoformat(),
        "to": series[-1][0].isoformat(),
        "total": total,
        "peak_day": max(count for _d, count in series),
        "longest_streak_days": longest_streak(series),
        "public_repos": profile.get("public_repos"),
        "created_at": profile.get("created_at"),
        "name": profile.get("name"),
        "gif_bytes": out.stat().st_size,
    }, indent=2))


if __name__ == "__main__":
    main()
