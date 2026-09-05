# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

**Tejido Empresarial · ProColombia** — company segmentation app for ProColombia's Exportaciones / Inversión / Turismo business axes, with an analysis assistant on Snowflake Cortex. React 19 + TypeScript (Vite 8) frontend, FastAPI backend querying Snowflake, single Docker image deployed on Railway (`https://tejidoempresarialasistente-production.up.railway.app/`). The original Streamlit app lives untouched in `legado_streamlit/` (reference only, not deployed).

## Invariants (never break these)

1. **Snowflake is the only connector.** No external LLM provider, no extra secret. Cortex Analyst → SQL; `SNOWFLAKE.CORTEX.COMPLETE` → prose. (D-01)
2. **The model proposes, the code disposes.** Every generated SQL passes `backend/ia/guardas.validar_sql`; every prose passes `verificar_cifras`. Both stay in the path of every answer. (D-03)
3. **The AI warning (`IA_ADVERTENCIA`) appears on screen and in every exported file** (Excel, PPTX, standard listing).
4. **A failure is shown, not retried.** One COMPLETE call per answer (the simple form only after a signature/compile error); session reopened only on session/network errors. Degradation carries `motivo_degradacion` and reaches telemetry. (D-10)
5. **Rows never persist in the browser or in telemetry.** They may contain contact data. The server keeps them in memory by `consulta_id` (D-05); `sessionStorage` holds the thread skeleton only.
6. **Downloads come from the server**, by `consulta_id`, with all rows. Never accept a table from the client for export.
7. **One company exporter.** Listings — from `/consultar` or from the assistant — go through `backend/exporter.create_export` (5 sheets, NIT as text). (D-04, D-09)
8. **Contact fields** obey `EXPORT_INCLUDE_CONTACT_FIELDS` everywhere (`backend/config.py`; assistant via `backend/ia/forma.es_columna_contacto`).
9. **Every suggested question has a verified query** with identical wording in the semantic view YAML (`tests/test_modelo_semantico.py`). (D-11)
10. **Route list is a contract** (`tests/test_rutas.py`): wildcards last, security headers on every response.
11. **Values are escaped or bound.** `sql_literal` for allowlisted filters; bound `?` parameters for anything the user typed that reaches an INSERT or COMPLETE.

## Definition of done

A change is done when: `ruff check backend tests scripts` is clean; `pytest -q` passes (127+); `cd frontend && npm test && npm run build` pass; new behaviour has a test that would fail without it; CHANGELOG has an entry under the version being prepared; if it touched the semantic view, `snowflake/LEEME.md` says it must be redeployed; if it touched env vars, `.env.example`, `RAILWAY_VARIABLES.md` and README agree; user-facing docs use literal URLs and steps a non-expert can follow.

## Commands

```bash
# Backend (Python 3.11; 3.10 works)
pip install -r requirements-dev.txt      # local; CI y Colab usan requirements-test.txt
ruff check backend tests scripts                                    # sintaxis + pyflakes
APP_DEMO_MODE=true uvicorn backend.main:app --reload --port 8000   # synthetic data, no Snowflake
pytest -q                                                           # 127 tests

# Frontend (Node 22)
cd frontend && npm ci && npm run dev      # http://localhost:5173, proxies /api → :8000
cd frontend && npm test                   # vitest (parser SSE, contexto del hilo, render)
cd frontend && npm run build              # tsc -b + vite build → frontend/dist (served by FastAPI)

# Docker (what Railway runs)
docker build -t tejido . && docker run --rm -p 8080:8080 -e APP_DEMO_MODE=true tejido

# Utilities
python scripts/reformatear_excel.py ENTRADA.xlsx --dir SALIDA/     # old flat Excel → new formatted workbook
python scripts/vista_previa_excel.py LIBRO.xlsx salida.html          # HTML preview of a workbook

# Colab notebooks (notebooks/) — run in Google Colab, not locally
#   Demo_Efimera_TejidoEmpresarial.ipynb        build + uvicorn + TryCloudflare public URL
#   Publicacion_GitHub_TejidoEmpresarial.ipynb  Drive → GitHub (validations, tests, build, tag)
```

## Architecture

```
backend/
  main.py       Assembly only: logging, lifespan (warms the Snowflake session), middleware, routers, /assets mount.
  comun.py      Runtime settings from env (DEMO_MODE, EXPORT_MAX_ROWS, access control…) and shared helpers
                (records, drop_contact_columns, cached_filter_frame, error_consulta, respuesta_archivo).
                Routers reference the connection as `comun.snowflake` so tests/mocks can replace it.
  middleware.py Size limit, optional HTTP Basic, security headers (CSP, HSTS on https, COOP…).
  routers/      salud (/api/health, /api/diagnostico) · empresas (metadata, filters, search, ficha, export)
                · asistente (/api/ia/*) · recursos (glossary, documents, API 404 wildcard, SPA fallback — LAST).
  config.py     ← THE file to edit when data cuts change (PASO 1 periods, PASO 2 export columns).
                Also: filters, QUERY_COLUMNS (63 aliases), CONTACT_COLUMNS + EXPORT_INCLUDE_CONTACT_FIELDS,
                assistant settings (SEMANTIC_VIEW, CORTEX_MODEL, IA_*, NITS_EJEMPLO, ASISTENTE_*_TABLE).
  models.py     Pydantic: SearchRequest (filters | business_name | nit | batch_nits), PreguntaIA (strict
                historial, consulta_ids, sesion_id), DescargaIA (consulta_id).
  queries.py    SQL generation with allowlisted columns and sql_literal (escapes `\` then `'`).
  database.py   SnowflakeService: RSA key auth + rotation, es_error_de_sesion (retry only then),
                filas_con_parametros (bound params, `silencioso` for background writes), calentar(),
                log_event (bound), diagnostico() incl. vista_semantica · tabla_asistente_log · cortex_complete.
  exporter.py   xlsxwriter workbook: Resumen · Ficha_Empresa · Vista_Principal · Datos_Completos · Diccionario;
                create_export(notas=…, aviso=…) and filename_for(prefijo=…) for the assistant listing.
  ia/           analyst.py (Cortex Analyst REST, JWT with the SAME RSA key) · guardas.py (token-based SQL
                validation: read-only, data sources in allowed schemas, top-level LIMIT; figure verification with
                sums/means only when not truncated) · redactor.py (COMPLETE with casts, one call, degradation
                with motivo/error, sondear_complete for the diagnostic) · forma.py (labels, contact detection,
                NIT listing detection) · graficos.py (chart spec + pide_grafica) · resultados.py (LRU+TTL store
                by consulta_id) · telemetria.py (bounded queue → ASISTENTE_CONSULTAS/DESCARGAS, fail-open)
                · exportadores.py (assistant xlsx/pptx) · orquestador.py (pipeline; every exit is registered).

frontend/src/
  api.ts                     json(), preguntarIA (SSE reader; ignores `: latido` comments), exportarIA(formato,
                             consulta_id), obtenerSesionId (sessionStorage), entregarArchivo.
  tipos.ts                   CuerpoResultadoIA, EventoIA, MetaIA (degradado, motivo_degradacion, ms_correccion…).
  componentes/TablaEmpresas  Standard company table (sort, columns, search, ficha link, mobile cards) used by
                             Resultados and by the assistant for listings.
  paginas/Asistente.tsx      Thread with memory (consulta_ids + fallback historial), progress card, Detener,
                             3-state badge, chart on request, listing + standard download, related questions.
  estilos/asistente.css      Assistant styles (progress, badges, memory line, related chips).

snowflake/      TEJIDO_EMPRESARIAL_SEGMENTACION.sv.yaml (semantic view: 23 verified queries; CADENA_EXPORTADA),
                01_permisos (CORTEX_USER + SELECT on the view), 02_comparar_modelos (incl. the options form),
                03_telemetria_asistente (tables, views, grants), 04_minimo_privilegio (revoke UPDATE/DELETE), LEEME.md.
docs/           METRICAS.md (ready SQL), DECISIONES.md (D-01…D-12), BITACORA.md, INCIDENTES.md.
notebooks/      Colab: ephemeral demo + GitHub publisher (Celda A: repo, required files, build commands; version
                synced in frontend/package.json and backend/config.py).
.github/workflows/build.yml   CI: ruff + pytest (demo mode) · vitest + npm run build.
```

## SSE contract (`POST /api/ia/preguntar`)

`etapa {etapa, detalle, ms, sql?}` × n → `resultado {consulta_id, sql, columnas, filas≤500, n_filas, truncado, grafica, mostrar_grafica, es_listado, n_nits, sugerencias, advertencia}` → `final {…same, texto, meta}` — or `error {mensaje}` at any point. Comment lines `: latido` every 10 s. `meta`: modelo, degradado, motivo_degradacion (`redaccion_fallo` | `respuesta_vacia` | `cifras_sin_respaldo` | ''), cifras_verificadas, forma_redaccion, ms_interpretacion, ms_consulta, ms_correccion, ms_redaccion, ms_total, intentos_sql, analyst_request_id, version, vista_semantica. Closing the connection sets the orchestrator's `cancelado` flag (state `detenida`).

## Conventions

- UI language is Spanish (Colombia). Identifiers: Spanish in the frontend and in all **new** backend code (`comun`, `routers`, `ia/*`); the older English identifiers in `config/models/queries/exporter` stay — do not mass-rename. HTTP contract (JSON keys, column labels) never changes without a CHANGELOG entry.
- Design tokens mirror the `celula-ia-gic` reference app: `--tinta #011627`, `--cinta #ffa400`, Jost / Maven Pro / IBM Plex Mono via `@fontsource`; no CDNs. Motion respects `prefers-reduced-motion`.
- Never put credentials or SQL in the frontend. Filters/columns are allowlisted in `backend/config.py`.
- Access is open unless `APP_BASIC_USER` and `APP_BASIC_PASSWORD` are both set (owner's decision, D-07; README explains how to turn it on).
- Excel: identifiers as text, COP without decimals, FOB USD with 2 decimals, navy header + amber accent, frozen panes, autofilter, print setup. Tests in `tests/test_exporter.py` pin this structure.
- Docs for the owner (README, ASISTENTE, RAILWAY_VARIABLES, DIAGNOSTICO_RAILWAY, DESPLIEGUE_NUEVO, VALIDACION) stay in the root and use the literal production URL; engineering docs live in `docs/`.

## Troubleshooting a deployment

`/api/health` reports connector presence, version, missing `SF_*` vars and key sources. `/api/diagnostico` (Basic auth, `APP_DIAG_TOKEN` via `X-Diag-Token` header or `?token=`, or APP_ENV=development) runs the full chain — entorno → conector → llave → sesión → tablas → vista_semantica → tabla_asistente_log → cortex_complete — and returns the first failing step, a concrete recommendation and the telemetry counters. `/estado` renders it for non-technical users. See `DIAGNOSTICO_RAILWAY.md`; for the assistant, `ASISTENTE.md` §5; for metrics, `docs/METRICAS.md`.

## Snowflake objects

- `APP_SEGMENTACION_EXPORTACIONES.SEGMENTACION.TEJIDO_EMPRESARIAL_COMPLETO_BASE_MUNICIPIOS_P` (companies, alias A)
- `APP_SEGMENTACION_EXPORTACIONES.PUBLIC.BIENES_Y_SERVICIOS_P` (export filters, alias B)
- `…SEGMENTACION.FILTROS_GENERALES_TEJIDO_EMPRESARIAL_COMPLETO`, `…SEGMENTACION.FILTROS_EXPORTADORAS` (filter options)
- `…SEGMENTACION.TEJIDO_EMPRESARIAL_SEGMENTACION` (semantic view for Cortex Analyst)
- `…SEGUIMIENTO.EVENTOS` (audit log, INSERT only) · `…SEGUIMIENTO.ASISTENTE_CONSULTAS` / `ASISTENTE_DESCARGAS` (assistant telemetry)

## Environment

See `.env.example` (single source; README and RAILWAY_VARIABLES.md must agree with it). Required for real data: `SF_ACCOUNT`, `SF_USER`, `SF_DATABASE`, `SF_SCHEMA`, `SF_WAREHOUSE`, `SF_ROLE` and one private key (`SF_PRIVATE_KEY_B64_1` or `SF_PRIVATE_KEY_PATH_1`). The assistant needs no new secret.
