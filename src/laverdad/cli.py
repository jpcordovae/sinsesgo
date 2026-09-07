from __future__ import annotations

import argparse
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from laverdad.catalog import load_catalog, select_outlets
from laverdad.cluster import cluster_articles
from laverdad.ingest import ingest_outlets
from laverdad.report import OUT_DIR, render_from_json, write_outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingiere RSS chilenos y agrupa sucesos.")
    parser.add_argument(
        "command",
        choices=["ingest", "render", "serve"],
        help="ingest: baja feeds · render: regenera la home · serve: sirve data/out",
    )
    parser.add_argument("--all-rss", action="store_true", help="Incluye outlets RSS que no son MVP")
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)

    if args.command == "render":
        paths = render_from_json()
        print(f"HTML {paths['html']}", flush=True)
        return 0

    if args.command == "serve":
        render_from_json()
        return _serve(args.port)

    catalog = load_catalog()
    outlets = select_outlets(catalog, mvp_only=not args.all_rss, ingest="rss")
    if not outlets:
        print("No hay outlets RSS para ingerir.", file=sys.stderr)
        return 1

    print(f"Ingestando {len(outlets)} medios…", flush=True)
    ingest = ingest_outlets(outlets, timeout=args.timeout)
    stories = cluster_articles(ingest["articles"])
    paths = write_outputs(catalog=catalog, ingest=ingest, stories=stories)

    ok = sum(1 for row in ingest["feed_status"] if row["ok"])
    fail = sum(1 for row in ingest["feed_status"] if not row["ok"])
    multi = sum(1 for story in stories if story["source_count"] >= 2)
    print(f"Feeds ok={ok} fail={fail}")
    print(f"Artículos={len(ingest['articles'])} clusters={len(stories)} cruzados={multi}")
    print(f"JSON {paths['json']}")
    print(f"HTML {paths['html']}")
    for row in ingest["feed_status"]:
        mark = "ok" if row["ok"] else "fail"
        extra = f" ({row['items']})" if row["ok"] else f" {row['error']}"
        print(f"  [{mark}] {row['outlet_id']}{extra}")
    return 0 if ok else 2


def _serve(port: int) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(OUT_DIR), **kwargs)

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
