"""Builds assets/stats.svg ("Numbers matter? ohhh yes.") from live GitHub data.

Uses the GraphQL API when GITHUB_TOKEN is set (stars, repos, followers,
contributions, streaks, languages); falls back to the public REST API without
contribution data otherwise. Runs daily from .github/workflows/profile.yml.

    GITHUB_TOKEN=... python scripts/build_stats.py
"""
import datetime as dt
import json
import os
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "profile.config.json").read_text(encoding="utf-8"))
USER = os.environ.get("PROFILE_USER") or CFG["username"]
TOKEN = os.environ.get("GITHUB_TOKEN")

MONO = "ui-monospace,'JetBrains Mono','SF Mono',Menlo,Consolas,'Liberation Mono',monospace"
C = {
    "win": "#070b14", "line": "#1a2742", "dim": "#5d6b85", "label": "#8a9bb8",
    "text": "#e6f1ff", "cyan": "#00f0ff", "magenta": "#ff2a6d", "yellow": "#fcee0a",
}
FALLBACK_COLORS = ["#00f0ff", "#ff2a6d", "#fcee0a", "#39ff88", "#b967ff", "#ff8a00", "#5d6b85", "#e6f1ff"]


def request(url, body=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "profile-stats"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=30) as r:
        return json.load(r)


QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    followers { totalCount }
    contributionsCollection {
      contributionCalendar { totalContributions weeks { contributionDays { date weekday contributionCount contributionLevel } } }
    }
    repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100, after: $cursor) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } }
      }
    }
  }
}"""


def streaks(days):
    counts = [d["contributionCount"] for d in sorted(days, key=lambda d: d["date"])]
    longest = run = 0
    for c in counts:
        run = run + 1 if c else 0
        longest = max(longest, run)
    current = 0
    # today may simply not have commits yet; don't break the streak for it
    tail = counts[:-1] if counts and counts[-1] == 0 else counts
    for c in reversed(tail):
        if not c:
            break
        current += 1
    return current, longest


def fetch_graphql():
    stats = {"stars": 0, "langs": {}, "colors": {}}
    cursor = None
    while True:
        res = request("https://api.github.com/graphql", {"query": QUERY, "variables": {"login": USER, "cursor": cursor}})
        if res.get("errors"):
            raise RuntimeError(res["errors"])
        u = res["data"]["user"]
        repos = u["repositories"]
        for repo in repos["nodes"]:
            stats["stars"] += repo["stargazerCount"]
            for e in repo["languages"]["edges"]:
                name = e["node"]["name"]
                stats["langs"][name] = stats["langs"].get(name, 0) + e["size"]
                stats["colors"][name] = e["node"]["color"]
        if not repos["pageInfo"]["hasNextPage"]:
            break
        cursor = repos["pageInfo"]["endCursor"]
    cal = u["contributionsCollection"]["contributionCalendar"]
    days = [d for w in cal["weeks"] for d in w["contributionDays"]]
    stats["weeks"] = [
        [{"date": d["date"], "weekday": d["weekday"], "count": d["contributionCount"], "level": d["contributionLevel"]}
         for d in w["contributionDays"]]
        for w in cal["weeks"]
    ]
    stats["current"], stats["longest"] = streaks(days)
    stats.update(repos=repos["totalCount"], followers=u["followers"]["totalCount"], contribs=cal["totalContributions"])
    return stats


def fetch_rest():
    u = request(f"https://api.github.com/users/{USER}")
    repos = [r for r in request(f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner") if not r["fork"]]
    langs = {}
    for r in repos:
        for name, size in request(r["languages_url"]).items():
            langs[name] = langs.get(name, 0) + size
    return {
        "stars": sum(r["stargazers_count"] for r in repos), "repos": u["public_repos"], "followers": u["followers"],
        "contribs": None, "current": None, "longest": None, "langs": langs, "colors": {}, "weeks": None,
    }


def fetch_projects():
    """Repo details for the project cards listed in profile.config.json."""
    out = []
    for p in CFG.get("projects", []):
        r = request(f"https://api.github.com/repos/{USER}/{p['repo']}")
        out.append({
            "name": r["name"], "description": r["description"] or p.get("description", ""),
            "language": r["language"], "stars": r["stargazers_count"], "forks": r["forks_count"],
            "tag": p.get("tag", ""),
        })
    return out


def wrap(text, width):
    lines, cur = [], ""
    for word in text.split():
        if len(cur) + len(word) + 1 > width and cur:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        lines.append(cur)
    if len(lines) > 2:
        lines = lines[:2]
        lines[1] = lines[1][: width - 1].rstrip() + "…"
    return lines


LANG_COLORS = {"Python": "#3572A5", "Kotlin": "#A97BFF", "TypeScript": "#3178c6", "JavaScript": "#f1e05a",
               "HTML": "#e34c26", "CSS": "#663399", "Java": "#b07219", "C++": "#f34b7d", "Shell": "#89e051"}


def build_card(p, index):
    W, H = 480, 140
    desc = "".join(f'<text x="22" y="{70 + i * 17}" class="d">{escape(line)}</text>'
                   for i, line in enumerate(wrap(p["description"] or "Sin descripción todavía.", 58)))
    lang = ""
    x = 22
    if p["language"]:
        lang = (f'<circle cx="{x + 5}" cy="{H - 26}" r="5" fill="{LANG_COLORS.get(p["language"], C["cyan"])}"/>'
                f'<text x="{x + 16}" y="{H - 22}" class="f">{escape(p["language"])}</text>')
        x += 30 + len(p["language"]) * 7.5
    meta = (f'<text x="{x}" y="{H - 22}" class="f">★ {p["stars"]}</text>'
            f'<text x="{x + 52}" y="{H - 22}" class="f">⑂ {p["forks"]}</text>')
    tag = (f'<text x="{W - 22}" y="{H - 22}" class="t" text-anchor="end">{escape(p["tag"])}</text>' if p["tag"] else "")
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{escape(p["name"])}">
<defs><style>
  text{{font-family:{MONO};}}
  .n{{font-size:15px;font-weight:800;fill:{C["cyan"]}}}
  .idx{{font-size:10px;fill:{C["magenta"]};letter-spacing:1px}}
  .d{{font-size:11.5px;fill:{C["label"]}}}
  .f{{font-size:11px;fill:{C["label"]}}}
  .t{{font-size:10px;font-weight:700;fill:{C["yellow"]};letter-spacing:1px}}
  .pill{{font-size:9.5px;fill:{C["dim"]}}}
  .scan{{animation:scan 5s linear infinite}}
  @keyframes scan{{from{{transform:translateX(-80px)}}to{{transform:translateX({W + 80}px)}}}}
</style>
<linearGradient id="sg" x1="0" x2="1"><stop offset="0" stop-color="{C["cyan"]}" stop-opacity="0"/><stop offset=".5" stop-color="{C["cyan"]}" stop-opacity=".9"/><stop offset="1" stop-color="{C["cyan"]}" stop-opacity="0"/></linearGradient>
<clipPath id="cc"><rect width="{W}" height="{H}" rx="10"/></clipPath>
</defs>
<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="10" fill="{C["win"]}" stroke="{C["line"]}"/>
<g clip-path="url(#cc)"><rect class="scan" x="0" y="0" width="80" height="2" fill="url(#sg)"/></g>
<path d="M1 18V1H18M{W - 18} 1H{W - 1}V18M1 {H - 18}V{H - 1}H18M{W - 18} {H - 1}H{W - 1}V{H - 18}" fill="none" stroke="{C["cyan"]}" stroke-opacity=".6" stroke-width="1.5"/>
<text x="22" y="26" class="idx">PROJECT_{index:02d}</text>
<text x="22" y="46" class="n">{escape(p["name"])}</text>
<rect x="{W - 72}" y="14" width="52" height="18" rx="9" fill="none" stroke="{C["line"]}"/>
<text x="{W - 46}" y="27" class="pill" text-anchor="middle">Public</text>
{desc}{lang}{meta}{tag}
</svg>
'''
    (ROOT / "assets" / f"project-{p['name']}.svg").write_text(svg, encoding="utf-8")


def human_bytes(n):
    for unit in ("B", "kB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.2f} {unit}"
        n /= 1024


def build(s):
    W = 1000
    fmt = lambda v: "—" if v is None else f"{v:,}"
    cells = [
        (fmt(s["stars"]), "Total stars"), (fmt(s["repos"]), "Public repos"), (fmt(s["followers"]), "Followers"),
        (fmt(s["contribs"]), "Contributions (1y)"), (fmt(s["current"]), "Current streak"), (fmt(s["longest"]), "Longest streak"),
    ]
    grid = []
    for i, (v, label) in enumerate(cells):
        x = 60 + (i % 3) * 300
        y = 104 + (i // 3) * 74
        grid.append(
            f'<g class="pop" style="animation-delay:{0.1 + i * 0.08:.2f}s">'
            f'<text x="{x}" y="{y}" class="num">{escape(v)}</text>'
            f'<text x="{x}" y="{y + 20}" class="cap">{escape(label)}</text></g>'
        )

    langs = sorted(s["langs"].items(), key=lambda kv: -kv[1])
    total = sum(v for _, v in langs) or 1
    top = langs[:8]
    color = {n: s["colors"].get(n) or FALLBACK_COLORS[i % len(FALLBACK_COLORS)] for i, (n, _) in enumerate(langs)}

    bar_x, bar_w, bar_y = 60, W - 120, 296
    segs, x = [], bar_x
    for name, size in langs:
        w = bar_w * size / total
        segs.append(f'<rect x="{x:.2f}" y="{bar_y}" width="{max(w, 0):.2f}" height="10" fill="{color[name]}"/>')
        x += w

    rows = []
    for i, (name, size) in enumerate(top):
        col, row = divmod(i, 4)
        cx = 60 + col * 450
        y = 340 + row * 24
        rows.append(
            f'<circle cx="{cx + 5}" cy="{y - 4}" r="5" fill="{color[name]}"/>'
            f'<text x="{cx + 20}" y="{y}" class="ln">{escape(name)}</text>'
            f'<text x="{cx + 300}" y="{y}" class="lb" text-anchor="end">{human_bytes(size)}</text>'
            f'<text x="{cx + 390}" y="{y}" class="lp" text-anchor="end">{size / total * 100:.2f}%</text>'
        )
    if not top:
        rows.append(f'<text x="{W / 2}" y="350" class="cap" text-anchor="middle">no language data yet — push some code ⚡</text>')

    H = 340 + max(min(len(top), 4), 1) * 24 + 20
    updated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="GitHub stats for {escape(USER)}">
<defs>
  <clipPath id="bar"><rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="10" rx="5"/></clipPath>
  <style>
    text{{font-family:{MONO};}}
    .usr{{font-size:14px;font-weight:700;fill:{C["cyan"]}}}
    .meta{{font-size:10.5px;fill:{C["dim"]}}}
    .num{{font-size:30px;font-weight:800;fill:{C["text"]}}}
    .cap{{font-size:11px;fill:{C["label"]}}}
    .hd{{font-size:13px;font-weight:700;fill:{C["magenta"]}}}
    .sub{{font-size:11px;fill:{C["cyan"]}}}
    .ln{{font-size:12px;fill:{C["text"]}}}
    .lb{{font-size:11px;fill:{C["label"]}}}
    .lp{{font-size:11px;fill:{C["yellow"]};font-weight:700}}
    .pop{{opacity:0;animation:pop .5s ease-out forwards}}
    .fill{{transform:scaleX(0);transform-origin:{bar_x}px 0;animation:fill 1.4s .5s cubic-bezier(.2,.8,.2,1) forwards}}
    @keyframes pop{{from{{opacity:0;transform:translateY(6px)}}to{{opacity:1;transform:none}}}}
    @keyframes fill{{to{{transform:scaleX(1)}}}}
  </style>
</defs>
<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="10" fill="{C["win"]}" stroke="{C["line"]}"/>
<text x="40" y="38" class="usr">{escape(USER)}</text>
<text x="{W - 40}" y="38" class="meta" text-anchor="end">at a glance · updated {updated}</text>
<line x1="40" y1="52" x2="{W - 40}" y2="52" stroke="{C["line"]}"/>
{"".join(grid)}
<line x1="40" y1="216" x2="{W - 40}" y2="216" stroke="{C["line"]}"/>
<text x="40" y="248" class="hd">⌗ {len(langs)} Languages</text>
<text x="{W / 2}" y="278" class="sub" text-anchor="middle">Most used languages</text>
<rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="10" rx="5" fill="{C["line"]}"/>
<g clip-path="url(#bar)"><g class="fill">{"".join(segs)}</g></g>
{"".join(rows)}
</svg>
'''
    (ROOT / "assets" / "stats.svg").write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    import build_snake

    data = fetch_graphql() if TOKEN else fetch_rest()
    build(data)
    if data["weeks"]:
        build_snake.build(data["weeks"], data["contribs"])
    for i, p in enumerate(fetch_projects(), 1):
        build_card(p, i)
    print(json.dumps({k: v for k, v in data.items() if k not in ("langs", "colors", "weeks")}))
