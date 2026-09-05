# Registro de cambios

Todas las versiones relevantes de **Tejido Empresarial · ProColombia**.
Formato: [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) · Versionado: [SemVer](https://semver.org/lang/es/).

Para un aplicativo de este tipo: **PATCH** corrige textos, estilos o errores; **MINOR** agrega funciones o secciones compatibles; **MAJOR** cambia la arquitectura o el contrato de datos.

---

## [3.5.0] — 2026-09-04

Puesta a punto del asistente: rápido cuando puede serlo, honesto cuando no, con
memoria, listados con el formato estándar y métricas en Snowflake.

### Corregido
- **Un fallo de la redacción costaba cuatro llamadas y dos reaperturas de sesión (88,7 s) y se mostraba como «Cifras verificadas».** Ahora un fallo de Cortex COMPLETE cuesta una llamada; sólo un error de firma de la función (inmediato) permite probar la forma simple, una vez; la sesión con Snowflake se reabre sólo ante errores de sesión o de red. La respuesta degradada llega en segundos con su causa (`meta.motivo_degradacion`) y la interfaz distingue tres estados: cifras verificadas · resumen automático por fallo de redacción · cifras sin respaldo descartadas.
- **Inyección SQL por barra invertida** en la búsqueda por razón social y en los valores de filtro: `sql_literal` escapa `\` antes que `'`. La auditoría (`log_event`) usa parámetros enlazados.
- La forma con opciones de COMPLETE (`max_tokens`, `temperature`) usa casts explícitos (`TO_ARRAY`, `TO_OBJECT`); el diagnóstico (`/estado`) tiene el paso «cortex_complete», que ejecuta la sentencia real y dice qué forma admite la cuenta.
- Las descargas del asistente traen **todas** las filas obtenidas (antes, sólo las 500 que viajaban al navegador) y salen del servidor por `consulta_id`; si el resumen aún estaba en redacción, el archivo lo declara.
- El tope de filas ya no envuelve la consulta en `SELECT * FROM (…)`: se ajusta el LIMIT de nivel superior o se añade al final, y el ORDER BY se conserva.
- El desglose de tiempos separa la corrección de la consulta (`ms_correccion`, `intentos_sql`) del tiempo de consulta.
- Un total o promedio correcto ya no degrada la respuesta: `verificar_cifras` acepta la suma y el promedio de cada columna cuando el resultado está completo (nunca si se recortó).
- `IA_ANALYST_TIMEOUT` pasa de 90 a 45 s: más de 45 s casi siempre es un fallo, y esperar sólo alarga el error.

### Corregido tras la revisión adversaria de esta misma versión
- **Las guardas leen la SQL como la lee Snowflake.** El validador no conocía los comentarios `//` ni las cadenas `$$…$$`, así que una comilla dentro de ellos desplazaba los límites de los literales y escondía un `UNION` a otro esquema, o un `LIMIT` que no existía. Ahora un lector de fichas reconoce las tres formas de comentario y las dos de cadena, y **rechaza** cualquier comentario o cadena sin cerrar en vez de interpretarlo.
- Se cierran otras cuatro vías por las que un origen de datos escapaba de los esquemas permitidos: los *stages* (`FROM @~`), los JOIN entre paréntesis (`FROM t1 JOIN (t2 JOIN t3 ON …)`), la coma después de `ON`/`USING`, y un literal con el texto «WITH X AS (» que daba de alta una tabla como si fuera una consulta común. `FETCH FIRST n ROWS ONLY` también se acota al tope de filas.
- **Menos respuestas degradadas sin motivo.** Un rango de años («2021-2025») o una raya («—231.544 empresas—») ya no se leen como cifras negativas huérfanas; a la vez, una cifra inventada con separador de miles («1.950 empresas») deja de pasar por año.
- La corrección de una consulta fallida se pide con la conversación completa: antes se enviaba la SQL del analista sin la pregunta que la originó, y con dos mensajes de usuario seguidos.
- El resumen automático de respaldo ya no se vuelve a examinar: revisar sus cifras sólo podía borrar la causa real de la degradación.
- **Un interbloqueo dejaba colgada la primera pregunta del servicio** (el candado que crea el orquestador se pedía dos veces de forma anidada). Detectado por las pruebas antes de publicar.
- La interfaz ya no se queda con el aviso «Redactando el resumen…» para siempre cuando la petición falla o se corta después de recibir la tabla, ni al recargar la página a mitad de una redacción; si `/api/ia/estado` no responde, la página lo dice en vez de quedarse en «Preparando el asistente…».
- Detalles: el menú de columnas de cada tabla tiene identificador propio (varias tablas en el mismo hilo se pisaban), el cronómetro no interrumpe a los lectores de pantalla, las descargas viajan en trozos de 64 KB en vez de línea por línea, un token de diagnóstico con acentos responde 403 y no un error interno, el hilo de la telemetría no puede retirarse dejando registros sin consumir, y el listado del asistente declara cuántos NIT encontró y cuántos registros trae el archivo.
- **La batería de pruebas ya no depende del equipo donde se ejecuta.** Los dobles compartidos viven en `tests/dobles.py` (ninguna prueba importa a otra) y `pyproject.toml` declara `pythonpath`, así que `pytest` y `python -m pytest` funcionan desde cualquier directorio. Es lo que rompió la primera publicación de esta versión en Colab.
- **Ninguna prueba puede abrir una conexión real con Snowflake.** `tests/conftest.py` anula la lectura del `.env` y vacía las variables `SF_*`: en un equipo con credenciales, la batería intentaba conectarse —y hasta llamar a Cortex— mientras que en Colab pasaba de largo.
- **El notebook de publicación se valida con la batería.** `tests/test_notebook.py` comprueba que todo archivo que el cuaderno exige exista, que su build cubra lo mismo que la integración continua (`ruff`, `pytest`, `npm test`, `npm run build`), que nunca publique cachés y que la versión coincida en el backend, en `package.json` y en el candado de npm. La quinta publicación fallida de esta familia se detecta ahora al ejecutar `pytest`, no en Colab.
- El cuaderno, además, alinea la versión del candado de npm, excluye `.ruff_cache` y comprueba antes de publicar que `package-lock.json` no se haya desviado de `package.json` (`npm ci` falla en seco si eso ocurre).
- Modelo semántico: se retiran cinco sinónimos repetidos (la especificación los exige únicos), se corrige la fecha de verificación, se alinea la descripción de la cadena de segmentación con la metodología publicada y se deja de declarar el NIT como llave única, porque unas decenas de empresas tienen más de una sede.

### Agregado
- **Memoria del hilo.** El servidor reconstruye el contexto de las últimas 2 preguntas con el contenido real de Cortex Analyst (`consulta_ids`); el navegador conserva sólo el esqueleto del hilo (nunca filas). Línea de memoria, «Empezar un hilo nuevo» y consultas relacionadas.
- **Listados con el formato estándar.** Cuando la respuesta trae NIT, se muestra con la misma tabla de la sección de consulta (orden, columnas, ficha, tarjetas en móvil) y se descarga con «Descargar listado con formato estándar»: el libro de siempre (Resumen · Vista_Principal · Datos_Completos · Diccionario) con la pregunta, la consulta y la advertencia de IA en el Resumen.
- **Gráfica bajo pedido.** La tabla es la respuesta por defecto; la gráfica se abre sola si la pregunta la pide («gráfica», «barras», «evolución»…) o si el resultado es una sola cifra; siempre queda el botón «Ver gráfica».
- **Métricas del asistente en Snowflake.** `SEGUIMIENTO.ASISTENTE_CONSULTAS` y `ASISTENTE_DESCARGAS` con todas las salidas (éxito, degradada, rechazada, fallo, detenida), tiempos por etapa y causa; vistas `V_ASISTENTE_DIARIO` y `V_ASISTENTE_CALIDAD`; `snowflake/03_telemetria_asistente.sql`; `docs/METRICAS.md`. Si la tabla no existe, el asistente sigue y el diagnóstico muestra los descartes.
- Tarjeta de progreso con cronómetro y etapas, latido SSE cada 10 s y botón **«Detener»** que detiene el trabajo en el servidor.
- NIT de ejemplo reales (890903938, 811000740, 890912462) en la consulta directa, el lote, la pregunta sugerida y el modelo semántico (`NITS_EJEMPLO`).
- Columnas con etiqueta legible («Departamento de la empresa» en vez de `DEPARTAMENTO_EMP`); campos de contacto gobernados por `EXPORT_INCLUDE_CONTACT_FIELDS` también en el asistente.
- Modelo semántico: 23 consultas verificadas (una por cada pregunta sugerida y una cadena de refinamiento conteo → filtro → listado), 2025 como año por defecto, `CADENA_EXPORTADA`, contrato de listados sin contacto, instrucciones de continuidad, métricas faltantes, 10 dimensiones inútiles retiradas; `tests/test_modelo_semantico.py`.
- Arquitectura: `backend/main.py` (887 líneas) repartido en `comun.py`, `middleware.py` y `routers/{salud,empresas,asistente,recursos}.py`, con prueba de contrato de rutas; HSTS y COOP; `APP_DIAG_TOKEN` también por cabecera `X-Diag-Token`; sesión abierta al arrancar; `client_session_keep_alive` y `STATEMENT_TIMEOUT_IN_SECONDS` (300 s).
- `snowflake/04_minimo_privilegio.sql` (retira UPDATE/DELETE sobre EVENTOS y documenta la revisión de `APPS_MANAGER`); `docs/DECISIONES.md`, `docs/BITACORA.md`, `docs/INCIDENTES.md`; CLAUDE.md con invariantes y definición de terminado; README con «Activar usuario y contraseña».
- `ruff` (sintaxis y pyflakes) y `vitest` (tres pruebas de la interfaz) en la integración continua.

### Cambiado
- `POST /api/ia/exportar/{excel,pptx}` reciben `{consulta_id}` en vez de la tabla; nuevo `POST /api/ia/exportar/empresas`. `PreguntaIA` valida el historial estrictamente y acepta `consulta_ids` y `sesion_id`.
- Pregunta sugerida «Principales sectores económicos por cadena…» → «Principales actividades económicas (CIIU) por cadena productiva en Antioquia» (las no exportadoras no tienen sector).
- Documentación al dominio nuevo `tejidoempresarialasistente-production.up.railway.app`.
- Pruebas de backend: 78 → 150 (17 fijan cada vía cerrada en la revisión adversaria y 6 validan el propio cuaderno de publicación).

## [3.4.2] — 2026-09-03

### Corregido
- **La redacción ya no hace esperar a la tabla.** El resultado (tabla, gráfica y consulta SQL) se entrega en cuanto Snowflake responde, y el resumen escrito llega después. Antes había que esperar a que el modelo terminara —unos 40 segundos— para ver algo que ya estaba calculado a los 10.
- **Se acota la salida del modelo** con `max_tokens` y `temperature: 0`. El tiempo de generación es aproximadamente proporcional al número de fichas de salida; sin tope, un modelo puede extenderse sin necesidad. Si la cuenta no admite esa forma de llamada, se cae a la forma simple.
- **La tabla que viaja al modelo pasa de 30 a 20 filas.** Para redactar 2 a 5 frases no hacen falta más; el detalle sigue completo en la tabla y en el Excel.
- **El notebook de publicación validaba el CHANGELOG después de escribir la versión.** Si faltaba la entrada, `package.json` y `backend/config.py` quedaban ya modificados mientras la celda reportaba error, dejando el proyecto a medio versionar. Ahora la comprobación va primero y, si falla, no se toca ningún archivo y se imprime el bloque exacto para pegar.
- **La comprobación del CHANGELOG exige el encabezado** `## [X.Y.Z]` y no una coincidencia suelta del número, que daba un visto bueno falso si la versión aparecía dentro de otra cifra o de una fecha.
- **Un tag ya existente deja de ser un callejón sin salida.** El notebook informa cuál es la siguiente versión libre —consultando los tags reales del repositorio— y ofrece dos salidas explícitas: `publicar(etiquetar=False)` para subir el contenido sin versionar (repositorio de respaldo) y `publicar(mover_tag=True)` para mover el tag a este commit.

### Agregado
- `versiones_publicadas()` y `siguiente_version()` en el notebook.
- Pruebas: 3 nuevas sobre la entrega progresiva y el acotado de la salida del modelo (78 en total).

## [3.4.1] — 2026-09-03

Primera publicación en el repositorio `tejido_empresarial_asistente`, aislado del
anterior. Sin cambios funcionales respecto a 3.4.0: sólo el número de versión.

## [3.4.0] — 2026-09-03

### Agregado
- **Asistente de análisis (`/asistente`)**: una sección nueva para preguntar en español sobre el tejido empresarial y recibir la respuesta escrita, una tabla, una gráfica cuando corresponde y la consulta SQL que la respalda. Responde conteos y cruces (empresas por departamento y tamaño, sectores por cadena productiva en un departamento), rankings (países destino, productos, empresas), comparaciones año corrido, listados por razón social o NIT, y fichas de empresa.
- **El único conector sigue siendo Snowflake.** La pregunta la traduce a SQL **Cortex Analyst** contra el modelo semántico `TEJIDO_EMPRESARIAL_SEGMENTACION`, y la respuesta la redacta **SNOWFLAKE.CORTEX.COMPLETE**: ningún dato sale de la cuenta y no hace falta ninguna credencial nueva —el token de Cortex se firma con la misma llave RSA que ya usa el aplicativo—.
- **El modelo propone y el código dispone.** Antes de tocar la base, el aplicativo exige que la consulta sea una sola sentencia de lectura, sobre los esquemas permitidos y con tope de filas; después comprueba que **cada cifra del texto exista en el resultado** y, si no, reemplaza la redacción por un resumen construido con los datos. La respuesta muestra si las cifras quedaron verificadas.
- **Advertencia de IA en todas partes**: en la portada, en la página, junto a cada respuesta y dentro de los dos archivos que se descargan.
- **Descargas**: libro de Excel (hoja «Respuesta» con la pregunta, el texto, la SQL y la advertencia; hoja «Datos» con la tabla, identificadores como texto y autofiltro) y presentación de PowerPoint (portada, tabla paginada y lámina de trazabilidad).
- **Gráficas propias en SVG**, sin librerías externas: barras de un solo tono para una medida, apiladas para cruces de dos dimensiones, agrupadas para varias medidas, líneas para series por año y cifra destacada para un solo número. La paleta está validada para daltonismo y contraste, y la tabla siempre acompaña a la gráfica.
- **Carpeta `snowflake/`**: el modelo semántico, la especificación del agente y el script de permisos con sus consultas de verificación, versionados junto al código.
- Variables nuevas: `SF_SEMANTIC_VIEW`, `SF_CORTEX_MODEL`, `SF_ALLOWED_SCHEMAS`, `SF_HOST`, `IA_MAX_ROWS`, `IA_MAX_ROWS_CLIENT`, `IA_ANALYST_TIMEOUT`. Todas tienen un valor por defecto correcto.
- **Desglose de tiempos en cada respuesta**: interpretar la pregunta, consultar la base y redactar, con el nombre del modelo que escribió el texto. Sin ese dato, «tardó 50 segundos» no se puede diagnosticar.
- `snowflake/02_comparar_modelos.sql`: mide en la propia cuenta el tiempo de cada modelo candidato con el prompt real del asistente y consulta los créditos consumidos, para elegir `SF_CORTEX_MODEL` con datos y no de memoria.
- Pruebas: 35 nuevas sobre las guardas de SQL, la verificación de cifras, la elección de gráfica, el flujo del asistente, el contenido de las descargas, el tamaño del prompt y la coherencia de las listas de dependencias (75 en total).
- `requirements-test.txt` y `RAILWAY_VARIABLES.md`.

### Cambiado
- La navegación principal y la portada incorporan el asistente; el resto del aplicativo no cambia.
- **Una sola lista de dependencias para las pruebas.** El notebook de publicación y la integración continua instalan `requirements-test.txt` en lugar de una lista escrita a mano. Mantener dos listas ya había causado tres fallos de publicación —faltaron `cryptography`, `pyarrow` y `python-pptx`—; `tests/test_dependencias.py` ahora falla en el propio conjunto de pruebas si una dependencia de producción no está declarada allí, de modo que el error aparece donde está la causa y no en Colab.
- El pre-flight del notebook vigila también los archivos del asistente y los artefactos de Snowflake.
- **La tabla que se envía al modelo se acota por tamaño, no sólo por filas.** Un listado de 30 empresas con 20 columnas ocupaba 35.000 caracteres; ahora se recorta a 6.000 y se declara cuántas filas quedaron fuera. El tiempo de redacción crece con el largo de la entrada, así que esto es tiempo y créditos ahorrados en cada consulta ancha.

## [3.3.1] — 2026-09-02

### Corregido
- **Las consultas fallaban en Railway aunque la conexión estuviera bien.** La imagen se construía sin `pyarrow`, así que `to_pandas()` del conector lanzaba «Optional dependency: pandas is not installed» y devolvían 502 el panel de filtros, la búsqueda, la ficha de empresa y la descarga. El aplicativo Streamlit original sí traía `pyarrow==17.0.0`. Ahora `requirements-api.txt` instala `snowflake-snowpark-python[pandas]`.
- **El aplicativo ya no depende de esa pieza opcional.** Si `pyarrow` falta, los resultados se arman a partir de las filas (`collect()`), como hacía el original; los importes se convierten a número para que el Excel conserve sus formatos. La página de estado indica cuál de las dos vías está en uso.
- **Los errores dicen la causa.** Antes un fallo de consulta respondía «No fue posible…» sin más; ahora incluye el mensaje real de Snowflake, ya redactado, de modo que se puede corregir sin abrir el diagnóstico.
- **El panel de filtros avisa cuando no pudo traer las opciones.** Antes los desplegables quedaban vacíos y el aviso aparecía lejos, debajo de los resultados: parecía que el aplicativo no servía.

### Agregado
- `/api/health` y el diagnóstico informan si el conector puede devolver tablas por la vía rápida (`pandas_arrow`).
- Pruebas: 5 nuevas que fijan la lectura de resultados con y sin `pyarrow`, el registro de la causa de un fallo y su limpieza tras una consulta correcta (40 en total).

## [3.3.0] — 2026-09-02

### Agregado
- **Página «Estado del aplicativo» (`/estado`)**: dice en una frase si el aplicativo consulta datos reales o de demostración, con una pastilla de color en el encabezado visible desde cualquier página (en móvil, un punto de color junto al menú). Al abrirse comprueba la conexión sola, así que da un veredicto sin que nadie pulse nada. Incluye botones para volver a probar y para ver el diagnóstico paso a paso, el detalle del servicio (versión, origen configurado, última conexión correcta, conector, llave, variables faltantes) y las instrucciones concretas para Railway. Acepta `/estado?token=…` para ejecutar el diagnóstico automáticamente.
- **`/api/health` distingue «configurado» de «conectado»**: el servicio sólo afirma que está conectado después de que Snowflake haya respondido de verdad, y devuelve la marca de tiempo de esa última conexión correcta (`verified`, `verified_at`). Antes bastaba con tener las variables puestas para mostrarse en verde.
- **`/api/diagnostico`**: recorre paso a paso entorno → conector → llave → sesión → tablas y devuelve el error real de cada paso, sin exponer secretos, con una recomendación concreta para el primero que falla. En producción exige autenticación HTTP Basic o `APP_DIAG_TOKEN`.
- `/api/health` ahora informa si el conector está instalado, su versión, qué variables `SF_*` faltan y de dónde sale la llave.
- `DIAGNOSTICO_RAILWAY.md`: guía de verificación y solución de fallos de conexión en Railway.
- Variables `APP_DIAG_TOKEN` y `LOG_LEVEL`.
- Pruebas: 18 nuevas sobre normalización de llaves, reporte de configuración, estados del health y el endpoint de diagnóstico (35 en total).
- El build de validación del notebook de publicación instala `cryptography` y, si falla, imprime el final del registro con la causa exacta en lugar de un «Comando falló (1)» sin contexto.

### Corregido
- **La llave privada se normaliza antes de usarla.** Antes, un Base64 con un salto de línea o un espacio al final —lo más frecuente al pegar variables en Railway— hacía fallar la conexión con un mensaje genérico. Ahora se aceptan Base64 con espacios y saltos, PEM pegado directamente, Base64 de un PEM y archivos `.der`/`.p8`; si la llave está cifrada se descifra con la frase configurada y se entrega al conector en DER PKCS8.
- Los errores de conexión dejan de ser genéricos: el mensaje incluye la causa real reportada por Snowflake (sin secretos) y apunta a `/api/diagnostico`.
- Los registros del servicio se envían explícitamente a la salida estándar para que aparezcan en Railway.
- Los avisos de la interfaz usaban una caja flexible que separaba las palabras en negrita; ahora el texto fluye normalmente.
- El estado de la conexión se comparte con `useSyncExternalStore`: antes, si la página `/estado` llegaba por carga diferida en el momento justo, se quedaba indefinidamente en «Consultando el estado…» mientras el encabezado ya mostraba el resultado.
- El health profundo hace un solo intento (antes reintentaba tres veces con espera creciente y tardaba casi medio minuto en responder que no había conexión).
- Las pruebas se omiten con elegancia cuando el entorno no trae `cryptography` o el conector de Snowflake, en lugar de interrumpir toda la ejecución.

## [3.2.0] — 2026-09-02

### Agregado
- `notebooks/Demo_Efimera_TejidoEmpresarial.ipynb`: demostración efímera desde Google Colab (compila el frontend, levanta FastAPI y expone una URL temporal con TryCloudflare). Dos modos de datos: demostración sintética y Snowflake real, este último protegido con usuario y contraseña automáticos.
- `notebooks/Publicacion_GitHub_TejidoEmpresarial.ipynb`: publicación desde Google Drive a GitHub con validaciones, build de validación (frontend y backend), tag `vX.Y.Z` y verificación post-push.
- `.github/workflows/build.yml`: integración continua que ejecuta las pruebas del backend y compila el frontend en cada push y pull request.
- `CHANGELOG.md` (este archivo).

### Cambiado
- El conector de Snowflake se importa de forma tolerante: el modo demostración funciona en entornos donde `snowflake-snowpark-python` no está instalado (por ejemplo Colab con Python 3.12). En producción no cambia nada: `requirements-api.txt` lo instala y `/api/health` reporta el estado real.

## [3.1.0] — 2026-09-02

### Agregado
- Migración completa de la interfaz de Streamlit a **React 19 + TypeScript (Vite 8)** con el sistema de diseño de la familia digital ProColombia (azul noche, ámbar, Jost / Maven Pro / IBM Plex Mono).
- Portada institucional con animación del tejido empresarial convergiendo en los ejes de Exportaciones, Inversión y Turismo.
- Página de consulta con cuatro modos (segmentación, razón social, NIT, lote de NIT), 19 filtros dependientes agrupados con ayuda contextual y consulta compartible por URL.
- Resultados con orden por columna, búsqueda local, selector de columnas, paginación configurable y tarjetas en celular.
- Ficha de empresa (`/empresa/<NIT>`) con indicadores, gráfico de exportaciones por periodo y las 63 variables por secciones.
- Glosario navegable a partir del archivo institucional de variables y sección de metodología.
- Descarga Excel en un paso con hojas `Resumen`, `Ficha_Empresa`, `Vista_Principal`, `Datos_Completos` y `Diccionario`, con nombres descriptivos.
- API FastAPI (`/api/*`) que conserva la lógica de consulta a Snowflake, con auditoría en segundo plano y modo de demostración sintético.
- Imagen Docker única (Node 22 compila, Python 3.11 sirve) y configuración de Railway con health check.
- Documentación: `README.md`, `GUIA_TRANSFERENCIA.md`, `MIGRACION_REACT.md`, `VALIDACION.md` y utilidades en `scripts/`.

### Conservado
- Código Streamlit original íntegro en `legado_streamlit/`, fuera del despliegue.
- Alias, tablas, orden y semántica de las consultas del aplicativo original.
