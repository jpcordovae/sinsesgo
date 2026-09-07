from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "data" / "outlets.json"

# 5 etiquetas editoriales → 3 cubetas del Bias Bar (misma fórmula que Ground News).
LEAN_BUCKETS = {
    "left": "left",
    "lean_left": "left",
    "center": "center",
    "lean_right": "right",
    "right": "right",
}

LEAN_LABELS = {
    "left": "Izquierda",
    "lean_left": "Centro-izquierda",
    "center": "Centro",
    "lean_right": "Centro-derecha",
    "right": "Derecha",
}

BUCKET_LABELS = {
    "left": "Izquierda",
    "center": "Centro",
    "right": "Derecha",
}


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    data = json.loads((path or CATALOG_PATH).read_text(encoding="utf-8"))
    if "outlets" not in data:
        raise ValueError("El catálogo no tiene outlets")
    return data


def lean_bucket(lean: str | None) -> str | None:
    if not lean:
        return None
    return LEAN_BUCKETS.get(lean)


def select_outlets(
    catalog: dict[str, Any],
    *,
    mvp_only: bool = True,
    ingest: str | None = None,
) -> list[dict[str, Any]]:
    selected = []
    allowed = {ingest} if ingest else {"rss", "sitemap"}
    for outlet in catalog["outlets"]:
        if mvp_only and not outlet.get("mvp"):
            continue
        mode = outlet.get("ingest") or "rss"
        if mode not in allowed:
            continue
        if not outlet.get("feeds") and not outlet.get("sitemaps") and not outlet.get("listings"):
            continue
        selected.append(outlet)
    return selected


def outlet_by_id(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["id"]: row for row in catalog["outlets"]}
