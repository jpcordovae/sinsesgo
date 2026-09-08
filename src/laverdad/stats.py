"""Estadísticas diarias de cobertura Blind Spot + persistencia Neon."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from laverdad.catalog import lean_bucket
from laverdad.db import connect, database_url, migrate

CL = ZoneInfo("America/Santiago")


def chile_day(iso: str | None = None) -> date:
    if iso:
        try:
            dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(CL).date()
        except ValueError:
            pass
    return datetime.now(CL).date()


def _pct(parts: Counter[str] | dict[str, int]) -> dict[str, float]:
    total = sum(parts.values()) or 1
    return {k: round(100.0 * v / total, 1) for k, v in sorted(parts.items(), key=lambda kv: -kv[1])}


def _article_day(article: dict[str, Any]) -> date | None:
    raw = article.get("published_at")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(CL).date()
    except ValueError:
        return None


def compute_day_stats(payload: dict[str, Any], *, source: str = "live") -> dict[str, Any]:
    stories = payload.get("stories") or []
    trends = payload.get("trends") or []
    articles: list[dict[str, Any]] = []
    for story in stories:
        articles.extend(story.get("articles") or [])

    lean_arts: Counter[str] = Counter()
    owner_arts: Counter[str] = Counter()
    kind_arts: Counter[str] = Counter()
    for article in articles:
        bucket = article.get("lean_bucket") or lean_bucket(article.get("lean"))
        if bucket:
            lean_arts[bucket] += 1
        owner_arts[article.get("ownership") or "otro"] += 1
        kind_arts[article.get("kind") or "digital"] += 1

    crossed = [s for s in stories if (s.get("source_count") or 0) >= 2]
    blinds = [s for s in stories if s.get("blindspot")]
    locals_ = [s for s in stories if s.get("is_local")]
    homogeneous = [
        s
        for s in crossed
        if ((s.get("social") or {}).get("copy_score") or 0) >= 0.45
    ]

    # Coverage mix among crossed: solo-lado vs mixto
    solo = mixed = 0
    for story in crossed:
        mix = story.get("lean_mix") or {}
        sides = sum(1 for k in ("left", "center", "right") if (mix.get(k) or 0) >= 15)
        if sides <= 1:
            solo += 1
        else:
            mixed += 1

    tone_by_lean: dict[str, Counter[str]] = defaultdict(Counter)
    for story in crossed:
        mix = story.get("lean_mix") or {}
        top_lean = max(("left", "center", "right"), key=lambda k: mix.get(k) or 0, default="center")
        tone_mix = story.get("tone_mix") or {}
        if tone_mix:
            top_tone = max(tone_mix, key=lambda k: tone_mix.get(k) or 0)
            tone_by_lean[top_lean][top_tone] += 1
        for article in story.get("articles") or []:
            bucket = article.get("lean_bucket") or lean_bucket(article.get("lean"))
            tone = article.get("tone") or {}
            valence = tone.get("valence") if isinstance(tone, dict) else None
            if bucket and valence:
                tone_by_lean[bucket][str(valence)] += 1

    copy_by_outlet: dict[str, list[float]] = defaultdict(list)
    late_scores: dict[str, list[int]] = defaultdict(list)
    for story in crossed:
        copy = float((story.get("social") or {}).get("copy_score") or 0)
        chrono = story.get("chronology") or []
        for idx, row in enumerate(chrono):
            oid = row.get("outlet_id") or row.get("outlet_name") or ""
            if oid:
                late_scores[oid].append(idx)
        for article in story.get("articles") or []:
            name = article.get("outlet_name") or article.get("outlet_id")
            if name:
                copy_by_outlet[str(name)].append(copy)

    late_arrivals = sorted(
        (
            {
                "outlet": oid,
                "avg_rank": round(sum(ranks) / len(ranks), 2),
                "n": len(ranks),
            }
            for oid, ranks in late_scores.items()
            if len(ranks) >= 2
        ),
        key=lambda row: (-row["avg_rank"], -row["n"]),
    )[:12]

    copy_outlet = sorted(
        (
            {
                "outlet": name,
                "copy": round(sum(vals) / len(vals), 2),
                "n": len(vals),
            }
            for name, vals in copy_by_outlet.items()
            if vals
        ),
        key=lambda row: (-row["copy"], -row["n"]),
    )[:12]

    # Trends lag: for stories with trend match, minutes from first publish to "now" is weak;
    # use span of media burst when trending.
    lags: list[float] = []
    for story in stories:
        social = story.get("social") or {}
        if social.get("kind") not in ("trending", "coordinated"):
            continue
        burst = social.get("burst") or {}
        span = burst.get("span_minutes")
        if span is not None:
            lags.append(float(span))

    matched_queries = {
        ((s.get("social") or {}).get("trend") or {}).get("query")
        for s in stories
        if ((s.get("social") or {}).get("trend") or {}).get("query")
    }
    orphans = [t for t in trends if (t.get("query") or "") not in matched_queries]

    social_kinds: Counter[str] = Counter()
    for story in stories:
        social_kinds[(story.get("social") or {}).get("kind") or "none"] += 1

    entities: Counter[str] = Counter()
    for story in stories:
        for ent in story.get("entities") or []:
            name = (ent.get("name") or "").strip()
            if name:
                entities[name] += 1

    pair_counts: Counter[tuple[str, str]] = Counter()
    for story in stories:
        names = sorted(
            {
                (ent.get("name") or "").strip()
                for ent in (story.get("entities") or [])
                if (ent.get("name") or "").strip()
            }
        )
        for i, left in enumerate(names):
            for right in names[i + 1 :]:
                pair_counts[(left, right)] += 1

    day = chile_day(payload.get("generated_at"))
    return {
        "day": day.isoformat(),
        "generated_at": payload.get("generated_at") or datetime.now(timezone.utc).isoformat(),
        "source": source,
        "article_count": len(articles) or int(payload.get("article_count") or 0),
        "story_count": len(stories),
        "multi_source_count": len(crossed),
        "blindspot_count": len(blinds),
        "local_count": len(locals_),
        "homogeneous_count": len(homogeneous),
        "orphan_trend_count": len(orphans),
        "lean_share": _pct(lean_arts),
        "ownership_share": _pct(owner_arts),
        "kind_share": _pct(kind_arts),
        "tone_by_lean": {k: dict(v) for k, v in tone_by_lean.items()},
        "copy_by_outlet": copy_outlet,
        "late_arrivals": late_arrivals,
        "trends_lag": {
            "n": len(lags),
            "avg_minutes": round(sum(lags) / len(lags), 1) if lags else None,
            "median_minutes": round(sorted(lags)[len(lags) // 2], 1) if lags else None,
        },
        "social_kinds": dict(social_kinds),
        "entities_top": [{"name": n, "n": c} for n, c in entities.most_common(20)],
        "entity_pairs": [
            {"a": a, "b": b, "n": c} for (a, b), c in pair_counts.most_common(16) if c >= 2
        ],
        "coverage_mix": {"solo_lado": solo, "mixto": mixed},
        "payload": {
            "orphan_trends": [
                {"query": t.get("query"), "traffic": t.get("traffic")} for t in orphans[:20]
            ],
            "blind_ids": [s.get("id") for s in blinds[:30]],
        },
    }


def upsert_day(stats: dict[str, Any]) -> None:
    if not database_url():
        return
    migrate()
    with connect() as conn:
        conn.execute(UPSERT_SQL, _stats_row_params(stats))
        conn.commit()


def persist_payload(payload: dict[str, Any], *, source: str = "live") -> dict[str, Any] | None:
    if not database_url():
        return None
    stats = compute_day_stats(payload, source=source)
    upsert_day(stats)
    return stats


def load_series(days: int = 90) -> list[dict[str, Any]]:
    if not database_url():
        return []
    migrate()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT day, generated_at, source, article_count, story_count, multi_source_count,
                   blindspot_count, local_count, homogeneous_count, orphan_trend_count,
                   lean_share, ownership_share, kind_share, tone_by_lean, copy_by_outlet,
                   late_arrivals, trends_lag, social_kinds, entities_top, entity_pairs,
                   coverage_mix, payload
            FROM daily_stats
            WHERE day >= CURRENT_DATE - %(days)s::int
            ORDER BY day ASC
            """,
            {"days": days},
        ).fetchall()
    cols = [
        "day",
        "generated_at",
        "source",
        "article_count",
        "story_count",
        "multi_source_count",
        "blindspot_count",
        "local_count",
        "homogeneous_count",
        "orphan_trend_count",
        "lean_share",
        "ownership_share",
        "kind_share",
        "tone_by_lean",
        "copy_by_outlet",
        "late_arrivals",
        "trends_lag",
        "social_kinds",
        "entities_top",
        "entity_pairs",
        "coverage_mix",
        "payload",
    ]
    out = []
    for row in rows:
        item = dict(zip(cols, row))
        item["day"] = item["day"].isoformat() if hasattr(item["day"], "isoformat") else str(item["day"])
        if hasattr(item["generated_at"], "isoformat"):
            item["generated_at"] = item["generated_at"].isoformat()
        out.append(item)
    return out


def _stats_row_params(stats: dict[str, Any]) -> dict[str, Any]:
    return {
        **stats,
        "lean_share": json.dumps(stats["lean_share"], ensure_ascii=False),
        "ownership_share": json.dumps(stats["ownership_share"], ensure_ascii=False),
        "kind_share": json.dumps(stats["kind_share"], ensure_ascii=False),
        "tone_by_lean": json.dumps(stats["tone_by_lean"], ensure_ascii=False),
        "copy_by_outlet": json.dumps(stats["copy_by_outlet"], ensure_ascii=False),
        "late_arrivals": json.dumps(stats["late_arrivals"], ensure_ascii=False),
        "trends_lag": json.dumps(stats["trends_lag"], ensure_ascii=False),
        "social_kinds": json.dumps(stats["social_kinds"], ensure_ascii=False),
        "entities_top": json.dumps(stats["entities_top"], ensure_ascii=False),
        "entity_pairs": json.dumps(stats["entity_pairs"], ensure_ascii=False),
        "coverage_mix": json.dumps(stats["coverage_mix"], ensure_ascii=False),
        "payload": json.dumps(stats["payload"], ensure_ascii=False),
    }


UPSERT_SQL = """
INSERT INTO daily_stats AS d (
  day, generated_at, source, article_count, story_count, multi_source_count,
  blindspot_count, local_count, homogeneous_count, orphan_trend_count,
  lean_share, ownership_share, kind_share, tone_by_lean, copy_by_outlet,
  late_arrivals, trends_lag, social_kinds, entities_top, entity_pairs,
  coverage_mix, payload
) VALUES (
  %(day)s::date, %(generated_at)s::timestamptz, %(source)s, %(article_count)s,
  %(story_count)s, %(multi_source_count)s, %(blindspot_count)s, %(local_count)s,
  %(homogeneous_count)s, %(orphan_trend_count)s,
  %(lean_share)s::jsonb, %(ownership_share)s::jsonb, %(kind_share)s::jsonb,
  %(tone_by_lean)s::jsonb, %(copy_by_outlet)s::jsonb, %(late_arrivals)s::jsonb,
  %(trends_lag)s::jsonb, %(social_kinds)s::jsonb, %(entities_top)s::jsonb,
  %(entity_pairs)s::jsonb, %(coverage_mix)s::jsonb, %(payload)s::jsonb
)
ON CONFLICT (day) DO UPDATE SET
  generated_at = EXCLUDED.generated_at,
  source = EXCLUDED.source,
  article_count = EXCLUDED.article_count,
  story_count = EXCLUDED.story_count,
  multi_source_count = EXCLUDED.multi_source_count,
  blindspot_count = EXCLUDED.blindspot_count,
  local_count = EXCLUDED.local_count,
  homogeneous_count = EXCLUDED.homogeneous_count,
  orphan_trend_count = EXCLUDED.orphan_trend_count,
  lean_share = EXCLUDED.lean_share,
  ownership_share = EXCLUDED.ownership_share,
  kind_share = EXCLUDED.kind_share,
  tone_by_lean = EXCLUDED.tone_by_lean,
  copy_by_outlet = EXCLUDED.copy_by_outlet,
  late_arrivals = EXCLUDED.late_arrivals,
  trends_lag = EXCLUDED.trends_lag,
  social_kinds = EXCLUDED.social_kinds,
  entities_top = EXCLUDED.entities_top,
  entity_pairs = EXCLUDED.entity_pairs,
  coverage_mix = EXCLUDED.coverage_mix,
  payload = EXCLUDED.payload
"""


def backfill_from_articles(
    articles: list[dict[str, Any]],
    catalog: dict[str, Any],
    *,
    months: int = 3,
) -> dict[str, int]:
    """Reconstruye días desde published_at. RSS/sitemaps casi nunca cubren 90 días reales."""
    from laverdad.catalog import outlet_by_id
    from laverdad.cluster import fold

    if not database_url():
        return {"days": 0, "skipped": 0}

    migrate()
    outlets = outlet_by_id(catalog)
    end = datetime.now(CL).date()
    start = end - timedelta(days=30 * months)
    by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for article in articles:
        meta = outlets.get(article.get("outlet_id") or "") or {}
        enriched = {
            **article,
            "lean": article.get("lean") or meta.get("lean"),
            "lean_bucket": article.get("lean_bucket")
            or lean_bucket(article.get("lean") or meta.get("lean")),
            "ownership": article.get("ownership") or meta.get("ownership") or "otro",
            "kind": article.get("kind") or meta.get("kind") or "digital",
        }
        day = _article_day(enriched)
        if day is None or day < start or day > end:
            continue
        by_day[day].append(enriched)

    rows: list[dict[str, Any]] = []
    skipped = 0
    for day, day_arts in sorted(by_day.items()):
        if len(day_arts) < 2:
            skipped += 1
            continue
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for art in day_arts:
            key = " ".join(fold(art.get("title") or "").split()[:6])
            if len(key) >= 12:
                buckets[key].append(art)
        crossed_stories = []
        used_ids: set[str] = set()
        for group in buckets.values():
            outlet_ids = {a.get("outlet_id") for a in group}
            if len(outlet_ids) < 2:
                continue
            lean_c: Counter[str] = Counter()
            for a in group:
                b = a.get("lean_bucket")
                if b:
                    lean_c[b] += 1
            total = sum(lean_c.values()) or 1
            for a in group:
                if a.get("id"):
                    used_ids.add(str(a["id"]))
            crossed_stories.append(
                {
                    "id": group[0].get("id"),
                    "title": group[0].get("title"),
                    "source_count": len(outlet_ids),
                    "articles": group,
                    "entities": [],
                    "lean_mix": {k: round(100 * v / total) for k, v in lean_c.items()},
                    "tone_mix": {},
                    "social": {"kind": "none", "copy_score": 0, "burst": {}},
                    "chronology": [
                        {
                            "outlet_id": a.get("outlet_id"),
                            "outlet_name": a.get("outlet_name"),
                            "published_at": a.get("published_at"),
                        }
                        for a in sorted(group, key=lambda x: x.get("published_at") or "")
                    ],
                }
            )
        singles = [
            {
                "id": a.get("id"),
                "title": a.get("title"),
                "source_count": 1,
                "articles": [a],
                "entities": [],
                "lean_mix": {},
                "tone_mix": {},
                "social": {"kind": "none", "copy_score": 0, "burst": {}},
                "chronology": [],
            }
            for a in day_arts
            if str(a.get("id") or "") not in used_ids
        ]
        payload = {
            "generated_at": datetime.combine(day, datetime.min.time(), tzinfo=CL)
            .astimezone(timezone.utc)
            .isoformat(),
            "article_count": len(day_arts),
            "stories": crossed_stories + singles,
            "trends": [],
        }
        rows.append(compute_day_stats(payload, source="backfill"))

    if rows:
        print(f"  escribiendo {len(rows)} días en Neon…", flush=True)
        with connect() as conn:
            for stats in rows:
                conn.execute(UPSERT_SQL, _stats_row_params(stats))
            conn.commit()
    written_days = [date.fromisoformat(r["day"]) if isinstance(r["day"], str) else r["day"] for r in rows]
    span = (
        f"{min(written_days)}→{max(written_days)}"
        if written_days
        else f"{start}→{end} (sin días con ≥2 arts)"
    )
    return {"days": len(rows), "skipped": skipped, "span": span}
