-- =============================================================================
-- Mínimo privilegio para el rol del aplicativo (decisión D-06)
-- =============================================================================
-- El guion inicial (setup/03) concedió INSERT, UPDATE y DELETE sobre
-- SEGUIMIENTO.EVENTOS. El aplicativo sólo INSERTA auditoría y telemetría; con
-- el asistente ejecutando SQL propuesta por un modelo —aunque validada—, el
-- privilegio del rol es la última barrera y debe ser el mínimo.
--
-- Ejecutar UNA vez con un rol administrador. Es idempotente: si el privilegio
-- ya no existe, REVOKE no falla.
-- =============================================================================

USE ROLE ACCOUNTADMIN;

SET ROL_APP = 'APP_SEGMENTACION_EXPORTACIONES';   -- ← su SF_ROLE

-- 1 · Retirar lo que el aplicativo nunca usa.
REVOKE UPDATE, DELETE ON TABLE APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.EVENTOS FROM ROLE IDENTIFIER($ROL_APP);

-- 2 · Confirmar lo que sí necesita (idempotente).
GRANT SELECT, INSERT ON TABLE APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.EVENTOS TO ROLE IDENTIFIER($ROL_APP);

-- 3 · Verificación: ninguna fila de esta salida debe tener privilege UPDATE ni DELETE.
SHOW GRANTS TO ROLE IDENTIFIER($ROL_APP);
SELECT "privilege", "granted_on", "name"
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "privilege" IN ('UPDATE', 'DELETE', 'TRUNCATE', 'OWNERSHIP')
ORDER BY "name";
--     → 0 filas (o sólo OWNERSHIP sobre objetos que el rol creó a propósito).

-- =============================================================================
-- 4 · Revisión pendiente del administrador (no la hace este guion)
-- =============================================================================
-- setup/03 tiene:
--     GRANT ROLE APPS_MANAGER TO ROLE APP_SEGMENTACION_EXPORTACIONES;
-- Con eso, el rol del aplicativo HEREDA todo lo que tenga APPS_MANAGER. La
-- dirección habitual es la contraria (el rol de gestión hereda el del
-- aplicativo, para poder administrarlo). Revisar con:
SHOW GRANTS TO ROLE IDENTIFIER($ROL_APP);
--     → si aparece una fila con granted_on = ROLE y name = APPS_MANAGER, el
--       aplicativo tiene más de lo que necesita. Corregir, si procede:
--     REVOKE ROLE APPS_MANAGER FROM ROLE APP_SEGMENTACION_EXPORTACIONES;
--     GRANT ROLE APP_SEGMENTACION_EXPORTACIONES TO ROLE APPS_MANAGER;
-- Hágalo sólo después de confirmar que el aplicativo no depende de ningún
-- privilegio heredado: ejecute /api/diagnostico después del cambio.
