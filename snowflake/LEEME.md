# Artefactos de Snowflake del asistente

Esta carpeta guarda, versionado junto al código, lo que vive **dentro** de la
cuenta de Snowflake y de lo que depende el asistente de análisis. Si algún día
hay que reconstruir la cuenta, todo lo necesario está aquí.

| Archivo | Qué es |
|---|---|
| `TEJIDO_EMPRESARIAL_SEGMENTACION.sv.yaml` | El **modelo semántico**: 60 dimensiones, 42 hechos, 35 métricas, 16 filtros y 13 consultas verificadas sobre la tabla del tejido empresarial. Es lo que le permite a Cortex Analyst traducir una pregunta en español a SQL correcta. |
| `AGENTE_TEJIDO_EMPRESARIAL.agent.yaml` | Especificación del agente de Cortex, por si se quiere exponer el mismo modelo en Snowflake Intelligence o en Teams. **El aplicativo no lo usa** (ver abajo). |
| `01_permisos_asistente.sql` | Los permisos mínimos y las cuatro consultas de verificación. |

## Qué usa el aplicativo, y por qué

El asistente llama a **Cortex Analyst** (`/api/v2/cortex/analyst/message`), no al
agente. La diferencia importa:

- **Cortex Analyst** sólo devuelve la SQL. El aplicativo la revisa (una sola
  sentencia de lectura, esquemas permitidos, tope de filas), la ejecuta con su
  propio rol y comprueba que cada cifra del texto exista en el resultado. Por eso
  puede mostrar la consulta y la tabla que respaldan cada respuesta.
- **Cortex Agent** orquesta y ejecuta por su cuenta. Es más cómodo, pero deja
  fuera del aplicativo justo el paso que da la garantía: la verificación.

El agente se conserva porque sirve para el mismo modelo en otros canales y
porque documenta las instrucciones de negocio acordadas.

## Si cambia el modelo semántico

1. Edite el YAML de esta carpeta.
2. Redespliéguelo:
   ```sql
   SELECT SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML(
     'APP_SEGMENTACION_EXPORTACIONES.SEGMENTACION',
     $$<contenido completo del YAML>$$);
   ```
3. Verifique con `DESCRIBE SEMANTIC VIEW …` y pruebe en `/asistente` las
   preguntas sugeridas.

**Regla aprendida:** el estado declarado no es el estado desplegado. Después de
cualquier cambio hecho en la interfaz de Snowsight, vuelva a exportar el YAML a
esta carpeta; no confíe en la memoria de cuántas consultas verificadas hay.

## Cuando llegue un corte nuevo de datos

Si la tabla suma columnas (`EXPO_2026`, `NUMERO_NEGOCIOS_2027`…), hay que
agregarlas al YAML como hechos y métricas, y actualizar `custom_instructions`
para que «año corrido» apunte al periodo nuevo. Mientras eso no se haga, el
asistente seguirá respondiendo con los periodos viejos sin avisar.
