"""Lee sitemaps y news-sitemaps (los XML de robots.txt de Google). Solo loc + título + fecha."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree as ET

SKIP_SITEMAP = ("foto", "video", "image", "autor", "columnista", "hemeroteca", "seccion")
NEWS_PATH = (
    "/noticias",
    "/noticia",
    "/nacional",
    "/politica",
    "/mundo",
    "/pais",
    "/actualidad",
    "/economia",
    "/deportes",
    "/tendencias",
    "/espectaculos",
    "/article",
    "/articles",
)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _text(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def _child(el: ET.Element, name: str) -> ET.Element | None:
    for child in el:
        if _local(child.tag) == name:
            return child
    return None


def _news_title(url_el: ET.Element) -> str:
    news = _child(url_el, "news")
    if news is not None:
        title = _text(_child(news, "title"))
        if title:
            return title
    for child in url_el.iter():
        if _local(child.tag) == "title" and (child.text or "").strip():
            return child.text.strip()
    return ""


def _news_date(url_el: ET.Element) -> str | None:
    news = _child(url_el, "news")
    if news is not None:
        raw = _text(_child(news, "publication_date"))
        if raw:
            return raw
    lastmod = _text(_child(url_el, "lastmod"))
    return lastmod or None


def title_from_url(url: str) -> str:
    path = unquote(urlparse(url).path).rstrip("/")
    slug = path.split("/")[-1] if path else ""
    slug = re.sub(r"\.(html?|aspx?)$", "", slug, flags=re.I)
    slug = re.sub(r"[-_]+", " ", slug).strip()
    if len(slug) < 8 or slug.isdigit():
        return ""
    return slug[:1].upper() + slug[1:]


def looks_like_article(url: str) -> bool:
    path = urlparse(url).path.lower()
    if any(x in path for x in ("/tag/", "/tags/", "/autor/", "/author/", "/tema/", "/seccion/", "/categoria/")):
        return False
    if path.endswith((".jpg", ".png", ".gif", ".mp4", ".pdf")):
        return False
    if any(part in path for part in NEWS_PATH):
        return True
    # slugs largos tipo /2026/09/07/titulo-de-la-nota/
    return bool(re.search(r"/20\d{2}/", path)) or len(path.split("/")) >= 3


def parse_sitemap_xml(xml_text: str) -> tuple[list[str], list[dict[str, str]]]:
    """Devuelve (sitemaps hijos, urls)."""
    children: list[str] = []
    urls: list[dict[str, str]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return children, urls
    kind = _local(root.tag)
    if kind == "sitemapindex":
        pairs: list[tuple[str, str]] = []
        for node in root:
            if _local(node.tag) != "sitemap":
                continue
            loc = _text(_child(node, "loc"))
            lastmod = _text(_child(node, "lastmod"))
            if loc:
                pairs.append((lastmod, loc))
        pairs.sort(reverse=True)
        return [loc for _, loc in pairs], urls
    if kind != "urlset":
        return children, urls
    for node in root:
        if _local(node.tag) != "url":
            continue
        loc = _text(_child(node, "loc"))
        if not loc:
            continue
        title = _news_title(node) or title_from_url(loc)
        urls.append(
            {
                "url": loc,
                "title": title,
                "published_at": _news_date(node) or "",
            }
        )
    return children, urls


def pick_child_sitemaps(locs: list[str], *, limit: int = 1) -> list[str]:
    year = str(datetime.now(timezone.utc).year)
    picked = []
    for loc in locs:
        low = loc.lower()
        if any(skip in low for skip in SKIP_SITEMAP):
            continue
        if year not in loc and re.search(r"20\d{2}", loc):
            continue
        picked.append(loc.replace("http://", "https://", 1))
        if len(picked) >= limit:
            break
    if picked:
        return picked
    https_locs = [loc.replace("http://", "https://", 1) for loc in locs if not any(s in loc.lower() for s in SKIP_SITEMAP)]
    return https_locs[:limit]


def normalize_published(raw: str) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d",
    ):
        try:
            cleaned = raw.replace("Z", "+00:00") if fmt.endswith("%z") and raw.endswith("Z") else raw
            if fmt.endswith("Z"):
                dt = datetime.strptime(raw.replace("Z", ""), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            else:
                dt = datetime.strptime(cleaned, fmt.replace("%z", "%z") if "%z" in fmt else fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def articles_from_sitemap_entries(
    entries: list[dict[str, str]],
    outlet: dict[str, Any],
    source: str,
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    from laverdad.catalog import lean_bucket
    from laverdad.ingest import canonicalize_url, strip_html

    import hashlib

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    cutoff = datetime.now(timezone.utc) - timedelta(days=10)
    entries = sorted(entries, key=lambda row: row.get("published_at") or "", reverse=True)
    for entry in entries:
        link = canonicalize_url(entry.get("url") or "")
        if not link or link in seen or not looks_like_article(link):
            continue
        title = strip_html(entry.get("title") or "")
        if not title:
            continue
        published = normalize_published(entry.get("published_at") or "")
        if published:
            try:
                if datetime.fromisoformat(published) < cutoff:
                    continue
            except ValueError:
                pass
        path_date = re.search(r"/((?:19|20)\d{2})/(\d{2})/", link)
        if path_date:
            try:
                path_dt = datetime(
                    int(path_date.group(1)), int(path_date.group(2)), 1, tzinfo=timezone.utc
                )
                if path_dt < cutoff.replace(day=1):
                    continue
            except ValueError:
                pass
        seen.add(link)
        out.append(
            {
                "id": hashlib.sha256(link.encode("utf-8")).hexdigest()[:16],
                "outlet_id": outlet["id"],
                "outlet_name": outlet["name"],
                "ownership": outlet.get("ownership", "otro"),
                "kind": outlet.get("kind", "digital"),
                "region": outlet.get("region", "nacional"),
                "lean": outlet.get("lean"),
                "lean_bucket": lean_bucket(outlet.get("lean")),
                "title": title,
                "lead": "",
                "url": link,
                "published_at": published,
                "feed": source,
            }
        )
        if len(out) >= limit:
            break
    return out
