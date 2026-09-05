# Asistente de análisis · qué es, cómo se usa y cómo se activa

El aplicativo tiene una sección, **Asistente**, donde se pregunta en español y
se recibe la respuesta escrita, la tabla, la consulta que la respalda y los
archivos para descargar. Desde la versión 3.5.0 el asistente **recuerda** las
últimas preguntas del hilo, muestra los **listados de empresas con el formato
estándar** de la sección de consulta y registra cada pregunta en una **tabla de
métricas** en Snowflake.

Su dirección es:

**https://tejidoempresarialasistente-production.up.railway.app/asistente**

---

## 1 · Qué se le puede preguntar

Todo lo que la base responde. Las doce preguntas que vienen cargadas en la
página tienen una **consulta verificada** en el modelo semántico (una persona
escribió la SQL), así que responden en segundos y sin ambigüedad:

| Tipo de análisis | Ejemplo |
|---|---|
| Conteos y cruces | ¿Cuántas empresas hay por departamento y tamaño? |
| Estructura productiva | Principales actividades económicas (CIIU) por cadena productiva en Antioquia |
| Rankings | ¿Cuáles son los 10 principales países destino por número de exportadoras? |
| Series y variaciones | ¿Cómo variaron las exportaciones enero-mayo 2026 frente a enero-mayo 2025 por cadena? |
| Prospección comercial | Pymes de Agroalimentos en Antioquia que exportan pero no han sido atendidas por ProColombia |
| Listados | Empresas medianas de Sistema Moda en Bogotá que aún no exportan, con NIT y correo |
| Territorio | ¿Cuántas empresas hay en municipios PDET por subregión y cuántas exportan? |
| Una empresa | Ficha de la empresa con NIT 890903938 · ¿Qué exporta y hacia dónde la empresa FLORES DE APOSENTOS? |

Cada respuesta trae:

- el **texto**, en español, con una pastilla que dice de dónde salió (ver §2);
- la **tabla** (hasta 500 filas en pantalla; las descargas traen todas);
- la **consulta exacta** que se ejecutó, con botón «Copiar»;
- la **gráfica**, con el botón «Ver gráfica»; se abre sola si la pregunta la
  pide («gráfica de…», «en barras», «evolución…») o si el resultado es una sola
  cifra;
- los botones de descarga: **Excel** y **presentación de PowerPoint**; y, si el
  resultado es un listado de empresas, **«Descargar listado con formato
  estándar»**.

### Refinar hasta llegar a un listado

El asistente recuerda sus **últimas dos preguntas**. Puede ir acotando:

1. «¿Cuántas pymes de Agroalimentos hay en Antioquia?»
2. «¿Cuántas de esas exportan?»
3. «Lístame esas empresas con NIT»

La tercera respuesta llega como listado: la misma tabla de la sección de
consulta (orden por columna, selector de columnas, enlace a la ficha, tarjetas
en el celular) y el botón para descargar el Excel de siempre —Resumen ·
Vista_Principal · Datos_Completos · Diccionario— con la pregunta, la consulta y
la advertencia de IA en la hoja Resumen. Para cambiar de tema, pulse **«Empezar
un hilo nuevo»**.

## 2 · Lo que hay que saber antes de usarlo

La respuesta la construye una inteligencia artificial y **puede contener
errores**. El aplicativo lo advierte en la página, junto a cada respuesta y
dentro de todos los archivos que se descargan. Antes de llevar una cifra a un
informe o a una decisión, contrástela con la tabla y con la consulta.

El aplicativo hace su parte, y lo dice con una pastilla debajo del texto:

| Pastilla | Qué significa |
|---|---|
| **Cifras verificadas contra la tabla** (verde) | La IA redactó el texto y cada cifra que cita existe en la tabla. |
| **Resumen automático de los datos: la redacción con IA no estuvo disponible** (ámbar) | La función de redacción de Snowflake falló. La tabla y la consulta son exactas; el texto es un resumen construido por el aplicativo. «¿Por qué?» muestra la explicación; la causa técnica está en `/estado` (paso «cortex_complete») y en la tabla de métricas. |
| **Se descartaron cifras sin respaldo en la tabla** (ámbar) | La IA citó una cifra que no está en la tabla; se reemplazó por el resumen automático. La protección funcionó. |

Además:

- La consulta se revisa antes de ejecutarse: sólo una sentencia de **lectura**,
  sobre los esquemas autorizados y con tope de filas.
- Nada sale de Snowflake: la traducción de la pregunta y la redacción ocurren
  dentro de la cuenta de ProColombia. No hay proveedor externo ni clave nueva.
- Debajo de cada respuesta está el desglose de tiempos: interpretar · consultar
  · (corregir) · redactar. Sirve para saber dónde se fue el tiempo (§8).

## 3 · Cómo activarlo (una sola vez)

**No hace falta ninguna credencial nueva en Railway.** En Snowsight, con un rol
administrador, ejecute en este orden:

| Paso | Archivo | Qué hace |
|---|---|---|
| 1 | `snowflake/01_permisos_asistente.sql` | `SNOWFLAKE.CORTEX_USER` y `SELECT` sobre la vista semántica para el rol del aplicativo. Trae cuatro verificaciones. |
| 2 | `snowflake/03_telemetria_asistente.sql` | Crea las tablas de métricas del asistente y concede sólo `INSERT` y `SELECT`. Sin esto el asistente funciona igual, pero no queda registro. |
| 3 | `snowflake/04_minimo_privilegio.sql` | Retira `UPDATE`/`DELETE` que el rol tenía sobre `EVENTOS` y muestra cómo revisar la herencia de `APPS_MANAGER`. |
| 4 | Redesplegar `snowflake/TEJIDO_EMPRESARIAL_SEGMENTACION.sv.yaml` | El modelo semántico de 3.5.0 trae las consultas verificadas de las doce preguntas sugeridas. Procedimiento en `snowflake/LEEME.md`. |

## 4 · Cómo saber si quedó funcionando

1. Abra `https://tejidoempresarialasistente-production.up.railway.app/estado` y
   pulse **Ejecutar diagnóstico**. Los pasos `vista_semantica`,
   `tabla_asistente_log` y `cortex_complete` deben quedar en verde. Si
   `cortex_complete` falla, el texto del paso dice si es un permiso, un modelo
   no disponible o una firma distinta; §5 dice qué hacer.
2. Abra `/asistente` y pulse la primera pregunta sugerida, **«¿Cuántas empresas
   hay por departamento y tamaño?»**. En menos de 15 s debe ver la tabla; en
   unos segundos más, el texto con la pastilla verde.
3. Pulse «Ver gráfica»: barras apiladas por departamento y tamaño.
4. Escriba «Lístame las pymes de Agroalimentos en Antioquia que exportan, con
   NIT» y descargue el listado con formato estándar: cuatro hojas.
5. En Snowsight:
   `SELECT * FROM APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.ASISTENTE_CONSULTAS ORDER BY FECHA_HORA DESC LIMIT 5;`
   debe mostrar sus preguntas con estado y tiempos.

## 5 · Si algo no funciona

| Lo que ve | Qué significa | Qué hacer |
|---|---|---|
| «El asistente necesita datos reales» | El aplicativo está en modo demostración. | Quite `APP_DEMO_MODE` en Railway. |
| «Falta configuración de Snowflake» | Faltan variables `SF_*`. | Complete lo que diga el mensaje (`DIAGNOSTICO_RAILWAY.md`). |
| «El rol no tiene permiso para usar Cortex (403)» | Falta el primer `GRANT`. | Ejecute `snowflake/01_permisos_asistente.sql`. |
| «No se encontró la vista semántica (404)» | La vista no está desplegada. | Despliéguela con el YAML (`snowflake/LEEME.md`). |
| «Snowflake rechazó las credenciales (401)» | `SF_USER` no es el dueño de la llave pública. | Revise `SF_USER`; mismo diagnóstico que `/estado`. |
| Pastilla ámbar «la redacción con IA no estuvo disponible» en todas las respuestas | Cortex COMPLETE falla con ese modelo. | Abra `/estado` → paso `cortex_complete`. Si dice *Insufficient privileges*: paso 1 de §3. Si dice que el modelo no existe o no está en la región: cambie `SF_CORTEX_MODEL` (mida con `snowflake/02_comparar_modelos.sql`). |
| «La consulta generada no pasó la revisión de seguridad» | El modelo propuso algo que no es una consulta de lectura sobre los esquemas permitidos. | Reformule la pregunta. El aplicativo hizo lo correcto. |
| «El resultado ya no está disponible en el servidor» al descargar | Pasaron más de 30 minutos, o el servicio se redesplegó. | Vuelva a preguntar y descargue de nuevo. |
| Interpretar tarda más de 40 s | Pregunta libre y ambigua, o Analyst con carga. | Use una pregunta sugerida o sea más concreto. `docs/METRICAS.md` dice cómo detectar las preguntas repetidas que conviene volver verificadas. |

## 6 · Privacidad

La base incluye correo, teléfono, dirección y representante legal. El asistente
sólo los incluye cuando la pregunta los pide expresamente («con correo», «con
teléfono», «ficha»), y `EXPORT_INCLUDE_CONTACT_FIELDS=false` los retira de
todo: descargas, fichas y asistente. La tabla de métricas guarda la pregunta,
la consulta y el texto; **nunca** las filas del resultado. Mientras el
aplicativo esté abierto a cualquiera con el enlace, los datos también lo están:
el README explica cómo activar usuario y contraseña.

## 7 · Costos

Cada pregunta consume una llamada a Cortex Analyst (por mensaje), una llamada a
Cortex COMPLETE (por fichas) y una consulta al warehouse. Las sentencias para
ver el consumo real están en `snowflake/02_comparar_modelos.sql`, sección 3, y
las de uso en `docs/METRICAS.md`.

---

## 8 · El modelo de redacción y los tiempos

### Qué hace realmente el modelo

| Etapa | Quién la hace | ¿Se configura? |
|---|---|---|
| Traducir la pregunta a SQL | **Cortex Analyst**, con sus propios modelos | No |
| Revisar y ejecutar la consulta | Este aplicativo | No |
| Verificar que cada cifra exista en la tabla | Este aplicativo | No |
| Escribir las 2 a 5 frases del resumen (máximo 90 palabras) | El modelo de `SF_CORTEX_MODEL` | **Sí** |

**Cambiar el modelo no cambia la exactitud de las cifras**: esa la garantiza el
código. Cambia cuánto tarda el resumen y cuánto cuesta. Mida en su cuenta con
`snowflake/02_comparar_modelos.sql` antes de decidir.

### De dónde salen los segundos

```
Interpretar la pregunta 6,2 s · consultar la base 4,1 s · corregir la consulta 12,0 s (2 intentos) · redactar 8,7 s (claude-3-5-sonnet)
```

| Si lo grande es… | Suele ser porque… | Qué hacer |
|---|---|---|
| **Interpretar** | Pregunta libre, ambigua o larga. Las sugeridas tienen consulta verificada y bajan a segundos. | Preguntas concretas; convertir en verificadas las que se repiten (`docs/METRICAS.md`). El plazo es de 45 s. |
| **Corregir** | La primera SQL falló en Snowflake y se pidió una corrección (aparece sólo entonces). | Nada; es el mecanismo normal. Si se repite con una misma pregunta, revise el modelo semántico. |
| **Consultar** | Warehouse suspendido (5 a 10 s al encender). | Subir `AUTO_SUSPEND` cuesta créditos de inactividad; suele no valer la pena. |
| **Redactar** | Modelo grande o tabla ancha. | Modelo más rápido (`SF_CORTEX_MODEL`). La tabla del prompt ya está acotada a 20 filas y 6.000 caracteres; la salida a 320 fichas / 90 palabras. |
| **Redactar 2 s y pastilla ámbar** | La redacción falló y el aplicativo lo dijo en vez de reintentar. | Ver §5. |

Desde 3.5.0 la sesión con Snowflake se abre al arrancar el servicio, así que la
primera pregunta ya no paga la conexión.
