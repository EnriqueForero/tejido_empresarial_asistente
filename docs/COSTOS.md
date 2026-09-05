# Qué cuesta el aplicativo y qué no

Escrito a partir de una revisión del código, del `Dockerfile`, de `railway.toml`
y de la documentación de facturación de Snowflake, para responder una pregunta
concreta: **el servicio en Railway está siempre activo, ¿eso gasta créditos?**

La respuesta corta: **el contenedor encendido no gasta ni un crédito de
Snowflake**. Lo que gasta créditos son las consultas, y quien las dispara son las
personas que abren el aplicativo. Lo que más mueve la factura no está en el
código: es el `AUTO_SUSPEND` del warehouse.

## Lo que sí cuesta, en orden de impacto

| # | Qué | Por qué cuesta | Qué hacer |
|---|---|---|---|
| 1 | **`AUTO_SUSPEND` de `APPS_WH`** | Un warehouse encendido consume créditos por segundo. Si está configurado para quedarse encendido esperando (por ejemplo 10 minutos), unas pocas consultas al día lo mantienen despierto muchas horas. Es, con diferencia, la variable que más pesa. | Ver el guion de abajo. `AUTO_SUSPEND = 60` es el punto justo: Snowflake factura un mínimo de 60 segundos por cada arranque, así que suspender antes sólo produce más arranques sin ahorrar. |
| 2 | **El acceso abierto** | Cualquiera con el enlace puede abrir `/consultar`, buscar y descargar. Cada búsqueda es un conteo más una consulta; cada descarga, hasta 5.000 filas; cada pregunta al asistente, una o dos llamadas a Cortex Analyst. Es el único camino por el que un tercero gasta su presupuesto. | README → «Activar usuario y contraseña». Son dos variables en Railway y un minuto. |
| 3 | **La redacción con IA que falla** | Hasta la versión 3.5.1, cada pregunta esperaba ~20 s a una llamada que nunca funcionó, y esos 20 s se facturan como tiempo de warehouse. | Ya corregido en el código: tras tres fallos seguidos el aplicativo deja de llamar durante diez minutos. La causa de fondo se arregla en Snowflake (ver `ASISTENTE.md` §5). |
| 4 | **La prueba de Cortex del diagnóstico** | Es el único punto del código que gasta créditos de **IA** sin que nadie haya preguntado nada. | Ya corregido: desde 3.5.1 no se ejecuta sola. Hay que pulsar «Probar la redacción con IA» en `/estado`. |

## Lo que NO cuesta, para dejar de perseguirlo

- **El contenedor de Railway encendido.** Railway cobra por tiempo de ejecución
  del contenedor, no Snowflake. El proceso encendido, sin visitas, no ejecuta
  ninguna consulta.
- **El chequeo de salud.** Ni el de Docker ni el de Railway tocan Snowflake:
  `/api/health` sólo mira la configuración en memoria. Únicamente
  `/api/health?deep=true` ejecuta un `SELECT 1`, y eso pasa cuando alguien abre
  `/estado`.
- **`client_session_keep_alive`.** Mantiene viva la *sesión* (un latido de
  autenticación cada hora). No ejecuta consultas y **no despierta el
  warehouse**.
- **Un warehouse suspendido.** Cero créditos de cómputo. Sólo se paga el
  almacenamiento de los datos, que es independiente del aplicativo.
- **La telemetría del asistente.** Si la tabla no existe, descarta el registro y
  cuenta el descarte; no reintenta en bucle.
- **Los rastreadores web.** La portada, `/api/metadata` y `/api/ia/estado` no
  tocan Snowflake, y las rutas que sí lo hacen son `POST`.

## Lo primero que conviene ejecutar en Snowsight

```sql
-- 1) Cómo está hoy el warehouse.
SHOW WAREHOUSES LIKE 'APPS_WH';

-- 2) Ponerlo en la configuración adecuada para un aplicativo de consulta.
ALTER WAREHOUSE APPS_WH SET
  WAREHOUSE_SIZE = XSMALL,
  AUTO_SUSPEND = 60,          -- el mínimo que se factura por arranque
  AUTO_RESUME = TRUE,         -- si se desactiva, el aplicativo responde 502
  MIN_CLUSTER_COUNT = 1,
  MAX_CLUSTER_COUNT = 1;

-- 3) Qué se ha gastado de verdad en los últimos 30 días.
SELECT WAREHOUSE_NAME,
       DATE_TRUNC('day', START_TIME)::DATE AS DIA,
       ROUND(SUM(CREDITS_USED), 3) AS CREDITOS
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP BY 1, 2
ORDER BY 2 DESC;

-- 4) Y cuánto de eso fue Cortex (se factura aparte del warehouse).
SELECT MODEL_NAME, COUNT(*) AS LLAMADAS, ROUND(SUM(TOKEN_CREDITS), 4) AS CREDITOS
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_FUNCTIONS_USAGE_HISTORY
WHERE START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP BY 1 ORDER BY 3 DESC;
```

## Poner un tope, no sólo mirar

Un **resource monitor** limita el gasto del warehouse y puede suspenderlo al
llegar a un umbral:

```sql
CREATE OR REPLACE RESOURCE MONITOR MONITOR_APPS_WH
  WITH CREDIT_QUOTA = 50                     -- créditos por mes; ajústelo
  FREQUENCY = MONTHLY
  START_TIMESTAMP = IMMEDIATELY
  TRIGGERS ON 75 PERCENT DO NOTIFY
           ON 100 PERCENT DO SUSPEND
           ON 110 PERCENT DO SUSPEND_IMMEDIATE;
ALTER WAREHOUSE APPS_WH SET RESOURCE_MONITOR = MONITOR_APPS_WH;
```

Un detalle que conviene saber: **el resource monitor no cubre Cortex.** El gasto
de IA se controla por otro camino (presupuestos, o retirando el rol
`SNOWFLAKE.CORTEX_USER`). Con el uso actual del asistente ese gasto es pequeño
frente al del warehouse, pero no se limita con lo anterior.

## En Railway

Railway cobra por los recursos del contenedor mientras esté desplegado. El
aplicativo mantiene en memoria hasta 50 resultados del asistente (2 millones de
celdas como máximo, `IA_RESULT_CAPACITY` e `IA_RESULT_TTL`) y el catálogo de
filtros. Para reducir el costo del contenedor: fijar un *usage limit* en el
proyecto, y si el uso es esporádico, valorar el arranque bajo demanda de
Railway. Nada de eso afecta a los créditos de Snowflake.

## Resumen para decidir en cinco minutos

1. Ejecute los guiones 1 y 3 de arriba. Si `AUTO_SUSPEND` es alto, ahí está el
   gasto.
2. Active usuario y contraseña en Railway si el aplicativo no tiene que ser
   público.
3. Cree el resource monitor con un tope que le resulte cómodo.
4. Publique la versión 3.5.1: deja de gastar 20 s de warehouse por pregunta en
   una llamada que falla, y ya no prueba Cortex al abrir el diagnóstico.
