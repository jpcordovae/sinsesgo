from __future__ import annotations

import argparse
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from laverdad.catalog import load_catalog, select_outlets
from laverdad.cluster import cluster_articles
from laverdad.ingest import ingest_outlets
from laverdad.market import filter_finance_articles
from laverdad.report import OUT_DIR, render_from_json, write_outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingiere RSS chilenos y agrupa sucesos.")
    parser.add_argument(
        "command",
        choices=["ingest", "render", "serve", "backfill-stats"],
        help="ingest | render | serve | backfill-stats (Neon)",
    )
    parser.add_argument("--all-rss", action="store_true", help="Incluye outlets RSS que no son MVP")
    parser.add_argument(
        "--vertical",
        choices=["news", "mercado"],
        default="news",
        help="Vertical: news (default) o mercado",
    )
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--months", type=int, default=3, help="Meses a intentar en backfill-stats")
    args = parser.parse_args(argv)

    vertical = args.vertical
    out_dir = OUT_DIR if vertical == "news" else OUT_DIR / "mercado"

    if args.command == "render":
        paths = render_from_json(
            json_path=out_dir / "clusters.json",
            out_dir=out_dir,
            vertical=vertical,
        )
        print(f"HTML {paths['html']}", flush=True)
        return 0

    if args.command == "serve":
        render_from_json(
            json_path=out_dir / "clusters.json" if (out_dir / "clusters.json").exists() else None,
            out_dir=out_dir,
            vertical=vertical,
        )
        return _serve(args.port, out_dir)

    if args.command == "backfill-stats":
        return _backfill(args.months, vertical=vertical, out_dir=out_dir)

    catalog = load_catalog(vertical=vertical)
    outlets = select_outlets(catalog, mvp_only=not args.all_rss)
    if not outlets:
        print("No hay outlets para ingerir.", file=sys.stderr)
        return 1

    print(f"Ingestando {len(outlets)} medios · vertical={vertical}…", flush=True)
    ingest = ingest_outlets(outlets, timeout=args.timeout)
    articles = ingest["articles"]
    if vertical == "mercado":
        before = len(articles)
        articles = filter_finance_articles(articles)
        ingest = {**ingest, "articles": articles}
        print(f"Filtro mercado: {before} → {len(articles)} artículos", flush=True)
    stories = cluster_articles(articles)
    paths = write_outputs(
        catalog=catalog,
        ingest=ingest,
        stories=stories,
        out_dir=out_dir,
        vertical=vertical,
    )

    ok = sum(1 for row in ingest["feed_status"] if row["ok"])
    fail = sum(1 for row in ingest["feed_status"] if not row["ok"])
    multi = sum(1 for story in stories if story["source_count"] >= 2)
    outlets_hit = {a.get("outlet_id") for a in articles if a.get("outlet_id")}
    print(f"Feeds ok={ok} fail={fail}")
    print(
        f"Artículos={len(articles)} clusters={len(stories)} cruzados={multi} "
        f"outlets={len(outlets_hit)}"
    )
    print(f"JSON {paths['json']}")
    print(f"HTML {paths['html']}")
    for row in ingest["feed_status"]:
        mark = "ok" if row["ok"] else "fail"
        extra = f" ({row['items']})" if row["ok"] else f" {row['error']}"
        print(f"  [{mark}] {row['outlet_id']}{extra}")
    return 0 if ok else 2


def _backfill(months: int, *, vertical: str, out_dir: Path) -> int:
    import json

    from laverdad.stats import backfill_from_articles

    catalog = load_catalog(vertical=vertical)
    source = out_dir / "clusters.json"
    if not source.exists():
        print("No hay clusters.json; corre ingest primero.", file=sys.stderr)
        return 1
    raw = json.loads(source.read_text(encoding="utf-8"))
    articles = []
    for story in raw.get("stories") or []:
        articles.extend(story.get("articles") or [])
    print(f"Backfill {vertical} desde {len(articles)} artículos · {months} meses…", flush=True)
    result = backfill_from_articles(articles, catalog, months=months, vertical=vertical)
    print(f"Días escritos={result.get('days')} omitidos={result.get('skipped')} span={result.get('span')}")
    return 0


def _serve(port: int, root: Path) -> int:
    root.mkdir(parents=True, exist_ok=True)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Home: http://127.0.0.1:{port}/index.html", flush=True)
    print("Ctrl+C para salir.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
