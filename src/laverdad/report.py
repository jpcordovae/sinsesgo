from __future__ import annotations

import html
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from laverdad.catalog import BUCKET_LABELS, LEAN_LABELS, ROOT, load_catalog
from laverdad.cluster import enrich_stories
from laverdad.history import persist_and_digest

SOCIAL_KIND_LABELS = {
    "coordinated": "Ráfaga",
    "trending": "Trending",
    "media": "Medios",
    "none": "Sin señal",
}

SOCIAL_SHORT = {
    "coordinated": "ráfaga",
    "trending": "trending",
    "media": "medios",
}

OUT_DIR = ROOT / "data" / "out"
PUBLIC_DIR = ROOT / "public"
SITE_NAME = "Sin Sesgo"
SITE_URL = "https://sinsesgo.stellaris.cl"
CONTACT_EMAIL = "jpcordovae@gmail.com"
TAGLINE = "El mismo suceso. Distintos medios. Cómo lo cuentan."
SUBLINE = "Cobertura chilena, sesgo y redes — sin el artículo completo."

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

TONE_LABELS = {"neg": "Negativo", "neu": "Neutro", "pos": "Positivo"}
TONE_COLORS = {"neg": "#8A4A42", "neu": "#8A8680", "pos": "#4A6B4A"}

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
    from laverdad.social import attach_social, fetch_trends_cl

    stories = enrich_stories(stories, catalog)
    trends = fetch_trends_cl()
    stories = attach_social(stories, trends)
    payload = _payload(
        catalog,
        ingest.get("feed_status") or [],
        ingest.get("articles") or [],
        stories,
        trends=trends,
    )
    return _write(payload, out_dir or OUT_DIR)


def render_from_json(json_path: Path | None = None, out_dir: Path | None = None) -> dict[str, Path]:
    source = json_path or (OUT_DIR / "clusters.json")
    raw = json.loads(source.read_text(encoding="utf-8"))
    catalog = load_catalog()
    from laverdad.social import attach_social, fetch_trends_cl

    stories = enrich_stories(raw.get("stories") or [], catalog)
    trends = fetch_trends_cl()
    stories = attach_social(stories, trends)
    payload = _payload(catalog, raw.get("feed_status") or [], [], stories, trends=trends)
    payload["generated_at"] = raw.get("generated_at") or payload["generated_at"]
    payload["article_count"] = raw.get("article_count") or payload["article_count"]
    return _write(payload, out_dir or OUT_DIR)


def _payload(
    catalog: dict[str, Any],
    feed_status: list[dict[str, Any]],
    articles: list[dict[str, Any]],
    stories: list[dict[str, Any]],
    trends: list[dict[str, Any]] | None = None,
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
        "trends": list(trends or []),
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
    weekly, history_path = persist_and_digest(payload, target)
    json_path = target / "clusters.json"
    html_path = target / "index.html"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(render_home(payload, weekly), encoding="utf-8")
    aviso_path = target / "aviso.html"
    aviso_path.write_text(render_aviso(), encoding="utf-8")
    (target / "clusters.html").write_text(html_path.read_text(encoding="utf-8"), encoding="utf-8")
    _sync_public(json_path, html_path, aviso_path, history_path)
    return {"json": json_path, "html": html_path, "aviso": aviso_path, "history": history_path}


def _sync_public(
    json_path: Path,
    html_path: Path,
    aviso_path: Path | None = None,
    history_path: Path | None = None,
) -> None:
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(html_path, PUBLIC_DIR / "index.html")
    shutil.copyfile(json_path, PUBLIC_DIR / "clusters.json")
    if aviso_path and aviso_path.exists():
        shutil.copyfile(aviso_path, PUBLIC_DIR / "aviso.html")
    if history_path and history_path.exists():
        shutil.copyfile(history_path, PUBLIC_DIR / "history.json")
    (PUBLIC_DIR / "robots.txt").write_text(
        "User-agent: *\nAllow: /\nSitemap: https://sinsesgo.stellaris.cl/\n",
        encoding="utf-8",
    )


def _analytics_snippet() -> str:
    measurement_id = (os.environ.get("GA_MEASUREMENT_ID") or "").strip()
    if not measurement_id.startswith("G-") or len(measurement_id) < 4:
        return ""
    mid = html.escape(measurement_id)
    return (
        f'<script async src="https://www.googletagmanager.com/gtag/js?id={mid}"></script>\n'
        "  <script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}"
        f"gtag('js',new Date());gtag('config','{mid}');</script>"
    )


def _signaled_count(stories: list[dict[str, Any]]) -> int:
    return sum(1 for story in stories if (story.get("social") or {}).get("kind") not in (None, "none"))


def _lean_kicker(story: dict[str, Any]) -> str:
    mix = story.get("lean_mix") or {}
    left, center, right = mix.get("left") or 0, mix.get("center") or 0, mix.get("right") or 0
    if not story.get("rated_count"):
        return "sin lean"
    sides = [(name, pct) for name, pct in (("izq.", left), ("centro", center), ("der.", right)) if pct >= 15]
    top_name, top_pct = max((("izq.", left), ("centro", center), ("der.", right)), key=lambda item: item[1])
    if top_pct >= 70:
        return f"inclinado {top_name}"
    if len(sides) >= 3:
        return "lean mixto"
    if len(sides) == 2:
        return "lean " + "/".join(name for name, _ in sides)
    return f"solo {top_name}"


def _owner_kicker(story: dict[str, Any]) -> str:
    mix = story.get("ownership_mix") or {}
    if not mix:
        return "—"
    items = sorted(mix.items(), key=lambda kv: -kv[1])
    if items[0][1] >= 50:
        return OWNER_LABELS.get(items[0][0], items[0][0])
    return "mixto"


def _tone_kicker(mix: dict[str, Any] | None) -> str:
    if not mix:
        return "—"
    key = max(mix, key=lambda name: mix.get(name) or 0)
    return TONE_LABELS.get(key, "—")


def _copy_kicker(score: float | None) -> str:
    if score is None:
        return "—"
    label = "homogéneo" if score >= 0.5 else "parecido" if score >= 0.25 else "distinto"
    return f"{score:.2f} · {label}"


def _social_kicker(story: dict[str, Any]) -> str | None:
    kind = (story.get("social") or {}).get("kind") or "none"
    return SOCIAL_SHORT.get(kind)


def _meta_line(story: dict[str, Any]) -> str:
    parts = [f"{story.get('source_count', 0)} medios", _lean_kicker(story)]
    social = _social_kicker(story)
    if social:
        parts.append(social)
    if story.get("blindspot"):
        parts.append("ciego " + ("izq." if story["blindspot"] == "left" else "der."))
    return " · ".join(parts)


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


def _lean_legend(story: dict[str, Any]) -> str:
    mix = story.get("lean_mix") or {}
    bits = []
    for key, letter in (("left", "L"), ("center", "C"), ("right", "R")):
        bits.append(f'<b class="{key}">{letter}</b> {mix.get(key) or 0}%')
    rated = story.get("rated_count") or 0
    extra = f" · {rated} tasados" if rated else ""
    return f'<p class="lean-n">{"".join(bits)}{extra}</p>'


def _compare_block(story: dict[str, Any]) -> str:
    compare = story.get("compare") or {}
    if not any(compare.get(side) for side in ("left", "center", "right")):
        return ""
    cols = []
    for side, short in (("left", "Izq."), ("center", "Centro"), ("right", "Der.")):
        item = compare.get(side)
        if item:
            body = (
                f'<p><span class="source">{html.escape(item.get("outlet_name") or "")}</span>'
                f'<a href="{html.escape(item.get("url") or "")}">{html.escape(item.get("title") or "")}</a></p>'
            )
        else:
            body = '<p class="miss">Sin titular</p>'
        cols.append(f'<section class="{side}"><h3>{short}</h3>{body}</section>')
    return f'<div class="compare">{"".join(cols)}</div>'


def _ficha(story: dict[str, Any], *, with_id: bool = True, compact: bool = False) -> str:
    lean = story.get("lean_mix") or {}
    owner = story.get("ownership_mix") or {}
    lean_bar, _ = _mix_bar(lean, LEAN_COLORS, BUCKET_LABELS)
    owner_bar, _ = _mix_bar(owner, OWNER_COLORS, OWNER_LABELS, "owner")
    social = story.get("social") or {}
    copy = social.get("copy_score")
    trends_url = social.get("trends_url") or ""
    trend_q = ((social.get("trend") or {}).get("query") or "").strip()
    trends_cell = (
        f'<a href="{html.escape(trends_url)}" target="_blank" rel="noopener">'
        f'{html.escape(trend_q or "Trends CL")}</a>'
        if trends_url
        else "—"
    )
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
        f"<li>{html.escape((row.get('published_at') or '')[:16])} · {html.escape(row.get('outlet_name') or '')}</li>"
        for row in (story.get("chronology") or [])[:6]
    )
    chrono = f"<p class='chrono'>{chrono_items}</p>" if chrono_items else ""
    extra = ""
    if not compact:
        extra = (
            f"{_compare_block(story)}"
            f"<details class='more'><summary>Titulares</summary>"
            f"<ul class='headlines'>{''.join(headlines)}</ul>{chrono}</details>"
        )
    title = (story.get("title") or "").strip()
    if len(title) > 160:
        title = title[:157].rstrip() + "…"
    sid = html.escape(story.get("id") or "")
    id_attr = f'id="story-{sid}" ' if with_id else ""
    copy_label = (
        "—"
        if (story.get("source_count") or 0) < 2
        else _copy_kicker(copy)
    )
    return f"""
    <article class="ficha" {id_attr}data-id="{sid}">
      <p class="kicker">{html.escape(_meta_line(story))}</p>
      <h2>{html.escape(title)}</h2>
      {lean_bar}
      {_lean_legend(story)}
      {owner_bar}
      <dl class='facts'>
        <div><dt>Tono</dt><dd>{html.escape(_tone_kicker(story.get('tone_mix')))}</dd></div>
        <div><dt>Copia</dt><dd>{html.escape(copy_label)}</dd></div>
        <div><dt>Propiedad</dt><dd>{html.escape(_owner_kicker(story))}</dd></div>
        <div><dt>Redes</dt><dd>{html.escape(SOCIAL_KIND_LABELS.get(social.get('kind') or 'none', 'Sin señal'))}</dd></div>
        <div class='fact-trend'><dt>Trends</dt><dd>{trends_cell}</dd></div>
      </dl>
      {extra}
    </article>
    """


def _orphan_trends(payload: dict[str, Any]) -> list[dict[str, Any]]:
    matched: set[str] = set()
    for story in payload.get("stories") or []:
        query = ((story.get("social") or {}).get("trend") or {}).get("query") or ""
        if query:
            matched.add(query.casefold())
    return [trend for trend in (payload.get("trends") or []) if (trend.get("query") or "").casefold() not in matched]


def _paste_box() -> str:
    return """
      <div class="paste-box" id="paste">
        <h3>Me lo mandaron</h3>
        <textarea id="fwd" rows="3" placeholder="Pega el reenvío. No leemos WhatsApp."></textarea>
        <button type="button" id="fwd-go">Comparar</button>
        <p id="fwd-status" class="hint"></p>
        <div id="fwd-orphan" class="orphan-card hidden">
          <p class="kicker">Sin suceso</p>
          <p>Ningún titular de esta tanda comparte suficientes palabras. Queda como reenvío huérfano.</p>
        </div>
        <ul id="fwd-hits" class="hits"></ul>
      </div>
    """


def _radar_ranking(stories: list[dict[str, Any]], *, limit: int = 12) -> str:
    ranked = [story for story in stories if story.get("source_count", 0) >= 2]
    ranked.sort(key=lambda story: (-(story.get("source_count") or 0), -((story.get("social") or {}).get("coordination") or 0)))
    if not ranked:
        return "<p class='empty'>Aún no hay sucesos cruzados en esta tanda.</p>"
    rows = []
    for index, story in enumerate(ranked[:limit], start=1):
        lean, _ = _mix_bar(story.get("lean_mix") or {}, LEAN_COLORS, BUCKET_LABELS, "mini")
        sid = html.escape(story.get("id") or "")
        rows.append(
            f'<a class="rank" href="#story-{sid}">'
            f'<span class="n">{index}</span>{lean}'
            f'<span class="rank-body"><strong>{html.escape(story.get("title") or "")}</strong>'
            f'<span class="kicker">{html.escape(_meta_line(story))}</span></span></a>'
        )
    return f'<div class="ranks">{"".join(rows)}</div>'


def _radar_pane(payload: dict[str, Any], stories: list[dict[str, Any]]) -> str:
    blinds = [story for story in stories if story.get("blindspot")]
    orphans = _orphan_trends(payload)
    if orphans:
        items = []
        for trend in orphans[:16]:
            query = trend.get("query") or ""
            url = "https://trends.google.com/trends/explore?geo=CL&q=" + quote(query)
            traffic = html.escape(trend.get("traffic") or "Trends CL")
            items.append(
                f'<li><a href="{html.escape(url)}" target="_blank" rel="noopener">{html.escape(query)}</a>'
                f'<span class="kicker">{traffic}</span></li>'
            )
        orphan_html = f'<ol class="orphans">{"".join(items)}</ol>'
    elif payload.get("trends"):
        orphan_html = "<p class='empty'>Todos los trends de esta tanda tienen suceso.</p>"
    else:
        orphan_html = "<p class='empty'>Trends CL no respondió en esta tanda.</p>"
    blind_html = (
        "".join(_ficha(story, with_id=False, compact=True) for story in blinds[:8])
        if blinds
        else "<p class='empty'>Sin puntos ciegos con la fórmula actual.</p>"
    )
    return f"""
      <header class="block-head">
        <p class="kicker">Radar de agenda</p>
        <h2>Qué pesa hoy</h2>
      </header>
      {_radar_ranking(stories, limit=20)}
      <header class="block-head">
        <p class="kicker">Puntos ciegos</p>
        <h2>Un lado casi no cubre</h2>
      </header>
      {blind_html}
      <header class="block-head">
        <p class="kicker">Huérfanos</p>
        <h2>Trends sin suceso</h2>
      </header>
      {orphan_html}
      {_paste_box()}
    """


def _week_row(row: dict[str, Any]) -> str:
    kind = SOCIAL_SHORT.get(row.get("social_kind") or "", "")
    bits = [f"{row.get('days', 1)} d", f"{row.get('outlets', 0)} medios"]
    if kind:
        bits.append(kind)
    if row.get("blindspot"):
        bits.append("ciego")
    copy = row.get("copy_score") or 0
    if copy:
        bits.append(f"copia {copy}")
    ents = " · ".join(row.get("entities") or [])
    ents_html = f'<p class="hint">{html.escape(ents)}</p>' if ents else ""
    sid = html.escape(row.get("id") or "")
    href = f'href="#story-{sid}"' if sid else ""
    return (
        f'<a class="week-row" {href}>'
        f'<strong>{html.escape(row.get("title") or "")}</strong>'
        f'<span class="kicker">{html.escape(" · ".join(bits))}</span>{ents_html}</a>'
    )


def _weekly_pane(weekly: dict[str, Any]) -> str:
    first = bool(weekly.get("first_week"))
    today = weekly.get("today") or {}
    if first:
        banner = (
            "<header class='week-banner'>"
            "<p class='kicker'>Semanario</p>"
            "<h2>Primera semana en curso</h2>"
            "<p>Hoy abre el archivo. Mañana se ve el patrón.</p>"
            "</header>"
        )
        lead_rows = weekly.get("today_top") or []
        lead_title = "Hoy en el archivo"
    else:
        span = f"{weekly.get('date_from') or ''} – {weekly.get('date_to') or ''}"
        banner = (
            "<header class='week-banner'>"
            "<p class='kicker'>Semanario</p>"
            f"<h2>{html.escape(span)}</h2>"
            f"<p>{weekly.get('day_count', 0)} días en archivo · "
            f"{len(weekly.get('recurring') or [])} sucesos que se repiten.</p>"
            "</header>"
        )
        lead_rows = weekly.get("recurring") or weekly.get("today_top") or []
        lead_title = "Se repiten"
    stats = f"""
      <div class="hero-stats week-stats">
        <div class="stat"><strong>{weekly.get("day_count") or 1}</strong><span>días</span></div>
        <div class="stat"><strong>{today.get("multi_source_count") or 0}</strong><span>cruzados hoy</span></div>
        <div class="stat"><strong>{today.get("blindspot_count") or 0}</strong><span>ciegos hoy</span></div>
      </div>
    """
    lead_html = "".join(_week_row(row) for row in lead_rows) or "<p class='empty'>Nada que enrollar todavía.</p>"
    blinds = "".join(_week_row(row) for row in (weekly.get("blindspots") or []))
    copies = "".join(_week_row(row) for row in (weekly.get("homogeneous") or []))
    return f"""
      {banner}
      {stats}
      <h3>{lead_title}</h3>
      <div class="week-list">{lead_html}</div>
      <h3>Ciegos de la semana</h3>
      <div class="week-list">{blinds or "<p class='empty'>Ningún ciego persistente todavía.</p>"}</div>
      <h3>Homogéneos</h3>
      <div class="week-list">{copies or "<p class='empty'>Sin titulares plantilla esta semana.</p>"}</div>
    """


def _redes_pane(payload: dict[str, Any]) -> str:
    trends = payload.get("trends") or []
    stories = payload.get("stories") or []
    rank = {"coordinated": 0, "trending": 1, "media": 2}
    signaled = [story for story in stories if (story.get("social") or {}).get("kind") in rank]
    signaled.sort(
        key=lambda story: (
            rank.get((story.get("social") or {}).get("kind"), 9),
            -((story.get("social") or {}).get("coordination") or 0),
        )
    )
    if trends:
        items = []
        for trend in trends[:20]:
            query = trend.get("query") or ""
            traffic = trend.get("traffic") or "Trends CL"
            url = "https://trends.google.com/trends/explore?geo=CL&q=" + quote(query)
            items.append(
                f'<li><a href="{html.escape(url)}" target="_blank" rel="noopener">{html.escape(query)}</a>'
                f'<span class="kicker">{html.escape(traffic)}</span></li>'
            )
        trends_html = f'<ol class="orphans">{"".join(items)}</ol>'
    else:
        trends_html = "<p class='empty'>Google Trends CL no respondió en esta tanda.</p>"
    cards = "".join(_ficha(story, with_id=False, compact=True) for story in signaled[:24])
    empty_sig = "<p class='empty'>Ningún suceso de esta tanda tiene señal de redes.</p>"
    return f"""
      <header class="block-head">
        <p class="kicker">Redes</p>
        <h2>Trends CL y ráfagas</h2>
      </header>
      {trends_html}
      <header class="block-head">
        <p class="kicker">Con señal</p>
        <h2>Pico, ráfaga o medios</h2>
      </header>
      {cards or empty_sig}
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
    return f"""
      <header class="block-head">
        <p class="kicker">Metodología</p>
        <h2>Cómo se construye</h2>
      </header>
      <dl class="method-dl">
        <div><dt>Bias Bar</dt><dd>Medios del catálogo con lean, no lectores. Borrador editorial chileno, no AllSides ni Ad Fontes. Independiente es propiedad, no “neutro”.</dd></div>
        <div><dt>Punto ciego</dt><dd>≥3 medios tasados, un lado ≤15% y el otro ≥33%.</dd></div>
        <div><dt>Copia</dt><dd>Fracción de titulares casi iguales. Alto = plantilla o cable, no bots.</dd></div>
        <div><dt>Redes</dt><dd>RSS público de Google Trends CL. Ráfaga = varias notas en pocas horas. No scrapemos WhatsApp.</dd></div>
        <div><dt>Qué se guarda</dt><dd>Título, bajada ≤400 caracteres y URL. Sin cuerpo del artículo.</dd></div>
      </dl>
      <h3>Catálogo</h3>
      <table class="method">
        <thead><tr><th>Medio</th><th>Tendencia</th><th>Propiedad</th><th>Región</th></tr></thead>
        <tbody>{"".join(rows)}</tbody>
      </table>
    """


def _aviso_body() -> str:
    mail = html.escape(CONTACT_EMAIL)
    return f"""
      <h2>Aviso legal</h2>
      <p><strong>Sin Sesgo</strong> es un agregador de cobertura noticiosa sobre Chile. No es un medio que publique reportajes propios ni un semáforo de verdad.</p>
      <p>De cada nota guardamos únicamente <strong>título, bajada (máximo 400 caracteres) y URL</strong>. No almacenamos el cuerpo del artículo, no bypaseamos paywalls y no hacemos clipping de la obra completa. El enlace lleva al sitio original.</p>
      <p>La tendencia izquierda / centro / derecha es un <strong>criterio editorial chileno</strong> del catálogo, no un rating de AllSides, Ad Fontes ni Media Bias/Fact Check. Independiente describe propiedad, no neutralidad.</p>
      <h2>Contacto</h2>
      <p>Para correcciones de catálogo o baja de un enlace: <a href="mailto:{mail}">{mail}</a>.</p>
    """


def render_aviso() -> str:
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Aviso legal · Sin Sesgo</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,560;9..144,700&family=Source+Sans+3:wght@400;600;700&display=swap" rel="stylesheet">
  <style>{_page_css()}</style>
</head>
<body>
  <div class="sky" aria-hidden="true"></div>
  <main class="sheet aviso-page">
    <p class="brand"><a href="/">Sin Sesgo</a></p>
    <p class="place">Aviso legal</p>
    {_aviso_body()}
  </main>
</body>
</html>
"""


def _search_index(stories: list[dict[str, Any]]) -> str:
    return json.dumps(
        [
            {
                "id": story.get("id"),
                "title": story.get("title"),
                "outlets": [a.get("outlet_name") for a in (story.get("articles") or [])],
                "urls": [a.get("url") for a in (story.get("articles") or [])],
                "sources": story.get("source_count", 0),
                "blindspot": story.get("blindspot"),
                "local": bool(story.get("is_local")),
                "kind": (story.get("social") or {}).get("kind") or "none",
                "tokens": " ".join(
                    [
                        story.get("title") or "",
                        *(e.get("name") or "" for e in (story.get("entities") or [])),
                        *(a.get("title") or "" for a in (story.get("articles") or [])[:8]),
                    ]
                ).strip(),
            }
            for story in stories
        ],
        ensure_ascii=False,
    )


def render_home(payload: dict[str, Any], weekly: dict[str, Any] | None = None) -> str:
    stories = payload.get("stories") or []
    crossed = [story for story in stories if story.get("source_count", 0) >= 2]
    briefing = crossed[:6]
    rest = crossed[6:]
    blinds = [story for story in stories if story.get("blindspot")]
    locals_ = [story for story in stories if story.get("is_local")]
    weekly = weekly or persist_and_digest(payload, OUT_DIR)[0]
    signaled = _signaled_count(stories)
    failed = [row for row in payload.get("feed_status", []) if not row.get("ok")]
    failed_block = ""
    if failed:
        items = "".join(
            f"<li>{html.escape(row['outlet_id'])}: {html.escape((row.get('error') or '')[:120])}</li>"
            for row in failed
        )
        failed_block = f'<details class="failed"><summary>Feeds caídos</summary><ul>{items}</ul></details>'

    briefing_html = "".join(_ficha(story) for story in briefing)
    rest_html = "".join(_ficha(story) for story in rest)
    blind_html = "".join(_ficha(story, with_id=False) for story in blinds)
    local_html = "".join(_ficha(story, with_id=False) for story in locals_)
    empty_cross = "<p class='empty'>Aún no hay sucesos con dos o más medios.</p>"
    empty_blind = "<p class='empty'>No hay puntos ciegos en esta tanda.</p>"
    empty_local = "<p class='empty'>No hay sucesos regionales en esta tanda.</p>"
    generated = html.escape((payload.get("generated_at") or "")[:16].replace("T", " "))
    orphans = _orphan_trends(payload)

    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sin Sesgo · {html.escape(TAGLINE)}</title>
  <meta name="description" content="{html.escape(TAGLINE)} {html.escape(SUBLINE)}">
  <link rel="canonical" href="{SITE_URL}/">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,560;9..144,700&family=Source+Sans+3:wght@400;600;700&display=swap" rel="stylesheet">
  {_analytics_snippet()}
  <style>{_page_css()}</style>
</head>
<body>
  <div class="sky" aria-hidden="true"></div>
  <header class="mast">
    <p class="brand">Sin Sesgo</p>
    <p class="place">Chile</p>
    <h1>{html.escape(TAGLINE)}</h1>
    <p class="sub">{html.escape(SUBLINE)}</p>
    <div class="hero-stats">
      <div class="stat"><strong>{len(crossed)}</strong><span>cruzados</span></div>
      <div class="stat"><strong>{payload.get("blindspot_count", 0)}</strong><span>ciegos</span></div>
      <div class="stat"><strong>{signaled}</strong><span>en redes</span></div>
    </div>
  </header>
  <nav aria-label="Secciones">
    <button type="button" data-pane="portada" aria-current="true">Portada</button>
    <button type="button" data-pane="radar">Radar</button>
    <button type="button" data-pane="ciego">Ciego</button>
    <button type="button" data-pane="local">Local</button>
    <button type="button" data-pane="redes">Redes</button>
    <button type="button" data-pane="semana">Semanario</button>
    <button type="button" data-pane="metodo">Metodología</button>
  </nav>
  <div class="search-wrap">
    <input id="q" type="search" placeholder="Suceso o URL" autocomplete="off">
  </div>
  <main>
    <section id="pane-search" class="pane">
      <ul id="hits" class="hits"></ul>
      <div id="hit-cards"></div>
    </section>
    <section id="pane-portada" class="pane active">
      <header class="block-head">
        <p class="kicker">Briefing</p>
        <h2>Fichas del día</h2>
      </header>
      {briefing_html or empty_cross}
      <header class="block-head">
        <p class="kicker">Radar</p>
        <h2>Agenda por cobertura</h2>
      </header>
      {_radar_ranking(crossed, limit=8)}
      <p class="hint orphans-hint">{len(orphans)} trends sin suceso · <a href="#pane-radar" data-jump="radar">ver Radar</a></p>
      {"<header class='block-head'><p class='kicker'>Resto</p><h2>Más sucesos</h2></header>" + rest_html if rest_html else ""}
    </section>
    <section id="pane-radar" class="pane">
      {_radar_pane(payload, stories)}
    </section>
    <section id="pane-ciego" class="pane">
      <header class="block-head"><p class="kicker">Ciego</p><h2>Un lado casi no cubre</h2></header>
      {blind_html or empty_blind}
    </section>
    <section id="pane-local" class="pane">
      <header class="block-head"><p class="kicker">Local</p><h2>Región o ancla geográfica</h2></header>
      {local_html or empty_local}
    </section>
    <section id="pane-redes" class="pane">
      {_redes_pane(payload)}
    </section>
    <section id="pane-semana" class="pane">
      {_weekly_pane(weekly)}
    </section>
    <section id="pane-metodo" class="pane">
      {_methodology(payload.get("outlets") or [])}
    </section>
    {failed_block}
  </main>
  <footer>
    <span>{generated} UTC</span>
    <a href="/aviso.html">Aviso legal</a>
    <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>
  </footer>
  <script>{_page_js(_search_index(stories))}</script>
</body>
</html>
"""


def _page_css() -> str:
    return """
    :root {
      --bg0: #e8f0f4;
      --bg1: #f7fafb;
      --ink: #14202b;
      --muted: #5a6a78;
      --line: #c9d6df;
      --paper: rgba(255,255,255,0.72);
      --accent: #0e7c6b;
      --link: #0b5f8a;
      --left: #c45c4a;
      --center: #7a8590;
      --right: #3d6a9a;
      --sans: "Source Sans 3", "Segoe UI", sans-serif;
      --display: "Fraunces", Georgia, serif;
    }
    * { box-sizing: border-box; }
    html { -webkit-text-size-adjust: 100%; }
    body {
      margin: 0;
      font-family: var(--sans);
      color: var(--ink);
      background: linear-gradient(165deg, var(--bg0) 0%, var(--bg1) 42%, #eef3f6 100%);
      min-height: 100vh;
      position: relative;
    }
    .sky {
      position: fixed; inset: 0; pointer-events: none; z-index: 0;
      background:
        radial-gradient(900px 420px at 8% -10%, rgba(14,124,107,0.16), transparent 60%),
        radial-gradient(700px 380px at 92% 8%, rgba(11,95,138,0.12), transparent 55%),
        repeating-linear-gradient(-12deg, transparent, transparent 18px, rgba(20,40,55,0.015) 18px, rgba(20,40,55,0.015) 19px);
    }
    .mast, nav, .search-wrap, main, footer {
      position: relative; z-index: 1;
      width: min(920px, calc(100% - 2rem));
      margin-left: auto; margin-right: auto;
    }
    .mast {
      padding: 2.4rem 0 1.5rem;
      animation: rise 0.7s ease-out both;
    }
    .brand {
      font-family: var(--display);
      font-size: clamp(2.4rem, 8vw, 3.6rem);
      font-weight: 700;
      line-height: 0.95;
      letter-spacing: -0.02em;
      color: var(--ink);
      margin: 0;
    }
    .brand a { color: inherit; text-decoration: none; }
    .place {
      font-family: var(--sans);
      font-size: 0.72rem;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: var(--accent);
      margin: 0.45rem 0 1.1rem;
      font-weight: 600;
    }
    h1 {
      font-family: var(--display);
      font-size: clamp(1.35rem, 3.4vw, 1.85rem);
      line-height: 1.2;
      font-weight: 560;
      margin: 0 0 0.45rem;
      max-width: 22ch;
      animation: rise 0.85s ease-out 0.08s both;
    }
    .sub {
      margin: 0;
      color: var(--muted);
      font-size: 1.02rem;
      max-width: 34rem;
      animation: rise 0.9s ease-out 0.14s both;
    }
    .hero-stats {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 0.75rem;
      margin: 1.55rem 0 0;
      animation: rise 1s ease-out 0.2s both;
    }
    .stat {
      border-left: 3px solid var(--accent);
      padding: 0.15rem 0 0.15rem 0.7rem;
    }
    .hero-stats strong {
      display: block;
      font-family: var(--display);
      font-size: clamp(1.75rem, 5vw, 2.35rem);
      line-height: 1;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
    }
    .hero-stats span {
      display: block;
      margin-top: 0.35rem;
      font-size: 0.7rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
      font-weight: 600;
    }
    nav {
      display: flex;
      flex-wrap: wrap;
      gap: 0.1rem;
      padding: 1rem 0 0.35rem;
      border-top: 1px solid var(--line);
      margin-top: 0.2rem;
    }
    nav button {
      font-family: var(--sans);
      font-size: 0.8rem;
      font-weight: 600;
      border: 0;
      background: transparent;
      color: var(--muted);
      padding: 0.45rem 0.7rem;
      cursor: pointer;
      border-bottom: 2px solid transparent;
      transition: color 0.18s ease, border-color 0.18s ease;
    }
    nav button[aria-current="true"] { color: var(--ink); border-bottom-color: var(--accent); }
    nav button:hover { color: var(--ink); }
    .search-wrap { padding: 0.4rem 0 1.15rem; }
    .search-wrap input {
      width: 100%;
      font-family: var(--sans);
      font-size: 0.95rem;
      padding: 0.65rem 0;
      border: 0;
      border-bottom: 1px solid var(--line);
      background: transparent;
      color: var(--ink);
    }
    .search-wrap input:focus { outline: none; border-bottom-color: var(--accent); }
    main { padding: 0 0 3.5rem; }
    .pane { display: none; }
    .pane.active { display: block; animation: fade 0.28s ease; }
    .block-head { margin: 1.8rem 0 0.85rem; }
    .block-head h2, .week-banner h2, .aviso-page h2 {
      font-family: var(--display);
      font-size: 1.35rem;
      margin: 0.1rem 0 0;
      font-weight: 560;
    }
    .kicker {
      font-size: 0.68rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: var(--muted);
      margin: 0 0 0.3rem;
      font-weight: 600;
    }
    .ficha {
      background: var(--paper);
      backdrop-filter: blur(8px);
      border: 1px solid var(--line);
      border-left: 3px solid var(--accent);
      padding: 1.05rem 1.15rem 0.95rem;
      margin-bottom: 0.8rem;
      transition: border-color 0.2s ease, transform 0.2s ease;
    }
    .ficha:hover { border-left-color: var(--link); }
    .ficha h2 {
      font-family: var(--display);
      font-size: 1.16rem;
      line-height: 1.28;
      margin: 0 0 0.65rem;
      font-weight: 560;
    }
    .ficha.flash { outline: 2px solid var(--accent); outline-offset: 2px; }
    .bar { display: flex; height: 10px; background: rgba(20,32,43,0.08); overflow: hidden; }
    .bar.owner { height: 4px; margin: 0.35rem 0 0.65rem; }
    .bar.mini { height: 7px; min-width: 56px; max-width: 72px; flex: 0 0 64px; margin-top: 0.35rem; }
    .bar span { display: block; height: 100%; }
    .lean-n {
      font-size: 0.72rem;
      color: var(--muted);
      margin: 0.35rem 0 0.15rem;
      display: flex;
      flex-wrap: wrap;
      gap: 0.55rem;
      font-weight: 600;
    }
    .lean-n b { font-weight: 700; }
    .lean-n .left { color: var(--left); }
    .lean-n .center { color: var(--center); }
    .lean-n .right { color: var(--right); }
    .facts {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 0.55rem 0.8rem;
      margin: 0 0 0.8rem;
    }
    .facts dt {
      font-size: 0.62rem;
      letter-spacing: 0.09em;
      text-transform: uppercase;
      color: var(--muted);
      font-weight: 600;
    }
    .facts dd { margin: 0.1rem 0 0; font-size: 0.9rem; }
    .facts a { color: var(--link); text-decoration: none; }
    .facts a:hover { text-decoration: underline; }
    .fact-trend { grid-column: 1 / -1; }
    .compare {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 0.55rem;
      margin: 0 0 0.65rem;
    }
    .compare section { border-top: 2px solid var(--line); padding: 0.4rem 0 0; min-width: 0; }
    .compare .left { border-top-color: var(--left); }
    .compare .right { border-top-color: var(--right); }
    .compare h3 {
      font-size: 0.62rem;
      letter-spacing: 0.09em;
      text-transform: uppercase;
      margin: 0 0 0.3rem;
      color: var(--muted);
      font-weight: 600;
    }
    .compare p { margin: 0; font-size: 0.86rem; }
    .compare a {
      color: var(--ink); text-decoration: none;
      display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
    }
    .compare a:hover { color: var(--link); }
    .compare .miss { color: var(--muted); font-style: italic; }
    .source {
      font-size: 0.68rem; letter-spacing: 0.05em; text-transform: uppercase;
      color: var(--muted); display: block; margin-bottom: 0.15rem; font-weight: 600;
    }
    details.more { font-size: 0.82rem; color: var(--muted); }
    details.more summary { cursor: pointer; color: var(--ink); font-weight: 600; }
    .headlines, .hits { list-style: none; padding: 0; margin: 0.4rem 0 0; }
    .headlines li, .hits li { padding: 0.45rem 0; border-top: 1px solid var(--line); font-size: 0.92rem; }
    .headlines a, .hits a { color: var(--ink); text-decoration: none; }
    .headlines a:hover, .hits a:hover { color: var(--link); }
    .chrono { font-size: 0.78rem; color: var(--muted); }
    .ranks { display: flex; flex-direction: column; }
    a.rank {
      display: grid;
      grid-template-columns: 1.6rem 64px 1fr;
      gap: 0.7rem;
      align-items: start;
      padding: 0.72rem 0;
      border-bottom: 1px solid var(--line);
      text-decoration: none;
      color: inherit;
      min-width: 0;
      transition: background 0.15s ease;
    }
    a.rank:hover { background: rgba(255,255,255,0.45); }
    a.rank .n { font-size: 0.75rem; color: var(--muted); padding-top: 0.15rem; font-weight: 600; }
    .rank-body { min-width: 0; }
    .rank-body strong {
      display: block; font-family: var(--display); font-size: 1.02rem;
      font-weight: 560; line-height: 1.25;
    }
    .orphans { padding-left: 1.15rem; margin: 0; }
    .orphans li { margin: 0.45rem 0; }
    .orphans a { color: var(--ink); text-decoration: none; font-weight: 600; }
    .orphans a:hover { color: var(--link); }
    .paste-box { border-top: 1px solid var(--line); padding: 1.1rem 0 0; margin: 1.6rem 0 0; }
    .paste-box h3 {
      font-size: 0.68rem; letter-spacing: 0.1em; text-transform: uppercase;
      margin: 0 0 0.45rem; color: var(--muted); font-weight: 600;
    }
    .paste-box textarea {
      width: 100%; font-family: var(--sans); font-size: 0.9rem;
      padding: 0.55rem 0; border: 0; border-bottom: 1px solid var(--line);
      background: transparent; resize: vertical;
    }
    .paste-box button {
      font-family: var(--sans); font-size: 0.8rem; font-weight: 600;
      margin-top: 0.75rem; border: 0; background: var(--ink); color: #fff;
      padding: 0.5rem 0.95rem; cursor: pointer;
      transition: background 0.18s ease;
    }
    .paste-box button:hover { background: var(--accent); }
    .orphan-card {
      border: 1px dashed var(--line); padding: 0.8rem 0.9rem;
      margin: 0.7rem 0; background: rgba(255,255,255,0.55);
    }
    .hint { font-size: 0.78rem; color: var(--muted); }
    .orphans-hint a { color: var(--link); cursor: pointer; }
    .week-banner { margin: 0.4rem 0 1rem; }
    .week-banner p { color: var(--muted); max-width: 34rem; margin: 0.35rem 0 0; }
    .week-stats { margin: 0 0 1.4rem; }
    .week-list { display: flex; flex-direction: column; }
    a.week-row {
      display: block; padding: 0.7rem 0; border-bottom: 1px solid var(--line);
      text-decoration: none; color: inherit;
    }
    a.week-row strong { display: block; font-family: var(--display); font-size: 1.02rem; font-weight: 560; }
    h3 { font-family: var(--display); font-size: 1.05rem; margin: 1.6rem 0 0.4rem; font-weight: 560; }
    .method-dl { margin: 0; }
    .method-dl div { padding: 0.7rem 0; border-bottom: 1px solid var(--line); }
    .method-dl dt {
      font-size: 0.68rem; letter-spacing: 0.1em; text-transform: uppercase;
      color: var(--accent); font-weight: 700;
    }
    .method-dl dd { margin: 0.25rem 0 0; color: var(--muted); }
    table.method { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
    table.method th, table.method td { text-align: left; padding: 0.4rem 0.3rem; border-bottom: 1px solid var(--line); }
    .empty { color: var(--muted); }
    .hidden { display: none !important; }
    .failed { margin-top: 2rem; font-size: 0.8rem; color: var(--muted); }
    footer {
      display: flex; flex-wrap: wrap; gap: 0.4rem 1rem;
      padding: 1.2rem 0 2.4rem; border-top: 1px solid var(--line);
      font-size: 0.75rem; color: var(--muted);
    }
    footer a { color: var(--link); text-decoration: none; }
    .aviso-page { padding: 2rem 0 3rem; }
    .aviso-page p { color: var(--muted); line-height: 1.5; }
    .sheet { width: min(720px, calc(100% - 2rem)); margin: 0 auto; position: relative; z-index: 1; }
    @keyframes rise {
      from { opacity: 0; transform: translateY(10px); }
      to { opacity: 1; transform: none; }
    }
    @keyframes fade {
      from { opacity: 0; }
      to { opacity: 1; }
    }
    @media (prefers-reduced-motion: reduce) {
      .mast, h1, .sub, .hero-stats, .pane.active { animation: none; }
    }
    @media (min-width: 720px) {
      .facts { grid-template-columns: repeat(4, 1fr); }
      .fact-trend { grid-column: auto; }
    }
    @media (max-width: 700px) {
      .compare { grid-template-columns: 1fr; }
      a.rank { grid-template-columns: 1.3rem 1fr; }
      a.rank .bar { display: none; }
      h1 { max-width: none; }
    }
    """


def _page_js(search_index: str) -> str:
    return f"""
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
      window.scrollTo({{ top: 0, behavior: "smooth" }});
    }}));
    document.querySelectorAll("[data-jump]").forEach((a) => {{
      a.addEventListener("click", (ev) => {{
        ev.preventDefault();
        show(a.dataset.jump);
        window.scrollTo({{ top: 0, behavior: "smooth" }});
      }});
    }});

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
      matches.filter((row) => row.sources >= 2).slice(0, 8).forEach((row) => {{
        const card = document.getElementById("story-" + row.id);
        if (card) hitCards.appendChild(card.cloneNode(true));
      }});
    }});

    const STOP = new Set("a al como con de del el en es esta este la las lo los me o para pero por que se sin su sus un una y ya chile".split(" "));
    function foldEs(value) {{
      return String(value || "").normalize("NFD").replace(/[\\u0300-\\u036f]/g, "").toLowerCase();
    }}
    function tokensOf(value) {{
      return (foldEs(value).match(/[a-z0-9]{{3,}}/g) || []).filter((w) => !STOP.has(w));
    }}
    function tokenKey(list) {{
      return [...new Set(list)].sort().join(" ");
    }}
    function scoreForward(text) {{
      const paste = tokensOf(text);
      if (paste.length < 2) return [];
      const pasteSet = new Set(paste);
      const pasteKey = tokenKey(paste);
      return INDEX.map((row) => {{
        const rowToks = tokensOf(row.tokens || row.title || "");
        const rowSet = new Set(rowToks);
        let shared = 0;
        pasteSet.forEach((w) => {{ if (rowSet.has(w)) shared += 1; }});
        const denom = Math.min(pasteSet.size, rowSet.size || 1);
        const overlap = denom ? shared / denom : 0;
        const exact = Boolean(pasteKey) && pasteKey === tokenKey(rowToks);
        return {{ row, shared, score: exact ? 1 : overlap }};
      }}).filter((x) => x.shared >= 2 || x.score >= 0.34)
        .sort((a, b) => b.score - a.score || b.shared - a.shared);
    }}
    function jumpToStory(id) {{
      const live = document.getElementById("story-" + id);
      if (!live) return false;
      show("portada");
      const det = live.querySelector("details");
      if (det) det.open = true;
      live.classList.add("flash");
      setTimeout(() => live.classList.remove("flash"), 1400);
      live.scrollIntoView({{ behavior: "smooth", block: "start" }});
      return true;
    }}
    function renderForwardHits(matches) {{
      const box = document.getElementById("fwd-hits");
      if (!box) return;
      box.innerHTML = matches.length
        ? matches.slice(0, 12).map((x) => {{
            const extra = x.row.sources >= 2 ? x.row.sources + " medios" : "1 medio";
            return "<li data-id='" + x.row.id + "'><span class='source'>" + extra + "</span><a href='#story-" + x.row.id + "'>" + escapeHtml(x.row.title) + "</a></li>";
          }}).join("")
        : "";
    }}
    const fwd = document.getElementById("fwd");
    const fwdGo = document.getElementById("fwd-go");
    const fwdStatus = document.getElementById("fwd-status");
    const fwdOrphan = document.getElementById("fwd-orphan");
    function runForward() {{
      const text = ((fwd && fwd.value) || "").trim();
      if (!text) {{
        if (fwdStatus) fwdStatus.textContent = "Pega el texto del reenvío.";
        if (fwdOrphan) fwdOrphan.classList.add("hidden");
        return;
      }}
      const matches = scoreForward(text);
      if (fwdOrphan) fwdOrphan.classList.toggle("hidden", matches.length > 0);
      if (fwdStatus) {{
        fwdStatus.textContent = matches.length
          ? matches.length + " suceso(s) con vocabulario parecido."
          : "Ningún suceso coincide. Queda como reenvío huérfano.";
      }}
      renderForwardHits(matches);
      if (matches[0] && jumpToStory(matches[0].row.id)) return;
    }}
    if (fwdGo) fwdGo.addEventListener("click", runForward);
    if (fwd) fwd.addEventListener("keydown", (ev) => {{
      if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) runForward();
    }});
    function onStoryLink(ev) {{
      const a = ev.target.closest("a[href^='#story-']");
      if (!a) return;
      const id = (a.getAttribute("href") || "").replace("#story-", "");
      if (jumpToStory(id)) ev.preventDefault();
    }}
    document.addEventListener("click", onStoryLink);

    function escapeHtml(value) {{
      return String(value || "").replace(/[&<>"']/g, (ch) => ({{
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }})[ch]);
    }}
    """
