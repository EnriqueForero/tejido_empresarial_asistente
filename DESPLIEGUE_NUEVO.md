# Repositorio y despliegue nuevos, aislados del anterior

Para dejar intacto lo que ya funciona (`tejido_empresarial`, versión 3.3.1) y
trabajar el asistente en un sitio aparte. Al terminar tendrá dos cosas
independientes: el aplicativo anterior sigue en línea sin tocarse, y el nuevo
corre en su propia dirección.

Los nombres que usa el notebook ya configurado:

| Qué | Nombre |
|---|---|
| Carpeta en Google Drive | `ProColombia/tejido_empresarial_asistente` |
| Repositorio en GitHub | `EnriqueForero/tejido_empresarial_asistente` |
| Servicio en Railway | uno nuevo, con su propio dominio |

---

## Paso 1 · La carpeta en Drive (2 minutos)

1. Entre a Google Drive y abra `MyDrive/ProColombia`.
2. Cree una carpeta llamada exactamente **`tejido_empresarial_asistente`**.
3. Descomprima el paquete `.zip` de esta entrega en su computador.
4. Suba **el contenido** de la carpeta `tejido-empresarial-react` a esa carpeta
   de Drive (no la carpeta contenedora: dentro de
   `tejido_empresarial_asistente` deben quedar `backend/`, `frontend/`,
   `Dockerfile`, etc.).

**Verificación:** en Drive, `ProColombia/tejido_empresarial_asistente/backend/config.py`
existe, y al abrirlo dice `APP_VERSION = "3.4.0"`.

> Deje la carpeta anterior (`tejido_empresarial_react`) como está. Ese es el
> respaldo de lo que ya funciona.

---

## Paso 2 · El repositorio en GitHub (2 minutos)

1. Entre a [github.com/new](https://github.com/new).
2. **Repository name:** `tejido_empresarial_asistente`
3. **Visibility:** Private.
4. **No marque** «Add a README file», «Add .gitignore» ni «Choose a license».
   El repositorio debe quedar **vacío**: el notebook sube el primer commit.
5. Cree el repositorio.

**Verificación:** GitHub muestra la pantalla de «Quick setup» con la frase
*"…is empty. Set up in Desktop or create a new file"*.

---

## Paso 3 · Publicar desde Colab (10 minutos)

1. Abra `notebooks/Publicacion_GitHub_TejidoEmpresarial.ipynb` en Google Colab.
2. Confirme en el panel de secretos (🔑) que existe `GITHUB_TOKEN` con permiso
   de escritura sobre repositorios privados.
3. Ejecute las celdas **en orden**. La Celda A ya trae la configuración correcta:

   ```
   RUTA_CARPETA       = /content/drive/MyDrive/ProColombia/tejido_empresarial_asistente
   NOMBRE_REPO_GITHUB = tejido_empresarial_asistente
   VERSION            = 3.4.0
   ```

4. El build de validación instala `requirements-test.txt`, corre las 72 pruebas
   y compila el frontend. Debe terminar sin fallos.

**Verificación:** la celda final imprime el SHA del commit y el tag `v3.4.0`, y
el repositorio en GitHub muestra 158 archivos.

---

## Paso 4 · El servicio en Railway (5 minutos)

1. Entre a [railway.app](https://railway.app) → **New Project** → **Deploy from
   GitHub repo**.
2. Elija `tejido_empresarial_asistente`. Railway detecta `railway.toml` y usa el
   `Dockerfile`; no hay que configurar nada de compilación.
3. Abra la pestaña **Variables** y pegue las de
   [`RAILWAY_VARIABLES.md`](RAILWAY_VARIABLES.md) (sección 6 trae la plantilla
   lista para copiar).
4. **Settings → Networking → Generate Domain.**

**Verificación:** la pestaña Deployments muestra el despliegue en verde y el
dominio responde.

---

## Paso 5 · Los dos permisos de Snowflake (5 minutos, una sola vez)

El asistente necesita usar Cortex y leer el modelo semántico. En Snowsight, con
un rol administrador, ejecute
[`snowflake/01_permisos_asistente.sql`](snowflake/01_permisos_asistente.sql).

**Verificación:** las cuatro consultas del final de ese archivo devuelven lo que
el propio archivo indica.

---

## Paso 6 · Comprobar que todo quedó bien (5 minutos)

En el dominio nuevo:

1. `/estado` dice **Datos reales**.
2. **Consultar** → los filtros traen departamentos y cadenas reales; una
   búsqueda devuelve resultados; el Excel se descarga.
3. **Asistente** → la primera pregunta sugerida responde con texto, gráfica y
   tabla; el Excel y la presentación se descargan.
4. Abra el mismo enlace en el celular.

Si algo falla: `DIAGNOSTICO_RAILWAY.md` para la conexión, `ASISTENTE.md` para el
asistente. Los dos dicen qué significa cada mensaje y qué corregir.

---

## Qué hacer con el aplicativo anterior

Mientras verifica el nuevo, no toque nada del anterior. Cuando el nuevo lleve
unos días funcionando bien, decida:

- **Dejar los dos**, si quiere conservar el anterior como respaldo en caliente.
  Cuesta lo que consuma su servicio en Railway.
- **Apagar el anterior** en Railway (Settings → Danger → Remove service). El
  repositorio `tejido_empresarial` queda como respaldo del código; puede
  volver a desplegarlo cuando quiera.

No borre el repositorio viejo: es la copia de la versión 3.3.1, que es la última
que usted verificó funcionando en producción.
