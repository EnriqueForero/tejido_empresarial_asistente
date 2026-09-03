# Validación · Tejido Empresarial React 3.4.0

Fecha: 2 de septiembre de 2026. Entorno: Windows 11, Python 3.10.5 (venv), Node 22.23.2 (portable), Chrome headless para capturas.

## Comprobaciones ejecutadas

| Área | Resultado |
|---|---|
| `pytest -q` | 75 pruebas aprobadas: API en modo demo (metadatos, filtros dependientes, búsqueda por filtros/razón social/NIT/lote, ficha por NIT, glosario, exportación, SPA, rutas desconocidas, filtros no permitidos), generación SQL (listas blancas, escape, paginación, NIT sólo dígitos), Excel (estructura de hojas, paneles congelados, autofiltro, identificadores como texto, secciones de la ficha, estados del diccionario, nombres de archivo, neutralización de fórmulas). |
| `python -m compileall backend scripts` | Sin errores. |
| `tsc -b` + `vite build` | Sin errores de tipos; bundle principal 266 kB (84 kB gzip) más páginas cargadas bajo demanda. |
| Servidor real (uvicorn, `APP_DEMO_MODE=true`) | `/api/health`, `/api/metadata`, búsquedas, ficha, glosario y exportación responden correctamente; SPA servida desde FastAPI con cabeceras de seguridad. |
| Recorrido en navegador (1440 px) | Portada con animación, consulta (4 modos), filtros dependientes verificados en vivo (Antioquia → Itagüí, Medellín, Rionegro), resultados con tabla, orden, columnas y paginación, ficha de empresa, glosario, metodología. Sin errores de consola. |
| Recorrido en navegador (375–390 px) | Encabezado con menú, portada, modos en dos columnas, resultados en tarjetas, ficha en una columna, botón flotante de filtros. Sin desbordamiento horizontal. |
| Excel generado | Revisado con openpyxl y vista HTML: hojas `Resumen`, `Ficha_Empresa` (una empresa), `Vista_Principal` (paneles C7, autofiltro), `Datos_Completos` (paneles D7), `Diccionario` (63 definiciones validadas/complementarias; columnas ajenas al glosario marcadas como pendientes). |
| Archivos de salida suministrados | Los tres libros originales fueron regenerados con el nuevo formato en `salidas-ejemplo-formateadas/` mediante `scripts/reformatear_excel.py`. |
| Notebook de demo efímera | Ejecutada su lógica fuera de Colab: localización del proyecto por marcadores, preparación del entorno con contraseña generada, arranque de la API, verificación de `/api/health` y de la portada, prueba de humo (metadatos, búsqueda, ficha, Excel de 25 kB, glosario), bloqueo con HTTP 401 sin credenciales y apagado limpio. |
| Normalización de la llave privada | 10 pruebas con una llave RSA generada al vuelo: Base64 de DER con espacios y saltos de línea, DER cifrado con la frase correcta, DER cifrado sin frase y con frase equivocada (mensajes claros), PEM pegado directamente, Base64 de un PEM, valor que no es Base64, y redacción de secretos en los mensajes. |
| Endpoint `/api/diagnostico` | 5 pruebas: cerrado con 403 en un despliegue sin protección, abierto con `APP_DIAG_TOKEN` correcto y cerrado con uno incorrecto, abierto con HTTP Basic, señalamiento del paso `llave_1` cuando el valor no sirve, y `/api/health` reportando las variables faltantes sin exponer valores. |
| Diagnóstico contra una conexión real que falla | Ejecutado con una cuenta inexistente y una llave válida: los pasos `entorno`, `conector` y `llave_1` pasan, `sesion` falla con el código real de Snowflake (290404) y el conjunto responde en 10 segundos. |
| Página `/estado` en modo demostración | Insignia azul «Modo demostración» en el encabezado, tarjeta con la explicación, tres pasos para salir del modo demostración y detalle del servicio con los campos marcados «No aplica en modo demostración». |
| Página `/estado` con Snowflake mal configurado | Al abrirla comprueba la conexión sola (sin pulsar nada) y en unos segundos pasa a «Conexión con problemas»; con `?token=…` ejecuta el diagnóstico y muestra `✓ Variables`, `✓ Conector`, `✓ Llave privada 1` y `✗ Sesión establecida con Snowflake` con el error real y la recomendación. El encabezado cambia a la insignia ámbar al mismo tiempo. |
| Estado honesto de la conexión | Con todas las variables presentes pero sin ninguna consulta hecha, `/api/health` responde `configured` y la interfaz dice «Sin verificar»; sólo después de que Snowflake responde pasa a `connected` y «Datos reales». Cubierto por dos pruebas automáticas. |
| Consulta contra el despliegue real | `POST /api/filters/options` y `POST /api/companies/search` en `tejidoempresarialreact-production.up.railway.app` respondían 502 con la conexión verificada. Reproducido el motivo: la imagen no traía `pyarrow`, así que `to_pandas()` del conector falla con «Optional dependency: pandas is not installed». Corregido en `requirements-api.txt` y con una vía alterna por filas. |
| Lectura de resultados sin `pyarrow` | Cuatro pruebas con un resultado simulado: mismas columnas y filas por las dos vías, importes numéricos (para que el Excel aplique formato de moneda), columnas conservadas en un resultado vacío. |
| Mensaje de error con la causa | Servidor en modo producción contra una cuenta inexistente: `POST /api/filters/options` responde «No fue posible cargar los filtros. Causa: … 290404 (08001) … Más detalle en la página /estado» y la interfaz lo muestra dentro del panel de filtros, junto a los desplegables vacíos. |
| Desglose de tiempos | La respuesta informa `ms_interpretacion`, `ms_consulta`, `ms_redaccion` y `ms_total`, y la interfaz los muestra bajo cada respuesta: «Interpretar la pregunta 6,2 s · consultar la base 4,1 s · redactar 21,7 s (claude-3-5-sonnet)». Verificado en navegador. |
| Tamaño del prompt | Una tabla de 30 filas por 20 columnas pasaba 35.205 caracteres al modelo; con el recorte quedan 4.988 y el texto declara las filas omitidas. Una tabla angosta de 30 filas no pierde ninguna. |
| Coherencia de dependencias | `tests/test_dependencias.py` compara `requirements-api.txt` con `requirements-test.txt`. Se comprobó que **detecta el fallo real**: al quitar `python-pptx` de la lista de pruebas, el conjunto falla nombrando el paquete que falta; al restaurarlo, pasa. También verifica que las versiones compartidas coincidan y que no queden excepciones obsoletas. |
| Entorno limpio tipo Colab | Venv nuevo con `pip install -r requirements-test.txt` y `pytest -q`: es exactamente lo que ejecuta el build de validación del notebook. |
| Asistente · guardas de SQL | Cinco pruebas: se rechazan DELETE, UPDATE, CREATE y las sentencias múltiples; se rechaza cualquier esquema fuera de la lista; se impone `LIMIT` cuando la consulta no lo trae y se respeta el que ya viene; un comentario no puede esconder una instrucción prohibida. Verificado además que una SQL peligrosa **no llega a ejecutarse**: la lista de consultas del servicio queda vacía. |
| Asistente · verificación de cifras | Cuatro pruebas: una cifra inventada se detecta; los redondeos de la tabla se aceptan; «USD 48.939 millones» se reconoce como equivalente a 48.938.863.957,94; los años y los ordinales no cuentan como invención. En el flujo completo, una redacción con una cifra sin respaldo se reemplaza por el resumen de los datos y la respuesta lo declara. |
| Asistente · elección de gráfica | Siete pruebas sobre las formas: una medida → barras de un tono; dos dimensiones → apiladas ordenadas de mayor a menor; un solo número → cifra destacada, no una barra; columnas por año → líneas; un listado sin cifras → sin gráfica; 30 categorías → 19 mayores más «Otros» con la nota del recorte; colores tomados de la paleta en orden fijo. |
| Asistente · paleta de la gráfica | `validate_palette.js` sobre los ocho tonos y la superficie blanca del aplicativo: banda de luminosidad, croma, separación bajo daltonismo (ΔE 9,1) y umbral de visión normal (ΔE 19,6) **pasan**. El contraste emite advertencia, cubierta porque toda gráfica va acompañada de la tabla y de las cifras escritas. |
| Asistente · flujo completo | Con dobles de Cortex Analyst y de la sesión: las etapas se emiten en orden (interpretando → validando → consultando → datos → redactando), el resultado trae texto, tabla, gráfica, advertencia y la marca de cifras verificadas, y queda registrado en la auditoría del aplicativo. Si la consulta falla se pide **una** corrección informando el error exacto y, si vuelve a fallar, se responde con el mensaje real de Snowflake. |
| Asistente · descargas | El Excel generado trae las hojas `Respuesta` y `Datos`, con la pregunta, el texto, la consulta SQL, la advertencia de IA y los identificadores como texto (`900123456` no se convierte en número). La presentación trae portada, tabla paginada y lámina de trazabilidad con la SQL y la advertencia. |
| Asistente · interfaz | Recorrido en navegador con el asistente simulado: la pregunta sugerida devuelve texto, gráfica de barras apiladas por departamento y tamaño (24 filas) y la tabla; los sellos muestran «Cifras verificadas contra la tabla», el conteo de filas y el tiempo. Sin errores de consola. |
| Asistente en móvil (390 px) | Sin desbordamiento horizontal (`scrollWidth` = `innerWidth` = 390). La gráfica conserva su tamaño legible y se desplaza dentro de su propia caja, igual que la tabla; los botones de descarga se reparten en dos filas. |
| Insignia en móvil (390 px) | Punto de color junto al botón de menú, enlazado a `/estado`; la página completa se lee sin desbordamiento horizontal (`scrollWidth` = `innerWidth` = 375). |
| Notebook de publicación | Ejecutada su lógica sin tocar GitHub: configuración, detección de ambigüedad entre dos copias del proyecto, sincronización de la versión en `frontend/package.json` y `backend/config.py`, disciplina de CHANGELOG, pre-flight (134 archivos · 2,9 MB), bloqueo de una llave `.der` y de un `.env`, detección de un token de GitHub incrustado, y los cuatro comandos de build reales (pip, pytest, `npm ci`, `npm run build`) en 92 s con limpieza posterior. |

## Capturas

Carpeta `previews/` del paquete de entrega: portada (escritorio y móvil), consulta, resultados, búsqueda por razón social, lote de NIT, ficha de empresa, glosario, metodología, vistas previas de los Excel y las tres vistas nuevas de la página de estado (modo demostración, diagnóstico paso a paso y versión móvil) y cuatro del asistente (inicio, respuesta con gráfica y tabla, versión móvil y el destacado de la portada).

## Validaciones que requieren el entorno del propietario

- **Cortex Analyst y Cortex COMPLETE.** No se dispuso de credenciales en este entorno: el cliente REST, la firma del token y la redacción se validaron con dobles y por revisión estática. La huella de la llave se comprobó idéntica a la que publica `DESC USER`. La prueba real es la del paso 4 de `ASISTENTE.md`.
- **Snowflake.** No se dispuso de credenciales en este entorno; la conexión, la rotación de llaves y las consultas se validaron por revisión estática y pruebas unitarias del SQL generado. Verifique en Railway abriendo `/estado`: la página hace la prueba sola y dice si el aplicativo quedó conectado.
- **Docker.** El equipo de validación no tiene Docker Engine; la imagen no se construyó localmente. El `Dockerfile` fue revisado paso a paso (npm ci + build, pip install, usuario sin privilegios, health check) y la compilación del frontend que alimenta la imagen se ejecutó con éxito.
- **Descarga en navegador real.** El flujo de descarga (blob → archivo) se verificó a nivel de API y de código; confirme en el navegador institucional que el archivo se guarda con el nombre esperado.

## Lo que no se pudo probar de los notebooks

- La ejecución **dentro de Colab** (montaje de Drive, instalación de Node por
  `apt-get`, túnel de TryCloudflare y lectura de secretos) requiere el entorno
  de Colab; se validó toda la lógica que no depende de él.
- El **push real a GitHub** requiere el `GITHUB_TOKEN`. La celda
  `diagnosticar_token()` está incluida precisamente para separar las causas de
  un fallo de credenciales antes de publicar.

## Decisiones de esta versión

- Acceso abierto por defecto, como la versión Streamlit; HTTP Basic opcional.
- Campos de contacto incluidos por defecto en la descarga, como la versión Streamlit; excluibles por variable.
- Dos rangos derivados sin definición en el glosario institucional se documentan como «definición complementaria del aplicativo».
