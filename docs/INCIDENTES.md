# Incidentes y lo que dejaron

Cada incidente que costó tiempo real, con la causa de fondo y la protección que
quedó en el código para que no se repita. Se escribe para quien herede el
aplicativo: la causa de un fallo casi nunca está donde aparece el error.

| Fecha | Incidente | Protección que quedó |
|---|---|---|
| 2026-09-02 | Publicación falla en Colab: falta `cryptography` | `requirements-test.txt` + `tests/test_dependencias.py` |
| 2026-09-03 | Producción responde 502 en filtros y búsqueda con la conexión verificada | `snowflake-snowpark-python[pandas]`, vía alterna sin pyarrow, causa real en el mensaje |
| 2026-09-03 | Publicación falla en Colab: falta `python-pptx` | La misma prueba de dependencias (lo atrapó al tercer intento de la misma causa) |
| 2026-09-03 | El notebook deja el proyecto a medio versionar | La comprobación del CHANGELOG va antes de escribir; tag existente con salida explícita |
| 2026-09-04 | Una respuesta tarda 149,5 s y sale como «Cifras verificadas» con el resumen de respaldo | Un fallo cuesta una llamada; degradación visible con causa; telemetría de todas las salidas |
| 2026-09-04 | Inyección SQL por barra invertida en razón social y filtros | `sql_literal` escapa `\` antes que `'`; auditoría con parámetros enlazados |
| 2026-09-04 | El validador de SQL no leía la sentencia como Snowflake: `//` y `$$…$$` escondían un `UNION` a otro esquema | Lector de fichas con las tres formas de comentario y las dos de cadena; se rechaza lo que quede sin cerrar |
| 2026-09-04 | Un candado no reentrante dejaba colgada la primera pregunta del servicio | `threading.RLock` y una prueba que crea el orquestador |
| 2026-09-04 | Cuarta publicación fallida: una prueba importaba a otra y en Colab el módulo no existía | `tests/dobles.py` + `pythonpath` en `pyproject.toml`; la batería corre desde cualquier directorio |

---

## 2026-09-04 · La redacción falló y se vio como lentitud

**Lo que se vio.** «135 fila(s) · 149,5 s · Interpretar 56,9 s · consultar 3,3 s
· redactar 88,7 s», y debajo el texto «La consulta devolvió 135 fila(s). Primer
registro → …» con el sello verde «Cifras verificadas contra la tabla».

**Causa.** Cortex COMPLETE falló (privilegio, modelo o firma; la telemetría de
esta versión lo dirá). El aplicativo (a) reintentaba con sesión nueva ante
*cualquier* excepción, (b) caía de la forma con opciones a la simple ante
*cualquier* error, y (c) la forma simple no tenía tope de fichas. Cuatro
llamadas y dos reaperturas de sesión: 88,7 s. La interfaz sólo miraba
`cifras_verificadas` —que el resumen determinista siempre cumple— y nunca
`degradado`.

**Protección.** `database.es_error_de_sesion` decide cuándo vale reintentar;
`redactor.es_error_de_firma` cuándo vale la forma simple; `meta.motivo_degradacion`
y tres estados en pantalla; `ASISTENTE_CONSULTAS.ESTADO = 'degradada'` con la
causa; el paso «cortex_complete» del diagnóstico ejecuta la sentencia real.
Pruebas: `test_una_redaccion_fallida_se_declara_degradada_con_su_causa`,
`test_un_error_del_modelo_no_dispara_la_forma_simple`.

## 2026-09-04 · `sql_literal` no escapaba la barra invertida

**Lo que se vio.** Nada: lo encontró la auditoría de código. `sql_literal("x\\' OR 1=1 --")`
producía un literal abierto porque Snowflake acepta `\'` como comilla escapada.
Afectaba a la búsqueda por razón social y a los valores de filtro (el NIT ya
pasaba por `clean_nit`); también `log_event` interpolaba texto en el INSERT.

**Protección.** `sql_literal` escapa `\` y luego `'`;
`test_un_literal_con_barra_invertida_queda_cerrado`. `log_event` y la telemetría
usan parámetros enlazados. Las guardas del asistente trabajan por fichas y
rechazan `IDENTIFIER(…)`, variables de sesión, nombres sin calificar y listas
de tablas separadas por comas fuera de los esquemas permitidos.

## 2026-09-04 · El validador y Snowflake no leían la misma consulta

**Lo que se vio.** Nada en producción: lo encontró la revisión adversaria de la
propia versión 3.5.0, con un banco de pruebas que intentaba burlar las guardas.

**Causa.** `validar_sql` quitaba los comentarios `--` y `/* */` con expresiones
regulares y no conocía ni `//` ni las cadenas `$$…$$`, que Snowflake sí acepta.
Una comilla dentro de un comentario `//` desplazaba los límites de los literales:
el validador creía que un tramo era texto y Snowflake lo ejecutaba como SQL. Con
eso, una consulta propuesta por el modelo podía leer `SEGUIMIENTO.EVENTOS` —fuera
de los esquemas permitidos— o fingir un `LIMIT` que no existía. La lección de
fondo: **si el validador y el motor no leen lo mismo, lo validado no es lo
ejecutado.**

**Protección.** Un lector de fichas único (`leer_fichas`) reconoce las tres
formas de comentario y las dos de cadena, y toda construcción sin cerrar se
rechaza en vez de interpretarse. Sobre esas fichas se hacen ahora todas las
comprobaciones, incluidas las CTE (antes se buscaban en el texto crudo, así que
un literal podía dar de alta una tabla). `tests/test_endurecimiento.py` fija
cada vía cerrada.

## 2026-09-04 · Un candado no reentrante colgaba la primera pregunta

**Lo que se vio.** Las pruebas del asistente dejaron de terminar: el proceso se
quedaba en la primera descarga.

**Causa.** Al sustituir `lru_cache` por dos singletons con candado —para que dos
preguntas simultáneas al arrancar no crearan dos orquestadores— `orquestador_ia`
pedía la telemetría **dentro** de su propio candado, y `threading.Lock` no es
reentrante. En producción habría colgado la primera pregunta del servicio.

**Protección.** `threading.RLock` y una prueba que construye el orquestador; el
tiempo de la batería de pruebas volvió de «no termina» a 18 s.

## 2026-09-04 · Cuarta publicación fallida: una prueba importaba a otra

**Lo que se vio.** El build del notebook, en Colab, con Python 3.13:
`ModuleNotFoundError: No module named 'tests.test_asistente_fase1'` en tres
pruebas de `tests/test_endurecimiento.py`. En el equipo de desarrollo pasaban.

**Causa.** Esas tres pruebas reutilizaban los dobles (`_Servicio`, `_Analyst`,
`_correr`) importándolos **de otro archivo de pruebas**. pytest carga cada
`test_*.py` como módulo de primer nivel, así que el nombre `tests.test_x` sólo
existe si la raíz del proyecto quedó en la ruta de módulos —cosa que dependía
del directorio de trabajo y de cómo se invocara pytest—. Al medirlo se vio que
el problema era mayor de lo que parecía: desde otro directorio, ni siquiera
`import backend` funcionaba.

**Protección.** Los dobles viven en `tests/dobles.py`, un módulo que no es una
prueba, y `pyproject.toml` declara `pythonpath = [".", "tests"]`, de modo que
pytest pone la raíz y la carpeta de pruebas en la ruta de módulos **antes** de
recoger nada. Comprobado de cuatro maneras —`pytest` y `python -m pytest`, desde
la raíz y desde otro directorio— y en una copia limpia del proyecto, que es lo
que hace Colab. Además el notebook ahora exige los archivos nuevos y corre
`npm test`, como la integración continua.

**Lección, ya por cuarta vez en esta familia:** una comprobación que sólo se
ejecuta en el equipo de desarrollo no comprueba nada. Lo que valida la
publicación tiene que correr en las mismas condiciones que la publicación.

## 2026-09-03 · pyarrow ausente en la imagen

**Lo que se vio.** `/estado` decía «Datos reales · verificado» y las búsquedas
respondían 502. La conexión funcionaba; `to_pandas()` no.

**Causa.** `snowflake-snowpark-python` sin el extra `[pandas]` no trae pyarrow y
el conector no puede devolver DataFrames. El mensaje de error no llegaba al
usuario.

**Protección.** `requirements-api.txt` instala `[pandas]`; `database._a_pandas`
tiene una vía alterna por filas; `/api/health` informa `pandas_arrow`; los
mensajes de error incluyen la causa redactada.

## 2026-09-02 → 2026-09-03 · Tres publicaciones fallidas por dependencias

**Causa.** El notebook mantenía a mano su lista de paquetes y se desviaba de la
del aplicativo: faltó `cryptography`, luego `pyarrow`, luego `python-pptx`.

**Protección.** `requirements-test.txt` es del proyecto (no del notebook) y
`tests/test_dependencias.py` falla si una dependencia de producción no está
allí. El error aparece donde está la causa.
