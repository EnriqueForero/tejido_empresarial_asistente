# Métricas del asistente

Desde la versión 3.5.0 cada pregunta al asistente y cada descarga quedan en dos
tablas del esquema `SEGUIMIENTO`, con el mismo espíritu de la tabla `EVENTOS`
que ya usaba la sección de consulta. Con ellas se responde, con SQL y sin abrir
el aplicativo, a tres preguntas: **qué se pregunta, cuánto tarda y dónde falla**.

## Lo que puede consultar HOY, sin crear nada

Comprobado el 5 de septiembre de 2026 contra la cuenta de ProColombia: las
tablas del asistente **todavía no existen** (el diagnóstico lo dice en el paso
`tabla_asistente_log`), pero la tabla de auditoría `EVENTOS` sí, y el asistente
deja una fila en ella por cada pregunta que llegó a mostrar tabla, la haya
redactado la IA o no. Las rechazadas, las fallidas y las detenidas no aparecen.
Con esto ve **qué se ha preguntado** desde el primer día:

```sql
SELECT FECHA_HORA,
       FILTROS          AS PREGUNTA,      -- la pregunta tal como se escribió
       DETALLE_EVENTO   AS FILAS_DEVUELTAS
FROM APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.EVENTOS
WHERE TIPO_EVENTO = 'Asistente'
ORDER BY FECHA_HORA DESC
LIMIT 50;
```

`EVENTOS` no guarda la respuesta ni los tiempos ni los fallos: para eso están
las dos tablas nuevas, y por eso conviene crearlas.

## Activarlas (una sola vez)

1. En Snowsight, con un rol que pueda crear objetos en `SEGUIMIENTO`
   (`APPS_MANAGER` o `ACCOUNTADMIN`), ejecute
   [`snowflake/03_telemetria_asistente.sql`](../snowflake/03_telemetria_asistente.sql)
   completo. Crea las dos tablas, dos vistas y concede al rol del aplicativo
   sólo `INSERT` y `SELECT`.
2. Abra `https://tejidoempresarialasistente-production.up.railway.app/estado`
   y pulse **Ver diagnóstico detallado**: el paso `tabla_asistente_log` debe quedar
   en verde. Al final del JSON de `/api/diagnostico` aparece el bloque
   `telemetria` con `registrados` y `descartados`.
3. Haga una pregunta en `/asistente` y ejecute la primera consulta de abajo.

Si las tablas no existen, el asistente funciona igual: la telemetría se
descarta y el contador `descartados` del diagnóstico lo muestra.

## Qué se guarda y qué no

| Se guarda | No se guarda nunca |
|---|---|
| La pregunta, la SQL propuesta y la SQL ejecutada | Las filas del resultado |
| El texto entregado y si fue redactado por la IA o es el resumen automático | Datos de contacto (correo, teléfono, dirección, representante) |
| Estado, etapa del fallo y causa (sin secretos) | Credenciales, llaves, cabeceras |
| Tiempos de cada etapa y número de filas | Identidad de la persona: `SESION_ID` es un identificador aleatorio de la pestaña |

Estados posibles (`ESTADO`): `exito` · `degradada` (hubo tabla pero el texto es
el resumen automático) · `sin_sql` (Analyst pidió más detalle) · `rechazada`
(las guardas no dejaron ejecutar la SQL) · `fallo_sql` · `fallo_analyst` ·
`error_interno` · `detenida` (el usuario pulsó «Detener») ·
`pregunta_invalida`.

## Consultas listas

Todas se ejecutan con el rol del aplicativo. Las vistas ya convierten la hora a
Bogotá.

### La pregunta y la respuesta, una al lado de la otra

Es la consulta que responde literalmente «¿qué se ha consultado, la pregunta y
la respuesta?». Requiere haber ejecutado el guion del paso 1.

```sql
SELECT CONVERT_TIMEZONE('America/Bogota', FECHA_HORA) AS FECHA_HORA_BOGOTA,
       PREGUNTA,
       RESPUESTA,                                   -- el texto que se entregó
       IFF(DEGRADADO, 'resumen construido con los datos', 'redactado con IA') AS QUIEN_ESCRIBIO,
       ESTADO,
       N_FILAS,
       ROUND(MS_TOTAL / 1000, 1) AS SEGUNDOS,
       SQL_VALIDADA                                 -- la consulta que se ejecutó
FROM APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.ASISTENTE_CONSULTAS
ORDER BY FECHA_HORA DESC
LIMIT 50;
```

### Últimas preguntas

```sql
SELECT CONVERT_TIMEZONE('America/Bogota', FECHA_HORA) AS FECHA_HORA_BOGOTA,
       ESTADO, ROUND(MS_TOTAL / 1000, 1) AS SEGUNDOS, N_FILAS, ES_LISTADO, PREGUNTA
FROM APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.ASISTENTE_CONSULTAS
ORDER BY FECHA_HORA DESC
LIMIT 20;
```

### Resumen diario (volumen, tasa de éxito y tiempos)

```sql
SELECT * FROM APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.V_ASISTENTE_DIARIO
ORDER BY DIA DESC
LIMIT 30;
```

### Qué falla y por qué

```sql
SELECT * FROM APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.V_ASISTENTE_CALIDAD
ORDER BY FECHA_HORA_BOGOTA DESC
LIMIT 50;
```

Lectura rápida de `MOTIVO_DEGRADACION`. En los cinco casos la respuesta es
correcta: cambia quién escribió el párrafo, no si el dato es cierto.

- `redaccion_fallo`: Cortex COMPLETE no respondió. `ERROR` trae la causa: si
  dice `unknown model`, el nombre de `SF_CORTEX_MODEL` ya no existe —es lo más
  frecuente—; si habla de privilegios, falta
  `GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER`.
- `redaccion_pausada`: falló tres veces seguidas y el aplicativo dejó de
  llamarla durante diez minutos, para no hacer esperar en cada pregunta.
  `MS_REDACCION` vale 0. Si aparece en serie, corrija la causa del anterior.
- `respuesta_vacia`: el modelo devolvió un texto vacío.
- `respuesta_ilegible`: el modelo respondió con una forma que el aplicativo no
  supo leer, así que no se usó nada de ella.
- `cifras_sin_respaldo`: el texto citaba una cifra que no está en la tabla y se
  reemplazó por el resumen construido con los datos. Es el único de los cinco
  que señala algo que salió mal de verdad.

`MODELO` dice quién escribió el texto, no quién estaba configurado: si está
vacío, lo escribió el aplicativo. Combinado con `DEGRADADO`, distingue «así está
diseñado» de «la IA falló».

### Dónde se va el tiempo (mediana por etapa, últimos 7 días)

```sql
SELECT ROUND(MEDIAN(MS_INTERPRETACION) / 1000, 1) AS INTERPRETAR,
       ROUND(MEDIAN(MS_CONSULTA) / 1000, 1)       AS CONSULTAR,
       ROUND(MEDIAN(MS_CORRECCION) / 1000, 1)     AS CORREGIR,
       ROUND(MEDIAN(MS_REDACCION) / 1000, 1)      AS REDACTAR,
       ROUND(MEDIAN(MS_TOTAL) / 1000, 1)          AS TOTAL,
       COUNT(*)                                   AS PREGUNTAS
FROM APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.ASISTENTE_CONSULTAS
WHERE FECHA_HORA >= DATEADD('day', -7, CURRENT_TIMESTAMP())
  AND EXITO;
```

### Preguntas que más se repiten (para convertirlas en preguntas verificadas del modelo semántico)

```sql
SELECT LOWER(TRIM(PREGUNTA)) AS PREGUNTA, COUNT(*) AS VECES,
       ROUND(AVG(MS_INTERPRETACION) / 1000, 1) AS SEG_INTERPRETAR_PROMEDIO
FROM APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.ASISTENTE_CONSULTAS
WHERE FECHA_HORA >= DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP BY 1
HAVING COUNT(*) >= 2
ORDER BY VECES DESC, SEG_INTERPRETAR_PROMEDIO DESC
LIMIT 30;
```

Una pregunta que se repite y tarda más de 20 s en «interpretar» es candidata a
`verified_queries` en `snowflake/TEJIDO_EMPRESARIAL_SEGMENTACION.sv.yaml`: con
la SQL escrita por una persona, Analyst responde en segundos y sin perder
precisión.

### Descargas

```sql
SELECT FORMATO, COUNT(*) AS DESCARGAS, SUM(N_FILAS) AS FILAS
FROM APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.ASISTENTE_DESCARGAS
WHERE FECHA_HORA >= DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP BY 1;
```

Cada descarga lleva el `CONSULTA_ID` de la pregunta que la originó: un `JOIN`
con `ASISTENTE_CONSULTAS` dice qué preguntas terminan en archivo.

## Los costos del aplicativo en Snowflake

Estas tres consultas necesitan un rol con acceso a `SNOWFLAKE.ACCOUNT_USAGE`
(normalmente `ACCOUNTADMIN`). Ese esquema tiene un retraso de hasta 45 minutos,
así que lo de hace un rato todavía no aparece. `docs/COSTOS.md` explica **qué**
gasta y qué no; esto es **cuánto**.

### 1 · Créditos del warehouse por día (es la mayor parte de la factura)

```sql
SELECT DATE_TRUNC('day', START_TIME)::DATE AS DIA,
       WAREHOUSE_NAME,
       ROUND(SUM(CREDITS_USED), 3)         AS CREDITOS,
       ROUND(SUM(CREDITS_USED_COMPUTE), 3) AS CREDITOS_COMPUTO
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
  AND WAREHOUSE_NAME = 'APPS_WH'
GROUP BY 1, 2
ORDER BY 1 DESC;
```

### 2 · Créditos de la IA (Cortex se factura aparte del warehouse)

```sql
SELECT DATE_TRUNC('day', START_TIME)::DATE AS DIA,
       FUNCTION_NAME,
       MODEL_NAME,
       SUM(TOKENS)                    AS FICHAS,
       ROUND(SUM(TOKEN_CREDITS), 4)   AS CREDITOS
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_FUNCTIONS_USAGE_HISTORY
WHERE START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP BY 1, 2, 3
ORDER BY 1 DESC, 5 DESC;
```

**Esta vista agrega por hora: no cuente sus filas para saber cuántas preguntas
hubo.** El número de preguntas es exacto, sin retraso y en español, en
`ASISTENTE_CONSULTAS` (arriba) o, mientras no exista, en `EVENTOS`.

Cortex Analyst —la parte que traduce la pregunta a SQL— se factura aparte:

```sql
SELECT DATE_TRUNC('day', START_TIME)::DATE AS DIA,
       ROUND(SUM(CREDITS), 4) AS CREDITOS
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_ANALYST_USAGE_HISTORY
WHERE START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP BY 1
ORDER BY 1 DESC;
```

### 3 · Qué consultas del aplicativo consumieron ese tiempo

Sin retraso, y sin `ACCOUNT_USAGE`: `QUERY_HISTORY` del `INFORMATION_SCHEMA`
guarda los últimos siete días. El aplicativo marca **todas** sus consultas con
`QUERY_TAG = 'TEJIDO_EMPRESARIAL_REACT'`, así que su gasto se puede separar del
de cualquier otra cosa que use el mismo warehouse.

```sql
SELECT START_TIME,
       ROUND(TOTAL_ELAPSED_TIME / 1000, 1) AS SEGUNDOS,
       EXECUTION_STATUS,
       ERROR_MESSAGE,
       LEFT(QUERY_TEXT, 120) AS CONSULTA
FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY(
       END_TIME_RANGE_START => DATEADD('day', -7, CURRENT_TIMESTAMP()),
       RESULT_LIMIT => 1000))
WHERE QUERY_TAG = 'TEJIDO_EMPRESARIAL_REACT'
ORDER BY TOTAL_ELAPSED_TIME DESC
LIMIT 50;
```

Y cuánto tiempo de warehouse consumió el aplicativo, frente al total:

```sql
SELECT IFF(QUERY_TAG = 'TEJIDO_EMPRESARIAL_REACT', 'Aplicativo', 'Otros') AS ORIGEN,
       COUNT(*)                                       AS CONSULTAS,
       ROUND(SUM(TOTAL_ELAPSED_TIME) / 1000 / 60, 1)  AS MINUTOS
FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY(
       END_TIME_RANGE_START => DATEADD('day', -7, CURRENT_TIMESTAMP()),
       RESULT_LIMIT => 10000))
WHERE WAREHOUSE_NAME = 'APPS_WH'
GROUP BY 1;
```

Si aparecen consultas de ~20 s con `ERROR_MESSAGE` que menciona
`unknown model`, es la redacción con IA fallando: cambie `SF_CORTEX_MODEL`
(ver `ASISTENTE.md` §5).

### 4 · Poner un tope

En `docs/COSTOS.md`, sección «Poner un tope, no sólo mirar»: un *resource
monitor* con aviso al 75 % y suspensión al 100 %. Recuerde que **no cubre
Cortex**.

## Relación con la tabla EVENTOS

La sección de consulta (`/consultar`) sigue registrando en
`SEGUIMIENTO.EVENTOS` como siempre, y el asistente deja allí una fila por cada
pregunta que llegó a mostrar tabla (tipo `Asistente`), la haya redactado la IA o
no, para no romper ningún seguimiento que ya exista sobre esa tabla. El detalle —tiempos, estados, fallos— sólo está en las
tablas nuevas.
