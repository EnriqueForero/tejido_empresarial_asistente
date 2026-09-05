-- =============================================================================
-- Telemetría del asistente de análisis · tablas de SEGUIMIENTO
-- =============================================================================
-- Qué registra el aplicativo (versión 3.5.0 en adelante):
--
--   ASISTENTE_CONSULTAS  una fila por pregunta, con su estado (éxito, degradada,
--                        rechazada, fallo de SQL, fallo de Analyst, detenida…),
--                        los tiempos de cada etapa, la SQL generada y validada y
--                        el texto entregado. NUNCA guarda filas del resultado ni
--                        datos de contacto.
--   ASISTENTE_DESCARGAS  una fila por archivo descargado (Excel de la tabla,
--                        presentación o listado con formato estándar), ligada a
--                        la consulta que lo originó.
--
-- La inserción la hace el aplicativo con parámetros enlazados, desde un hilo
-- aparte y sin bloquear la respuesta. Si estas tablas no existen, el asistente
-- funciona igual y /api/diagnostico (paso «tabla_asistente_log») lo indica.
--
-- Ejecutar UNA VEZ con un rol que pueda crear objetos en el esquema (p. ej.
-- APPS_MANAGER o ACCOUNTADMIN). Las consultas de lectura para el seguimiento
-- están en docs/METRICAS.md.
-- =============================================================================

-- El rol del aplicativo se escribe UNA vez (es el valor de SF_ROLE en Railway).
-- Ejecute el guion con un rol que pueda crear objetos aquí: APPS_MANAGER o
-- ACCOUNTADMIN. No se fija con USE ROLE a propósito, para no obligar a
-- ACCOUNTADMIN ni dejar las tablas con su OWNERSHIP.
SET ROL_APP = 'APP_SEGMENTACION_EXPORTACIONES';   -- ← su SF_ROLE

USE DATABASE APP_SEGMENTACION_EXPORTACIONES;
USE SCHEMA SEGUIMIENTO;

-- ── 1 · Tablas ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ASISTENTE_CONSULTAS (
    CONSULTA_ID          VARCHAR(12)     NOT NULL,
    SESION_ID            VARCHAR(64),
    FECHA_HORA           TIMESTAMP_LTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    PREGUNTA             VARCHAR(2000),
    SQL_GENERADA         VARCHAR(20000),   -- lo que propuso Cortex Analyst
    SQL_VALIDADA         VARCHAR(20000),   -- lo que se ejecutó tras las guardas
    RESPUESTA            VARCHAR(4000),    -- texto entregado al usuario
    ESTADO               VARCHAR(30),      -- exito · degradada · sin_sql · rechazada · fallo_sql · fallo_analyst · error_interno · detenida · pregunta_invalida
    EXITO                BOOLEAN,          -- exito o degradada (hubo tabla)
    DEGRADADO            BOOLEAN,          -- el texto lo escribió el aplicativo, no la IA
    MOTIVO_DEGRADACION   VARCHAR(60),      -- redaccion_fallo · redaccion_pausada · respuesta_vacia · respuesta_ilegible · cifras_sin_respaldo
    CIFRAS_VERIFICADAS   BOOLEAN,
    N_FILAS              NUMBER(10, 0),
    TRUNCADO             BOOLEAN,
    ES_LISTADO           BOOLEAN,          -- traía columna NIT (descargable con formato estándar)
    MOSTRO_GRAFICA       BOOLEAN,
    MS_INTERPRETACION    NUMBER(10, 0),    -- Cortex Analyst
    MS_CONSULTA          NUMBER(10, 0),    -- ejecución en Snowflake (ambos intentos)
    MS_CORRECCION        NUMBER(10, 0),    -- segunda llamada a Analyst, si hizo falta
    MS_REDACCION         NUMBER(10, 0),    -- SNOWFLAKE.CORTEX.COMPLETE
    MS_TOTAL             NUMBER(10, 0),
    INTENTOS_SQL         NUMBER(2, 0),
    MODELO               VARCHAR(80),      -- vacío si el texto lo escribió el aplicativo
    FORMA_REDACCION      VARCHAR(20),      -- opciones · simple · vacío
    ANALYST_REQUEST_ID   VARCHAR(80),
    ETAPA_FALLO          VARCHAR(30),
    ERROR                VARCHAR(1000),    -- causa redactada, sin secretos
    APP_VERSION          VARCHAR(20),
    VISTA_SEMANTICA      VARCHAR(300),
    ENTORNO              VARCHAR(30)
)
COMMENT = 'Una fila por pregunta al asistente de análisis del Tejido Empresarial (sin filas de resultado ni contacto).';

CREATE TABLE IF NOT EXISTS ASISTENTE_DESCARGAS (
    DESCARGA_ID   VARCHAR(12)    NOT NULL,
    CONSULTA_ID   VARCHAR(12)    NOT NULL,
    SESION_ID     VARCHAR(64),
    FORMATO       VARCHAR(20),   -- excel · pptx · empresas
    N_FILAS       NUMBER(10, 0),
    FECHA_HORA    TIMESTAMP_LTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Una fila por archivo descargado desde el asistente, ligada a su consulta.';

-- Para una cuenta donde las tablas ya existían: CREATE TABLE IF NOT EXISTS no
-- añade columnas nuevas, y si el aplicativo inserta una que no está, la
-- telemetría se descarta en silencio. Esta línea es inocua si ya está.
ALTER TABLE ASISTENTE_CONSULTAS ADD COLUMN IF NOT EXISTS FORMA_REDACCION VARCHAR(20);

-- ── 2 · Vistas de lectura (hora de Bogotá sólo aquí) ─────────────────────────

CREATE OR REPLACE VIEW V_ASISTENTE_DIARIO AS
SELECT
    DATE_TRUNC('day', CONVERT_TIMEZONE('America/Bogota', FECHA_HORA))::DATE AS DIA,
    COUNT(*)                                                            AS PREGUNTAS,
    COUNT(DISTINCT SESION_ID)                                           AS SESIONES,
    SUM(IFF(ESTADO = 'exito', 1, 0))                                    AS EXITOSAS,
    SUM(IFF(ESTADO = 'degradada', 1, 0))                                AS DEGRADADAS,
    SUM(IFF(ESTADO IN ('rechazada', 'fallo_sql', 'fallo_analyst', 'error_interno'), 1, 0)) AS FALLIDAS,
    SUM(IFF(ESTADO = 'detenida', 1, 0))                                 AS DETENIDAS,
    -- Analyst pidió más detalle: no es un fallo, es una conversación.
    SUM(IFF(ESTADO = 'sin_sql', 1, 0))                                  AS SIN_CONSULTA,
    SUM(IFF(ESTADO = 'pregunta_invalida', 1, 0))                        AS PREGUNTAS_INVALIDAS,
    SUM(IFF(ES_LISTADO, 1, 0))                                          AS LISTADOS,
    SUM(IFF(EXITO AND NOT DEGRADADO, 1, 0))                             AS TEXTO_ESCRITO_POR_IA,
    ROUND(MEDIAN(MS_TOTAL) / 1000, 1)                                   AS MEDIANA_SEGUNDOS,
    ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY MS_TOTAL) / 1000, 1) AS P90_SEGUNDOS,
    -- Sólo sobre las preguntas que llegaron a esa etapa: un cero duro de una
    -- pregunta rechazada hundiría la mediana justo de lo que se quiere medir.
    ROUND(MEDIAN(IFF(MS_INTERPRETACION > 0, MS_INTERPRETACION, NULL)) / 1000, 1) AS MEDIANA_INTERPRETAR,
    ROUND(MEDIAN(IFF(MS_REDACCION > 0, MS_REDACCION, NULL)) / 1000, 1)  AS MEDIANA_REDACTAR
FROM ASISTENTE_CONSULTAS
GROUP BY 1;

CREATE OR REPLACE VIEW V_ASISTENTE_CALIDAD AS
SELECT
    CONVERT_TIMEZONE('America/Bogota', FECHA_HORA) AS FECHA_HORA_BOGOTA,
    CONSULTA_ID,
    SESION_ID,
    ESTADO,
    MOTIVO_DEGRADACION,
    ETAPA_FALLO,
    ERROR,
    PREGUNTA,
    N_FILAS,
    INTENTOS_SQL,
    ROUND(MS_TOTAL / 1000, 1)          AS SEGUNDOS,
    ROUND(MS_INTERPRETACION / 1000, 1) AS SEG_INTERPRETAR,
    ROUND(MS_CONSULTA / 1000, 1)       AS SEG_CONSULTAR,
    ROUND(MS_CORRECCION / 1000, 1)     AS SEG_CORREGIR,
    ROUND(MS_REDACCION / 1000, 1)      AS SEG_REDACTAR,
    MODELO,
    FORMA_REDACCION,
    APP_VERSION
FROM ASISTENTE_CONSULTAS
WHERE ESTADO <> 'exito';

-- ── 3 · Permisos para el rol del aplicativo ──────────────────────────────────
-- Mínimo privilegio: el aplicativo sólo inserta y lee; no actualiza ni borra.

GRANT USAGE ON SCHEMA APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO TO ROLE IDENTIFIER($ROL_APP);
GRANT INSERT, SELECT ON TABLE APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.ASISTENTE_CONSULTAS TO ROLE IDENTIFIER($ROL_APP);
GRANT INSERT, SELECT ON TABLE APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.ASISTENTE_DESCARGAS TO ROLE IDENTIFIER($ROL_APP);
GRANT SELECT ON VIEW APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.V_ASISTENTE_DIARIO TO ROLE IDENTIFIER($ROL_APP);
GRANT SELECT ON VIEW APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.V_ASISTENTE_CALIDAD TO ROLE IDENTIFIER($ROL_APP);

-- ── 4 · Verificación (misma sesión del paso 1) ───────────────────────────────
-- No se inserta ninguna fila de prueba: sería una fila falsa que se queda para
-- siempre y encabeza justamente las dos consultas que más se miran. Quien
-- comprueba de verdad que el INSERT funciona es el aplicativo, con una pregunta
-- real, y el paso «tabla_asistente_log» del diagnóstico.

-- 4.1 Las dos tablas existen y tienen las columnas que el aplicativo escribe:
DESC TABLE APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.ASISTENTE_CONSULTAS;
DESC TABLE APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.ASISTENTE_DESCARGAS;

-- 4.2 Las dos vistas compilan:
SELECT * FROM APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.V_ASISTENTE_DIARIO ORDER BY DIA DESC LIMIT 5;
SELECT * FROM APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.V_ASISTENTE_CALIDAD ORDER BY FECHA_HORA_BOGOTA DESC LIMIT 5;

-- 4.3 El rol del aplicativo tiene INSERT y SELECT, y NO tiene UPDATE ni DELETE:
SHOW GRANTS ON TABLE APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.ASISTENTE_CONSULTAS;

-- 4.4 La comprobación de verdad: haga una pregunta en /asistente y ejecute
SELECT FECHA_HORA, ESTADO, PREGUNTA FROM APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.ASISTENTE_CONSULTAS
ORDER BY FECHA_HORA DESC LIMIT 5;

-- ── 5 · Qué verá en el aplicativo ────────────────────────────────────────────
-- /api/diagnostico → paso «tabla_asistente_log» en verde y, al final, el bloque
-- «telemetria» con registrados / descartados. Si «descartados» crece, el
-- INSERT está fallando: el campo «ultimo_error» trae la causa.
