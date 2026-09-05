"""
Orquestador del asistente: pregunta → SQL → datos → texto verificado.

Emite un evento por etapa para que la interfaz muestre en qué va, entrega la
tabla en cuanto Snowflake responde (evento ``resultado``) y termina con un
evento ``final`` que trae el texto y los metadatos. Si la consulta falla, se le
pide **una** corrección a Cortex Analyst informándole el error exacto.

Cada salida —éxito, degradación, rechazo, fallo o detención— deja un registro
de telemetría con sus tiempos, y cada resultado queda guardado en el servidor
por ``consulta_id`` para descargarlo completo y para dar continuidad al hilo.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pandas as pd

from backend.config import (
    ALLOWED_SCHEMAS,
    APP_VERSION,
    CORTEX_MODEL,
    ENTORNO_APP,
    EXPORT_INCLUDE_CONTACT_FIELDS,
    IA_ADVERTENCIA,
    IA_HISTORY_TURNS,
    IA_MAX_QUESTION_CHARS,
    IA_MAX_ROWS,
    IA_MAX_ROWS_CLIENT,
    IA_RESULT_CAPACITY,
    IA_RESULT_TTL,
)
from backend.database import redactar as redactar_secreto
from backend.ia import forma, graficos
from backend.ia.analyst import ClienteAnalyst, ErrorAnalyst, RespuestaAnalyst
from backend.ia.guardas import VerificacionCifras, validar_sql, verificar_cifras
from backend.ia.redactor import redactar as redactar_texto
from backend.ia.redactor import resumen_determinista
from backend.ia.resultados import AlmacenResultados, ResultadoGuardado

logger = logging.getLogger("tejido.ia")

#: Estados posibles de una consulta en la telemetría.
ESTADOS = (
    "exito", "degradada", "sin_sql", "rechazada", "fallo_sql", "fallo_analyst",
    "error_interno", "detenida", "pregunta_invalida",
)


def _valor(dato: Any) -> Any:
    """Convierte lo que devuelve pandas a algo que se pueda serializar a JSON."""
    if dato is None or (isinstance(dato, float) and pd.isna(dato)):
        return None
    if isinstance(dato, (pd.Timestamp,)):
        return dato.isoformat()
    if hasattr(dato, "item"):
        try:
            return dato.item()
        except (ValueError, AttributeError):
            return str(dato)
    return dato


def _ms(desde: float) -> int:
    return int((time.monotonic() - desde) * 1000)


class Orquestador:
    """Coordina Cortex Analyst, las guardas, la ejecución, la redacción y el registro."""

    def __init__(
        self,
        servicio: Any,
        cliente: ClienteAnalyst | None = None,
        almacen: AlmacenResultados | None = None,
        telemetria: Any = None,
    ) -> None:
        self._servicio = servicio
        self._cliente = cliente or ClienteAnalyst()
        self._almacen = almacen or AlmacenResultados(IA_RESULT_CAPACITY, IA_RESULT_TTL)
        self._telemetria = telemetria

    @property
    def almacen(self) -> AlmacenResultados:
        return self._almacen

    # ── Historial ────────────────────────────────────────────────────────
    def _turnos_previos(
        self, consulta_ids: list[str] | None, historial_cliente: list[dict[str, Any]] | None
    ) -> list[dict[str, Any]]:
        """Turnos previos para Analyst.

        Primero desde el servidor: por cada ``consulta_id`` guardado se reenvía la
        pregunta y el contenido **real** que Analyst devolvió (no una
        reconstrucción). Si la caché no los tiene —pestaña abierta con una versión
        anterior o resultado vencido— se usa el historial que manda el navegador,
        que el modelo de entrada ya validó.
        """
        mensajes: list[dict[str, Any]] = []
        for consulta_id in (consulta_ids or [])[-max(1, IA_HISTORY_TURNS // 2):]:
            guardado = self._almacen.obtener(consulta_id)
            if guardado is None or not guardado.sql:
                continue
            mensajes.append({"role": "user", "content": [{"type": "text", "text": guardado.pregunta}]})
            mensajes.append(
                {
                    "role": "analyst",
                    "content": guardado.contenido_crudo or [{"type": "sql", "statement": guardado.sql}],
                }
            )
        if mensajes:
            return mensajes[-IA_HISTORY_TURNS:]
        limpio: list[dict[str, Any]] = []
        for turno in historial_cliente or []:
            papel = turno.get("role")
            contenido = turno.get("content")
            if papel in {"user", "analyst"} and isinstance(contenido, list):
                limpio.append({"role": papel, "content": contenido})
        return limpio[-IA_HISTORY_TURNS:]

    @staticmethod
    def _historial_con_error(
        historial: list[dict[str, Any]], pregunta: str, respuesta: RespuestaAnalyst
    ) -> list[dict[str, Any]]:
        """Conversación hasta la SQL que falló: …, usuario(pregunta), analista(SQL).

        La pregunta que originó la consulta tiene que ir **antes** del turno del
        analista: sin ella el modelo recibe la orden de corregir una SQL cuya
        pregunta no ha visto, y los mensajes dejan de alternar usuario/analista.
        La petición de corrección viaja como la pregunta de esta llamada, que es
        lo que `ClienteAnalyst.preguntar` añade al final.
        """
        nuevo = list(historial)
        nuevo.append({"role": "user", "content": [{"type": "text", "text": pregunta}]})
        nuevo.append(
            {"role": "analyst", "content": respuesta.contenido_crudo or [{"type": "text", "text": respuesta.interpretacion}]}
        )
        return nuevo

    @staticmethod
    def _peticion_de_correccion(error: str) -> str:
        return (
            "La consulta anterior falló al ejecutarse con este error exacto: "
            f"{error[:400]}. Corrígela y devuelve una sola consulta válida."
        )

    # ── Flujo principal ──────────────────────────────────────────────────
    def procesar(
        self,
        pregunta: str,
        historial: list[dict[str, Any]] | None = None,
        consulta_ids: list[str] | None = None,
        sesion_id: str = "",
        cancelado: threading.Event | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Genera los eventos del flujo completo para una pregunta.

        Args:
            historial: Turnos previos enviados por el navegador (respaldo).
            consulta_ids: Identificadores de las respuestas anteriores del hilo;
                el historial real se reconstruye desde el servidor con ellos.
            sesion_id: Identificador de la pestaña, sólo para la telemetría.
            cancelado: Se activa cuando el navegador cerró la conexión; el flujo
                no sigue con etapas que nadie va a leer.

        Yields:
            Diccionarios con ``tipo`` en {``etapa``, ``resultado``, ``error``, ``final``}.
        """
        consulta_id = uuid.uuid4().hex[:12]
        inicio = time.monotonic()
        pregunta = (pregunta or "").strip()
        registro = self._registro_base(consulta_id, sesion_id, pregunta)

        if not pregunta:
            yield self._error(consulta_id, "Escriba una pregunta para comenzar.")
            self._registrar(registro, "pregunta_invalida", inicio, error="pregunta vacía")
            return
        if len(pregunta) > IA_MAX_QUESTION_CHARS:
            yield self._error(
                consulta_id,
                f"La pregunta supera los {IA_MAX_QUESTION_CHARS} caracteres. Divídala en dos más concretas.",
            )
            self._registrar(registro, "pregunta_invalida", inicio, error="pregunta demasiado larga")
            return

        turnos = self._turnos_previos(consulta_ids, historial)
        try:
            # 1 · Cortex Analyst propone la consulta ------------------------
            yield self._etapa(consulta_id, "interpretando", "Interpretando la pregunta…", inicio)
            t_analyst = time.monotonic()
            respuesta = self._cliente.preguntar(pregunta, turnos)
            ms_analyst = _ms(t_analyst)
            registro.update(
                ms_interpretacion=ms_analyst, analyst_request_id=respuesta.request_id, sql_generada=respuesta.sql
            )

            if not respuesta.sql:
                texto = respuesta.interpretacion or (
                    "No logré convertir esa pregunta en una consulta sobre la base. Intente ser más "
                    "concreto: mencione qué quiere contar o sumar y por cuál criterio agruparlo."
                )
                yield self._final(
                    consulta_id,
                    texto=texto,
                    meta=self._meta(ms_analyst=ms_analyst, inicio=inicio, request_id=respuesta.request_id),
                    sql="",
                    columnas=[],
                    filas=[],
                    n_filas=0,
                    truncado=False,
                    grafica=None,
                    mostrar_grafica=False,
                    es_listado=False,
                    n_nits=0,
                    sugerencias=respuesta.sugerencias,
                )
                self._registrar(registro, "sin_sql", inicio, respuesta=texto)
                return

            # 2 · Las guardas deciden si esa consulta se ejecuta ------------
            yield self._etapa(consulta_id, "validando", "Revisando que la consulta sea de solo lectura…", inicio)
            validada = validar_sql(respuesta.sql, ALLOWED_SCHEMAS, IA_MAX_ROWS)
            if not validada.ok:
                logger.warning("[%s] SQL rechazada por las guardas: %s", consulta_id, validada.motivo)
                yield self._error(
                    consulta_id,
                    f"La consulta generada no pasó la revisión de seguridad: {validada.motivo} "
                    "Reformule la pregunta.",
                )
                self._registrar(registro, "rechazada", inicio, etapa_fallo="validando", error=validada.motivo)
                return
            registro["sql_validada"] = validada.sql
            yield self._etapa(consulta_id, "consultando", "Consultando la base en Snowflake…", inicio, sql=validada.sql)

            # 3 · Ejecución, con una corrección si Snowflake la rechaza -----
            t_sql = time.monotonic()
            marco, error = self._ejecutar(validada.sql)
            ms_sql = _ms(t_sql)
            ms_correccion = 0
            intentos = 1
            sql_final = validada.sql
            contenido_crudo = respuesta.contenido_crudo
            if marco is None:
                if self._detenido(cancelado):
                    # La consulta sí se ejecutó: su tiempo y sus intentos deben quedar
                    # registrados aunque el navegador se haya ido antes de la corrección.
                    self._registrar(
                        registro,
                        "detenida",
                        inicio,
                        etapa_fallo="consultando",
                        error=redactar_secreto(error),
                        ms_consulta=ms_sql,
                        intentos_sql=intentos,
                    )
                    return
                yield self._etapa(consulta_id, "corrigiendo", "La consulta falló; pidiendo una corrección…", inicio)
                t_correccion = time.monotonic()
                try:
                    segunda = self._cliente.preguntar(
                        self._peticion_de_correccion(error),
                        self._historial_con_error(turnos, pregunta, respuesta),
                    )
                except ErrorAnalyst as exc:
                    segunda = RespuestaAnalyst()
                    error = f"{error} | al corregir: {exc}"
                ms_correccion = _ms(t_correccion)
                if segunda.sql:
                    validada2 = validar_sql(segunda.sql, ALLOWED_SCHEMAS, IA_MAX_ROWS)
                    if validada2.ok:
                        sql_final = validada2.sql
                        intentos = 2
                        contenido_crudo = segunda.contenido_crudo or contenido_crudo
                        registro["sql_validada"] = sql_final
                        yield self._etapa(
                            consulta_id, "consultando", "Reintentando con la consulta corregida…", inicio, sql=sql_final
                        )
                        t_sql = time.monotonic()
                        marco, error = self._ejecutar(sql_final)
                        ms_sql += _ms(t_sql)
                    else:
                        error = f"{error} | la corrección tampoco pasó la revisión: {validada2.motivo}"
            registro.update(ms_consulta=ms_sql, ms_correccion=ms_correccion, intentos_sql=intentos)

            if marco is None:
                yield self._error(
                    consulta_id,
                    f"Snowflake no pudo ejecutar la consulta: {redactar_secreto(error)[:300]}",
                )
                self._registrar(registro, "fallo_sql", inicio, etapa_fallo="consultando", error=redactar_secreto(error))
                return

            # 4 · Forma del resultado --------------------------------------
            columnas_tecnicas = [str(columna) for columna in marco.columns]
            filas = [[_valor(dato) for dato in fila] for fila in marco.itertuples(index=False, name=None)]
            if not EXPORT_INCLUDE_CONTACT_FIELDS:
                # La misma regla que gobierna la descarga estándar: si el
                # despliegue retira el contacto, el asistente tampoco lo muestra.
                conservar = [i for i, columna in enumerate(columnas_tecnicas) if not forma.es_columna_contacto(columna)]
                if len(conservar) != len(columnas_tecnicas):
                    columnas_tecnicas = [columnas_tecnicas[i] for i in conservar]
                    filas = [[fila[i] for i in conservar] for fila in filas]
            columnas = forma.columnas_legibles(columnas_tecnicas)
            n_filas = len(filas)
            truncado = n_filas >= IA_MAX_ROWS
            nits = forma.nits_del_resultado(columnas_tecnicas, filas)
            grafica = graficos.sugerir(columnas, filas)
            # La gráfica se abre sola si la pregunta la pide o si es un indicador
            # (una cifra sola no es una gráfica: es el titular del resultado).
            mostrar_grafica = grafica is not None and (grafica["tipo"] == "indicador" or graficos.pide_grafica(pregunta))
            registro.update(n_filas=n_filas, truncado=truncado, es_listado=bool(nits), mostro_grafica=mostrar_grafica)

            self._almacen.guardar(
                ResultadoGuardado(
                    consulta_id=consulta_id,
                    sesion_id=sesion_id,
                    pregunta=pregunta,
                    sql=sql_final,
                    columnas=columnas,
                    columnas_tecnicas=columnas_tecnicas,
                    filas=filas,
                    n_filas=n_filas,
                    truncado=truncado,
                    nits=nits,
                    contenido_crudo=contenido_crudo,
                    request_id=respuesta.request_id,
                )
            )
            yield self._etapa(consulta_id, "datos", f"{n_filas} fila(s) obtenidas en {ms_sql} ms.", inicio)

            # La tabla, la gráfica y la SQL ya están listas: se entregan ahora,
            # sin esperar a la redacción. El usuario puede leer y descargar el
            # resultado mientras se escribe el resumen, que es la parte lenta.
            cuerpo = {
                "sql": sql_final,
                "columnas": columnas,
                "filas": filas[:IA_MAX_ROWS_CLIENT],
                "n_filas": n_filas,
                "truncado": truncado or n_filas > IA_MAX_ROWS_CLIENT,
                "grafica": grafica,
                "mostrar_grafica": mostrar_grafica,
                "es_listado": bool(nits),
                "n_nits": len(nits),
                "sugerencias": respuesta.sugerencias,
            }
            yield {"tipo": "resultado", "consulta_id": consulta_id, "advertencia": IA_ADVERTENCIA, **cuerpo}

            if self._detenido(cancelado):
                self._registrar(registro, "detenida", inicio, etapa_fallo="redactando")
                return

            # 5 · Redacción dentro de Snowflake ----------------------------
            yield self._etapa(consulta_id, "redactando", "Redactando la respuesta…", inicio)
            t_redaccion = time.monotonic()
            redaccion = redactar_texto(
                self._servicio.filas_con_parametros,
                pregunta,
                columnas,
                filas,
                n_filas,
                truncado,
                CORTEX_MODEL,
                consulta_id,
            )
            ms_redaccion = _ms(t_redaccion)

            # 6 · Ninguna cifra sin respaldo -------------------------------
            # Sólo se revisa lo que escribió el modelo: el resumen determinista se
            # construye con la propia tabla, y volver a examinarlo únicamente podría
            # borrar la causa real de una degradación anterior.
            verificacion = (
                VerificacionCifras(ok=True)
                if redaccion.degradado
                else verificar_cifras(redaccion.texto, filas, n_filas, pregunta, truncado)
            )
            if not verificacion.ok:
                logger.warning(
                    "[%s] Cifras sin respaldo en la redacción (%s); se entrega el resumen de los datos.",
                    consulta_id,
                    verificacion.huerfanas[:5],
                )
                redaccion.texto = resumen_determinista(columnas, filas, n_filas, truncado)
                redaccion.modelo, redaccion.degradado = "", True
                redaccion.motivo = "cifras_sin_respaldo"
                redaccion.error = "Cifras sin respaldo en la tabla: " + ", ".join(verificacion.huerfanas[:5])

            self._almacen.actualizar(
                consulta_id, texto=redaccion.texto, degradado=redaccion.degradado, motivo_degradacion=redaccion.motivo
            )
            self._auditar(pregunta, sql_final, n_filas)
            meta = self._meta(
                ms_analyst=ms_analyst,
                ms_sql=ms_sql,
                ms_correccion=ms_correccion,
                ms_redaccion=ms_redaccion,
                intentos=intentos,
                request_id=respuesta.request_id,
                modelo=redaccion.modelo,
                degradado=redaccion.degradado,
                motivo=redaccion.motivo,
                detalle=redaccion.error,
                cifras_ok=verificacion.ok,
                forma_redaccion=redaccion.forma,
                inicio=inicio,
            )
            yield self._final(consulta_id, texto=redaccion.texto, meta=meta, **cuerpo)
            registro.update(
                ms_redaccion=ms_redaccion,
                degradado=redaccion.degradado,
                motivo_degradacion=redaccion.motivo,
                cifras_verificadas=verificacion.ok,
                respuesta=redaccion.texto,
                error=redaccion.error,
            )
            self._registrar(registro, "degradada" if redaccion.degradado else "exito", inicio)
        except ErrorAnalyst as exc:
            logger.warning("[%s] Cortex Analyst no respondió: %s", consulta_id, exc)
            yield self._error(consulta_id, str(exc))
            self._registrar(registro, "fallo_analyst", inicio, etapa_fallo="interpretando", error=str(exc))
        except Exception as exc:  # noqa: BLE001 - frontera del servicio
            logger.exception("[%s] Fallo inesperado del asistente", consulta_id)
            yield self._error(
                consulta_id,
                f"El asistente encontró un error inesperado: {redactar_secreto(exc)[:200]}",
            )
            self._registrar(registro, "error_interno", inicio, etapa_fallo="interno", error=redactar_secreto(exc))

    # ── Auxiliares ───────────────────────────────────────────────────────
    def _ejecutar(self, sql: str) -> tuple[pd.DataFrame | None, str]:
        try:
            return self._servicio.dataframe(sql), ""
        except Exception as exc:  # noqa: BLE001 - el texto viaja a la corrección
            return None, str(exc)

    @staticmethod
    def _detenido(cancelado: threading.Event | None) -> bool:
        return cancelado is not None and cancelado.is_set()

    def _auditar(self, pregunta: str, sql: str, n_filas: int) -> None:
        try:
            self._servicio.log_event("Asistente", "Asistente IA", f"{n_filas} filas", pregunta[:900])
        except Exception:  # noqa: BLE001 - la auditoría nunca rompe el flujo
            return

    @staticmethod
    def _registro_base(consulta_id: str, sesion_id: str, pregunta: str) -> dict[str, Any]:
        return {
            "consulta_id": consulta_id,
            "sesion_id": sesion_id,
            "pregunta": pregunta,
            "sql_generada": "",
            "sql_validada": "",
            "respuesta": "",
            "estado": "",
            "exito": False,
            "degradado": False,
            "motivo_degradacion": "",
            "cifras_verificadas": False,
            "n_filas": 0,
            "truncado": False,
            "es_listado": False,
            "mostro_grafica": False,
            "ms_interpretacion": 0,
            "ms_consulta": 0,
            "ms_correccion": 0,
            "ms_redaccion": 0,
            "ms_total": 0,
            "intentos_sql": 0,
            "modelo": CORTEX_MODEL,
            "analyst_request_id": "",
            "etapa_fallo": "",
            "error": "",
            "app_version": APP_VERSION,
            "vista_semantica": "",
            "entorno": ENTORNO_APP,
        }

    def _registrar(self, registro: dict[str, Any], estado: str, inicio: float, **campos: Any) -> None:
        """Deja el registro de telemetría de cualquier salida; nunca interrumpe el flujo."""
        registro.update(campos)
        registro["estado"] = estado
        registro["exito"] = estado in {"exito", "degradada"}
        registro["ms_total"] = _ms(inicio)
        registro["vista_semantica"] = self._cliente.vista_semantica
        if self._telemetria is None:
            return
        try:
            self._telemetria.registrar_consulta(registro)
        except Exception:  # noqa: BLE001
            logger.exception("[%s] No se pudo encolar la telemetría", registro.get("consulta_id"))

    def _etapa(self, consulta_id: str, etapa: str, detalle: str, inicio: float, **extra: Any) -> dict[str, Any]:
        return {"tipo": "etapa", "consulta_id": consulta_id, "etapa": etapa, "detalle": detalle, "ms": _ms(inicio), **extra}

    def _error(self, consulta_id: str, mensaje: str) -> dict[str, Any]:
        return {"tipo": "error", "consulta_id": consulta_id, "mensaje": mensaje}

    def _meta(
        self,
        *,
        inicio: float,
        ms_analyst: int = 0,
        ms_sql: int = 0,
        ms_correccion: int = 0,
        ms_redaccion: int = 0,
        intentos: int = 0,
        request_id: str = "",
        modelo: str = "",
        degradado: bool = False,
        motivo: str = "",
        detalle: str = "",
        cifras_ok: bool = True,
        forma_redaccion: str = "",
    ) -> dict[str, Any]:
        return {
            "modelo": modelo,
            "degradado": degradado,
            "motivo_degradacion": motivo,
            # La causa real, ya sin secretos: quien mira la pantalla no debería tener
            # que abrir /estado ni los registros para saber por qué se degradó.
            "detalle_degradacion": detalle[:300],
            "cifras_verificadas": cifras_ok,
            "forma_redaccion": forma_redaccion,
            "ms_interpretacion": ms_analyst,
            "ms_consulta": ms_sql,
            "ms_correccion": ms_correccion,
            "ms_redaccion": ms_redaccion,
            "ms_total": _ms(inicio),
            "intentos_sql": intentos,
            "analyst_request_id": request_id,
            "version": APP_VERSION,
            "vista_semantica": self._cliente.vista_semantica,
        }

    def _final(self, consulta_id: str, *, texto: str, meta: dict[str, Any], **datos: Any) -> dict[str, Any]:
        return {
            "tipo": "final",
            "consulta_id": consulta_id,
            "texto": texto,
            "advertencia": IA_ADVERTENCIA,
            "meta": meta,
            **datos,
        }
