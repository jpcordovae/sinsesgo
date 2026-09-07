from __future__ import annotations

import html
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from laverdad.catalog import BUCKET_LABELS, LEAN_LABELS, ROOT, load_catalog
from laverdad.cluster import enrich_stories

OUT_DIR = ROOT / "data" / "out"
PUBLIC_DIR = ROOT / "public"
SITE_NAME = "Sin Sesgo"
SITE_URL = "https://sinsesgo.stellaris.cl"
CONTACT_EMAIL = "jpcordovae@gmail.com"

OWNER_LABELS = {
    "edwards": "Edwards",
    "copesa": "Copesa",
    "claro": "Claro",
    "estado": "Estado",
    "luksic": "Luksic",
    "bethia": "Bethia",
    "carey": "Carey",
    "vytal": "Vytal",
    "independiente": "Independiente",
    "iglesia": "Iglesia",
    "otro": "Otro",
}

OWNER_COLORS = {
    "edwards": "#6B5344",
    "copesa": "#3D4F7C",
    "claro": "#8A6A1A",
    "estado": "#4A5568",
    "luksic": "#5C3D6E",
    "bethia": "#7A4A3A",
    "carey": "#2F5F7A",
    "vytal": "#5A6B3A",
    "independiente": "#2F6F4E",
    "iglesia": "#5A4A6A",
    "otro": "#6B6B6B",
}

LEAN_COLORS = {
    "left": "#C45C4A",
    "center": "#8A8680",
    "right": "#3D6A9A",
}

REGION_LABELS = {
    "nacional": "Nacional",
    "valparaiso": "Valparaíso",
    "biobio": "Biobío",
    "antofagasta": "Antofagasta",
    "ohiggins": "O'Higgins",
    "magallanes": "Magallanes",
    "araucania": "Araucanía",
    "nuble": "Ñuble",
    "atacama": "Atacama",
    "loslagos": "Los Lagos",
    "losrios": "Los Ríos",
    "metropolitana": "RM",
}


def write_outputs(
    *,
    catalog: dict[str, Any],
    ingest: dict[str, Any],
    stories: list[dict[str, Any]],
    out_dir: Path | None = None,
) -> dict[str, Path]:
    stories = enrich_stories(stories, catalog)
    payload = _payload(catalog, ingest.get("feed_status") or [], ingest.get("articles") or [], stories)
    return _write(payload, out_dir or OUT_DIR)


def render_from_json(json_path: Path | None = None, out_dir: Path | None = None) -> dict[str, Path]:
    source = json_path or (OUT_DIR / "clusters.json")
    raw = json.loads(source.read_text(encoding="utf-8"))
    catalog = load_catalog()
    stories = enrich_stories(raw.get("stories") or [], catalog)
    payload = _payload(catalog, raw.get("feed_status") or [], [], stories)
    payload["generated_at"] = raw.get("generated_at") or payload["generated_at"]
    payload["article_count"] = raw.get("article_count") or payload["article_count"]
    return _write(payload, out_dir or OUT_DIR)


def _payload(
    catalog: dict[str, Any],
    feed_status: list[dict[str, Any]],
    articles: list[dict[str, Any]],
    stories: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "country": catalog.get("country"),
        "feed_status": feed_status,
        "article_count": len(articles) or sum(s.get("article_count") or 0 for s in stories),
        "story_count": len(stories),
        "multi_source_count": sum(1 for story in stories if story["source_count"] >= 2),
        "blindspot_count": sum(1 for story in stories if story.get("blindspot")),
        "local_count": sum(1 for story in stories if story.get("is_local")),
        "outlets": [
            {
                "id": row["id"],
                "name": row["name"],
                "owner": row.get("owner"),
                "ownership": row.get("ownership"),
                "lean": row.get("lean"),
                "region": row.get("region"),
                "mvp": bool(row.get("mvp")),
            }
            for row in catalog["outlets"]
        ],
        "stories": stories,
    }


def _write(payload: dict[str, Any], target: Path) -> dict[str, Path]:
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "clusters.json"
    html_path = target / "index.html"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(render_home(payload), encoding="utf-8")
    aviso_path = target / "aviso.html"
    aviso_path.write_text(render_aviso(), encoding="utf-8")
    (target / "clusters.html").write_text(html_path.read_text(encoding="utf-8"), encoding="utf-8")
    _sync_public(json_path, html_path, aviso_path)
    return {"json": json_path, "html": html_path, "aviso": aviso_path}


def _sync_public(json_path: Path, html_path: Path, aviso_path: Path | None = None) -> None:
    """Copia el snapshot estático que Netlify publica (public/)."""
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(html_path, PUBLIC_DIR / "index.html")
    shutil.copyfile(json_path, PUBLIC_DIR / "clusters.json")
    if aviso_path and aviso_path.exists():
        shutil.copyfile(aviso_path, PUBLIC_DIR / "aviso.html")
    (PUBLIC_DIR / "robots.txt").write_text(
        "User-agent: *\nAllow: /\nSitemap: https://sinsesgo.stellaris.cl/\n",
        encoding="utf-8",
    )


def _analytics_snippet() -> str:
    """GA4 opcional: pega G-XXXXXXXX en el secret GA_MEASUREMENT_ID. No inventar un ID."""
    measurement_id = (os.environ.get("GA_MEASUREMENT_ID") or "").strip()
    if not measurement_id.startswith("G-") or len(measurement_id) < 4:
        return ""
    mid = html.escape(measurement_id)
    return (
        f'<script async src="https://www.googletagmanager.com/gtag/js?id={mid}"></script>\n'
        "  <script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}"
        f"gtag('js',new Date());gtag('config','{mid}');</script>"
    )


def render_home(payload: dict[str, Any]) -> str:
    stories = payload.get("stories") or []
    crossed = [story for story in stories if story.get("source_count", 0) >= 2]
    briefing = crossed[:6]
    rest = crossed[6:]
    blinds = [story for story in stories if story.get("blindspot")]
    locals_ = [story for story in stories if story.get("is_local")]
    failed = [row for row in payload.get("feed_status", []) if not row.get("ok")]
    failed_block = ""
    if failed:
        items = "".join(
            f"<li>{html.escape(row['outlet_id'])}: {html.escape((row.get('error') or '')[:160])}</li>"
            for row in failed
        )
        failed_block = f'<section class="failed"><h2>Feeds que no respondieron</h2><ul>{items}</ul></section>'

    briefing_html = "".join(_story_card(story, badge="Briefing") for story in briefing)
    rest_html = "".join(_story_card(story) for story in rest)
    blind_html = "".join(
        _story_card(story, badge=_blind_label(story.get("blindspot")), with_id=False) for story in blinds
    )
    local_html = "".join(_story_card(story, with_id=False) for story in locals_)
    method_html = _methodology(payload.get("outlets") or [])
    search_index = json.dumps(
        [
            {
                "id": story.get("id"),
                "title": story.get("title"),
                "outlets": [a.get("outlet_name") for a in (story.get("articles") or [])],
                "urls": [a.get("url") for a in (story.get("articles") or [])],
                "sources": story.get("source_count", 0),
                "blindspot": story.get("blindspot"),
                "local": bool(story.get("is_local")),
            }
            for story in stories
        ],
        ensure_ascii=False,
    )
    generated = html.escape(payload.get("generated_at") or "")
    analytics = _analytics_snippet()
    empty_cross = "<p class='empty'>Aún no hay sucesos con dos o más medios. Corre <code>laverdad ingest</code>.</p>"
    empty_blind = "<p class='empty'>No hay puntos ciegos con la fórmula actual (≥2 medios tasados, un lado ≤15% y el otro ≥33%).</p>"
    empty_local = "<p class='empty'>No hay sucesos regionales en esta tanda. El Rancagüino ya está en el MVP; el resto de diarios locales entra cuando haya RSS estable.</p>"

    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sin Sesgo · cobertura en Chile</title>
  <meta name="description" content="Cómo cubren el mismo suceso los medios chilenos. Bias Bar editorial (borrador), propiedad, punto ciego y local. Solo título, bajada y URL.">
  <link rel="canonical" href="{SITE_URL}/">
  {analytics}
  <style>
    :root {{
      --bg: #f4f1ea;
      --ink: #1c1b19;
      --muted: #5c5852;
      --line: #d8d2c6;
      --card: #fffdf8;
      --link: #1f4d6d;
      --left: #C45C4A;
      --center: #8A8680;
      --right: #3D6A9A;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Iowan Old Style", Georgia, serif;
      background: var(--bg);
      color: var(--ink);
    }}
    header, nav, main, .note, .search-wrap {{
      max-width: 920px;
      margin-left: auto;
      margin-right: auto;
    }}
    header {{ padding: 2rem 1.25rem 0.75rem; }}
    header p.brand {{
      font-family: ui-sans-serif, system-ui, sans-serif;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-size: 0.72rem;
      color: var(--muted);
      margin: 0 0 0.6rem;
    }}
    h1 {{ font-size: 2rem; line-height: 1.15; margin: 0 0 0.75rem; font-weight: 600; }}
    .lede {{ font-size: 1.05rem; color: var(--muted); max-width: 42rem; }}
    .stats {{
      font-family: ui-sans-serif, system-ui, sans-serif;
      font-size: 0.8rem;
      color: var(--muted);
      margin-top: 1rem;
    }}
    nav {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.4rem;
      padding: 0 1.25rem 0.75rem;
    }}
    nav button {{
      font-family: ui-sans-serif, system-ui, sans-serif;
      font-size: 0.78rem;
      border: 1px solid var(--line);
      background: var(--card);
      color: var(--ink);
      padding: 0.4rem 0.75rem;
      cursor: pointer;
    }}
    nav button[aria-current="true"] {{
      background: var(--ink);
      color: var(--card);
      border-color: var(--ink);
    }}
    .search-wrap {{ padding: 0 1.25rem 1rem; }}
    .search-wrap input {{
      width: 100%;
      font-family: ui-sans-serif, system-ui, sans-serif;
      font-size: 0.92rem;
      padding: 0.65rem 0.8rem;
      border: 1px solid var(--line);
      background: var(--card);
    }}
    .note {{
      margin-bottom: 1.25rem;
      padding: 0.9rem 1.1rem;
      border: 1px solid var(--line);
      background: var(--card);
      font-family: ui-sans-serif, system-ui, sans-serif;
      font-size: 0.86rem;
      color: var(--muted);
    }}
    main {{ padding: 0 1.25rem 3rem; }}
    .pane {{ display: none; }}
    .pane.active {{ display: block; }}
    article.story {{
      background: var(--card);
      border: 1px solid var(--line);
      padding: 1.2rem 1.25rem 1rem;
      margin-bottom: 1rem;
    }}
    article.story h2 {{ font-size: 1.2rem; margin: 0 0 0.5rem; line-height: 1.3; }}
    .badge {{
      display: inline-block;
      font-family: ui-sans-serif, system-ui, sans-serif;
      font-size: 0.68rem;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      border: 1px solid var(--line);
      padding: 0.15rem 0.4rem;
      margin: 0 0 0.55rem 0;
      color: var(--muted);
    }}
    .bar {{
      display: flex;
      height: 10px;
      background: #e8e2d6;
      overflow: hidden;
      margin: 0.35rem 0 0.45rem;
    }}
    .bar.owner {{ height: 6px; opacity: 0.9; }}
    .bar span {{ display: block; height: 100%; }}
    .legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.55rem 1rem;
      font-family: ui-sans-serif, system-ui, sans-serif;
      font-size: 0.75rem;
      color: var(--muted);
      margin-bottom: 0.55rem;
    }}
    .legend i {{
      display: inline-block;
      width: 8px;
      height: 8px;
      margin-right: 0.3rem;
      vertical-align: middle;
    }}
    .summary {{
      font-size: 0.95rem;
      color: var(--muted);
      margin: 0 0 0.85rem;
    }}
    .compare {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 0.6rem;
      margin: 0 0 0.9rem;
    }}
    .compare section {{
      border: 1px solid var(--line);
      padding: 0.55rem 0.65rem;
      min-height: 4.5rem;
    }}
    .compare h3 {{
      font-family: ui-sans-serif, system-ui, sans-serif;
      font-size: 0.68rem;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      margin: 0 0 0.35rem;
    }}
    .compare .left h3 {{ color: var(--left); }}
    .compare .right h3 {{ color: var(--right); }}
    .compare p {{ margin: 0; font-size: 0.86rem; }}
    .compare a {{ color: var(--ink); text-decoration: none; }}
    .compare a:hover {{ color: var(--link); }}
    .compare .miss {{ color: var(--muted); font-style: italic; }}
    .headlines, .hits {{ list-style: none; padding: 0; margin: 0; }}
    .headlines li, .hits li {{
      padding: 0.5rem 0;
      border-top: 1px solid var(--line);
      font-size: 0.95rem;
    }}
    .headlines a, .hits a {{ color: var(--ink); text-decoration: none; }}
    .headlines a:hover, .hits a:hover {{ color: var(--link); }}
    .source {{
      font-family: ui-sans-serif, system-ui, sans-serif;
      font-size: 0.72rem;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--muted);
      display: block;
      margin-bottom: 0.2rem;
    }}
    details {{
      font-family: ui-sans-serif, system-ui, sans-serif;
      font-size: 0.8rem;
      color: var(--muted);
      margin-top: 0.4rem;
    }}
    details ul {{ padding-left: 1.1rem; }}
    .failed {{
      margin-top: 2rem;
      font-family: ui-sans-serif, system-ui, sans-serif;
      font-size: 0.82rem;
      color: var(--muted);
    }}
    .empty {{ color: var(--muted); }}
    table.method {{
      width: 100%;
      border-collapse: collapse;
      font-family: ui-sans-serif, system-ui, sans-serif;
      font-size: 0.8rem;
    }}
    table.method th, table.method td {{
      text-align: left;
      padding: 0.4rem 0.35rem;
      border-bottom: 1px solid var(--line);
    }}
    .skip {{
      margin: 1rem 0 0;
      padding: 0;
      color: var(--muted);
      font-size: 0.9rem;
    }}
    .hidden {{ display: none !important; }}
    @media (max-width: 700px) {{
      .compare {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <p class="brand">Sin Sesgo · Chile</p>
    <h1>Cómo cubren el mismo suceso</h1>
    <p class="lede">Bias Bar de tendencia editorial (borrador chileno) más barra de propiedad. No es AllSides ni un semáforo de verdad.</p>
    <p class="stats">{payload.get("article_count", 0)} artículos · {len(crossed)} cruzados · {payload.get("blindspot_count", 0)} puntos ciegos · {payload.get("local_count", 0)} locales · {generated}</p>
  </header>
    <nav aria-label="Secciones">
    <button type="button" data-pane="portada" aria-current="true">Portada</button>
    <button type="button" data-pane="ciego">Punto ciego</button>
    <button type="button" data-pane="local">Local</button>
    <button type="button" data-pane="metodo">Metodología</button>
    <button type="button" data-pane="aviso">Aviso</button>
  </nav>
  <div class="search-wrap">
    <input id="q" type="search" placeholder="Buscar suceso o pegar una URL de un medio chileno" autocomplete="off">
  </div>
  <p class="note">La barra L/C/R cuenta medios con lean en el catálogo, no lectores. Independiente no es “neutro”. El cluster decide qué notas son el mismo hecho. Transparencia, no neutralidad.</p>
  <main>
    <section id="pane-search" class="pane">
      <h2 class="source">Resultados</h2>
      <ul id="hits" class="hits"></ul>
      <div id="hit-cards"></div>
    </section>
    <section id="pane-portada" class="pane active">
      <p class="source">Briefing del día · los 6 sucesos con más medios</p>
      {briefing_html or empty_cross}
      {"<p class='source'>Resto de la portada</p>" + rest_html if rest_html else ""}
    </section>
    <section id="pane-ciego" class="pane">
      <p class="source">Lo que casi no cubre un lado · ≥3 medios tasados, un lado ≤15% y el otro ≥33%</p>
      {blind_html or empty_blind}
    </section>
    <section id="pane-local" class="pane">
      <p class="source">Medios regionales del catálogo o sucesos con ancla geográfica chilena</p>
      {local_html or empty_local}
    </section>
    <section id="pane-metodo" class="pane">
      {method_html}
    </section>
    <section id="pane-aviso" class="pane">
      {_aviso_body()}
    </section>
    {failed_block}
  </main>
  <footer class="note">
    <a href="/aviso.html">Aviso legal</a> ·
    Contacto: <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>
  </footer>
  <script>
    const INDEX = {search_index};
    const panes = document.querySelectorAll(".pane");
    const buttons = document.querySelectorAll("nav button");
    const q = document.getElementById("q");
    const hits = document.getElementById("hits");
    const hitCards = document.getElementById("hit-cards");

    function show(id) {{
      panes.forEach((p) => p.classList.toggle("active", p.id === "pane-" + id));
      buttons.forEach((b) => b.setAttribute("aria-current", b.dataset.pane === id ? "true" : "false"));
    }}
    buttons.forEach((b) => b.addEventListener("click", () => {{
      q.value = "";
      show(b.dataset.pane);
    }}));

    q.addEventListener("input", () => {{
      const term = q.value.trim().toLowerCase();
      if (!term) {{
        show("portada");
        hits.innerHTML = "";
        hitCards.innerHTML = "";
        return;
      }}
      show("search");
      const matches = INDEX.filter((row) => {{
        const blob = [row.title, ...(row.outlets || []), ...(row.urls || [])].join(" ").toLowerCase();
        return blob.includes(term);
      }});
      hits.innerHTML = matches.length
        ? matches.slice(0, 40).map((row) => {{
            const extra = row.sources >= 2 ? row.sources + " medios" : "1 medio";
            return "<li data-id='" + row.id + "'><span class='source'>" + extra + "</span><a href='#story-" + row.id + "'>" + escapeHtml(row.title) + "</a></li>";
          }}).join("")
        : "<li class='empty'>Sin coincidencias en esta tanda.</li>";
      hitCards.innerHTML = "";
      matches.filter((row) => row.sources >= 2).slice(0, 12).forEach((row) => {{
        const card = document.getElementById("story-" + row.id);
        if (card) hitCards.appendChild(card.cloneNode(true));
      }});
    }});

    function escapeHtml(value) {{
      return String(value || "").replace(/[&<>"']/g, (ch) => ({{
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }})[ch]);
    }}
  </script>
</body>
</html>
"""


def _blind_label(side: str | None) -> str:
    if side == "left":
        return "Punto ciego de la izquierda"
    if side == "right":
        return "Punto ciego de la derecha"
    return "Punto ciego"


def _mix_bar(mix: dict[str, Any], colors: dict[str, str], labels: dict[str, str], extra_class: str = "") -> tuple[str, str]:
    bar_parts = []
    legend_parts = []
    for key, pct in mix.items():
        if not pct:
            continue
        color = colors.get(key, "#6B6B6B")
        label = labels.get(key, key)
        bar_parts.append(
            f'<span style="width:{pct}%;background:{color}" title="{html.escape(str(label))} {pct}%"></span>'
        )
        legend_parts.append(
            f'<span><i style="background:{color}"></i>{html.escape(str(label))} {pct}%</span>'
        )
    cls = f"bar {extra_class}".strip()
    return f'<div class="{cls}">{"".join(bar_parts)}</div>', "".join(legend_parts)


def _compare_block(story: dict[str, Any]) -> str:
    compare = story.get("compare") or {}
    if not any(compare.get(side) for side in ("left", "center", "right")):
        return ""
    cols = []
    for side in ("left", "center", "right"):
        item = compare.get(side)
        label = BUCKET_LABELS[side]
        if item:
            body = (
                f'<p><span class="source">{html.escape(item.get("outlet_name") or "")}</span>'
                f'<a href="{html.escape(item.get("url") or "")}">{html.escape(item.get("title") or "")}</a></p>'
            )
        else:
            body = '<p class="miss">Sin titular de este lado en el cluster</p>'
        cols.append(f'<section class="{side}"><h3>{label}</h3>{body}</section>')
    return f'<div class="compare">{"".join(cols)}</div>'


def _story_card(story: dict[str, Any], badge: str | None = None, *, with_id: bool = True) -> str:
    lean = story.get("lean_mix") or {}
    owner = story.get("ownership_mix") or {}
    rated = story.get("rated_count") or 0
    lean_bar, lean_legend = _mix_bar(lean, LEAN_COLORS, BUCKET_LABELS)
    owner_bar, owner_legend = _mix_bar(owner, OWNER_COLORS, OWNER_LABELS, "owner")
    lean_block = ""
    if rated:
        lean_block = f"{lean_bar}<div class='legend'>{lean_legend} · {rated} medios con lean</div>"
    owner_block = f"{owner_bar}<div class='legend'>{owner_legend} · {story.get('source_count', 0)} medios</div>"
    summary = story.get("summary") or ""
    summary_html = f"<p class='summary'>{html.escape(summary)}</p>" if summary else ""
    badge_html = f'<p class="badge">{html.escape(badge)}</p>' if badge else ""
    headlines = []
    seen_outlets: set[str] = set()
    for article in story.get("articles") or []:
        oid = article.get("outlet_id")
        if oid in seen_outlets:
            continue
        seen_outlets.add(oid)
        owner_label = OWNER_LABELS.get(article.get("ownership", ""), article.get("ownership", ""))
        lean_label = LEAN_LABELS.get(article.get("lean") or "", "")
        extra = f" · {lean_label}" if lean_label else ""
        headlines.append(
            f"""<li>
              <span class="source">{html.escape(article.get("outlet_name", ""))} · {html.escape(str(owner_label))}{html.escape(extra)}</span>
              <a href="{html.escape(article.get("url", ""))}">{html.escape(article.get("title", ""))}</a>
            </li>"""
        )
    chrono_items = "".join(
        f"<li>{html.escape((row.get('published_at') or '')[:16])} · {html.escape(row.get('outlet_name') or '')}: {html.escape(row.get('title') or '')}</li>"
        for row in story.get("chronology") or []
    )
    chrono = f"<details><summary>Cronología</summary><ul>{chrono_items}</ul></details>" if chrono_items else ""
    sid = html.escape(story.get("id") or "")
    id_attr = f'id="story-{sid}" ' if with_id else ""
    return f"""
    <article class="story" {id_attr}data-id="{sid}">
      {badge_html}
      <h2>{html.escape(story.get("title", ""))}</h2>
      {lean_block}
      {owner_block}
      {summary_html}
      {_compare_block(story)}
      <ul class="headlines">{"".join(headlines)}</ul>
      {chrono}
    </article>
    """


def _methodology(outlets: list[dict[str, Any]]) -> str:
    rows = []
    for row in outlets:
        lean = LEAN_LABELS.get(row.get("lean") or "", "Sin nota")
        owner = OWNER_LABELS.get(row.get("ownership") or "", row.get("ownership") or "")
        region = REGION_LABELS.get(row.get("region") or "", row.get("region") or "")
        rows.append(
            "<tr>"
            f"<td>{html.escape(row.get('name') or '')}</td>"
            f"<td>{html.escape(lean)}</td>"
            f"<td>{html.escape(str(owner))}</td>"
            f"<td>{html.escape(str(region))}</td>"
            "</tr>"
        )
    skip = (
        "<ul class='skip'>"
        "<li>For You / My Feed y My News Bias: piden cuentas y historial de lectura. Fuera del MVP.</li>"
        "<li>Factuality (Ad Fontes / MBFC): no hay licencia ni escala chilena comparable. No se copia.</li>"
        "<li>Extensión de navegador, newsletters y Alternative Media / podcasts: después.</li>"
        "<li>Mapa internacional: el recorte es Chile. Local usa la región del catálogo.</li>"
        "<li>TV entra por news sitemaps (XML de robots.txt), no por YouTube en este piloto.</li>"
        "</ul>"
    )
    return f"""
      <h2>Qué se adaptó de Ground News</h2>
      <p>Portada (Briefing), Bias Bar L/C/R, comparar titulares, Punto ciego, Local (región del medio o ancla geográfica en el titular), búsqueda/URL, cronología y un extracto de bajadas. La barra de propiedad es el equivalente de Vantage/ownership.</p>
      <p>El lean es un <strong>borrador editorial 2026-09-rev2</strong>, no un promedio de AllSides + Ad Fontes + MBFC. Se colapsa a tres cubetas. Los medios sin lean no entran al porcentaje. CIPER y Radio UChile son centro-izquierda; Bío-Bío es centro (no Edwards).</p>
      <p>Punto ciego (Chile): ≥3 medios tasados, un lado ≤15% y el otro ≥33%. Ground News usa umbrales pensados para decenas de fuentes estadounidenses; con 2 medios casi todo sería “ciego”.</p>
      <h3>Catálogo</h3>
      <table class="method">
        <thead><tr><th>Medio</th><th>Tendencia</th><th>Propiedad</th><th>Región</th></tr></thead>
        <tbody>{"".join(rows)}</tbody>
      </table>
      <h3>Qué no se porta todavía</h3>
      {skip}
    """


def _aviso_body() -> str:
    mail = html.escape(CONTACT_EMAIL)
    return f"""
      <h2>Aviso legal</h2>
      <p><strong>Sin Sesgo</strong> es un agregador de cobertura noticiosa sobre Chile. No es un medio que publique reportajes propios ni un semáforo de verdad.</p>
      <p>De cada nota guardamos únicamente <strong>título, bajada (máximo 400 caracteres) y URL</strong>. No almacenamos el cuerpo del artículo, no bypaseamos paywalls y no hacemos clipping de la obra completa. El enlace lleva al sitio original. Eso es lo que permite la Ley 17.336 para un agregador: citar, no reproducir.</p>
      <p>La tendencia izquierda / centro / derecha es un <strong>criterio editorial chileno</strong> del catálogo, no un rating de AllSides, Ad Fontes ni Media Bias/Fact Check. Independiente describe propiedad, no neutralidad.</p>
      <p>Los sitemaps XML que publican los medios para Google (robots.txt) se usan para descubrir URL y titulares. Si hace falta, se lee solo la bajada pública (meta descripción), no el cuerpo de la nota. El cluster compara ese vocabulario.</p>
      <h2>Contacto</h2>
      <p>Para correcciones de catálogo, reclamos de titulares o baja de un enlace: <a href="mailto:{mail}">{mail}</a>.</p>
    """


def render_aviso() -> str:
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Aviso legal · Sin Sesgo</title>
  <style>
    body {{ margin: 0; font-family: "Iowan Old Style", Georgia, serif; background: #f4f1ea; color: #1c1b19; }}
    main {{ max-width: 720px; margin: 0 auto; padding: 2rem 1.25rem 3rem; }}
    a {{ color: #1f4d6d; }}
    p {{ line-height: 1.5; color: #5c5852; }}
    .brand {{ font-family: ui-sans-serif, system-ui, sans-serif; letter-spacing: 0.12em; text-transform: uppercase; font-size: 0.72rem; color: #5c5852; }}
  </style>
</head>
<body>
  <main>
    <p class="brand"><a href="/">Sin Sesgo · Chile</a></p>
    {_aviso_body()}
  </main>
</body>
</html>
"""
