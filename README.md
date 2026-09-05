# Tejido Empresarial · ProColombia

Aplicativo web para identificar, segmentar y comprender el tejido empresarial colombiano en apoyo a los ejes de **Exportaciones, Inversión y Turismo** de ProColombia (Gerencia de Inteligencia Comercial).

**React 19 + TypeScript (Vite 8)** en el navegador, **Python / FastAPI** en el servidor y **Snowflake** como única fuente de datos y única plataforma de inteligencia artificial (Cortex). Un contenedor Docker compila el frontend y sirve la API y la interfaz desde el mismo origen, desplegado en **Railway**:

**https://tejidoempresarialasistente-production.up.railway.app/**

## Qué incluye

| Área | Detalle |
|---|---|
| Portada | Animación institucional del tejido empresarial conectando los tres ejes; cifras del aplicativo; descripción, beneficios y alcance. |
| Consulta | Cuatro modos: segmentación con 19 filtros dependientes agrupados, razón social, NIT y lote de NIT (archivo o lista pegada). URL compartible por consulta. NIT de ejemplo reales. |
| Resultados | Tabla estándar de empresas (15 variables clave), orden por columna, búsqueda local, selector de columnas, 25/50/100 por página; tarjetas en celular. |
| Ficha de empresa | `/empresa/<NIT>`: indicadores, gráfico de exportaciones por periodo y las 63 variables agrupadas por secciones. |
| Descarga | Excel en un solo paso con hojas `Resumen`, `Ficha_Empresa` (una empresa), `Vista_Principal`, `Datos_Completos` y `Diccionario`; nombres descriptivos con fecha y criterio. |
| Asistente | `/asistente`: preguntas en español resueltas con Snowflake Cortex. Recuerda las últimas preguntas del hilo; devuelve texto verificado, tabla, la SQL que la respalda y la gráfica cuando se pide; los listados de empresas usan la tabla y el Excel estándar. Cada pregunta queda en una tabla de métricas. Toda respuesta lleva la advertencia de que la generó una IA. |
| Estado | `/estado`: si el aplicativo usa datos reales o de demostración, prueba de conexión y diagnóstico paso a paso (incluidos los pasos del asistente). Pastilla de color siempre visible en el encabezado. |
| Glosario | Lectura estructurada del archivo institucional de variables con búsqueda, secciones, fuentes y uso en el aplicativo. |
| Metodología | Fuentes y cortes, definiciones clave, alcance y límites, guía de transferencia. |
| Diseño | Sistema visual de la familia digital ProColombia (Célula de IA · GIC): azul noche `#011627`, ámbar `#FFA400`, Jost / Maven Pro / IBM Plex Mono, logos MinCIT · ProColombia, movimiento respetuoso de `prefers-reduced-motion`. |

## Arquitectura

```text
Navegador ──▶ React + TypeScript (frontend/)      páginas: Inicio · Consultar · Asistente · Glosario · Metodología · Ficha · Estado
                 │  /api/*  (JSON y SSE)
                 ▼
             FastAPI (backend/)
                 ├── main.py         ensambla: registro, arranque (calienta la sesión), middleware, routers
                 ├── comun.py        ajustes de ejecución y utilidades compartidas
                 ├── middleware.py   tamaño de solicitud, HTTP Basic opcional, cabeceras de seguridad
                 ├── routers/        salud · empresas · asistente · recursos (comodines al final)
                 ├── config.py       periodos, filtros, columnas, ajustes del asistente (ÚNICO archivo a editar por corte)
                 ├── queries.py      SQL parametrizado (misma lógica del original; literales escapados)
                 ├── database.py     sesión Snowflake con llaves RSA, rotación, reintento sólo ante sesión caída, diagnóstico
                 ├── exporter.py     libro Excel estándar (xlsxwriter)
                 ├── ia/             asistente: Cortex Analyst → guardas → ejecución → COMPLETE → verificación de cifras;
                 │                   resultados por consulta_id, telemetría, gráficas, exportadores
                 ├── glossary.py · demo.py · resources/
snowflake/       modelo semántico (23 consultas verificadas), permisos, comparación de modelos, telemetría, mínimo privilegio
docs/            METRICAS · DECISIONES · BITACORA · INCIDENTES
```

El código Streamlit original se conserva íntegro en `legado_streamlit/` como referencia; no participa en el despliegue. Los cuadernos de creación de la base de datos siguen en `setup/`.

## Ejecución local

Requisitos: Node.js 20.19 o superior (recomendado 22), Python 3.11 (3.10 también funciona).

```bash
# 1. Frontend (terminal A)
cd frontend
npm ci
npm run dev            # http://localhost:5173 · redirige /api a http://127.0.0.1:8000

# 2. API (terminal B), en la raíz del repositorio
python -m venv .venv
.venv\Scripts\activate          # Windows   |   source .venv/bin/activate  (macOS/Linux)
pip install -r requirements-dev.txt
uvicorn backend.main:app --reload --port 8000
```

Para probar toda la experiencia **sin Snowflake**, active el modo de demostración con datos sintéticos (el asistente se desactiva en ese modo):

```bash
# PowerShell
$env:APP_DEMO_MODE="true"; uvicorn backend.main:app --reload --port 8000
# Bash
APP_DEMO_MODE=true uvicorn backend.main:app --reload --port 8000
```

Para servir el frontend compilado desde FastAPI (como en producción): `cd frontend && npm run build` y abra `http://127.0.0.1:8000`.

## Variables de entorno

`.env.example` es la fuente única. Copie ese archivo a `.env` sólo en desarrollo; en Railway configure las variables desde el panel del servicio ([`RAILWAY_VARIABLES.md`](RAILWAY_VARIABLES.md) trae la lista completa con valores y una plantilla para pegar).

| Variable | Obligatoria | Uso |
|---|:-:|---|
| `SF_ACCOUNT`, `SF_USER`, `SF_DATABASE`, `SF_SCHEMA`, `SF_WAREHOUSE`, `SF_ROLE` | Sí | Conexión a Snowflake (mismos valores que la versión Streamlit). |
| `SF_PRIVATE_KEY_B64_1` | Sí* | Llave RSA DER en Base64 (recomendada en Railway). |
| `SF_PRIVATE_KEY_PASSPHRASE_1` | No | Frase de la llave 1, si está cifrada. |
| `SF_PRIVATE_KEY_B64_2`, `SF_PRIVATE_KEY_PASSPHRASE_2` | No | Segunda llave para rotación/respaldo. |
| `SF_PRIVATE_KEY_PATH_1`, `SF_PRIVATE_KEY_PATH_2` | Sí* | Alternativa local: ruta al archivo `.der`. |
| `APP_ENV` | No | `production` (por defecto) o `development` (habilita `/api/docs` y el diagnóstico). |
| `APP_DEMO_MODE` | No | `true` sólo para demostración con datos sintéticos. |
| `PUBLIC_ORIGIN` | Recomendable | URL pública HTTPS para metadatos sociales. |
| `EXPORT_MAX_ROWS` | No | Máximo de empresas por Excel (por defecto 5.000; hasta 20.000). |
| `EXPORT_INCLUDE_CONTACT_FIELDS` | No | `true` por defecto. `false` retira dirección, teléfono, correo y representante legal de descargas, fichas y asistente. |
| `MAX_REQUEST_BYTES` | No | Tamaño máximo del cuerpo HTTP (2 MB por defecto). |
| `APP_BASIC_USER`, `APP_BASIC_PASSWORD` | No | Si se configuran ambas, todo el aplicativo pide usuario y contraseña (ver abajo). Vacías = acceso abierto. |
| `APP_DIAG_TOKEN` | No | Abre `/api/diagnostico` en producción sin HTTP Basic (`?token=…` o cabecera `X-Diag-Token`). |
| `LOG_LEVEL` | No | `INFO` por defecto. Los registros salen por stdout (visibles en Railway). |
| `SF_LOGIN_TIMEOUT`, `SF_NETWORK_TIMEOUT`, `SF_STATEMENT_TIMEOUT` | No | Segundos para conectar (30), por operación de red (60) y por sentencia en Snowflake (300). |
| `SF_SEMANTIC_VIEW`, `SF_CORTEX_MODEL`, `SF_ALLOWED_SCHEMAS`, `SF_HOST`, `IA_*`, `NITS_EJEMPLO`, `ASISTENTE_*_TABLE` | No | Ajustes del asistente; todos con valor por defecto correcto. Detalle en `RAILWAY_VARIABLES.md` §4. |

\* Configure al menos una llave (Base64 o ruta). Conversión a Base64: PowerShell `[Convert]::ToBase64String([IO.File]::ReadAllBytes("rsa_key_1.der"))` · macOS/Linux `base64 -w 0 rsa_key_1.der`.

## Activar usuario y contraseña

Hoy el aplicativo se sirve **abierto** (igual que la versión Streamlit), por decisión del propietario. Las descargas y las fichas incluyen correo, teléfono y dirección de empresas reales, así que activar el acceso con contraseña es un paso de un minuto que conviene dar:

1. Entre a **Railway → su servicio → pestaña Variables → Raw Editor**.
2. Agregue estas dos líneas (elija un usuario y una contraseña larga; las dos son obligatorias):
   ```
   APP_BASIC_USER=procolombia
   APP_BASIC_PASSWORD=<una contraseña larga y difícil de adivinar>
   ```
3. Guarde. Railway redespliega solo (1 a 2 minutos).
4. Abra `https://tejidoempresarialasistente-production.up.railway.app/`: el navegador pedirá usuario y contraseña. `/api/health` sigue abierto para que Railway compruebe que el servicio vive; todo lo demás queda protegido.
5. Para compartir el acceso, entregue el usuario y la contraseña por un canal distinto del enlace.

Si configura sólo una de las dos variables, el aplicativo responde 503 a propósito hasta que las complete. Para volver al acceso abierto, borre las dos.

## Activar el asistente y sus métricas (una sola vez, en Snowflake)

No hace falta ninguna credencial nueva. En Snowsight, con un rol administrador, ejecute en orden `snowflake/01_permisos_asistente.sql`, `snowflake/03_telemetria_asistente.sql` y `snowflake/04_minimo_privilegio.sql`, y redespliegue el modelo semántico (`snowflake/LEEME.md`). El paso a paso, con qué hacer ante cada error, está en [`ASISTENTE.md`](ASISTENTE.md); las consultas para leer las métricas, en [`docs/METRICAS.md`](docs/METRICAS.md); qué gasta créditos de Snowflake y qué no, en [`docs/COSTOS.md`](docs/COSTOS.md).

## Publicación y demostración desde Google Colab

La carpeta `notebooks/` trae dos cuadernos listos para usar con el proyecto en
Google Drive (`/content/drive/MyDrive/ProColombia/tejido_empresarial_asistente`):

| Notebook | Para qué |
|---|---|
| `Demo_Efimera_TejidoEmpresarial.ipynb` | Compila el frontend, levanta la API en Colab y expone una **URL pública temporal** (TryCloudflare) para revisar el aplicativo antes de desplegarlo. |
| `Publicacion_GitHub_TejidoEmpresarial.ipynb` | Publica de Drive a **GitHub** (`EnriqueForero/tejido_empresarial_asistente`) con validaciones, `ruff`, pruebas del backend, compilación del frontend, `commit`, `push`, tag `vX.Y.Z` y verificación del SHA remoto. |

Flujo recomendado: revisar con la demo efímera → publicar con el notebook →
Railway redespliega solo en cada push. El procedimiento completo está en
[`DESPLIEGUE_NUEVO.md`](DESPLIEGUE_NUEVO.md).

## Despliegue en Railway

1. Suba este directorio a un repositorio Git (sin `.env` ni llaves).
2. En Railway, cree un servicio desde el repositorio: detecta `railway.toml` y construye el `Dockerfile` (Node 22 compila React; Python 3.11 ejecuta FastAPI).
3. Configure las variables `SF_*` y la llave en Base64 (`RAILWAY_VARIABLES.md`).
4. Despliegue. Railway inyecta `PORT`; el health check usa `/api/health`.
5. Verifique `/estado` dentro del aplicativo: **Datos reales**, diagnóstico en verde, una búsqueda, una descarga y una pregunta al asistente.

Si el aplicativo abre pero **no hace búsquedas**, `/estado` dice si está conectado, permite probar la conexión y muestra el paso exacto que falla. El procedimiento completo, escrito para alguien sin experiencia en despliegues, está en [`DIAGNOSTICO_RAILWAY.md`](DIAGNOSTICO_RAILWAY.md).

## Actualizar los cortes de información

Cuando llegue un nuevo mes o se cierre un año, edite **sólo** `backend/config.py` (bloques *PASO 1* y *PASO 2*) siguiendo los comentarios del archivo, reemplace el glosario en `backend/resources/` si cambió, actualice el año por defecto del modelo semántico (`snowflake/LEEME.md`) y vuelva a desplegar.

## Calidad y pruebas

```bash
# Backend: revisión estática + 161 pruebas (API en modo demo, SQL, guardas, redactor, telemetría, Excel, modelo semántico, rutas)
pip install -r requirements-dev.txt
ruff check backend tests scripts
pytest -q

# Frontend: 3 pruebas (parser SSE, contexto del hilo, tabla estándar) + tipos + build de producción
cd frontend && npm test && npm run build

# Imagen Docker
docker build -t tejido-empresarial .
docker run --rm -p 8080:8080 -e APP_DEMO_MODE=true tejido-empresarial
```

La integración continua (`.github/workflows/build.yml`) repite estas comprobaciones en cada push y pull request. `CLAUDE.md` recoge los invariantes del proyecto y la definición de «terminado»; `docs/DECISIONES.md`, las decisiones de arquitectura; `docs/INCIDENTES.md`, lo aprendido de cada fallo; `docs/COSTOS.md`, el consumo de créditos.

Herramientas adicionales en `scripts/`:

- `reformatear_excel.py`: convierte un Excel plano (como los de la versión Streamlit) al nuevo formato con resumen y diccionario.
- `vista_previa_excel.py`: genera una vista HTML de cualquier libro para revisar el formato sin abrir Excel.

## Endpoints

| Método | Ruta | Propósito |
|---|---|---|
| `GET` | `/api/health` (`?deep=true`) | Estado del servicio, conector, variables faltantes; con `deep` prueba Snowflake. |
| `GET` | `/api/diagnostico` | Revisión paso a paso: entorno → conector → llave → sesión → tablas → vista semántica → tabla de métricas → Cortex COMPLETE, con el error real de cada paso y los contadores de telemetría. Protegido en producción. |
| `GET` | `/api/metadata` | Filtros, columnas, secciones, fuentes, cortes, límites y NIT de ejemplo. |
| `POST` | `/api/filters/options` | Opciones dependientes según las selecciones actuales. |
| `POST` | `/api/companies/search` | Vista previa paginada (15 variables clave). |
| `GET` | `/api/companies/{nit}` | Ficha completa de una empresa por NIT exacto. |
| `POST` | `/api/companies/export` | Excel estándar con todos los resultados permitidos. |
| `GET` | `/api/ia/estado` | Disponibilidad del asistente, preguntas sugeridas, NIT de ejemplo, memoria. |
| `POST` | `/api/ia/preguntar` | Pregunta en español; respuesta por SSE: `etapa` → `resultado` → `final` (o `error`), con latido cada 10 s. |
| `POST` | `/api/ia/exportar/excel` · `/pptx` · `/empresas` | Descargas de un resultado guardado en el servidor (`{consulta_id}`): tabla del asistente, presentación, o listado con formato estándar. |
| `GET` | `/api/glossary` | Glosario estructurado. |
| `GET` | `/api/resources/glossary.xlsx` · `/api/resources/methodology.docx` | Documentos institucionales. |

## Seguridad

- El navegador nunca recibe credenciales ni SQL; los filtros y columnas provienen de listas blancas, los valores se escapan como literales (incluida la barra invertida) y todo texto del usuario que llega a un INSERT o a Cortex viaja como parámetro enlazado.
- La SQL que propone Cortex Analyst se valida ficha a ficha antes de ejecutarse: una sola sentencia de lectura, orígenes de datos sólo en los esquemas permitidos, sin `IDENTIFIER(…)`, variables de sesión ni funciones de sistema, y con tope de filas. Cada cifra del texto redactado se verifica contra la tabla.
- Cabeceras `Content-Security-Policy`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Cross-Origin-Opener-Policy` y `Strict-Transport-Security` (en HTTPS); límite de tamaño de solicitud.
- Autenticación HTTP Basic opcional para toda la aplicación (arriba: «Activar usuario y contraseña»).
- Las cadenas que Excel podría interpretar como fórmulas se neutralizan; los identificadores se escriben como texto.
- El rol de Snowflake del aplicativo lee los datos y sólo inserta auditoría y telemetría (`snowflake/04_minimo_privilegio.sql`). La auditoría y la telemetría se registran en segundo plano y nunca bloquean al usuario; nunca guardan filas de resultados ni datos de contacto.
