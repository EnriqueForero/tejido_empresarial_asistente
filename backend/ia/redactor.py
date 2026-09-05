"""
Redacción de la respuesta en español, dentro de Snowflake.

La prosa se genera con ``SNOWFLAKE.CORTEX.COMPLETE``, es decir en la misma
cuenta donde viven los datos: ninguna fila sale hacia un servicio externo y no
hace falta ninguna clave adicional. Si el modelo no responde —o si responde una
cifra que no está en la tabla, según `guardas.verificar_cifras`— se entrega un
resumen determinista construido a partir de los datos reales, y se dice por qué.

Regla de costo: **un fallo cuesta una llamada**. La forma con opciones (que fija
``max_tokens`` y ``temperature``) sólo se sustituye por la forma simple cuando
el error es de firma de la función —la cuenta no la admite—, que es un error de
compilación y por tanto inmediato. Un fallo de permisos, de modelo o de tiempo
fallaría igual en las dos formas: repetirlo sólo duplicaría la espera.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from backend.config import CORTEX_MODEL
from backend.database import redactar as redactar_secreto

logger = logging.getLogger("tejido.ia")

#: Filas de la tabla que viajan al modelo. Para resumir no hacen falta más: el
#: detalle lo tiene el usuario en la tabla y en el Excel.
_MAX_FILAS_PROMPT = 20
#: Tope de fichas de salida. La redacción son 2 a 5 frases: unas 300 fichas
#: sobran. Sin tope, un modelo puede extenderse y triplicar el tiempo.
_MAX_FICHAS_SALIDA = 320
#: Tope en palabras, escrito en el prompt: sobrevive a cualquier forma de la
#: función, incluida la simple, que no acepta ``max_tokens``.
_MAX_PALABRAS = 90
_MAX_ANCHO_CELDA = 80
#: Tope de caracteres de la tabla que viaja al modelo. El tiempo de redacción
#: crece con el tamaño del texto de entrada: un listado de 30 empresas con 20
#: columnas ocupa unos 35.000 caracteres y no se resume mejor por ser más largo.
_MAX_CARACTERES_TABLA = 6000

#: Forma con opciones: ARRAY de mensajes y OBJECT de opciones. Los parámetros
#: llegan como texto enlazado (``?``); PARSE_JSON los vuelve VARIANT y los
#: casts explícitos entregan los tipos que la firma de COMPLETE exige.
SQL_COMPLETE_OPCIONES = (
    "SELECT SNOWFLAKE.CORTEX.COMPLETE(?, TO_ARRAY(PARSE_JSON(?)), TO_OBJECT(PARSE_JSON(?))) AS RESPUESTA"
)
SQL_COMPLETE_SIMPLE = "SELECT SNOWFLAKE.CORTEX.COMPLETE(?, ?) AS RESPUESTA"

#: Señales de que la sentencia con opciones no compila en esta cuenta. Sólo en
#: ese caso vale la pena probar la forma simple (y el error fue inmediato).
_SENALES_FIRMA = (
    "argument type",
    "invalid argument",
    "unknown function",
    "number of arguments",
    "not enough arguments",
    "too many arguments",
    "syntax error",
    "sql compilation error",
)

SesionSql = Callable[[str, list[Any]], list[Any]]


def es_error_de_firma(exc: BaseException) -> bool:
    """¿El error dice que la forma con opciones no existe (y no que el modelo falló)?"""
    texto = str(exc).lower()
    return any(senal in texto for senal in _SENALES_FIRMA)


@dataclass
class Redaccion:
    """Texto entregado al usuario y de dónde salió."""

    texto: str
    modelo: str
    degradado: bool = False
    #: Por qué se degradó: ``redaccion_fallo`` · ``respuesta_vacia`` ·
    #: ``cifras_sin_respaldo`` (este último lo pone el orquestador). Vacío si no.
    motivo: str = ""
    #: Causa técnica, ya sin secretos (para la telemetría y el registro).
    error: str = ""
    #: ``opciones`` o ``simple``: con qué firma de COMPLETE se redactó.
    forma: str = ""


def _celda(valor: Any) -> str:
    if valor is None:
        return ""
    texto = str(valor)
    return texto if len(texto) <= _MAX_ANCHO_CELDA else texto[: _MAX_ANCHO_CELDA - 1] + "…"


def tabla_markdown(columnas: list[str], filas: list[list[Any]], n_filas: int) -> str:
    """Las primeras filas del resultado, acotadas por número y por tamaño.

    Se recorta también por caracteres porque el tiempo de redacción depende del
    largo del texto de entrada, y una tabla ancha puede ser cincuenta veces más
    grande que una angosta con las mismas filas.
    """
    cabecera = " | ".join(columnas)
    separador = " | ".join("---" for _ in columnas)
    lineas: list[str] = []
    usados = len(cabecera) + len(separador)
    for fila in filas[:_MAX_FILAS_PROMPT]:
        linea = " | ".join(_celda(valor) for valor in fila)
        if lineas and usados + len(linea) > _MAX_CARACTERES_TABLA:
            break
        lineas.append(linea)
        usados += len(linea) + 1
    omitidas = n_filas - len(lineas)
    resto = f"\n(… {omitidas} filas más, no mostradas)" if omitidas > 0 else ""
    return f"{cabecera}\n{separador}\n" + "\n".join(lineas) + resto


def construir_prompt(pregunta: str, columnas: list[str], filas: list[list[Any]], n_filas: int) -> str:
    """Instrucción de redacción con el contrato anti-invención explícito."""
    return (
        "Eres el analista del aplicativo Tejido Empresarial de ProColombia. Responde en español, "
        "en 2 a 5 frases claras y profesionales, la pregunta del usuario usando EXCLUSIVAMENTE los "
        "datos de la tabla adjunta, que ya fue calculada en Snowflake.\n"
        "REGLAS OBLIGATORIAS:\n"
        "1. No inventes ni calcules cifras nuevas: cita únicamente valores que estén en la tabla, "
        "redondeando a lo sumo a dos decimales. No sumes filas, no promedies ni saques porcentajes.\n"
        "2. Las cifras de exportación están en dólares FOB (USD); activos, ingresos y utilidad, en "
        "pesos colombianos (COP). Di siempre la unidad y el periodo.\n"
        "3. Si la tabla está vacía o no responde la pregunta, dilo con claridad y no especules.\n"
        "4. No menciones SQL, columnas técnicas ni detalles internos del sistema.\n"
        "5. No repitas la tabla completa: destaca los primeros lugares y los contrastes que se leen "
        "en la tabla, y deja el detalle para la tabla que el usuario ya ve.\n"
        f"6. Máximo {_MAX_PALABRAS} palabras.\n\n"
        f"Pregunta: {pregunta}\n\n"
        f"Tabla de resultados ({n_filas} filas):\n{tabla_markdown(columnas, filas, n_filas)}\n\n"
        "Respuesta:"
    )


def resumen_determinista(columnas: list[str], filas: list[list[Any]], n_filas: int, truncado: bool) -> str:
    """Resumen sin modelo, para cuando la redacción falla o cita cifras sin respaldo."""
    if n_filas == 0:
        return (
            "La consulta se ejecutó correctamente, pero no encontró empresas con esa combinación "
            "de criterios. Pruebe con un filtro más amplio: otro departamento, otra cadena o "
            "incluyendo empresas no exportadoras."
        )
    primera = ", ".join(f"{columna}: {_celda(valor)}" for columna, valor in zip(columnas, filas[0]))
    texto = f"La consulta devolvió {n_filas} fila(s). Primer registro → {primera}."
    if truncado:
        texto += " El resultado se recortó al tope configurado; afine los criterios para ver el resto."
    return texto + " La tabla de abajo tiene el detalle completo."


def redactar(
    sesion_sql: SesionSql,
    pregunta: str,
    columnas: list[str],
    filas: list[list[Any]],
    n_filas: int,
    truncado: bool,
    modelo: str = CORTEX_MODEL,
    consulta_id: str = "",
) -> Redaccion:
    """Redacta con Cortex COMPLETE; ante cualquier fallo entrega el resumen determinista.

    Args:
        sesion_sql: Callable que ejecuta una consulta con parámetros enlazados y
            devuelve filas (la sesión de Snowpark del aplicativo).
        consulta_id: Sólo para que el registro permita correlacionar el fallo.
    """
    if n_filas == 0:
        return Redaccion(texto=resumen_determinista(columnas, filas, n_filas, truncado), modelo="", degradado=False)
    prompt = construir_prompt(pregunta, columnas, filas, n_filas)
    try:
        texto, forma = completar(sesion_sql, modelo, prompt)
    except Exception as exc:  # noqa: BLE001 - la redacción nunca puede tumbar la consulta
        causa = redactar_secreto(exc, 300)
        logger.warning("[%s] La redacción con Cortex falló (%s); se entrega el resumen de los datos.", consulta_id, causa)
        return Redaccion(
            texto=resumen_determinista(columnas, filas, n_filas, truncado),
            modelo="",
            degradado=True,
            motivo="redaccion_fallo",
            error=causa,
        )
    if not texto:
        logger.warning("[%s] Cortex COMPLETE devolvió una respuesta vacía; se entrega el resumen de los datos.", consulta_id)
        return Redaccion(
            texto=resumen_determinista(columnas, filas, n_filas, truncado),
            modelo="",
            degradado=True,
            motivo="respuesta_vacia",
            error="Cortex COMPLETE devolvió una respuesta vacía.",
            forma=forma,
        )
    return Redaccion(texto=texto, modelo=modelo, degradado=False, forma=forma)


def _primer_valor(filas: list[Any]) -> Any:
    if not filas:
        return None
    fila = filas[0]
    if isinstance(fila, dict):
        return next(iter(fila.values()), None)
    return fila[0]


def _texto_de_respuesta(valor: Any) -> str:
    """Extrae el texto tanto de la forma con opciones como de la forma simple.

    Con opciones, Cortex devuelve un objeto
    ``{"choices": [{"messages": "…"}], "usage": {…}}``; sin opciones, el texto
    plano. Se aceptan las dos para no depender de la variante disponible.
    """
    if valor is None:
        return ""
    texto = valor if isinstance(valor, str) else str(valor)
    recortado = texto.strip()
    if recortado.startswith("{"):
        try:
            cuerpo = json.loads(recortado)
        except ValueError:
            return recortado
        opciones = cuerpo.get("choices") or []
        if opciones:
            mensaje = opciones[0].get("messages") or opciones[0].get("message") or ""
            return str(mensaje).strip()
        return ""
    return recortado


def completar(sesion_sql: SesionSql, modelo: str, prompt: str) -> tuple[str, str]:
    """Pide la redacción a SNOWFLAKE.CORTEX.COMPLETE y dice con qué forma se obtuvo.

    Se usa primero la forma con opciones porque permite fijar ``max_tokens`` y
    ``temperature``: el tiempo de generación es proporcional a las fichas de
    salida, y con temperatura 0 la respuesta es reproducible. Sólo si esa firma
    no existe en la cuenta (error de compilación, inmediato) se prueba la forma
    simple, **una vez**. Cualquier otro error se propaga sin reintentar.

    Returns:
        ``(texto, forma)`` con ``forma`` en {``opciones``, ``simple``}. El texto
        puede llegar vacío: decidir qué hacer con eso es de quien llama.
    """
    mensajes = json.dumps([{"role": "user", "content": prompt}])
    opciones = json.dumps({"temperature": 0, "max_tokens": _MAX_FICHAS_SALIDA})
    try:
        filas = sesion_sql(SQL_COMPLETE_OPCIONES, [modelo, mensajes, opciones])
        return _texto_de_respuesta(_primer_valor(filas)), "opciones"
    except Exception as exc:
        if not es_error_de_firma(exc):
            raise
        logger.info("COMPLETE con opciones no compila en esta cuenta (%s); se usa la forma simple.", redactar_secreto(exc))
    filas = sesion_sql(SQL_COMPLETE_SIMPLE, [modelo, prompt])
    return _texto_de_respuesta(_primer_valor(filas)), "simple"


def sondear_complete(sesion_sql: SesionSql, modelo: str) -> dict[str, Any]:
    """Paso del diagnóstico: ¿qué forma de COMPLETE admite la cuenta con este modelo?

    Pide una respuesta de una palabra para que el paso cueste segundos, no
    créditos. Si fallan las dos formas, el error reúne ambas causas: es lo que
    hay que leer para saber si es un permiso, un modelo no disponible en la
    región o una firma distinta.
    """
    prompt = "Responde únicamente con la palabra OK."
    mensajes = json.dumps([{"role": "user", "content": prompt}])
    opciones = json.dumps({"temperature": 0, "max_tokens": 8})
    try:
        filas = sesion_sql(SQL_COMPLETE_OPCIONES, [modelo, mensajes, opciones])
        return {
            "modelo": modelo,
            "forma": "opciones (max_tokens y temperature activos)",
            "respuesta": _texto_de_respuesta(_primer_valor(filas))[:40],
        }
    except Exception as exc:  # noqa: BLE001 - se informa, no se oculta
        error_opciones = redactar_secreto(exc, 300)
    try:
        filas = sesion_sql(SQL_COMPLETE_SIMPLE, [modelo, prompt])
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Ninguna forma de COMPLETE respondió. Con opciones: {error_opciones} · "
            f"Forma simple: {redactar_secreto(exc, 300)}"
        ) from exc
    return {
        "modelo": modelo,
        "forma": "simple (sin tope de fichas; la forma con opciones falló)",
        "respuesta": _texto_de_respuesta(_primer_valor(filas))[:40],
        "error_con_opciones": error_opciones,
    }
