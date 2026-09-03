-- =============================================================================
-- Elegir el modelo de redacción del asistente, midiendo en SU cuenta
-- =============================================================================
-- Qué hace el modelo en este aplicativo: NADA de la consulta. La SQL la genera
-- Cortex Analyst (que usa sus propios modelos y no se configura aquí) y las
-- cifras las verifica el backend contra la tabla. El modelo sólo escribe 2 a 5
-- frases a partir de una tabla ya calculada.
--
-- Consecuencia práctica: es una tarea corta y acotada. Un modelo grande no
-- mejora la exactitud de las cifras —eso ya está garantizado por el código— y
-- sí cuesta más tiempo y más créditos. Por eso conviene medir.
--
-- La disponibilidad de modelos cambia por región y con el tiempo. Este script no
-- asume cuáles existen: prueba una lista de candidatos y el que no esté
-- disponible dará error en SU sentencia, sin afectar a las demás.
--
-- Ejecutar con el rol del aplicativo (el que tiene SNOWFLAKE.CORTEX_USER).
-- =============================================================================

USE WAREHOUSE APPS_WH;

-- Prompt equivalente al que envía el asistente: una tabla pequeña y la
-- instrucción de resumirla en español. Medir con esto y no con «hola» es la
-- diferencia entre un número útil y uno decorativo.
SET PROMPT = 'Eres el analista del aplicativo Tejido Empresarial de ProColombia. Responde en español, en 2 a 5 frases claras y profesionales, usando EXCLUSIVAMENTE los datos de la tabla. No inventes cifras. Pregunta: ¿Cuáles son las principales empresas exportadoras de café?

Tabla de resultados (5 filas):
NIT | Razón social | Departamento | Exportaciones 2024 (USD FOB)
--- | --- | --- | ---
890300406 | RACAFE Y CIA S C A | Caldas | 214531880,45
860002536 | OLAM AGRO COLOMBIA S A S | Bogotá, D.C. | 198442310,10
890900608 | LOUIS DREYFUS COMPANY COLOMBIA S A S | Antioquia | 176003921,77
800016186 | SUCDEN COLOMBIA S A S | Bogotá, D.C. | 121885004,32
860007538 | CARCAFE LTDA | Bogotá, D.C. | 118770210,60

Respuesta:';

-- =============================================================================
-- 1 · Medición. Ejecute las líneas UNA POR UNA y anote el tiempo que informa
--     Snowsight en cada una (columna «Duration» del panel de resultados).
--     Si un modelo no está disponible en su región, esa línea dará error:
--     táchelo de la lista y siga con el siguiente.
-- =============================================================================

-- Rápidos y económicos (candidatos preferidos para esta tarea)
SELECT 'claude-3-5-haiku'  AS MODELO, SNOWFLAKE.CORTEX.COMPLETE('claude-3-5-haiku',  $PROMPT) AS RESPUESTA;
SELECT 'llama3.1-8b'       AS MODELO, SNOWFLAKE.CORTEX.COMPLETE('llama3.1-8b',       $PROMPT) AS RESPUESTA;
SELECT 'mistral-7b'        AS MODELO, SNOWFLAKE.CORTEX.COMPLETE('mistral-7b',        $PROMPT) AS RESPUESTA;

-- Intermedios (buen español, coste medio)
SELECT 'llama3.3-70b'      AS MODELO, SNOWFLAKE.CORTEX.COMPLETE('llama3.3-70b',      $PROMPT) AS RESPUESTA;
SELECT 'mistral-large2'    AS MODELO, SNOWFLAKE.CORTEX.COMPLETE('mistral-large2',    $PROMPT) AS RESPUESTA;

-- Grandes (los que hoy usa: más caros y más lentos para esta tarea)
SELECT 'claude-3-5-sonnet' AS MODELO, SNOWFLAKE.CORTEX.COMPLETE('claude-3-5-sonnet', $PROMPT) AS RESPUESTA;
SELECT 'claude-3-7-sonnet' AS MODELO, SNOWFLAKE.CORTEX.COMPLETE('claude-3-7-sonnet', $PROMPT) AS RESPUESTA;
SELECT 'claude-4-sonnet'   AS MODELO, SNOWFLAKE.CORTEX.COMPLETE('claude-4-sonnet',   $PROMPT) AS RESPUESTA;

-- =============================================================================
-- 2 · Cómo decidir
-- =============================================================================
-- Lea las respuestas y descarte los modelos que:
--   · no escriban en español correcto,
--   · inventen una cifra que no está en la tabla (el aplicativo lo detectaría y
--     degradaría la respuesta, pero entonces el modelo no aporta nada),
--   · omitan la unidad (USD FOB) o el periodo.
--
-- Entre los que quedan, elija el más rápido. Para esta tarea la diferencia de
-- calidad entre un modelo intermedio y uno grande es mínima; la de tiempo, no.

-- =============================================================================
-- 3 · Cuánto cuesta de verdad (créditos consumidos, últimos 7 días)
-- =============================================================================
-- Los precios por modelo están en la «Snowflake Service Consumption Table» de su
-- contrato, en créditos por millón de tokens. En vez de estimarlos, mire lo que
-- realmente consumió:

SELECT MODEL_NAME,
       COUNT(*)                       AS LLAMADAS,
       SUM(TOKENS)                    AS TOKENS,
       ROUND(SUM(TOKEN_CREDITS), 4)   AS CREDITOS
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_FUNCTIONS_USAGE_HISTORY
WHERE START_TIME >= DATEADD('day', -7, CURRENT_TIMESTAMP())
GROUP BY MODEL_NAME
ORDER BY CREDITOS DESC;

-- Y lo que consume Cortex Analyst, que se cobra por mensaje y NO depende del
-- modelo que usted configure aquí:
SELECT DATE_TRUNC('day', START_TIME) AS DIA, COUNT(*) AS MENSAJES, SUM(CREDITS) AS CREDITOS
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_ANALYST_USAGE_HISTORY
WHERE START_TIME >= DATEADD('day', -7, CURRENT_TIMESTAMP())
GROUP BY 1 ORDER BY 1 DESC;

-- Nota: las vistas de ACCOUNT_USAGE tienen retraso (hasta 3 horas) y requieren
-- un rol con acceso a la base SNOWFLAKE. Si no las ve, pídalas al administrador.

-- =============================================================================
-- 4 · Aplicar la elección
-- =============================================================================
-- En Railway → su servicio → Variables:
--
--     SF_CORTEX_MODEL = <el modelo elegido>
--
-- Guarde y espere el redespliegue. En la página del asistente, debajo de cada
-- respuesta, aparece el desglose de tiempos y el nombre del modelo que la
-- escribió: sirve para confirmar que el cambio tuvo efecto.
