# Validación · Tejido Empresarial React 3.5.2

Fecha: 5 de septiembre de 2026. Alcance: la respuesta deja de esperar a la
redacción con IA, se cierran dos vías de exposición encontradas usando el
servicio, y se unifica la regla con la que se escribe cada cifra. Al final se
conserva lo verificado en 3.5.1 y en 3.5.0.

## Verificado contra el servicio real, no simulado

Todo lo de esta tabla se comprobó llamando a
`https://tejidoempresarialasistente-production.up.railway.app` el 5 de
septiembre de 2026, con la 3.5.1 desplegada.

| Comprobación | Resultado |
|---|---|
| Cuatro preguntas reales por el mismo flujo SSE que usa el navegador | Las cuatro degradaron. Snowflake responde literalmente `unknown model "claude-3-5-sonnet"`; `ms_redaccion` = 20.610, 20.542, 20.640 y 0. |
| Causa | `/api/ia/estado` devuelve `modelo: "claude-3-5-sonnet"`: la variable `SF_CORTEX_MODEL` está fijada en Railway al modelo retirado, así que el valor por defecto del código nunca se aplicó. |
| El interruptor de 3.5.1 funciona en producción | La cuarta pregunta respondió en **7,36 s** con `motivo = redaccion_pausada` y `ms_redaccion = 0`, en vez de 30 s. |
| Modelos que sí responden en esa cuenta | `claude-haiku-4-5` y `claude-sonnet-4-6`, según la prueba real de `/api/diagnostico?cortex=1`. |
| Región | `AWS_US_EAST_2` con `CORTEX_ENABLED_CROSS_REGION = ANY_REGION`: la hipótesis de la región queda descartada. |
| Tablas de métricas | No existen: nunca se ejecutó `snowflake/03_telemetria_asistente.sql`. Por eso no había registro de preguntas ni respuestas. |
| Modelo semántico | `version_3_5_0_desplegada: false`: la cuenta tiene el YAML de la 3.4.x. |
| Exposición | `/api/docs` responde 200 y `/api/diagnostico` también, sin credenciales: `APP_ENV` no vale `production` en Railway. |
| Descargas | `/api/ia/exportar/excel` y `/api/ia/exportar/empresas` responden 200 con las hojas y las filas correctas; NIT y teléfono como texto, columnas en dólares con dos decimales. |
| Contacto no solicitado | «Lístame las pymes de Agroalimentos en Antioquia que exportan, con NIT» devolvió también correo y teléfono de 100 empresas reales. |

## Comprobaciones de 3.5.2

| Comprobación | Resultado |
|---|---|
| `ruff check backend tests scripts` | Sin hallazgos. |
| `pytest -q` | **178 pruebas en verde** (161 en 3.5.1). |
| `npm test` (vitest) | **15 pruebas en 4 archivos** (10 en 3.5.1). |
| `npm run build` (tsc + Vite) | Limpio. |
| Revisión adversaria | 3 diseños independientes, 3 jueces con criterios distintos, 5 lentes de revisión y una refutación por hallazgo: 46 agentes. De 35 hallazgos, 33 sobrevivieron a la refutación y se corrigieron con el ajuste verificado de cada uno. |
| La respuesta no espera al párrafo | Prueba del orquestador: el evento `resultado` ya trae un texto legible construido con la tabla, llega antes que el `final`, y cuando la IA responde su texto lo sustituye. |
| La pastilla no miente | Prueba de `autoria`: sin texto del modelo nunca dice «escrito con IA», ni aunque el usuario deje de esperar; el rojo se reserva para la cifra descartada. |
| Unidad única | `NUMERO_EXPORTADORAS` es un conteo y no dólares; `PARTICIPACION_USD_PCT` es un porcentaje y no dólares; `EXPO_2025` sigue siendo dólares. Fijado en pytest y en vitest a la vez, sobre los alias reales del modelo semántico. |
| El diagnóstico en un dominio publicado | Responde 403 con instrucciones, incluso con `?cortex=1`; desde `localhost` y `testserver` sigue abierto. |
| El tope de tamaño | Una petición troceada, sin `Content-Length`, responde 411. |
| Contrato de motivos | Prueba nueva: cada motivo de `MOTIVOS_DEGRADACION` está explicado en la interfaz, en `tipos.ts`, en `CLAUDE.md`, en `docs/METRICAS.md` y en el DDL. Encontró cuatro huecos reales al escribirla. |
| Contrato de telemetría | Prueba nueva: las columnas que escribe el aplicativo existen en el DDL, sus topes caben en el `VARCHAR`, y el registro del orquestador coincide exactamente con la lista de columnas. |
| Portabilidad | `pytest` y `python -m pytest`, desde la raíz y desde una copia limpia: 178 en verde en los cuatro casos. |

## Comprobaciones de 3.5.1

| Comprobación | Resultado |
|---|---|
| `ruff check backend tests scripts` | Sin hallazgos. |
| `pytest -q` | **161 pruebas en verde** (150 en 3.5.0). Las 11 nuevas están en `test_endurecimiento.py` (28 en total). |
| `npm test` (vitest) | **10 pruebas en 4 archivos**. Nuevo: `formato.test.ts`, que fija la regla de moneda por nombre de columna. |
| `npm run build` (tsc + Vite) | Limpio. |
| El interruptor de la redacción | Tres fallos seguidos abren el circuito; la cuarta pregunta **no** llega a Snowflake y responde con `motivo_degradacion = redaccion_pausada`; un éxito lo reinicia. |
| La causa llega a la pantalla | Un error de privilegios de Cortex aparece literal en `meta.detalle_degradacion` y se pinta bajo «¿Por qué?». |
| El sondeo de modelos | Con el configurado inexistente y un candidato vivo, el mensaje dice «Ponga SF_CORTEX_MODEL = llama3.1-8b»; con todos muertos, nombra las tres causas en orden (permiso · región · nombre retirado). |
| El sondeo no bloquea | Un modelo inexistente tarda ~20 s en fallar: se comprueba que cuesta **una** llamada por modelo y que el paso se corta a los 75 s diciendo qué quedó sin probar. Antes habría tardado más de tres minutos. |
| El diagnóstico no gasta créditos solo | `/api/diagnostico` sin `cortex=true` no ejecuta ninguna llamada a COMPLETE; el paso nuevo `cortex_region` sólo lee `CURRENT_REGION()` y el parámetro de inferencia entre regiones. |
| El resumen automático | Cifras en formato de Colombia con su unidad (`USD 52.158.504.845,93`), NIT sin separador de miles, la empresa nombrada por su razón social, sin superlativo cuando el resultado está recortado, y sin prometer una tabla completa cuando pasa de 500 filas. |
| Gráfica y Excel coherentes con la tabla | Un promedio de 19,89 ya no se dibuja como «20»; las columnas en dólares y en pesos salen con su formato en el Excel del asistente y en la tabla en pantalla. La regla vive en un solo sitio por lado (`backend/ia/forma.clase_de_cifra` y `frontend/src/formato.ts`) y ambas versiones están fijadas con pruebas. |
| Cuaderno de publicación | Versión 3.5.1 alineada en `backend/config.py`, `frontend/package.json` y el candado de npm; los archivos nuevos (`docs/COSTOS.md`, `frontend/src/formato.ts` y su prueba) están en el pre-flight, y `tests/test_notebook.py` exige ahora **toda** prueba del frontend y **todo** documento de `docs/`, para que no vuelva a olvidarse ninguno. |
| Pregunta de créditos | Revisión del código, del `Dockerfile` y de `railway.toml`: ninguna ruta consulta Snowflake sin que alguien la pida, salvo la prueba de Cortex del diagnóstico, que pasa a ser bajo demanda. Resultado y guiones en `docs/COSTOS.md`. |

## Comprobaciones de 3.5.0

| Comprobación | Resultado |
|---|---|
| `ruff check backend tests scripts` (sintaxis y pyflakes) | Sin hallazgos. |
| `pytest -q` | **150 pruebas en verde** (78 en 3.4.2). Nuevas: `test_asistente_fase1.py` (38), `test_endurecimiento.py` (17, una por cada vía cerrada en la revisión adversaria), `test_modelo_semantico.py` (7), `test_rutas.py` (4), `test_notebook.py` (6, validan el cuaderno de publicación). |
| Portabilidad de la batería | `pytest` y `python -m pytest`, desde la raíz y desde otro directorio, y en una copia limpia del proyecto (como hace Colab): 150 en verde en los cuatro casos. Antes, desde otro directorio fallaba hasta `import backend`. |
| Secuencia completa de Colab en copia limpia | `ruff` · `pytest` (150) · `npm ci` (129 paquetes) · `npm test` (5) · `npm run build`: todo en verde, que es exactamente lo que ejecuta el cuaderno al publicar. |
| Aislamiento de Snowflake | `tests/conftest.py` anula la lectura del `.env` y vacía las `SF_*`: ninguna prueba puede abrir una conexión real ni consumir créditos de Cortex, en ningún equipo. |
| `npm test` (vitest) | 5 pruebas en 3 archivos: parser SSE con trozos partidos y latidos; `contexto()` del hilo; `TablaEmpresas` enlaza a la ficha y conserva el NIT como texto. |
| `npm run build` (tsc + Vite) | Limpio. |
| Inyección SQL | `sql_literal("x\\' OR 1=1 --")` produce un literal cerrado; prueba dedicada. `log_event` y la telemetría usan parámetros enlazados. |
| Guardas adversarias | Rechazan `IDENTIFIER('…')`, `TABLE($T)`, `SYSTEM$…`, *stages* (`FROM @~`), nombres de dos partes fuera de los esquemas, listas `FROM a, b`, comas tras `ON`, JOIN entre paréntesis, tablas sin calificar, y comentarios o cadenas sin cerrar; aceptan `SEMANTIC_VIEW(…)`, CTEs (con y sin lista de columnas), `ORDER BY … DESC`, `FETCH FIRST`, literales con paréntesis y palabras prohibidas dentro de comillas. |
| Revisión adversaria (5 revisores + refutación) | 31 hallazgos; los verificados se corrigieron y cada uno quedó fijado con una prueba. Los dos de mayor gravedad: comentarios `//` y cadenas `$$…$$` desplazaban los límites de los literales y permitían leer un esquema no autorizado. Un interbloqueo en la creación del orquestador —que habría colgado la primera pregunta del servicio— se detectó al ejecutar las pruebas. |
| Un fallo de la redacción cuesta una llamada | Prueba con error de privilegios: 1 llamada, sin forma simple, `motivo_degradacion = redaccion_fallo`, causa en la telemetría. Error de firma: 2 llamadas exactas. |
| Reintento de sesión | Sólo ante error de sesión (`Session no longer exists`); un error de consulta no reabre la sesión y deja la causa en `ultimo_error_consulta`; el modo silencioso no la pisa. |
| Descargas desde el servidor | 5 filas en el servidor con 2 en el navegador → el Excel trae las 5; `consulta_id` desconocido → 404 legible; resultado sin texto → el archivo lo declara. |
| Listado con formato estándar | `POST /api/ia/exportar/empresas` (modo demostración) → libro con Resumen · Vista_Principal · Datos_Completos · Diccionario, la pregunta, el origen y la advertencia en el Resumen; resultado sin NIT → 422. |
| Telemetría | Todas las salidas del orquestador dejan un registro (`exito`, `degradada`, `sin_sql`, `rechazada`, `fallo_sql`, `fallo_analyst`, `detenida`, `pregunta_invalida`); INSERT con 28 parámetros enlazados sin comillas; tabla inexistente → descarte contado, sin excepción. |
| Modelo semántico | YAML válido; cada consulta verificada usa sólo nombres lógicos definidos; las 12 sugeridas tienen consulta verificada con redacción idéntica; listados acotados y sin contacto salvo petición; sin dimensiones retiradas ni `CADENA` ambigua; NIT de ejemplo alineados con `NITS_EJEMPLO`. |
| Contrato de rutas | 15 rutas públicas exactas; comodines registrados al final; cabeceras de seguridad (incluidas COOP y HSTS bajo HTTPS) en toda respuesta. |
| Servidor simulado | `servidor_ia_falso.py` usa el **orquestador real** (guardas, redactor, almacén, descargas) con dobles de Snowflake y Analyst. Se recorrieron los estados: respuesta normal, gráfica pedida, redacción fallida, cifras sin respaldo, listado, progreso, redactando, móvil. |
| Notebook de publicación | Celda A en 3.5.0 con los archivos nuevos (routers, `comun`, `middleware`, `ia/forma·resultados·telemetria`, pruebas, `docs/`, guiones SQL) y `ruff` en los comandos de build; CHANGELOG con la entrada `## [3.5.0]`. |

## Capturas

`previews/` (carpeta de la entrega):

- `asistente_inicio.png` — página con las preguntas sugeridas desplegadas.
- `asistente_respuesta.png` — respuesta normal: pastilla verde, desglose, «Ver gráfica», columnas legibles, consulta desplegada con «Copiar», consultas relacionadas, memoria.
- `asistente_grafica.png` — la pregunta pidió gráfica: barras apiladas abiertas.
- `asistente_degradado.png` — la redacción falló: pastilla ámbar con causa desplegada, tabla intacta, tiempos honestos (redactar 2,5 s).
- `asistente_cifras.png` — cifra sin respaldo descartada.
- `asistente_listado.png` — listado con la tabla estándar y «Descargar listado con formato estándar».
- `asistente_progreso.png` — tarjeta de progreso con etapas, cronómetro y «Detener».
- `asistente_redactando.png` — tabla visible mientras se redacta, con «Quedarme con la tabla».
- `asistente_listado_movil.png` — listado en tarjetas (390 px).

## Validaciones que requieren el entorno del propietario

1. Ejecutar en Snowsight `snowflake/03_telemetria_asistente.sql` y
   `snowflake/04_minimo_privilegio.sql`; redesplegar el YAML del modelo
   semántico (`snowflake/LEEME.md`).
2. Publicar 3.5.0 con el notebook y esperar el redespliegue de Railway.
3. Abrir `/estado` → **Ver diagnóstico detallado**: `vista_semantica`,
   `tabla_asistente_log` y `cortex_complete` en verde. **Si `cortex_complete`
   falla, ese texto es la causa del caso de 149,5 s.**
4. En `/asistente`, la primera pregunta sugerida: tabla en menos de 15 s (consulta
   verificada), texto con pastilla verde. Repetir con «lístame…» y descargar el
   listado con formato estándar.
5. `SELECT * FROM SEGUIMIENTO.ASISTENTE_CONSULTAS ORDER BY FECHA_HORA DESC LIMIT 5;`
6. Confirmar con el administrador la herencia `APPS_MANAGER` (guion 04, §4).
7. Construcción de la imagen Docker (aquí no hay Docker Engine).

## Decisiones de esta versión

Documentadas en `docs/DECISIONES.md` (D-05 caché por `consulta_id` en una
instancia; D-06 rol con INSERT; D-07 acceso abierto con la protección lista;
D-09 listados con formato estándar; D-10 un fallo se muestra, no se reintenta;
D-11 sugeridas = verificadas; D-12 documentos operativos en la raíz).
Desviación respecto del plan: los documentos operativos **no** se movieron a
`docs/` (D-12); los de ingeniería sí nacieron allí.
