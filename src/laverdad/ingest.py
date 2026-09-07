from __future__ import annotations

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import unescape
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import feedparser
import httpx

from laverdad.catalog import lean_bucket

USER_AGENT = "SinSesgo/0.1 (agregador de cobertura; +https://sinsesgo.stellaris.cl)"
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}


def canonicalize_url(url: str) -> str:
    raw = (url or "").strip()
    parsed = urlparse(raw)
    query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
    ]
    cleaned = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        query=urlencode(query),
        fragment="",
    )
    return urlunparse(cleaned).rstrip("/")


def strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", unescape(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def _published(entry: Any) -> str | None:
    for key in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, key, None)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()
            except (TypeError, ValueError):
                pass
    return None


def fetch_feed(url: str, *, timeout: float = 12.0) -> tuple[str, str | None]:
    """Devuelve (cuerpo, error). No lanza: el worker debe seguir con otros feeds."""
    limits = httpx.Timeout(timeout, connect=min(5.0, timeout), read=timeout, write=timeout, pool=timeout)
    try:
        with httpx.Client(
            timeout=limits,
            follow_redirects=True,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
            },
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.text, None
    except Exception as exc:  # noqa: BLE001 — queremos el feed fallido, no abortar el lote
        return "", f"{type(exc).__name__}: {exc}"


def parse_feed(xml_text: str, outlet: dict[str, Any], feed_url: str) -> list[dict[str, Any]]:
    parsed = feedparser.parse(xml_text)
    articles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in parsed.entries:
        link = canonicalize_url(getattr(entry, "link", "") or "")
        title = strip_html(getattr(entry, "title", "") or "")
        if not link or not title or link in seen:
            continue
        seen.add(link)
        lead = strip_html(
            getattr(entry, "summary", "")
            or getattr(entry, "description", "")
            or ""
        )[:400]
        articles.append(
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
                "lead": lead,
                "url": link,
                "published_at": _published(entry),
                "feed": feed_url,
            }
        )
    return articles


def _jobs_for(outlet: dict[str, Any]) -> list[tuple[str, str]]:
    jobs: list[tuple[str, str]] = []
    for url in outlet.get("feeds") or []:
        jobs.append(("rss", url))
    for url in outlet.get("sitemaps") or []:
        jobs.append(("sitemap", url))
    for url in outlet.get("listings") or []:
        jobs.append(("listing", url))
    return jobs


_LISTING_A = re.compile(r"""<a[^>]+href=["']([^"']+)["'][^>]*>(.*?)</a>""", re.I | re.S)


def parse_listing(html_text: str, outlet: dict[str, Any], page_url: str) -> list[dict[str, Any]]:
    """Solo titulares y URLs de una portada. No baja el cuerpo de la nota."""
    from laverdad.sitemap import articles_from_sitemap_entries, looks_like_article

    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for href, inner in _LISTING_A.findall(html_text or ""):
        abs_url = canonicalize_url(urljoin(page_url, href))
        title = strip_html(inner)
        if not looks_like_article(abs_url) or len(title) < 22 or abs_url in seen:
            continue
        seen.add(abs_url)
        entries.append({"url": abs_url, "title": title, "published_at": ""})
    return articles_from_sitemap_entries(entries, outlet, page_url, limit=40)


def _ingest_sitemap(outlet: dict[str, Any], sitemap_url: str, *, timeout: float) -> tuple[list[dict[str, Any]], str | None]:
    from laverdad.sitemap import articles_from_sitemap_entries, parse_sitemap_xml, pick_child_sitemaps

    xml_text, error = fetch_feed(sitemap_url, timeout=timeout)
    if error:
        return [], error
    children, entries = parse_sitemap_xml(xml_text)
    if children:
        entries = []
        last_error = None
        for child in pick_child_sitemaps(children, limit=2):
            child_xml, child_err = fetch_feed(child, timeout=timeout)
            if child_err:
                last_error = child_err
                continue
            _, child_entries = parse_sitemap_xml(child_xml)
            entries.extend(child_entries)
        if not entries:
            return [], last_error or "sitemap index sin urls"
    items = articles_from_sitemap_entries(entries, outlet, sitemap_url)
    return items, None if items else "sitemap sin artículos útiles"


def ingest_outlets(outlets: list[dict[str, Any]], *, timeout: float = 12.0) -> dict[str, Any]:
    articles: list[dict[str, Any]] = []
    feed_status: list[dict[str, Any]] = []
    jobs = [(outlet, kind, url) for outlet in outlets for kind, url in _jobs_for(outlet)]

    def _one(outlet: dict[str, Any], kind: str, url: str) -> dict[str, Any]:
        if kind == "sitemap":
            items, error = _ingest_sitemap(outlet, url, timeout=timeout)
            return {
                "outlet": outlet,
                "feed": url,
                "ok": not error,
                "items": items,
                "error": error,
            }
        if kind == "listing":
            html_text, error = fetch_feed(url, timeout=timeout)
            if error:
                return {"outlet": outlet, "feed": url, "ok": False, "items": [], "error": error}
            items = parse_listing(html_text, outlet, url)
            return {
                "outlet": outlet,
                "feed": url,
                "ok": bool(items),
                "items": items,
                "error": None if items else "portada sin titulares útiles",
            }
        xml_text, error = fetch_feed(url, timeout=timeout)
        if error:
            return {
                "outlet": outlet,
                "feed": url,
                "ok": False,
                "items": [],
                "error": error,
            }
        return {
            "outlet": outlet,
            "feed": url,
            "ok": True,
            "items": parse_feed(xml_text, outlet, url),
            "error": None,
        }

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(_one, outlet, kind, url) for outlet, kind, url in jobs]
        for future in as_completed(futures):
            row = future.result()
            parsed_articles = row["items"]
            articles.extend(parsed_articles)
            feed_status.append(
                {
                    "outlet_id": row["outlet"]["id"],
                    "feed": row["feed"],
                    "ok": row["ok"],
                    "items": len(parsed_articles),
                    "error": row["error"],
                }
            )
    unique: dict[str, dict[str, Any]] = {}
    for article in articles:
        unique[article["url"]] = article
    filled = fill_missing_leads(list(unique.values()), timeout=min(8.0, timeout))
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "feed_status": feed_status,
        "articles": filled,
    }


_META_LEAD = re.compile(
    r"""<meta[^>]+(?:property|name)\s*=\s*["'](?:og:description|twitter:description|description)["'][^>]+content\s*=\s*["']([^"']+)["']""",
    re.I,
)
_META_LEAD_REV = re.compile(
    r"""<meta[^>]+content\s*=\s*["']([^"']+)["'][^>]+(?:property|name)\s*=\s*["'](?:og:description|twitter:description|description)["']""",
    re.I,
)
_FIRST_P = re.compile(r"<p[^>]*>(.*?)</p>", re.I | re.S)


def extract_lead_html(html_text: str) -> str:
    """Solo bajada pública (meta/primer párrafo). Nunca el cuerpo completo."""
    for pattern in (_META_LEAD, _META_LEAD_REV):
        match = pattern.search(html_text or "")
        if match:
            lead = strip_html(match.group(1))
            if len(lead) >= 40:
                return lead[:400]
    for block in _FIRST_P.findall(html_text or "")[:4]:
        lead = strip_html(block)
        if len(lead) >= 70:
            return lead[:400]
    return ""


def fill_missing_leads(articles: list[dict[str, Any]], *, timeout: float = 8.0, limit: int = 140) -> list[dict[str, Any]]:
    need = [row for row in articles if len((row.get("lead") or "").strip()) < 50][:limit]
    if not need:
        return articles

    def _one(row: dict[str, Any]) -> None:
        html_text, error = fetch_feed(row.get("url") or "", timeout=timeout)
        if error or not html_text:
            return
        lead = extract_lead_html(html_text)
        if lead:
            row["lead"] = lead

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_one, need))
    return articles
