# Asistente de análisis · qué es y cómo activarlo

El aplicativo tiene una sección nueva, **Asistente**, donde se pregunta en
español y se recibe la respuesta con su tabla, su gráfica y el archivo listo para
descargar.

Su dirección es:

**https://tejidoempresarialreact-production.up.railway.app/asistente**

---

## 1 · Qué se le puede preguntar

Todo lo que la base responde. Algunos ejemplos que ya vienen cargados en la
página:

| Tipo de análisis | Ejemplo |
|---|---|
| Conteos y cruces | ¿Cuántas empresas hay por departamento y tamaño? |
| Estructura productiva | Principales sectores económicos por cadena productiva en Antioquia |
| Rankings | ¿Cuáles son los 10 principales países destino por número de exportadoras? |
| Series y variaciones | ¿Cómo variaron las exportaciones enero-mayo 2026 frente a 2025 por cadena? |
| Prospección comercial | Pymes de Agroalimentos en Antioquia que exportan y no han sido atendidas por ProColombia |
| Listados | Empresas medianas de Sistema Moda en Bogotá que aún no exportan, con NIT y correo |
| Territorio | ¿Cuántas empresas hay en municipios PDET por subregión y cuántas exportan? |
| Una empresa | Ficha de la empresa con NIT 830068604 · ¿Qué exporta y hacia dónde FLORES DE APOSENTOS? |

Cada respuesta trae:

- el texto, en español;
- una **gráfica** cuando el resultado se presta (barras, barras apiladas, líneas
  o una cifra destacada);
- la **tabla** completa;
- la **consulta exacta** que se ejecutó, para poder verificarla;
- botones para descargar en **Excel** o en **presentación de PowerPoint**.

## 2 · Lo que hay que saber antes de usarlo

La respuesta la construye una inteligencia artificial y **puede contener
errores**. El aplicativo lo advierte en la página, junto a cada respuesta y
dentro de los dos archivos que se descargan. Antes de llevar una cifra a un
informe o a una decisión, contrástela con la tabla y con la consulta que aparece
al pulsar «Ver la consulta».

El aplicativo hace su parte para que eso sea posible:

- La consulta se revisa antes de ejecutarse: sólo se aceptan consultas de
  **lectura**, sobre los esquemas autorizados y con tope de filas.
- Después de redactar, se comprueba que **cada cifra del texto exista en la
  tabla**. Si aparece una que no está, el texto se reemplaza por un resumen
  hecho con los datos reales. La pastilla verde «Cifras verificadas contra la
  tabla» indica cuándo pasó esa comprobación.
- Nada sale de Snowflake: tanto la traducción de la pregunta como la redacción
  ocurren dentro de la cuenta de ProColombia.

## 3 · Cómo activarlo (una sola vez, 5 minutos)

**No hace falta ninguna credencial nueva en Railway.** El asistente usa la misma
llave y el mismo usuario que ya consulta la base. Sólo hay que darle dos permisos
en Snowflake.

En Snowsight, con un rol administrador, abra el archivo
`snowflake/01_permisos_asistente.sql` de este mismo paquete y ejecútelo. En
resumen, hace esto:

```sql
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE APP_SEGMENTACION_EXPORTACIONES;

GRANT SELECT ON SEMANTIC VIEW
  APP_SEGMENTACION_EXPORTACIONES.SEGMENTACION.TEJIDO_EMPRESARIAL_SEGMENTACION
  TO ROLE APP_SEGMENTACION_EXPORTACIONES;
```

(Reemplace `APP_SEGMENTACION_EXPORTACIONES` por el valor que tenga en la variable
`SF_ROLE` de Railway, si es distinto.)

El mismo archivo trae cuatro consultas de verificación con el resultado que debe
ver en cada una.

## 4 · Cómo saber si quedó funcionando

1. Abra `https://tejidoempresarialreact-production.up.railway.app/asistente`.
2. Si aparece un aviso amarillo diciendo que falta configuración, léalo: dice
   exactamente qué falta.
3. Pulse la primera pregunta sugerida, **«¿Cuántas empresas hay por departamento
   y tamaño?»**.
4. En unos segundos debe ver el texto, una gráfica de barras apiladas por
   departamento y la tabla.
5. Pulse **«Descargar Excel»** y ábralo: la primera hoja trae la pregunta, la
   respuesta, la consulta y la advertencia; la segunda, los datos.

## 5 · Si algo no funciona

| Lo que ve | Qué significa | Qué hacer |
|---|---|---|
| «El asistente necesita datos reales» | El aplicativo está en modo demostración. | Quite `APP_DEMO_MODE` en Railway. |
| «Falta configuración de Snowflake» | Faltan variables `SF_*`. | Complete lo que diga el mensaje; es el mismo procedimiento de `DIAGNOSTICO_RAILWAY.md`. |
| «El rol no tiene permiso para usar Cortex (403)» | Falta el primer `GRANT` del paso 3. | Ejecute `snowflake/01_permisos_asistente.sql`. |
| «No se encontró la vista semántica (404)» | La vista no está desplegada en la cuenta. | Despliéguela con el YAML de `snowflake/`; el procedimiento está en `snowflake/LEEME.md`. |
| «Snowflake rechazó las credenciales (401)» | El usuario del token no es el dueño de la llave pública. | Revise `SF_USER`; es el mismo diagnóstico de la página `/estado`. |
| «La consulta generada no pasó la revisión de seguridad» | El modelo propuso algo que no es una consulta de lectura. | Reformule la pregunta. El aplicativo hizo lo correcto al no ejecutarla. |
| La respuesta no dice «Cifras verificadas» | La redacción citó una cifra que no estaba en la tabla y se reemplazó por el resumen de los datos. | No es un fallo: es la protección funcionando. La tabla sigue siendo correcta. |

## 6 · Privacidad

La base incluye correo, teléfono, dirección y representante legal. El asistente
puede devolverlos en un listado, igual que la sección de consulta. Mientras el
aplicativo esté abierto a cualquiera con el enlace, esos datos también lo están:
configure `APP_BASIC_USER` y `APP_BASIC_PASSWORD` en Railway.

## 7 · Costos

Cada pregunta consume dos llamadas a Cortex (traducir y redactar) y una consulta
al warehouse. El consumo se revisa en Snowflake con
`SNOWFLAKE.ACCOUNT_USAGE.CORTEX_ANALYST_USAGE_HISTORY` y en el historial de
consultas del warehouse. Conviene mirarlo la primera semana para dimensionar el
uso real.

---

## 8 · Elegir el modelo de redacción y entender los tiempos

### Qué hace realmente el modelo

Casi nada de lo que usted ve. El reparto del trabajo es:

| Etapa | Quién la hace | ¿Se configura? |
|---|---|---|
| Traducir la pregunta a SQL | **Cortex Analyst**, con sus propios modelos | No |
| Revisar y ejecutar la consulta | Este aplicativo | No |
| Verificar que cada cifra exista en la tabla | Este aplicativo | No |
| Escribir las 2 a 5 frases del resumen | El modelo de `SF_CORTEX_MODEL` | **Sí** |

Es decir: **cambiar el modelo no cambia la exactitud de las cifras.** Esa la
garantiza el código, no el modelo. Lo que sí cambia es cuánto tarda en escribir
el resumen y cuánto cuesta.

Por eso, para esta tarea —corta, acotada y verificada— un modelo intermedio
suele ser mejor negocio que uno grande: responde antes y gasta menos, sin
pérdida apreciable de calidad.

### Cómo elegirlo con datos

No adopte una recomendación de memoria: la disponibilidad de modelos cambia por
región y con el tiempo. Ejecute
[`snowflake/02_comparar_modelos.sql`](snowflake/02_comparar_modelos.sql): mide en
su propia cuenta el tiempo de cada candidato con el prompt real del aplicativo y
consulta los créditos que efectivamente consumió.

Cuando decida, en Railway: `SF_CORTEX_MODEL = <el modelo elegido>`.

### De dónde salen los segundos

Debajo de cada respuesta, el asistente muestra el desglose:

```
Interpretar la pregunta 6,2 s · consultar la base 4,1 s · redactar 21,7 s (claude-3-5-sonnet)
```

Con eso se sabe siempre dónde se fue el tiempo. Las causas habituales, en orden
de frecuencia:

| Si lo grande es… | Suele ser porque… | Qué hacer |
|---|---|---|
| **Redactar** | El modelo es grande, o la tabla que se le envía es ancha. | Cambie `SF_CORTEX_MODEL` por uno más rápido. El aplicativo ya recorta la tabla del prompt a 6.000 caracteres. |
| **Consultar la base** | El warehouse estaba suspendido y tuvo que encenderse (5 a 10 s), o es la primera consulta tras un redespliegue y hubo que abrir la sesión con Snowflake (3 a 5 s). | Nada en el aplicativo. Si molesta, suba `AUTO_SUSPEND` del warehouse; cuesta créditos de inactividad. |
| **Interpretar la pregunta** | Cortex Analyst tarda más con preguntas ambiguas o con historial largo. | Preguntas más concretas. El historial ya está limitado a los últimos turnos. |
| **Todo a la vez, sólo la primera vez** | Arranque en frío: sesión nueva + warehouse dormido + primera llamada a Cortex. | La segunda pregunta es notablemente más rápida. Es normal. |

Una consulta de 50 segundos casi siempre es la **primera** del día o la primera
después de un redespliegue, con el warehouse dormido y un modelo grande
redactando. Repita la misma pregunta y compare el desglose: la diferencia le dirá
cuánto era arranque en frío y cuánto es el costo estable.
