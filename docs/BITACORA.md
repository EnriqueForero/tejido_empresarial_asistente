# Bitácora

Qué se hizo, cuándo y con qué resultado, en orden cronológico. El CHANGELOG
dice qué cambió en cada versión; esta bitácora dice cómo se llegó allí. Las
decisiones de fondo están en `DECISIONES.md`; los fallos, en `INCIDENTES.md`.

## 2026-09-04 · 3.5.0 — puesta a punto del asistente

**Punto de partida.** Producción (dominio nuevo, 3.4.2) con conexión verificada.
Una consulta de 135 filas tardó 149,5 s y mostró el resumen determinista bajo
el sello «Cifras verificadas». El propietario pidió además: gráfica sólo bajo
pedido, memoria conversacional que termine en un listado descargable con el
formato estándar, tabla de métricas como la de ExportBot, NIT de ejemplo reales
y una puesta a punto general sin deuda técnica.

**Método.** Auditoría de solo lectura por siete lentes (latencia, memoria y
listado, telemetría, seguridad, modelo semántico, arquitectura, experiencia),
síntesis y crítica de completitud; plan por fases aprobado por el propietario;
ejecución con pruebas por cada cambio y verificación visual contra un servidor
simulado que usa el orquestador real.

**Fase 1 · corregir lo que falla o es inseguro.** `sql_literal` escapa la barra
invertida; `log_event` con parámetros enlazados; reintento de sesión sólo ante
errores de sesión; forma con opciones de COMPLETE con casts explícitos y una
única alternativa ante error de firma; degradación con causa (`motivo_degradacion`)
y tres estados en pantalla; desglose con corrección e intentos; guardas por
fichas con orígenes de datos verificados; tope de filas sin envolver la
consulta; sumas y promedios aceptados sólo con resultado completo; resultados
en el servidor por `consulta_id`; descargas completas; columnas legibles;
contacto gobernado; historial reconstruido en el servidor; SSE con latido y
«Detener»; sesión y `STATEMENT_TIMEOUT` en el conector; sesión abierta al
arrancar.

**Fase 3 · telemetría.** `SEGUIMIENTO.ASISTENTE_CONSULTAS` y
`ASISTENTE_DESCARGAS`, dos vistas, cola en segundo plano, todas las salidas
registradas, contador de descartes en el diagnóstico, `docs/METRICAS.md`.

**Fase 2 · interfaz.** Gráfica bajo pedido (o indicador), listado con
`TablaEmpresas` y descarga estándar, memoria visible con «Empezar un hilo
nuevo», tarjeta de progreso con cronómetro y etapas, sugerencias siempre
accesibles, consultas relacionadas, consulta ejecutada con «Copiar», contador
de caracteres, NIT de ejemplo reales en consulta, lote y sugerencia.

**Fase 4 · modelo semántico.** 23 consultas verificadas (una por cada
pregunta sugerida, más una cadena de refinamiento), 2025 como año por defecto,
`CADENA` → `CADENA_EXPORTADA`, contrato de listados sin contacto, instrucciones
de continuidad, 10 dimensiones inútiles fuera, 7 métricas faltantes,
`tests/test_modelo_semantico.py`.

**Fase 5 · arquitectura y documentación.** `main.py` (887 líneas) repartido en
`comun`, `middleware` y cuatro routers, con prueba de contrato de rutas;
HSTS y COOP; token de diagnóstico por cabecera; mínimo privilegio en
`snowflake/04_minimo_privilegio.sql`; `docs/` con decisiones, incidentes,
métricas y esta bitácora; CLAUDE.md con invariantes y definición de terminado;
README con «Activar usuario y contraseña».

**Resultado.** 129 pruebas de backend en verde, build del frontend limpio,
capturas de los estados del asistente en `previews/`. Queda para producción:
ejecutar `03_telemetria_asistente.sql` y `04_minimo_privilegio.sql`,
redesplegar el YAML, y leer el paso «cortex_complete» del diagnóstico.

## 2026-09-03 · 3.4.2 — entrega progresiva y notebook

Tabla y gráfica antes que el texto; salida del modelo acotada; tabla del prompt
de 30 a 20 filas; notebook con CHANGELOG antes de escribir versiones, tag
existente con salida explícita, `siguiente_version()`.

## 2026-09-03 · 3.4.0 / 3.4.1 — asistente de análisis

Módulo `backend/ia/` (Analyst, guardas, redactor, gráficas, exportadores,
orquestador), página `/asistente`, modelo semántico y permisos en `snowflake/`,
repositorio y servicio nuevos aislados del anterior.

## 2026-09-03 · 3.3.1 — pyarrow

Producción con conexión verificada y consultas en 502: la imagen no traía
pyarrow. Extra `[pandas]`, vía alterna por filas, causa real en los mensajes.

## 2026-09-03 · 3.3.0 — página de estado

`/estado` con pastilla de conexión, prueba real y diagnóstico paso a paso;
guía `DIAGNOSTICO_RAILWAY.md` con la URL literal del servicio.
