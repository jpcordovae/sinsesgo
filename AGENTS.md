# AGENTS.md — Blind Spot handoff

For any AI taking over this repo. Product rules also live in `.cursor/rules/sin-sesgo-*.mdc`.

## Objective

Build and operate **Blind Spot**: a Chilean multi-outlet news coverage comparator. Show how different media tell the *same* story — editorial lean (curated draft), ownership, blindspots, tone, headline homogeneity, and open-web Trends CL signals — without storing full articles or accusing accounts of being bots.

Tagline: **El mismo suceso. Distintos medios. Cómo lo cuentan.**
Public site: **https://blindspot.cl** (package still `laverdad`; Netlify site id still `sinsesgo`).

## Non-negotiables

| Do | Don't |
|----|--------|
| Title + lead ≤400 + URL only | Persist article bodies |
| Chilean curated lean draft | AllSides / Ad Fontes / MBFC ratings |
| Trends CL RSS + media burst + copy-score | Claim “bots” or scrape WhatsApp |
| User-paste “me lo mandaron” | Track others’ chats/accounts |
| Push `main` → Actions → Netlify | Commit `.env` / tokens |

## Architecture (quick)

- Package: `laverdad` under `src/laverdad/`
- Ingest: RSS + Google news sitemaps + weak TV homepage title scrape
- Cluster: greedy vs seed title (strict); tokens from title+lead; no union-find mega-clusters
- Style: entities + hedonic tone (display only, not clustering)
- Social: `fetch_trends_cl` → `attach_social` → kind/label/coordination
- History: `history.py` compact day snapshots → Semanario digest
- UI: single generated `index.html` from `report.py` (inline CSS/JS)

## Product surfaces

1. **Portada / Fichas** — briefing + Bias Bar + facts row + compare headlines
2. **Radar** — agenda by coverage, blindspots, orphan Trends, paste box
3. **Redes** — Trends list + signaled stories
4. **Semanario** — multi-day archive when `public/history.json` accumulates
5. **Ciego / Local / Metodología / Aviso**

## State as of 2026-09-08

- Live: https://blindspot.cl (also sinsesgo.stellaris.cl / sinsesgo.netlify.app)
- GitHub: https://github.com/jpcordovae/sinsesgo · user `jpcordovae`
- Catalog: **35 outlets MVP** (RSS, sitemap o listing). Actions: `ingest --all-rss --timeout 20`
- Radios activas: BioBio, Cooperativa, UChile, ADN, Duna, Agricultura, Pauta
- Paywall Edwards (Mercurio/LUN/La Segunda): solo titulares de portada cuando el listing responde

### Done recently

- Social MVP + Redes UI; ficha / radar / semanario
- Full-catalog ingest (no longer MVP-only subset)

### Open / improve next

1. Tighten `match_trend` (require query tokens, raise threshold, or entity-gated)
2. Stop oversized titles from TV listing scrape (`ingest` / listing parsers)
3. Let Semanario mature over multiple deploy days
4. Optional analytics when `GA_MEASUREMENT_ID` is set in Actions

## Commands

```powershell
$env:PYTHONPATH='E:\Projects\LaVerdad\src'
python -u -m laverdad.cli ingest --timeout 20
python -u -m laverdad.cli render
python -u -m laverdad.cli serve --port 8765
```

Gitignored outputs: `data/out/`, `public/index.html`, `public/clusters.json`, `public/history.json`, etc. Source of truth for UI is `src/laverdad/report.py`.

## Voice / design

Chilean, precise, calm. Short UI copy. Brand-first hero. Avoid AI-default cream+terracotta broadsheet, purple SaaS glow, and dense newspaper chrome. Prefer scannable fichas over essay methodology on the home pane.
