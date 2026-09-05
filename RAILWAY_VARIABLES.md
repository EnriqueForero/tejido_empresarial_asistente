# Variables de entorno en Railway

Todo lo que hay que configurar en **Railway → su servicio → pestaña Variables**
para que el aplicativo funcione, incluido el asistente de análisis. El servicio
actual es `https://tejidoempresarialasistente-production.up.railway.app/`.

**El asistente no pide ninguna credencial nueva**: firma la API de Cortex con
la misma llave RSA. La versión 3.5.0 tampoco añade variables obligatorias.

---

## 1 · Obligatorias — sin ellas el aplicativo no consulta

| Variable | Valor | Nota |
|---|---|---|
| `SF_ACCOUNT` | `my17686.us-east-2.aws` | El identificador con el que entra a Snowflake por el navegador, sin `https://` ni `.snowflakecomputing.com`. |
| `SF_USER` | El usuario de servicio | Debe ser el **dueño de la llave pública** registrada con `ALTER USER … SET RSA_PUBLIC_KEY`. |
| `SF_DATABASE` | `APP_SEGMENTACION_EXPORTACIONES` | |
| `SF_SCHEMA` | `SEGMENTACION` | |
| `SF_WAREHOUSE` | `APPS_WH` | |
| `SF_ROLE` | `APP_SEGMENTACION_EXPORTACIONES` | Es el rol que necesita los permisos de Cortex (ver `ASISTENTE.md` §3). |
| `SF_PRIVATE_KEY_B64_1` | La llave privada en Base64 | Ver abajo cómo generarla. En una sola línea. |

**Cómo obtener `SF_PRIVATE_KEY_B64_1`.** En PowerShell, en la carpeta donde está
el archivo `.der`:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("rsa_key_1.der")) | Set-Clipboard
```

Pegue el resultado sin comillas. Si al pegar queda en varias líneas no importa:
el aplicativo tolera espacios y saltos.

---

## 2 · Recomendadas — protegen el aplicativo

| Variable | Valor sugerido | Para qué |
|---|---|---|
| `APP_BASIC_USER` | `procolombia` | Pide usuario y contraseña al entrar. Hoy el acceso está abierto por decisión del propietario; las descargas incluyen correo, teléfono y dirección de empresas reales. El README explica el paso a paso («Activar usuario y contraseña»). |
| `APP_BASIC_PASSWORD` | Una contraseña larga que usted elija | Las dos van juntas: si configura una sola, el aplicativo responde 503 a propósito. |
| `PUBLIC_ORIGIN` | `https://tejidoempresarialasistente-production.up.railway.app` | Sólo para las tarjetas al compartir el enlace. |

---

## 3 · Opcionales — sólo si necesita cambiar un comportamiento

| Variable | Valor por defecto | Cuándo tocarla |
|---|---|---|
| `APP_ENV` | `production` (lo pone el Dockerfile) | `development` habilita `/api/docs` y abre el diagnóstico. No lo use en producción. |
| `APP_DEMO_MODE` | ausente = `false` | `true` muestra 14 empresas de ejemplo sin tocar Snowflake. **Con `true` el asistente se desactiva.** |
| `APP_DIAG_TOKEN` | vacío | Permite abrir el diagnóstico sin contraseña: `/estado?token=EL_VALOR` (o cabecera `X-Diag-Token`). Innecesaria si configuró `APP_BASIC_USER`/`APP_BASIC_PASSWORD`. |
| `EXPORT_MAX_ROWS` | `5000` | Máximo de empresas por archivo de Excel (también para el listado del asistente). |
| `EXPORT_INCLUDE_CONTACT_FIELDS` | `true` | `false` quita dirección, teléfono, correo y representante legal de las descargas, las fichas **y el asistente**. |
| `MAX_REQUEST_BYTES` | `2000000` | Tamaño máximo de una petición. |
| `LOG_LEVEL` | `INFO` | `DEBUG` para más detalle en los registros de Railway. |
| `SF_PRIVATE_KEY_PASSPHRASE_1` | vacío | Sólo si la llave privada está cifrada. |
| `SF_PRIVATE_KEY_B64_2` · `SF_PRIVATE_KEY_PASSPHRASE_2` | vacías | Llave de respaldo para rotar sin cortar el servicio. **No configure la 2 si su pública no está registrada en Snowflake**: el failover hacia ella sólo produce errores 401. En el servicio actual está configurada; si no la usa, retírela. |
| `SF_LOGIN_TIMEOUT` · `SF_NETWORK_TIMEOUT` | `30` · `60` | Segundos. Sólo si su red es especialmente lenta. |
| `SF_STATEMENT_TIMEOUT` | `300` | Segundos que Snowflake da a cualquier sentencia del aplicativo (incluida la redacción). |

---

## 4 · Opcionales del asistente — todas tienen el valor correcto por defecto

| Variable | Valor por defecto | Cuándo tocarla |
|---|---|---|
| `SF_SEMANTIC_VIEW` | `APP_SEGMENTACION_EXPORTACIONES.SEGMENTACION.TEJIDO_EMPRESARIAL_SEGMENTACION` | Si despliega el modelo semántico con otro nombre. |
| `SF_CORTEX_MODEL` | `claude-haiku-4-5` | Sólo afecta a las 2-5 frases del resumen. **Los nombres de los modelos caducan**: si el asistente entrega el resumen automático en vez del texto escrito, abra `/estado` → «Probar la redacción con IA»: dice si éste responde y, si no, cuáles sí. |
| `SF_ALLOWED_SCHEMAS` | `APP_SEGMENTACION_EXPORTACIONES.SEGMENTACION,APP_SEGMENTACION_EXPORTACIONES.PUBLIC` | Si el asistente debe poder leer otro esquema. |
| `SF_HOST` | derivado de `SF_ACCOUNT` | Sólo si su cuenta usa un dominio distinto de `<SF_ACCOUNT>.snowflakecomputing.com`. |
| `IA_MAX_ROWS` | `5000` | Tope de filas que trae una consulta del asistente. |
| `IA_MAX_ROWS_CLIENT` | `500` | Filas que viajan al navegador (las descargas traen todas). |
| `IA_ANALYST_TIMEOUT` | `45` | Segundos de espera a Cortex Analyst por llamada. |
| `IA_HISTORY_TURNS` | `4` | Mensajes previos que se reenvían a Analyst (4 = dos preguntas anteriores). |
| `IA_RESULT_CAPACITY` · `IA_RESULT_TTL` | `50` · `1800` | Cuántos resultados conserva el servidor para descargar y por cuántos segundos. |
| `IA_REDACCION_FALLOS_PARA_PAUSA` · `IA_REDACCION_PAUSA` | `3` · `600` | Tras esos fallos seguidos, la redacción con IA se pausa esos segundos y las respuestas dejan de esperarla. |
| `NITS_EJEMPLO` | `890903938,811000740,890912462` | NIT de ejemplo en la consulta, el lote y la pregunta sugerida. |
| `ASISTENTE_LOG_TABLE` · `ASISTENTE_DOWNLOAD_TABLE` | `…SEGUIMIENTO.ASISTENTE_CONSULTAS` · `…SEGUIMIENTO.ASISTENTE_DESCARGAS` | Sólo si crea las tablas de métricas con otro nombre. |

---

## 5 · Lo que NO se configura en Railway

Los permisos y las tablas del asistente van **en Snowflake**, no aquí. En
orden: `snowflake/01_permisos_asistente.sql`, `snowflake/03_telemetria_asistente.sql`,
`snowflake/04_minimo_privilegio.sql` y el redespliegue del YAML (`snowflake/LEEME.md`).
El detalle está en `ASISTENTE.md` §3.

---

## 6 · Copiar y pegar en Railway

Railway admite pegar varias variables de una vez con el botón **Raw Editor**.
Esta es la plantilla mínima; reemplace lo que está entre `<…>`:

```
SF_ACCOUNT=my17686.us-east-2.aws
SF_USER=<usuario de servicio>
SF_DATABASE=APP_SEGMENTACION_EXPORTACIONES
SF_SCHEMA=SEGMENTACION
SF_WAREHOUSE=APPS_WH
SF_ROLE=APP_SEGMENTACION_EXPORTACIONES
SF_PRIVATE_KEY_B64_1=<la llave en Base64, en una sola línea>
PUBLIC_ORIGIN=https://tejidoempresarialasistente-production.up.railway.app
```

Railway inyecta `PORT` por su cuenta: **no la configure**.

---

## 7 · Cómo comprobar que quedó bien

1. Abra `https://tejidoempresarialasistente-production.up.railway.app/estado`.
   Debe decir **Datos reales**. Pulse **Ejecutar diagnóstico**: todos los pasos
   en verde, incluidos `vista_semantica`, `tabla_asistente_log` y `cortex_complete`.
2. Vaya a **Consultar** y haga una búsqueda: los filtros deben traer
   departamentos y cadenas reales; los chips de NIT muestran 890903938,
   811000740 y 890912462.
3. Vaya a **Asistente** y pulse la primera pregunta sugerida.
4. Descargue el Excel de esa respuesta.

Si algo falla, la página `/estado` dice en qué paso y qué corregir; el
procedimiento está en `DIAGNOSTICO_RAILWAY.md` y, para el asistente, en
`ASISTENTE.md` §5.
