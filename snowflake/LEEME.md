# Artefactos de Snowflake del asistente

Esta carpeta guarda, versionado junto al código, lo que vive **dentro** de la
cuenta de Snowflake y de lo que depende el asistente de análisis. Si algún día
hay que reconstruir la cuenta, todo lo necesario está aquí.

| Archivo | Qué es | Cuándo ejecutarlo |
|---|---|---|
| `TEJIDO_EMPRESARIAL_SEGMENTACION.sv.yaml` | El **modelo semántico**: 50 dimensiones, 42 hechos, 42 métricas, 16 filtros y **23 consultas verificadas** (una por cada pregunta sugerida en la página y una cadena de refinamiento conteo → filtro → listado). Es lo que le permite a Cortex Analyst traducir una pregunta en español a SQL correcta. | Al instalar y cada vez que cambie (ver abajo). |
| `01_permisos_asistente.sql` | `SNOWFLAKE.CORTEX_USER` y `SELECT` sobre la vista semántica para el rol del aplicativo, con cuatro verificaciones. | Una vez. |
| `02_comparar_modelos.sql` | Mide en su cuenta el tiempo de cada modelo de redacción con el prompt real, prueba la **forma con opciones** que usa el aplicativo y consulta los créditos consumidos. | Cuando quiera cambiar `SF_CORTEX_MODEL` o entender un fallo de `cortex_complete`. |
| `03_telemetria_asistente.sql` | Tablas `SEGUIMIENTO.ASISTENTE_CONSULTAS` y `ASISTENTE_DESCARGAS`, vistas `V_ASISTENTE_DIARIO` y `V_ASISTENTE_CALIDAD`, permisos `INSERT`/`SELECT`. | Una vez (3.5.0). Consultas listas en `docs/METRICAS.md`. |
| `04_minimo_privilegio.sql` | Retira `UPDATE`/`DELETE` sobre `EVENTOS` y muestra cómo revisar la herencia de `APPS_MANAGER`. | Una vez (3.5.0). |
| `AGENTE_TEJIDO_EMPRESARIAL.agent.yaml` | Especificación del agente de Cortex, por si se quiere exponer el mismo modelo en Snowflake Intelligence o en Teams. **El aplicativo no lo usa** (ver abajo). | Opcional. |

## Qué usa el aplicativo, y por qué

El asistente llama a **Cortex Analyst** (`/api/v2/cortex/analyst/message`), no al
agente. La diferencia importa:

- **Cortex Analyst** sólo devuelve la SQL. El aplicativo la revisa (una sola
  sentencia de lectura, orígenes de datos en los esquemas permitidos, tope de
  filas), la ejecuta con su propio rol y comprueba que cada cifra del texto
  exista en el resultado. Por eso puede mostrar la consulta y la tabla que
  respaldan cada respuesta, y decir cuándo la redacción no pudo verificarse.
- **Cortex Agent** orquesta y ejecuta por su cuenta. Es más cómodo, pero deja
  fuera del aplicativo justo el paso que da la garantía.

## Qué cambió en el modelo semántico en 3.5.0

- **Una consulta verificada por cada pregunta sugerida**, con la redacción
  exacta de la página y `use_as_onboarding_question: true`. Analyst responde en
  segundos a esas preguntas y sin ambigüedad. `tests/test_modelo_semantico.py`
  exige que sigan alineadas.
- **2025 es el año por defecto** («último año completo»); «año corrido» es
  enero-mayo 2026 frente a 2025; «últimos 5 años» es `TOTAL_EXPO_2021_2025`.
- `CADENA` pasa a llamarse **`CADENA_EXPORTADA`** (mismo `expr: CADENA`): «cadena»
  a secas es `CADENA_SEGMENTACION`, que aplica a todas las empresas.
- **Contrato de listados**: NIT, RAZON_SOCIAL, TAMANO, DEPARTAMENTO_EMP,
  MUNICIPIO_EMP + hasta tres columnas, ORDER BY y LIMIT 100; sin correo,
  teléfono, dirección ni representante salvo que la pregunta los pida.
- **Continuidad**: cuando la pregunta sigue a la anterior («de esas»,
  «lístame»), conserva todos los filtros y agrega sólo lo nuevo.
- Se retiraron 10 dimensiones que el propio YAML declaraba redundantes
  (`*_BASE_MUNICIPIOS`, CIIU 3 y 4) y se añadieron las métricas simétricas que
  faltaban (2023, enero-junio 2026, exportadoras NME). Las métricas de
  indicadores municipales citan el hecho `PCT_*`, no la columna física.
- Los `sample_values` de NIT son los NIT de ejemplo reales del aplicativo.

## Si cambia el modelo semántico

1. Edite el YAML de esta carpeta y ejecute `pytest tests/test_modelo_semantico.py`.
2. Redespliéguelo en Snowsight:
   ```sql
   SELECT SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML(
     'APP_SEGMENTACION_EXPORTACIONES.SEGMENTACION',
     $$<contenido completo del YAML>$$);
   ```
   Si la vista ya existe, elimínela antes (`DROP SEMANTIC VIEW …`) o use el
   editor de Snowsight para reemplazarla; después repita el `GRANT SELECT` del
   guion `01`.
3. Verifique con `DESCRIBE SEMANTIC VIEW …` y con el paso `vista_semantica` de
   `/api/diagnostico`; pruebe en `/asistente` las preguntas sugeridas.

**Regla aprendida:** el estado declarado no es el estado desplegado. Después de
cualquier cambio hecho en la interfaz de Snowsight, vuelva a exportar el YAML a
esta carpeta.

## Cuando llegue un corte nuevo de datos

Si la tabla suma columnas (`EXPO_2026`, `NUMERO_NEGOCIOS_2027`…), hay que
agregarlas al YAML como hechos y métricas, cambiar el año por defecto en
`custom_instructions` y en las consultas verificadas, y redesplegar. Mientras
eso no se haga, el asistente seguirá respondiendo con los periodos viejos sin
avisar. `docs/METRICAS.md` explica cómo detectar, en la tabla de consultas, las
preguntas repetidas que conviene volver verificadas.
