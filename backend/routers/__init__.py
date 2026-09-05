"""
Routers de la API, uno por dominio:

- ``salud``     · /api/health y /api/diagnostico
- ``empresas``  · metadatos, filtros, consulta, ficha y descarga estándar
- ``asistente`` · el asistente de análisis (Snowflake Cortex)
- ``recursos``  · glosario, documentos, y los comodines de API y SPA (van al final)

`backend/main.py` sólo los ensambla. Lo compartido vive en `backend/comun.py`.
"""
