from __future__ import annotations

import re
import unicodedata
from typing import Any

from rapidfuzz import fuzz

from laverdad.catalog import lean_bucket, outlet_by_id

STOPWORDS = {
    "a",
    "al",
    "ante",
    "asi",
    "aunque",
    "bajo",
    "como",
    "con",
    "contra",
    "cual",
    "cuando",
    "de",
    "del",
    "desde",
    "donde",
    "e",
    "el",
    "en",
    "entre",
    "era",
    "es",
    "esta",
    "este",
    "esto",
    "estos",
    "fue",
    "ha",
    "hay",
    "la",
    "las",
    "le",
    "les",
    "lo",
    "los",
    "mas",
    "me",
    "mientras",
    "muy",
    "o",
    "para",
    "pero",
    "por",
    "porque",
    "que",
    "se",
    "sin",
    "sobre",
    "su",
    "sus",
    "tambien",
    "tras",
    "un",
    "una",
    "unas",
    "unos",
    "y",
    "ya",
    "chile",
    "chileno",
    "chilena",
    "tras",
}


def fold(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


FILLER = STOPWORDS | {
    "anuncia",
    "asegura",
    "confirma",
    "detalla",
    "dice",
    "gobierno",
    "hora",
    "hoy",
    "ministra",
    "ministro",
    "nacional",
    "nueva",
    "nuevo",
    "pais",
    "presidente",
    "revela",
    "segun",
    "ultima",
    "video",
    "fotos",
}


def tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]{3,}", fold(text))
    return {word for word in words if word not in STOPWORDS}


def _doc_freq(articles: list[dict[str, Any]]) -> dict[str, int]:
    freq: dict[str, int] = {}
    for article in articles:
        for word in tokens(article.get("title") or ""):
            freq[word] = freq.get(word, 0) + 1
    return freq


def signatures(title: str, freq: dict[str, int], n_docs: int) -> set[str]:
    rare_cap = max(5, int(n_docs * 0.045))
    sig: set[str] = set()
    for word in tokens(title):
        if word in FILLER or len(word) < 4:
            continue
        if freq.get(word, 1) <= rare_cap:
            sig.add(word)
    return sig


def similar(a: dict[str, Any], b: dict[str, Any], *, freq: dict[str, int] | None = None, n_docs: int = 0) -> bool:
    title_a, title_b = a["title"], b["title"]
    token_a, token_b = tokens(title_a), tokens(title_b)
    if not token_a or not token_b:
        return False
    overlap = token_a & token_b
    if freq and n_docs:
        sig_a = signatures(title_a, freq, n_docs)
        sig_b = signatures(title_b, freq, n_docs)
        shared = sig_a & sig_b
        if len(shared) >= 2:
            return True
        if len(shared) == 1:
            word = next(iter(shared))
            if freq.get(word, 99) <= 8 and len(word) >= 5:
                return True
    if len(overlap) < 2:
        return False
    ratio = fuzz.token_set_ratio(title_a, title_b)
    jaccard = len(overlap) / len(token_a | token_b)
    return ratio >= 62 or (ratio >= 52 and jaccard >= 0.28)


def unique_members(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for member in members:
        oid = member.get("outlet_id")
        if not oid or oid in seen:
            continue
        seen.add(oid)
        unique.append(member)
    return unique


def ownership_mix(members: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for member in members:
        key = member.get("ownership") or "otro"
        counts[key] = counts.get(key, 0) + 1
    total = sum(counts.values()) or 1
    return {key: round(100 * value / total) for key, value in sorted(counts.items())}


def lean_mix(members: list[dict[str, Any]]) -> dict[str, Any]:
    """Porcentaje L/C/R entre medios con lean. Los sin nota no entran (como Ground News)."""
    counts = {"left": 0, "center": 0, "right": 0}
    rated = 0
    for member in members:
        bucket = member.get("lean_bucket") or lean_bucket(member.get("lean"))
        if not bucket:
            continue
        counts[bucket] += 1
        rated += 1
    if not rated:
        return {"left": 0, "center": 0, "right": 0, "rated": 0, "unrated": len(members)}
    return {
        "left": round(100 * counts["left"] / rated),
        "center": round(100 * counts["center"] / rated),
        "right": round(100 * counts["right"] / rated),
        "rated": rated,
        "unrated": len(members) - rated,
    }


def compare_headlines(members: list[dict[str, Any]]) -> dict[str, dict[str, str] | None]:
    picked: dict[str, dict[str, str] | None] = {"left": None, "center": None, "right": None}
    for member in members:
        bucket = member.get("lean_bucket") or lean_bucket(member.get("lean"))
        if not bucket or picked[bucket]:
            continue
        picked[bucket] = {
            "title": member.get("title") or "",
            "url": member.get("url") or "",
            "outlet_name": member.get("outlet_name") or "",
            "lean": member.get("lean") or bucket,
        }
    return picked


def classify_blindspot(mix: dict[str, Any], source_count: int) -> str | None:
    """Punto ciego adaptado a N chileno. left = la izquierda casi no cubre.

    Ground News asume decenas de fuentes. Aquí pedimos ≥3 medios tasados
    para no marcar como ciego cada dúo centro–derecha.
    """
    rated = mix.get("rated") or 0
    if source_count < 3 or rated < 3:
        return None
    left, right = mix.get("left") or 0, mix.get("right") or 0
    if left <= 15 and right >= 33:
        return "left"
    if right <= 15 and left >= 33:
        return "right"
    return None


REGION_HINTS = (
    ("valparaiso", ("valparaíso", "valparaiso", "viña del mar", "vina del mar")),
    ("biobio", ("concepción", "concepcion", "talcahuano", "biobío", "los angeles")),
    ("antofagasta", ("antofagasta", "calama", "tocopilla")),
    ("ohiggins", ("rancagua", "rancagüino", "o'higgins", "ohiggins")),
    ("magallanes", ("punta arenas", "magallanes")),
    ("araucania", ("temuco", "araucanía", "araucania")),
    ("nuble", ("chillán", "chillan", "ñuble")),
    ("atacama", ("copiapó", "copiapo", "atacama")),
    ("loslagos", ("puerto montt", "osorno", "castro")),
    ("losrios", ("valdivia", "la unión", "rio bueno")),
    ("metropolitana", ("huechuraba", "san bernardo", "puente alto", "maipú", "la florida")),
)


def regions_from_text(text: str) -> list[str]:
    folded = fold(text)
    found: list[str] = []
    for region, hints in REGION_HINTS:
        if any(fold(hint) in folded for hint in hints):
            found.append(region)
    return found


def extractive_summary(members: list[dict[str, Any]]) -> str:
    leads: list[str] = []
    seen: set[str] = set()
    for member in members:
        lead = (member.get("lead") or "").strip()
        if len(lead) < 40:
            continue
        key = lead[:80].lower()
        if key in seen:
            continue
        seen.add(key)
        leads.append(lead)
        if len(leads) == 2:
            break
    return " ".join(leads)


def chronology(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dated = [m for m in members if m.get("published_at")]
    dated.sort(key=lambda row: row["published_at"] or "")
    return [
        {
            "published_at": row.get("published_at"),
            "outlet_name": row.get("outlet_name"),
            "title": row.get("title"),
            "url": row.get("url"),
        }
        for row in dated[:8]
    ]


def annotate_story(index: int, members: list[dict[str, Any]]) -> dict[str, Any]:
    unique = unique_members(members)
    mix = lean_mix(unique)
    regions = sorted({m.get("region") or "nacional" for m in unique})
    blob = " ".join(
        [members[0].get("title") or "", *(m.get("title") or "" for m in unique)]
    )
    hinted = regions_from_text(blob)
    for region in hinted:
        if region not in regions:
            regions.append(region)
    catalog_local = any((m.get("region") or "nacional") != "nacional" for m in unique)
    return {
        "id": f"s{index:04d}",
        "title": members[0]["title"],
        "source_count": len(unique),
        "article_count": len(members),
        "ownership_mix": ownership_mix(unique),
        "lean_mix": {k: mix[k] for k in ("left", "center", "right")},
        "rated_count": mix["rated"],
        "unrated_count": mix["unrated"],
        "compare": compare_headlines(unique),
        "blindspot": classify_blindspot(mix, len(unique)),
        "regions": regions,
        "is_local": catalog_local or bool(hinted),
        "summary": extractive_summary(unique),
        "chronology": chronology(unique),
        "outlets": [m["outlet_id"] for m in unique],
        "articles": members,
    }


def enrich_articles(articles: list[dict[str, Any]], catalog: dict[str, Any]) -> None:
    """Estampa lean/región del catálogo sobre artículos ya ingeridos."""
    by_id = outlet_by_id(catalog)
    for article in articles:
        outlet = by_id.get(article.get("outlet_id") or "")
        if not outlet:
            continue
        article["lean"] = outlet.get("lean")
        article["lean_bucket"] = lean_bucket(outlet.get("lean"))
        article["region"] = outlet.get("region") or article.get("region") or "nacional"
        article.setdefault("ownership", outlet.get("ownership", "otro"))
        article.setdefault("outlet_name", outlet.get("name"))


def enrich_stories(stories: list[dict[str, Any]], catalog: dict[str, Any]) -> list[dict[str, Any]]:
    enriched = []
    for index, story in enumerate(stories, start=1):
        members = story.get("articles") or []
        enrich_articles(members, catalog)
        row = annotate_story(index, members)
        row["id"] = story.get("id") or row["id"]
        if story.get("title"):
            row["title"] = story["title"]
        enriched.append(row)
    enriched.sort(key=lambda row: (-row["source_count"], -row["article_count"]))
    return enriched


def _pair_similar(
    title_a: str,
    title_b: str,
    tok_a: set[str],
    tok_b: set[str],
    sig_a: set[str],
    sig_b: set[str],
    freq: dict[str, int],
    same_outlet: bool,
) -> bool:
    if not tok_a or not tok_b:
        return False
    if same_outlet:
        return fuzz.token_set_ratio(title_a, title_b) >= 92
    shared = {w for w in (sig_a & sig_b) if freq.get(w, 99) <= 4 and len(w) >= 5}
    if len(shared) >= 2:
        return True
    if len(shared) == 1:
        word = next(iter(shared))
        if freq.get(word, 99) <= 2 and len(word) >= 6:
            return True
    overlap = tok_a & tok_b
    if len(overlap) < 3:
        return False
    ratio = fuzz.token_set_ratio(title_a, title_b)
    return ratio >= 74


def cluster_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Greedy por titular. Sin union-find: la transitividad armaba un cluster de 600 notas."""
    if not articles:
        return []
    freq = _doc_freq(articles)
    n_docs = len(articles)
    stories: list[dict[str, Any]] = []
    story_meta: list[list[tuple[str, set[str], set[str], str]]] = []
    for article in articles:
        title = article.get("title") or ""
        tok = tokens(title)
        sig = signatures(title, freq, n_docs)
        oid = article.get("outlet_id") or ""
        placed = False
        for story, meta in zip(stories, story_meta, strict=True):
            for other_title, other_tok, other_sig, other_oid in meta[:6]:
                if _pair_similar(title, other_title, tok, other_tok, sig, other_sig, freq, oid == other_oid):
                    story["articles"].append(article)
                    meta.append((title, tok, sig, oid))
                    placed = True
                    break
            if placed:
                break
        if not placed:
            stories.append({"articles": [article]})
            story_meta.append([(title, tok, sig, oid)])

    result = [annotate_story(index, story["articles"]) for index, story in enumerate(stories, start=1)]
    result.sort(key=lambda row: (-row["source_count"], -row["article_count"]))
    return result

