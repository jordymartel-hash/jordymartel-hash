"""Builds assets/snake.svg: the contribution calendar as a neon grid with a
snake that roams the board, eats every contribution cell one by one, grows,
exits right and respawns on the left.

Called by build_stats.py with the real calendar; run directly with --demo to
preview with fake data:

    python scripts/build_snake.py --demo
"""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MONO = "ui-monospace,'JetBrains Mono','SF Mono',Menlo,Consolas,'Liberation Mono',monospace"
C = {"win": "#070b14", "panel": "#0a1120", "line": "#1a2742", "dim": "#5d6b85", "label": "#8a9bb8",
     "cyan": "#00f0ff", "magenta": "#ff2a6d", "green": "#39ff88"}
LEVELS = {
    "NONE": "#0d1526",
    "FIRST_QUARTILE": "#0b4d34",
    "SECOND_QUARTILE": "#0f8a55",
    "THIRD_QUARTILE": "#22d07a",
    "FOURTH_QUARTILE": "#39ff88",
}
CELL, GAP = 13, 3
STEP = CELL + GAP
STEP_SECONDS = 0.22
BASE_LEN, MAX_LEN = 4, 12


def mix(a, b, t):
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(pa, pb))


def plan(cols, targets):
    """Greedy nearest-food walk on the grid. Returns positions and the step
    index at which each target is eaten."""
    pos = (-BASE_LEN, 3)
    path = [pos]
    eaten = {}
    left = set(targets)

    def walk(to):
        nonlocal pos
        while pos != to:
            dx, dy = to[0] - pos[0], to[1] - pos[1]
            # move along the longer axis first: gives a natural staircase
            if abs(dx) >= abs(dy):
                pos = (pos[0] + (1 if dx > 0 else -1), pos[1])
            else:
                pos = (pos[0], pos[1] + (1 if dy > 0 else -1))
            path.append(pos)

    while left:
        nxt = min(left, key=lambda c: (abs(c[0] - pos[0]) + abs(c[1] - pos[1]), c))
        walk(nxt)
        eaten[nxt] = len(path) - 1
        left.remove(nxt)
    # leave the board to the right, then sneak back under it (outside the clip)
    walk((cols + MAX_LEN, pos[1]))
    for p in [(cols + MAX_LEN, 9), (-BASE_LEN - MAX_LEN, 9), (-BASE_LEN - MAX_LEN, 3)]:
        path.append(p)
    pos = path[-1]
    walk((-BASE_LEN, 3))
    return path, eaten


def build(weeks, total, out=ROOT / "assets" / "snake.svg"):
    """weeks: list of lists of {date, weekday, level, count}."""
    cols = len(weeks)
    W = 1000
    gx = (W - cols * STEP) / 2 + 16
    gy = 84
    H = gy + 7 * STEP + 58

    cells, targets = {}, []
    for c, week in enumerate(weeks):
        for d in week:
            r = d["weekday"]
            cells[(c, r)] = d
            if d["count"] > 0:
                targets.append((c, r))

    path, eaten = plan(cols, targets)
    n = len(path)
    dur = n * STEP_SECONDS
    xy = lambda p: f"{gx + p[0] * STEP:.0f} {gy + p[1] * STEP:.0f}"

    grid = []
    for (c, r), d in sorted(cells.items()):
        fill = LEVELS.get(d["level"], LEVELS["NONE"])
        x, y = gx + c * STEP, gy + r * STEP
        anim = ""
        if (c, r) in eaten:
            t = eaten[(c, r)] / n
            anim = (f'<animate attributeName="fill" dur="{dur:.2f}s" repeatCount="indefinite" calcMode="discrete" '
                    f'keyTimes="0;{t:.4f}" values="{fill};{LEVELS["NONE"]}"/>')
        glow = ' filter="url(#cg)"' if d["level"] == "FOURTH_QUARTILE" else ""
        grid.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{CELL}" height="{CELL}" rx="2.5" fill="{fill}"{glow}>'
                    f'<title>{d["count"]} contributions on {d["date"]}</title>{anim}</rect>')

    eat_steps = sorted(eaten.values())
    HIDDEN = ' opacity="0"'
    snake = []
    length = min(MAX_LEN, BASE_LEN + len(eat_steps))
    for k in reversed(range(length)):
        vals = ";".join(xy(path[max(i - k, 0)]) for i in range(n))
        col = mix(C["magenta"], C["cyan"], k / max(length - 1, 1))
        size = CELL - (k * 0.35 if k else -1)
        off = (CELL - size) / 2
        vis = ""
        if k >= BASE_LEN:
            t = eat_steps[k - BASE_LEN] / n
            vis = (f'<animate attributeName="opacity" dur="{dur:.2f}s" repeatCount="indefinite" calcMode="discrete" '
                   f'keyTimes="0;{t:.4f}" values="0;1"/>')
        snake.append(
            f'<g><rect x="{off:.2f}" y="{off:.2f}" width="{size:.2f}" height="{size:.2f}" rx="{3.5 if k else 4}" fill="{col}"'
            f'{HIDDEN if vis else ""}>{vis}</rect>'
            f'<animateTransform attributeName="transform" type="translate" dur="{dur:.2f}s" repeatCount="indefinite" values="{vals}"/></g>'
        )

    months, last = [], None
    for c, week in enumerate(weeks):
        first = dt.date.fromisoformat(week[0]["date"])
        if first.month != last and c < cols - 1:
            if last is not None or first.day <= 7:
                months.append(f'<text x="{gx + c * STEP:.0f}" y="{gy - 10}" class="m">{first.strftime("%b")}</text>')
            last = first.month
    days = "".join(f'<text x="{gx - 10:.0f}" y="{gy + r * STEP + 10:.0f}" class="m" text-anchor="end">{name}</text>'
                   for r, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")))
    legend_x = gx + cols * STEP - 5 * STEP - 40
    legend = "".join(f'<rect x="{legend_x + 34 + i * STEP:.0f}" y="{H - 34}" width="{CELL - 2}" height="{CELL - 2}" rx="2" fill="{f}"/>'
                     for i, f in enumerate(LEVELS.values()))

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{total} contributions in the last year, eaten by a snake">
<defs>
  <filter id="cg" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <clipPath id="board"><rect x="{gx - 2:.0f}" y="{gy - 2}" width="{cols * STEP + 1}" height="{7 * STEP + 1}"/></clipPath>
  <style>
    text{{font-family:{MONO};}}
    .hd{{font-size:11px;font-weight:700;fill:{C["cyan"]};letter-spacing:1.5px}}
    .meta{{font-size:10.5px;fill:{C["dim"]}}}
    .m{{font-size:10px;fill:{C["label"]}}}
    .run{{font-size:10px;fill:{C["green"]};letter-spacing:1px}}
    .pulse{{animation:pulse 1.6s ease-in-out infinite}}
    @keyframes pulse{{50%{{opacity:.3}}}}
  </style>
</defs>
<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="10" fill="{C["win"]}" stroke="{C["line"]}"/>
<text x="24" y="30" class="hd">CONTRIBUTION.GRID</text>
<text x="{W - 24}" y="30" class="meta" text-anchor="end">{total} contributions // last year</text>
<line x1="24" y1="44" x2="{W - 24}" y2="44" stroke="{C["line"]}"/>
{"".join(months)}{days}
{"".join(grid)}
<g clip-path="url(#board)">{"".join(snake)}</g>
<circle class="pulse" cx="{gx + 3:.0f}" cy="{H - 29}" r="3" fill="{C["green"]}"/>
<text x="{gx + 12:.0f}" y="{H - 25}" class="run">SNAKE.EXE // {len(targets)} TARGETS</text>
<text x="{legend_x:.0f}" y="{H - 25}" class="m">Less</text>{legend}
<text x="{legend_x + 34 + 5 * STEP + 4:.0f}" y="{H - 25}" class="m">More</text>
</svg>
'''
    Path(out).write_text(svg, encoding="utf-8")


def demo_weeks():
    """Fake calendar shaped like the real one (a burst in Aug, a couple in Oct)."""
    end = dt.date(2026, 10, 10)
    start = end - dt.timedelta(days=end.weekday() + 1 + 52 * 7)
    hot = {dt.date(2026, 8, 19): "FIRST_QUARTILE", dt.date(2026, 8, 20): "FOURTH_QUARTILE",
           dt.date(2026, 8, 21): "FOURTH_QUARTILE", dt.date(2026, 8, 22): "FOURTH_QUARTILE",
           dt.date(2026, 10, 9): "FIRST_QUARTILE", dt.date(2026, 10, 10): "FOURTH_QUARTILE",
           dt.date(2026, 3, 4): "SECOND_QUARTILE", dt.date(2026, 5, 13): "THIRD_QUARTILE"}
    weeks, day = [], start
    while day <= end:
        week = []
        for _ in range(7):
            if day <= end:
                lvl = hot.get(day, "NONE")
                week.append({"date": day.isoformat(), "weekday": (day.weekday() + 1) % 7, "level": lvl,
                             "count": 0 if lvl == "NONE" else 5})
            day += dt.timedelta(days=1)
        weeks.append(week)
    return weeks


if __name__ == "__main__" and "--demo" in sys.argv:
    build(demo_weeks(), 58)
    print("snake.svg (demo)")
