"""Panel derecho de estadísticas + Chart.js."""
from __future__ import annotations

import html
import json
from typing import Any


OWNER_LABELS = {
    "edwards": "Edwards",
    "copesa": "Copesa",
    "claro": "Claro",
    "estado": "Estado",
    "luksic": "Luksic",
    "bethia": "Bethia",
    "carey": "Carey",
    "vytal": "Vytal",
    "independiente": "Independiente",
    "iglesia": "Iglesia",
    "otro": "Otro",
}

LEAN_LABELS_SHORT = {"left": "Izq.", "center": "Centro", "right": "Der."}


def stats_panel_html(today: dict[str, Any] | None, series: list[dict[str, Any]]) -> str:
    today = today or {}
    series_json = json.dumps(series, ensure_ascii=False)
    today_json = json.dumps(today, ensure_ascii=False)
    day_n = len(series)
    note = (
        f"{day_n} días en Neon"
        if day_n
        else "Sin serie en Neon todavía — se guarda en cada ingest"
    )
    entities = "".join(
        f"<li><span>{html.escape(row.get('name') or '')}</span><b>{row.get('n') or 0}</b></li>"
        for row in (today.get("entities_top") or [])[:10]
    ) or "<li class='empty'>Sin entidades</li>"
    pairs = "".join(
        f"<li><span>{html.escape(row.get('a') or '')} · {html.escape(row.get('b') or '')}</span>"
        f"<b>{row.get('n') or 0}</b></li>"
        for row in (today.get("entity_pairs") or [])[:8]
    ) or "<li class='empty'>Sin co-ocurrencias</li>"
    late = "".join(
        f"<li><span>{html.escape(str(row.get('outlet') or ''))}</span>"
        f"<b>#{row.get('avg_rank')}</b></li>"
        for row in (today.get("late_arrivals") or [])[:8]
    ) or "<li class='empty'>Sin cronología cruzada</li>"
    copy = "".join(
        f"<li><span>{html.escape(str(row.get('outlet') or ''))}</span>"
        f"<b>{row.get('copy')}</b></li>"
        for row in (today.get("copy_by_outlet") or [])[:8]
    ) or "<li class='empty'>Sin copia</li>"
    orphans = "".join(
        f"<li>{html.escape(row.get('query') or '')} "
        f"<span class='kicker'>{html.escape(str(row.get('traffic') or ''))}</span></li>"
        for row in ((today.get("payload") or {}).get("orphan_trends") or [])[:8]
    ) or "<li class='empty'>Sin huérfanos</li>"
    lag = today.get("trends_lag") or {}
    lag_txt = (
        f"mediana {lag.get('median_minutes')} min · n={lag.get('n')}"
        if lag.get("median_minutes") is not None
        else "Sin ráfagas con Trends"
    )
    mix = today.get("coverage_mix") or {}

    return f"""
    <aside class="stats-rail" aria-label="Estadísticas">
      <header class="rail-head">
        <p class="kicker">Estadísticas</p>
        <h2>Agenda y práctica</h2>
        <p class="hint">{html.escape(note)}</p>
      </header>
      <div class="rail-grid">
        <section class="rail-card">
          <h3>Cuota lean</h3>
          <canvas id="chart-lean" height="160"></canvas>
        </section>
        <section class="rail-card">
          <h3>Propiedad</h3>
          <canvas id="chart-owner" height="160"></canvas>
        </section>
        <section class="rail-card">
          <h3>Tipo de medio</h3>
          <canvas id="chart-kind" height="140"></canvas>
        </section>
        <section class="rail-card">
          <h3>Cruzados vs ciegos</h3>
          <canvas id="chart-blind" height="140"></canvas>
        </section>
        <section class="rail-card">
          <h3>Cobertura mixta</h3>
          <p class="rail-metric"><strong>{mix.get('mixto') or 0}</strong> mixtos · <strong>{mix.get('solo_lado') or 0}</strong> un lado</p>
          <canvas id="chart-mix" height="120"></canvas>
        </section>
        <section class="rail-card">
          <h3>Señal de redes</h3>
          <canvas id="chart-social" height="140"></canvas>
        </section>
        <section class="rail-card">
          <h3>Homogeneidad</h3>
          <canvas id="chart-homo" height="120"></canvas>
          <p class="hint">Sucesos cruzados con copia ≥ 0.45</p>
        </section>
        <section class="rail-card">
          <h3>Desfase Trends↔medios</h3>
          <p class="rail-metric">{html.escape(lag_txt)}</p>
          <canvas id="chart-lag" height="120"></canvas>
        </section>
        <section class="rail-card">
          <h3>Tono por lean</h3>
          <canvas id="chart-tone" height="160"></canvas>
        </section>
        <section class="rail-card">
          <h3>Llegan tarde</h3>
          <ol class="rail-list">{late}</ol>
        </section>
        <section class="rail-card">
          <h3>Más plantilla</h3>
          <ol class="rail-list">{copy}</ol>
        </section>
        <section class="rail-card">
          <h3>Entidades del día</h3>
          <ol class="rail-list">{entities}</ol>
        </section>
        <section class="rail-card">
          <h3>Co-ocurrencia</h3>
          <ol class="rail-list">{pairs}</ol>
        </section>
        <section class="rail-card">
          <h3>Trends huérfanos</h3>
          <ol class="rail-list orphans-list">{orphans}</ol>
        </section>
        <section class="rail-card">
          <h3>Local vs nacional</h3>
          <canvas id="chart-local" height="120"></canvas>
        </section>
        <section class="rail-card">
          <h3>Serie histórica</h3>
          <canvas id="chart-series" height="140"></canvas>
          <p class="hint">Artículos y ciegos por día (Neon)</p>
        </section>
      </div>
      <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
      <script>
      (() => {{
        const SERIES = {series_json};
        const TODAY = {today_json};
        const leanColors = {{ left: '#C45C4A', center: '#8A8680', right: '#3D6A9A' }};
        const ownerColors = {{
          edwards:'#6B5344', copesa:'#3D4F7C', claro:'#8A6A1A', estado:'#4A5568',
          luksic:'#5C3D6E', bethia:'#7A4A3A', carey:'#2F5F7A', vytal:'#5A6B3A',
          independiente:'#2F6F4E', iglesia:'#5A4A6A', otro:'#6B6B6B'
        }};
        const labels = {{ left:'Izq.', center:'Centro', right:'Der.', neg:'Neg', neu:'Neu', pos:'Pos' }};
        function doughnut(id, share, colorMap, labelMap) {{
          const el = document.getElementById(id);
          if (!el || typeof Chart === 'undefined') return;
          const keys = Object.keys(share || {{}});
          if (!keys.length) return;
          new Chart(el, {{
            type: 'doughnut',
            data: {{
              labels: keys.map(k => labelMap[k] || k),
              datasets: [{{ data: keys.map(k => share[k]), backgroundColor: keys.map(k => colorMap[k] || '#8A8680'), borderWidth: 0 }}]
            }},
            options: {{ plugins: {{ legend: {{ position: 'bottom', labels: {{ boxWidth: 10, font: {{ size: 10 }} }} }} }}, cutout: '58%' }}
          }});
        }}
        function line(id, field, color) {{
          const el = document.getElementById(id);
          if (!el || typeof Chart === 'undefined' || !SERIES.length) return;
          new Chart(el, {{
            type: 'line',
            data: {{
              labels: SERIES.map(r => (r.day || '').slice(5)),
              datasets: [{{
                data: SERIES.map(r => r[field] || 0),
                borderColor: color,
                backgroundColor: color + '33',
                fill: true,
                tension: 0.35,
                pointRadius: 0,
                borderWidth: 2
              }}]
            }},
            options: {{
              plugins: {{ legend: {{ display: false }} }},
              scales: {{
                x: {{ ticks: {{ maxTicksLimit: 6, font: {{ size: 9 }} }}, grid: {{ display: false }} }},
                y: {{ beginAtZero: true, ticks: {{ font: {{ size: 9 }} }}, grid: {{ color: 'rgba(20,32,43,0.06)' }} }}
              }}
            }}
          }});
        }}
        doughnut('chart-lean', TODAY.lean_share || {{}}, leanColors, labels);
        doughnut('chart-owner', TODAY.ownership_share || {{}}, ownerColors, {{
          edwards:'Edwards', copesa:'Copesa', claro:'Claro', estado:'Estado', luksic:'Luksic',
          bethia:'Bethia', carey:'Carey', vytal:'Vytal', independiente:'Indep.', iglesia:'Iglesia', otro:'Otro'
        }});
        doughnut('chart-kind', TODAY.kind_share || {{}}, {{
          radio:'#0e7c6b', tv:'#0b5f8a', diario:'#3d6a9a', digital:'#5c3d6e',
          investigacion:'#7a4a3a', factcheck:'#5a6b3a'
        }}, {{}});
        line('chart-blind', 'blindspot_count', '#C45C4A');
        line('chart-homo', 'homogeneous_count', '#8A6A1A');
        line('chart-lag', 'orphan_trend_count', '#0b5f8a');
        const localEl = document.getElementById('chart-local');
        if (localEl && SERIES.length && typeof Chart !== 'undefined') {{
          new Chart(localEl, {{
            type: 'bar',
            data: {{
              labels: SERIES.map(r => (r.day || '').slice(5)),
              datasets: [
                {{ label: 'Local', data: SERIES.map(r => r.local_count || 0), backgroundColor: '#2F6F4E' }},
                {{
                  label: 'Nacional',
                  data: SERIES.map(r => Math.max(0, (r.story_count || 0) - (r.local_count || 0))),
                  backgroundColor: '#3D6A9A'
                }}
              ]
            }},
            options: {{
              plugins: {{ legend: {{ position: 'bottom', labels: {{ boxWidth: 10, font: {{ size: 10 }} }} }} }},
              scales: {{
                x: {{ stacked: true, ticks: {{ maxTicksLimit: 6, font: {{ size: 9 }} }}, grid: {{ display: false }} }},
                y: {{ stacked: true, beginAtZero: true, ticks: {{ font: {{ size: 9 }} }}, grid: {{ color: 'rgba(20,32,43,0.06)' }} }}
              }}
            }}
          }});
        }}
        const seriesEl = document.getElementById('chart-series');
        if (seriesEl && SERIES.length && typeof Chart !== 'undefined') {{
          new Chart(seriesEl, {{
            type: 'line',
            data: {{
              labels: SERIES.map(r => (r.day || '').slice(5)),
              datasets: [
                {{
                  label: 'Artículos',
                  data: SERIES.map(r => r.article_count || 0),
                  borderColor: '#3D6A9A',
                  backgroundColor: '#3D6A9A33',
                  fill: true,
                  tension: 0.35,
                  pointRadius: 0,
                  borderWidth: 2
                }},
                {{
                  label: 'Ciegos',
                  data: SERIES.map(r => r.blindspot_count || 0),
                  borderColor: '#C45C4A',
                  fill: false,
                  tension: 0.35,
                  pointRadius: 0,
                  borderWidth: 2
                }}
              ]
            }},
            options: {{
              plugins: {{ legend: {{ position: 'bottom', labels: {{ boxWidth: 10, font: {{ size: 10 }} }} }} }},
              scales: {{
                x: {{ ticks: {{ maxTicksLimit: 6, font: {{ size: 9 }} }}, grid: {{ display: false }} }},
                y: {{ beginAtZero: true, ticks: {{ font: {{ size: 9 }} }}, grid: {{ color: 'rgba(20,32,43,0.06)' }} }}
              }}
            }}
          }});
        }}
        // mix stacked-ish as bar of last points
        const mixEl = document.getElementById('chart-mix');
        if (mixEl && SERIES.length && typeof Chart !== 'undefined') {{
          new Chart(mixEl, {{
            type: 'bar',
            data: {{
              labels: SERIES.map(r => (r.day || '').slice(5)),
              datasets: [
                {{ label: 'Mixto', data: SERIES.map(r => (r.coverage_mix || {{}}).mixto || 0), backgroundColor: '#0e7c6b' }},
                {{ label: 'Un lado', data: SERIES.map(r => (r.coverage_mix || {{}}).solo_lado || 0), backgroundColor: '#C45C4A' }}
              ]
            }},
            options: {{
              plugins: {{ legend: {{ position: 'bottom', labels: {{ boxWidth: 10, font: {{ size: 10 }} }} }} }},
              scales: {{
                x: {{ stacked: true, ticks: {{ maxTicksLimit: 6, font: {{ size: 9 }} }}, grid: {{ display: false }} }},
                y: {{ stacked: true, beginAtZero: true, ticks: {{ font: {{ size: 9 }} }}, grid: {{ color: 'rgba(20,32,43,0.06)' }} }}
              }}
            }}
          }});
        }}
        const socialEl = document.getElementById('chart-social');
        if (socialEl && typeof Chart !== 'undefined') {{
          const sk = TODAY.social_kinds || {{}};
          const order = ['trending','coordinated','media','none'];
          const names = {{ trending:'Trending', coordinated:'Ráfaga', media:'Medios', none:'Sin señal' }};
          const keys = order.filter(k => sk[k] != null);
          new Chart(socialEl, {{
            type: 'bar',
            data: {{
              labels: keys.map(k => names[k] || k),
              datasets: [{{ data: keys.map(k => sk[k] || 0), backgroundColor: ['#0e7c6b','#C45C4A','#3D6A9A','#8A8680'] }}]
            }},
            options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ ticks: {{ font: {{ size: 10 }} }}, grid: {{ display: false }} }}, y: {{ beginAtZero: true, ticks: {{ font: {{ size: 9 }} }} }} }} }}
          }});
        }}
        const toneEl = document.getElementById('chart-tone');
        if (toneEl && typeof Chart !== 'undefined') {{
          const tbl = TODAY.tone_by_lean || {{}};
          const leans = ['left','center','right'].filter(k => tbl[k]);
          const tones = ['neg','neu','pos'];
          const colors = {{ neg:'#8A4A42', neu:'#8A8680', pos:'#4A6B4A' }};
          new Chart(toneEl, {{
            type: 'bar',
            data: {{
              labels: leans.map(k => labels[k] || k),
              datasets: tones.map(t => ({{
                label: labels[t] || t,
                data: leans.map(l => (tbl[l] || {{}})[t] || 0),
                backgroundColor: colors[t]
              }}))
            }},
            options: {{
              plugins: {{ legend: {{ position: 'bottom', labels: {{ boxWidth: 10, font: {{ size: 10 }} }} }} }},
              scales: {{
                x: {{ stacked: true, ticks: {{ font: {{ size: 10 }} }}, grid: {{ display: false }} }},
                y: {{ stacked: true, beginAtZero: true, ticks: {{ font: {{ size: 9 }} }} }}
              }}
            }}
          }});
        }}
      }})();
      </script>
    </aside>
    """


def stats_rail_css() -> str:
    return """
    .shell {
      width: min(1280px, calc(100% - 2rem));
      margin: 0 auto;
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(280px, 340px);
      gap: 1.5rem;
      align-items: start;
      position: relative;
      z-index: 1;
    }
    .shell-main { min-width: 0; }
    .shell-main .mast, .shell-main nav, .shell-main .search-wrap, .shell-main main, .shell-main footer {
      width: 100%;
      margin-left: 0;
      margin-right: 0;
    }
    .stats-rail {
      position: sticky;
      top: 0.75rem;
      max-height: calc(100vh - 1rem);
      overflow: auto;
      padding: 0.2rem 0 2rem;
    }
    .rail-head { margin-bottom: 0.85rem; }
    .rail-head h2 {
      font-family: var(--display);
      font-size: 1.2rem;
      margin: 0.1rem 0 0.35rem;
      font-weight: 560;
    }
    .rail-grid { display: flex; flex-direction: column; gap: 0.75rem; }
    .rail-card {
      background: var(--paper);
      backdrop-filter: blur(8px);
      border: 1px solid var(--line);
      border-left: 3px solid var(--accent);
      padding: 0.75rem 0.8rem 0.7rem;
    }
    .rail-card h3 {
      font-family: var(--sans);
      font-size: 0.68rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      margin: 0 0 0.45rem;
      color: var(--muted);
      font-weight: 700;
    }
    .rail-metric { margin: 0 0 0.45rem; font-size: 0.88rem; }
    .rail-list { list-style: none; padding: 0; margin: 0; }
    .rail-list li {
      display: flex; justify-content: space-between; gap: 0.5rem;
      padding: 0.28rem 0; border-top: 1px solid var(--line);
      font-size: 0.8rem;
    }
    .rail-list li:first-child { border-top: 0; }
    .rail-list b { font-variant-numeric: tabular-nums; color: var(--muted); font-weight: 600; }
    .orphans-list li { display: block; }
    @media (max-width: 980px) {
      .shell { grid-template-columns: 1fr; }
      .stats-rail { position: static; max-height: none; order: 2; }
      .shell-main { order: 1; }
    }
    """
