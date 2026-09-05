# Decisiones de arquitectura

Registro de las decisiones que dan forma al aplicativo y que no se deducen del
código. Cada una dice qué se decidió, por qué y qué se descartó. Si una deja de
ser válida, se marca como sustituida y se enlaza la nueva; no se borra.

| # | Decisión | Estado |
|---|---|---|
| D-01 | Snowflake es el único conector | Vigente |
| D-02 | Cortex Analyst, no Cortex Agent | Vigente |
| D-03 | El modelo propone, el código dispone | Vigente |
| D-04 | Un solo exportador de empresas | Vigente |
| D-05 | Resultados del asistente en memoria, por `consulta_id` | Vigente |
| D-06 | El rol del aplicativo lee datos y escribe auditoría, nada más | Vigente |
| D-07 | Acceso abierto por decisión del propietario, con la protección lista | Vigente |
| D-08 | Entrega progresiva por SSE con latido | Vigente |
| D-09 | Un listado del asistente se muestra y descarga con el formato estándar | Vigente |
| D-10 | Un fallo se muestra, no se reintenta | Vigente |
| D-11 | Preguntas sugeridas = preguntas verificadas del modelo semántico | Vigente |
| D-12 | Documentos operativos en la raíz; documentos de ingeniería en `docs/` | Vigente |
| D-13 | Un servicio externo que falla siempre deja de llamarse | Vigente |
| D-14 | El nombre del modelo de redacción es configuración, no código | Vigente |

---

## D-01 · Snowflake es el único conector

**Decisión.** Toda la inteligencia artificial del asistente corre dentro de la
cuenta de Snowflake de ProColombia: Cortex Analyst traduce la pregunta a SQL y
`SNOWFLAKE.CORTEX.COMPLETE` redacta el resumen. No hay proveedor externo de
modelos, ninguna clave adicional y ningún dato sale de la cuenta.

**Por qué.** La base contiene datos de contacto de empresas reales. Enviar
tablas a un servicio externo obligaría a un acuerdo de tratamiento de datos, a
una clave más que rotar y a un tercero que auditar. Dentro de Snowflake, el
mismo rol y la misma llave RSA que ya consulta la base sirven para todo.

**Descartado.** Llamar a la API de un proveedor de modelos desde el backend.
Más rápido de integrar, pero con datos saliendo de la cuenta y un secreto nuevo.

## D-02 · Cortex Analyst, no Cortex Agent

**Decisión.** El aplicativo llama a `/api/v2/cortex/analyst/message` y recibe
SQL; él la ejecuta. El agente definido en `snowflake/AGENTE_TEJIDO_EMPRESARIAL.agent.yaml`
se conserva para otros canales, pero el aplicativo no lo usa.

**Por qué.** Un agente orquesta y ejecuta por su cuenta, lo que deja fuera del
aplicativo el paso que da la garantía: revisar la SQL antes de ejecutarla y
comprobar que cada cifra del texto exista en la tabla (D-03).

## D-03 · El modelo propone, el código dispone

**Decisión.** Ninguna salida del modelo llega al usuario sin pasar por código
determinista: `guardas.validar_sql` (una sola sentencia de lectura, orígenes
sólo en los esquemas permitidos, tope de filas) y `guardas.verificar_cifras`
(toda cifra del texto debe existir en la tabla, con redondeos y escalas; si
no, se reemplaza por un resumen construido con los datos y se declara).

**Por qué.** Es lo que permite mostrar la consulta y la tabla que respaldan cada
respuesta, y advertir con honestidad cuando la redacción no pudo verificarse.
La precisión no depende del modelo elegido, sino de estas dos barreras.

## D-04 · Un solo exportador de empresas

**Decisión.** Todo listado de empresas se descarga con `backend/exporter.py`
(`create_export`): Resumen · Ficha_Empresa · Vista_Principal · Datos_Completos ·
Diccionario. El asistente reutiliza ese camino (`batch_nits` con los NIT del
resultado) y añade en el Resumen la pregunta, la consulta y la advertencia de IA.
El Excel «tabla del asistente» (dos hojas) existe sólo para resultados que no
son listados (agregados, rankings).

**Por qué.** Un segundo formato de listado obligaría a mantener dos estilos, dos
diccionarios y dos conjuntos de pruebas, y confundiría a quien recibe el archivo.

## D-05 · Resultados del asistente en memoria, por `consulta_id`

**Decisión.** El servidor conserva cada resultado (todas las filas, la SQL, el
contenido real que devolvió Analyst) durante 30 minutos, hasta 50 resultados y
2 millones de celdas (`backend/ia/resultados.py`). Las descargas, el listado
estándar y la memoria del hilo salen de ahí, no de lo que envía el navegador.

**Por qué.** Al navegador viajan a lo sumo 500 filas; la descarga debe traer
las 5.000 que la consulta obtuvo. Reenviar la tabla desde el cliente era, además,
aceptar tablas arbitrarias en un endpoint de descarga. Y el historial que Analyst
necesita es su propio contenido, no una reconstrucción.

**Supuesto.** Una sola instancia del servicio (la configuración actual de
Railway). Si se escalara a varias, la tabla `ASISTENTE_CONSULTAS` —que ya lleva el
`consulta_id`— sería el reemplazo natural. El navegador guarda sólo el esqueleto
del hilo (pregunta, identificador, texto, columnas): nunca filas, porque pueden
traer contacto.

## D-06 · El rol del aplicativo lee datos y escribe auditoría, nada más

**Decisión.** `APP_SEGMENTACION_EXPORTACIONES` tiene `SELECT` sobre los datos y la
vista semántica, `INSERT` (y `SELECT`) sobre las tablas de `SEGUIMIENTO`, y usa
Cortex. No tiene `UPDATE` ni `DELETE`; `snowflake/04_minimo_privilegio.sql`
retira los que el guion inicial concedió sobre `EVENTOS` y deja la verificación.

**Por qué.** Los documentos decían «solo lectura» y el guion de creación
concedía más. Con el asistente ejecutando SQL propuesta por un modelo —aunque
validada—, el privilegio del rol es la última barrera y debe ser el mínimo.

**Pendiente del administrador.** `GRANT ROLE APPS_MANAGER TO ROLE APP_SEGMENTACION_EXPORTACIONES`
(setup/03) hace que el rol del aplicativo herede un rol de gestión. No lo
cambia el código; hay que revisarlo en la cuenta.

## D-07 · Acceso abierto por decisión del propietario, con la protección lista

**Decisión.** El aplicativo se sirve sin usuario ni contraseña, igual que la
versión Streamlit, porque así lo decidió el propietario (2026-09-04). El
control de acceso HTTP Basic está implementado y documentado en el README
(«Activar usuario y contraseña»): son dos variables en Railway.

**Por qué.** Cambiar el modo de acceso es una decisión institucional, no
técnica. Lo que corresponde al código es dejarlo a un paso y avisar en los
registros y en la documentación que las descargas incluyen datos de contacto.

## D-08 · Entrega progresiva por SSE con latido

**Decisión.** `/api/ia/preguntar` transmite eventos `etapa` → `resultado` →
`final` (o `error`). La tabla se entrega en cuanto Snowflake responde, antes de
redactar; el servidor envía un comentario SSE cada 10 s mientras no hay eventos;
si el navegador cierra la conexión, el orquestador no sigue con etapas que nadie
va a leer.

**Por qué.** Redactar es la etapa lenta y no hay razón para retener lo que ya
está calculado. Los proxies cierran las conexiones mudas; el latido las mantiene.
«Detener» debe detener trabajo real, no sólo la pantalla.

## D-09 · Un listado del asistente se muestra y descarga con el formato estándar

**Decisión.** Cuando el resultado trae una columna NIT con valores válidos, el
asistente lo presenta con `TablaEmpresas` (el mismo componente de la sección de
consulta: orden, columnas, ficha, tarjetas en móvil) y ofrece «Descargar listado
con formato estándar» (D-04). Los demás resultados usan la tabla simple.

**Por qué.** El usuario pidió que refinar una pregunta termine «en un listado de
empresas a descargar» que «conserve el formato de la sección de los filtros».
Detectarlo por la columna NIT es determinista y no depende del modelo.

## D-10 · Un fallo se muestra, no se reintenta

**Decisión.** Ante un error de Cortex COMPLETE se hace **una** llamada; sólo
un error de compilación de la sentencia (firma no admitida) permite probar la
forma simple, una vez. La sesión de Snowflake se reabre sólo ante errores de
sesión o de red, nunca ante errores de la consulta. La degradación llega al
navegador con su motivo (`meta.motivo_degradacion`) y queda en la telemetría.

**Por qué.** En producción un fallo de la redacción se presentó como «88,7 s»
porque se reintentó cuatro veces con dos reaperturas de sesión, y la interfaz lo
selló como «Cifras verificadas». Un error visible a los 2 s vale más que un
error oculto a los 90.

## D-11 · Preguntas sugeridas = preguntas verificadas del modelo semántico

**Decisión.** Cada pregunta sugerida en `/asistente` existe, con la misma
redacción, como `verified_query` en el YAML, con la SQL escrita por una persona.
`tests/test_modelo_semantico.py` lo exige.

**Por qué.** Analyst responde en segundos y sin ambigüedad cuando la pregunta
coincide con una verificada; con una pregunta libre puede tardar 50 s. Es la
palanca de latencia que no sacrifica precisión.

## D-12 · Documentos operativos en la raíz; documentos de ingeniería en `docs/`

**Decisión.** Los documentos que usa el propietario para operar (README,
ASISTENTE, RAILWAY_VARIABLES, DIAGNOSTICO_RAILWAY, DESPLIEGUE_NUEVO, VALIDACION,
CHANGELOG, CLAUDE) se quedan en la raíz, donde ya los conoce y donde el notebook
de publicación los exige. Los de ingeniería (DECISIONES, BITACORA, INCIDENTES,
METRICAS) viven en `docs/`.

**Por qué.** Mover los operativos rompería enlaces, hábitos y la lista de
archivos del notebook por una ganancia sólo estética.

## D-13 · Un servicio externo que falla siempre deja de llamarse

**Decisión.** La redacción con IA lleva un interruptor: tras
`IA_REDACCION_FALLOS_PARA_PAUSA` fallos consecutivos (3 por defecto) deja de
llamarse durante `IA_REDACCION_PAUSA` segundos (600). Durante la pausa la
respuesta llega con el resumen automático y el motivo `redaccion_pausada`; el
primer éxito reinicia la cuenta. La pausa nunca impide responder: sólo evita la
espera.

**Por qué.** D-10 quitó los reintentos dentro de una pregunta, pero no entre
preguntas: las tres primeras consultas reales pagaron cada una ~20 s de espera
por el mismo fallo, ya conocido desde la primera. Un servicio que acaba de
fallar tres veces seguidas va a fallar la cuarta; preguntárselo cuesta tiempo
del usuario y créditos de warehouse.

**Qué se descartó.** Desactivar la redacción con una variable de entorno (exige
que alguien se dé cuenta y actúe) y reintentar con otro modelo (multiplicaría el
gasto justo cuando la cuenta está fallando).

## D-14 · El nombre del modelo de redacción es configuración, no código

**Decisión.** `SF_CORTEX_MODEL` elige el modelo, y el aplicativo trae una prueba
propia —`/estado` → «Probar la redacción con IA»— que llama a varios candidatos
y dice cuáles responden en esta cuenta y esta región. El código nunca fija un
único nombre.

**Por qué.** Los nombres de modelo de Cortex caducan. `claude-3-5-sonnet`, el
valor por defecto hasta la 3.5.1, fue retirado, y con un nombre inexistente la
redacción falla en todas las preguntas sin ninguna otra señal. El aplicativo
tiene que poder decir cuál usar sin desplegar código y sin que el propietario
consulte documentación externa.
