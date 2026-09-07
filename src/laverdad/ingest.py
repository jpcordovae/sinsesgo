from __future__ import annotations

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import unescape
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

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


def ingest_outlets(outlets: list[dict[str, Any]], *, timeout: float = 12.0) -> dict[str, Any]:
    articles: list[dict[str, Any]] = []
    feed_status: list[dict[str, Any]] = []
    jobs = [
        (outlet, feed_url)
        for outlet in outlets
        for feed_url in outlet.get("feeds") or []
    ]

    def _one(outlet: dict[str, Any], feed_url: str) -> dict[str, Any]:
        xml_text, error = fetch_feed(feed_url, timeout=timeout)
        if error:
            return {
                "outlet": outlet,
                "feed": feed_url,
                "ok": False,
                "items": [],
                "error": error,
            }
        return {
            "outlet": outlet,
            "feed": feed_url,
            "ok": True,
            "items": parse_feed(xml_text, outlet, feed_url),
            "error": None,
        }

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(_one, outlet, feed_url) for outlet, feed_url in jobs]
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
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "feed_status": feed_status,
        "articles": list(unique.values()),
    }
