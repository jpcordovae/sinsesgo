"""Snapshots compactos para el Semanario. Sin cuerpos de artículo."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from laverdad.catalog import ROOT
from laverdad.cluster import fold, tokens

HISTORY_NAME = "history.json"
HISTORY_PATH = ROOT / "data" / "out" / HISTORY_NAME
PUBLIC_HISTORY = ROOT / "public" / HISTORY_NAME
LIVE_HISTORY_URL = "https://blindspot.cl/history.json"
MAX_DAYS = 14
MAX_STORIES = 80
CL = ZoneInfo("America/Santiago")


def chile_date(iso: str | None = None) -> str:
    if iso:
        try:
            dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(CL).date().isoformat()
        except ValueError:
            pass
    return datetime.now(CL).date().isoformat()


def compact_story(story: dict[str, Any]) -> dict[str, Any] | None:
    """Solo id, tokens de título, outlets, leans, señal. Sin bajadas ni URLs."""
    title = (story.get("title") or "").strip()
    if not title:
        return None
    sources = story.get("source_count") or 0
    social = story.get("social") or {}
    kind = social.get("kind") or "none"
    if sources < 2 and kind == "none" and not story.get("blindspot"):
        return None
    outlet_ids = list(story.get("outlets") or [])
    if not outlet_ids:
        seen: set[str] = set()
        for article in story.get("articles") or []:
            oid = article.get("outlet_id")
            if oid and oid not in seen:
                seen.add(oid)
                outlet_ids.append(oid)
    leans: list[str] = []
    for article in story.get("articles") or []:
        bucket = article.get("lean_bucket") or article.get("lean")
        if bucket and bucket not in leans:
            leans.append(str(bucket))
    title_tokens = sorted(w for w in tokens(title) if len(w) >= 4)[:16]
    entities = [
        (row.get("name") or "").strip()
        for row in (story.get("entities") or [])
        if (row.get("name") or "").strip()
    ][:8]
    return {
        "id": story.get("id"),
        "title": title[:160],
        "tokens": title_tokens,
        "outlet_ids": outlet_ids[:16],
        "leans": leans[:8],
        "social_kind": kind,
        "copy_score": social.get("copy_score") or 0,
        "blindspot": story.get("blindspot"),
        "entities": entities,
    }


def snapshot_day(payload: dict[str, Any]) -> dict[str, Any]:
    stories: list[dict[str, Any]] = []
    for story in payload.get("stories") or []:
        row = compact_story(story)
        if row:
            stories.append(row)
        if len(stories) >= MAX_STORIES:
            break
    generated = payload.get("generated_at") or datetime.now(timezone.utc).isoformat()
    return {
        "date": chile_date(generated),
        "generated_at": generated,
        "story_count": payload.get("story_count") or len(payload.get("stories") or []),
        "multi_source_count": payload.get("multi_source_count")
        or sum(1 for s in (payload.get("stories") or []) if (s.get("source_count") or 0) >= 2),
        "blindspot_count": payload.get("blindspot_count")
        or sum(1 for s in (payload.get("stories") or []) if s.get("blindspot")),
        "stories": stories,
    }


def _read_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("days"), list):
        return None
    return data


def _fetch_live() -> dict[str, Any] | None:
    try:
        import httpx

        response = httpx.get(
            LIVE_HISTORY_URL,
            timeout=8.0,
            headers={"User-Agent": "BlindSpot/0.1 (+https://blindspot.cl)"},
            follow_redirects=True,
        )
        if response.status_code != 200:
            return None
        data = response.json()
    except Exception:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("days"), list):
        return None
    return data


def load_history(out_dir: Path | None = None) -> dict[str, Any]:
    target = (out_dir or HISTORY_PATH.parent) / HISTORY_NAME
    for path in (target, PUBLIC_HISTORY):
        data = _read_file(path)
        if data and data.get("days"):
            return data
    live = _fetch_live()
    if live and live.get("days"):
        return live
    return {"days": []}


def upsert_day(history: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    day = snapshot_day(payload)
    days = [row for row in (history.get("days") or []) if isinstance(row, dict) and row.get("date")]
    days = [row for row in days if row.get("date") != day["date"]]
    days.append(day)
    days.sort(key=lambda row: row.get("date") or "")
    history["days"] = days[-MAX_DAYS:]
    return history


def save_history(history: dict[str, Any], out_dir: Path | None = None) -> Path:
    target = (out_dir or HISTORY_PATH.parent)
    target.mkdir(parents=True, exist_ok=True)
    path = target / HISTORY_NAME
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _prints(row: dict[str, Any]) -> tuple[set[str], set[str]]:
    ents = {fold(name) for name in (row.get("entities") or []) if name}
    toks = {fold(tok) for tok in (row.get("tokens") or []) if tok}
    return ents, toks


def same_story(a: dict[str, Any], b: dict[str, Any]) -> bool:
    ea, ta = _prints(a)
    eb, tb = _prints(b)
    shared_ent = len(ea & eb)
    shared_tok = len(ta & tb)
    if shared_ent >= 2:
        return True
    if shared_tok >= 3:
        return True
    return shared_ent >= 1 and shared_tok >= 2


def digest(history: dict[str, Any], payload: dict[str, Any] | None = None) -> dict[str, Any]:
    days = [row for row in (history.get("days") or []) if row.get("date")]
    days.sort(key=lambda row: row.get("date") or "")
    first_week = len(days) < 2
    threads: list[dict[str, Any]] = []
    for day in days:
        date = day.get("date")
        for story in day.get("stories") or []:
            found = None
            for thread in threads:
                if same_story(thread["seed"], story):
                    found = thread
                    break
            if found is None:
                threads.append(
                    {
                        "seed": story,
                        "title": story.get("title") or "",
                        "id": story.get("id"),
                        "dates": [date],
                        "outlet_ids": list(story.get("outlet_ids") or []),
                        "copy_scores": [story.get("copy_score") or 0],
                        "social_kinds": [story.get("social_kind") or "none"],
                        "blindspot": story.get("blindspot"),
                        "entities": list(story.get("entities") or []),
                        "leans": list(story.get("leans") or []),
                    }
                )
                continue
            if date not in found["dates"]:
                found["dates"].append(date)
            for oid in story.get("outlet_ids") or []:
                if oid not in found["outlet_ids"]:
                    found["outlet_ids"].append(oid)
            found["copy_scores"].append(story.get("copy_score") or 0)
            found["social_kinds"].append(story.get("social_kind") or "none")
            if story.get("blindspot"):
                found["blindspot"] = story.get("blindspot")
            found["title"] = story.get("title") or found["title"]
            found["id"] = story.get("id") or found["id"]
            found["leans"] = list(story.get("leans") or found["leans"])
            for name in story.get("entities") or []:
                if name not in found["entities"]:
                    found["entities"].append(name)

    rolled = []
    for thread in threads:
        copies = thread["copy_scores"] or [0]
        kinds = [k for k in thread["social_kinds"] if k and k != "none"]
        rolled.append(
            {
                "id": thread["id"],
                "title": thread["title"],
                "days": len(thread["dates"]),
                "dates": thread["dates"],
                "outlets": len(thread["outlet_ids"]),
                "copy_score": round(sum(copies) / len(copies), 2),
                "social_kind": kinds[-1] if kinds else "none",
                "blindspot": thread["blindspot"],
                "entities": thread["entities"][:6],
                "leans": thread["leans"],
            }
        )
    rolled.sort(key=lambda row: (-row["days"], -row["outlets"]))
    recurring = [row for row in rolled if row["days"] >= 2]
    blinds = [row for row in rolled if row.get("blindspot")]
    homogeneous = [row for row in rolled if (row.get("copy_score") or 0) >= 0.45]
    signaled = [row for row in rolled if row.get("social_kind") not in (None, "none")]
    today = days[-1] if days else snapshot_day(payload or {})
    return {
        "first_week": first_week,
        "day_count": len(days),
        "date_from": days[0]["date"] if days else None,
        "date_to": days[-1]["date"] if days else None,
        "today": {
            "date": today.get("date"),
            "multi_source_count": today.get("multi_source_count") or 0,
            "blindspot_count": today.get("blindspot_count") or 0,
            "story_count": today.get("story_count") or 0,
        },
        "recurring": recurring[:16],
        "today_top": [row for row in rolled if row["days"] == 1][:12] if first_week else recurring[:12],
        "blindspots": blinds[:12],
        "homogeneous": homogeneous[:8],
        "signaled": signaled[:8],
    }


def persist_and_digest(payload: dict[str, Any], out_dir: Path | None = None) -> tuple[dict[str, Any], Path]:
    target = out_dir or HISTORY_PATH.parent
    history = load_history(target)
    history = upsert_day(history, payload)
    path = save_history(history, target)
    return digest(history, payload), path
