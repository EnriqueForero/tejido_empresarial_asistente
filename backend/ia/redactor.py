"""
Redacción de la respuesta en español, dentro de Snowflake.

La prosa se genera con ``SNOWFLAKE.CORTEX.COMPLETE``, es decir en la misma
cuenta donde viven los datos: ninguna fila sale hacia un servicio externo y no
hace falta ninguna clave adicional. Si el modelo no responde —o si responde una
cifra que no está en la tabla, según `guardas.verificar_cifras`— se entrega un
resumen determinista construido a partir de los datos reales.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from backend.config import CORTEX_MODEL
from backend.database import redactar as redactar_secreto

logger = logging.getLogger("tejido.ia")

#: Filas de la tabla que viajan al modelo. Para resumir no hacen falta más: el
#: detalle lo tiene el usuario en la tabla y en el Excel.
_MAX_FILAS_PROMPT = 20
#: Tope de fichas de salida. La redacción son 2 a 5 frases: unas 300 fichas
#: sobran. Sin tope, un modelo puede extenderse y triplicar el tiempo.
_MAX_FICHAS_SALIDA = 320
_MAX_ANCHO_CELDA = 80
#: Tope de caracteres de la tabla que viaja al modelo. El tiempo de redacción
#: crece con el tamaño del texto de entrada: un listado de 30 empresas con 20
#: columnas ocupa unos 35.000 caracteres y no se resume mejor por ser más largo.
_MAX_CARACTERES_TABLA = 6000


@dataclass
class Redaccion:
    """Texto entregado al usuario y de dónde salió."""

    texto: str
    modelo: str
    degradado: bool = False


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
        "redondeando a lo sumo a dos decimales.\n"
        "2. Las cifras de exportación están en dólares FOB (USD); activos, ingresos y utilidad, en "
        "pesos colombianos (COP). Di siempre la unidad y el periodo.\n"
        "3. Si la tabla está vacía o no responde la pregunta, dilo con claridad y no especules.\n"
        "4. No menciones SQL, columnas técnicas ni detalles internos del sistema.\n"
        "5. No repitas la tabla completa: destaca lo relevante (totales, primeros lugares, "
        "contrastes) y deja el detalle para la tabla que el usuario ya ve.\n\n"
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
    sesion_sql: Any,
    pregunta: str,
    columnas: list[str],
    filas: list[list[Any]],
    n_filas: int,
    truncado: bool,
    modelo: str = CORTEX_MODEL,
) -> Redaccion:
    """Redacta con Cortex COMPLETE; ante cualquier fallo entrega el resumen determinista.

    Args:
        sesion_sql: Callable que ejecuta una consulta y devuelve filas
            (la sesión de Snowpark del aplicativo).
    """
    if n_filas == 0:
        return Redaccion(texto=resumen_determinista(columnas, filas, n_filas, truncado), modelo="", degradado=False)
    prompt = construir_prompt(pregunta, columnas, filas, n_filas)
    try:
        texto = _completar(sesion_sql, modelo, prompt)
        if texto:
            return Redaccion(texto=texto, modelo=modelo, degradado=False)
        raise RuntimeError("Cortex COMPLETE devolvió una respuesta vacía.")
    except Exception as exc:  # noqa: BLE001 - la redacción nunca puede tumbar la consulta
        logger.warning("La redacción con Cortex falló (%s); se entrega el resumen de los datos.", redactar_secreto(exc))
        return Redaccion(texto=resumen_determinista(columnas, filas, n_filas, truncado), modelo="", degradado=True)


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


def _completar(sesion_sql: Any, modelo: str, prompt: str) -> str:
    """Pide la redacción a SNOWFLAKE.CORTEX.COMPLETE acotando la salida.

    Se usa la forma con opciones porque permite fijar ``max_tokens`` y
    ``temperature``. El tiempo de generación es aproximadamente proporcional al
    número de fichas de salida, así que acotarlo es la palanca principal contra
    una redacción lenta; con temperatura 0 la respuesta además es reproducible.

    Si la cuenta no admite esa forma, se cae a la forma simple: el aplicativo no
    puede quedarse sin redactar por una diferencia de versión del servicio.
    """
    mensajes = json.dumps([{"role": "user", "content": prompt}])
    opciones = json.dumps({"temperature": 0, "max_tokens": _MAX_FICHAS_SALIDA})
    try:
        filas = sesion_sql(
            "SELECT SNOWFLAKE.CORTEX.COMPLETE(?, PARSE_JSON(?), PARSE_JSON(?)) AS RESPUESTA",
            [modelo, mensajes, opciones],
        )
        texto = _texto_de_respuesta(_primer_valor(filas))
        if texto:
            return texto
        raise RuntimeError("respuesta vacía con opciones")
    except Exception as exc:  # noqa: BLE001 - se intenta la forma simple
        logger.info("COMPLETE con opciones no disponible (%s); se usa la forma simple.", redactar_secreto(exc))
        filas = sesion_sql("SELECT SNOWFLAKE.CORTEX.COMPLETE(?, ?) AS RESPUESTA", [modelo, prompt])
        return _texto_de_respuesta(_primer_valor(filas))
