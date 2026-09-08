# Sin Sesgo

Agregador de cobertura noticiosa para Chile (estilo Ground News): catálogo de medios, RSS (solo **título + bajada ≤400 caracteres + URL**) y clustering de sucesos. No guarda el cuerpo de las notas (Ley 17.336). No bypasea paywalls.

Sitio: [https://sinsesgo.stellaris.cl](https://sinsesgo.stellaris.cl)

El lean del catálogo es un **borrador editorial chileno**, no ratings de Ground News / AllSides / Ad Fontes / MBFC.

El paquete Python interno se llama `laverdad` (CLI `laverdad`); el nombre público del producto es **Sin Sesgo**.

## Correr en local

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
laverdad ingest
laverdad render
laverdad serve
# Home: http://127.0.0.1:8765/index.html
```

Comandos: `ingest` (baja feeds y agrupa) · `render` (regenera HTML desde `data/out/clusters.json`) · `serve` (sirve `data/out`).

Salida local: `data/out/index.html` y `data/out/clusters.json` (gitignorados).  
Snapshot que publica Netlify: `public/index.html` y `public/clusters.json` (lo escribe el worker al renderizar).

Catálogo: `data/outlets.json`. Emol, El Mostrador y TV (T13, 24 Horas, Mega, CNN Chile) entran por **news sitemaps** (XML de robots.txt): solo título + URL. Aviso legal: `/aviso.html`. Contacto: jpcordovae@gmail.com.

## Cómo se actualiza el sitio

**GitHub Actions** (cada 30 minutos, y al hacer push de código) corre `laverdad ingest` y sube `public/` a Netlify por API. No commitea el HTML generado.

**Netlify** no ingiere RSS. Solo hospeda el snapshot. Los builders de Netlify suelen timeout contra feeds chilenos; Actions es el camino gratis más fiable.

Flujo: cron Actions → ingest/render → deploy a Netlify (sitio `sinsesgo`).

## Cuentas

| Cuenta | Uso |
| --- | --- |
| **GitHub** | Código, Actions (ingest/render cada 30 min). Repo: este. |
| **Netlify** | Hosting estático de `public/` + DNS del subdominio. `stellaris.cl` ya usa Netlify DNS (NSONE). |
| **Google** | Opcional: GA4. Más adelante YouTube Data API para TV. No se usa Cloud Run / BigQuery / News API. |

## Variables / secretos

Nada obligatorio para el MVP. No commitear `.env`.

| Dónde | Nombre | Para qué |
| --- | --- | --- |
| GitHub → Settings → Secrets | `NETLIFY_AUTH_TOKEN` | Token personal de Netlify para que Actions publique el snapshot. |
| GitHub → Settings → Secrets | `GA_MEASUREMENT_ID` | ID de medición GA4 (`G-…`). Si no está, el HTML no carga analytics. **No inventar un ID.** |

El site id de Netlify (`sinsesgo`) ya está en el workflow. No commitear el token.

## Dominio

- Producto actual: `https://sinsesgo.stellaris.cl` (también `https://sinsesgo.netlify.app`)
- Dominio propio del producto: **`blindspot.cl`** (alias del mismo sitio Netlify `sinsesgo`)
- Apex `stellaris.cl` ya está en **Netlify DNS**.
- En el sitio Netlify de Sin Sesgo: Domain management → aliases `blindspot.cl` + `www.blindspot.cl`.

### DNS `blindspot.cl` (Netlify DNS / NSONE)

En el registrador del dominio, **cambia solo los nameservers** a:

| Nameserver |
| --- |
| `dns1.p09.nsone.net` |
| `dns2.p09.nsone.net` |
| `dns3.p09.nsone.net` |
| `dns4.p09.nsone.net` |

Netlify ya controla la zona y tiene estos registros (no los cargues a mano en el registrador si usas Netlify DNS):

| Tipo | Host | Valor |
| --- | --- | --- |
| `NETLIFY` | `@` / `blindspot.cl` | `sinsesgo.netlify.app` |
| `NETLIFY` | `www` | `sinsesgo.netlify.app` |

Cuando los NS propaguen, Netlify emite el certificado HTTPS. Panel: [Domain management](https://app.netlify.com/projects/sinsesgo/domain-management).

### DNS `sinsesgo.stellaris.cl` (zona `stellaris.cl`)

| Tipo | Host | Valor |
| --- | --- | --- |
| `CNAME` | `sinsesgo` | `sinsesgo.netlify.app` |

No hace falta `www` en un subdominio.

## Conectar Netlify (si el sitio aún no existe)

1. [Import from Git](https://app.netlify.com/start) → GitHub → repo `sinsesgo`.
2. Build command: el de `netlify.toml` (no corre ingest). Publish directory: `public`.
3. Site name sugerido: `sinsesgo`.
4. Domain settings → Add custom domain `sinsesgo.stellaris.cl` (misma cuenta que ya sirve `stellaris.cl` para que el DNS se cree solo).
5. Esperar el certificado Let’s Encrypt.

## Legal y editorial

- Solo título, bajada (≤400) y URL. Sin cuerpos, sin scraping de paywall.
- El lean es un borrador editorial 2026-09, no un promedio de AllSides/MBFC.
- Fuera del MVP: WhatsApp, cuentas de usuario, For You / My News Bias, factuality scores.

## Siguiente paso (Google, TV)

Para T13 / 24 Horas / Mega se puede usar la **YouTube Data API** (cupo gratis) sobre los canales oficiales. No está implementado en este MVP.
