"""Generate an animated SVG of an elephant eating the GitHub contribution graph.

Usage: GITHUB_TOKEN=... python scripts/elephant.py <username> <out_dir>
Writes elephant-dark.svg and elephant-light.svg into out_dir.
"""

import base64
import json
import math
import os
import sys
import urllib.request

CELL, GAP = 11, 3
STEP = CELL + GAP
PAD_X, PAD_TOP, PAD_BOTTOM = 72, 24, 22
SPEED = 140  # px per second
MAX_WALK = 40  # seconds
PAUSE, REGROW = 2.0, 1.0

# Pixel-art elephant (assets/elephant.png) facing left; TIP is the trunk tip in image pixels.
SPRITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "elephant.png")
SPRITE_SIZE = (200, 108)
SPRITE_SCALE = 1 / 3
TIP = (0, 53)

# PHP purple ramps.
THEMES = {
    "dark": {"empty": "#161b22", "levels": ["#3b3f6e", "#5a60a8", "#8a8fd0", "#c3c6ff"]},
    "light": {"empty": "#ebedf0", "levels": ["#d9dbf2", "#b0b4e2", "#8288c6", "#4f5b93"]},
}
LEVELS = {"FIRST_QUARTILE": 0, "SECOND_QUARTILE": 1, "THIRD_QUARTILE": 2, "FOURTH_QUARTILE": 3}

QUERY = """query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks { contributionDays { weekday contributionLevel } }
      }
    }
  }
}"""


def fetch_weeks(login, token):
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as res:
        data = json.load(res)
    return data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]


def cell_center(col, row):
    return PAD_X + col * STEP + CELL / 2, PAD_TOP + row * STEP + CELL / 2


def plan_route(cells, width):
    """Greedy nearest-neighbour walk over the filled cells, entering left and leaving right."""
    todo = [c for c in cells if c["level"] is not None]
    todo.sort(key=lambda c: (c["col"], c["row"]))
    start_y = cell_center(0, todo[0]["row"])[1] if todo else cell_center(0, 3)[1]
    off = SPRITE_SIZE[0] * SPRITE_SCALE + 10
    pos = (-off, start_y)
    route = [(pos, None)]
    while todo:
        nearest = min(todo, key=lambda c: math.dist(pos, cell_center(c["col"], c["row"])))
        todo.remove(nearest)
        pos = cell_center(nearest["col"], nearest["row"])
        route.append((pos, nearest))
    route.append(((width + off, pos[1]), None))
    return route


def pct(t, total):
    return f"{t / total * 100:.4f}%"


def render(cells, theme, sprite):
    width = PAD_X * 2 + 53 * STEP - GAP
    height = PAD_TOP + 7 * STEP - GAP + PAD_BOTTOM
    route = plan_route(cells, width)

    walk = sum(math.dist(a[0], b[0]) for a, b in zip(route, route[1:]))
    scale = min(1.0, MAX_WALK * SPEED / walk) if walk else 1.0
    walk_time = walk / SPEED * scale
    total = walk_time + PAUSE + REGROW
    regrow_at = pct(walk_time + PAUSE, total)

    frames, eaten = [], {}
    t, facing = 0.0, 1
    for i, (pos, cell) in enumerate(route):
        if i:
            prev = route[i - 1][0]
            t += math.dist(prev, pos) / SPEED * scale
        nxt = route[i + 1][0] if i + 1 < len(route) else None
        frames.append((t, pos, facing))
        if nxt and nxt[0] != pos[0]:
            new_facing = -1 if nxt[0] > pos[0] else 1
            if new_facing != facing:
                facing = new_facing
                frames.append((t + 0.01, pos, facing))
        if cell:
            eaten[(cell["col"], cell["row"])] = t
    frames.append((total, route[-1][0], facing))

    css = [
        ".c{transform-box:fill-box;transform-origin:center}",
        ".e{animation:walk %.2fs linear infinite}" % total,
        ".b{animation:bob .32s ease-in-out infinite alternate}",
        "@keyframes bob{to{transform:translateY(-1.6px)}}",
    ]
    walk_kf = "".join(
        "%s{transform:translate(%.1fpx,%.1fpx) scaleX(%d)}" % (pct(ft, total), x, y, f)
        for ft, (x, y), f in frames
    )
    css.append("@keyframes walk{%s}" % walk_kf)

    rects = []
    for c in cells:
        x = PAD_X + c["col"] * STEP
        y = PAD_TOP + c["row"] * STEP
        rects.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" fill="{theme["empty"]}"/>')
        if c["level"] is None:
            continue
        name = f"k{c['col']}_{c['row']}"
        at = eaten[(c["col"], c["row"])]
        gone = pct(at + 0.12, total)
        css.append(
            "@keyframes %s{0%%,%s{transform:scale(1);opacity:1}%s,%s{transform:scale(0);opacity:0}100%%{transform:scale(1);opacity:1}}"
            % (name, pct(at, total), gone, regrow_at)
        )
        rects.append(
            f'<rect class="c" x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" '
            f'fill="{theme["levels"][c["level"]]}" style="animation:{name} {total:.2f}s linear infinite"/>'
        )

    elephant = (
        f'<g class="e"><g class="b"><g transform="scale({SPRITE_SCALE:.4f}) translate({-TIP[0]} {-TIP[1]})">'
        f'<image width="{SPRITE_SIZE[0]}" height="{SPRITE_SIZE[1]}" href="data:image/png;base64,{sprite}"/></g></g></g>'
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">'
        f'<style>{"".join(css)}</style>'
        f'{"".join(rects)}{elephant}</svg>'
    )


def main():
    login, out_dir = sys.argv[1], sys.argv[2]
    weeks = fetch_weeks(login, os.environ["GITHUB_TOKEN"])
    cells = [
        {"col": col, "row": day["weekday"], "level": LEVELS.get(day["contributionLevel"])}
        for col, week in enumerate(weeks)
        for day in week["contributionDays"]
    ]
    with open(SPRITE, "rb") as f:
        sprite = base64.b64encode(f.read()).decode()
    os.makedirs(out_dir, exist_ok=True)
    for name, theme in THEMES.items():
        with open(os.path.join(out_dir, f"elephant-{name}.svg"), "w") as f:
            f.write(render(cells, theme, sprite))


if __name__ == "__main__":
    main()
