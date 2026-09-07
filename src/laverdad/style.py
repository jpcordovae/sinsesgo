"""Entidades y tono sobre título + bajada. No se usa para juntar sucesos."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Any


def fold(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def _clean(title: str) -> str:
    return re.sub(r"\s+", " ", (title or "").strip())

_ENTITY_SKIP = {
    "el",
    "la",
    "los",
    "las",
    "un",
    "una",
    "chile",
    "gobierno",
    "ministro",
    "ministra",
    "presidente",
    "diputado",
    "senador",
    "lunes",
    "martes",
    "video",
}

_ORGS = (
    "la moneda",
    "banco central",
    "fiscalia",
    "fiscalía",
    "corte de apelaciones",
    "contraloria",
    "contraloría",
    "carabineros",
    "congreso",
    "camara de diputados",
    "cámara de diputados",
    "senado",
    "ministerio del interior",
    "ministerio de hacienda",
    "corte suprema",
    "tribunal constitucional",
    "cadem",
    "pdi",
)

_PLACES = (
    "santiago",
    "valparaiso",
    "valparaíso",
    "vina del mar",
    "viña del mar",
    "concepcion",
    "concepción",
    "antofagasta",
    "temuco",
    "rancagua",
    "valdivia",
    "punta arenas",
    "copiapo",
    "copiapó",
    "san bernardo",
    "araucania",
    "araucanía",
    "collipulli",
    "magallanes",
    "costanera norte",
    "la moneda",
)

_NAME = re.compile(
    r"\b([A-ZÁÉÍÓÚÑ][\wáéíóúñ']+(?:\s+(?:de|del|la|los|las|y)?\s*[A-ZÁÉÍÓÚÑ][\wáéíóúñ']+){1,3})\b"
)

_VALENCE_NEG = {
    "muerte",
    "homicidio",
    "crimen",
    "fuga",
    "narco",
    "narcotrafico",
    "irregular",
    "escandalo",
    "polemica",
    "critica",
    "amenaza",
    "crisis",
    "incendio",
    "detenido",
    "detencion",
    "condena",
    "cuestiona",
    "abuso",
    "violencia",
    "tragedia",
    "indignacion",
    "ataque",
    "tension",
    "polémica",
}
_VALENCE_POS = {
    "logro",
    "triunfo",
    "acuerdo",
    "celebra",
    "premio",
    "alivio",
    "esperanza",
    "avanza",
    "record",
    "historico",
    "avance",
}

_REG_INST = {
    "segun",
    "oficial",
    "ministerio",
    "fiscalia",
    "decreto",
    "comunicado",
    "confirmaron",
    "informo",
    "resolucion",
    "tribunal",
    "corte",
    "gobierno",
    "autoridades",
    "vocero",
}
_REG_HARD = {
    "irregular",
    "escandalo",
    "polemica",
    "cuestiona",
    "denuncia",
    "acusa",
    "blinda",
    "ataca",
    "cuestionamientos",
    "fraude",
}
_REG_EMO = {
    "emotivo",
    "impactante",
    "conmovedor",
    "indignacion",
    "dramatico",
    "terrible",
    "conmocion",
    "conmociona",
    "conmovedora",
    "impacto",
    "dolor",
    "miedo",
}


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9áéíóúñ]{3,}", fold(text))


def extract_entities(title: str, lead: str = "") -> dict[str, list[str]]:
    blob = f"{_clean(title)} {lead or ''}"
    folded = fold(blob)
    orgs = [name.title() for name in _ORGS if fold(name) in folded]
    places = [name.title() for name in _PLACES if fold(name) in folded and name not in ("la moneda",)]
    people: list[str] = []
    for match in _NAME.finditer(blob):
        raw = re.sub(r"\s+", " ", match.group(1)).strip()
        parts = [fold(p) for p in raw.split() if p]
        if not parts or parts[0] in _ENTITY_SKIP or parts[-1] in _ENTITY_SKIP or len(raw) < 6:
            continue
        if fold(raw) in {fold(x) for x in orgs + places}:
            continue
        if "segundo piso" in fold(raw) or "ver video" in fold(raw):
            continue
        people.append(raw)
    # únicos preservando orden
    def uniq(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            key = fold(item)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out[:6]

    return {"people": uniq(people), "orgs": uniq(orgs), "places": uniq(places)}


def analyze_tone(title: str, lead: str = "") -> dict[str, Any]:
    words = _words(f"{title} {lead}")
    neg = sum(1 for w in words if w in _VALENCE_NEG)
    pos = sum(1 for w in words if w in _VALENCE_POS)
    if neg > pos:
        valence, valence_label = "neg", "Negativo"
    elif pos > neg:
        valence, valence_label = "pos", "Positivo"
    else:
        valence, valence_label = "neu", "Neutro"

    inst = sum(1 for w in words if w in _REG_INST)
    hard = sum(1 for w in words if w in _REG_HARD)
    emo = sum(1 for w in words if w in _REG_EMO)
    register, register_label = "inst", "Institucional"
    if hard >= inst and hard >= emo and hard > 0:
        register, register_label = "hard", "Duro"
    elif emo >= inst and emo >= hard and emo > 0:
        register, register_label = "emo", "Emocional"
    elif inst == 0 and hard == 0 and emo == 0:
        register, register_label = "neu", "Neutro"

    return {
        "valence": valence,
        "valence_label": valence_label,
        "register": register,
        "register_label": register_label,
        "label": f"{valence_label} · {register_label}",
    }


def stamp_style(article: dict[str, Any]) -> None:
    title = article.get("title") or ""
    lead = article.get("lead") or ""
    article["entities"] = extract_entities(title, lead)
    article["tone"] = analyze_tone(title, lead)


def story_entities(members: list[dict[str, Any]]) -> list[dict[str, str]]:
    counts: Counter[tuple[str, str]] = Counter()
    for member in members:
        ents = member.get("entities") or extract_entities(member.get("title") or "", member.get("lead") or "")
        for kind in ("people", "orgs", "places"):
            for name in ents.get(kind) or []:
                counts[(kind, name)] += 1
    ranked = [ {"kind": kind, "name": name} for (kind, name), _ in counts.most_common(8) ]
    return ranked


def story_tone_mix(members: list[dict[str, Any]]) -> dict[str, int]:
    mix = {"neg": 0, "neu": 0, "pos": 0}
    for member in members:
        tone = member.get("tone") or analyze_tone(member.get("title") or "", member.get("lead") or "")
        key = tone.get("valence") or "neu"
        mix[key] = mix.get(key, 0) + 1
    total = sum(mix.values()) or 1
    return {key: round(100 * value / total) for key, value in mix.items() if value}
