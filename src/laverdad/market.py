"""Filtro de artículos para el vertical Mercado."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from laverdad.cluster import fold

# Outlets cuyo feed ya es de economía/Pulso/mercados: no filtrar.
ALWAYS_KEEP_OUTLETS = frozenset(
    {
        "df",
        "latercera",
        "diario_estrategia",
        "emol",
        "emol_inversiones",
        "bloomberg_linea",
        "bnamericas",
        "mch",
        "revistaei",
        "portalminero",
        "nueva_mineria",
        "cooperativa",
    }
)

FINANCE_PATH = re.compile(
    r"/(economia|economía|mercados?|pulso|negocios|empresas|finanzas|inversiones|bolsa)(/|$)",
    re.I,
)

FINANCE_LEXICON = re.compile(
    r"\b("
    r"dolar|dólar|ipsa|bolsa|banco\s+central|imacec|ipc|inflaci[oó]n|pib|"
    r"cobre|tpm|tasa\s+de\s+inter[eé]s|hacienda|presupuesto|acciones|"
    r"utilidades|ganancias|mercado|finanzas|bursa|wall\s+street|"
    r"federal\s+reserve|fed\b|sofofa|citi|jp\s*morgan|bci|santander|"
    r"banco\s+estado|codelco|sqm|enel|aes\s+andes|latam\s+airlines|"
    r"tipo\s+de\s+cambio|uf\b|utm|fisco|deuda|bonos|afp|"
    r"mineria|miner[ií]a|exportaciones|importaciones|pacto\s+fiscal|"
    r"litio|energ[ií]a|el[eé]ctric|petrol|combustible|isapres?|"
    r"empresas?|ceo|gerente|inversion|inversi[oó]n|startup|fintech|"
    r"impuesto|iva\b|royalty|concesion|licitaci[oó]n|corfo|prochile"
    r")\b",
    re.I,
)


def is_finance_article(article: dict[str, Any]) -> bool:
    oid = article.get("outlet_id") or ""
    if oid in ALWAYS_KEEP_OUTLETS:
        return True
    url = str(article.get("url") or "")
    path = urlparse(url).path or ""
    if FINANCE_PATH.search(path):
        return True
    text = fold(f"{article.get('title') or ''} {article.get('lead') or ''}")
    return bool(FINANCE_LEXICON.search(text))


def filter_finance_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [a for a in articles if is_finance_article(a)]
