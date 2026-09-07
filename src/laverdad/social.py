"""Señales de trending y ráfaga. No scrapea WhatsApp; Trends CL es público (RSS)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree as ET

from urllib.parse import quote

from laverdad.cluster import STOPWORDS, tokens
from laverdad.ingest import fetch_feed

TRENDS_RSS = "https://trends.google.com/trending/rss?geo=CL"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_traffic(raw: str) -> int:
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    return int(digits) if digits else 0


def fetch_trends_cl(*, timeout: float = 12.0) -> list[dict[str, Any]]:
    xml_text, error = fetch_feed(TRENDS_RSS, timeout=timeout)
    if error or not xml_text:
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    items: list[dict[str, Any]] = []
    for node in root.iter():
        if _local(node.tag) != "item":
            continue
        query = ""
        traffic = ""
        news: list[str] = []
        for child in node:
            name = _local(child.tag)
            if name == "title":
                query = (child.text or "").strip()
            elif name == "approx_traffic":
                traffic = (child.text or "").strip()
            elif name == "news_item":
                for bit in child:
                    if _local(bit.tag) == "news_item_title" and bit.text:
                        news.append(bit.text.strip())
        if query:
            items.append(
                {
                    "query": query,
                    "traffic": traffic,
                    "traffic_n": parse_traffic(traffic),
                    "news": news[:4],
                }
            )
    return items


def media_burst(members: list[dict[str, Any]]) -> dict[str, Any]:
    dates: list[datetime] = []
    for member in members:
        raw = member.get("published_at")
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dates.append(dt.astimezone(timezone.utc))
        except ValueError:
            continue
    if len(dates) < 2:
        return {"span_minutes": None, "in_2h": len(dates), "score": 0.0}
    dates.sort()
    span = (dates[-1] - dates[0]).total_seconds() / 60
    in_2h = sum(1 for dt in dates if (dt - dates[0]).total_seconds() <= 7200)
    score = 0.0
    if in_2h >= 4 and span <= 180:
        score = min(1.0, 0.35 + 0.15 * in_2h)
    elif in_2h >= 3 and span <= 240:
        score = 0.45
    elif in_2h >= 3:
        score = 0.25
    return {"span_minutes": round(span), "in_2h": in_2h, "score": round(score, 2)}


def copy_score(members: list[dict[str, Any]]) -> float:
    """Alto = titulares casi iguales (plantilla / cable). No prueba bots."""
    titles = [m.get("title") or "" for m in members if m.get("title")]
    if len(titles) < 2:
        return 0.0
    from rapidfuzz import fuzz

    pairs = 0
    high = 0
    for i, left in enumerate(titles):
        for right in titles[i + 1 :]:
            pairs += 1
            if fuzz.token_set_ratio(left, right) >= 78:
                high += 1
    if not pairs:
        return 0.0
    return round(high / pairs, 2)


def _story_tokens(story: dict[str, Any]) -> set[str]:
    parts = [story.get("title") or ""]
    for ent in story.get("entities") or []:
        parts.append(ent.get("name") or "")
    return {w for w in tokens(" ".join(parts)) if w not in STOPWORDS and len(w) >= 4}


def match_trend(story: dict[str, Any], trend: dict[str, Any]) -> int:
    story_tok = _story_tokens(story)
    trend_tok = {w for w in tokens(" ".join([trend.get("query") or "", *(trend.get("news") or [])])) if len(w) >= 4}
    shared = story_tok & trend_tok
    return len(shared)


def attach_social(stories: list[dict[str, Any]], trends: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    trends = trends if trends is not None else fetch_trends_cl()
    for story in stories:
        burst = media_burst(story.get("articles") or [])
        copies = copy_score(story.get("articles") or [])
        hits = []
        for trend in trends:
            shared = match_trend(story, trend)
            if shared >= 2:
                hits.append({**trend, "shared": shared})
        hits.sort(key=lambda row: (-row["shared"], -row.get("traffic_n") or 0))
        top = hits[0] if hits else None
        coord = min(1.0, 0.55 * burst["score"] + 0.45 * copies)
        if top and coord >= 0.55:
            label = "Ráfaga coordinada (posible)"
            kind = "coordinated"
        elif top:
            label = f"En trending CL · {top['query']}"
            kind = "trending"
        elif burst["score"] >= 0.45:
            label = "Ráfaga de medios"
            kind = "media"
        else:
            label = "Sin señal de redes"
            kind = "none"
        q = (top or {}).get("query") or " ".join(
            e.get("name") or "" for e in (story.get("entities") or [])[:2]
        ) or (story.get("title") or "")[:40]
        story["social"] = {
            "kind": kind,
            "label": label,
            "coordination": round(coord, 2),
            "burst": burst,
            "copy_score": copies,
            "trend": top,
            "trends_url": "https://trends.google.com/trends/explore?geo=CL&q=" + quote(q),
        }
    return stories
