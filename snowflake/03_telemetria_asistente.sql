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
    DEGRADADO            BOOLEAN,          -- el texto es el resumen automático
    MOTIVO_DEGRADACION   VARCHAR(60),      -- redaccion_fallo · respuesta_vacia · cifras_sin_respaldo
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
    MODELO               VARCHAR(80),
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
    SUM(IFF(ES_LISTADO, 1, 0))                                          AS LISTADOS,
    ROUND(MEDIAN(MS_TOTAL) / 1000, 1)                                   AS MEDIANA_SEGUNDOS,
    ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY MS_TOTAL) / 1000, 1) AS P90_SEGUNDOS,
    ROUND(MEDIAN(MS_INTERPRETACION) / 1000, 1)                          AS MEDIANA_INTERPRETAR,
    ROUND(MEDIAN(MS_REDACCION) / 1000, 1)                               AS MEDIANA_REDACTAR
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
    APP_VERSION
FROM ASISTENTE_CONSULTAS
WHERE ESTADO <> 'exito'
ORDER BY FECHA_HORA DESC;

-- ── 3 · Permisos para el rol del aplicativo ──────────────────────────────────
-- Mínimo privilegio: el aplicativo sólo inserta y lee; no actualiza ni borra.

GRANT USAGE ON SCHEMA APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO TO ROLE APP_SEGMENTACION_EXPORTACIONES;
GRANT INSERT, SELECT ON TABLE APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.ASISTENTE_CONSULTAS TO ROLE APP_SEGMENTACION_EXPORTACIONES;
GRANT INSERT, SELECT ON TABLE APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.ASISTENTE_DESCARGAS TO ROLE APP_SEGMENTACION_EXPORTACIONES;
GRANT SELECT ON VIEW APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.V_ASISTENTE_DIARIO TO ROLE APP_SEGMENTACION_EXPORTACIONES;
GRANT SELECT ON VIEW APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.V_ASISTENTE_CALIDAD TO ROLE APP_SEGMENTACION_EXPORTACIONES;

-- ── 4 · Verificación (ejecutar con el rol del aplicativo) ────────────────────
-- 4.1 Las tablas existen y están vacías (o no) según lo esperado:
SELECT 'ASISTENTE_CONSULTAS' AS TABLA, COUNT(*) AS FILAS FROM APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.ASISTENTE_CONSULTAS
UNION ALL
SELECT 'ASISTENTE_DESCARGAS', COUNT(*) FROM APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.ASISTENTE_DESCARGAS;

-- 4.2 El rol puede insertar (la fila de prueba se identifica por el CONSULTA_ID):
INSERT INTO APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.ASISTENTE_CONSULTAS (CONSULTA_ID, ESTADO, PREGUNTA, ENTORNO)
VALUES ('prueba000000', 'exito', 'Fila de prueba del script 03', 'prueba');

-- 4.3 Y leerla:
SELECT * FROM APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.V_ASISTENTE_DIARIO ORDER BY DIA DESC LIMIT 5;

-- 4.4 Confirmar que el rol NO tiene UPDATE ni DELETE (mínimo privilegio):
SHOW GRANTS ON TABLE APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.ASISTENTE_CONSULTAS;

-- Después de comprobar, un rol con privilegio de borrado puede retirar la fila
-- de prueba (el rol del aplicativo no puede, y así debe ser):
--   DELETE FROM APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.ASISTENTE_CONSULTAS WHERE CONSULTA_ID = 'prueba000000';

-- ── 5 · Qué verá en el aplicativo ────────────────────────────────────────────
-- /api/diagnostico → paso «tabla_asistente_log» en verde y, al final, el bloque
-- «telemetria» con registrados / descartados. Si «descartados» crece, el
-- INSERT está fallando: el campo «ultimo_error» trae la causa.
