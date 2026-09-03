-- =============================================================================
-- Permisos mínimos para el asistente de análisis del Tejido Empresarial
-- =============================================================================
-- Ejecutar UNA vez, con un rol administrador (ACCOUNTADMIN o quien sea dueño de
-- la base). Reemplace <ROL_DEL_APLICATIVO> por el valor de la variable SF_ROLE
-- que tiene configurada en Railway (por defecto APP_SEGMENTACION_EXPORTACIONES).
--
-- El asistente NO necesita credenciales nuevas: usa la misma llave RSA y el
-- mismo usuario de servicio que ya consulta la base. Lo único que hace falta es
-- que ese rol pueda (1) leer la vista semántica y (2) usar Cortex.
-- =============================================================================

USE ROLE ACCOUNTADMIN;

SET ROL_APP = 'APP_SEGMENTACION_EXPORTACIONES';   -- ← su SF_ROLE

-- 1 · Uso de Cortex (Analyst para traducir la pregunta, COMPLETE para redactar).
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE IDENTIFIER($ROL_APP);

-- 2 · Lectura de la vista semántica que define qué puede preguntarse.
GRANT SELECT ON SEMANTIC VIEW
  APP_SEGMENTACION_EXPORTACIONES.SEGMENTACION.TEJIDO_EMPRESARIAL_SEGMENTACION
  TO ROLE IDENTIFIER($ROL_APP);

-- 3 · La tabla de datos ya debería estar concedida (el aplicativo la consulta
--     desde antes). Se repite por si el rol es nuevo.
GRANT USAGE ON DATABASE APP_SEGMENTACION_EXPORTACIONES TO ROLE IDENTIFIER($ROL_APP);
GRANT USAGE ON SCHEMA APP_SEGMENTACION_EXPORTACIONES.SEGMENTACION TO ROLE IDENTIFIER($ROL_APP);
GRANT SELECT ON TABLE
  APP_SEGMENTACION_EXPORTACIONES.SEGMENTACION.TEJIDO_EMPRESARIAL_COMPLETO_BASE_MUNICIPIOS_P
  TO ROLE IDENTIFIER($ROL_APP);

-- =============================================================================
-- VERIFICACIÓN — cada paso debe devolver lo que se indica
-- =============================================================================

-- (a) La vista semántica existe y el rol la ve.
DESCRIBE SEMANTIC VIEW APP_SEGMENTACION_EXPORTACIONES.SEGMENTACION.TEJIDO_EMPRESARIAL_SEGMENTACION;
--     → devuelve las dimensiones, hechos y métricas del modelo.

-- (b) La base es la que espera el modelo (valores de referencia al 2026-09-03).
SELECT COUNT(*) AS filas,
       COUNT(DISTINCT NIT) AS nits,
       SUM(IFF(HA_EXPORTADO = 'Sí', 1, 0)) AS exportadoras
FROM APP_SEGMENTACION_EXPORTACIONES.SEGMENTACION.TEJIDO_EMPRESARIAL_COMPLETO_BASE_MUNICIPIOS_P;
--     → 1.678.643 | 1.678.568 | 14.838

-- (c) El rol puede redactar con Cortex.
SELECT SNOWFLAKE.CORTEX.COMPLETE('claude-3-5-sonnet', 'Responde solo: listo') AS PRUEBA;
--     → una respuesta breve, sin error de privilegios.

-- (d) Consulta directa a la vista semántica, sin IA (sirve para tableros).
SELECT * FROM SEMANTIC_VIEW(
  APP_SEGMENTACION_EXPORTACIONES.SEGMENTACION.TEJIDO_EMPRESARIAL_SEGMENTACION
  METRICS numero_empresas, numero_exportadoras, pct_exportadoras
  DIMENSIONS departamento_emp
) ORDER BY numero_empresas DESC LIMIT 10;
--     → Bogotá, D.C. y Antioquia encabezan la lista.

-- =============================================================================
-- Si (a) falla: la vista semántica no está desplegada. Despliéguela con el YAML
-- de esta misma carpeta:
--
--   SELECT SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML(
--     'APP_SEGMENTACION_EXPORTACIONES.SEGMENTACION',
--     $$<contenido de TEJIDO_EMPRESARIAL_SEGMENTACION.sv.yaml>$$);
--
-- Si (c) falla con «Insufficient privileges»: falta el paso 1.
-- =============================================================================
