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

## 1.bis · Qué es «la redacción» y por qué la respuesta no la espera

La respuesta del asistente tiene cuatro partes, y **sólo una** la escribe un
modelo de lenguaje:

| Parte | Quién la hace | ¿Puede equivocarse? |
|---|---|---|
| La consulta SQL | Cortex Analyst, a partir del modelo semántico | Sí, y por eso el código la revisa antes de ejecutarla |
| La tabla y la gráfica | Snowflake y este aplicativo | No: son los datos |
| El resumen de dos o tres frases | El aplicativo, leyendo la propia tabla | No: cada cifra que dice está en el resultado |
| **La redacción**: el mismo resumen, escrito con mejor prosa | El modelo de `SF_CORTEX_MODEL`, dentro de Snowflake | Se le revisan las cifras: si cita una que no está en la tabla, se descarta |

Desde la versión 3.5.2 la respuesta **no espera** a la redacción: en cuanto
Snowflake devuelve la tabla, usted ve el resultado completo con su resumen. Si
la redacción llega —tarda entre dos y cuatro segundos con un modelo vigente—,
sustituye ese texto por uno mejor escrito. Si no llega, no falta nada: la
pastilla dice «Resumen construido con los datos de la tabla» y ahí se acaba el
asunto.

Dicho de otro modo: **si la redacción con IA no funciona, el asistente sigue
sirviendo para lo mismo**. Lo que se pierde es estilo, no información.

## 2 · Lo que hay que saber antes de usarlo

La respuesta la construye una inteligencia artificial y **puede contener
errores**. El aplicativo lo advierte en la página, junto a cada respuesta y
dentro de todos los archivos que se descargan. Antes de llevar una cifra a un
informe o a una decisión, contrástela con la tabla y con la consulta.

El aplicativo hace su parte, y lo dice con una pastilla debajo del texto:

| Pastilla | Qué significa |
|---|---|
| **Resumen escrito con IA · cifras verificadas** (verde) | El párrafo lo escribió el modelo y cada cifra que cita existe en la tabla. |
| **Resumen construido con los datos de la tabla** (gris) | El párrafo lo escribió el aplicativo leyendo el resultado, porque la IA no respondió, está en pausa, devolvió un texto vacío o ilegible, o porque usted no esperó. **La respuesta es igualmente exacta y completa.** El desplegable «¿Por qué este resumen lo escribió el aplicativo y no la IA?» lo explica y muestra la causa técnica. |
| **Se descartó una cifra que no estaba en la tabla** (rojo) | La IA citó una cifra que no aparece en el resultado; el aplicativo la descartó y puso en su lugar el resumen construido con los datos. Es el único de los tres casos en que algo salió mal, y la protección funcionó. |

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
   pulse **Ver diagnóstico detallado**. Deben quedar en verde todos los pasos, y
   en particular «Vista semántica del asistente», «Tablas de métricas del
   asistente» y «Modo del despliegue y quién puede ver el diagnóstico». Dos
   avisos que conviene entender: el paso de Cortex sale en verde diciendo «no se
   probó» —es lo normal, sólo se prueba con el botón de abajo—, y el de la vista
   semántica avisa en su detalle si la cuenta tiene desplegada una versión
   anterior del modelo.
2. Pulse después **Probar la redacción con IA**. Es un botón aparte porque es
   el único paso que gasta créditos de IA: prueba varios modelos y dice cuál
   responde en su cuenta. Copie ese nombre a `SF_CORTEX_MODEL` en Railway. Si
   **ninguno** responde, el paso `cortex_region` explica por qué: la región de
   la cuenta no aloja modelos de generación y hay que habilitar la inferencia
   entre regiones (§5).
3. Abra `/asistente` y pulse la primera pregunta sugerida, **«¿Cuántas empresas
   hay por departamento y tamaño?»**. En menos de 15 s debe ver la tabla; en
   unos segundos más, el texto con la pastilla verde.
4. Pulse «Ver gráfica»: barras apiladas por departamento y tamaño.
5. Escriba «Lístame las pymes de Agroalimentos en Antioquia que exportan, con
   NIT» y descargue el listado con formato estándar: cuatro hojas.
6. En Snowsight:
   `SELECT * FROM APP_SEGMENTACION_EXPORTACIONES.SEGUIMIENTO.ASISTENTE_CONSULTAS ORDER BY FECHA_HORA DESC LIMIT 5;`
   debe mostrar sus preguntas con estado y tiempos.

## 5 · Si algo no funciona

| Lo que ve | Qué significa | Qué hacer |
|---|---|---|
| «Resumen construido con los datos de la tabla» en todas las respuestas, y en «¿Por qué?» dice `unknown model "…"` | **La causa más frecuente, y la que se dio en este servicio.** El nombre en `SF_CORTEX_MODEL` ya no existe en Snowflake: los modelos se retiran. | Ponga `SF_CORTEX_MODEL=claude-haiku-4-5` en Railway → Variables y redespliegue. Para saber cuál responde hoy en su cuenta: `/estado` → «Probar la redacción con IA». |
| «El asistente necesita datos reales» | El aplicativo está en modo demostración. | Quite `APP_DEMO_MODE` en Railway. |
| «Falta configuración de Snowflake» | Faltan variables `SF_*`. | Complete lo que diga el mensaje (`DIAGNOSTICO_RAILWAY.md`). |
| «El rol no tiene permiso para usar Cortex (403)» | Falta el primer `GRANT`. | Ejecute `snowflake/01_permisos_asistente.sql`. |
| «No se encontró la vista semántica (404)» | La vista no está desplegada. | Despliéguela con el YAML (`snowflake/LEEME.md`). |
| «Snowflake rechazó las credenciales (401)» | `SF_USER` no es el dueño de la llave pública. | Revise `SF_USER`; mismo diagnóstico que `/estado`. |
| Pastilla ámbar «la redacción con IA no estuvo disponible» en todas las respuestas | Cortex COMPLETE falla. **La causa más frecuente es que el nombre del modelo caducó**: los de Snowflake se retiran, y con un nombre inexistente falla cada pregunta. | La respuesta ya trae la causa: despliegue **«¿Por qué?»** debajo del texto. Y en `/estado` → **«Probar la redacción con IA»**: dice qué modelos responden. Copie uno a `SF_CORTEX_MODEL`. Si dice *Insufficient privileges*, ejecute el paso 1 de §3. |
| «Probar la redacción con IA» dice que **ningún** modelo responde | La región de la cuenta no aloja modelos de generación de texto. | Con `ACCOUNTADMIN` en Snowsight: `ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';` (o `'AWS_US'` si los datos deben quedarse en Estados Unidos). El paso `cortex_region` del diagnóstico muestra la región y el valor actual. |
| «La redacción con IA está en pausa tras varios fallos» | El aplicativo falló tres veces seguidas al redactar y dejó de intentarlo por diez minutos, para no hacerle esperar veinte segundos por un error ya conocido. | Corrija la causa (las dos filas anteriores) y espere diez minutos, o redespliegue el servicio. Las respuestas mientras tanto son correctas: cambia el texto, no las cifras. Se ajusta con `IA_REDACCION_FALLOS_PARA_PAUSA` e `IA_REDACCION_PAUSA`. |
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

**El servicio encendido en Railway no consume créditos de Snowflake.** Los
consumen las consultas, y quien las dispara son las personas que abren el
aplicativo. Lo que más pesa en la factura es el `AUTO_SUSPEND` del warehouse,
que se configura en Snowflake y no aquí. `docs/COSTOS.md` lo explica con los
guiones listos para pegar en Snowsight, incluido el tope de gasto.

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
código. Cambia cuánto tarda el resumen, cuánto cuesta y, sobre todo, si hay
resumen: **los nombres de modelo de Cortex caducan**. El valor por defecto es
`claude-haiku-4-5`; para saber qué responde hoy en su cuenta, use `/estado` →
«Probar la redacción con IA», y para comparar velocidad y estilo,
`snowflake/02_comparar_modelos.sql`.

### De dónde salen los segundos

```
Interpretar la pregunta 6,2 s · consultar la base 4,1 s · corregir la consulta 12,0 s (2 intentos) · redactar 3,4 s (claude-haiku-4-5)
```

| Si lo grande es… | Suele ser porque… | Qué hacer |
|---|---|---|
| **Interpretar** | Pregunta libre, ambigua o larga. Las sugeridas tienen consulta verificada y bajan a segundos. | Preguntas concretas; convertir en verificadas las que se repiten (`docs/METRICAS.md`). El plazo es de 45 s. |
| **Corregir** | La primera SQL falló en Snowflake y se pidió una corrección (aparece sólo entonces). | Nada; es el mecanismo normal. Si se repite con una misma pregunta, revise el modelo semántico. |
| **Consultar** | Warehouse suspendido (5 a 10 s al encender). | Subir `AUTO_SUSPEND` cuesta créditos de inactividad; suele no valer la pena. |
| **Redactar** | Modelo grande o tabla ancha. | Modelo más rápido (`SF_CORTEX_MODEL`). La tabla del prompt ya está acotada a 20 filas y 6.000 caracteres; la salida a 320 fichas / 90 palabras. |
| **Redactar ~20 s y pastilla ámbar en todas las respuestas** | El nombre del modelo caducó, o la región no tiene modelos de generación. La llamada agota su plazo y el aplicativo entrega el resumen automático. | Ver §5. Tras tres fallos seguidos el aplicativo deja de esperar durante diez minutos, así que las respuestas vuelven a ser rápidas aunque el texto siga siendo el automático. |
| **Redactar 0 s y pastilla ámbar** | La redacción está en pausa por los fallos anteriores. | Ver §5. |

Desde 3.5.0 la sesión con Snowflake se abre al arrancar el servicio, así que la
primera pregunta ya no paga la conexión.
