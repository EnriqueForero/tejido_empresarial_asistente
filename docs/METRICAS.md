# Métricas del asistente

Desde la versión 3.5.0 cada pregunta al asistente y cada descarga quedan en dos
tablas del esquema `SEGUIMIENTO`, con el mismo espíritu de la tabla `EVENTOS`
que ya usaba la sección de consulta. Con ellas se responde, con SQL y sin abrir
el aplicativo, a tres preguntas: **qué se pregunta, cuánto tarda y dónde falla**.

## Activarlas (una sola vez)

1. En Snowsight, con un rol que pueda crear objetos en `SEGUIMIENTO`
   (`APPS_MANAGER` o `ACCOUNTADMIN`), ejecute
   [`snowflake/03_telemetria_asistente.sql`](../snowflake/03_telemetria_asistente.sql)
   completo. Crea las dos tablas, dos vistas y concede al rol del aplicativo
   sólo `INSERT` y `SELECT`.
2. Abra `https://tejidoempresarialasistente-production.up.railway.app/estado`
   y pulse **Ejecutar diagnóstico**: el paso `tabla_asistente_log` debe quedar
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
LIMIT 50;
```

Lectura rápida de `MOTIVO_DEGRADACION`:

- `redaccion_fallo`: Cortex COMPLETE no respondió. `ERROR` trae la causa: si
  habla de privilegios, falta `GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER`; si
  dice que el modelo no existe o no está en la región, cambie `SF_CORTEX_MODEL`.
- `respuesta_vacia`: el modelo devolvió texto vacío.
- `cifras_sin_respaldo`: el texto citaba una cifra que no está en la tabla y se
  reemplazó por el resumen construido con los datos.

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

### Créditos consumidos por la IA (requiere acceso a `SNOWFLAKE.ACCOUNT_USAGE`)

Las consultas de costo están en
[`snowflake/02_comparar_modelos.sql`](../snowflake/02_comparar_modelos.sql),
sección 3.

## Relación con la tabla EVENTOS

La sección de consulta (`/consultar`) sigue registrando en
`SEGUIMIENTO.EVENTOS` como siempre, y el asistente deja allí una fila por
respuesta exitosa (tipo `Asistente`) para no romper ningún seguimiento que ya
exista sobre esa tabla. El detalle —tiempos, estados, fallos— sólo está en las
tablas nuevas.
