"""Postgres (Neon) helpers. DATABASE_URL from env; never commit the secret."""
from __future__ import annotations

import os
import socket
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def database_url() -> str | None:
    _load_dotenv()
    return (os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL") or "").strip() or None


def _prefer_ipv4(url: str) -> str:
    """Windows often hangs on Neon AAAA; pin hostaddr to an A record."""
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return url
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if query.get("hostaddr"):
        return url
    try:
        infos = socket.getaddrinfo(host, parsed.port or 5432, socket.AF_INET, socket.SOCK_STREAM)
        if not infos:
            return url
        query["hostaddr"] = infos[0][4][0]
    except OSError:
        return url
    return urlunparse(parsed._replace(query=urlencode(query)))


@contextmanager
def connect() -> Iterator[Any]:
    import psycopg

    url = database_url()
    if not url:
        raise RuntimeError("DATABASE_URL no configurada")
    with psycopg.connect(_prefer_ipv4(url), connect_timeout=30) as conn:
        yield conn


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS daily_stats (
  day DATE PRIMARY KEY,
  generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  source TEXT NOT NULL DEFAULT 'live',
  article_count INT NOT NULL DEFAULT 0,
  story_count INT NOT NULL DEFAULT 0,
  multi_source_count INT NOT NULL DEFAULT 0,
  blindspot_count INT NOT NULL DEFAULT 0,
  local_count INT NOT NULL DEFAULT 0,
  homogeneous_count INT NOT NULL DEFAULT 0,
  orphan_trend_count INT NOT NULL DEFAULT 0,
  lean_share JSONB NOT NULL DEFAULT '{}'::jsonb,
  ownership_share JSONB NOT NULL DEFAULT '{}'::jsonb,
  kind_share JSONB NOT NULL DEFAULT '{}'::jsonb,
  tone_by_lean JSONB NOT NULL DEFAULT '{}'::jsonb,
  copy_by_outlet JSONB NOT NULL DEFAULT '{}'::jsonb,
  late_arrivals JSONB NOT NULL DEFAULT '[]'::jsonb,
  trends_lag JSONB NOT NULL DEFAULT '{}'::jsonb,
  social_kinds JSONB NOT NULL DEFAULT '{}'::jsonb,
  entities_top JSONB NOT NULL DEFAULT '[]'::jsonb,
  entity_pairs JSONB NOT NULL DEFAULT '[]'::jsonb,
  coverage_mix JSONB NOT NULL DEFAULT '{}'::jsonb,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS daily_stats_generated_idx ON daily_stats (generated_at DESC);
"""


_migrated = False


def migrate() -> None:
    global _migrated
    if _migrated:
        return
    with connect() as conn:
        conn.execute(SCHEMA_SQL)
        conn.commit()
    _migrated = True
