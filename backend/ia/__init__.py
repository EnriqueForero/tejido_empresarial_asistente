"""
Asistente de análisis del Tejido Empresarial.

Traduce preguntas en español a SQL con **Snowflake Cortex Analyst**, ejecuta esa
SQL con la misma conexión y el mismo rol de solo lectura que el resto del
aplicativo, y redacta la respuesta con **SNOWFLAKE.CORTEX.COMPLETE**.

El único conector del aplicativo es Snowflake: no hay proveedores de IA
externos, ninguna clave adicional y ningún dato sale de la cuenta.

La regla que gobierna el módulo: **el modelo propone, el código dispone.** Cortex
Analyst sólo genera SQL; la validación (una sola sentencia de lectura, esquemas
permitidos, tope de filas), la ejecución y la verificación de que cada cifra
citada exista en el resultado ocurren aquí. Por eso el aplicativo puede mostrar
la SQL y la tabla que respaldan cada respuesta.
"""
