"""Builds the animated profile SVGs (assets/hero.svg and assets/signals.svg).

The hero is a fake "profile.sh --live" terminal: a particle cloud on the left
morphs between shapes (portrait -> ring -> </> -> initials) and a SYSTEM.INFO
panel on the right boots up line by line. All data lives in profile.config.json.

Drop a photo at assets/portrait.png (or .jpg) to use your own face as the first
particle shape; otherwise a hooded cyber-operator silhouette is drawn.

    python scripts/build_profile.py
"""
import json
import math
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
CFG = json.loads((ROOT / "profile.config.json").read_text(encoding="utf-8"))

# Particle canvas is drawn at 2x and scaled down in the SVG, so integer
# coordinates still give half-pixel precision.
CW, CH = 600, 480

C = {
    "bg": "#05070d",
    "win": "#070b14",
    "panel": "#0a1120",
    "line": "#1a2742",
    "dim": "#5d6b85",
    "label": "#8a9bb8",
    "text": "#e6f1ff",
    "cyan": "#00f0ff",
    "magenta": "#ff2a6d",
    "yellow": "#fcee0a",
    "green": "#39ff88",
    "red": "#ff3b5c",
}
MONO = "ui-monospace,'JetBrains Mono','SF Mono',Menlo,Consolas,'Liberation Mono',monospace"

rng = np.random.default_rng(1337)


def font(size, bold=True):
    names = (
        ["DejaVuSansMono-Bold.ttf", "LiberationMono-Bold.ttf"]
        if bold
        else ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"]
    )
    for name in names:
        for base in ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/liberation"):
            path = Path(base) / name
            if path.exists():
                return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size)


# ---------------------------------------------------------------- shapes ---

def emphasize_edges(img, fill_weight=0.35):
    """Mix a filled mask with its outline so particles trace crisp contours."""
    edges = img.filter(ImageFilter.GaussianBlur(1.2)).filter(ImageFilter.FIND_EDGES)
    edges = edges.filter(ImageFilter.MaxFilter(3))
    a = np.asarray(img, dtype=float) / 255 * fill_weight
    e = np.asarray(edges, dtype=float) / 255
    return np.clip(a + e * 1.6, 0, 1)


def shape_operator():
    """Hooded netrunner with a glowing visor."""
    img = Image.new("L", (CW, CH), 0)
    d = ImageDraw.Draw(img)
    cx = CW // 2
    # shoulders / hoodie body
    d.polygon([(70, CH), (120, 395), (200, 345), (cx, 330), (400, 345), (480, 395), (530, CH)], fill=120)
    # hood
    d.ellipse([cx - 128, 52, cx + 128, 372], fill=150)
    d.polygon([(cx - 128, 230), (cx - 150, 380), (cx + 150, 380), (cx + 128, 230)], fill=150)
    # face cavity
    d.ellipse([cx - 78, 112, cx + 78, 342], fill=0)
    # visor
    d.rounded_rectangle([cx - 70, 190, cx + 70, 222], radius=14, fill=255)
    d.line([(cx - 60, 206), (cx + 60, 206)], fill=0, width=3)
    # respirator mask
    for i, y in enumerate(range(262, 312, 12)):
        w = 46 - i * 6
        d.rounded_rectangle([cx - w, y, cx + w, y + 6], radius=3, fill=170)
    # hood rim light
    d.arc([cx - 128, 52, cx + 128, 372], 160, 380, fill=255, width=5)
    # hoodie strings + zipper
    d.line([(cx - 40, 345), (cx - 46, 430)], fill=230, width=4)
    d.line([(cx + 40, 345), (cx + 46, 430)], fill=230, width=4)
    d.line([(cx, 350), (cx, CH)], fill=200, width=3)
    # circuit traces on the chest
    for sx in (-1, 1):
        x0 = cx + sx * 70
        d.line([(x0, 400), (x0 + sx * 40, 400), (x0 + sx * 40, 440), (x0 + sx * 110, 440)], fill=255, width=3)
        d.ellipse([x0 + sx * 110 - 6, 434, x0 + sx * 110 + 6, 446], fill=255)
        d.line([(x0 + sx * 20, 470), (x0 + sx * 20, 455), (x0 + sx * 90, 455)], fill=220, width=3)
    arr = emphasize_edges(img, fill_weight=0.45)
    # rim lighting from the left like a monitor glow
    xs = np.linspace(1.15, 0.7, CW)[None, :]
    return np.clip(arr * xs, 0, 1)


def shape_portrait(path):
    img = Image.open(path).convert("L")
    img = ImageOps.fit(img, (CW, CH), centering=(0.5, 0.35))
    img = ImageOps.autocontrast(img, cutoff=2)
    base = np.asarray(img, dtype=float) / 255
    edges = np.asarray(img.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.MaxFilter(3)), dtype=float) / 255
    return np.clip(base ** 1.6 * 0.8 + edges * 1.2, 0, 1)


def shape_ring():
    yy, xx = np.mgrid[0:CH, 0:CW]
    r = np.hypot(xx - CW / 2, yy - CH / 2)
    ring = np.exp(-((r - 150) / 30) ** 2)
    inner = np.exp(-((r - 72) / 5) ** 2) * 0.55
    img = Image.new("L", (CW, CH), 0)
    d = ImageDraw.Draw(img)
    cx, cy = CW // 2, CH // 2
    d.line([(cx - 22, cy), (cx + 22, cy)], fill=255, width=4)
    d.line([(cx, cy - 22), (cx, cy + 22)], fill=255, width=4)
    cross = np.asarray(img, dtype=float) / 255
    return np.clip(ring + inner + cross, 0, 1)


def shape_text(text, size, mono=True):
    img = Image.new("L", (CW, CH), 0)
    d = ImageDraw.Draw(img)
    f = font(size, bold=mono)
    box = d.textbbox((0, 0), text, font=f)
    x = (CW - (box[2] - box[0])) / 2 - box[0]
    y = (CH - (box[3] - box[1])) / 2 - box[1]
    d.text((x, y), text, font=f, fill=255)
    return emphasize_edges(img, fill_weight=0.3)


def sample(prob, n):
    p = prob.ravel() ** 1.3
    p = p / p.sum()
    idx = rng.choice(p.size, size=n, replace=False, p=p)
    ys, xs = np.divmod(idx, CW)
    pts = np.stack([xs, ys], axis=1).astype(float) + rng.uniform(-0.5, 0.5, (n, 2))
    # Order by angle around the centre so particles swirl between shapes
    # instead of crossing the whole canvas at random.
    ang = np.arctan2(pts[:, 1] - CH / 2, pts[:, 0] - CW / 2)
    return np.rint(pts[np.argsort(ang)]).astype(int)


# ------------------------------------------------------------------ hero ---

def morph_layer(m):
    n = m["particles"]
    portrait = next((p for p in (ASSETS / "portrait.png", ASSETS / "portrait.jpg") if p.exists()), None)
    shapes = [
        ("OPERATOR" if portrait is None else "OPERATOR.FACE",
         shape_portrait(portrait) if portrait else shape_operator()),
        ("CORE.RING", shape_ring()),
        ("SOURCE.CODE", shape_text("</>", 250)),
        (f"ID:{m['initials']}", shape_text(m["initials"], 270, mono=False)),
    ]
    pts = [sample(prob, n) for _, prob in shapes]

    hold, move = m["hold_seconds"], m["move_seconds"]
    k = len(shapes)
    total = k * (hold + move)
    frames, times, splines = [], [], []
    for i in range(k):
        t0 = i * (hold + move)
        frames += [i, i]
        times += [t0, t0 + hold]
    frames.append(0)
    times.append(total)
    for j in range(len(frames) - 1):
        splines.append("0 0 1 1" if j % 2 == 0 else ".7 0 .3 1")
    key_times = ";".join(f"{t / total:.4f}" for t in times)
    key_splines = ";".join(splines)

    # Split particles into colour groups; each group is ONE path whose "d"
    # morphs, which keeps the file small and cheap for the browser.
    groups = rng.choice(3, size=n, p=[0.72, 0.2, 0.08])
    colors = [C["cyan"], C["magenta"], C["text"]]
    out = []
    for g, col in enumerate(colors):
        sel = np.where(groups == g)[0]
        ds = ["".join(f"M{x} {y}h0" for x, y in pts[f][sel]) for f in frames]
        out.append(
            f'<path d="{ds[0]}" stroke="{col}" stroke-width="2.6" stroke-linecap="round" fill="none">'
            f'<animate attributeName="d" dur="{total}s" repeatCount="indefinite" calcMode="spline" '
            f'keyTimes="{key_times}" keySplines="{key_splines}" values="{";".join(ds)}"/></path>'
        )

    labels = []
    for i, (name, _) in enumerate(shapes):
        a = i * (hold + move) / total
        b = (i * (hold + move) + hold + move) / total
        vals, kts = ("1;0;0", f"0;{b:.4f};1") if i == 0 else ("0;1;0;0", f"0;{a:.4f};{b:.4f};1")
        labels.append(
            f'<text opacity="{1 if i == 0 else 0}">{escape(name)}'
            f'<animate attributeName="opacity" dur="{total}s" repeatCount="indefinite" calcMode="discrete" '
            f'keyTimes="{kts}" values="{vals}"/></text>'
        )
    return "".join(out), "".join(labels), n


def build_hero():
    W, H = 1000, 440
    particles, mode_labels, n = morph_layer(CFG["morph"])
    info = CFG["info"]
    user = CFG["username"]

    # left panel geometry
    lx, ly, lw, lh = 30, 58, 380, 356
    bx, by, bw, bh = lx + 14, ly + 36, lw - 28, lh - 76
    vx, vy = bx + (bw - CW / 2) / 2, by + (bh - CH / 2) / 2
    # right panel geometry
    rx, ry, rw, rh = 426, 58, 544, 356

    rows = []
    step = (rh - 100) / max(len(info) - 1, 1)
    for i, (k, v) in enumerate(info):
        y = ry + 50 + i * step
        delay = 0.35 + i * 0.12
        rows.append(
            f'<g class="row" style="animation-delay:{delay:.2f}s">'
            f'<text x="{rx + 16}" y="{y:.1f}" class="lbl">{escape(k)}</text>'
            f'<text x="{rx + rw - 16}" y="{y:.1f}" class="val" text-anchor="end">{escape(v)}</text></g>'
        )

    user_pill_w = 16 + len(user) * 7.2
    corner = lambda x, y, dx, dy: f'<path d="M{x} {y + dy}V{y}H{x + dx}" />'

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="profile.sh live terminal for {escape(user)}">
<defs>
  <linearGradient id="winbg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0a1020"/><stop offset="1" stop-color="{C["win"]}"/></linearGradient>
  <radialGradient id="vglow" cx=".5" cy=".5" r=".6"><stop offset="0" stop-color="{C["cyan"]}" stop-opacity=".10"/><stop offset="1" stop-color="{C["cyan"]}" stop-opacity="0"/></radialGradient>
  <pattern id="grid" width="16" height="16" patternUnits="userSpaceOnUse"><path d="M16 0H0V16" fill="none" stroke="{C["line"]}" stroke-width=".6" opacity=".55"/></pattern>
  <pattern id="scan" width="3" height="3" patternUnits="userSpaceOnUse"><rect width="3" height="1" fill="#000" opacity=".22"/></pattern>
  <filter id="glow" x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="1.6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <clipPath id="vclip"><rect x="{bx}" y="{by}" width="{bw}" height="{bh}"/></clipPath>
  <style>
    text{{font-family:{MONO};}}
    .ttl{{font-size:11px;fill:{C["dim"]};letter-spacing:.5px}}
    .hd{{font-size:11px;font-weight:700;fill:{C["cyan"]};letter-spacing:1.5px}}
    .meta{{font-size:9.5px;fill:{C["dim"]};letter-spacing:.8px}}
    .lbl{{font-size:11.5px;fill:{C["label"]}}}
    .val{{font-size:11.5px;fill:{C["text"]};font-weight:600}}
    .mode text{{font-size:9.5px;fill:{C["magenta"]};letter-spacing:1px}}
    .row{{opacity:0;animation:boot .45s ease-out forwards}}
    .live{{animation:blink 1.1s steps(1) infinite}}
    .pulse{{animation:pulse 2s ease-in-out infinite}}
    .sweep{{animation:sweep 4.5s linear infinite}}
    .glitch{{animation:glitch 6s steps(1) infinite}}
    .cur{{animation:blink 1s steps(1) infinite}}
    @keyframes boot{{0%{{opacity:0;transform:translateX(-6px)}}60%{{opacity:1}}70%{{opacity:.4}}100%{{opacity:1;transform:none}}}}
    @keyframes blink{{50%{{opacity:.15}}}}
    @keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.35}}}}
    @keyframes sweep{{from{{transform:translateY(0)}}to{{transform:translateY({bh}px)}}}}
    @keyframes glitch{{0%,93%,100%{{transform:none}}94%{{transform:translate(3px,-1px)}}96%{{transform:translate(-4px,1px)}}98%{{transform:translate(2px,0)}}}}
  </style>
</defs>

<rect width="{W}" height="{H}" fill="{C["bg"]}"/>
<g class="glitch">
<rect x="10" y="10" width="{W - 20}" height="{H - 20}" rx="12" fill="url(#winbg)" stroke="{C["line"]}"/>
<rect x="10.5" y="10.5" width="{W - 21}" height="{H - 21}" rx="12" fill="none" stroke="{C["cyan"]}" stroke-opacity=".18"/>

<!-- title bar -->
<circle cx="32" cy="29" r="5.5" fill="#ff5f57"/><circle cx="50" cy="29" r="5.5" fill="#febc2e"/><circle cx="68" cy="29" r="5.5" fill="#28c840"/>
<text x="{W / 2}" y="33" class="ttl" text-anchor="middle">{escape(CFG["window_title"])}</text>
<line x1="10" y1="46" x2="{W - 10}" y2="46" stroke="{C["line"]}"/>

<!-- VISUAL.MAP -->
<rect x="{lx}" y="{ly}" width="{lw}" height="{lh}" rx="6" fill="{C["panel"]}" stroke="{C["line"]}"/>
<text x="{lx + 14}" y="{ly + 21}" class="hd">VISUAL.MAP</text>
<text x="{lx + lw - 14}" y="{ly + 21}" class="meta" text-anchor="end">300×240 / 1-BIT</text>
<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" fill="url(#grid)"/>
<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" fill="url(#vglow)"/>
<g stroke="{C["dim"]}" stroke-width="1.2" fill="none">
  {corner(bx, by, 12, 12)}{corner(bx + bw, by, -12, 12)}{corner(bx, by + bh, 12, -12)}{corner(bx + bw, by + bh, -12, -12)}
</g>
<g clip-path="url(#vclip)">
  <g transform="translate({vx:.1f} {vy:.1f}) scale(.5)">{particles}</g>
  <rect class="sweep" x="{bx}" y="{by - 2}" width="{bw}" height="2" fill="{C["cyan"]}" opacity=".25"/>
</g>
<text x="{lx + 14}" y="{ly + lh - 14}" class="meta">PTS {n} · FX/MORPH</text>
<g class="mode" transform="translate({lx + lw - 14} {ly + lh - 14})" text-anchor="end">{mode_labels}</g>

<!-- SYSTEM.INFO -->
<rect x="{rx}" y="{ry}" width="{rw}" height="{rh}" rx="6" fill="{C["panel"]}" stroke="{C["line"]}"/>
<text x="{rx + 16}" y="{ry + 21}" class="hd">SYSTEM.INFO</text>
<g transform="translate({rx + rw - 16 - user_pill_w - 62} {ry + 9})">
  <rect width="54" height="17" rx="8.5" fill="{C["red"]}" fill-opacity=".14" stroke="{C["red"]}" stroke-opacity=".5"/>
  <circle class="live" cx="12" cy="8.5" r="3.2" fill="{C["red"]}"/>
  <text x="21" y="12.5" style="font-size:9.5px;font-weight:700;fill:{C["red"]}">LIVE</text>
</g>
<g transform="translate({rx + rw - 16 - user_pill_w} {ry + 9})">
  <rect width="{user_pill_w}" height="17" rx="8.5" fill="{C["green"]}" fill-opacity=".14" stroke="{C["green"]}" stroke-opacity=".5"/>
  <text x="{user_pill_w / 2}" y="12.5" text-anchor="middle" style="font-size:9.5px;font-weight:700;fill:{C["green"]}">@{escape(user)}</text>
</g>
<line x1="{rx + 16}" y1="{ry + 32}" x2="{rx + rw - 16}" y2="{ry + 32}" stroke="{C["line"]}"/>
{"".join(rows)}
<line x1="{rx + 16}" y1="{ry + rh - 30}" x2="{rx + rw - 16}" y2="{ry + rh - 30}" stroke="{C["line"]}"/>
<circle class="pulse" cx="{rx + 20}" cy="{ry + rh - 17.5}" r="3" fill="{C["green"]}"/>
<text x="{rx + 29}" y="{ry + rh - 14}" class="meta" style="fill:{C["green"]}">ALL SYSTEMS NORMAL<tspan class="cur">_</tspan></text>
<text x="{rx + rw - 16}" y="{ry + rh - 14}" class="meta" text-anchor="end">{escape(CFG["node"])}</text>
</g>
<rect width="{W}" height="{H}" fill="url(#scan)" pointer-events="none"/>
</svg>
'''
    (ASSETS / "hero.svg").write_text(svg, encoding="utf-8")


# --------------------------------------------------------------- signals ---

def radar(cx, cy, radius, axes, title, subtitle, delay):
    n = len(axes)
    angle = lambda i: -math.pi / 2 + i * 2 * math.pi / n
    pt = lambda i, r: (cx + r * math.cos(angle(i)), cy + r * math.sin(angle(i)))
    poly = lambda pts: " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)

    DASH = 'stroke-dasharray="3 4"'
    rings = "".join(
        f'<polygon points="{poly([pt(i, radius * f) for i in range(n)])}" fill="none" stroke="{C["line"]}" '
        f'{DASH if f < 1 else ""}/>'
        for f in (0.25, 0.5, 0.75, 1)
    )
    spokes = "".join(
        f'<line x1="{cx}" y1="{cy}" x2="{pt(i, radius)[0]:.1f}" y2="{pt(i, radius)[1]:.1f}" stroke="{C["line"]}"/>'
        for i in range(n)
    )
    vals = [pt(i, radius * v / 100) for i, (_, v) in enumerate(axes)]
    labels = []
    for i, (name, v) in enumerate(axes):
        x, y = pt(i, radius + 22)
        c = math.cos(angle(i))
        anchor = "middle" if abs(c) < 0.3 else ("start" if c > 0 else "end")
        labels.append(
            f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" class="ax">{escape(name)}'
            f'<tspan x="{x:.1f}" dy="12" class="axv">{v}</tspan></text>'
        )
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{C["cyan"]}"/>' for x, y in vals)
    return f'''
<text x="{cx}" y="{cy - radius - 58}" text-anchor="middle" class="rt">{escape(title)}</text>
<text x="{cx}" y="{cy - radius - 44}" text-anchor="middle" class="rs">{escape(subtitle)}</text>
{rings}{spokes}
<g class="grow" style="transform-origin:{cx}px {cy}px;animation-delay:{delay}s">
  <polygon points="{poly(vals)}" fill="{C["magenta"]}" fill-opacity=".28" stroke="{C["cyan"]}" stroke-width="2" filter="url(#sg)" class="breathe"/>
  {dots}
</g>
{"".join(labels)}'''


def build_signals():
    W, H = 1000, 400
    r1, r2 = CFG["radars"]
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="skill radar charts">
<defs>
  <filter id="sg" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <style>
    text{{font-family:{MONO};}}
    .rt{{font-size:12px;font-weight:700;fill:{C["cyan"]};letter-spacing:1.5px}}
    .rs{{font-size:10px;fill:{C["dim"]}}}
    .ax{{font-size:10.5px;fill:{C["label"]}}}
    .axv{{font-size:9.5px;fill:{C["magenta"]};font-weight:700}}
    .grow{{transform:scale(0);animation:grow 1.1s cubic-bezier(.2,.9,.3,1.2) forwards}}
    .breathe{{animation:breathe 3s ease-in-out infinite}}
    @keyframes grow{{to{{transform:scale(1)}}}}
    @keyframes breathe{{0%,100%{{fill-opacity:.22}}50%{{fill-opacity:.4}}}}
  </style>
</defs>
<rect width="{W}" height="{H}" rx="10" fill="{C["win"]}" stroke="{C["line"]}"/>
<line x1="{W / 2}" y1="20" x2="{W / 2}" y2="{H - 20}" stroke="{C["line"]}"/>
{radar(250, 225, 115, r1["axes"], r1["title"], r1["subtitle"], 0.2)}
{radar(750, 225, 115, r2["axes"], r2["title"], r2["subtitle"], 0.5)}
</svg>
'''
    (ASSETS / "signals.svg").write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    ASSETS.mkdir(exist_ok=True)
    build_hero()
    build_signals()
    for name in ("hero.svg", "signals.svg"):
        print(f"{name}: {(ASSETS / name).stat().st_size / 1024:.0f} KB")
