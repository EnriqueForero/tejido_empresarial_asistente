# Variables de entorno en Railway

Todo lo que hay que configurar en **Railway → su servicio → pestaña Variables**
para que el aplicativo funcione, incluido el asistente de análisis.

**Nada de esto cambia respecto al despliegue que ya tiene funcionando.** El
asistente no pide ninguna credencial nueva: firma la API de Cortex con la misma
llave RSA. Si va a crear un servicio nuevo desde el repositorio nuevo, esta es la
lista completa que hay que copiar.

---

## 1 · Obligatorias — sin ellas el aplicativo no consulta

| Variable | Valor | Nota |
|---|---|---|
| `SF_ACCOUNT` | `my17686.us-east-2.aws` | El identificador con el que entra a Snowflake por el navegador, sin `https://` ni `.snowflakecomputing.com`. |
| `SF_USER` | El usuario de servicio | Debe ser el **dueño de la llave pública** registrada con `ALTER USER … SET RSA_PUBLIC_KEY`. |
| `SF_DATABASE` | `APP_SEGMENTACION_EXPORTACIONES` | |
| `SF_SCHEMA` | `SEGMENTACION` | |
| `SF_WAREHOUSE` | `APPS_WH` | |
| `SF_ROLE` | `APP_SEGMENTACION_EXPORTACIONES` | Es el rol que necesita los dos permisos de Cortex (ver `ASISTENTE.md`). |
| `SF_PRIVATE_KEY_B64_1` | La llave privada en Base64 | Ver abajo cómo generarla. En una sola línea. |

**Cómo obtener `SF_PRIVATE_KEY_B64_1`.** En PowerShell, en la carpeta donde está
el archivo `.der`:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("rsa_key_1.der")) | Set-Clipboard
```

Pegue el resultado sin comillas. Si al pegar queda en varias líneas no importa:
el aplicativo tolera espacios y saltos desde la versión 3.3.0.

---

## 2 · Recomendadas — protegen el aplicativo

| Variable | Valor sugerido | Para qué |
|---|---|---|
| `APP_BASIC_USER` | `procolombia` | Pide usuario y contraseña al entrar. **Configúrelas**: las descargas incluyen correo, teléfono y dirección de empresas reales, y hoy el enlace es público. |
| `APP_BASIC_PASSWORD` | Una contraseña larga que usted elija | Las dos van juntas: si configura una sola, el aplicativo responde 503 a propósito. |
| `PUBLIC_ORIGIN` | `https://<su-dominio>.up.railway.app` | Sólo para las tarjetas al compartir el enlace. |

---

## 3 · Opcionales — sólo si necesita cambiar un comportamiento

| Variable | Valor por defecto | Cuándo tocarla |
|---|---|---|
| `APP_ENV` | `production` (lo pone el Dockerfile) | `development` habilita `/api/docs`. No lo use en producción. |
| `APP_DEMO_MODE` | ausente = `false` | `true` muestra 14 empresas de ejemplo sin tocar Snowflake. Útil para revisar la interfaz. **Con `true` el asistente se desactiva.** |
| `APP_DIAG_TOKEN` | vacío | Permite abrir el diagnóstico sin contraseña: `/estado?token=EL_VALOR`. Innecesaria si configuró `APP_BASIC_USER`/`APP_BASIC_PASSWORD`. |
| `EXPORT_MAX_ROWS` | `5000` | Máximo de empresas por archivo de Excel. |
| `EXPORT_INCLUDE_CONTACT_FIELDS` | `true` | `false` quita dirección, teléfono, correo y representante legal de las descargas. |
| `MAX_REQUEST_BYTES` | `2000000` | Tamaño máximo de una petición. |
| `LOG_LEVEL` | `INFO` | `DEBUG` para más detalle en los registros de Railway. |
| `SF_PRIVATE_KEY_PASSPHRASE_1` | vacío | Sólo si la llave privada está cifrada. |
| `SF_PRIVATE_KEY_B64_2` · `SF_PRIVATE_KEY_PASSPHRASE_2` | vacías | Llave de respaldo para rotar sin cortar el servicio. **No configure la 2 si su pública no está registrada en Snowflake**: el failover hacia ella sólo produce errores 401. |
| `SF_LOGIN_TIMEOUT` · `SF_NETWORK_TIMEOUT` | `30` · `60` | Segundos. Sólo si su red es especialmente lenta. |

---

## 4 · Opcionales del asistente — todas tienen el valor correcto por defecto

No hace falta configurarlas. Están documentadas por si algún día cambia el
modelo semántico o el modelo de redacción.

| Variable | Valor por defecto | Cuándo tocarla |
|---|---|---|
| `SF_SEMANTIC_VIEW` | `APP_SEGMENTACION_EXPORTACIONES.SEGMENTACION.TEJIDO_EMPRESARIAL_SEGMENTACION` | Si despliega el modelo semántico con otro nombre. |
| `SF_CORTEX_MODEL` | `claude-3-5-sonnet` | Sólo afecta a las 2-5 frases del resumen: la SQL la genera Cortex Analyst y las cifras las verifica el código. Para elegir uno más rápido y barato, mida con `snowflake/02_comparar_modelos.sql`. |
| `SF_ALLOWED_SCHEMAS` | `APP_SEGMENTACION_EXPORTACIONES.SEGMENTACION,APP_SEGMENTACION_EXPORTACIONES.PUBLIC` | Si el asistente debe poder leer otro esquema. |
| `SF_HOST` | derivado de `SF_ACCOUNT` | Sólo si su cuenta usa un dominio distinto de `<SF_ACCOUNT>.snowflakecomputing.com`. |
| `IA_MAX_ROWS` | `5000` | Tope de filas que trae una consulta del asistente. |
| `IA_MAX_ROWS_CLIENT` | `500` | Filas que viajan al navegador (el Excel trae todas). |
| `IA_ANALYST_TIMEOUT` | `90` | Segundos de espera a Cortex Analyst. |

---

## 5 · Lo que NO se configura en Railway

Los dos permisos del asistente van **en Snowflake**, no aquí:

```sql
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE APP_SEGMENTACION_EXPORTACIONES;

GRANT SELECT ON SEMANTIC VIEW
  APP_SEGMENTACION_EXPORTACIONES.SEGMENTACION.TEJIDO_EMPRESARIAL_SEGMENTACION
  TO ROLE APP_SEGMENTACION_EXPORTACIONES;
```

Están listos en `snowflake/01_permisos_asistente.sql`, con sus verificaciones.

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
APP_BASIC_USER=procolombia
APP_BASIC_PASSWORD=<una contraseña larga>
```

Railway inyecta `PORT` por su cuenta: **no la configure**.

---

## 7 · Cómo comprobar que quedó bien

1. Abra `https://<su-dominio>.up.railway.app/estado`. Debe decir **Datos reales**.
2. Vaya a **Consultar** y haga una búsqueda: los filtros deben traer
   departamentos y cadenas reales.
3. Vaya a **Asistente** y pulse la primera pregunta sugerida.
4. Descargue el Excel de esa respuesta.

Si algo falla, la página `/estado` dice en qué paso y qué corregir; el
procedimiento está en `DIAGNOSTICO_RAILWAY.md` y, para el asistente, en
`ASISTENTE.md`.
