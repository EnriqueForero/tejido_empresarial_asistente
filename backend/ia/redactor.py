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
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from backend.config import (
    CORTEX_MODEL,
    IA_MAX_ROWS_CLIENT,
    IA_REDACCION_FALLOS_PARA_PAUSA,
    IA_REDACCION_PAUSA,
)
from backend.database import redactar as redactar_secreto

logger = logging.getLogger("tejido.ia")

#: Por qué el texto de una respuesta puede no haberlo escrito el modelo.
#: La lista es única a propósito: `tests/test_endurecimiento.py` exige que
#: cada motivo esté explicado en la interfaz, en el contrato y en la
#: documentación que el propietario usa para leer la telemetría. Añadir uno
#: sin explicarlo rompe la batería, con el nombre del archivo que falta.
MOTIVOS_DEGRADACION = (
    "redaccion_fallo",
    "redaccion_pausada",
    "respuesta_vacia",
    "respuesta_ilegible",
    "cifras_sin_respaldo",
)

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
#: Deliberadamente estrictas: «SQL compilation error» a secas también aparece en
#: fallos del servicio, y probar la forma simple ante uno de esos duplicaría la
#: espera sin ninguna posibilidad de éxito.
_SENALES_FIRMA = (
    "argument type",
    "invalid argument",
    "unknown function",
    "number of arguments",
    "not enough arguments",
    "too many arguments",
    "invalid number of arguments",
    "no matching function signature",
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


#: Cuántas filas se enumeran en el resumen de un cruce pequeño, y cuántas columnas
#: se citan de un registro. Más allá, el detalle lo tiene la tabla.
_MAX_FILAS_RESUMEN = 6
_MAX_COLUMNAS_RESUMEN = 6


def _numero_legible(valor: float) -> str:
    """1234.5678 → «1.234,57»; 231544.0 → «231.544» (formato de Colombia)."""
    entero = float(valor).is_integer()
    texto = f"{valor:,.0f}" if entero else f"{valor:,.2f}"
    return texto.replace(",", "·").replace(".", ",").replace("·", ".")


def _valor_legible(valor: Any, columna: str = "") -> str:
    """El número tal como debe leerse en una frase, con su unidad si la tiene."""
    from backend.ia.forma import clase_de_cifra

    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    if isinstance(valor, (int, float)):
        clase = clase_de_cifra(columna) if columna else "numero"
        if clase == "identificador":
            # Un NIT con separador de miles («899.999.068») deja de ser un NIT.
            return str(int(valor)) if float(valor).is_integer() else str(valor)
        legible = _numero_legible(float(valor))
        if clase == "porcentaje":
            return legible + " %"
        return {"usd": "USD ", "cop": "$ "}.get(clase, "") + legible
    return _celda(valor) or "Sin dato"


def _es_numero(valor: Any) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def _indices_numericos(columnas: list[str], filas: list[list[Any]]) -> list[int]:
    """Columnas cuyos valores no nulos son todos números (las medidas del resultado)."""
    numericas: list[int] = []
    for indice in range(len(columnas)):
        valores = [fila[indice] for fila in filas if indice < len(fila) and fila[indice] is not None]
        if valores and all(_es_numero(valor) for valor in valores):
            numericas.append(indice)
    return numericas


#: Columnas que nombran una fila, y columnas que sólo la identifican. Se comparan
#: sobre el nombre normalizado (sin tildes), porque «Razón social» y RAZON_SOCIAL
#: son la misma columna con dos escrituras.
_NOMBRA = ("RAZON_SOCIAL", "RAZON", "NOMBRE")
_IDENTIFICA = ("NIT", "CODIGO", "DIGITO", "ID")


def _columna_que_nombra(columnas: list[str], textuales: list[int], filas: list[list[Any]]) -> int | None:
    """Columna de texto que sirve para nombrar una fila: «ECOPETROL S A», no «899999068».

    Entre varias candidatas gana la que **distingue** las filas. En producción,
    una evolución de exportaciones de Antioquia por año decía «el valor más alto
    … en Antioquia»: cierto y perfectamente inútil, porque las siete filas eran
    de Antioquia y lo que las diferenciaba era el periodo.
    """
    from backend.ia.forma import normalizar

    if not textuales:
        return None
    normalizadas = {indice: normalizar(columnas[indice]) for indice in textuales}

    def distingue(indice: int) -> bool:
        return len({fila[indice] for fila in filas if indice < len(fila)}) > 1

    for candidatas in (
        [i for i in textuales if any(c in normalizadas[i] for c in _NOMBRA)],
        [i for i in textuales if not any(c in normalizadas[i].split("_") for c in _IDENTIFICA)],
    ):
        if not candidatas:
            continue
        return next((i for i in candidatas if distingue(i)), candidatas[0])
    return None


def _columna_que_mide(columnas: list[str], numericas: list[int]) -> int | None:
    """Columna numérica que mide algo: unas exportaciones, no un NIT ni un código."""
    from backend.ia.forma import clase_de_cifra

    return next((i for i in numericas if clase_de_cifra(columnas[i]) != "identificador"), None)


def resumen_determinista(columnas: list[str], filas: list[list[Any]], n_filas: int, truncado: bool) -> str:
    """Resumen sin modelo, para cuando la redacción falla o cita cifras sin respaldo.

    Lo escribe el código a partir de la tabla, así que no puede inventar nada: cada
    cifra que aparece está en el resultado. Se adapta a la forma del resultado —un
    cruce corto se enumera entero, un listado largo se resume por su primer
    registro y su valor mayor— porque es el texto que el usuario lee cada vez que
    la redacción con IA no está disponible.
    """
    if n_filas == 0:
        return (
            "La consulta se ejecutó correctamente, pero no encontró empresas con esa combinación "
            "de criterios. Pruebe con un filtro más amplio: otro departamento, otra cadena o "
            "incluyendo empresas no exportadoras."
        )
    plural = "filas" if n_filas != 1 else "fila"
    partes = [f"La consulta devolvió {_numero_legible(n_filas)} {plural}."]
    numericas = _indices_numericos(columnas, filas)
    textuales = [i for i in range(len(columnas)) if i not in numericas]

    if len(textuales) == 1 and len(numericas) == 1 and len(filas) <= _MAX_FILAS_RESUMEN:
        # Un cruce corto (una categoría y una medida) se puede leer entero.
        dimension, medida = textuales[0], numericas[0]
        detalle = "; ".join(
            f"{_valor_legible(fila[medida], columnas[medida])} ({_valor_legible(fila[dimension])})"
            for fila in filas
        )
        partes.append(f"{columnas[medida]}: {detalle}.")
    else:
        visibles = list(zip(columnas, filas[0]))[:_MAX_COLUMNAS_RESUMEN]
        primera = ", ".join(f"{columna}: {_valor_legible(valor, columna)}" for columna, valor in visibles)
        omitidas = len(columnas) - len(visibles)
        resto = f" y {omitidas} columnas más" if omitidas > 0 else ""
        partes.append(f"Primer registro → {primera}{resto}.")
        etiqueta = _columna_que_nombra(columnas, textuales, filas)
        medida = _columna_que_mide(columnas, numericas)
        # Con un resultado recortado, el mayor de las filas traídas no es el mayor:
        # es la misma razón por la que `verificar_cifras` no acepta del modelo una
        # suma sobre un resultado incompleto. Lo que no se puede afirmar, no se afirma.
        if medida is not None and etiqueta is not None and len(filas) > 1 and not truncado:
            mejor = max(filas, key=lambda fila: fila[medida] if _es_numero(fila[medida]) else float("-inf"))
            if _es_numero(mejor[medida]):
                donde = _valor_legible(mejor[etiqueta])
                partes.append(
                    f"El valor más alto de «{columnas[medida]}» es "
                    f"{_valor_legible(mejor[medida], columnas[medida])}, "
                    # «Bogotá, D.C.» ya termina en punto: dos seguidos se leen mal.
                    f"en {donde}" + ("" if donde.endswith(".") else ".")
                )

    if truncado:
        partes.append("El resultado se recortó al tope configurado; afine los criterios para ver el resto.")
    if n_filas > IA_MAX_ROWS_CLIENT:
        partes.append(
            f"La tabla muestra las primeras {_numero_legible(IA_MAX_ROWS_CLIENT)} filas; "
            "la descarga trae el detalle completo."
        )
    else:
        partes.append("La tabla de abajo tiene el detalle completo.")
    return " ".join(partes)


class Interruptor:
    """Corta las llamadas a COMPLETE cuando falla varias veces seguidas.

    Un fallo de la redacción cuesta el tiempo completo de la llamada —en el
    despliegue de ProColombia, unos 20 s— y su causa casi nunca es pasajera: un
    permiso que falta, un modelo retirado o una firma que la cuenta no admite
    fallan igual en la pregunta siguiente. Tras `fallos_para_pausa` fallos
    seguidos se deja de llamar durante `pausa` segundos: las respuestas pasan a
    salir en cuanto Snowflake devuelve la tabla, y la pantalla explica por qué.
    Un solo éxito lo reinicia.
    """

    def __init__(self, fallos_para_pausa: int, pausa: float, reloj: Callable[[], float] = time.monotonic) -> None:
        self._fallos_para_pausa = max(1, fallos_para_pausa)
        self._pausa = max(0.0, float(pausa))
        self._reloj = reloj
        self._lock = threading.Lock()
        self.fallos_seguidos = 0
        self.hasta = 0.0
        self.causa = ""

    def permite_llamar(self) -> bool:
        with self._lock:
            return self._reloj() >= self.hasta

    def anotar_exito(self) -> None:
        with self._lock:
            self.fallos_seguidos = 0
            self.hasta = 0.0
            self.causa = ""

    def anotar_fallo(self, causa: str) -> bool:
        """Registra el fallo y devuelve si a partir de ahora la redacción queda en pausa."""
        with self._lock:
            self.fallos_seguidos += 1
            self.causa = causa
            if self.fallos_seguidos >= self._fallos_para_pausa:
                self.hasta = self._reloj() + self._pausa
                return True
            return False

    @property
    def minutos_de_pausa(self) -> int:
        return max(1, round(self._pausa / 60))

    def reiniciar(self) -> None:
        """Vuelve al estado inicial (para las pruebas y para el diagnóstico)."""
        self.anotar_exito()


#: Interruptor del proceso. Se consulta en cada redacción.
INTERRUPTOR = Interruptor(IA_REDACCION_FALLOS_PARA_PAUSA, IA_REDACCION_PAUSA)


def redactar(
    sesion_sql: SesionSql,
    pregunta: str,
    columnas: list[str],
    filas: list[list[Any]],
    n_filas: int,
    truncado: bool,
    modelo: str = CORTEX_MODEL,
    consulta_id: str = "",
    interruptor: Interruptor | None = None,
) -> Redaccion:
    """Redacta con Cortex COMPLETE; ante cualquier fallo entrega el resumen determinista.

    Args:
        sesion_sql: Callable que ejecuta una consulta con parámetros enlazados y
            devuelve filas (la sesión de Snowpark del aplicativo).
        consulta_id: Sólo para que el registro permita correlacionar el fallo.
        interruptor: Corta las llamadas tras varios fallos seguidos.
    """
    if n_filas == 0:
        return Redaccion(texto=resumen_determinista(columnas, filas, n_filas, truncado), modelo="", degradado=False)
    corta = interruptor or INTERRUPTOR
    resumen = lambda motivo, error: Redaccion(  # noqa: E731 - las cuatro salidas degradadas comparten forma
        texto=resumen_determinista(columnas, filas, n_filas, truncado),
        modelo="",
        degradado=True,
        motivo=motivo,
        error=error,
    )
    if not corta.permite_llamar():
        return resumen(
            "redaccion_pausada",
            f"Tras {corta.fallos_seguidos} fallos seguidos, la redacción con IA está en pausa "
            f"{corta.minutos_de_pausa} minutos para no hacer esperar cada consulta. Última causa: {corta.causa}",
        )
    prompt = construir_prompt(pregunta, columnas, filas, n_filas)
    try:
        texto, forma = completar(sesion_sql, modelo, prompt)
    except RespuestaIlegible as exc:
        # El modelo sí respondió y se pagó su tiempo: no es un fallo de Snowflake
        # ni cuenta para el interruptor, es una forma de respuesta que no conocemos.
        causa = redactar_secreto(exc, 300)
        logger.warning("[%s] Cortex COMPLETE respondió algo que no se supo leer (%s).", consulta_id, causa)
        return resumen("respuesta_ilegible", causa)
    except Exception as exc:  # noqa: BLE001 - la redacción nunca puede tumbar la consulta
        causa = redactar_secreto(exc, 300)
        en_pausa = corta.anotar_fallo(causa)
        logger.warning(
            "[%s] La redacción con Cortex falló (%s); se entrega el resumen de los datos.%s",
            consulta_id,
            causa,
            f" Se pausa {corta.minutos_de_pausa} min tras {corta.fallos_seguidos} fallos seguidos." if en_pausa else "",
        )
        return resumen("redaccion_fallo", causa)
    corta.anotar_exito()
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


class RespuestaIlegible(ValueError):
    """Cortex respondió, pero con una forma que no se supo leer."""


def _texto_de_respuesta(valor: Any) -> str:
    """Extrae el texto tanto de la forma con opciones como de la forma simple.

    Con opciones, Cortex devuelve un objeto
    ``{"choices": [{"messages": "…"}], "usage": {…}}``; sin opciones, el texto
    plano. Se aceptan las dos, y también la variante en la que ``choices`` trae
    cadenas: si el servicio cambia la forma de la respuesta, el aplicativo no
    debe reportarlo como «Snowflake falló», que es una causa distinta y llevaría
    a buscar el problema donde no está.

    Raises:
        RespuestaIlegible: si la respuesta llegó con una forma desconocida.
    """
    if valor is None:
        return ""
    texto = valor if isinstance(valor, str) else str(valor)
    recortado = texto.strip()
    if not recortado.startswith("{"):
        return recortado
    try:
        cuerpo = json.loads(recortado)
    except ValueError:
        return recortado
    if not isinstance(cuerpo, dict):
        raise RespuestaIlegible(f"Se esperaba un objeto y llegó {type(cuerpo).__name__}.")
    opciones = cuerpo.get("choices") or []
    if not opciones:
        return ""
    primera = opciones[0]
    if isinstance(primera, str):
        return primera.strip()
    if isinstance(primera, dict):
        return str(primera.get("messages") or primera.get("message") or "").strip()
    raise RespuestaIlegible(f"«choices[0]» llegó como {type(primera).__name__}: {str(primera)[:120]}")


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


#: Modelos que el diagnóstico prueba cuando el configurado no responde. Los
#: nombres de Cortex caducan —claude-3-5-sonnet, el que traía el aplicativo, fue
#: retirado— y ninguna variable de Railway sirve si el nombre ya no existe. Así
#: el diagnóstico no dice sólo «falla»: dice cuál poner.
MODELOS_CANDIDATOS = (
    "claude-haiku-4-5",
    "claude-sonnet-4-6",
    "llama3.1-8b",
    "mistral-large2",
    "snowflake-llama-3.1-405b",
)


#: Segundos que puede durar el sondeo completo. Una llamada a un modelo que no
#: existe no falla rápido: en el despliegue de ProColombia agota unos 20 s. Sin
#: tope, probar el configurado más cinco candidatos dejaría al propietario
#: esperando minutos delante de una página que no dice nada.
_PRESUPUESTO_SONDEO = 75.0


def _probar_modelo(
    sesion_sql: SesionSql, modelo: str, probar_opciones: bool = True
) -> tuple[bool, str, bool]:
    """Una llamada mínima (8 fichas) para saber si ese modelo responde en la cuenta.

    Aquí rige la misma regla que en la redacción real: **un fallo cuesta una
    llamada**. La forma simple sólo se prueba cuando el error es de firma —un
    error de compilación, y por tanto inmediato—; con cualquier otro error
    repetir sólo duplicaría la espera, que es justo lo que hace inservible un
    diagnóstico.

    Returns:
        ``(responde, detalle, admite_opciones)``. El tercer valor evita volver a
        probar una firma que ya se sabe que la cuenta no admite.
    """
    prompt = "Responde únicamente con la palabra OK."
    primero = ""
    if probar_opciones:
        mensajes = json.dumps([{"role": "user", "content": prompt}])
        opciones = json.dumps({"temperature": 0, "max_tokens": 8})
        try:
            filas = sesion_sql(SQL_COMPLETE_OPCIONES, [modelo, mensajes, opciones])
            return True, _texto_de_respuesta(_primer_valor(filas))[:40], True
        except Exception as exc:  # noqa: BLE001 - el error es justamente lo que se busca
            primero = redactar_secreto(exc, 300)
            if not es_error_de_firma(exc):
                return False, primero, True
    try:
        filas = sesion_sql(SQL_COMPLETE_SIMPLE, [modelo, prompt])
        return True, _texto_de_respuesta(_primer_valor(filas))[:40], False
    except Exception as exc:  # noqa: BLE001
        simple = redactar_secreto(exc, 200)
        detalle = f"con opciones: {primero} · forma simple: {simple}" if primero else simple
        return False, detalle, False


def sondear_complete(
    sesion_sql: SesionSql,
    modelo: str,
    candidatos: tuple[str, ...] = MODELOS_CANDIDATOS,
    reloj: Callable[[], float] = time.monotonic,
    presupuesto: float = _PRESUPUESTO_SONDEO,
) -> dict[str, Any]:
    """Paso del diagnóstico: ¿puede esta cuenta redactar, y con qué modelo?

    Prueba el modelo configurado y, si no responde, los candidatos, con una
    respuesta de una palabra para que el paso cueste segundos y no créditos. La
    diferencia importa: «no funciona» manda a revisar permisos, mientras que
    «no funciona ése pero sí este otro» se arregla cambiando una variable.

    Raises:
        RuntimeError: si ningún modelo responde, con la causa y qué hacer.
    """
    inicio = reloj()
    funciona, detalle, admite_opciones = _probar_modelo(sesion_sql, modelo)
    if funciona:
        forma = "opciones" if admite_opciones else "simple"
        return {"modelo": modelo, "responde": True, "respuesta": detalle, "forma": forma}

    alternativas: list[str] = []
    sin_probar: list[str] = []
    for candidato in candidatos:
        if candidato == modelo:
            continue
        if reloj() - inicio >= presupuesto:
            sin_probar.append(candidato)
            continue
        responde, _, _ = _probar_modelo(sesion_sql, candidato, probar_opciones=admite_opciones)
        if responde:
            alternativas.append(candidato)
        if len(alternativas) >= 2:
            break

    if alternativas:
        raise RuntimeError(
            f"El modelo configurado «{modelo}» no responde ({detalle}). "
            f"En esta cuenta sí responden: {', '.join(alternativas)}. "
            f"Ponga SF_CORTEX_MODEL = {alternativas[0]} en Railway y redespliegue."
        )
    pendientes = (
        f" No dio tiempo a probar {', '.join(sin_probar)}: repita la prueba para descartarlos."
        if sin_probar
        else ""
    )
    raise RuntimeError(
        f"Ningún modelo de Cortex COMPLETE responde en esta cuenta. Con «{modelo}»: {detalle}.{pendientes} "
        "Causas habituales, en orden: (1) falta el permiso, ejecute "
        "GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <su SF_ROLE>; "
        "(2) la región de la cuenta no aloja modelos de generación y hace falta habilitar la "
        "inferencia entre regiones con ACCOUNTADMIN: "
        "ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION'; "
        "(3) el nombre del modelo ya no existe. El asistente sigue funcionando: entrega la tabla, "
        "la consulta y un resumen construido con los datos."
    )
